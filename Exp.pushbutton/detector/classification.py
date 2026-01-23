# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
CLASSIFICATION.PY - FIXED TO KEEP INTERIOR ELEMENTS
═══════════════════════════════════════════════════════════════════════════
"""
from config import (STUD_HEIGHT_THRESHOLD_MM, SIDE_WEIGHTS, INTERIOR_THRESHOLD, 
                    Log, SIDES, GROUP_PANEL_COMPONENTS, GROUP_DOOR_COMPONENTS,
                    FILTER_INTERIOR_ELEMENTS)
from core import dims, mid_xy, center_z, compute_bounds, init_side_summary, get_element_id, is_exterior_element

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: FLOOR CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def compute_floor_split(panel_elems, view):
    """Calculate Z-height threshold between floors using median."""
    z_bottoms = []
    for p in panel_elems:
        d = dims(p, view)
        if d:
            z_bottoms.append(d[7])
    
    if not z_bottoms:
        raise Exception("No panel Z-values found for floor split")
    
    z_bottoms.sort()
    split = z_bottoms[len(z_bottoms) // 2]
    
    Log.debug("Floor split Z: %.2f mm (based on panel bottoms)", split)
    return split


def classify_floor(d, floor_split):
    """Classify element as floor1 or floor2."""
    bottom_z = d[7]
    return "floor1" if bottom_z < floor_split else "floor2"

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: IMPROVED SIDE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_side_smart(cx, cy, bounds, is_interior=False):
    """
    Improved side classification that handles both exterior and interior elements.
    
    For EXTERIOR elements: Uses distance to nearest facade
    For INTERIOR elements: Uses orientation based on position in building
    
    Args:
        cx, cy: Element center coordinates
        bounds: (xmin, xmax, ymin, ymax)
        is_interior: Whether element is classified as interior
    
    Returns:
        str: "A", "B", "C", or "D"
    """
    xmin, xmax, ymin, ymax = bounds
    
    # Calculate center of building
    cx_building = (xmin + xmax) / 2.0
    cy_building = (ymin + ymax) / 2.0
    
    # Calculate building dimensions
    width = xmax - xmin
    height = ymax - ymin
    
    if is_interior:
        # For interior elements, use quadrant-based assignment
        # This ensures interior elements get distributed across sides
        
        # Determine which quadrant the element is in
        is_left = cx < cx_building
        is_bottom = cy < cy_building
        
        # Calculate relative position (0-1) from center
        rel_x = abs(cx - cx_building) / (width / 2.0) if width > 0 else 0
        rel_y = abs(cy - cy_building) / (height / 2.0) if height > 0 else 0
        
        # Assign based on which axis is dominant
        if rel_x > rel_y:
            # Element is more aligned with left-right axis
            return "A" if is_left else "C"
        else:
            # Element is more aligned with top-bottom axis
            return "B" if is_bottom else "D"
    
    else:
        # For exterior elements, use distance to nearest facade
        distances = {
            "A": abs(cx - xmin),      # left
            "C": abs(cx - xmax),      # right
            "B": abs(cy - ymin),      # bottom
            "D": abs(cy - ymax)       # top
        }
        
        return min(distances, key=distances.get)


def classify_side(cx, cy, bounds):
    """
    Legacy wrapper for classify_side_smart.
    Assumes exterior element for backwards compatibility.
    """
    return classify_side_smart(cx, cy, bounds, is_interior=False)


def classify_windows(window_elems, view, bounds, side_summary):
    """Assign ALL windows to sides (both interior and exterior)."""
    
    exterior_count = 0
    interior_count = 0
    
    for e in window_elems:
        d = dims(e, view)
        if not d:
            continue
        
        is_ext = is_exterior_element(d, bounds)
        
        if is_ext:
            exterior_count += 1
        else:
            interior_count += 1
        
        cx, cy = mid_xy(d)
        side = classify_side_smart(cx, cy, bounds, is_interior=not is_ext)
        side_summary[side]["windows"].append(e.Id.IntegerValue)
        
        Log.debug("Window %d -> Side %s (%s)", 
                 e.Id.IntegerValue, side, "exterior" if is_ext else "interior")
    
    total = sum(len(side_summary[s]["windows"]) for s in SIDES)
    
    # Log filtering summary
    if FILTER_INTERIOR_ELEMENTS and Log.SHOW_FILTERING:
        Log.filtering_summary("Windows", len(window_elems), exterior_count, interior_count)
    
    Log.info("Assigned %d windows to sides (%d ext, %d int)", total, exterior_count, interior_count)


def classify_doors(door_groups, bounds, side_summary, panel_groups):
    """
    Assign door groups to sides with panel-based interior/exterior detection.
    Associates each door with its nearest panel to determine exterior/interior status.
    
    Args:
        door_groups: List of door group dicts
        bounds: Building bounds
        side_summary: Side classification summary
        panel_groups: List of panel groups with interior/exterior info
    
    Returns:
        tuple: (door_side_map, door_interior_map)
            door_side_map: {door_id: side}
            door_interior_map: {door_id: is_interior}
    """
    
    door_side_map = {}
    door_interior_map = {}
    
    exterior_counts = {s: 0 for s in SIDES}
    interior_counts = {s: 0 for s in SIDES}
    
    # Build panel lookup with interior/exterior info
    panel_lookup = {}
    for pg in panel_groups:
        # Determine if panel is interior
        is_int = pg.get("is_interior", False)
        if not is_int and "is_interior" not in pg:
            # Fallback: check using center position
            center_dims = (0, 0, 0, pg["xmin"], pg["xmax"], pg["ymin"], pg["ymax"], pg["zmin"], pg["zmax"])
            is_int = not is_exterior_element(center_dims, bounds)
        
        panel_lookup[pg["id"]] = {
            "center": pg["center"],
            "is_interior": is_int,
            "side": pg.get("side", ""),
            "floor": pg.get("floor", "")
        }
    
    Log.debug("Built panel lookup with %d panels", len(panel_lookup))
    
    for d in door_groups:
        did = d["id"]
        cx, cy = d["center"]
        
        # Find nearest panel to associate with this door
        nearest_panel = None
        min_dist = float('inf')
        
        for panel_id, panel_info in panel_lookup.items():
            pcx, pcy = panel_info["center"]
            dist = ((cx - pcx) ** 2 + (cy - pcy) ** 2) ** 0.5
            
            if dist < min_dist:
                min_dist = dist
                nearest_panel = panel_info
        
        # Determine interior/exterior based on nearest panel
        if nearest_panel:
            # Only trust panel interior flag if door is VERY close to panel
            PANEL_ASSOCIATION_THRESHOLD_MM = 800.0
            
            if min_dist <= PANEL_ASSOCIATION_THRESHOLD_MM:
                is_interior = nearest_panel["is_interior"]
            else:
                # Door is not embedded in a panel -> use geometry
                if "dims_left" in d and d["dims_left"]:
                    is_interior = not is_exterior_element(d["dims_left"], bounds)
                elif "dims_right" in d and d["dims_right"]:
                    is_interior = not is_exterior_element(d["dims_right"], bounds)
                else:
                    is_interior = False
            
            Log.debug("Door %d -> nearest panel %.1fmm away (%s)", 
                     did, min_dist, "interior" if is_interior else "exterior")
        else:
            # Fallback: use dims-based detection
            is_interior = False
            if "dims_left" in d and d["dims_left"]:
                is_interior = not is_exterior_element(d["dims_left"], bounds)
            elif "dims_right" in d and d["dims_right"]:
                is_interior = not is_exterior_element(d["dims_right"], bounds)
            
            Log.debug("Door %d -> no nearby panel, using dims-based detection (%s)", 
                     did, "interior" if is_interior else "exterior")
        
        # Classify side using improved logic
        side = classify_side_smart(cx, cy, bounds, is_interior=is_interior)
        door_side_map[did] = side
        door_interior_map[did] = is_interior
        side_summary[side]["door"].append(did)
        
        # Track counts
        if is_interior:
            interior_counts[side] += 1
        else:
            exterior_counts[side] += 1
        
        Log.debug("Door %d -> Side %s (%s)", 
                 did, side, "interior" if is_interior else "exterior")
    
    # Log distribution with interior/exterior breakdown
    Log.subsection("Door Distribution")
    for s in SIDES:
        total = len(side_summary[s]["door"])
        if total > 0:
            ext = exterior_counts[s]
            int_cnt = interior_counts[s]
            Log.info("Side %s: %d doors (%d ext, %d int)", s, total, ext, int_cnt)
    
    return door_side_map, door_interior_map

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: PANEL GROUPING & CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_all_panels(panel_elems, view):
    """
    Classify ALL panels by side and floor (both interior and exterior).
    
    Returns:
        tuple: (side_summary, bounds, floor_split, panel_groups)
    """
    Log.section("CLASSIFYING PANELS")
    
    if GROUP_PANEL_COMPONENTS:
        Log.info("Panel grouping: ENABLED (4 sub-components -> 1 panel)")
    else:
        Log.info("Panel grouping: DISABLED (each element = 1 panel)")
    
    if FILTER_INTERIOR_ELEMENTS:
        Log.info("Interior filtering: ENABLED (tracking int/ext)")
    else:
        Log.info("Interior filtering: DISABLED (all elements treated as exterior)")
    
    # STEP 1: Compute bounds from ALL panels
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
    
    # STEP 2: Process ALL panels (don't filter them out)
    original_count = len(panel_elems)
    
    if not panel_elems:
        raise Exception("No panels found")
    
    # STEP 3: Compute floor split
    floor_split = compute_floor_split(panel_elems, view)
    Log.info("Floor split: %.2f mm", floor_split)
    
    # STEP 4: Initialize side summary
    side_summary = init_side_summary()
    
    # STEP 5: Classify ALL panels with interior detection
    
    if GROUP_PANEL_COMPONENTS:
        # GROUP MODE - collect by side/floor then group
        for p in panel_elems:
            pid = p.Id.IntegerValue
            d = dims(p, view)
            if not d:
                continue
            
            cx, cy = mid_xy(d)
            is_int = not is_exterior_element(d, bounds)
            
            side = classify_side_smart(cx, cy, bounds, is_interior=is_int)
            floor = classify_floor(d, floor_split)
            
            side_summary[side]["wall_panels"].append(pid)
            side_summary[side][floor].append(pid)
            
            Log.debug("Panel %d -> Side %s, %s (%s)", 
                     pid, side, floor, "interior" if is_int else "exterior")
        
        Log.info("Classified %d individual panel elements", len(panel_elems))
        
        # Create panel groups
        panel_groups = []
        group_id = 1
        elem_lookup = {e.Id.IntegerValue: e for e in panel_elems}
        
        for side in SIDES:
            for floor in ["floor1", "floor2"]:
                element_ids = side_summary[side][floor]
                
                if not element_ids:
                    continue
                
                # Allow flexible grouping
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
                
                # Determine if group is interior
                center_dims = (0, 0, 0, xmin, xmax, ymin, ymax, zmin, zmax)
                is_int = not is_exterior_element(center_dims, bounds)
                
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
                    "component_count": len(element_ids),
                    "is_interior": is_int
                })
                
                Log.debug("Panel group %d: Side %s, %s, %d components (%s)", 
                         group_id, side, floor, len(element_ids),
                         "interior" if is_int else "exterior")
                
                group_id += 1
        
        Log.info("Created %d panel groups", len(panel_groups))
        
        # Update side_summary to use group IDs
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
        # NO GROUP MODE - each element is separate panel
        panel_groups = []
        
        for idx, p in enumerate(panel_elems, 1):
            pid = p.Id.IntegerValue
            d = dims(p, view)
            if not d:
                continue
            
            cx, cy = mid_xy(d)
            is_int = not is_exterior_element(d, bounds)
            
            side = classify_side_smart(cx, cy, bounds, is_interior=is_int)
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
                "component_count": 1,
                "is_interior": is_int
            })
            
            side_summary[side]["wall_panels"].append(pid)
            side_summary[side][floor].append(pid)
            
            Log.debug("Panel %d -> Side %s, %s (%s)", 
                     pid, side, floor, "interior" if is_int else "exterior")
        
        Log.info("Created %d individual panels (no grouping)", len(panel_groups))
    
    # Count interior/exterior for summary
    if FILTER_INTERIOR_ELEMENTS and Log.SHOW_FILTERING:
        ext_count = sum(1 for pg in panel_groups if not pg.get("is_interior", False))
        int_count = len(panel_groups) - ext_count
        Log.filtering_summary("Panels", len(panel_groups), ext_count, int_count)
    
    # Log summary
    for s in SIDES:
        Log.info("Side %s: %d panels (floor1=%d, floor2=%d)", 
                s,
                len(side_summary[s]["wall_panels"]),
                len(side_summary[s]["floor1"]),
                len(side_summary[s]["floor2"]))
    
    return side_summary, bounds, floor_split, panel_groups

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: DOOR PROCESSING
# ═══════════════════════════════════════════════════════════════════════════

def process_doors_simple(door_elems, view, floor_split):
    """Process doors WITHOUT grouping - each door element stays separate."""
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
    """Split door elements into studs and headers."""
    studs = []
    headers = []
    
    Log.info("Analyzing %d door elements for grouping...", len(door_elems))
    
    for e in door_elems:
        d = dims(e, view)
        if not d:
            continue
        
        height = d[2]
        
        if height > 500.0:
            studs.append((e, d))
        else:
            headers.append((e, d))
    
    Log.info("Found %d studs, %d headers", len(studs), len(headers))
    
    return studs, headers


def group_door_studs(studs):
    """Group studs into door pairs."""
    if len(studs) < 2:
        raise Exception("Need at least 2 studs to form a door pair, found {}".format(len(studs)))
    
    studs_sorted = sorted(studs, key=lambda sd: (center_z(sd[1]), mid_xy(sd[1])[0]))
    
    pairs = []
    i = 0
    while i < len(studs_sorted) - 1:
        stud1 = studs_sorted[i]
        stud2 = studs_sorted[i + 1]
        
        z1 = center_z(stud1[1])
        z2 = center_z(stud2[1])
        
        if abs(z1 - z2) < 1000.0:
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
    """Create door group metadata from stud pairs."""
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
    """Assign headers to door pairs."""
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
    
    return door_output

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: YOLO SIDE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_yolo_side(yolo_detections, bim_export):
    """Classify which facade side the YOLO image shows."""
    if not yolo_detections:
        return "INTERIOR", 0.0
    
    # Use EXTERIOR data only for side classification
    exterior_data = bim_export.get("exterior", {})
    sides = list(exterior_data.get("sides", {}).keys())
    
    if not sides:
        return "INTERIOR", 0.0
    
    bim_by_side = {s: {"door": [], "windows": [], "wall_panels": []} 
                   for s in sides}
    
    for side, side_data in exterior_data.get("sides", {}).items():
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