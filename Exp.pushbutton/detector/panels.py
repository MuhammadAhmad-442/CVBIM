# -*- coding: utf-8 -*-
"""
Panel classification: sides (A/B/C/D) and floors (1/2).
"""
from Autodesk.Revit.DB import *
from geometry import dims
from config import FACADE_SIDES
from logger import Logger

# ============================================================
# INITIALIZATION
# ============================================================

def init_side_summary():
    """
    Initialize empty side summary structure.
    
    Returns:
        dict: Standardized side summary with all expected keys
    """
    return {
        side: {
            "panels": [],
            "panels_floor1": [],
            "panels_floor2": [],
            "floor1": [],  # Alias for panels_floor1
            "floor2": [],  # Alias for panels_floor2
            "windows": [],
            "door": []
        }
        for side in FACADE_SIDES
    }


# ============================================================
# BUILDING BOUNDS
# ============================================================

def compute_global_bounds(panel_elems, view):
    """
    Compute global building bounds from panel bounding boxes.
    
    Returns:
        tuple: (xmin, xmax, ymin, ymax) in mm
    """
    xs, ys = [], []
    
    for e in panel_elems:
        d = dims(e, view)
        if not d:
            continue
        
        xs.extend([d[3], d[4]])  # xmin, xmax
        ys.extend([d[5], d[6]])  # ymin, ymax
    
    if not xs or not ys:
        raise Exception("Could not determine building extents. No panel bbox found.")
    
    bounds = (min(xs), max(xs), min(ys), max(ys))
    Logger.debug("Global bounds: xmin=%.2f, xmax=%.2f, ymin=%.2f, ymax=%.2f", *bounds)
    return bounds


# ============================================================
# FLOOR CLASSIFICATION
# ============================================================

def compute_floor_split_z(panel_elems, view):
    """
    Compute Z-height threshold between floors using median.
    
    Args:
        panel_elems: List of panel elements
        view: Active view
    
    Returns:
        float: Z-coordinate (mm) separating floor1 from floor2
    """
    zmids = []
    for p in panel_elems:
        d = dims(p, view)
        if d:
            zmids.append((d[7] + d[8]) / 2.0)
    
    if not zmids:
        raise Exception("No Z values found for panel bboxes.")
    
    zmids_sorted = sorted(zmids)
    floor_split_z = zmids_sorted[len(zmids) // 2]
    
    Logger.debug("Floor split Z: %.2f mm", floor_split_z)
    return floor_split_z


def classify_panel_floor(d, floor_split_z):
    """
    Classify panel as floor1 or floor2 based on Z midpoint.
    
    Args:
        d: dims tuple
        floor_split_z: Z-threshold between floors
    
    Returns:
        str: "floor1" or "floor2"
    """
    zmin, zmax = d[7], d[8]
    zmid = (zmin + zmax) / 2.0
    return "floor1" if zmid < floor_split_z else "floor2"


# ============================================================
# SIDE CLASSIFICATION
# ============================================================

def classify_panel_side(d, bounds):
    """
    Classify panel to nearest facade side (A/B/C/D).
    
    Args:
        d: dims tuple
        bounds: (xmin, xmax, ymin, ymax) building bounds
    
    Returns:
        str: "A", "B", "C", or "D"
    """
    xmin_b, xmax_b, ymin_b, ymax_b = bounds
    
    xmin, xmax = d[3], d[4]
    ymin, ymax = d[5], d[6]
    
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    
    # Distance to each side
    dA = abs(cx - xmin_b)  # left
    dC = abs(cx - xmax_b)  # right
    dB = abs(cy - ymin_b)  # bottom
    dD = abs(cy - ymax_b)  # top
    
    dmin = min(dA, dB, dC, dD)
    
    if dmin == dA:
        return "A"
    if dmin == dC:
        return "C"
    if dmin == dB:
        return "B"
    return "D"


# ============================================================
# DOOR CLASSIFICATION
# ============================================================

def classify_door_side(door_groups, bounds):
    """
    Assign each door to nearest facade side.
    
    Args:
        door_groups: List of door group dicts with 'id' and 'center'
        bounds: Building bounds tuple
    
    Returns:
        dict: {door_id: side}
    """
    xmin_b, xmax_b, ymin_b, ymax_b = bounds
    door_side_map = {}
    
    for d in door_groups:
        did = d["id"]
        cx, cy = d["center"]
        
        dA = abs(cx - xmin_b)
        dC = abs(cx - xmax_b)
        dB = abs(cy - ymin_b)
        dD = abs(cy - ymax_b)
        
        dmin = min(dA, dB, dC, dD)
        
        if dmin == dA:
            side = "A"
        elif dmin == dC:
            side = "C"
        elif dmin == dB:
            side = "B"
        else:
            side = "D"
        
        door_side_map[did] = side
        Logger.debug("Door %d assigned to side %s", did, side)
    
    return door_side_map


# ============================================================
# MASTER CLASSIFICATION
# ============================================================

def classify_all_panels(panel_elems, view):
    """
    Classify all panels by side (A/B/C/D) and floor (1/2).
    
    Args:
        panel_elems: List of panel elements
        view: Active view
    
    Returns:
        dict: side_summary with classified panels
    """
    Logger.subsection("Classifying Panels")
    
    # Compute bounds and floor split
    bounds = compute_global_bounds(panel_elems, view)
    floor_split_z = compute_floor_split_z(panel_elems, view)
    
    # Initialize structure
    side_summary = init_side_summary()
    
    # Classify each panel
    for p in panel_elems:
        pid = p.Id.IntegerValue
        d = dims(p, view)
        if not d:
            continue
        
        side = classify_panel_side(d, bounds)
        floor = classify_panel_floor(d, floor_split_z)
        
        # Add to all relevant lists
        side_summary[side]["panels"].append(pid)
        side_summary[side]["panels_" + floor].append(pid)
        side_summary[side][floor].append(pid)  # Alias
    
    # Log results
    for side in FACADE_SIDES:
        Logger.info("Side %s: %d panels (floor1=%d, floor2=%d)",
                   side,
                   len(side_summary[side]["panels"]),
                   len(side_summary[side]["floor1"]),
                   len(side_summary[side]["floor2"]))
    
    return side_summary