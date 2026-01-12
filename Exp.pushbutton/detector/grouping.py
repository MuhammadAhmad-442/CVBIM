# -*- coding: utf-8 -*-
from .geometry import dims


def split_studs_headers(door_elems, view):
    """Split 'door' elements into studs (vertical) and headers (short)."""
    studs = []
    headers = []

    for e in door_elems:
        d = dims(e, view)
        if not d:
            continue
        h = d[2]
        if h > 500.0:
            studs.append((e, d))
        else:
            headers.append((e, d))

    if len(studs) < 2:
        print("\n[WARN] Not enough studs (found:", len(studs), ")")
    if len(headers) < 1:
        print("\n[WARN] No headers found.")

    return studs, headers


def group_studs_into_rows_and_pairs(studs):
    """Assume 4 studs → 2 door, 2 floors. Returns rowA, rowB, pairs."""
    if len(studs) != 4:
        raise Exception("Expected exactly 4 studs; found %d" % len(studs))

    # sort by Z
    studs_sorted = sorted(studs, key=lambda sd: (sd[1][7] + sd[1][8]) / 2.0)
    # bottom two, top two
    rowA = studs_sorted[0:2]
    rowB = studs_sorted[2:4]

    # sort each row by X for left-right
    rowA = sorted(rowA, key=lambda sd: (sd[1][3] + sd[1][4]) / 2.0)
    rowB = sorted(rowB, key=lambda sd: (sd[1][3] + sd[1][4]) / 2.0)

    pairs = [
        (rowA[0], rowA[1]),
        (rowB[0], rowB[1])
    ]

    print("\n[DEBUG] DOOR STUD PAIRS:")
    idx = 1
    for (eL, dL), (eR, dR) in pairs:
        print(" Door", idx, "studs:", eL.Id.IntegerValue, eR.Id.IntegerValue)
        idx += 1

    return rowA, rowB, pairs


def build_door_groups(pairs, view):
    """Build basic door group info for side classification."""
    door_groups = []
    door_index = 1

    for (eL, dL), (eR, dR) in pairs:
        # center X/Y from dims
        _, _, _, xminL, xmaxL, yminL, ymaxL, _, _ = dL
        _, _, _, xminR, xmaxR, yminR, ymaxR, _, _ = dR

        cx = ( (xminL + xmaxL) / 2.0 + (xminR + xmaxR) / 2.0 ) / 2.0
        cy = ( (yminL + ymaxL) / 2.0 + (yminR + ymaxR) / 2.0 ) / 2.0

        door_groups.append({
            "id": door_index,
            "stud_left": eL.Id.IntegerValue,
            "stud_right": eR.Id.IntegerValue,
            "center": (cx, cy),
            "dims_left": dL,
            "dims_right": dR
        })
        door_index += 1

    return door_groups


def match_headers_for_door(pairs, headers, view):
    """Assign one header to each door pair by closest Z to stud tops."""
    unused = headers[:]
    door_output = []
    door_index = 1

    for (eL, dL), (eR, dR) in pairs:
        if not unused:
            print("\n[WARN] No headers left to assign at door", door_index)
            break

        # stud top Z
        zmaxL = dL[8]
        zmaxR = dR[8]
        stud_top_z = min(zmaxL, zmaxR)

        best = None
        best_diff = 999999.0

        for eH, dH in unused:
            zminH = dH[7]
            zmaxH = dH[8]
            header_z = (zminH + zmaxH) / 2.0
            diff = abs(header_z - stud_top_z)
            if diff < best_diff:
                best_diff = diff
                best = (eH, dH)

        if not best:
            print("\n[WARN] Could not find matching header for door", door_index)
            door_index += 1
            continue

        eH, dH = best
        unused.remove(best)

        # width & height
        _, _, _, xminL, xmaxL, _, _, zminL, _ = dL
        _, _, _, xminR, xmaxR, _, _, zminR, _ = dR
        left_x = (xminL + xmaxL) / 2.0
        right_x = (xminR + xmaxR) / 2.0
        width = abs(right_x - left_x)
        height = abs(dH[7] - min(zminL, zminR))

        door_output.append({
            "door": door_index,
            "stud_left": eL.Id.IntegerValue,
            "stud_right": eR.Id.IntegerValue,
            "header": eH.Id.IntegerValue,
            "width_mm": width,
            "height_mm": height,
            "dims_left": dL,
            "dims_right": dR,
            "dims_header": dH
        })

        print("\n=== DOOR", door_index, "===")
        print(" Studs:", eL.Id.IntegerValue, eR.Id.IntegerValue)
        print(" Header:", eH.Id.IntegerValue)
        print(" Width:", width)
        print(" Height:", height)

        door_index += 1

    return door_output
