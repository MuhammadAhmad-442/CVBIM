# -*- coding: utf-8 -*-
__title__ = "Highlight + Print Sizes"
__author__ = "Ahmad + ChatGPT"
__doc__ = "Highlight all elements and print their bounding box dimensions."

from pyrevit import revit, DB
from Autodesk.Revit.DB import *
from pyrevit import forms

doc = revit.doc
view = doc.ActiveView


# -----------------------------------------------------
# Get solid fill pattern
# -----------------------------------------------------
fill_patterns = FilteredElementCollector(doc).OfClass(FillPatternElement)
solid_pattern = None
for fp in fill_patterns:
    if fp.GetFillPattern().IsSolidFill:
        solid_pattern = fp
        break

if solid_pattern is None:
    forms.alert("No solid fill pattern found.")
    raise Exception("Solid fill missing")


# -----------------------------------------------------
# Override settings (red fill)
# -----------------------------------------------------
ogs = OverrideGraphicSettings()
ogs.SetProjectionLineColor(Color(255, 0, 0))
ogs.SetSurfaceForegroundPatternId(solid_pattern.Id)
ogs.SetSurfaceForegroundPatternColor(Color(255, 0, 0))


# -----------------------------------------------------
# Collect visible elements
# -----------------------------------------------------
collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()

highlighted = []
skipped = []


# -----------------------------------------------------
# Utility: compute sizes
# -----------------------------------------------------
def get_sizes(elem):
    """Returns (width, depth, height) in mm."""
    try:
        bbox = elem.get_BoundingBox(view)
        if not bbox:
            return None

        min_pt = bbox.Min
        max_pt = bbox.Max

        width  = abs(max_pt.X - min_pt.X) * 304.8   # ft → mm
        depth  = abs(max_pt.Y - min_pt.Y) * 304.8
        height = abs(max_pt.Z - min_pt.Z) * 304.8

        return (width, depth, height)
    except:
        return None


# -----------------------------------------------------
# Modify elements
# -----------------------------------------------------
with revit.Transaction("Highlight + Sizes"):

    for elem in collector:
        try:
            view.SetElementOverrides(elem.Id, ogs)

            dims = get_sizes(elem)
            if dims:
                width, depth, height = dims
                name = elem.Name if hasattr(elem, "Name") else "<no name>"
                highlighted.append((elem.Id, name, width, depth, height))

        except:
            skipped.append(elem.Id)
            pass


# -----------------------------------------------------
# Print results
# -----------------------------------------------------
print("=== ELEMENT SIZES (mm) ===")
for eid, name, w, d, h in highlighted:
    print(
        "ID: {} | Name: {} | W:{:.1f}mm  D:{:.1f}mm  H:{:.1f}mm".format(
            eid, name, w, d, h
        )
    )

print("\n=== Skipped (couldn't override) ===")
for eid in skipped:
    print("ID:", eid)

forms.alert("Printed sizes for {} elements.\nSkipped {}.".format(len(highlighted), len(skipped)))
