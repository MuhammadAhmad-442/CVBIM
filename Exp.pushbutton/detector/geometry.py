# -*- coding: utf-8 -*-
"""
Geometry utilities with caching support.
"""
from Autodesk.Revit.DB import Color, OverrideGraphicSettings
from config import REVIT_FT_TO_MM

# ============================================================
# BOUNDING BOX OPERATIONS
# ============================================================

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


# ============================================================
# CACHING UTILITIES (NEW)
# ============================================================

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


# ============================================================
# VISUALIZATION
# ============================================================

def make_color(r, g, b, solid_pattern):
    """Create override graphic settings with color."""
    ogs = OverrideGraphicSettings()
    ogs.SetProjectionLineColor(Color(r, g, b))
    ogs.SetSurfaceForegroundPatternId(solid_pattern.Id)
    ogs.SetSurfaceForegroundPatternColor(Color(r, g, b))
    return ogs