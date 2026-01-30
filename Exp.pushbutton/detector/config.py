# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
CONFIG.PY - CONFIGURATION & CONSTANTS (ENHANCED LOGGING)
═══════════════════════════════════════════════════════════════════════════
"""
import os
import time

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════

BASE_DIR = r"."
PYREVIT_DATA = os.path.join(BASE_DIR, "Pyrevit", "Data_saves")
VALIDATION_DIR = os.path.join(BASE_DIR, "test", "Step.2")

PATHS = {
    # Input
    "yolo_detections": os.path.join(VALIDATION_DIR, ".json"),
    
    # Output
    "bim_export": os.path.join(PYREVIT_DATA, "Door_detections", "bim_export.json"),
    "side_summary": os.path.join(PYREVIT_DATA, "Door_detections", "side_objects_summary.json"),
    "door_output": os.path.join(PYREVIT_DATA, "BIM", "door_bim_output.json"),
    "yolo_matches": os.path.join(PYREVIT_DATA, "Door_detections", "yolo_bim_matches.json"),
    "sequences": os.path.join(PYREVIT_DATA, "Door_detections", "side_element_sequences.json"),
}

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: DETECTION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

REVIT_FT_TO_MM = 304.8
STUD_HEIGHT_THRESHOLD_MM = 150.0
PANEL_MIN_WIDTH_MM = 500.0
PANEL_MIN_HEIGHT_MM = 500.0
SIDES = ["A", "B", "C", "D"]

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2.5: INTERIOR/EXTERIOR FILTERING
# ═══════════════════════════════════════════════════════════════════════════

EXTERIOR_DISTANCE_THRESHOLD_MM = 500.0
FILTER_INTERIOR_ELEMENTS = True

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2.6: GROUPING BEHAVIOR SWITCHES
# ═══════════════════════════════════════════════════════════════════════════

GROUP_PANEL_COMPONENTS = False
GROUP_DOOR_COMPONENTS = False

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: CLASSIFICATION WEIGHTS
# ═══════════════════════════════════════════════════════════════════════════

SIDE_WEIGHTS = {
    "door": 3.0,
    "windows": 2.0,
    "wall_panels": 1.0
}

INTERIOR_THRESHOLD = 0.5

YOLO_TO_BIM = {
    "door": "door",
    "window": "windows",
    "wall_panels": "wall_panels",
}

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: ENHANCED LOGGING SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

#SHELL

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def ensure_dir(path):
    """Ensure directory exists for given file path."""
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

def get_path(key):
    """Get configured path by key."""
    if key not in PATHS:
        raise KeyError("Unknown path key: {}".format(key))
    return PATHS[key]
