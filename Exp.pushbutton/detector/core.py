# -*- coding: utf-8 -*-
"""
CORE.PY - Core utilities with exterior/interior filtering
"""
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, ElementId
from config import REVIT_FT_TO_MM, SIDES, Log, FILTER_INTERIOR_ELEMENTS, EXTERIOR_DISTANCE_THRESHOLD_MM

SHELL
