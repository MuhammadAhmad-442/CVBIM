from .geometry import dims, mid_xy

def classify_all_sides(panels, windows, door_output):

    # compute building bounds from panels
    midpoints = []
    for e in panels:
        d = dims(e)
        if d:
            midpoints.append(mid_xy(d))

    xs = [p[0] for p in midpoints]
    ys = [p[1] for p in midpoints]

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    def classify(cx, cy):
        d = {
            "A": abs(cx-xmin),
            "C": abs(cx-xmax),
            "B": abs(cy-ymin),
            "D": abs(cy-ymax)
        }
        side = min(d, key=d.get)
        return side if d[side] < 200 else None

    summary = {s: {"doors": [], "windows": [], "panels": []} for s in "ABCD"}

    # doors
    for d in door_output:
        cx = (d["dims_left"][3] + d["dims_right"][4]) / 2
        cy = (d["dims_left"][5] + d["dims_right"][6]) / 2
        side = classify(cx, cy)
        if side:
            summary[side]["doors"].append(d["door"])

    # windows
    for e in windows:
        d = dims(e)
        if d:
            cx, cy = mid_xy(d)
            s = classify(cx,cy)
            if s: summary[s]["windows"].append(e.Id.IntegerValue)

    # panels
    for e in panels:
        d = dims(e)
        if d:
            cx, cy = mid_xy(d)
            s = classify(cx,cy)
            if s: summary[s]["panels"].append(e.Id.IntegerValue)

    return summary
