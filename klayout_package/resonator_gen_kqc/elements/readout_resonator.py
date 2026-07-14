"""Frequency-driven readout resonator PCell for the KLayout GUI."""

from __future__ import annotations

from kqcircuits.elements.element import Element
from kqcircuits.elements.finger_capacitor_square import FingerCapacitorSquare
from kqcircuits.elements.meander import Meander
from kqcircuits.pya_resolver import pya
from kqcircuits.util.parameters import Param, pdt

from resonator_gen.calibration import Calibration
from resonator_gen.constants import DEFAULT_EPS_EFF


class ReadoutResonator(Element):
    """GUI-editable λ/4 (or λ/2) meander readout resonator with finger coupler.

    Regenerates in milliseconds because ``Meander`` solves length analytically.
    """

    frequency_ghz = Param(pdt.TypeDouble, "Frequency", 5.0, unit="GHz")
    mode = Param(
        pdt.TypeString,
        "Mode",
        "quarter",
        choices=[["quarter", "quarter"], ["half", "half"]],
    )
    bend_radius = Param(pdt.TypeDouble, "Bend radius", 100, unit="μm")
    pitch = Param(pdt.TypeDouble, "Pitch (requested)", 100, unit="μm")
    cpw_width = Param(pdt.TypeDouble, "CPW width", 10, unit="μm")
    cpw_gap = Param(pdt.TypeDouble, "CPW gap", 6, unit="μm")
    coupler_finger_length = Param(pdt.TypeDouble, "Coupler finger length", 20, unit="μm")
    coupler_finger_gap = Param(pdt.TypeDouble, "Coupler finger gap", 3, unit="μm")
    coupler_finger_number = Param(pdt.TypeInt, "Coupler finger number", 5)
    orientation = Param(pdt.TypeDouble, "Orientation", 90, unit="deg")
    meander_span = Param(pdt.TypeDouble, "Meander span", 1200, unit="μm")
    eps_eff = Param(pdt.TypeDouble, "Effective permittivity", DEFAULT_EPS_EFF)
    coupler_dL = Param(pdt.TypeDouble, "Coupler electrical dL", 0.0, unit="μm")
    n_bridges = Param(pdt.TypeInt, "Airbridges", 0)
    meanders = Param(pdt.TypeInt, "Number of meanders (≤0 auto)", -1)

    def build(self):
        cal = Calibration(eps_eff=self.eps_eff, coupler_dL_um=self.coupler_dL)
        target = cal.body_length_um(self.frequency_ghz * 1e9, mode=self.mode)

        # Coupler near the origin of this element.
        coupler = self.add_element(
            FingerCapacitorSquare,
            a=self.cpw_width,
            b=self.cpw_gap,
            r=self.bend_radius,
            finger_number=self.coupler_finger_number,
            finger_length=self.coupler_finger_length,
            finger_gap=self.coupler_finger_gap,
            finger_width=5.0,
        )
        self.insert_cell(coupler, pya.DTrans(0, False, 0, 0))

        lead = 50.0 + self.coupler_finger_length + self.cpw_width
        start = pya.DPoint(lead, 0)
        end = pya.DPoint(lead + self.meander_span, 0)
        meander = self.add_element(
            Meander,
            start_point=start,
            end_point=end,
            length=float(target),
            meanders=int(self.meanders),
            n_bridges=int(self.n_bridges),
            a=self.cpw_width,
            b=self.cpw_gap,
            r=self.bend_radius,
        )
        self.insert_cell(
            meander,
            pya.DCplxTrans(1, self.orientation, False, pya.DVector(0, 0)),
        )
