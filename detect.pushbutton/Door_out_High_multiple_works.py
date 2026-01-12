# -*- coding: utf-8 -*-
__title__ = "Detect Doors by Type"
__author__ = "Ahmad + ChatGPT"
__doc__ = "Detect doors using Type Name = Door, group studs, and match headers correctly per door."

from Autodesk.Revit.DB import *
from pyrevit import revit, forms
import os, json
from collections import defaultdict

doc = revit.doc
view = doc.ActiveView


# -------------------------- HELPERS --------------------------
def bbox(e):
    return e.get_BoundingBox(view)

def dims(e):
    """Return (w, d, h, xmin, xmax, ymin, ymax, zmin, zmax) in mm."""
    b = bbox(e)
    if not b:
        return None
    w = (b.Max.X - b.Min.X) * 304.8
    d = (b.Max.Y - b.Min.Y) * 304.8
    h = (b.Max.Z - b.Min.Z) * 304.8
    xmin = b.Min.X * 304.8
    xmax = b.Max.X * 304.8
    ymin = b.Min.Y * 304.8
    ymax = b.Max.Y * 304.8
    zmin = b.Min.Z * 304.8
    zmax = b.Max.Z * 304.8
    return (w, d, h, xmin, xmax, ymin, ymax, zmin, zmax)

def mid_x_from_dims(d):
    _, _, _, xmin, xmax, _, _, _, _ = d
    return (xmin + xmax) / 2.0



# -------------------------- COLLECT ONLY DOOR-TYPE ELEMENTS --------------------------
collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()

door_elems = []
for e in collector:
    etype = doc.GetElement(e.GetTypeId())
    if not etype:
        continue

    p = etype.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_AND_TYPE_NAMES_PARAM)
    if not p:
        continue

    tname = p.AsString()
    if tname and "Door" in tname:
        door_elems.append(e)

if not door_elems:
    forms.alert("No Door-type elements found.")
    raise SystemExit



# -------------------------- SPLIT INTO STUDS + HEADERS --------------------------
studs = []
headers = []

for e in door_elems:
    d = dims(e)
    if not d:
        continue

    w, depth, h, xmin, xmax, ymin, ymax, zmin, zmax = d

    if h > 500:
        studs.append((e, d))
    elif h < 150:
        headers.append((e, d))



# -------------------------- GROUP STUDS INTO DOOR PAIRS --------------------------
def round5(x):
    return round(x / 5.0) * 5.0

x_groups = defaultdict(list)

for e, d in studs:
    xmid = mid_x_from_dims(d)
    x_groups[round5(xmid)].append((e, d))

# pick tallest from each X column
group_reps = []
for xkey, items in x_groups.items():
    tallest = max(items, key=lambda it: it[1][2])
    group_reps.append((xkey, tallest))

group_reps.sort(key=lambda g: g[0])

clusters = []
i = 0
while i < len(group_reps) - 1:
    x1, rep1 = group_reps[i]
    x2, rep2 = group_reps[i + 1]
    clusters.append((rep1, rep2))
    i += 2

if not clusters:
    forms.alert("No door stud pairs detected.")
    raise SystemExit



# -------------------------- PREP OVERRIDES --------------------------
fps = FilteredElementCollector(doc).OfClass(FillPatternElement)
solid = next(fp for fp in fps if fp.GetFillPattern().IsSolidFill)

ogs = OverrideGraphicSettings()
ogs.SetProjectionLineColor(Color(0, 0, 255))
ogs.SetSurfaceForegroundPatternId(solid.Id)
ogs.SetSurfaceForegroundPatternColor(Color(0, 0, 255))



# -------------------------- PROCESS DOORS --------------------------
door_output = []
door_index = 1

with revit.Transaction("Highlight Doors by Type"):
    for (eL, dL), (eR, dR) in clusters:

        # Stud bounds
        wL, dL_, hL, xminL, xmaxL, yminL, ymaxL, zminL, zmaxL = dL
        wR, dR_, hR, xminR, xmaxR, ymaxR, yminR, zminR, zmaxR = dR

        door_xmin = min(xminL, xminR)
        door_xmax = max(xmaxL, xmaxR)
        door_zmin = min(zminL, zminR)
        door_zmax = min(zmaxL, zmaxR)

        assigned_headers = []

        # ---------------------------- FIXED HEADER MATCHING ----------------------------
        for eH, dH in headers:
            wH, dH_, hH, xminH, xmaxH, yminH, ymaxH, zminH, zmaxH = dH
            header_z_center = (zminH + zmaxH) / 2.0

            # TIGHT horizontal match: header must sit BETWEEN the two studs
            horizontal_ok = (
                xminH >= door_xmin - 5 and
                xmaxH <= door_xmax + 5
            )

            # Vertical alignment stays the same
            vertical_ok = (door_zmin <= header_z_center <= door_zmax)

            if horizontal_ok and vertical_ok:
                assigned_headers.append((eH, dH))
        # -------------------------------------------------------------------------------

        if not assigned_headers:
            print("\n[WARN] No header matched for door", door_index)
            continue

        # sort by elevation (lowest first)
        assigned_headers.sort(key=lambda h: h[1][7])

        # lower header = used for height calc
        lower_header, lower_dims = assigned_headers[0]

        # highlight studs + ALL headers
        for el, _ in assigned_headers:
            view.SetElementOverrides(el.Id, ogs)

        # compute door height (using lower header)
        _, _, _, _, _, _, _, zminH_lower, _ = lower_dims
        width = abs(door_xmax - door_xmin)
        height = abs(zminH_lower - door_zmin)

        # record IDs of all headers belonging to this door
        header_ids = [eH.Id.IntegerValue for eH, _ in assigned_headers]

        # save output
        door_output.append({
            "door_index": door_index,
            "left_stud_id": eL.Id.IntegerValue,
            "right_stud_id": eR.Id.IntegerValue,
            "header_ids": header_ids,
            "width_mm": width,
            "height_mm": height
        })

        door_index += 1



# -------------------------- SAVE JSON --------------------------
desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
path = os.path.join(desktop, "door_by_type.json")
# -------------------------- SAVE JSON --------------------------
desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
path = os.path.join(desktop, "door_by_type.json")

with open(path, "w") as f:
    json.dump(door_output, f, indent=4)


# -------------------------- PRINT SUMMARY --------------------------
print("\n=========================================")
print("           DOOR DETECTION SUMMARY        ")
print("=========================================\n")

print("Total studs found:   ", len(studs))
print("Total headers found: ", len(headers))
print("Total doors detected:", len(door_output))
print("\n-----------------------------------------\n")

for door in door_output:
    print("DOOR", door["door_index"])
    print(" Left Stud ID:   ", door["left_stud_id"])
    print(" Right Stud ID:  ", door["right_stud_id"])

    if len(door["header_ids"]) == 1:
        print(" Header ID:      ", door["header_ids"][0])
    elif len(door["header_ids"]) >= 2:
        print(" Lower Header ID:", door["header_ids"][0])
        print(" Upper Header ID:", door["header_ids"][1])

    print(" Width (mm):     ", door["width_mm"])
    print(" Height (mm):    ", door["height_mm"])
    print("-----------------------------------------\n")

print("JSON saved to:", path)
print("\n=========================================\n")
