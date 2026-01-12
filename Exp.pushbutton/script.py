# -*- coding: utf-8 -*-
__title__ = "Exp side loc mark [OPTIMIZED]"
__author__ = "Script"
__doc__ = "Detect doors, classify sides + floors, export BIM, match YOLO, highlight."

from pyrevit import revit, forms
from Autodesk.Revit.DB import FilteredElementCollector, ElementId

# Import refactored modules
from logger import Logger
from config import FACADE_SIDES
from detector.collectors import collect_bim_openings
from detector.grouping import (
    split_studs_headers,
    group_studs_into_rows_and_pairs,
    build_door_groups,
    match_headers_for_door
)
from detector.panels import (
    compute_global_bounds,
    classify_all_panels,
    classify_door_side,
    init_side_summary
)
from detector.sides import classify_side
from detector.geometry import dims, build_bbox_cache
from detector.highlight import (
    highlight_panels_by_floor,
    highlight_panels_by_side,
    highlight_door
)
from detector.json_io import (
    load_yolo_detections,
    load_bim_export,
    save_side_summary,
    save_door_output,
    save_yolo_bim_matches,
    save_side_sequences
)
from detector.bim_export import export_bim_geometry
from detector.matching import match_all_yolo_to_bim

# ============================================================
# MAIN PIPELINE
# ============================================================

doc = revit.doc
view = doc.ActiveView

Logger.section("PIPELINE START")

# ---------------------------------------------------------
# STEP 1 — COLLECT MODEL ELEMENTS
# ---------------------------------------------------------
Logger.subsection("Step 1: Collecting BIM Elements")

bim = collect_bim_openings(doc, view)
door_elems = bim["door"]
window_elems = bim["windows"]
panel_elems = bim["panels"]

if not panel_elems:
    forms.alert("No wall panels found. Stopping.", exitscript=True)

Logger.info("Collected: Doors=%d, Windows=%d, Panels=%d",
           len(door_elems), len(window_elems), len(panel_elems))

# ---------------------------------------------------------
# OPTIMIZATION: Build element caches
# ---------------------------------------------------------
Logger.subsection("Building Element Caches")

all_elements = list(door_elems) + list(window_elems) + list(panel_elems)
bbox_cache = build_bbox_cache(all_elements, view)

# Build element lookup
element_cache = {}
for e in FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType():
    element_cache[e.Id.IntegerValue] = e

Logger.info("Cached %d element bounding boxes", len(bbox_cache))
Logger.info("Cached %d element references", len(element_cache))

# ---------------------------------------------------------
# STEP 2 — STUD / HEADER SPLITTING
# ---------------------------------------------------------
Logger.subsection("Step 2: Processing Door Components")

studs, headers = split_studs_headers(door_elems, view)
rowA, rowB, pairs = group_studs_into_rows_and_pairs(studs)

Logger.info("Found %d stud pairs for doors", len(pairs))

# ---------------------------------------------------------
# STEP 3 — BUILD DOOR GROUPS
# ---------------------------------------------------------
Logger.subsection("Step 3: Building Door Groups")

door_groups = build_door_groups(pairs, view)
Logger.info("Created %d logical door groups", len(door_groups))

# ---------------------------------------------------------
# STEP 4 — PANEL CLASSIFICATION (SIDE + FLOOR)
# ---------------------------------------------------------
Logger.subsection("Step 4: Classifying Panels")

bounds = compute_global_bounds(panel_elems, view)
side_summary = classify_all_panels(panel_elems, view)

# ---------------------------------------------------------
# STEP 5 — ASSIGN WINDOWS TO SIDES
# ---------------------------------------------------------
Logger.subsection("Step 5: Assigning Windows to Sides")

for e in window_elems:
    d = dims(e, view)
    if not d:
        continue
    
    cx = (d[3] + d[4]) / 2.0
    cy = (d[5] + d[6]) / 2.0
    
    xmin_b, xmax_b, ymin_b, ymax_b = bounds
    
    dA = abs(cx - xmin_b)
    dC = abs(cx - xmax_b)
    dB = abs(cy - ymin_b)
    dD = abs(cy - ymax_b)
    
    m = min(dA, dB, dC, dD)
    if m == dA:
        side = "A"
    elif m == dC:
        side = "C"
    elif m == dB:
        side = "B"
    else:
        side = "D"
    
    side_summary[side]["windows"].append(e.Id.IntegerValue)

window_count = sum(len(side_summary[s]["windows"]) for s in FACADE_SIDES)
Logger.info("Assigned %d windows to sides", window_count)

# ---------------------------------------------------------
# STEP 6 — ASSIGN DOORS TO SIDES
# ---------------------------------------------------------
Logger.subsection("Step 6: Assigning Doors to Sides")

door_side_map = classify_door_side(door_groups, bounds)

for did, side in door_side_map.items():
    side_summary[side]["door"].append(did)

save_side_summary(side_summary)

# ---------------------------------------------------------
# STEP 7 — MATCH HEADERS TO DOOR STUDS
# ---------------------------------------------------------
Logger.subsection("Step 7: Matching Headers to Doors")

door_output = match_headers_for_door(pairs, headers, view)
save_door_output(door_output)

Logger.info("Matched %d doors with headers", len(door_output))

# ---------------------------------------------------------
# STEP 8 — EXPORT BIM GEOMETRY
# ---------------------------------------------------------
Logger.subsection("Step 8: Exporting BIM Geometry")

from config import PATHS
bim_export = export_bim_geometry(
    doc, view, side_summary, door_output, door_side_map, 
    PATHS["bim_export"]
)

# Save sequences
save_side_sequences(bim_export, side_summary)

# ---------------------------------------------------------
# STEP 9 — LOAD YOLO AND CLASSIFY SIDE
# ---------------------------------------------------------
Logger.subsection("Step 9: YOLO Side Classification")

yolo = load_yolo_detections()
classified_side, score = classify_side(yolo, bim_export)

Logger.info("Classified side: %s | Score: %.3f", classified_side, score)

# ---------------------------------------------------------
# STEP 10 — YOLO–BIM MATCHING
# ---------------------------------------------------------
Logger.subsection("Step 10: Matching YOLO to BIM")

matches = match_all_yolo_to_bim(yolo, bim_export, classified_side)

Logger.info("Generated %d YOLO-BIM matches", len(matches))

# Print match summary
matched_count = sum(1 for m in matches if m.get("bim_id") is not None)
Logger.info("Successfully matched: %d/%d", matched_count, len(matches))

save_yolo_bim_matches(matches, classified_side, score)

# ---------------------------------------------------------
# STEP 11 — HIGHLIGHTING (SINGLE TRANSACTION)
# ---------------------------------------------------------
Logger.subsection("Step 11: Highlighting Elements in Revit")

with revit.Transaction("Apply All Highlighting"):
    highlight_panels_by_side(side_summary, doc, view, highlight_only=classified_side)
    highlight_panels_by_floor(side_summary, doc, view, highlight_only=classified_side)
    highlight_door(door_output, None, doc, view)

Logger.info("Highlighting complete for side: %s", classified_side)

# ---------------------------------------------------------
# PIPELINE COMPLETE
# ---------------------------------------------------------
Logger.section("PIPELINE COMPLETE")
Logger.info("All operations finished successfully")