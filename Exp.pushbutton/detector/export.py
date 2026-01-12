# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
EXPORT.PY - BIM EXPORT & YOLO MATCHING
═══════════════════════════════════════════════════════════════════════════

PURPOSE:
    Export BIM geometry to JSON and match with YOLO detections.
    Handles coordinate normalization and element matching.

SECTIONS:
    1. JSON I/O Operations
    2. BIM Geometry Export
    3. YOLO-BIM Matching
═══════════════════════════════════════════════════════════════════════════
"""
import json
import os
import time
from Autodesk.Revit.DB import ElementId
from config import REVIT_FT_TO_MM, PATHS, ensure_dir, Log, SIDES, YOLO_TO_BIM
from core import dims, center_z

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


def save_sequences(bim_export, side_summary):
    """
    Save ordered element sequences per side.
    
    Args:
        bim_export: Full BIM export data
        side_summary: Side classification summary
    """
    sequences = {}
    
    # Build sequences for each side
    for side in SIDES:
        all_elems = []
        
        # Collect all elements for this side
        for key in ("wall-panels", "door", "windows"):
            for e in bim_export.get(key, []):
                if e["side"] == side:
                    all_elems.append(e)
        
        # Sort by normalized X position
        all_elems.sort(key=lambda x: x["center_norm"])
        
        # Extract type sequence
        sequences[side] = [e["type"] for e in all_elems]
    
    # Create export
    export = {
        "summary": {
            "Doors": sum(len(v.get("door", [])) for v in side_summary.values()),
            "Windows": sum(len(v.get("windows", [])) for v in side_summary.values()),
            "Panels": sum(len(v.get("panels", [])) for v in side_summary.values())
        },
        "sides": sequences
    }
    
    save_json(export, path_key="sequences")
    Log.info("Saved element sequences")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: BIM GEOMETRY EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def export_bim_geometry(doc, view, side_summary, door_output, door_side_map, floor_split):
    """
    Export BIM geometry to JSON with normalized coordinates.
    
    Args:
        doc: Revit document
        view: Active view
        side_summary: Side classification data
        door_output: Door detection results
        door_side_map: Mapping of door IDs to sides
        floor_split: Z-coordinate threshold between floors
    
    Returns:
        dict: Full BIM export data
    """
    Log.section("EXPORTING BIM GEOMETRY")
    
    export = {
        "door": [],
        "windows": [],
        "wall-panels": [],
        "side_widths": {}
    }
    
    # ---------------------------------------------------------------
    # Calculate side widths from panels
    # ---------------------------------------------------------------
    side_min_x = {}
    
    for side in SIDES:
        xs = []
        for pid in side_summary[side].get("panels", []):
            elem = doc.GetElement(ElementId(pid))
            if not elem:
                continue
            d = dims(elem, view)
            if d:
                xs.extend([d[3], d[4]])  # xmin, xmax
        
        if xs:
            side_min_x[side] = min(xs)
            export["side_widths"][side] = max(xs) - min(xs)
        else:
            side_min_x[side] = 0.0
            export["side_widths"][side] = 0.0
    
    Log.debug("Side widths calculated: %s", export["side_widths"])
    
    # ---------------------------------------------------------------
    # Helper: normalize X coordinate per side
    # ---------------------------------------------------------------
    def normalize_x(xmin, xmax, side):
        """Convert absolute X to normalized [0-1] coordinate per side."""
        center = (xmin + xmax) / 2.0
        local_min = side_min_x.get(side, 0.0)
        width = export["side_widths"].get(side, 1.0)
        return (center - local_min) / width if width > 0 else 0.0
    
    # ---------------------------------------------------------------
    # Export PANELS
    # ---------------------------------------------------------------
    for side in SIDES:
        for pid in side_summary[side].get("panels", []):
            elem = doc.GetElement(ElementId(pid))
            if not elem:
                continue
            
            d = dims(elem, view)
            if not d:
                continue
            
            # Determine floor
            floor = 1 if pid in side_summary[side].get("floor1", []) else 2
            
            export["wall-panels"].append({
                "id": pid,
                "type": "wall-panels",
                "side": side,
                "floor": floor,
                "xmin": d[3],
                "xmax": d[4],
                "side_width_mm": export["side_widths"][side],
                "center_norm": normalize_x(d[3], d[4], side)
            })
    
    # ---------------------------------------------------------------
    # Export DOORS (composite: studs + header)
    # ---------------------------------------------------------------
    if door_output and door_side_map:
        for d in door_output:
            did = d["door"]
            side = door_side_map.get(did)
            if not side:
                continue
            
            # Get composite bounds from all door components
            elems = [
                doc.GetElement(ElementId(d["stud_left"])),
                doc.GetElement(ElementId(d["stud_right"])),
                doc.GetElement(ElementId(d["header"]))
            ]
            
            xs = []
            zs = []
            for e in elems:
                if not e:
                    continue
                dd = dims(e, view)
                if dd:
                    xs.extend([dd[3], dd[4]])
                    zs.append(center_z(dd))
            
            if not xs:
                continue
            
            xmin, xmax = min(xs), max(xs)
            avg_z = sum(zs) / len(zs) if zs else 0.0
            floor = 1 if avg_z < floor_split else 2
            
            export["door"].append({
                "id": did,
                "type": "door",
                "side": side,
                "floor": floor,
                "xmin": xmin,
                "xmax": xmax,
                "side_width_mm": export["side_widths"][side],
                "center_norm": normalize_x(xmin, xmax, side)
            })
    
    # ---------------------------------------------------------------
    # Export WINDOWS
    # ---------------------------------------------------------------
    for side in SIDES:
        for wid in side_summary[side].get("windows", []):
            elem = doc.GetElement(ElementId(wid))
            if not elem:
                continue
            
            d = dims(elem, view)
            if not d:
                continue
            
            # Classify floor by Z
            floor = 1 if center_z(d) < floor_split else 2
            
            export["windows"].append({
                "id": wid,
                "type": "window",
                "side": side,
                "floor": floor,
                "xmin": d[3],
                "xmax": d[4],
                "side_width_mm": export["side_widths"][side],
                "center_norm": normalize_x(d[3], d[4], side)
            })
    
    # ---------------------------------------------------------------
    # Save to file
    # ---------------------------------------------------------------
    save_json(export, path_key="bim_export")
    
    Log.info("Exported: %d doors, %d windows, %d panels",
            len(export["door"]), len(export["windows"]), len(export["wall-panels"]))
    
    return export

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: YOLO-BIM MATCHING
# ═══════════════════════════════════════════════════════════════════════════

def match_yolo_to_bim(yolo_detections, bim_export, classified_side):
    """
    Match YOLO detections to BIM elements by normalized X-position.
    
    Args:
        yolo_detections: List of YOLO detection dicts
        bim_export: BIM geometry export data
        classified_side: Classified facade side (A/B/C/D or INTERIOR)
    
    Returns:
        list: Match records [{yolo_id, label, bim_id, distance}, ...]
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
                "note": "Interior image - no exterior matching"
            })
        Log.info("Interior image detected - skipping matching")
        return matches
    
    # ---------------------------------------------------------------
    # Validate side width
    # ---------------------------------------------------------------
    side_width = bim_export.get("side_widths", {}).get(classified_side, 0.0)
    if side_width <= 0:
        Log.error("Invalid side width for side %s", classified_side)
        for det in yolo_detections:
            matches.append({
                "yolo_id": det["id"],
                "label": det["label"],
                "bim_id": None,
                "note": "Invalid side width"
            })
        return matches
    
    # ---------------------------------------------------------------
    # Process each YOLO detection
    # ---------------------------------------------------------------
    for det in yolo_detections:
        label = det["label"]
        floor = det.get("floor")
        yolo_x = det["center_xy_norm"][0]  # Normalized X from YOLO
        
        # Normalize YOLO label to BIM key
        bim_key = YOLO_TO_BIM.get(label, label)
        
        # Filter BIM elements by side, floor, and type
        candidates = [
            e for e in bim_export.get(bim_key, [])
            if e["side"] == classified_side and e["floor"] == floor
        ]
        
        if not candidates:
            matches.append({
                "yolo_id": det["id"],
                "label": label,
                "bim_id": None,
                "note": "No BIM elements match type/side/floor"
            })
            continue
        
        # Find closest BIM element by normalized X position
        best_id = None
        best_dist = float('inf')
        
        for elem in candidates:
            dist = abs(elem["center_norm"] - yolo_x)
            if dist < best_dist:
                best_dist = dist
                best_id = elem["id"]
        
        matches.append({
            "yolo_id": det["id"],
            "label": label,
            "bim_id": best_id,
            "distance": best_dist
        })
    
    # ---------------------------------------------------------------
    # Log summary
    # ---------------------------------------------------------------
    matched = sum(1 for m in matches if m.get("bim_id") is not None)
    Log.info("Successfully matched: %d/%d YOLO detections to BIM", 
            matched, len(matches))
    
    return matches