# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance

def _safe_name(elem):
    try:
        fam = elem.Symbol.Family.Name.lower()
    except:
        fam = ""
    try:
        typ = elem.Symbol.Name.lower()
    except:
        typ = ""
    try:
        name = elem.Name.lower()
    except:
        name = ""
    return fam, typ, name


def collect_bim_openings(doc, view):
    door = []
    windows = []
    panels = []

    insts = FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance)

    for e in insts:
        fam, typ, name = _safe_name(e)
        combo = fam + " " + typ + " " + name

        # --- Door opening parts ---
        if " door" in combo:
            door.append(e)

        # --- Window opening parts ---
        if "window" in combo:
            windows.append(e)

        # --- Wall panel (= all other wall-frame items) ---
        if "wall panel" in combo or "panel" in combo:
            panels.append(e)

    print("\n[INFO] Collected: door =", len(door),
          "| windows =", len(windows),
          "| panels =", len(panels))

    return {
        "door": door,
        "windows": windows,
        "panels": panels,
    }
