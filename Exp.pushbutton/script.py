# -*- coding: utf-8 -*-
"""
FILE: script.py
PURPOSE: YOLO-BIM detection pipeline with crash protection
"""
__title__ = "YOLO-BIM Matcher"
__author__ = "Script"
__doc__ = "Match YOLO detections to BIM elements"

import sys
import os

# Add script directory to path
script_dir = os.path.dirname(__file__)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from pyrevit import revit, forms
import traceback

# ===========================================================================
# CRASH-SAFE MAIN FUNCTION
# ===========================================================================

def main():
    """Main pipeline with error handling."""
    
    try:
        # Import modules
        from detector.config import Log, SIDES
        from detector.core import collect_elements, build_element_cache, dims, center_xy, get_element_id
        from detector.classification import (
            classify_all_panels,
            split_studs_headers,
            group_door_studs,
            build_door_groups,
            match_headers,
            classify_yolo_side
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
        print("\n" + "=" * 70)
        print("FATAL ERROR: Cannot load modules")
        print("=" * 70)
        print(str(e))
        traceback.print_exc()
        forms.alert("Module import failed. Check console.", exitscript=True)
        return
    
    # Get document and view
    doc = revit.doc
    view = doc.ActiveView
    
    if not view:
        forms.alert("No active view. Please open a 3D view.", exitscript=True)
        return
    
    Log.section("YOLO-BIM PIPELINE START")
    
    # -----------------------------------------------------------------------
    # STEP 1: COLLECT ELEMENTS
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 1: COLLECTING BIM ELEMENTS")
        bim = collect_elements(doc, view)
        door_elems = bim["door"]
        window_elems = bim["windows"]
        panel_elems = bim["panels"]
        
        if not panel_elems:
            forms.alert("No wall panels found. Cannot proceed.", exitscript=True)
            return
        
        Log.info("Collection complete")
        
    except Exception as e:
        Log.error("Step 1 failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Failed to collect elements. See console.", exitscript=True)
        return
    
    # -----------------------------------------------------------------------
    # STEP 2: BUILD CACHES (OPTIONAL - SKIP IF CAUSING CRASH)
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 2: BUILDING ELEMENT CACHES")
        element_cache = build_element_cache(doc, view)
        Log.info("Cache built successfully")
    except Exception as e:
        Log.warn("Caching failed (non-critical): %s", str(e))
        element_cache = {}
    
    # -----------------------------------------------------------------------
    # STEP 3: CLASSIFY PANELS
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 3: CLASSIFYING PANELS")
        side_summary, bounds, floor_split = classify_all_panels(panel_elems, view)
        Log.info("Building bounds: xmin=%.2f, xmax=%.2f, ymin=%.2f, ymax=%.2f", *bounds)
        Log.info("Floor split Z: %.2f mm", floor_split)
        
    except Exception as e:
        Log.error("Step 3 failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Panel classification failed. See console.", exitscript=True)
        return
    
    # -----------------------------------------------------------------------
    # STEP 4: ASSIGN WINDOWS
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 4: ASSIGNING WINDOWS")
        
        for e in window_elems:
            d = dims(e, view)
            if not d:
                continue
            
            cx, cy = center_xy(d)
            xmin_b, xmax_b, ymin_b, ymax_b = bounds
            
            distances = {
                "A": abs(cx - xmin_b),
                "C": abs(cx - xmax_b),
                "B": abs(cy - ymin_b),
                "D": abs(cy - ymax_b)
            }
            side = min(distances, key=distances.get)
            
            side_summary[side]["windows"].append(get_element_id(e))
        
        window_count = sum(len(side_summary[s]["windows"]) for s in SIDES)
        Log.info("Assigned %d windows", window_count)
        
    except Exception as e:
        Log.error("Step 4 failed: %s", str(e))
        traceback.print_exc()
        window_count = 0
    
    # -----------------------------------------------------------------------
    # STEP 5: PROCESS DOORS
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 5: PROCESSING DOORS")
        
        studs, headers = split_studs_headers(door_elems, view)
        
        if len(studs) < 2:
            Log.warn("Not enough studs - skipping doors")
            door_groups = []
            door_output = []
            door_side_map = {}
        else:
            pairs = group_door_studs(studs)
            door_groups = build_door_groups(pairs)
            door_output = match_headers(pairs, headers)
            Log.info("Matched %d doors", len(door_output))
            
    except Exception as e:
        Log.error("Step 5 failed: %s", str(e))
        traceback.print_exc()
        door_groups = []
        door_output = []
        door_side_map = {}
    
    # -----------------------------------------------------------------------
    # STEP 6: ASSIGN DOORS TO SIDES
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 6: ASSIGNING DOORS TO SIDES")
        
        if door_groups:
            door_side_map = {}
            
            for d in door_groups:
                did = d["id"]
                cx, cy = d["center"]
                xmin_b, xmax_b, ymin_b, ymax_b = bounds
                
                distances = {
                    "A": abs(cx - xmin_b),
                    "C": abs(cx - xmax_b),
                    "B": abs(cy - ymin_b),
                    "D": abs(cy - ymax_b)
                }
                side = min(distances, key=distances.get)
                
                door_side_map[did] = side
                side_summary[side]["door"].append(did)
            
            Log.info("Assigned %d doors", len(door_side_map))
        else:
            door_side_map = {}
        
        # Save results
        save_side_summary(side_summary)
        if door_output:
            save_door_output(door_output)
            
    except Exception as e:
        Log.error("Step 6 failed: %s", str(e))
        traceback.print_exc()
        door_side_map = {}
    
    # -----------------------------------------------------------------------
    # STEP 7: EXPORT BIM
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 7: EXPORTING BIM GEOMETRY")
        bim_export = export_bim_geometry(
            doc, view, side_summary, door_output, door_side_map, floor_split
        )
        save_sequences(bim_export, side_summary)
        
    except Exception as e:
        Log.error("Step 7 failed: %s", str(e))
        traceback.print_exc()
        forms.alert("BIM export failed. See console.", exitscript=True)
        return
    
    # -----------------------------------------------------------------------
    # STEP 8: LOAD YOLO
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 8: LOADING YOLO DETECTIONS")
        yolo = load_yolo()
        Log.info("Loaded %d YOLO detections", len(yolo))
        
    except Exception as e:
        Log.error("Step 8 failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Cannot load YOLO detections. Check path.", exitscript=True)
        return
    
    # -----------------------------------------------------------------------
    # STEP 9: CLASSIFY SIDE
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 9: CLASSIFYING FACADE SIDE")
        classified_side, score = classify_yolo_side(yolo, bim_export)
        
        Log.info("=" * 70)
        Log.info("CLASSIFIED SIDE: %s", classified_side)
        Log.info("CONFIDENCE SCORE: %.3f", score)
        Log.info("=" * 70)
        
    except Exception as e:
        Log.error("Step 9 failed: %s", str(e))
        traceback.print_exc()
        classified_side = "A"
        score = 0.0
    
    # -----------------------------------------------------------------------
    # STEP 10: MATCH YOLO TO BIM
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 10: MATCHING YOLO TO BIM")
        matches = match_yolo_to_bim(yolo, bim_export, classified_side)
        
        Log.info("Match Results:")
        for m in matches:
            if m.get("bim_id"):
                Log.info("  YOLO %s (%s) -> BIM %s (dist=%.4f)",
                        m["yolo_id"], m["label"], m["bim_id"], m.get("distance", 0))
            else:
                Log.info("  YOLO %s (%s) -> NO MATCH (%s)",
                        m["yolo_id"], m["label"], m.get("note", ""))
        
        save_yolo_matches(matches, classified_side, score)
        
    except Exception as e:
        Log.error("Step 10 failed: %s", str(e))
        traceback.print_exc()
        matches = []
    
    # -----------------------------------------------------------------------
    # STEP 11: HIGHLIGHT (MOST LIKELY TO CRASH - EXTRA PROTECTION)
    # -----------------------------------------------------------------------
    try:
        Log.section("STEP 11: HIGHLIGHTING ELEMENTS")
        
        # Check if we can modify the view
        if view.IsTemplate:
            Log.warn("Cannot highlight in template view")
            forms.alert("Please switch to a non-template 3D view.", exitscript=False)
        else:
            with revit.Transaction("Apply YOLO-BIM Highlighting"):
                try:
                    highlight_panels_by_side(side_summary, doc, view, highlight_only=classified_side)
                except Exception as e:
                    Log.warn("Panel side highlighting failed: %s", str(e))
                
                try:
                    highlight_panels_by_floor(side_summary, doc, view, highlight_only=classified_side)
                except Exception as e:
                    Log.warn("Panel floor highlighting failed: %s", str(e))
                
                try:
                    if door_output:
                        highlight_doors(door_output, doc, view)
                except Exception as e:
                    Log.warn("Door highlighting failed: %s", str(e))
            
            Log.info("Highlighting complete")
            
    except Exception as e:
        Log.error("Step 11 failed: %s", str(e))
        traceback.print_exc()
        forms.alert("Highlighting failed (non-critical). Data still saved.", exitscript=False)
    
    # -----------------------------------------------------------------------
    # FINAL SUMMARY
    # -----------------------------------------------------------------------
    Log.section("PIPELINE COMPLETE")
    
    print("\n" + "=" * 70)
    print("FINAL SUMMARY".center(70))
    print("=" * 70)
    print("  Panels:          {}".format(sum(len(side_summary[s]["panels"]) for s in SIDES)))
    print("  Windows:         {}".format(window_count))
    print("  Doors:           {}".format(len(door_output)))
    print("  Classified Side: {}".format(classified_side))
    print("  Side Score:      {:.3f}".format(score))
    print("  YOLO Detections: {}".format(len(yolo)))
    print("  Matched:         {}/{}".format(
        sum(1 for m in matches if m.get("bim_id")),
        len(matches)
    ))
    print("=" * 70)
    
    Log.info("All operations completed successfully")

# ===========================================================================
# RUN WITH CRASH PROTECTION
# ===========================================================================

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("\n" + "=" * 70)
        print("UNHANDLED EXCEPTION")
        print("=" * 70)
        print(str(e))
        traceback.print_exc()
        print("=" * 70)
        forms.alert("Script crashed. Check console for details.", exitscript=False)