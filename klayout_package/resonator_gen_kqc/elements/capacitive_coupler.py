"""Standalone capacitive finger coupler PCell."""

from __future__ import annotations

from kqcircuits.elements.element import Element
from kqcircuits.elements.finger_capacitor_square import FingerCapacitorSquare
from kqcircuits.util.parameters import Param, pdt


class CapacitiveCouplerElement(Element):
    """Thin GUI wrapper around ``FingerCapacitorSquare``."""

    coupler_finger_length = Param(pdt.TypeDouble, "Finger length", 20, unit="μm")
    coupler_finger_gap = Param(pdt.TypeDouble, "Finger gap", 3, unit="μm")
    coupler_finger_number = Param(pdt.TypeInt, "Finger number", 5)
    coupler_finger_width = Param(pdt.TypeDouble, "Finger width", 5, unit="μm")

    def build(self):
        cell = self.add_element(
            FingerCapacitorSquare,
            finger_number=self.coupler_finger_number,
            finger_length=self.coupler_finger_length,
            finger_gap=self.coupler_finger_gap,
            finger_width=self.coupler_finger_width,
            a=self.a,
            b=self.b,
            r=self.r,
        )
        self.insert_cell(cell)
