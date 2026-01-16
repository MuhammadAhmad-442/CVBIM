# -*- coding: utf-8 -*-
"""
YOLO-BIM pipeline with fixed door processing logic
"""
__title__ = "YOLO-BIM Matcher"
__author__ = "Script"

import sys, os, traceback
from pyrevit import revit, forms
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, Wall, WallType, BuiltInCategory
DB = revit.DB

# =======================================================================
# MAIN PIPELINE
# =======================================================================

def main():
    """Main YOLO-BIM pipeline with fixed door processing."""

    doc = revit.doc
    view = doc.ActiveView

    if not view:
        forms.alert("No active view. Open a 3D view first.", exitscript=True)
        return

    # -------------------------------------------------------------------
    # MODULE IMPORTS
    # -------------------------------------------------------------------
    try:
        from detector.config import Log, SIDES, GROUP_DOOR_COMPONENTS
        from detector.core import build_element_cache, dims, center_xy, get_element_id
        from detector.classification import (
            classify_all_panels,
            classify_windows,
            process_doors_simple,
            split_studs_headers,
            group_door_studs,
            build_door_groups,
            match_headers,
            classify_yolo_side,
            classify_doors
        )
        from detector.export import (
            export_bim_geometry,
            match_yolo_to_bim,
            load_yolo,
            save_side_summary,
            save_door_output,
            save_yolo_matches,
            save_sequences
        )
        from detector.visualization import (
            highlight_panels_by_side,
            highlight_panels_by_floor,
            highlight_doors
        )
        Log.info("All modules loaded successfully")
    except Exception as e:
        print("FATAL ERROR: Cannot load modules")
        print(str(e))
        traceback.print_exc()
        forms.alert("Module import failed. Check console.", exitscript=True)
        return

    # -------------------------------------------------------------------
    # STEP 1 – SAFE ELEMENT COLLECTION
    # -------------------------------------------------------------------
    Log.section("STEP 1: SAFE COLLECTING BIM ELEMENTS")

    def _safe_name(elem):
        try: fam = elem.Symbol.Family.Name.lower()
        except: fam = ""
        try: typ = elem.Symbol.Name.lower()
        except: typ = ""
        try: name = elem.Name.lower()
        except: name = ""
        return fam, typ, name

    doors, windows, wall_panels = [], [], []

    try:
        # Collect by actual Revit category
        doors = list(FilteredElementCollector(doc, view.Id)
                     .OfClass(FamilyInstance)
                     .OfCategory(BuiltInCategory.OST_Doors)
                     .ToElements())
        
        windows = list(FilteredElementCollector(doc, view.Id)
                       .OfClass(FamilyInstance)
                       .OfCategory(BuiltInCategory.OST_Windows)
                       .ToElements())
        
        # For wall panels, use string matching
        wall_panels = []
        walls = FilteredElementCollector(doc, view.Id).OfClass(Wall).ToElements()
        
        Log.info("Total walls found in view: %d", len(walls))
        
        for wall in walls:
            try:
                wall_type = doc.GetElement(wall.GetTypeId())
                
                try:
                    type_name = wall_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
                    if type_name:
                        type_name = type_name.AsString()
                    else:
                        type_name = "Unknown"
                except:
                    try:
                        type_name = wall_type.FamilyName
                    except:
                        try:
                            type_name = str(wall_type.Name)
                        except:
                            type_name = "Unknown"
                
                Log.debug("Wall type found: '%s'", type_name)
                
                type_name_lower = type_name.lower()
                if "wall panel" in type_name_lower or "wallpanel" in type_name_lower or "panel" in type_name_lower:
                    wall_panels.append(wall)
                    Log.debug("  -> MATCHED as wall panel")
            except Exception as ex:
                Log.warn("Wall skipped: {}".format(ex))
                continue
        
        Log.info("Collected: doors=%d, windows=%d, wall_panels=%d",
                 len(doors), len(windows), len(wall_panels))

    except Exception as e:
        Log.error("Step 1 failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Failed to collect elements. See console.", exitscript=True)
        return

    # -------------------------------------------------------------------
    # STEP 2 – BUILD ELEMENT CACHE
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 2: BUILDING ELEMENT CACHE")
        element_cache = build_element_cache(doc, view)
        Log.info("Cache built successfully")
    except Exception as e:
        Log.warn("Cache build failed (non-critical): %s", str(e))
        element_cache = {}

    # -------------------------------------------------------------------
    # STEP 3 – CLASSIFY PANELS (SIDES + FLOOR + GROUPS)
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 3: CLASSIFYING PANELS")
        side_summary, bounds, floor_split, panel_groups = classify_all_panels(wall_panels, view)
        Log.info("Bounds: xmin=%.2f xmax=%.2f ymin=%.2f ymax=%.2f", *bounds)
        Log.info("Floor split Z=%.2f", floor_split)
    except Exception as e:
        Log.error("Panel classification failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Panel classification failed. See console.", exitscript=True)
        return

    # -------------------------------------------------------------------
    # STEP 4 – ASSIGN WINDOWS TO SIDES
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 4: ASSIGNING WINDOWS")
        classify_windows(windows, view, bounds, side_summary)
        Log.info("Assigned %d windows", sum(len(side_summary[s]["windows"]) for s in SIDES))
    except Exception as e:
        Log.error("Window assignment failed: %s", str(e))
        traceback.print_exc()

    # -------------------------------------------------------------------
    # STEP 5 – PROCESS DOORS (RESPECTS GROUP_DOOR_COMPONENTS FLAG)
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 5: PROCESSING DOORS")
        
        if not GROUP_DOOR_COMPONENTS:
            # ═══════════════════════════════════════════════════════════
            # MODE A: NO GROUPING - Each door element stays separate
            # ═══════════════════════════════════════════════════════════
            door_groups, door_output = process_doors_simple(doors, view, floor_split)
            
        else:
            # ═══════════════════════════════════════════════════════════
            # MODE B: GROUPING - Split studs/headers and pair them
            # ═══════════════════════════════════════════════════════════
            studs, headers = split_studs_headers(doors, view)
            
            if len(studs) < 2:
                Log.warn("Not enough studs for door pairing. Falling back to simple processing.")
                door_groups, door_output = process_doors_simple(doors, view, floor_split)
            else:
                pairs = group_door_studs(studs)
                door_groups = build_door_groups(pairs)
                door_output = match_headers(pairs, headers)
        
        Log.info("Processed %d doors", len(door_output))
        
    except Exception as e:
        Log.error("Door processing failed: %s", str(e))
        traceback.print_exc()
        door_groups, door_output = [], []

    # -------------------------------------------------------------------
    # STEP 6 – ASSIGN DOORS TO SIDES
    # -------------------------------------------------------------------
    try:
        if door_groups:
            Log.section("STEP 6: ASSIGNING DOORS TO SIDES")
            door_side_map = classify_doors(door_groups, bounds, side_summary)
            Log.info("Assigned %d doors", len(door_side_map))
        else:
            Log.warn("No door groups to assign to sides")
            door_side_map = {}
    except Exception as e:
        Log.error("Door side assignment failed: %s", str(e))
        traceback.print_exc()
        door_side_map = {}

    # -------------------------------------------------------------------
    # STEP 7 – EXPORT BIM GEOMETRY
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 7: EXPORTING BIM GEOMETRY")
        bim_export = export_bim_geometry(doc, view, side_summary, door_output,
                                         door_side_map, floor_split, panel_groups)
        save_sequences(bim_export, side_summary)
        save_side_summary(side_summary)
        if door_output:
            save_door_output(door_output)
    except Exception as e:
        Log.error("BIM export failed: %s", str(e))
        traceback.print_exc()
        forms.alert("BIM export failed. See console.", exitscript=True)
        return

    # -------------------------------------------------------------------
    # STEP 8 – LOAD YOLO DETECTIONS
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 8: LOADING YOLO DETECTIONS")
        yolo = load_yolo()
        Log.info("Loaded %d YOLO detections", len(yolo))
    except Exception as e:
        Log.error("YOLO load failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Cannot load YOLO detections. Check path.", exitscript=True)
        return

    # -------------------------------------------------------------------
    # STEP 9 – CLASSIFY SIDE
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 9: CLASSIFYING FACADE SIDE")
        classified_side, score = classify_yolo_side(yolo, bim_export)
        Log.info("CLASSIFIED SIDE: %s | SCORE: %.3f", classified_side, score)
    except Exception as e:
        Log.error("Side classification failed: %s", str(e))
        traceback.print_exc()
        classified_side, score = "A", 0.0

    # -------------------------------------------------------------------
    # STEP 10 – MATCH YOLO TO BIM
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 10: MATCHING YOLO TO BIM")
        matches = match_yolo_to_bim(yolo, bim_export, classified_side)
        Log.info("Matched %d YOLO elements", sum(1 for m in matches if m.get("bim_id")))
        save_yolo_matches(matches, classified_side, score)
    except Exception as e:
        Log.error("YOLO-BIM matching failed: %s", str(e))
        traceback.print_exc()
        matches = []

    # -------------------------------------------------------------------
    # STEP 11 – HIGHLIGHT ELEMENTS
    # -------------------------------------------------------------------
    try:
        Log.section("STEP 11: HIGHLIGHTING ELEMENTS")
        if view.IsTemplate:
            Log.warn("Cannot highlight in template view")
            forms.alert("Switch to a non-template 3D view.", exitscript=False)
        else:
            with revit.Transaction("Apply YOLO-BIM Highlighting"):
                try: highlight_panels_by_side(side_summary, doc, view, highlight_only=classified_side)
                except Exception as e: Log.warn("Panel side highlight failed: %s", str(e))
                try: highlight_panels_by_floor(side_summary, doc, view, highlight_only=classified_side)
                except Exception as e: Log.warn("Panel floor highlight failed: %s", str(e))
                try:
                    if door_output: highlight_doors(door_output, doc, view)
                except Exception as e: Log.warn("Door highlight failed: %s", str(e))
            Log.info("Highlighting complete")
    except Exception as e:
        Log.error("Highlighting failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Highlighting failed (non-critical). Data still saved.", exitscript=False)

    # -------------------------------------------------------------------
    # FINAL SUMMARY
    # -------------------------------------------------------------------
    Log.section("PIPELINE COMPLETE")
    Log.info("Panels=%d, Doors=%d, Windows=%d, YOLO=%d, Matches=%d",
             len(wall_panels), len(door_output), len(windows), len(yolo), sum(1 for m in matches if m.get("bim_id")))
    forms.alert("Pipeline completed successfully!", exitscript=False)

# =======================================================================
# RUN SCRIPT
# =======================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("UNHANDLED EXCEPTION")
        traceback.print_exc()
        forms.alert("Script crashed. Check console for details.", exitscript=False)