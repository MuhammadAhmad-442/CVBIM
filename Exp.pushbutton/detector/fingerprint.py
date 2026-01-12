# detector/fingerprint.py
# -*- coding: utf-8 -*-
from .geometry import dims, mid_xy

def build_side_fingerprint(side_summary, door_groups, window_elems, panel_elems, view):
    """Build ordered façade fingerprints + side composition summaries."""

    # Lookup tables
    panel_lookup = {e.Id.IntegerValue: e for e in panel_elems}
    window_lookup = {e.Id.IntegerValue: e for e in window_elems}

    # Door groups lookup
    door_lookup = {d["id"]: d["center"] for d in door_groups}

    fingerprint = {
        "A": {"counts": {}, "ordered_sequence": []},
        "B": {"counts": {}, "ordered_sequence": []},
        "C": {"counts": {}, "ordered_sequence": []},
        "D": {"counts": {}, "ordered_sequence": []},
    }

    for side in ["A", "B", "C", "D"]:
        seq = []

        # ------------------------------
        # PANELS
        # ------------------------------
        panel_ids = side_summary[side].get("panels", [])
        for pid in panel_ids:
            e = panel_lookup.get(pid)
            if not e:
                continue
            d = dims(e, view)
            cx, cy = mid_xy(d)
            seq.append({"type": "panel", "id": pid, "cx": cx, "cy": cy})

        # ------------------------------
        # door
        # ------------------------------
        door_ids = side_summary[side].get("door", [])
        for did in door_ids:
            if did in door_lookup:
                cx, cy = door_lookup[did]
                seq.append({"type": "door", "id": did, "cx": cx, "cy": cy})

        # ------------------------------
        # WINDOWS
        # ------------------------------
        window_ids = side_summary[side].get("windows", [])
        for wid in window_ids:
            e = window_lookup.get(wid)
            if not e:
                continue
            d = dims(e, view)
            cx, cy = mid_xy(d)
            seq.append({"type": "window", "id": wid, "cx": cx, "cy": cy})

        # ------------------------------
        # SORT left-to-right
        # ------------------------------
        seq_sorted = sorted(seq, key=lambda x: x["cx"])
        fingerprint[side]["ordered_sequence"] = seq_sorted

        # ------------------------------
        # SUMMARY COUNTS
        # ------------------------------
        fingerprint[side]["counts"] = {
            "panels": len(panel_ids),
            "door": len(door_ids),
            "windows": len(window_ids)
        }

    return fingerprint
