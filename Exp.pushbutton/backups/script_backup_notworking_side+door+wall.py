# -*- coding: utf-8 -*-
__title__ = "Exp side loc mark"
__author__ = "Script"
__doc__ = "Detect doors, assign sides + floors to panels, export JSON, and highlight."

from Autodesk.Revit.DB import *
from pyrevit import revit, forms
import os, json

doc = revit.doc
view = doc.ActiveView


# ----------------------------------------------------------------------
# YOLO JSON FILTER (door indexes to highlight)
# ----------------------------------------------------------------------
JSON_PATH = r"C:/Users/ma3589/OneDrive - The University of Waikato/Desktop/Topic 3/Pyrevit/Data_saves/Door_detections/door_detection_output.json"
JSON_KEY = "door"   # JSON must contain entries like {"door": 1, ...}


def load_json_labels():
    """Load list of door numbers from JSON (as strings)."""
    if not os.path.exists(JSON_PATH):
        forms.alert("JSON file not found:\n{}".format(JSON_PATH), exitscript=False)
        return None

    try:
        with open(JSON_PATH, "r") as f:
            data = json.load(f)
    except:
        forms.alert("Error reading JSON file.", exitscript=False)
        return None

    labels = set()

    # Case 1: list of dicts: [{"door": 1}, {"door": 2}, ...]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        for entry in data:
            v = entry.get(JSON_KEY)
            if v is not None:
                labels.add(str(v).strip())

    # Case 2: ["1","2",...]
    elif isinstance(data, list):
        labels = {str(v).strip() for v in data}

    return labels or None


json_labels = load_json_labels()

print("\n========== TROUBLESHOOTING START ==========\n")
print("JSON labels loaded:", json_labels)

bim_doors_debug = []
for e in FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType():
    name = (e.Name or "").lower()
    if "door" in name:
        bim_doors_debug.append(e)
        print("  Found BIM element with 'door' in name, ID:", e.Id.IntegerValue)

if not bim_doors_debug:
    print("NO BIM elements with 'door' in their name found in this view!")
else:
    print("Total BIM 'door-like' elements found:", len(bim_doors_debug))

print("\n========== TROUBLESHOOTING END ==========\n")


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
def bbox(e):
    return e.get_BoundingBox(view)

def dims(e):
    """Return (w, d, h, xmin, xmax, ymin, ymax, zmin, zmax) in mm."""
    b = bbox(e)
    if not b:
        return None
    to_mm = 304.8
    return (
        (b.Max.X - b.Min.X) * to_mm,   # w
        (b.Max.Y - b.Min.Y) * to_mm,   # d
        (b.Max.Z - b.Min.Z) * to_mm,   # h
        b.Min.X * to_mm, b.Max.X * to_mm,
        b.Min.Y * to_mm, b.Max.Y * to_mm,
        b.Min.Z * to_mm, b.Max.Z * to_mm
    )

def mid_xy(d):
    _, _, _, xmin, xmax, ymin, ymax, _, _ = d
    return ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)


# ----------------------------------------------------------------------
# COLLECT ELEMENTS BY NAME
# ----------------------------------------------------------------------
collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()

door_elems   = []   # CFS members named "door" (studs + headers)
window_elems = []   # elements named "windows"
panel_elems  = []   # elements named "Wall Panel"

for e in collector:
    name = (e.Name or "").strip()
    if name == "door":
        door_elems.append(e)
    elif name == "windows":
        window_elems.append(e)
    elif name == "Wall Panel":
        panel_elems.append(e)

print("\n========== ELEMENT COUNTS ==========\n")
print("door elements   :", len(door_elems))
print("windows elements:", len(window_elems))
print("Wall Panel     :", len(panel_elems))

if not door_elems:
    forms.alert("No 'door' elements found. Door logic may fail.", exitscript=False)
if not panel_elems:
    forms.alert("No 'Wall Panel' elements found. Side detection will fail.", exitscript=True)


# ----------------------------------------------------------------------
# BUILDING BOUNDS FROM WALL PANEL (for side A/B/C/D)
# ----------------------------------------------------------------------
panel_midpoints = []
for e in panel_elems:
    d = dims(e)
    if not d:
        continue
    cx, cy = mid_xy(d)
    panel_midpoints.append((cx, cy))

if not panel_midpoints:
    forms.alert("No valid Wall Panel bounding boxes. Cannot determine sides.", exitscript=True)

all_x = [p[0] for p in panel_midpoints]
all_y = [p[1] for p in panel_midpoints]

xmin = min(all_x)
xmax = max(all_x)
ymin = min(all_y)
ymax = max(all_y)

print("\nEstimated building bounds (mm):")
print(" xmin:", xmin, "xmax:", xmax, "ymin:", ymin, "ymax:", ymax)

edge_tol = 200.0  # mm, tolerance to consider "on that side"

def classify_side_edge(cx, cy):
    """Return 'A','B','C','D' or None, based on proximity to building edges."""
    d_left   = abs(cx - xmin)
    d_right  = abs(cx - xmax)
    d_bottom = abs(cy - ymin)
    d_top    = abs(cy - ymax)

    d_min = min(d_left, d_right, d_bottom, d_top)

    if d_min > edge_tol:
        return None

    if d_min == d_left:
        return "A"   # left
    elif d_min == d_right:
        return "C"   # right
    elif d_min == d_bottom:
        return "B"   # bottom
    else:
        return "D"   # top


# ----------------------------------------------------------------------
# SPLIT DOOR_ELEMS INTO STUDS / HEADERS
# ----------------------------------------------------------------------
studs   = []
headers = []

for e in door_elems:
    d = dims(e)
    if not d:
        continue

    w, depth, h, xmin_d, xmax_d, ymin_d, ymax_d, zmin_d, zmax_d = d

    if h > 500.0:
        studs.append((e, d))
    else:
        headers.append((e, d))

if len(studs) < 2:
    forms.alert("Not enough studs detected from 'door' elements.", exitscript=True)

if len(headers) < 1:
    forms.alert("No headers detected from 'door' elements.", exitscript=True)


# ----------------------------------------------------------------------
# GROUP STUDS BY HEIGHT INTO TWO ROWS (FLOOR 1 + FLOOR 2)
# ----------------------------------------------------------------------
studs_sorted = sorted(studs, key=lambda sd: ((sd[1][7] + sd[1][8]) / 2.0))  # by Z-center

if len(studs_sorted) != 4:
    forms.alert("Expected exactly 4 studs (2 doors, 2 floors). Adjust logic if needed.", exitscript=True)

# lower 2 studs = floor 1, upper 2 studs = floor 2
rowA = sorted(studs_sorted[0:2], key=lambda sd: (sd[1][3] + sd[1][4]) / 2.0)  # left-right
rowB = sorted(studs_sorted[2:4], key=lambda sd: (sd[1][3] + sd[1][4]) / 2.0)

pairs = [
    (rowA[0], rowA[1]),  # Door 1 studs (floor 1)
    (rowB[0], rowB[1])   # Door 2 studs (floor 2)
]

print("\nDOOR STUD PAIRS:")
for i, ((eL, dL), (eR, dR)) in enumerate(pairs, start=1):
    print(" Door", i, "studs:", eL.Id.IntegerValue, eR.Id.IntegerValue)


# ----------------------------------------------------------------------
# STUD-BASED FLOOR CLASSIFICATION FOR PANELS
# ----------------------------------------------------------------------
# Build list of all stud centers
stud_centers = []
for (e_s, d_s) in studs:
    _, _, _, xmin_s, xmax_s, ymin_s, ymax_s, zmin_s, zmax_s = d_s
    cx_s = (xmin_s + xmax_s) / 2.0
    cy_s = (ymin_s + ymax_s) / 2.0
    cz_s = (zmin_s + zmax_s) / 2.0
    stud_centers.append((cx_s, cy_s, cz_s))

# Typical Z for floor-1 & floor-2 studs
rowA_z = sum([(d[7] + d[8]) / 2.0 for e, d in rowA]) / len(rowA)
rowB_z = sum([(d[7] + d[8]) / 2.0 for e, d in rowB]) / len(rowB)

def classify_panel_floor_by_studs(panel_d):
    """Return floor1 / floor2 / both / unknown using studs inside panel footprint."""
    _, _, _, xmin_p, xmax_p, ymin_p, ymax_p, zmin_p, zmax_p = panel_d

    found_floor1 = False
    found_floor2 = False

    for (cx_s, cy_s, cz_s) in stud_centers:
        if xmin_p <= cx_s <= xmax_p and ymin_p <= cy_s <= ymax_p:
            # compare this stud's Z with typical rowZ
            if abs(cz_s - rowA_z) < abs(cz_s - rowB_z):
                found_floor1 = True
            else:
                found_floor2 = True

    if found_floor1 and found_floor2:
        return "both"
    if found_floor1:
        return "floor1"
    if found_floor2:
        return "floor2"
    return "unknown"


# Fallback simple height-based classifier (as backup only)
def classify_panel_floor_simple(panel_d):
    _, _, _, _, _, _, _, zmin_p, zmax_p = panel_d
    panel_z = (zmin_p + zmax_p) / 2.0

    distA = abs(panel_z - rowA_z)
    distB = abs(panel_z - rowB_z)

    if distA < distB:
        return "floor1"
    elif distB < distA:
        return "floor2"
    else:
        return "both"


# ----------------------------------------------------------------------
# COLLECT PANELS & WINDOWS WITH DIMENSIONS
# ----------------------------------------------------------------------
all_panels  = []
all_windows = []

for e in panel_elems:
    d = dims(e)
    if d:
        all_panels.append((e, d))

for e in window_elems:
    d = dims(e)
    if d:
        all_windows.append((e, d))


# ----------------------------------------------------------------------
# BUILD DOOR GROUPS (DOOR 1, DOOR 2) WITH CENTER POINTS
# ----------------------------------------------------------------------
all_door_groups = []

for idx, ((eL, dL), (eR, dR)) in enumerate(pairs, start=1):
    cxL, cyL = mid_xy(dL)
    cxR, cyR = mid_xy(dR)
    door_center = ((cxL + cxR) / 2.0, (cyL + cyR) / 2.0)

    all_door_groups.append({
        "id": idx,
        "stud_left": eL.Id.IntegerValue,
        "stud_right": eR.Id.IntegerValue,
        "center": door_center
    })


# ----------------------------------------------------------------------
# SIDE SUMMARY STRUCTURE
# ----------------------------------------------------------------------
side_summary = {
    s: {
        "doors": [],
        "windows": [],
        "panels": [],
        "panels_floor1": [],
        "panels_floor2": [],
        "panels_both": []
    }
    for s in ["A", "B", "C", "D"]
}


# Assign doors to sides
for door in all_door_groups:
    cx, cy = door["center"]
    side = classify_side_edge(cx, cy)
    if side in side_summary:
        side_summary[side]["doors"].append(door["id"])


# Assign windows and panels to side + floor
for e, d in all_windows:
    cx, cy = mid_xy(d)
    side = classify_side_edge(cx, cy)
    if side in side_summary:
        side_summary[side]["windows"].append(e.Id.IntegerValue)

for e, d in all_panels:
    cx, cy = mid_xy(d)
    side = classify_side_edge(cx, cy)
    if side not in side_summary:
        continue

    # floor classification using studs
    floor = classify_panel_floor_by_studs(d)
    if floor == "unknown":
        floor = classify_panel_floor_simple(d)

    # record
    side_summary[side]["panels"].append(e.Id.IntegerValue)
    if floor == "floor1":
        side_summary[side]["panels_floor1"].append(e.Id.IntegerValue)
    elif floor == "floor2":
        side_summary[side]["panels_floor2"].append(e.Id.IntegerValue)
    elif floor == "both":
        side_summary[side]["panels_both"].append(e.Id.IntegerValue)


print("\nEXTERIOR SIDE ASSIGNMENT (with floors):")
for side in ["A", "B", "C", "D"]:
    info = side_summary[side]
    print("\nSide", side)
    print(" Doors:        ", info["doors"])
    print(" Windows:      ", info["windows"])
    print(" Panels (all): ", info["panels"])
    print(" Panels F1:    ", info["panels_floor1"])
    print(" Panels F2:    ", info["panels_floor2"])
    print(" Panels BOTH:  ", info["panels_both"])


# ----------------------------------------------------------------------
# SAVE SIDE SUMMARY JSON
# ----------------------------------------------------------------------
save_folder = r"C:/Users/ma3589/OneDrive - The University of Waikato/Desktop/Topic 3/Pyrevit/Data_saves/Door_detections"
if not os.path.exists(save_folder):
    os.makedirs(save_folder)

side_json_path = os.path.join(save_folder, "side_objects_summary.json")

with open(side_json_path, "w") as f:
    json.dump(side_summary, f, indent=4)

print("\nSaved updated side summary:", side_json_path)


# ----------------------------------------------------------------------
# PREP COLORS
# ----------------------------------------------------------------------
fps = FilteredElementCollector(doc).OfClass(FillPatternElement)
solid = next(fp for fp in fps if fp.GetFillPattern().IsSolidFill)

def make_color(r, g, b):
    ogs = OverrideGraphicSettings()
    ogs.SetProjectionLineColor(Color(r, g, b))
    ogs.SetSurfaceForegroundPatternId(solid.Id)
    ogs.SetSurfaceForegroundPatternColor(Color(r, g, b))
    return ogs

door_colors = [
    make_color(255, 0, 0),
    make_color(0, 255, 0),
    make_color(0, 0, 255),
]

side_colors = {
    "A": make_color(255, 0, 0),      # Red
    "B": make_color(0, 255, 0),      # Green
    "C": make_color(0, 0, 255),      # Blue
    "D": make_color(255, 255, 0),    # Yellow
}


# ----------------------------------------------------------------------
# MATCH + HIGHLIGHT DOORS (studs + header per door, filtered by JSON)
# ----------------------------------------------------------------------
unused_headers = headers[:]
door_output = []
door_index = 1

with revit.Transaction("Highlight Doors"):
    for (eL, dL), (eR, dR) in pairs:

        # Filter by YOLO JSON labels (door index)
        if json_labels and str(door_index) not in json_labels:
            print("Skipping door", door_index, "(not in YOLO JSON)")
            door_index += 1
            continue

        # header matching by Z proximity
        _,_,_, xminL,xmaxL, yminL,ymaxL, zminL,zmaxL = dL
        _,_,_, xminR,xmaxR, yminR,ymaxR, zminR,zmaxR = dR

        stud_top_z = min(zmaxL, zmaxR)

        best = None
        best_diff = 999999.0

        for eH, dH in unused_headers:
            _,_,_, xminH,xmaxH, yminH,ymaxH, zminH,zmaxH = dH
            header_z = (zminH + zmaxH) / 2.0
            diff = abs(header_z - stud_top_z)
            if diff < best_diff:
                best_diff = diff
                best = (eH, dH)

        if not best:
            print("[WARN] No header available for door", door_index)
            door_index += 1
            continue

        eH, dH = best
        unused_headers.remove(best)

        # highlight door elements
        door_color = door_colors[(door_index - 1) % len(door_colors)]
        view.SetElementOverrides(eL.Id, door_color)
        view.SetElementOverrides(eR.Id, door_color)
        view.SetElementOverrides(eH.Id, door_color)

        # compute width & height
        left_x  = (xminL + xmaxL) / 2.0
        right_x = (xminR + xmaxR) / 2.0
        width   = abs(right_x - left_x)
        height  = abs(dH[7] - min(zminL, zminR))

        door_output.append({
            "door": door_index,
            "stud_left":  eL.Id.IntegerValue,
            "stud_right": eR.Id.IntegerValue,
            "header":     eH.Id.IntegerValue,
            "width_mm":   width,
            "height_mm":  height
        })

        print("\n=== DOOR", door_index, "===")
        print(" Studs:", eL.Id.IntegerValue, eR.Id.IntegerValue)
        print(" Header:", eH.Id.IntegerValue)
        print(" Width:", width)
        print(" Height:", height)

        door_index += 1


# ----------------------------------------------------------------------
# HIGHLIGHT WALL PANEL BY SIDE (color-coded façade)
# ----------------------------------------------------------------------
with revit.Transaction("Highlight Wall Panel by Side"):
    for side, info in side_summary.items():
        color = side_colors.get(side)
        if not color:
            continue
        for panel_id in info["panels"]:
            elem = doc.GetElement(ElementId(panel_id))
            if elem:
                view.SetElementOverrides(elem.Id, color)


# ----------------------------------------------------------------------
# SUMMARY
# ----------------------------------------------------------------------
print("\n=========================================")
print("       FINAL DOOR SUMMARY (Filtered)")
print("=========================================\n")

print("JSON labels used:", json_labels)
print("Total doors highlighted:", len(door_output))

for d in door_output:
    print("\nDoor", d["door"])
    print(" Studs:", d["stud_left"], d["stud_right"])
    print(" Header:", d["header"])
    print(" Width:", d["width_mm"])
    print(" Height:", d["height_mm"])
