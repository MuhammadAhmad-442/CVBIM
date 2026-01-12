# -*- coding: utf-8 -*-
__title__ = "Door Elements + Distances"
__author__ = "Ahmad + ChatGPT"
__doc__ = "Highlight all elements named 'Door' and print gaps between them."

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
    if not b: return None
    w = (b.Max.X - b.Min.X) * 304.8
    d = (b.Max.Y - b.Min.Y) * 304.8
    h = (b.Max.Z - b.Min.Z) * 304.8
    return w, d, h

def center_x(e):
    b = get_bbox(e)
    return (b.Min.X + b.Max.X) / 2.0 if b else None


# ----------------------------------------------------------
# STEP 1 — Find all elements named "Door"
# ----------------------------------------------------------
collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()

door_elems = []
for e in collector:
    name = e.Name or ""
    if "Door" in name:     # case-sensitive match
        door_elems.append(e)

if not door_elems:
    forms.alert("No elements found whose name contains 'Door'.")
    raise SystemExit


# ----------------------------------------------------------
# STEP 2 — Sort them left → right (X coordinate)
# ----------------------------------------------------------
door_sorted = sorted(door_elems, key=lambda e: center_x(e))


# ----------------------------------------------------------
# STEP 3 — Print info for each element
# ----------------------------------------------------------
print("\n===========================")
print("   DOOR ELEMENTS FOUND")
print("===========================\n")

for e in door_sorted:
    w, d, h = get_dims(e)
    cx = center_x(e)
    print("ID {} | Name {} | W:{:.1f} D:{:.1f} H:{:.1f} | X:{:.1f}".format(
        e.Id, e.Name, w, d, h, cx
    ))


# ----------------------------------------------------------
# STEP 4 — Compute horizontal gaps between them
# ----------------------------------------------------------
print("\n===========================")
print("   HORIZONTAL GAPS (mm)")
print("===========================\n")

prev = None
for e in door_sorted:
    if prev:
        b1 = get_bbox(prev)
        b2 = get_bbox(e)
        gap = (b2.Min.X - b1.Max.X) * 304.8

        print("Between [{}:{}] → [{}:{}] = {:.1f} mm".format(
            prev.Id, prev.Name, e.Id, e.Name, gap
        ))

    prev = e


# ----------------------------------------------------------
# STEP 5 — Highlight them
# ----------------------------------------------------------
# find solid fill pattern
fps = FilteredElementCollector(doc).OfClass(FillPatternElement)
solid = None
for fp in fps:
    if fp.GetFillPattern().IsSolidFill:
        solid = fp
        break

ogs = OverrideGraphicSettings()
ogs.SetProjectionLineColor(Color(0, 0, 255))
ogs.SetSurfaceForegroundPatternId(solid.Id)
ogs.SetSurfaceForegroundPatternColor(Color(0, 0, 255))

with revit.Transaction("Highlight Door Elements"):
    for e in door_sorted:
        view.SetElementOverrides(e.Id, ogs)


forms.alert("Door elements highlighted. Check console for gaps + dimensions.")
