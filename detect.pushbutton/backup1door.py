# -*- coding: utf-8 -*-
__title__ = "Extract + Highlight Door"
__author__ = "Ahmad + ChatGPT"
__doc__ = "Extracts door geometry and highlights the door opening region."

from pyrevit import revit
from Autodesk.Revit.DB import *
from pyrevit import forms
import json
import os

doc = revit.doc
view = doc.ActiveView


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def get_bbox(e):
    return e.get_BoundingBox(view)

def dims(e):
    b = get_bbox(e)
    if not b:
        return None
    w = (b.Max.X - b.Min.X) * 304.8
    d = (b.Max.Y - b.Min.Y) * 304.8
    h = (b.Max.Z - b.Min.Z) * 304.8
    return w, d, h

def cx(e):
    b = get_bbox(e)
    return (b.Min.X + b.Max.X) / 2.0 if b else None

def cz(e):
    b = get_bbox(e)
    return (b.Min.Z + b.Max.Z) / 2.0 if b else None


# ----------------------------------------------------------
# STEP 1 — Gather all Door elements
# ----------------------------------------------------------
collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
doors = [e for e in collector if "Door" in (e.Name or "")]

if not doors:
    forms.alert("No Door elements found.")
    raise SystemExit


# ----------------------------------------------------------
# STEP 2 — Classify elements by height
# ----------------------------------------------------------
verticals = []
headers = []
sills = []

for e in doors:
    w, d, h = dims(e)

    if h > 3000:
        verticals.append(e)
    elif 150 < h < 400:
        headers.append(e)
    elif h < 100:
        sills.append(e)

if len(verticals) < 2:
    forms.alert("Error: Could not find enough vertical Door studs.")
    raise SystemExit

verticals_sorted = sorted(verticals, key=lambda e: cx(e))
left_stud = verticals_sorted[0]
right_stud = verticals_sorted[-1]

if headers:
    headers_sorted = sorted(headers, key=lambda e: cz(e))
    top_header = headers_sorted[-1]
else:
    forms.alert("No header element (270 mm) found.")
    raise SystemExit

if sills:
    sills_sorted = sorted(sills, key=lambda e: cz(e))
    bottom_sill = sills_sorted[0]
else:
    bottom_sill = None


# ----------------------------------------------------------
# STEP 3 — Compute door geometry
# ----------------------------------------------------------
bL = get_bbox(left_stud)
bR = get_bbox(right_stud)
bH = get_bbox(top_header)

xmin = bL.Max.X
xmax = bR.Min.X

if bottom_sill:
    bS = get_bbox(bottom_sill)
    zmin = bS.Max.Z
else:
    zmin = min(bL.Min.Z, bR.Min.Z)

zmax = bH.Min.Z

ymin = min(bL.Min.Y, bR.Min.Y, bH.Min.Y)
ymax = max(bL.Max.Y, bR.Max.Y, bH.Max.Y)

door_width = (xmax - xmin) * 304.8
door_height = (zmax - zmin) * 304.8
door_depth = (ymax - ymin) * 304.8

center_point = {
    "x": (xmin + xmax) / 2.0,
    "y": (ymin + ymax) / 2.0,
    "z": (zmin + zmax) / 2.0
}

# Print results
print("\n==============================")
print("       DOOR GEOMETRY")
print("==============================\n")

print("Left Stud ID:  ", left_stud.Id)
print("Right Stud ID: ", right_stud.Id)
print("Header ID:     ", top_header.Id)
print("Sill ID:       ", bottom_sill.Id if bottom_sill else "None")

print("\nDoor Width  = {:.1f} mm".format(door_width))
print("Door Height = {:.1f} mm".format(door_height))
print("Door Depth  = {:.1f} mm".format(door_depth))

print("\nCenter Point:")
print(center_point)


# ----------------------------------------------------------
# STEP 4 — Save JSON file
# ----------------------------------------------------------
out_data = {
    "door_width_mm": door_width,
    "door_height_mm": door_height,
    "door_depth_mm": door_depth,
    "center_point": center_point,
    "bbox": {
        "xmin": xmin, "xmax": xmax,
        "ymin": ymin, "ymax": ymax,
        "zmin": zmin, "zmax": zmax
    },
    "elements": {
        "left_stud": left_stud.Id.IntegerValue,
        "right_stud": right_stud.Id.IntegerValue,
        "header": top_header.Id.IntegerValue,
        "sill": bottom_sill.Id.IntegerValue if bottom_sill else None
    }
}
desktop = os.path.join(os.environ["USERPROFILE"], r"C:\Users\ma3589\Downloads\New folder")
out_path = os.path.join(desktop, "door_data.json")

with open(out_path, "w") as f:
    json.dump(out_data, f, indent=4)


# ----------------------------------------------------------
# STEP 5 — Highlight the door opening region
# ----------------------------------------------------------
# Find solid pattern
fps = FilteredElementCollector(doc).OfClass(FillPatternElement)
solid = None
for fp in fps:
    if fp.GetFillPattern().IsSolidFill:
        solid = fp
        break

ogs = OverrideGraphicSettings()
ogs.SetProjectionLineColor(Color(255, 0, 0))
ogs.SetSurfaceForegroundPatternId(solid.Id)
ogs.SetSurfaceForegroundPatternColor(Color(255, 0, 0))


# Build a 3D outline for the door opening
door_outline = Outline(
    XYZ(xmin, ymin, zmin),
    XYZ(xmax, ymax, zmax)
)

with revit.Transaction("Highlight Door Opening"):
    for e in collector:
        b = get_bbox(e)
        if not b: 
            continue
        element_outline = Outline(b.Min, b.Max)
        if door_outline.Intersects(element_outline, 0.0):
            view.SetElementOverrides(e.Id, ogs)


forms.alert("Door extracted + highlighted.\nJSON saved to Desktop.")
