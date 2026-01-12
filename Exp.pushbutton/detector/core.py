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
def get_element_id(element_or_id):
    """
    Safely get integer ID from Element or ElementId.
    Handles different Revit API versions.
    
    Args:
        element_or_id: Revit Element or ElementId
    
    Returns:
        int: Element ID as integer
    """
    if isinstance(element_or_id, int):
        return element_or_id
    
    # If it's an Element, get its Id first
    if hasattr(element_or_id, 'Id'):
        elem_id = element_or_id.Id
    else:
        elem_id = element_or_id
    
    # Now convert ElementId to int
    if hasattr(elem_id, 'IntegerValue'):
        return elem_id.IntegerValue
    else:
        return int(elem_id)
        
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
    Collect elements - ULTRA SAFE VERSION (no LINQ, no filters).
    """
    door = []
    windows = []
    panels = []
    PANEL_KEYS  = ["panel", "wp", "wallpanel", "wall_panel"]
    DOOR_KEYS   = ["door", "opening", "frame", "jamb"]
    WINDOW_KEYS = ["window", "glazing", "vision"]

    
    try:
        Log.info("Starting ULTRA-SAFE element collection...")
        
        # Get all elements of Category OST_GenericModel or try multiple categories
        from Autodesk.Revit.DB import BuiltInCategory
        
        categories_to_try = [
            BuiltInCategory.OST_GenericModel,
            BuiltInCategory.OST_Doors,
            BuiltInCategory.OST_Windows,
            BuiltInCategory.OST_Walls,
        ]
        
        all_elements = []
        
        for cat in categories_to_try:
            try:
                Log.info("Trying category: %s", cat)
                collector = FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType()
                elements = list(collector)
                Log.info("  Found %d elements in this category", len(elements))
                all_elements.extend(elements)
            except Exception as e:
                Log.warn("  Category failed: %s", str(e))
                continue
        
        Log.info("Total elements to process: %d", len(all_elements))
        
        # Process collected elements
        for idx, e in enumerate(all_elements):
            if idx % 500 == 0:
                Log.info("Processing element %d/%d", idx, len(all_elements))
            
            try:
                # Check if it's a family instance
                def has_any(text, keys):
                    return any(k in text for k in keys)

                fam, typ, name = _safe_name(e)
                combo = (fam + " " + typ + " " + name).lower()

                if has_any(combo, DOOR_KEYS) and isinstance(e, FamilyInstance):
                    door.append(e)

                elif has_any(combo, WINDOW_KEYS) and isinstance(e, FamilyInstance):
                    windows.append(e)

                elif has_any(combo, PANEL_KEYS):
                    panels.append(e)


                    
            except:
                continue
        
        Log.info("Collection complete: Doors=%d, Windows=%d, Panels=%d", 
                 len(door), len(windows), len(panels))
        
    except Exception as e:
        Log.error("FATAL: Collection failed: %s", str(e))
        import traceback
        traceback.print_exc()
    
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

# ===========================================================================
# SECTION 3: CACHING UTILITIES
# ===========================================================================

def build_element_cache(doc, view):
    """
    Build lookup cache for fast element access (with limits).
    
    Returns:
        dict: {element_id: element}
    """
    cache = {}
    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    
    count = 0
    max_elements = 10000  # Safety limit
    
    for e in collector:
        if count >= max_elements:
            Log.warn("Element cache limit reached (%d elements)", max_elements)
            break
        
        try:
            elem_id = get_element_id(e)
            cache[elem_id] = e
            count += 1
        except:
            continue
    
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