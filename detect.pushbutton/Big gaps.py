# -*- coding: utf-8 -*-
__title__ = "Door Elements + Large Gaps (Abs > 600)"
__author__ = "Ahmad + ChatGPT"
__doc__ = "Print all gaps (neg or pos) between Door elements and highlight abs(gap)>600."

from pyrevit import revit
from Autodesk.Revit.DB import *
from pyrevit import forms

doc = revit.doc
view = doc.ActiveView


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def get_bbox(e):
    return e.get_BoundingBox(view)

def get_dims(e):
    b = get_bbox(e)
    if not b:
        return None
    w = (b.Max.X - b.Min.X) * 304.8
    d = (b.Max.Y - b.Min.Y) * 304.8
    h = (b.Max.Z - b.Min.Z) * 304.8
    return w, d, h

def center_x(e):
    b = get_bbox(e)
    return (b.Min.X + b.Max.X) / 2.0 if b else None


# ----------------------------------------------------------
# STEP 1 — Collect “Door” elements
# ----------------------------------------------------------
collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()

door_elems = [e for e in collector if "Door" in (e.Name or "")]

if not door_elems:
    forms.alert("No 'Door' elements found.")
    raise SystemExit


# ----------------------------------------------------------
# STEP 2 — Sort by X coordinate
# ----------------------------------------------------------
door_sorted = sorted(door_elems, key=lambda e: center_x(e))


# ----------------------------------------------------------
# STEP 3 — Print Door elements
# ----------------------------------------------------------
print("\n=============================")
print("     DOOR ELEMENTS FOUND")
print("=============================\n")

for e in door_sorted:
    dims = get_dims(e)
    if dims:
        w, d, h = dims
        print("ID {} | Name {} | W:{:.1f} D:{:.1f} H:{:.1f} | X:{:.1f}".format(
            e.Id, e.Name, w, d, h, center_x(e)
        ))


# ----------------------------------------------------------
# STEP 4 — Compute ALL gaps (negative or positive)
# ----------------------------------------------------------
print("\n=============================")
print("     ALL HORIZONTAL GAPS (mm)")
print("=============================\n")

large_gaps = []   # store gaps where abs(gap) > 600 mm

prev = None
for e in door_sorted:
    if prev:
        b1 = get_bbox(prev)
        b2 = get_bbox(e)

        # signed gap (may be negative)
        gap = (b2.Min.X - b1.Max.X) * 304.8
        gap_abs = abs(gap)

        print("Between [{}:{}] → [{}:{}] = gap: {:.1f} mm (abs {:.1f})".format(
            prev.Id, prev.Name, e.Id, e.Name, gap, gap_abs
        ))

        # NEW RULE: check abs(gap) > 600
        if gap_abs > 600.0:
            large_gaps.append((prev, e, gap, gap_abs))

    prev = e


if not large_gaps:
    forms.alert("No gaps with |gap| > 600 mm found.")
    raise SystemExit


# ----------------------------------------------------------
# STEP 5 — Highlight ONLY gaps with abs(gap) > 600
# ----------------------------------------------------------
# find solid fill pattern
fps = FilteredElementCollector(doc).OfClass(FillPatternElement)
solid = next((fp for fp in fps if fp.GetFillPattern().IsSolidFill), None)

ogs = OverrideGraphicSettings()
ogs.SetProjectionLineColor(Color(255, 0, 0))
ogs.SetSurfaceForegroundPatternId(solid.Id)
ogs.SetSurfaceForegroundPatternColor(Color(255, 0, 0))


def outline_between(a, b, ext=300):
    """Build highlight region between bbox(a) and bbox(b)."""
    b1 = get_bbox(a)
    b2 = get_bbox(b)

    # Determine left & right order dynamically
    min_x = min(b1.Max.X, b2.Max.X)
    max_x = max(b1.Min.X, b2.Min.X)

    min_y = min(b1.Min.Y, b2.Min.Y) - ext
    max_y = max(b1.Max.Y, b2.Max.Y) + ext

    min_z = min(b1.Min.Z, b2.Min.Z) - ext
    max_z = max(b1.Max.Z, b2.Max.Z) + ext

    return Outline(XYZ(min_x, min_y, min_z), XYZ(max_x, max_y, max_z))


with revit.Transaction("Highlight Large |Gaps|"):
    for left, right, g_signed, g_abs in large_gaps:

        outline = outline_between(left, right)

        # highlight elements inside the gap region
        for e in collector:
            b = get_bbox(e)
            if not b:
                continue

            o = Outline(b.Min, b.Max)
            if outline.Intersects(o, 0.0):
                view.SetElementOverrides(e.Id, ogs)

        print("Highlighted |gap| {:.1f} mm between {} and {} (signed {:.1f}).".format(
            g_abs, left.Id, right.Id, g_signed
        ))


forms.alert("Highlighted {} large gap(s) |gap| > 600 mm.\nCheck console.".format(
    len(large_gaps)
))
