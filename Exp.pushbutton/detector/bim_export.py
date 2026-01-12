# -*- coding: utf-8 -*-
# detector/bim_export.py
# Patched version: panels + composite doors + windows, with side-local normalization and door floors.

import json
import os
from Autodesk.Revit.DB import ElementId

MM = 304.8  # Revit ft → mm


def _element_bounds_mm(elem, view):
    """Return (xmin, xmax, zmid) in mm or (None, None, None) if no bbox."""
    if elem is None:
        return (None, None, None)
    bb = elem.get_BoundingBox(view)
    if not bb:
        return (None, None, None)
    xmin = bb.Min.X * MM
    xmax = bb.Max.X * MM
    zmid = ((bb.Min.Z + bb.Max.Z) * 0.5) * MM
    return (xmin, xmax, zmid)


def export_bim_geometry(doc, view, side_summary, door_output, door_side_map, output_path):
    """
    Export BIM geometry for:
      - wall-panels (per side + floor)
      - doors (composite: left stud + right stud + header)
      - windows (simple)
      - side_widths (for each façade)
    Uses side-local normalization: center_norm in [0,1] per side.
    """

    print("\n[EXPORT] Building BIM export…")

    export = {
        "door": [],
        "windows": [],
        "wall-panels": [],
        "side_widths": {}
    }

    # ------------------------------------------------------
    # 1) Compute side_min_x and side_width_mm from panels
    # ------------------------------------------------------
    side_min_x = {}
    side_floor_split_z = {}  # For door floor classification

    for side, data in side_summary.items():
        xs = []
        # Use all panels for side extent
        for pid in data.get("panels", []):
            elem = doc.GetElement(ElementId(pid))
            if not elem:
                continue
            bb = elem.get_BoundingBox(view)
            if bb:
                xs.append(bb.Min.X * MM)
                xs.append(bb.Max.X * MM)

        if xs:
            smin = min(xs)
            smax = max(xs)
            side_min_x[side] = smin
            export["side_widths"][side] = smax - smin
        else:
            side_min_x[side] = 0.0
            export["side_widths"][side] = 0.0

    # ------------------------------------------------------
    # 2) Compute per-side floor split Z from panels
    #    (average zmid of floor1 vs floor2 panels)
    # ------------------------------------------------------
    for side, data in side_summary.items():
        z_floor1 = []
        z_floor2 = []

        for pid in data.get("panels_floor1", []):
            elem = doc.GetElement(ElementId(pid))
            if not elem:
                continue
            bb = elem.get_BoundingBox(view)
            if bb:
                zmid = ((bb.Min.Z + bb.Max.Z) * 0.5) * MM
                z_floor1.append(zmid)

        for pid in data.get("panels_floor2", []):
            elem = doc.GetElement(ElementId(pid))
            if not elem:
                continue
            bb = elem.get_BoundingBox(view)
            if bb:
                zmid = ((bb.Min.Z + bb.Max.Z) * 0.5) * MM
                z_floor2.append(zmid)

        if z_floor1 and z_floor2:
            avg1 = sum(z_floor1) / float(len(z_floor1))
            avg2 = sum(z_floor2) / float(len(z_floor2))
            side_floor_split_z[side] = 0.5 * (avg1 + avg2)
        else:
            side_floor_split_z[side] = None

    # Small helper for center_norm
    def _center_norm(xmin, xmax, side):
        center_mm = (xmin + xmax) * 0.5
        local_min = side_min_x.get(side, 0.0)
        width = export["side_widths"].get(side, 0.0)
        if width <= 0.0:
            return 0.0
        return (center_mm - local_min) / width

    # ------------------------------------------------------
    # 3) Export PANELS (with correct floors + center_norm)
    # ------------------------------------------------------
    for side, data in side_summary.items():
        for pid in data.get("panels", []):
            elem = doc.GetElement(ElementId(pid))
            if not elem:
                continue

            xmin, xmax, _ = _element_bounds_mm(elem, view)
            if xmin is None:
                continue

            # Floor from membership in panels_floor1 / panels_floor2
            if pid in data.get("panels_floor1", []):
                floor = 1
            elif pid in data.get("panels_floor2", []):
                floor = 2
            else:
                floor = 1  # fallback

            export["wall-panels"].append({
                "id": pid,
                "type": "wall-panels",
                "side": side,
                "floor": floor,
                "xmin": xmin,
                "xmax": xmax,
                "side_width_mm": export["side_widths"][side],
                "center_norm": _center_norm(xmin, xmax, side)
            })

    # ------------------------------------------------------
    # 4) Export DOORS as composite elements
    #    (stud_left + stud_right + header)
    # ------------------------------------------------------
    if door_output and door_side_map:
        for d in door_output:
            door_id = d["door"]
            side = door_side_map.get(door_id, None)
            if not side or side not in export["side_widths"]:
                # Skip doors not assigned to a valid side
                continue

            sid = d["stud_left"]
            rid = d["stud_right"]
            hid = d["header"]

            elems = [
                doc.GetElement(ElementId(sid)),
                doc.GetElement(ElementId(rid)),
                doc.GetElement(ElementId(hid))
            ]

            xs = []
            zms = []
            for e in elems:
                if not e:
                    continue
                bb = e.get_BoundingBox(view)
                if not bb:
                    continue
                xs.append(bb.Min.X * MM)
                xs.append(bb.Max.X * MM)
                zms.append(((bb.Min.Z + bb.Max.Z) * 0.5) * MM)

            if not xs:
                continue

            xmin = min(xs)
            xmax = max(xs)
            center_z = zms and (sum(zms) / float(len(zms))) or None

            # Classify door floor by comparing header/stud Z to panel split
            floor_split = side_floor_split_z.get(side, None)
            if floor_split is not None and center_z is not None:
                floor = 1 if center_z < floor_split else 2
            else:
                floor = 1

            export["door"].append({
                "id": door_id,  # logical door index
                "type": "door",
                "side": side,
                "floor": floor,
                "xmin": xmin,
                "xmax": xmax,
                "side_width_mm": export["side_widths"][side],
                "center_norm": _center_norm(xmin, xmax, side)
            })

    # ------------------------------------------------------
    # 5) Export WINDOWS
    # ------------------------------------------------------
    for side, data in side_summary.items():
        for wid in data.get("windows", []):
            elem = doc.GetElement(ElementId(wid))
            if not elem:
                continue

            xmin, xmax, _ = _element_bounds_mm(elem, view)
            if xmin is None:
                continue

            # For now, assume floor1. You can classify later like doors.
            floor = 1

            export["windows"].append({
                "id": wid,
                "type": "window",
                "side": side,
                "floor": floor,
                "xmin": xmin,
                "xmax": xmax,
                "side_width_mm": export["side_widths"][side],
                "center_norm": _center_norm(xmin, xmax, side)
            })

    # ------------------------------------------------------
    # 6) Save JSON
    # ------------------------------------------------------
    folder = os.path.dirname(output_path)
    if not os.path.exists(folder):
        os.makedirs(folder)

    with open(output_path, "w") as f:
        json.dump(export, f, indent=4)

    print("[EXPORT COMPLETE] Saved BIM matching data to:", output_path)
    return export
