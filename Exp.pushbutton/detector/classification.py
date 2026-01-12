# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
CLASSIFICATION.PY - SIDE, FLOOR & DOOR CLASSIFICATION
═══════════════════════════════════════════════════════════════════════════

PURPOSE:
    Classify building elements by:
        - Side (A/B/C/D facades)
        - Floor (1/2)
        - Door grouping (studs + headers)

SECTIONS:
    1. Floor Classification
    2. Side Classification (Panels & Doors)
    3. Door Component Processing
    4. YOLO Side Classification
═══════════════════════════════════════════════════════════════════════════
"""
from config import STUD_HEIGHT_THRESHOLD_MM, SIDE_WEIGHTS, INTERIOR_THRESHOLD, Log, SIDES
from core import dims, center_xy, center_z, compute_bounds, init_side_summary
from core import dims, center_xy, center_z, compute_bounds, init_side_summary, get_element_id

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: FLOOR CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def compute_floor_split(panel_elems, view):
    """
    Calculate Z-height threshold between floors using median.
    
    Returns:
        float: Z-coordinate (mm) separating floor1/floor2
    """
    zmids = []
    for p in panel_elems:
        d = dims(p, view)
        if d:
            zmids.append(center_z(d))
    
    if not zmids:
        raise Exception("No panel Z-values found for floor split")
    
    zmids.sort()
    split = zmids[len(zmids) // 2]
    Log.debug("Floor split Z: %.2f mm", split)
    return split


def classify_floor(d, floor_split):
    """Classify element as floor1 or floor2."""
    return "floor1" if center_z(d) < floor_split else "floor2"

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: SIDE CLASSIFICATION (PANELS & DOORS)
# ═══════════════════════════════════════════════════════════════════════════

def classify_side(cx, cy, bounds):
    """
    Classify element to nearest facade side.
    
    Args:
        cx, cy: Element center coordinates
        bounds: (xmin, xmax, ymin, ymax)
    
    Returns:
        str: "A", "B", "C", or "D"
    """
    xmin, xmax, ymin, ymax = bounds
    
    distances = {
        "A": abs(cx - xmin),  # left
        "C": abs(cx - xmax),  # right
        "B": abs(cy - ymin),  # bottom
        "D": abs(cy - ymax)   # top
    }
    
    return min(distances, key=distances.get)


def classify_all_panels(panel_elems, view):
    """
    Classify all panels by side and floor.
    
    Returns:
        tuple: (side_summary, bounds, floor_split)
    """
    Log.section("CLASSIFYING PANELS")
    
    bounds = compute_bounds(panel_elems, view)
    floor_split = compute_floor_split(panel_elems, view)
    side_summary = init_side_summary()
    
    for p in panel_elems:
        pid = p.Id.IntegerValue
        d = dims(p, view)
        if not d:
            continue
        
        cx, cy = center_xy(d)
        side = classify_side(cx, cy, bounds)
        floor = classify_floor(d, floor_split)
        
        side_summary[side]["panels"].append(pid)
        side_summary[side][floor].append(pid)
    
    # Log summary
    for s in SIDES:
        Log.info("Side %s: %d panels (floor1=%d, floor2=%d)", 
                s,
                len(side_summary[s]["panels"]),
                len(side_summary[s]["floor1"]),
                len(side_summary[s]["floor2"]))
    
    return side_summary, bounds, floor_split


def classify_windows(window_elems, view, bounds, side_summary):
    """Assign windows to sides (modifies side_summary in-place)."""
    for e in window_elems:
        d = dims(e, view)
        if not d:
            continue
        
        cx, cy = center_xy(d)
        side = classify_side(cx, cy, bounds)
        side_summary[side]["windows"].append(e.Id.IntegerValue)
    
    total = sum(len(side_summary[s]["windows"]) for s in SIDES)
    Log.info("Assigned %d windows to sides", total)


def classify_doors(door_groups, bounds, side_summary):
    """
    Assign door groups to sides.
    
    Returns:
        dict: {door_id: side}
    """
    door_side_map = {}
    
    for d in door_groups:
        did = d["id"]
        cx, cy = d["center"]
        
        side = classify_side(cx, cy, bounds)
        door_side_map[did] = side
        side_summary[side]["door"].append(did)
        
        Log.debug("Door %d → Side %s", did, side)
    
    return door_side_map

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: DOOR COMPONENT PROCESSING
# ═══════════════════════════════════════════════════════════════════════════

def split_studs_headers(door_elems, view):
    """
    Split door elements into studs (tall/vertical) and headers (short/horizontal).
    
    Returns:
        tuple: (studs, headers) - each is list of (element, dims)
    """
    studs = []
    headers = []
    
    for e in door_elems:
        d = dims(e, view)
        if not d:
            continue
        
        height = d[2]
        if height > STUD_HEIGHT_THRESHOLD_MM:
            studs.append((e, d))
        else:
            headers.append((e, d))
    
    Log.info("Found %d studs, %d headers", len(studs), len(headers))
    
    if len(studs) < 2:
        Log.warn("Not enough studs found: %d", len(studs))
    if len(headers) < 1:
        Log.warn("No headers found")
    
    return studs, headers


def group_door_studs(studs):
    """
    Group 4 studs into 2 door pairs (assumes 2 floors).
    
    Returns:
        list: [(stud_left, stud_right), ...]
    """
    if len(studs) != 4:
        raise Exception("Expected 4 studs, found {}".format(len(studs)))
    
    # Sort by Z (bottom to top)
    studs_sorted = sorted(studs, key=lambda sd: center_z(sd[1]))
    
    # Split into floors
    floor1 = sorted(studs_sorted[0:2], key=lambda sd: center_xy(sd[1])[0])  # by X
    floor2 = sorted(studs_sorted[2:4], key=lambda sd: center_xy(sd[1])[0])
    
    pairs = [(floor1[0], floor1[1]), (floor2[0], floor2[1])]
    
    Log.debug("Door pairs created: %d", len(pairs))
    return pairs


def build_door_groups(pairs):
    """
    Create door group metadata from stud pairs.
    """
    groups = []
    
    for idx, ((eL, dL), (eR, dR)) in enumerate(pairs, 1):
        cxL, cyL = center_xy(dL)
        cxR, cyR = center_xy(dR)
        
        groups.append({
            "id": idx,
            "stud_left": get_element_id(eL),  # FIXED
            "stud_right": get_element_id(eR),  # FIXED
            "center": ((cxL + cxR) / 2.0, (cyL + cyR) / 2.0),
            "dims_left": dL,
            "dims_right": dR
        })
    
    return groups


def match_headers(pairs, headers):
    """
    Assign one header to each door pair based on Z-proximity.
    
    Returns:
        list: [{"door": 1, "stud_left": id, "stud_right": id, "header": id, ...}, ...]
    """
    unused_headers = headers[:]
    door_output = []
    
    for idx, ((eL, dL), (eR, dR)) in enumerate(pairs, 1):
        if not unused_headers:
            Log.warn("No headers left for door %d", idx)
            break
        
        # Find header closest to top of studs
        stud_top_z = min(dL[8], dR[8])  # top Z of studs
        
        best = None
        best_dist = float('inf')
        
        for eH, dH in unused_headers:
            header_z = center_z(dH)
            dist = abs(header_z - stud_top_z)
            if dist < best_dist:
                best_dist = dist
                best = (eH, dH)
        
        if not best:
            Log.warn("No header found for door %d", idx)
            continue
        
        eH, dH = best
        unused_headers.remove(best)
        
        # Calculate door dimensions
        cxL, _ = center_xy(dL)
        cxR, _ = center_xy(dR)
        width = abs(cxR - cxL)
        height = abs(dH[7] - min(dL[7], dR[7]))  # header bottom - stud bottom
        
        door_output.append({
            "door": idx,
            "stud_left": get_element_id(eL),  # FIXED
            "stud_right": get_element_id(eR),  # FIXED
            "header": get_element_id(eH),  # FIXED
            "width_mm": width,
            "height_mm": height,
            "dims_left": dL,
            "dims_right": dR,
            "dims_header": dH
        })
        
        Log.info("Door %d: studs=%d,%d, header=%d, size=%.0fx%.0fmm",
                idx, eL.Id.IntegerValue, eR.Id.IntegerValue, 
                eH.Id.IntegerValue, width, height)
    
    return door_output

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: YOLO SIDE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_yolo_side(yolo_detections, bim_export):
    """
    Classify which facade side the YOLO image shows.
    Uses presence-based scoring (no distance metrics).
    
    Returns:
        tuple: (best_side, score)
    """
    if not yolo_detections:
        return "INTERIOR", 0.0
    
    sides = sorted(bim_export.get("side_widths", {}).keys())
    
    # Group BIM by side & type
    bim_by_side = {s: {"door": [], "windows": [], "wall-panels": []} 
                   for s in sides}
    
    for key in ("door", "windows", "wall-panels"):
        for e in bim_export.get(key, []):
            side = e["side"]
            bim_by_side[side][key].append(e)
    
    # Score each side
    scores = {s: 0.0 for s in sides}
    
    for det in yolo_detections:
        label = det["label"]
        if label == "window":
            label = "windows"  # Normalize
        
        if label not in SIDE_WEIGHTS:
            continue
        
        weight = SIDE_WEIGHTS[label]
        
        for s in sides:
            if len(bim_by_side[s][label]) > 0:
                scores[s] += weight
    
    # Find best
    best_side = max(scores, key=scores.get)
    best_score = scores[best_side]
    
    # Debug table
    Log.section("SIDE CLASSIFICATION")
    print("Object".ljust(18) + "".join(s.rjust(10) for s in sides))
    print("-" * 60)
    
    for det in yolo_detections:
        label = det["label"]
        if label == "window":
            label = "windows"
        
        row = ("{}_{}".format(label, det.get("id", "?"))).ljust(18)
        for s in sides:
            if label in SIDE_WEIGHTS:
                sc = SIDE_WEIGHTS[label] if len(bim_by_side[s][label]) > 0 else 0.0
                row += ("{:.2f}".format(sc)).rjust(10)
            else:
                row += "---".rjust(10)
        print(row)
    
    print("-" * 60)
    print("TOTAL".ljust(18) + "".join("{:.2f}".format(scores[s]).rjust(10) for s in sides))
    print("\nBest: {} (score={:.3f})\n".format(best_side, best_score))
    
    if best_score < INTERIOR_THRESHOLD:
        return "INTERIOR", best_score
    
    return best_side, best_score