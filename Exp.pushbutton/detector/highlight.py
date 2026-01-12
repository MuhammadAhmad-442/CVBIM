from Autodesk.Revit.DB import OverrideGraphicSettings, BuiltInCategory, Color, FilteredElementCollector, FillPatternElement, ElementId
from pyrevit import revit
from .geometry import make_color


def _get_solid_pattern(doc):
    fps = FilteredElementCollector(doc).OfClass(FillPatternElement)
    for fp in fps:
        pat = fp.GetFillPattern()
        if pat and pat.IsSolidFill:
            return fp
    return None

# ------------------------------------------------------------
# NEW: Highlight panels by FLOOR (floor1 / floor2)
# ------------------------------------------------------------
def highlight_panels_by_floor(side_summary, doc, view, highlight_only=None, floor_only=None):
    solid = _get_solid_pattern(doc)
    if not solid:
        print("\n[WARN] No solid fill pattern found for panel floor highlighting.")
        return

    floor_colors = {
        "floor1": make_color(0, 255, 255, solid),   # Cyan
        "floor2": make_color(255, 0, 255, solid),   # Magenta
    }

    with revit.Transaction("Highlight Panels by Floor"):
        sides_to_process = [highlight_only] if highlight_only else ["A", "B", "C", "D"]
        for side in sides_to_process:
            floors_to_process = [floor_only] if floor_only else ["floor1", "floor2"]
            for f in floors_to_process:
                for pid in side_summary[side].get(f, []):
                    elem = doc.GetElement(ElementId(pid))
                    if elem:
                        view.SetElementOverrides(elem.Id, floor_colors[f])
# ------------------------------------------------------------
# NEW: Highlight ALL door elements (panel-based model)
# ------------------------------------------------------------
def highlight_all_door(door_output, doc, view):
    """Highlight every door (stud_left, stud_right, header) without YOLO filtering."""
    solid = _get_solid_pattern(doc)
    if not solid:
        print("\n[WARN] No solid fill pattern found.")
        return

    color = make_color(255, 128, 0, solid)   # Orange

    with revit.Transaction("Highlight All door"):
        for d in door_output:
            for eid in [d["stud_left"], d["stud_right"], d["header"]]:
                elem = doc.GetElement(ElementId(eid))
                if elem:
                    view.SetElementOverrides(elem.Id, color)

    print("\n[INFO] All door elements highlighted.")


# ------------------------------------------------------------
# IMPROVED: Highlight panels by SIDE (already existing)
# ------------------------------------------------------------
def highlight_panels_by_side(side_summary, doc, view, highlight_only=None):
    solid = _get_solid_pattern(doc)
    if not solid:
        print("\n[WARN] No solid fill pattern found for panels.")
        return

    side_colors = {
        "A": make_color(255, 0, 0, solid),
        "B": make_color(0, 255, 0, solid),
        "C": make_color(0, 0, 255, solid),
        "D": make_color(255, 255, 0, solid),
    }

    sides_to_process = [highlight_only] if highlight_only else ["A", "B", "C", "D"]

    with revit.Transaction("Highlight Panels by Side"):
        for side in sides_to_process:
            color = side_colors[side]
            panel_ids = side_summary[side].get("panels", [])
            for pid in panel_ids:
                elem = doc.GetElement(ElementId(pid))
                if elem:
                    view.SetElementOverrides(elem.Id, color)



def highlight_door(door_output, json_labels, doc, view):
    """Highlight door studs + headers, filtered by YOLO labels."""
    solid = _get_solid_pattern(doc)
    if not solid:
        print("\n[WARN] No solid fill pattern found.")
        return

    door_colors = [
        make_color(255, 0, 0, solid),
        make_color(0, 255, 0, solid),
        make_color(0, 0, 255, solid),
    ]

    with revit.Transaction("Highlight door"):
        for d in door_output:
            door_idx = d["door"]
            if json_labels and str(door_idx) not in json_labels:
                print("Skipping door", door_idx, "(not in YOLO JSON)")
                continue

            color = door_colors[(door_idx - 1) % len(door_colors)]
            for eid in [d["stud_left"], d["stud_right"], d["header"]]:
                elem = doc.GetElement(ElementId(eid))
                if elem:
                    view.SetElementOverrides(elem.Id, color)

