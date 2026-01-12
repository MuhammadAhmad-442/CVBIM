# -*- coding: utf-8 -*-
# sides.py
# Presence-based side classifier (no distance scoring)

def build_sequence(yolo_detections):
    """Debug helper: sequence of labels sorted by YOLO X."""
    return [d["label"] for d in sorted(
        yolo_detections,
        key=lambda x: x["center_xy_norm"][0]
    )]


# ------------------------------------------------------------
# Presence-based scoring (fixed weights)
# ------------------------------------------------------------
def classify_side(yolo_detections, bim_export):
    """
    Returns (best_side, best_score)

    NO DISTANCE SCORING.
    NO POSITION COMPARISON.

    Logic:
        For each YOLO detection:
            If the side contains that object type → add fixed weight

    Weights:
        door → 3
        windows → 2
        wall-panels → 1
    """

    # No detections → interior
    if not yolo_detections:
        return "INTERIOR", 0.0

    sides = sorted(bim_export.get("side_widths", {}).keys())

    # --------------------------
    # GROUP BIM BY SIDE & TYPE
    # --------------------------
    bim_by_side = {s: {"door": [], "windows": [], "wall-panels": []}
                   for s in sides}

    for e in bim_export.get("door", []):
        side = e["side"]
        bim_by_side[side]["door"].append(e)

    for e in bim_export.get("windows", []):
        side = e["side"]
        bim_by_side[side]["windows"].append(e)

    for e in bim_export.get("wall-panels", []):
        side = e["side"]
        bim_by_side[side]["wall-panels"].append(e)

    # --------------------------
    # FIXED WEIGHTS
    # --------------------------
    W = {
        "door": 3.0,
        "windows": 2.0,
        "wall-panels": 1.0
    }

    # --------------------------
    # INITIALIZE SCORES
    # --------------------------
    side_scores = {s: 0.0 for s in sides}

    # --------------------------
    # MAIN SCORING LOOP
    # --------------------------
    for det in yolo_detections:
        raw_label = det["label"]

        # Normalize YOLO label to BIM key
        if raw_label == "window":
            label = "windows"
        else:
            label = raw_label

        if label not in W:
            continue

        weight = W[label]

        # For each façade side:
        for s in sides:
            elems = bim_by_side[s][label]

            # PRESENCE CHECK:
            if len(elems) > 0:
                # If the side has this object type → add the weight
                side_scores[s] += weight
            else:
                # If side has none → add nothing
                side_scores[s] += 0.0

    # --------------------------
    # FIND BEST SIDE
    # --------------------------
    best_side = max(side_scores, key=lambda s: side_scores[s])
    best_score = side_scores[best_side]

    # --------------------------
    # DEBUG TABLE
    # --------------------------
    print("\n=== SIDE SCORING TABLE ===\n")

    header = "Object".ljust(18)
    for s in sides:
        header += s.rjust(10)
    print(header + "\n")

    for det in yolo_detections:
        raw_label = det["label"]
        if raw_label == "window":
            label = "windows"
        else:
            label = raw_label

        row = ("%s_%s" % (raw_label, det.get("id", "?"))).ljust(18)
        for s in sides:
            elems = bim_by_side[s][label]
            if label in W:
                sc = W[label] if len(elems) > 0 else 0.0
                row += ("%0.2f" % sc).rjust(10)
            else:
                row += "    ---".rjust(10)
        print(row)

    print("\n" + "-" * 60 + "\n")

    row = "TOTAL".ljust(18)
    for s in sides:
        row += ("%0.2f" % side_scores[s]).rjust(10)
    print(row + "\n")

    print("Best side → %s | Score → %.3f" % (best_side, best_score))
    print("============================================\n")

    # Threshold
    if best_score < 0.5:
        return "INTERIOR", best_score

    return best_side, best_score
