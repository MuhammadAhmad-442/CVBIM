# -*- coding: utf-8 -*-
# ---------------------------------------------------------
# Convert BIM element center into normalized scale (0–1)
# ---------------------------------------------------------
def bim_to_normalized_x(xmin, xmax, side_width_mm):
    center = (xmin + xmax) / 2.0
    return center / float(side_width_mm)


# ---------------------------------------------------------
# Find the closest BIM element to the YOLO x-position
# ---------------------------------------------------------
def match_yolo_to_bim(yolo_x_norm, bim_elements, side_width_mm):
    """
    Find closest BIM element to the YOLO normalized X position.
    Returns: (best BIM id, distance)
    """
    best_id = None
    best_dist = 999

    for elem in bim_elements:
        elem_norm = bim_to_normalized_x(elem["xmin"], elem["xmax"], side_width_mm)
        dist = abs(elem_norm - yolo_x_norm)

        if dist < best_dist:
            best_dist = dist
            best_id = elem["id"]

    return best_id, best_dist


# ---------------------------------------------------------
# Match every YOLO detection to the correct BIM element
# ---------------------------------------------------------
# ---------------------------------------------------------
# Match every YOLO detection to the correct BIM element
# ---------------------------------------------------------
def match_all_yolo_to_bim(yolo_detections, bim_data, classified_side):
    """
    yolo_detections: list of YOLO dicts
    bim_data: full BIM export dict from pyRevit
    classified_side: "A", "B", "C", "D", or "INTERIOR"

    Returns:
        list of match records
    """
    matches = []

    # If interior → skip matching
    if classified_side == "INTERIOR":
        for det in yolo_detections:
            matches.append({
                "yolo_id": det["id"],
                "label": det["label"],
                "bim_id": None,
                "note": "Interior image — no exterior matching"
            })
        return matches

    # Width of the classified side (in mm)
    side_width_mm = bim_data["side_widths"][classified_side]

    # Map YOLO labels to BIM export keys
    label_to_key = {
        "door": "door",
        "window": "windows",
        "wall-panels": "wall-panels",
    }

    # ---------------------------------------------------------
    # Process every YOLO detection
    # ---------------------------------------------------------
    for det in yolo_detections:
        label = det["label"]
        floor = det.get("floor", None)
        xnorm = det["center_xy_norm"][0]

        # Pick correct BIM list key
        bim_key = label_to_key.get(label, label)

        # BIM elements must match type, side, and floor
        candidates = [
            e for e in bim_data.get(bim_key, [])
            if e["side"] == classified_side and e["floor"] == floor
        ]

        if not candidates:
            matches.append({
                "yolo_id": det["id"],
                "label": label,
                "bim_id": None,
                "note": "No matching BIM elements for type/side/floor"
            })
            continue

        bim_id, dist = match_yolo_to_bim(xnorm, candidates, side_width_mm)

        matches.append({
            "yolo_id": det["id"],
            "label": label,
            "bim_id": bim_id,
            "distance": dist
        })

    return matches

