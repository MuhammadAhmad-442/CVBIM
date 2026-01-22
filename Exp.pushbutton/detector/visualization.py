# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
VISUALIZATION.PY - REVIT HIGHLIGHTING & DISPLAY (FIXED)
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
        
        for pid in side_summary[side].get("wall_panels", []):
            try:
                elem = doc.GetElement(ElementId(int(pid)))
                if elem:
                    view.SetElementOverrides(elem.Id, color)
            except Exception as ex:
                Log.debug("Could not highlight panel %s: %s", pid, str(ex))
    
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
                try:
                    elem = doc.GetElement(ElementId(int(pid)))
                    if elem:
                        view.SetElementOverrides(elem.Id, color)
                except Exception as ex:
                    Log.debug("Could not highlight panel %s: %s", pid, str(ex))
    
    Log.info("Highlighted panels by floor")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: DOOR HIGHLIGHTING (FIXED FOR NONE VALUES)
# ═══════════════════════════════════════════════════════════════════════════

def highlight_doors(door_output, doc, view, filter_ids=None):
    """
    Highlight door elements (studs + headers).
    FIXED: Properly handles None values in door components.
    
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
        
        # Collect all component IDs, filtering out None values
        component_ids = []
        
        if d.get("stud_left") is not None:
            component_ids.append(d["stud_left"])
        
        if d.get("stud_right") is not None:
            component_ids.append(d["stud_right"])
        
        if d.get("header") is not None:
            component_ids.append(d["header"])
        
        # Highlight all valid components
        for elem_id in component_ids:
            try:
                elem = doc.GetElement(ElementId(int(elem_id)))
                if elem:
                    view.SetElementOverrides(elem.Id, color)
                    count += 1
            except Exception as ex:
                Log.debug("Could not highlight door component %s: %s", elem_id, str(ex))
    
    Log.info("Highlighted %d door components", count)