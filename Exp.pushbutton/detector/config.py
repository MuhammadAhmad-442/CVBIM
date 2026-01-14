# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
CONFIG.PY - CONFIGURATION & CONSTANTS
═══════════════════════════════════════════════════════════════════════════
"""
import os

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════

BASE_DIR = r"C:\Users\ma3589\OneDrive - The University of Waikato\Desktop\Topic 3"
PYREVIT_DATA = os.path.join(BASE_DIR, "Pyrevit", "Data_saves")
VALIDATION_DIR = os.path.join(BASE_DIR, "Validation_Output_test", "Step.2")

PATHS = {
    # Input
    "yolo_detections": os.path.join(VALIDATION_DIR, "detected_objects.json"),
    
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

# Geometry thresholds
REVIT_FT_TO_MM = 304.8                  # Revit internal units → millimeters

# FIXED: Lower threshold for CFS models - studs can be much shorter
STUD_HEIGHT_THRESHOLD_MM = 150.0        # Min height to classify as vertical stud (vs header)
                                        # Headers are typically < 150mm in CFS
                                        # Studs are typically > 150mm

# Panel filtering - to exclude small framing members
PANEL_MIN_WIDTH_MM = 500.0              # Minimum width for a panel (to filter out studs/noggins)
PANEL_MIN_HEIGHT_MM = 500.0             # Minimum height for a panel

# Facade sides
SIDES = ["A", "B", "C", "D"]            # A=left, B=bottom, C=right, D=top

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: CLASSIFICATION WEIGHTS
# ═══════════════════════════════════════════════════════════════════════════

# Side classification weights (presence-based scoring)
SIDE_WEIGHTS = {
    "door": 3.0,
    "windows": 2.0,
    "wall_panels": 1.0
}

INTERIOR_THRESHOLD = 0.5                # Below this score → interior image

# YOLO label → BIM key mapping
YOLO_TO_BIM = {
    "door": "door",
    "window": "windows",
    "wall_panels": "wall_panels",
}

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

class Log(object):
    """Simple logger with verbosity control."""
    VERBOSE = True
    DEBUG = False
    
    @staticmethod
    def info(msg, *args):
        if Log.VERBOSE:
            print("[INFO] {}".format(msg % args if args else msg))
    
    @staticmethod
    def debug(msg, *args):
        if Log.DEBUG:
            print("[DEBUG] {}".format(msg % args if args else msg))
    
    @staticmethod
    def warn(msg, *args):
        print("[WARN] {}".format(msg % args if args else msg))
    
    @staticmethod
    def error(msg, *args):
        print("[ERROR] {}".format(msg % args if args else msg))
    
    @staticmethod
    def section(title):
        if Log.VERBOSE:
            print("\n" + "=" * 70)
            print("  {}".format(title))
            print("=" * 70 + "\n")

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