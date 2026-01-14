# -*- coding: utf-8 -*-
"""
CORE.PY - Core utilities matching your working code
"""
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, ElementId
from config import REVIT_FT_TO_MM, SIDES, Log

def get_element_id(element_or_id):
    """Safely get integer ID from Element or ElementId."""
    if isinstance(element_or_id, int):
        return element_or_id
    
    if hasattr(element_or_id, 'Id'):
        elem_id = element_or_id.Id
    else:
        elem_id = element_or_id
    
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
    EXACT COPY of your working collect_bim_openings logic.
    """
    door = []
    windows = []
    wall_panels = []
    
    insts = FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance)
    
    for e in insts:
        fam, typ, name = _safe_name(e)
        combo = fam + " " + typ + " " + name
        
        # --- Door opening parts ---
        if " door" in combo:
            door.append(e)
        
        # --- Window opening parts ---
        if "window" in combo:
            windows.append(e)
        
        # --- Wall panel (= all other wall-frame items) ---
        if "wall panel" in combo or "panel" in combo:
            wall_panels.append(e)
    
    print("\n[INFO] Collected: door =", len(door),
          "| windows =", len(windows),
          "| wall_panels =", len(wall_panels))
    
    return {
        "door": door,
        "windows": windows,
        "wall_panels": wall_panels,
    }


def bbox(e, view):
    """Get bounding box for element in view."""
    return e.get_BoundingBox(view)


def dims(e, view):
    """
    Return element dimensions in mm.
    
    Returns:
        tuple: (w, d, h, xmin, xmax, ymin, ymax, zmin, zmax) or None
    """
    b = bbox(e, view)
    if not b:
        return None
    
    return (
        (b.Max.X - b.Min.X) * REVIT_FT_TO_MM,  # width
        (b.Max.Y - b.Min.Y) * REVIT_FT_TO_MM,  # depth
        (b.Max.Z - b.Min.Z) * REVIT_FT_TO_MM,  # height
        b.Min.X * REVIT_FT_TO_MM,  # xmin
        b.Max.X * REVIT_FT_TO_MM,  # xmax
        b.Min.Y * REVIT_FT_TO_MM,  # ymin
        b.Max.Y * REVIT_FT_TO_MM,  # ymax
        b.Min.Z * REVIT_FT_TO_MM,  # zmin
        b.Max.Z * REVIT_FT_TO_MM   # zmax
    )


def mid_xy(d):
    """
    Extract center X,Y from dims tuple.
    
    Args:
        d: dims tuple (w, d, h, xmin, xmax, ymin, ymax, zmin, zmax)
    
    Returns:
        tuple: (cx, cy)
    """
    _, _, _, xmin, xmax, ymin, ymax, _, _ = d
    return ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)


def center_xy(d):
    """Alias for mid_xy for backwards compatibility."""
    return mid_xy(d)


def center_z(d):
    """Extract center Z from dims tuple."""
    return (d[7] + d[8]) / 2.0


def compute_bounds(panel_elems, view):
    """Compute global building bounds from panels."""
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


def build_element_cache(doc, view):
    """Build lookup cache for fast element access."""
    cache = {}
    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    
    count = 0
    max_elements = 10000
    
    for e in collector:
        if count >= max_elements:
            break
        
        try:
            elem_id = get_element_id(e)
            cache[elem_id] = e
            count += 1
        except:
            continue
    
    return cache


def build_bbox_cache(elements, view):
    """
    Build a cache of bounding boxes for performance.
    
    Args:
        elements: Iterable of Revit elements
        view: Active view
    
    Returns:
        dict: {element_id: bbox}
    """
    cache = {}
    for e in elements:
        bb = e.get_BoundingBox(view)
        if bb:
            cache[e.Id.IntegerValue] = bb
    return cache


def dims_from_bbox(bb):
    """
    Convert cached bounding box to dims tuple.
    
    Args:
        bb: Revit BoundingBoxXYZ
    
    Returns:
        tuple: (w, d, h, xmin, xmax, ymin, ymax, zmin, zmax)
    """
    if not bb:
        return None
    
    return (
        (bb.Max.X - bb.Min.X) * REVIT_FT_TO_MM,
        (bb.Max.Y - bb.Min.Y) * REVIT_FT_TO_MM,
        (bb.Max.Z - bb.Min.Z) * REVIT_FT_TO_MM,
        bb.Min.X * REVIT_FT_TO_MM,
        bb.Max.X * REVIT_FT_TO_MM,
        bb.Min.Y * REVIT_FT_TO_MM,
        bb.Max.Y * REVIT_FT_TO_MM,
        bb.Min.Z * REVIT_FT_TO_MM,
        bb.Max.Z * REVIT_FT_TO_MM
    )


def init_side_summary():
    """Initialize standardized side summary structure."""
    return {
        side: {
            "wall_panels": [],
            "floor1": [],
            "floor2": [],
            "windows": [],
            "door": []
        }
        for side in SIDES
    }