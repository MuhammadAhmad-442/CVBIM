# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
EXPORT.PY - STRUCTURED BIM EXPORT & YOLO MATCHING (FIXED)
═══════════════════════════════════════════════════════════════════════════
"""
import json
import os
import time
from Autodesk.Revit.DB import ElementId
from config import REVIT_FT_TO_MM, PATHS, ensure_dir, Log, SIDES, YOLO_TO_BIM
from core import dims, center_z, get_element_id, mid_xy

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: JSON I/O OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def load_json(path):
    """Load JSON file with error handling."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except IOError:
        Log.error("File not found: %s", path)
        raise
    except ValueError:
        Log.error("Invalid JSON in: %s", path)
        raise


def save_json(data, path_key=None, custom_path=None):
    """Save data to JSON file."""
    if custom_path:
        path = custom_path
    elif path_key:
        path = PATHS[path_key]
    else:
        raise ValueError("Must provide path_key or custom_path")
    
    ensure_dir(path)
    
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    
    Log.info("Saved: %s", path)


def load_yolo():
    """Load YOLO detections."""
    return load_json(PATHS["yolo_detections"])


def save_side_summary(data):
    """Save side classification summary."""
    save_json(data, path_key="side_summary")


def save_door_output(data):
    """Save door detection results."""
    save_json(data, path_key="door_output")


def save_yolo_matches(matches, classified_side, score):
    """Save YOLO-BIM matching results."""
    export = {
        "timestamp": time.time(),
        "classified_side": classified_side,
        "side_score": score,
        "matches": matches
    }
    save_json(export, path_key="yolo_matches")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: STRUCTURED BIM EXPORT (BY SIDE WITH SEQUENCE TAGS)
# ═══════════════════════════════════════════════════════════════════════════

def export_bim_geometry(doc, view, side_summary, door_output, door_side_map, floor_split, panel_groups):
    """
    Export BIM geometry STRUCTURED BY SIDE with sequential tags.
    FIXED: Better error handling for element access.
    
    Returns:
        dict: Structured BIM export
    """
    Log.section("EXPORTING STRUCTURED BIM GEOMETRY")
    
    export = {
        "sides": {},
        "summary": {
            "total_doors": 0,
            "total_windows": 0,
            "total_panels": 0
        }
    }
    
    # Create panel lookup dictionary - maps panel GROUP ID to panel_group
    panel_lookup = {}
    for pg in panel_groups:
        panel_lookup[pg["id"]] = pg
    
    Log.debug("Panel lookup created with %d panel groups", len(panel_groups))
    
    # -----------------------------------------------------------------------
    # Process each side
    # -----------------------------------------------------------------------
    for side in SIDES:
        Log.info("Processing side %s...", side)
        
        # Calculate side width from panels
        side_elements_raw = []
        xs = []
        
        # side_summary["wall_panels"] now contains panel_group IDs (or element IDs if ungrouped)
        for panel_id in side_summary[side].get("wall_panels", []):
            pg = panel_lookup.get(panel_id)
            if not pg:
                Log.debug("Panel group %d not found in lookup", panel_id)
                continue
            xs.extend([pg["xmin"], pg["xmax"]])
        
        if not xs:
            Log.warn("No panels found on side %s - skipping", side)
            continue
        
        side_min_x = min(xs)
        side_max_x = max(xs)
        side_width = side_max_x - side_min_x
        
        # ---------------------------------------------------------------
        # Helper: normalize X coordinate for this side
        # ---------------------------------------------------------------
        def normalize_x(xmin, xmax):
            """Convert absolute X to normalized [0-1] coordinate for this side."""
            center = (xmin + xmax) / 2.0
            if side_width > 0:
                return (center - side_min_x) / side_width
            return 0.0
        
        # ---------------------------------------------------------------
        # Collect PANELS for this side
        # ---------------------------------------------------------------
        for panel_id in side_summary[side].get("wall_panels", []):
            pg = panel_lookup.get(panel_id)
            if not pg:
                continue
            
            # Determine floor from panel group
            floor = 1 if pg["floor"] == "floor1" else 2
            
            side_elements_raw.append({
                "type": "wall_panels",
                "id": panel_id,  # Use panel_group ID
                "floor": floor,
                "xmin": pg["xmin"],
                "xmax": pg["xmax"],
                "position": normalize_x(pg["xmin"], pg["xmax"])
            })
        
        # ---------------------------------------------------------------
        # Collect DOORS for this side
        # ---------------------------------------------------------------
        if door_output and door_side_map:
            for d in door_output:
                did = d["door"]
                if door_side_map.get(did) != side:
                    continue
                
                # Get composite bounds from door components
                # FIXED: Handle None values in door components
                xs_door = []
                zs = []
                
                # Collect dimensions from all available door components
                for key in ["dims_left", "dims_right", "dims_header"]:
                    dd = d.get(key)
                    if dd:
                        xs_door.extend([dd[3], dd[4]])
                        zs.append(center_z(dd))
                
                # Fallback: try getting elements by ID if dims not available
                if not xs_door:
                    try:
                        elem_ids = []
                        if d.get("stud_left"):
                            elem_ids.append(d["stud_left"])
                        if d.get("stud_right"):
                            elem_ids.append(d["stud_right"])
                        if d.get("header"):
                            elem_ids.append(d["header"])
                        
                        for eid in elem_ids:
                            elem = doc.GetElement(ElementId(int(eid)))
                            if elem:
                                dd = dims(elem, view)
                                if dd:
                                    xs_door.extend([dd[3], dd[4]])
                                    zs.append(center_z(dd))
                    except Exception as ex:
                        Log.warn("Could not get door %d dimensions: %s", did, str(ex))
                        continue
                
                if not xs_door:
                    Log.warn("Door %d has no valid dimensions, skipping", did)
                    continue
                
                xmin_door = min(xs_door)
                xmax_door = max(xs_door)
                avg_z = sum(zs) / len(zs) if zs else 0.0
                floor = 1 if avg_z < floor_split else 2
                
                side_elements_raw.append({
                    "type": "door",
                    "id": did,
                    "floor": floor,
                    "xmin": xmin_door,
                    "xmax": xmax_door,
                    "position": normalize_x(xmin_door, xmax_door)
                })
        
        # ---------------------------------------------------------------
        # Collect WINDOWS for this side
        # ---------------------------------------------------------------
        for wid in side_summary[side].get("windows", []):
            try:
                elem = doc.GetElement(ElementId(int(wid)))
                if not elem:
                    Log.debug("Window %d not found", wid)
                    continue
                
                d = dims(elem, view)
                if not d:
                    Log.debug("Window %d has no dimensions", wid)
                    continue
                
                # Classify floor by Z
                floor = 1 if center_z(d) < floor_split else 2
                
                side_elements_raw.append({
                    "type": "window",
                    "id": wid,
                    "floor": floor,
                    "xmin": d[3],
                    "xmax": d[4],
                    "position": normalize_x(d[3], d[4])
                })
            except Exception as ex:
                Log.warn("Could not process window %d: %s", wid, str(ex))
                continue
        
        # ---------------------------------------------------------------
        # Sort elements by position and assign sequential tags
        # ---------------------------------------------------------------
        side_elements_raw.sort(key=lambda x: x["position"])
        
        # Assign sequential tags (1, 2, 3, ...)
        elements_with_tags = []
        for idx, elem in enumerate(side_elements_raw, start=1):
            elements_with_tags.append({
                "tag": idx,
                "type": elem["type"],
                "id": elem["id"],
                "floor": elem["floor"],
                "position": elem["position"],
                "xmin": elem["xmin"],
                "xmax": elem["xmax"]
            })
        
        # ---------------------------------------------------------------
        # Add to export
        # ---------------------------------------------------------------
        export["sides"][side] = {
            "width_mm": side_width,
            "element_count": len(elements_with_tags),
            "elements": elements_with_tags
        }
        
        Log.info("  Side %s: %d elements (width=%.2f mm)", 
                side, len(elements_with_tags), side_width)
    
    # -----------------------------------------------------------------------
    # Calculate summary
    # -----------------------------------------------------------------------
    for side_data in export["sides"].values():
        for elem in side_data["elements"]:
            if elem["type"] == "door":
                export["summary"]["total_doors"] += 1
            elif elem["type"] == "window":
                export["summary"]["total_windows"] += 1
            elif elem["type"] == "wall_panels":
                export["summary"]["total_panels"] += 1
    
    # -----------------------------------------------------------------------
    # Save to file
    # -----------------------------------------------------------------------
    save_json(export, path_key="bim_export")
    
    Log.info("="*70)
    Log.info("Exported: %d doors, %d windows, %d panels across %d sides",
            export["summary"]["total_doors"],
            export["summary"]["total_windows"],
            export["summary"]["total_panels"],
            len(export["sides"]))
    Log.info("="*70)
    
    return export

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: YOLO-BIM MATCHING (Updated for new structure)
# ═══════════════════════════════════════════════════════════════════════════

def match_yolo_to_bim(yolo_detections, bim_export, classified_side):
    """
    Match YOLO detections to BIM elements by normalized X-position.
    Uses the new structured export format.
    
    Args:
        yolo_detections: List of YOLO detection dicts
        bim_export: Structured BIM geometry export
        classified_side: Classified facade side (A/B/C/D or INTERIOR)
    
    Returns:
        list: Match records [{yolo_id, label, bim_id, bim_tag, distance}, ...]
    """
    Log.section("MATCHING YOLO TO BIM")
    
    matches = []
    
    # ---------------------------------------------------------------
    # Handle interior case
    # ---------------------------------------------------------------
    if classified_side == "INTERIOR":
        for det in yolo_detections:
            matches.append({
                "yolo_id": det["id"],
                "label": det["label"],
                "bim_id": None,
                "bim_tag": None,
                "note": "Interior image - no exterior matching"
            })
        Log.info("Interior image detected - skipping matching")
        return matches
    
    # ---------------------------------------------------------------
    # Validate side exists
    # ---------------------------------------------------------------
    if classified_side not in bim_export.get("sides", {}):
        Log.error("Classified side %s not found in BIM export", classified_side)
        for det in yolo_detections:
            matches.append({
                "yolo_id": det["id"],
                "label": det["label"],
                "bim_id": None,
                "bim_tag": None,
                "note": "Side not found in BIM"
            })
        return matches
    
    side_data = bim_export["sides"][classified_side]
    
    # ---------------------------------------------------------------
    # Process each YOLO detection
    # ---------------------------------------------------------------
    for det in yolo_detections:
        label = det["label"]
        floor = det.get("floor")
        yolo_x = det["center_xy_norm"][0]  # Normalized X from YOLO
        
        # Normalize YOLO label to BIM type
        bim_type = YOLO_TO_BIM.get(label, label)
        
        # Filter BIM elements by type and floor
        candidates = [
            e for e in side_data["elements"]
            if e["type"] == bim_type and e["floor"] == floor
        ]
        
        if not candidates:
            matches.append({
                "yolo_id": det["id"],
                "label": label,
                "bim_id": None,
                "bim_tag": None,
                "note": "No BIM elements match type/floor on side {}".format(classified_side)
            })
            continue
        
        # Find closest BIM element by normalized X position
        best_elem = None
        best_dist = float('inf')
        
        for elem in candidates:
            dist = abs(elem["position"] - yolo_x)
            if dist < best_dist:
                best_dist = dist
                best_elem = elem
        
        matches.append({
            "yolo_id": det["id"],
            "label": label,
            "bim_id": best_elem["id"],
            "bim_tag": best_elem["tag"],
            "distance": best_dist,
            "side": classified_side
        })
    
    # ---------------------------------------------------------------
    # Log summary
    # ---------------------------------------------------------------
    matched = sum(1 for m in matches if m.get("bim_id") is not None)
    Log.info("Successfully matched: %d/%d YOLO detections to BIM", 
            matched, len(matches))
    
    return matches


def save_sequences(bim_export, side_summary):
    """
    Save ordered element sequences per side.
    Uses the new structured export format.
    
    Args:
        bim_export: Structured BIM export data
        side_summary: Side classification summary (for backwards compatibility)
    """
    sequences = {}
    
    # Build sequences for each side from structured export
    for side, side_data in bim_export.get("sides", {}).items():
        # Elements are already sorted by position with tags
        sequences[side] = [
            {
                "tag": e["tag"],
                "type": e["type"],
                "id": e["id"],
                "floor": e["floor"]
            }
            for e in side_data["elements"]
        ]
    
    # Create export
    export = {
        "summary": bim_export.get("summary", {}),
        "sides": sequences
    }
    
    save_json(export, path_key="sequences")
    Log.info("Saved element sequences")