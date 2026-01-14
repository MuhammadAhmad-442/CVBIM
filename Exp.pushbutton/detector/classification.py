# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
CLASSIFICATION.PY - SIDE, FLOOR & DOOR CLASSIFICATION (FIXED FOR CFS)
═══════════════════════════════════════════════════════════════════════════
"""
from config import STUD_HEIGHT_THRESHOLD_MM, SIDE_WEIGHTS, INTERIOR_THRESHOLD, Log, SIDES
from core import dims, mid_xy, center_z, compute_bounds, init_side_summary, get_element_id

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


def classify_windows(window_elems, view, bounds, side_summary):
    """Assign windows to sides (modifies side_summary in-place)."""
    for e in window_elems:
        d = dims(e, view)
        if not d:
            continue
        
        cx, cy = mid_xy(d)
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
# SECTION 3: PANEL CLASSIFICATION (NO GROUPING - CLASSIFY INDIVIDUAL ELEMENTS)
# ═══════════════════════════════════════════════════════════════════════════

def classify_all_panels(panel_elems, view):
    """
    Classify all panel ELEMENTS by side and floor.
    Uses your reference logic - NO grouping of sub-elements.
    
    Returns:
        tuple: (side_summary, bounds, floor_split, panel_groups)
    """
    Log.section("CLASSIFYING PANELS")
    
    # STEP 1: Compute bounds from panel elements
    xs, ys = [], []
    for e in panel_elems:
        d = dims(e, view)
        if not d:
            continue
        xs.extend([d[3], d[4]])
        ys.extend([d[5], d[6]])
    
    if not xs or not ys:
        raise Exception("Could not determine building bounds - no panel data")
    
    bounds = (min(xs), max(xs), min(ys), max(ys))
    Log.info("Bounds: xmin=%.2f xmax=%.2f ymin=%.2f ymax=%.2f", *bounds)
    
    # STEP 2: Compute floor split
    floor_split = compute_floor_split(panel_elems, view)
    Log.info("Floor split: %.2f mm", floor_split)
    
    # STEP 3: Initialize side summary
    side_summary = init_side_summary()
    
    # STEP 4: Classify each panel element individually
    for p in panel_elems:
        pid = p.Id.IntegerValue
        d = dims(p, view)
        if not d:
            continue
        
        # Classify side (nearest facade)
        cx, cy = mid_xy(d)
        side = classify_side(cx, cy, bounds)
        
        # Classify floor (by Z position)
        floor = classify_floor(d, floor_split)
        
        # Add to all relevant lists
        side_summary[side]["wall_panels"].append(pid)
        side_summary[side][floor].append(pid)
    
    # STEP 5: Create panel_groups for export compatibility
    # Each "group" is actually just one element, but we create the structure
    panel_groups = []
    group_id = 1
    
    for p in panel_elems:
        d = dims(p, view)
        if not d:
            continue
        
        cx, cy = mid_xy(d)
        z = center_z(d)
        floor_label = "floor1" if z < floor_split else "floor2"
        
        panel_groups.append({
            "id": group_id,
            "elements": [p],
            "element_ids": [p.Id.IntegerValue],
            "center": (cx, cy),
            "xmin": d[3],
            "xmax": d[4],
            "ymin": d[5],
            "ymax": d[6],
            "zmin": d[7],
            "zmax": d[8],
            "floor": floor_label
        })
        group_id += 1
    
    Log.info("Created %d panel groups (1 element each)", len(panel_groups))
    
    # Log summary
    for s in SIDES:
        Log.info("Side %s: %d panels (floor1=%d, floor2=%d)", 
                s,
                len(side_summary[s]["wall_panels"]),
                len(side_summary[s]["floor1"]),
                len(side_summary[s]["floor2"]))
    
    return side_summary, bounds, floor_split, panel_groups

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: DOOR COMPONENT PROCESSING
# ═══════════════════════════════════════════════════════════════════════════

def split_studs_headers(door_elems, view):
    """
    Split door elements into studs (tall/vertical) and headers (short/horizontal).
    Uses 500mm threshold.
    
    Returns:
        tuple: (studs, headers) - each is list of (element, dims)
    """
    studs = []
    headers = []
    
    Log.info("Analyzing %d door elements...", len(door_elems))
    Log.info("Using threshold: 500.0 mm (height > 500mm = stud)")
    
    for e in door_elems:
        d = dims(e, view)
        if not d:
            continue
        
        height = d[2]
        width = d[0]
        
        # Get element name for debugging
        fam, typ = "", ""
        try:
            fam = e.Symbol.Family.Name
            typ = e.Symbol.Name
        except:
            pass
        
        # Use 500mm threshold
        if height > 500.0:
            studs.append((e, d))
            Log.info("  STUD: %s %s | H=%.1fmm W=%.1fmm ID=%d", 
                     fam, typ, height, width, e.Id.IntegerValue)
        else:
            headers.append((e, d))
            Log.info("  HEADER: %s %s | H=%.1fmm W=%.1fmm ID=%d", 
                     fam, typ, height, width, e.Id.IntegerValue)
    
    Log.info("Found %d studs, %d headers", len(studs), len(headers))
    
    if len(studs) < 2:
        Log.warn("Not enough studs found: %d (need at least 2 per door)", len(studs))
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
    floor1 = sorted(studs_sorted[0:2], key=lambda sd: mid_xy(sd[1])[0])  # by X
    floor2 = sorted(studs_sorted[2:4], key=lambda sd: mid_xy(sd[1])[0])
    
    pairs = [(floor1[0], floor1[1]), (floor2[0], floor2[1])]
    
    Log.debug("Door pairs created: %d", len(pairs))
    return pairs


def build_door_groups(pairs):
    """
    Create door group metadata from stud pairs.
    """
    groups = []
    
    for idx, ((eL, dL), (eR, dR)) in enumerate(pairs, 1):
        cxL, cyL = mid_xy(dL)
        cxR, cyR = mid_xy(dR)
        
        groups.append({
            "id": idx,
            "stud_left": get_element_id(eL),
            "stud_right": get_element_id(eR),
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
        cxL, _ = mid_xy(dL)
        cxR, _ = mid_xy(dR)
        width = abs(cxR - cxL)
        height = abs(dH[7] - min(dL[7], dR[7]))  # header bottom - stud bottom
        
        door_output.append({
            "door": idx,
            "stud_left": get_element_id(eL),
            "stud_right": get_element_id(eR),
            "header": get_element_id(eH),
            "width_mm": width,
            "height_mm": height,
            "dims_left": dL,
            "dims_right": dR,
            "dims_header": dH
        })
        
        Log.info("Door %d: studs=%d,%d, header=%d, size=%.0fx%.0fmm",
                idx, get_element_id(eL), get_element_id(eR), 
                get_element_id(eH), width, height)
    
    return door_output

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: YOLO SIDE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_yolo_side(yolo_detections, bim_export):
    """
    Classify which facade side the YOLO image shows.
    Updated to work with structured BIM export.
    
    Returns:
        tuple: (best_side, score)
    """
    if not yolo_detections:
        return "INTERIOR", 0.0
    
    sides = list(bim_export.get("sides", {}).keys())
    if not sides:
        return "INTERIOR", 0.0
    
    # Group BIM by side & type (from structured export)
    bim_by_side = {s: {"door": [], "windows": [], "wall_panels": []} 
                   for s in sides}
    
    for side, side_data in bim_export.get("sides", {}).items():
        for elem in side_data.get("elements", []):
            elem_type = elem["type"]
            bim_by_side[side][elem_type].append(elem)
    
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