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

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: BIM GEOMETRY EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def export_bim_geometry(doc, view, side_summary, door_output, door_side_map, floor_split):
    """
    Export BIM geometry to JSON with normalized coordinates.
    
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
    
    # -------------------------------------------------------------------
    # Calculate side widths from panels
    # -------------------------------------------------------------------
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
    
    # -------------------------------------------------------------------
    # Helper: normalize X coordinate per side
    # -------------------------------------------------------------------
    def normalize_x(xmin, xmax, side):
        center = (xmin + xmax) / 2.0
        local_min = side_min_x.get(side, 0.0)
        width = export["side_widths"].get(side, 1.0)
        return (center - local_min) / width if width > 0 else 0.0
    
    # -------------------------------------------------------------------
    # Export PANELS
    # -------------------------------------------------------------------
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
    
    # -------------------------------------------------------------------
    #