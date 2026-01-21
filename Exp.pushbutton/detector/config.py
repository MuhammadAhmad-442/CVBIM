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

class Log(object):
    """Enhanced logger with structured output and troubleshooting info."""
    
    # Verbosity levels
    VERBOSE = True
    DEBUG = False
    SHOW_STATS = True          # Show statistics summaries
    SHOW_WARNINGS = True       # Show warning messages
    SHOW_FILTERING = True      # Show filtering details
    
    # Counters for statistics
    _stats = {
        "errors": 0,
        "warnings": 0,
        "filtered_elements": 0,
        "processed_elements": 0
    }
    
    # Timing
    _start_time = None
    _step_times = {}
    
    @staticmethod
    def reset_stats():
        """Reset all statistics counters."""
        Log._stats = {
            "errors": 0,
            "warnings": 0,
            "filtered_elements": 0,
            "processed_elements": 0
        }
        Log._step_times = {}
    
    @staticmethod
    def start_timer():
        """Start global timer."""
        Log._start_time = time.time()
    
    @staticmethod
    def step_timer(step_name):
        """Record time for a processing step."""
        if Log._start_time:
            Log._step_times[step_name] = time.time() - Log._start_time
    
    @staticmethod
    def info(msg, *args):
        """Standard info message."""
        if Log.VERBOSE:
            formatted = msg % args if args else msg
            print("  {}".format(formatted))
    
    @staticmethod
    def debug(msg, *args):
        """Debug-level message (only shown if DEBUG=True)."""
        if Log.DEBUG:
            formatted = msg % args if args else msg
            print("  [DEBUG] {}".format(formatted))
    
    @staticmethod
    def warn(msg, *args):
        """Warning message with counter."""
        if Log.SHOW_WARNINGS:
            formatted = msg % args if args else msg
            print("  [!] WARNING: {}".format(formatted))
            Log._stats["warnings"] += 1
    
    @staticmethod
    def error(msg, *args):
        """Error message with counter."""
        formatted = msg % args if args else msg
        print("  [X] ERROR: {}".format(formatted))
        Log._stats["errors"] += 1
    
    @staticmethod
    def success(msg, *args):
        """Success message (highlighted)."""
        if Log.VERBOSE:
            formatted = msg % args if args else msg
            print("  [OK] {}".format(formatted))
    
    @staticmethod
    def section(title):
        """Major section header."""
        if Log.VERBOSE:
            print("\n" + "=" * 75)
            print("  {}".format(title))
            print("=" * 75)
    
    @staticmethod
    def subsection(title):
        """Minor section header."""
        if Log.VERBOSE:
            print("\n  --- {} ---".format(title))
    
    @staticmethod
    def table_header(columns):
        """Print table header."""
        if Log.VERBOSE:
            header = "  " + "  ".join(col.ljust(15) for col in columns)
            print("\n" + header)
            print("  " + "-" * (len(columns) * 17))
    
    @staticmethod
    def table_row(values):
        """Print table row."""
        if Log.VERBOSE:
            row = "  " + "  ".join(str(val).ljust(15) for val in values)
            print(row)
    
    @staticmethod
    def filtering_summary(element_type, total, exterior, interior):
        """Log filtering results for element type."""
        if Log.SHOW_FILTERING:
            Log.subsection("{} Filtering".format(element_type))
            print("  Total collected:     {}".format(total))
            print("  Exterior (kept):     {}".format(exterior))
            print("  Interior (filtered): {}".format(interior))
            if total > 0:
                pct = (float(exterior) / total) * 100
                print("  Retention rate:      {:.1f}%".format(pct))
            Log._stats["filtered_elements"] += interior
            Log._stats["processed_elements"] += exterior
    
    @staticmethod
    def element_details(elem_type, elem_id, details):
        """Log detailed element information."""
        if Log.DEBUG:
            print("  [{}] ID={} | {}".format(elem_type, elem_id, details))
    
    @staticmethod
    def progress(current, total, label="Processing"):
        """Show progress for long operations."""
        if Log.VERBOSE and total > 0:
            pct = (float(current) / total) * 100
            print("  {} {}/{} ({:.0f}%)".format(label, current, total, pct))
    
    @staticmethod
    def final_summary():
        """Print final execution summary."""
        if not Log.SHOW_STATS:
            return
        
        print("\n" + "=" * 75)
        print("  EXECUTION SUMMARY")
        print("=" * 75)
        
        # Statistics
        print("\n  STATISTICS:")
        print("  - Elements processed:  {}".format(Log._stats["processed_elements"]))
        print("  - Elements filtered:   {}".format(Log._stats["filtered_elements"]))
        print("  - Warnings:            {}".format(Log._stats["warnings"]))
        print("  - Errors:              {}".format(Log._stats["errors"]))
        
        # Timing
        if Log._step_times:
            print("\n  TIMING:")
            for step, elapsed in Log._step_times.items():
                print("  - {}: {:.2f}s".format(step.ljust(30), elapsed))
        
        # Total time
        if Log._start_time:
            total_time = time.time() - Log._start_time
            print("\n  TOTAL EXECUTION TIME: {:.2f}s".format(total_time))
        
        print("=" * 75 + "\n")
    
    @staticmethod
    def config_summary():
        """Print current configuration settings."""
        if Log.VERBOSE:
            Log.section("CONFIGURATION")
            print("  Panel grouping:        {}".format("ENABLED" if GROUP_PANEL_COMPONENTS else "DISABLED"))
            print("  Door grouping:         {}".format("ENABLED" if GROUP_DOOR_COMPONENTS else "DISABLED"))
            print("  Interior filtering:    {}".format("ENABLED" if FILTER_INTERIOR_ELEMENTS else "DISABLED"))
            if FILTER_INTERIOR_ELEMENTS:
                print("  Filter threshold:      {:.0f}mm".format(EXTERIOR_DISTANCE_THRESHOLD_MM))
            print("  Debug mode:            {}".format("ON" if Log.DEBUG else "OFF"))

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