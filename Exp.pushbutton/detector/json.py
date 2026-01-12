# -*- coding: utf-8 -*-
"""
Unified JSON input/output operations.
Consolidates all JSON loading/saving functionality.
"""
import json
import time
from config import PATHS, ensure_dir

# ============================================================
# LOAD OPERATIONS
# ============================================================

def load_json(path):
    """Generic JSON loader with error handling."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except IOError as e:
        print("[ERROR] File not found: {}".format(path))
        raise
    except ValueError as e:
        print("[ERROR] Invalid JSON in file: {}".format(path))
        raise


def load_yolo_detections():
    """Load YOLO detection results from configured path."""
    path = PATHS["yolo_detections"]
    print("[INFO] Loading YOLO detections from:", path)
    return load_json(path)


def load_bim_export():
    """Load BIM export (doors, windows, panels) from configured path."""
    path = PATHS["bim_export"]
    print("[INFO] Loading BIM export from:", path)
    return load_json(path)


def load_side_summary():
    """Load side classification summary."""
    path = PATHS["side_summary"]
    print("[INFO] Loading side summary from:", path)
    return load_json(path)


# ============================================================
# SAVE OPERATIONS
# ============================================================

def save_json(data, path_key=None, custom_path=None):
    """
    Generic JSON saver.
    
    Args:
        data: Data to save
        path_key: Key from PATHS config (e.g., 'bim_export')
        custom_path: Direct file path (overrides path_key)
    """
    if custom_path:
        path = custom_path
    elif path_key:
        path = PATHS[path_key]
    else:
        raise ValueError("Must provide either path_key or custom_path")
    
    ensure_dir(path)
    
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    
    print("[INFO] Saved JSON to:", path)


def save_side_summary(side_summary):
    """Save side classification summary."""
    save_json(side_summary, path_key="side_summary")


def save_door_output(door_output):
    """Save door detection output."""
    save_json(door_output, path_key="door_output")


def save_yolo_bim_matches(matches, classified_side, score):
    """Save YOLO-BIM matching results."""
    export = {
        "timestamp": time.time(),
        "classified_side": classified_side,
        "side_score": score,
        "matches": matches
    }
    save_json(export, path_key="yolo_bim_matches")
    print("[INFO] YOLO-BIM matches saved")


def save_side_sequences(bim_export, side_summary):
    """
    Save ordered element-type sequences per side.
    
    Args:
        bim_export: Full BIM export data
        side_summary: Side classification data
    """
    sequences = build_side_sequences(bim_export)
    
    export = {
        "summary": {
            "Doors": sum(len(v.get("door", [])) for v in side_summary.values()),
            "Windows": sum(len(v.get("windows", [])) for v in side_summary.values()),
            "Panels": sum(len(v.get("panels", [])) for v in side_summary.values())
        },
        "sides": sequences
    }
    
    save_json(export, path_key="side_sequences")
    print("[INFO] Side element sequences saved")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def build_side_sequences(bim_export):
    """
    Build ordered element-type sequences per side using center_norm.
    
    Returns:
        dict: {side: [element_types_in_order]}
    """
    from config import FACADE_SIDES
    
    sequences = {s: [] for s in FACADE_SIDES}
    
    # Collect all facade elements
    all_elems = []
    for key in ("wall-panels", "door", "windows"):
        for e in bim_export.get(key, []):
            all_elems.append(e)
    
    # Group by side
    by_side = {}
    for e in all_elems:
        side = e["side"]
        by_side.setdefault(side, []).append(e)
    
    # Sort and emit type sequences
    for side, elems in by_side.items():
        ordered = sorted(elems, key=lambda x: x["center_norm"])
        sequences[side] = [e["type"] for e in ordered]
    
    return sequences