# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
CLASSIFICATION.PY - FIXED DOOR PROCESSING + FLOOR CLASSIFICATION
═══════════════════════════════════════════════════════════════════════════
"""
from config import (STUD_HEIGHT_THRESHOLD_MM, SIDE_WEIGHTS, INTERIOR_THRESHOLD, 
                    Log, SIDES, GROUP_PANEL_COMPONENTS, GROUP_DOOR_COMPONENTS,
                    FILTER_INTERIOR_ELEMENTS)
from core import dims, mid_xy, center_z, compute_bounds, init_side_summary, get_element_id, filter_exterior_elements

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: FLOOR CLASSIFICATION (FIXED)
# ═══════════════════════════════════════════════════════════════════════════

def compute_floor_split(panel_elems, view):
    """
    Calculate Z-height threshold between floors using median.
    FIXED: Now uses median of BOTTOM Z values instead of CENTER Z.
    
    Returns:
        float: Z-coordinate (mm) separating floor1/floor2
    """
    z_bottoms = []
    for p in panel_elems:
        d = dims(p, view)
        if d:
            z_bottoms.append(d[7])  # zmin (bottom Z)
    
    if not z_bottoms:
        raise Exception("No panel Z-values found for floor split")
    
    z_bottoms.sort()
    
    # Use median of bottom Z values
    split = z_bottoms[len(z_bottoms) // 2]
    
    Log.debug("Floor split Z: %.2f mm (based on panel bottoms)", split)
    Log.debug("Z-bottom range: %.2f to %.2f mm", min(z_bottoms), max(z_bottoms))
    
    return split


def classify_floor(d, floor_split):
    """
    Classify element as floor1 or floor2.
    FIXED: Now uses BOTTOM Z instead of CENTER Z for more reliable classification.
    """
    bottom_z = d[7]  # zmin
    return "floor1" if bottom_z < floor_split else "floor2"

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
    # Filter exterior windows if enabled
    if FILTER_INTERIOR_ELEMENTS:
        window_elems, interior_count = filter_exterior_elements(window_elems, view, bounds)
        if interior_count > 0:
            Log.info("Filtered out %d interior windows", interior_count)
    
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
# SECTION 3: PANEL GROUPING & CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_all_panels(panel_elems, view):
    """
    Classify all panels by side and floor, optionally group 4 components per panel.
    NOW WITH INTERIOR/EXTERIOR FILTERING.
    
    Returns:
        tuple: (side_summary, bounds, floor_split, panel_groups)
    """
    Log.section("CLASSIFYING PANELS")
    
    if GROUP_PANEL_COMPONENTS:
        Log.info("Panel grouping: ENABLED (4 sub-components → 1 panel)")
    else:
        Log.info("Panel grouping: DISABLED (each element = 1 panel)")
    
    if FILTER_INTERIOR_ELEMENTS:
        Log.info("Interior filtering: ENABLED (exterior elements only)")
    else:
        Log.info("Interior filtering: DISABLED (all elements)")
    
    # STEP 1: Compute bounds from ALL panel elements first
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
    
    # STEP 2: Filter exterior elements if enabled
    original_count = len(panel_elems)
    if FILTER_INTERIOR_ELEMENTS:
        panel_elems, interior_count = filter_exterior_elements(panel_elems, view, bounds)
        Log.info("Filtered panels: %d exterior, %d interior (removed)", len(panel_elems), interior_count)
    
    if not panel_elems:
        raise Exception("No exterior panels found after filtering")
    
    # STEP 3: Compute floor split from FILTERED panels
    floor_split = compute_floor_split(panel_elems, view)
    Log.info("Floor split: %.2f mm", floor_split)
    
    # STEP 4: Initialize side summary
    side_summary = init_side_summary()
    
    # ═══════════════════════════════════════════════════════════════════
    # BRANCHING LOGIC: GROUP vs NO GROUP
    # ═══════════════════════════════════════════════════════════════════
    
    if GROUP_PANEL_COMPONENTS:
        # MODE A: GROUP 4 SUB-COMPONENTS INTO 1 PANEL
        for p in panel_elems:
            pid = p.Id.IntegerValue
            d = dims(p, view)
            if not d:
                continue
            
            cx, cy = mid_xy(d)
            side = classify_side(cx, cy, bounds)
            floor = classify_floor(d, floor_split)
            
            side_summary[side]["wall_panels"].append(pid)
            side_summary[side][floor].append(pid)
        
        Log.info("Classified %d individual panel elements", len(panel_elems))
        
        panel_groups = []
        group_id = 1
        elem_lookup = {e.Id.IntegerValue: e for e in panel_elems}
        
        for side in SIDES:
            for floor in ["floor1", "floor2"]:
                element_ids = side_summary[side][floor]
                
                if len(element_ids) != 4:
                    Log.warn("Side %s %s has %d elements (expected 4)", side, floor, len(element_ids))
                
                if not element_ids:
                    continue
                
                group_elements = [elem_lookup[eid] for eid in element_ids if eid in elem_lookup]
                
                all_x, all_y, all_z = [], [], []
                for e in group_elements:
                    d = dims(e, view)
                    if d:
                        all_x.extend([d[3], d[4]])
                        all_y.extend([d[5], d[6]])
                        all_z.extend([d[7], d[8]])
                
                if not all_x:
                    continue
                
                xmin, xmax = min(all_x), max(all_x)
                ymin, ymax = min(all_y), max(all_y)
                zmin, zmax = min(all_z), max(all_z)
                
                panel_groups.append({
                    "id": group_id,
                    "elements": group_elements,
                    "element_ids": element_ids,
                    "center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0),
                    "xmin": xmin,
                    "xmax": xmax,
                    "ymin": ymin,
                    "ymax": ymax,
                    "zmin": zmin,
                    "zmax": zmax,
                    "floor": floor,
                    "side": side,
                    "component_count": len(element_ids)
                })
                
                Log.debug("Panel group %d: Side %s, %s, %d components", 
                         group_id, side, floor, len(element_ids))
                
                group_id += 1
        
        Log.info("Created %d panel groups", len(panel_groups))
        
        elem_to_group = {}
        for pg in panel_groups:
            for eid in pg["element_ids"]:
                elem_to_group[eid] = pg["id"]
        
        for side in SIDES:
            group_ids = list(set(elem_to_group.get(eid) for eid in side_summary[side]["wall_panels"] if eid in elem_to_group))
            side_summary[side]["wall_panels"] = group_ids
            
            for floor in ["floor1", "floor2"]:
                floor_group_ids = list(set(elem_to_group.get(eid) for eid in side_summary[side][floor] if eid in elem_to_group))
                side_summary[side][floor] = floor_group_ids
    
    else:
        # MODE B: NO GROUPING - EACH ELEMENT IS A SEPARATE PANEL
        panel_groups = []
        
        for idx, p in enumerate(panel_elems, 1):
            pid = p.Id.IntegerValue
            d = dims(p, view)
            if not d:
                continue
            
            cx, cy = mid_xy(d)
            side = classify_side(cx, cy, bounds)
            floor = classify_floor(d, floor_split)
            
            panel_groups.append({
                "id": pid,
                "elements": [p],
                "element_ids": [pid],
                "center": (cx, cy),
                "xmin": d[3],
                "xmax": d[4],
                "ymin": d[5],
                "ymax": d[6],
                "zmin": d[7],
                "zmax": d[8],
                "floor": floor,
                "side": side,
                "component_count": 1
            })
            
            side_summary[side]["wall_panels"].append(pid)
            side_summary[side][floor].append(pid)
        
        Log.info("Created %d individual panels (no grouping)", len(panel_groups))
    
    # Log summary
    for s in SIDES:
        Log.info("Side %s: %d panels (floor1=%d, floor2=%d)", 
                s,
                len(side_summary[s]["wall_panels"]),
                len(side_summary[s]["floor1"]),
                len(side_summary[s]["floor2"]))
    
    return side_summary, bounds, floor_split, panel_groups

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: DOOR PROCESSING - RESPECTS GROUP_DOOR_COMPONENTS FLAG
# ═══════════════════════════════════════════════════════════════════════════

def process_doors_simple(door_elems, view, floor_split):
    """
    Process doors WITHOUT grouping - each door element stays separate.
    Used when GROUP_DOOR_COMPONENTS = False.
    
    Returns:
        tuple: (door_groups, door_output)
    """
    Log.info("Door grouping: DISABLED - processing %d individual doors", len(door_elems))
    
    door_groups = []
    door_output = []
    
    for idx, e in enumerate(door_elems, 1):
        d = dims(e, view)
        if not d:
            continue
        
        cx, cy = mid_xy(d)
        
        door_groups.append({
            "id": idx,
            "stud_left": get_element_id(e),
            "stud_right": None,
            "center": (cx, cy),
            "dims_left": d,
            "dims_right": None
        })
        
        door_output.append({
            "door": idx,
            "stud_left": get_element_id(e),
            "stud_right": None,
            "header": None,
            "width_mm": d[0],
            "height_mm": d[2],
            "dims_left": d,
            "dims_right": None,
            "dims_header": None
        })
        
        Log.debug("Door %d: ID=%d, size=%.0fx%.0fmm", 
                 idx, get_element_id(e), d[0], d[2])
    
    Log.info("Created %d individual door elements", len(door_output))
    
    return door_groups, door_output


def split_studs_headers(door_elems, view):
    """
    Split door elements into studs (tall/vertical) and headers (short/horizontal).
    Uses 500mm threshold.
    ONLY CALLED when GROUP_DOOR_COMPONENTS = True.
    
    Returns:
        tuple: (studs, headers) - each is list of (element, dims)
    """
    studs = []
    headers = []
    
    Log.info("Analyzing %d door elements for grouping...", len(door_elems))
    Log.info("Using threshold: 500.0 mm (height > 500mm = stud)")
    
    for e in door_elems:
        d = dims(e, view)
        if not d:
            continue
        
        height = d[2]
        width = d[0]
        
        fam, typ = "", ""
        try:
            fam = e.Symbol.Family.Name
            typ = e.Symbol.Name
        except:
            pass
        
        if height > 500.0:
            studs.append((e, d))
            Log.info("  STUD: %s %s | H=%.1fmm W=%.1fmm ID=%d", 
                     fam, typ, height, width, e.Id.IntegerValue)
        else:
            headers.append((e, d))
            Log.info("  HEADER: %s %s | H=%.1fmm W=%.1fmm ID=%d", 
                     fam, typ, height, width, e.Id.IntegerValue)
    
    Log.info("Found %d studs, %d headers", len(studs), len(headers))
    
    return studs, headers


def group_door_studs(studs):
    """
    Group studs into door pairs (2 studs per door).
    Handles any even number of studs.
    ONLY CALLED when GROUP_DOOR_COMPONENTS = True.
    
    Returns:
        list: [(stud_left, stud_right), ...]
    """
    if len(studs) < 2:
        raise Exception("Need at least 2 studs to form a door pair, found {}".format(len(studs)))
    
    if len(studs) % 2 != 0:
        Log.warn("Odd number of studs (%d). Last stud will be unpaired.", len(studs))
    
    # Sort by Z (bottom to top), then by X (left to right)
    studs_sorted = sorted(studs, key=lambda sd: (center_z(sd[1]), mid_xy(sd[1])[0]))
    
    pairs = []
    i = 0
    while i < len(studs_sorted) - 1:
        stud1 = studs_sorted[i]
        stud2 = studs_sorted[i + 1]
        
        # Check if they're on same floor (similar Z)
        z1 = center_z(stud1[1])
        z2 = center_z(stud2[1])
        
        if abs(z1 - z2) < 1000.0:  # Within 1000mm vertically = same floor
            # Sort by X to get left/right
            if mid_xy(stud1[1])[0] < mid_xy(stud2[1])[0]:
                pairs.append((stud1, stud2))
            else:
                pairs.append((stud2, stud1))
            i += 2
        else:
            Log.warn("Stud %d has no pair on same floor, skipping", get_element_id(stud1[0]))
            i += 1
    
    Log.info("Created %d door pairs from %d studs", len(pairs), len(studs))
    return pairs


def build_door_groups(pairs):
    """
    Create door group metadata from stud pairs.
    ONLY CALLED when GROUP_DOOR_COMPONENTS = True.
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
    Assign headers to door pairs based on Z-proximity.
    ONLY CALLED when GROUP_DOOR_COMPONENTS = True.
    
    Returns:
        list: Door output records
    """
    Log.info("Door grouping: ENABLED - matching headers to %d door pairs", len(pairs))
    
    if not headers:
        Log.warn("No headers found - creating doors from studs only")
        door_output = []
        for idx, ((eL, dL), (eR, dR)) in enumerate(pairs, 1):
            cxL, _ = mid_xy(dL)
            cxR, _ = mid_xy(dR)
            width = abs(cxR - cxL)
            height = max(dL[2], dR[2])
            
            door_output.append({
                "door": idx,
                "stud_left": get_element_id(eL),
                "stud_right": get_element_id(eR),
                "header": None,
                "width_mm": width,
                "height_mm": height,
                "dims_left": dL,
                "dims_right": dR,
                "dims_header": None
            })
            
            Log.info("Door %d: studs=%d,%d, NO HEADER, size=%.0fx%.0fmm",
                    idx, get_element_id(eL), get_element_id(eR), width, height)
        
        return door_output
    
    unused_headers = headers[:]
    door_output = []
    
    for idx, ((eL, dL), (eR, dR)) in enumerate(pairs, 1):
        stud_top_z = min(dL[8], dR[8])
        
        best = None
        best_dist = float('inf')
        
        for eH, dH in unused_headers:
            header_z = center_z(dH)
            dist = abs(header_z - stud_top_z)
            if dist < best_dist:
                best_dist = dist
                best = (eH, dH)
        
        if best:
            eH, dH = best
            unused_headers.remove(best)
            header_id = get_element_id(eH)
        else:
            eH, dH = None, None
            header_id = None
            Log.warn("No header found for door %d", idx)
        
        cxL, _ = mid_xy(dL)
        cxR, _ = mid_xy(dR)
        width = abs(cxR - cxL)
        
        if dH:
            height = abs(dH[7] - min(dL[7], dR[7]))
        else:
            height = max(dL[2], dR[2])
        
        door_output.append({
            "door": idx,
            "stud_left": get_element_id(eL),
            "stud_right": get_element_id(eR),
            "header": header_id,
            "width_mm": width,
            "height_mm": height,
            "dims_left": dL,
            "dims_right": dR,
            "dims_header": dH
        })
        
        if header_id:
            Log.info("Door %d: studs=%d,%d, header=%d, size=%.0fx%.0fmm",
                    idx, get_element_id(eL), get_element_id(eR), 
                    header_id, width, height)
        else:
            Log.info("Door %d: studs=%d,%d, NO HEADER, size=%.0fx%.0fmm",
                    idx, get_element_id(eL), get_element_id(eR), width, height)
    
    return door_output

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: YOLO SIDE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_yolo_side(yolo_detections, bim_export):
    """
    Classify which facade side the YOLO image shows.
    
    Returns:
        tuple: (best_side, score)
    """
    if not yolo_detections:
        return "INTERIOR", 0.0
    
    sides = list(bim_export.get("sides", {}).keys())
    if not sides:
        return "INTERIOR", 0.0
    
    bim_by_side = {s: {"door": [], "windows": [], "wall_panels": []} 
                   for s in sides}
    
    for side, side_data in bim_export.get("sides", {}).items():
        for elem in side_data.get("elements", []):
            elem_type = elem["type"]
            bim_by_side[side][elem_type].append(elem)
    
    scores = {s: 0.0 for s in sides}
    
    for det in yolo_detections:
        label = det["label"]
        
        if label == "window":
            label = "windows"
        elif label == "wall-panels":
            label = "wall_panels"
        
        if label not in SIDE_WEIGHTS:
            continue
        
        weight = SIDE_WEIGHTS[label]
        
        for s in sides:
            if len(bim_by_side[s][label]) > 0:
                scores[s] += weight
    
    best_side = max(scores, key=scores.get)
    best_score = scores[best_side]
    
    Log.section("SIDE CLASSIFICATION")
    print("Object".ljust(18) + "".join(s.rjust(10) for s in sides))
    print("-" * 60)
    
    for det in yolo_detections:
        label = det["label"]
        
        if label == "window":
            label = "windows"
        elif label == "wall-panels":
            label = "wall_panels"
        
        row = ("{}_{}".format(det["label"], det.get("id", "?"))).ljust(18)
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