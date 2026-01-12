# -*- coding: utf-8 -*-
__title__ = "Detect Doors (Stable Version)"
__author__ = "Script"
__doc__ = "Detect studs + headers with one-time-use matching."
#Finds door elements by name, sorts them by xyz and limits each element to 1
from Autodesk.Revit.DB import *
from pyrevit import revit, forms
import os, json
from math import hypot


doc = revit.doc
view = doc.ActiveView


# ---------------------- HELPERS ----------------------
def bbox(e):
    return e.get_BoundingBox(view)

def dims(e):
    b = bbox(e)
    if not b:
        return None
    to_mm = 304.8
    return (
        (b.Max.X - b.Min.X) * to_mm,                        # w
        (b.Max.Y - b.Min.Y) * to_mm,                        # d
        (b.Max.Z - b.Min.Z) * to_mm,                        # h
        b.Min.X * to_mm, b.Max.X * to_mm,                   # xmin, xmax
        b.Min.Y * to_mm, b.Max.Y * to_mm,                   # ymin, ymax
        b.Min.Z * to_mm, b.Max.Z * to_mm                    # zmin, zmax
    )

def mid_xy(d):
    _,_,_, xmin, xmax, ymin, ymax, _, _ = d
    return ((xmin+xmax)/2, (ymin+ymax)/2)


# ---------------------- COLLECT DOOR ELEMENTS ----------------------
collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
door_elems = [e for e in collector if (e.Name or "") == "Door"]

if not door_elems:
    forms.alert("No Door elements found.")
    raise SystemExit


# ---------------------- SPLIT STUDS / HEADERS ----------------------
studs = []
headers = []

for e in door_elems:
    d = dims(e)
    if not d:
        continue

    w = d[0]
    depth = d[1]
    h = d[2]

    if h > 500:
        studs.append((e, d))
    else:
        headers.append((e, d))



if len(studs) < 2:
    forms.alert("Not enough studs.")
    raise SystemExit

if len(headers) < 1:
    forms.alert("No headers found.")
    raise SystemExit


# ---------------------- GROUP STUDS BY HEIGHT ----------------------
# Sort studs by their Z center
studs_sorted = sorted(studs, key=lambda sd: ( (sd[1][7] + sd[1][8]) / 2 ))

# Now split into rows (bottom 2, top 2)
if len(studs_sorted) != 4:
    forms.alert("Expected 4 studs only. Adjust logic if needed.")
    raise SystemExit

# bottom row = first 2 studs
rowA = studs_sorted[0:2]
# top row = last 2 studs
rowB = studs_sorted[2:4]

# sort each row by X to get left–right order
rowA = sorted(rowA, key=lambda sd: (sd[1][3] + sd[1][4]) / 2)
rowB = sorted(rowB, key=lambda sd: (sd[1][3] + sd[1][4]) / 2)

# pair them
pairs = [
    (rowA[0], rowA[1]),   # Door 1 studs
    (rowB[0], rowB[1])    # Door 2 studs
]



# ---------------------- PREP COLORS ----------------------
fps = FilteredElementCollector(doc).OfClass(FillPatternElement)
solid = next(fp for fp in fps if fp.GetFillPattern().IsSolidFill)

def make_color(r, g, b):
    ogs = OverrideGraphicSettings()
    ogs.SetProjectionLineColor(Color(r,g,b))
    ogs.SetSurfaceForegroundPatternId(solid.Id)
    ogs.SetSurfaceForegroundPatternColor(Color(r,g,b))
    return ogs

door_colors = [
    make_color(255, 0, 0),
    make_color(0, 255, 0),
    make_color(0, 0, 255),
]


# ---------------------- ASSIGN HEADERS (USE ONCE ONLY) ----------------------
unused_headers = headers[:]

door_output = []
door_index = 1

with revit.Transaction("Highlight Doors"):
    for (eL, dL), (eR, dR) in pairs:

        # find stud top midpoint
        _,_,_, xminL,xmaxL, yminL,ymaxL, zminL,zmaxL = dL
        _,_,_, xminR,xmaxR, yminR,ymaxR, zminR,zmaxR = dR

        stud_top_z = min(zmaxL, zmaxR)

        # find header closest in Z
        best = None
        best_diff = 999999

        for eH, dH in unused_headers:
            _,_,_, xminH,xmaxH, yminH,ymaxH, zminH,zmaxH = dH
            header_z = (zminH + zmaxH)/2
            diff = abs(header_z - stud_top_z)
            if diff < best_diff:
                best_diff = diff
                best = (eH, dH)

        if not best:
            print("[WARN] No header available.")
            continue

        eH, dH = best

        # remove header so it cannot be reused
        unused_headers.remove(best)

        # highlight both studs + header in same door color
        door_color = door_colors[(door_index-1) % len(door_colors)]
        view.SetElementOverrides(eL.Id, door_color)
        view.SetElementOverrides(eR.Id, door_color)
        view.SetElementOverrides(eH.Id, door_color)

        # compute width
        left_x = (xminL + xmaxL)/2
        right_x = (xminR + xmaxR)/2
        width = abs(right_x - left_x)

        # height
        _,_,_,_,_,_,_, zminH, _ = dH
        height = abs(zminH - min(zminL, zminR))

        # record
        door_output.append({
            "door": door_index,
            "label": "Door",
            "stud_left": eL.Id.IntegerValue,
            "stud_right": eR.Id.IntegerValue,
            "header": eH.Id.IntegerValue,
            "width_mm": width,
            "height_mm": height
        })

        print("\n=== DOOR", door_index, "===")
        print(" Studs:", eL.Id.IntegerValue, eR.Id.IntegerValue)
        print(" Header:", eH.Id.IntegerValue)
        print(" Width:", width)
        print(" Height:", height)

        door_index += 1


# ---------------------- SUMMARY ----------------------
print("\n=========================================")
print("         FINAL DOOR SUMMARY")
print("=========================================\n")

print("Total doors:", len(door_output))
for d in door_output:
    print("\nDoor", d["door"])
    print(" Studs:", d["stud_left"], d["stud_right"])
    print(" Header:", d["header"])
    print(" Width:", d["width_mm"])
    print(" Height:", d["height_mm"])
# ---------------------- SAVE JSON ----------------------
desktop = os.path.join(os.environ["USERPROFILE"], r"C:/Users/ma3589/OneDrive - The University of Waikato/Desktop/Topic 3/Pyrevit/Data_saves/Door_detections")
path = os.path.join(desktop, "door_detection_output.json")

with open(path, "w") as f:
    json.dump(door_output, f, indent=4)

print("\nJSON saved to:", path)
print("=========================================\n")
