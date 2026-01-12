# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
VISUALIZATION.PY - REVIT HIGHLIGHTING & DISPLAY
═══════════════════════════════════════════════════════════════════════════

PURPOSE:
    Visual feedback in Revit by color-coding elements.
    Supports highlighting by side, floor, and matched elements.

SECTIONS:
    1. Color Setup
    2. Panel Highlighting
    3. Door Highlighting
═══════════════════════════════════════════════════════════════════════════
"""
from Autodesk.Revit.DB import (
    OverrideGraphicSettings, Color, ElementId,
    FilteredElementCollector, FillPatternElement
)
from pyrevit import revit
from config import Log, SIDES

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: COLOR SETUP
# ═══════════════════════════════════════════════════════════════════════════

def get_solid_pattern(doc):
    """Get solid fill pattern from document."""
    patterns = FilteredElementCollector(doc).OfClass(FillPatternElement)
    for fp in patterns:
        pat = fp.GetFillPattern()
        if pat and pat.IsSolidFill:
            return fp
    return None


def make_color(r, g, b, solid_pattern):
    """Create override graphic settings with color."""
    ogs = OverrideGraphicSettings()
    ogs.SetProjectionLineColor(Color(r, g, b))
    ogs.SetSurfaceForegroundPatternId(solid_pattern.Id)
    ogs.SetSurfaceForegroundPatternColor(Color(r, g, b))
    return ogs


# Color palettes
SIDE_COLORS = {
    "A": (255, 0, 0),      # Red - Left
    "B": (0, 255, 0),      # Green - Bottom
    "C": (0, 0, 255),      # Blue - Right
    "D": (255, 255, 0),    # Yellow - Top
}

FLOOR_COLORS = {
    "floor1": (0, 255, 255),    # Cyan
    "floor2": (255, 0, 255),    # Magenta
}

DOOR_COLOR = (255, 128, 0)      # Orange

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: PANEL HIGHLIGHTING
# ═══════════════════════════════════════════════════════════════════════════

def highlight_panels_by_side(side_summary, doc, view, highlight_only=None):
    """
    Highlight panels by facade side.
    
    Args:
        side_summary: Classification data
        doc: Revit document
        view: Active view
        highlight_only: Optional - only highlight this side
    """
    solid = get_solid_pattern(doc)
    if not solid:
        Log.warn("No solid fill pattern found")
        return
    
    sides_to_process = [highlight_only] if highlight_only else SIDES
    
    for side in sides_to_process:
        r, g, b = SIDE_COLORS[side]
        color = make_color(r, g, b, solid)
        
        for pid in side_summary[side].get("panels", []):
            elem = doc.GetElement(ElementId(pid))
            if elem:
                view.SetElementOverrides(elem.Id, color)
    
    Log.info("Highlighted panels by side: %s", highlight_only or "ALL")


def highlight_panels_by_floor(side_summary, doc, view, highlight_only=None, floor_only=None):
    """
    Highlight panels by floor.
    
    Args:
        side_summary: Classification data
        doc: Revit document
        view: Active view
        highlight_only: Optional - only process this side
        floor_only: Optional - only process this floor
    """
    solid = get_solid_pattern(doc)
    if not solid:
        Log.warn("No solid fill pattern found")
        return
    
    sides_to_process = [highlight_only] if highlight_only else SIDES
    floors_to_process = [floor_only] if floor_only else ["floor1", "floor2"]
    
    for side in sides_to_process:
        for floor in floors_to_process:
            r, g, b = FLOOR_COLORS[floor]
            color = make_color(r, g, b, solid)
            
            for pid in side_summary[side].get(floor, []):
                elem = doc.GetElement(ElementId(pid))
                if elem:
                    view.SetElementOverrides(elem.Id, color)
    
    Log.info("Highlighted panels by floor")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: DOOR HIGHLIGHTING
# ═══════════════════════════════════════════════════════════════════════════

def highlight_doors(door_output, doc, view, filter_ids=None):
    """
    Highlight door elements (studs + headers).
    
    Args:
        door_output: List of door data dicts
        doc: Revit document
        view: Active view
        filter_ids: Optional - only highlight these door IDs
    """
    solid = get_solid_pattern(doc)
    if not solid:
        Log.warn("No solid fill pattern found")
        return
    
    r, g, b = DOOR_COLOR
    color = make_color(r, g, b, solid)
    
    count = 0
    for d in door_output:
        door_id = d["door"]
        
        # Apply filter if specified
        if filter_ids and str(door_id) not in filter_ids:
            continue
        
        # Highlight all components
        for elem_id in [d["stud_left"], d["stud_right"], d["header"]]:
            elem = doc.GetElement(ElementId(elem_id))
            if elem:
                view.SetElementOverrides(elem.Id, color)
                count += 1
    
    Log.info("Highlighted %d door components", count)