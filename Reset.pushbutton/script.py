# -*- coding: utf-8 -*-
__title__ = "Reset Highlights"

from Autodesk.Revit.DB import *
from pyrevit import revit

doc = revit.doc

t = Transaction(doc, "Reset Overrides")
t.Start()

collector = FilteredElementCollector(doc)\
            .WhereElementIsNotElementType()

for elem in collector:
    doc.ActiveView.SetElementOverrides(elem.Id, OverrideGraphicSettings())

t.Commit()
