# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
CORE.PY - BIM COLLECTION & GEOMETRY UTILITIES
═══════════════════════════════════════════════════════════════════════════

PURPOSE:
    Core utilities for collecting BIM elements and computing geometry.
    Handles all Revit API interactions and bounding box calculations.

SECTIONS:
    1. Element Collection
    2. Geometry Calculations
    3. Caching Utilities
    4. Structure Initialization
═══════════════════════════════════════════════════════════════════════════
"""
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, ElementId
from config import REVIT_FT_TO_MM, SIDES, Log

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: ELEMENT COLLECTION
# ═══════════════════════════════════════════════════════════════════════════

def _safe_name(elem):
    """Extract family, type, and element names safely."""
    try:
        fam = elem.Symbol.Family.Name.lower()
    except:
        fam = ""
    try:
        typ = elem.Symbol.Name.lower()
    except:
        typ = ""
    try:
        name = elem.Name.lower()
    except:
        name = ""
    return fam, typ, name


def collect_elements(doc, view):
    """
    Collect all facade elements from Revit model.
    
    Returns:
        dict: {
            "door": [elements],
            "windows": [elements],
            "panels": [elements]
        }
    """
    door = []
    windows = []
    panels = []
    
    instances = FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance)
    
    for e in instances:
        fam, typ, name = _safe_name(e)
        combo = fam + " " + typ + " " + name
        
        if " door" in combo:
            door.append(e)
        elif "window" in combo:
            windows.append(e)
        elif "panel" in combo or "wall panel" in combo:
            panels.append(e)
    
    Log.info("Collected: Doors=%d, Windows=%d, Panels=%d", 
             len(door), len(windows), len(panels))
    
    return {
        "door": door,
        "windows": windows,
        "panels": panels
    }

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: GEOMETRY CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════

def dims(elem, view):
    """
    Calculate element dimensions in mm.
    
    Returns:
        tuple: (w, d, h, xmin, xmax, ymin, ymax, zmin, zmax) or None
    """
    bbox = elem.get_BoundingBox(view)
    if not bbox:
        return None
    
    return (
        (bbox.Max.X - bbox.Min.X) * REVIT_FT_TO_MM,  # width
        (bbox.Max.Y - bbox.Min.Y) * REVIT_FT_TO_MM,  # depth
        (bbox.Max.Z - bbox.Min.Z) * REVIT_FT_TO_MM,  # height
        bbox.Min.X * REVIT_FT_TO_MM,                 # xmin
        bbox.Max.X * REVIT_FT_TO_MM,                 # xmax
        bbox.Min.Y * REVIT_FT_TO_MM,                 # ymin
        bbox.Max.Y * REVIT_FT_TO_MM,                 # ymax
        bbox.Min.Z * REVIT_FT_TO_MM,                 # zmin
        bbox.Max.Z * REVIT_FT_TO_MM                  # zmax
    )


def center_xy(d):
    """Extract center X,Y from dims tuple."""
    return ((d[3] + d[4]) / 2.0, (d[5] + d[6]) / 2.0)


def center_z(d):
    """Extract center Z from dims tuple."""
    return (d[7] + d[8]) / 2.0


def compute_bounds(panel_elems, view):
    """
    Compute global building bounds from panels.
    
    Returns:
        tuple: (xmin, xmax, ymin, ymax) in mm
    """
    xs, ys = [], []
    
    for e in panel_elems:
        d = dims(e, view)
        if not d:
            continue
        xs.extend([d[3], d[4]])
        ys.extend([d[5], d[6]])
    
    if not xs or not ys:
        raise Exception("Cannot determine building bounds - no panels found")
    
    return (min(xs), max(xs), min(ys), max(ys))

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: CACHING UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def build_element_cache(doc, view):
    """
    Build lookup cache for fast element access.
    
    Returns:
        dict: {element_id: element}
    """
    cache = {}
    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    for e in collector:
        cache[e.Id.IntegerValue] = e
    
    Log.debug("Cached %d elements", len(cache))
    return cache

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: STRUCTURE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def init_side_summary():
    """
    Initialize standardized side summary structure.
    
    Returns:
        dict: Empty side summary with all expected keys
    """
    return {
        side: {
            "panels": [],
            "floor1": [],
            "floor2": [],
            "windows": [],
            "door": []
        }
        for side in SIDES
    }