# -*- coding: utf-8 -*-
"""
YOLO-BIM pipeline with enhanced logging and filtering
"""
__title__ = "YOLO-BIM Matcher"
__author__ = "Script"

import sys, os, traceback
from pyrevit import revit, forms
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, Wall, WallType, BuiltInCategory
DB = revit.DB

def main():
    """Main YOLO-BIM pipeline with enhanced logging."""
    
    doc = revit.doc
    view = doc.ActiveView

    if not view:
        forms.alert("No active view. Open a 3D view first.", exitscript=True)
        return

    # Import modules
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
    except Exception as e:
        print("FATAL ERROR: Cannot load modules")
        print(str(e))
        traceback.print_exc()
        forms.alert("Module import failed. Check console.", exitscript=True)
        return

    # Initialize logging
    Log.reset_stats()
    Log.start_timer()
    
    # Print configuration
    Log.config_summary()

    # ----------------------------------------------------------------
    # STEP 1: COLLECT BIM ELEMENTS
    # ----------------------------------------------------------------
    Log.section("STEP 1: COLLECTING BIM ELEMENTS")
    
    doors, windows, wall_panels = [], [], []

    try:
        # Collect doors
        doors = list(FilteredElementCollector(doc, view.Id)
                     .OfClass(FamilyInstance)
                     .OfCategory(BuiltInCategory.OST_Doors)
                     .ToElements())
        
        # Collect windows
        windows = list(FilteredElementCollector(doc, view.Id)
                       .OfClass(FamilyInstance)
                       .OfCategory(BuiltInCategory.OST_Windows)
                       .ToElements())
        
        # Collect wall panels
        walls = FilteredElementCollector(doc, view.Id).OfClass(Wall).ToElements()
        
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
                
                type_name_lower = type_name.lower()
                if "wall panel" in type_name_lower or "wallpanel" in type_name_lower or "panel" in type_name_lower:
                    wall_panels.append(wall)
            except Exception as ex:
                Log.debug("Wall skipped: %s", str(ex))
                continue
        
        Log.subsection("Collection Results")
        Log.info("Doors:        %d", len(doors))
        Log.info("Windows:      %d", len(windows))
        Log.info("Wall panels:  %d", len(wall_panels))
        Log.step_timer("Collection")

    except Exception as e:
        Log.error("Element collection failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Failed to collect elements. See console.", exitscript=True)
        return

    # ----------------------------------------------------------------
    # STEP 2: BUILD ELEMENT CACHE
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 2: BUILDING ELEMENT CACHE")
        element_cache = build_element_cache(doc, view)
        Log.success("Cache built with %d elements", len(element_cache))
        Log.step_timer("Cache Building")
    except Exception as e:
        Log.warn("Cache build failed (non-critical): %s", str(e))
        element_cache = {}

    # ----------------------------------------------------------------
    # STEP 3: CLASSIFY PANELS
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 3: CLASSIFYING PANELS")
        side_summary, bounds, floor_split, panel_groups = classify_all_panels(wall_panels, view)
        
        Log.subsection("Bounds")
        Log.info("X-range: %.2f to %.2f mm", bounds[0], bounds[1])
        Log.info("Y-range: %.2f to %.2f mm", bounds[2], bounds[3])
        Log.info("Floor split: %.2f mm", floor_split)
        
        Log.subsection("Panel Distribution")
        Log.table_header(["Side", "Total", "Floor 1", "Floor 2"])
        for s in SIDES:
            Log.table_row([
                s,
                len(side_summary[s]["wall_panels"]),
                len(side_summary[s]["floor1"]),
                len(side_summary[s]["floor2"])
            ])
        
        Log.step_timer("Panel Classification")
    except Exception as e:
        Log.error("Panel classification failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Panel classification failed. See console.", exitscript=True)
        return

    # ----------------------------------------------------------------
    # STEP 4: ASSIGN WINDOWS
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 4: ASSIGNING WINDOWS TO SIDES")
        classify_windows(windows, view, bounds, side_summary)
        
        total_windows = sum(len(side_summary[s]["windows"]) for s in SIDES)
        Log.success("Assigned %d windows", total_windows)
        
        if Log.SHOW_STATS:
            Log.subsection("Window Distribution")
            for s in SIDES:
                count = len(side_summary[s]["windows"])
                if count > 0:
                    Log.info("Side %s: %d windows", s, count)
        
        Log.step_timer("Window Assignment")
    except Exception as e:
        Log.error("Window assignment failed: %s", str(e))
        traceback.print_exc()

    # ----------------------------------------------------------------
    # STEP 5: PROCESS DOORS
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 5: PROCESSING DOORS")
        
        if not GROUP_DOOR_COMPONENTS:
            door_groups, door_output = process_doors_simple(doors, view, floor_split)
        else:
            studs, headers = split_studs_headers(doors, view)
            
            if len(studs) < 2:
                Log.warn("Not enough studs for door pairing. Falling back to simple processing.")
                door_groups, door_output = process_doors_simple(doors, view, floor_split)
            else:
                pairs = group_door_studs(studs)
                door_groups = build_door_groups(pairs)
                door_output = match_headers(pairs, headers)
        
        Log.success("Processed %d doors", len(door_output))
        Log.step_timer("Door Processing")
        
    except Exception as e:
        Log.error("Door processing failed: %s", str(e))
        traceback.print_exc()
        door_groups, door_output = [], []

    # ----------------------------------------------------------------
    # STEP 6: ASSIGN DOORS TO SIDES
    # ----------------------------------------------------------------
    try:
        if door_groups:
            Log.section("STEP 6: ASSIGNING DOORS TO SIDES")
            door_side_map = classify_doors(door_groups, bounds, side_summary)
            
            Log.subsection("Door Distribution")
            for s in SIDES:
                count = len(side_summary[s]["door"])
                if count > 0:
                    Log.info("Side %s: %d doors", s, count)
            
            Log.step_timer("Door Assignment")
        else:
            Log.warn("No door groups to assign to sides")
            door_side_map = {}
    except Exception as e:
        Log.error("Door side assignment failed: %s", str(e))
        traceback.print_exc()
        door_side_map = {}

    # ----------------------------------------------------------------
    # STEP 7: EXPORT BIM GEOMETRY
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 7: EXPORTING BIM GEOMETRY")
        bim_export = export_bim_geometry(doc, view, side_summary, door_output,
                                         door_side_map, floor_split, panel_groups)
        save_sequences(bim_export, side_summary)
        save_side_summary(side_summary)
        if door_output:
            save_door_output(door_output)
        
        Log.success("BIM geometry exported successfully")
        Log.step_timer("BIM Export")
    except Exception as e:
        Log.error("BIM export failed: %s", str(e))
        traceback.print_exc()
        forms.alert("BIM export failed. See console.", exitscript=True)
        return

    # ----------------------------------------------------------------
    # STEP 8: LOAD YOLO DETECTIONS
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 8: LOADING YOLO DETECTIONS")
        yolo = load_yolo()
        Log.success("Loaded %d YOLO detections", len(yolo))
        Log.step_timer("YOLO Loading")
    except Exception as e:
        Log.error("YOLO load failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Cannot load YOLO detections. Check path.", exitscript=True)
        return

    # ----------------------------------------------------------------
    # STEP 9: CLASSIFY FACADE SIDE
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 9: CLASSIFYING FACADE SIDE")
        classified_side, score = classify_yolo_side(yolo, bim_export)
        Log.success("CLASSIFIED SIDE: %s (score: %.3f)", classified_side, score)
        Log.step_timer("Side Classification")
    except Exception as e:
        Log.error("Side classification failed: %s", str(e))
        traceback.print_exc()
        classified_side, score = "A", 0.0

    # ----------------------------------------------------------------
    # STEP 10: MATCH YOLO TO BIM
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 10: MATCHING YOLO TO BIM")
        matches = match_yolo_to_bim(yolo, bim_export, classified_side)
        
        matched_count = sum(1 for m in matches if m.get("bim_id"))
        Log.success("Matched %d/%d YOLO elements", matched_count, len(matches))
        
        save_yolo_matches(matches, classified_side, score)
        Log.step_timer("YOLO Matching")
    except Exception as e:
        Log.error("YOLO-BIM matching failed: %s", str(e))
        traceback.print_exc()
        matches = []

    # ----------------------------------------------------------------
    # STEP 11: HIGHLIGHT ELEMENTS
    # ----------------------------------------------------------------
    try:
        Log.section("STEP 11: HIGHLIGHTING ELEMENTS")
        if view.IsTemplate:
            Log.warn("Cannot highlight in template view")
            forms.alert("Switch to a non-template 3D view.", exitscript=False)
        else:
            with revit.Transaction("Apply YOLO-BIM Highlighting"):
                try:
                    highlight_panels_by_side(side_summary, doc, view, highlight_only=classified_side)
                    Log.success("Highlighted panels by side")
                except Exception as e:
                    Log.warn("Panel side highlight failed: %s", str(e))
                
                try:
                    highlight_panels_by_floor(side_summary, doc, view, highlight_only=classified_side)
                    Log.success("Highlighted panels by floor")
                except Exception as e:
                    Log.warn("Panel floor highlight failed: %s", str(e))
                
                try:
                    if door_output:
                        highlight_doors(door_output, doc, view)
                        Log.success("Highlighted doors")
                except Exception as e:
                    Log.warn("Door highlight failed: %s", str(e))
        
        Log.step_timer("Highlighting")
    except Exception as e:
        Log.error("Highlighting failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Highlighting failed (non-critical). Data still saved.", exitscript=False)

    # ----------------------------------------------------------------
    # FINAL SUMMARY
    # ----------------------------------------------------------------
    Log.final_summary()
    
    forms.alert("Pipeline completed successfully!", exitscript=False)

# ===================================================================
# RUN SCRIPT
# ===================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("UNHANDLED EXCEPTION")
        traceback.print_exc()
        forms.alert("Script crashed. Check console for details.", exitscript=False)