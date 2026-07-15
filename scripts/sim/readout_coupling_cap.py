"""Elmer capacitance between resonator and feedline center conductors (readout tap).

Models the coupling region as two isolated metal islands (negative tone: everything
except the islands is etched gap) to obtain a well-defined 2-port capacitance matrix.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kqcircuits.pya_resolver import pya
from kqcircuits.simulations.simulation import Simulation
from kqcircuits.simulations.port import InternalPort
from kqcircuits.simulations.export.elmer.elmer_solution import ElmerCapacitanceSolution
from kqcircuits.simulations.export.elmer.mesh_size_helpers import refine_metal_edges

from _elmer_run import default_workflow, load_results, run_batch

COUPLING_LENGTH_UM = 200.0
SEPARATION_UM = 132.0
FEED_W = 25.0
RES_W = 30.0


class ReadoutCoupling(Simulation):
    def build(self):
        dbu = self.layout.dbu
        L = COUPLING_LENGTH_UM
        sep = SEPARATION_UM

        def box(x1, y1, x2, y2) -> pya.Region:
            return pya.Region(pya.DBox(x1, y1, x2, y2).to_itype(dbu))

        # Two finite metal islands; everything else in the plane is etched away.
        feed_island = box(-L / 2, -FEED_W / 2, L / 2, FEED_W / 2)
        res_y_center = -FEED_W / 2 - sep - RES_W / 2
        res_island = box(-L / 2, res_y_center - RES_W / 2, L / 2, res_y_center + RES_W / 2)

        frame = box(-260, -320, 260, 120)
        gap = frame - feed_island - res_island
        self.cell.shapes(self.get_layer("base_metal_gap_wo_grid")).insert(gap)

        self.ports.append(InternalPort(1, signal_location=pya.DPoint(0.0, 0.0)))
        self.ports.append(InternalPort(2, signal_location=pya.DPoint(0.0, res_y_center)))


def main(argv: list[str] | None = None) -> int:
    out = Path("/tmp/kqc_readout")
    layout = pya.Layout()
    box = pya.DBox(-260, -320, 260, 120)
    sim = ReadoutCoupling(layout, box=box, name="readout_coupling")
    sol = ElmerCapacitanceSolution(
        p_element_order=3,
        maximum_passes=1,
        minimum_passes=1,
        mesh_size=refine_metal_edges(size=4.0, slope=0.3),
    )
    run_batch([(sim, sol)], out, workflow=default_workflow())
    res = load_results(out, "readout_coupling")
    cm = abs(res["Cdata"]["C_Net2_Net1"][0])
    c1 = abs(res["Cdata"]["C_Net1_Net1"][0])
    c2 = abs(res["Cdata"]["C_Net2_Net2"][0])
    print(f"readout coupling capacitance C_m = {cm*1e15:.3f} fF")
    print(f"  C_feed = {c1*1e15:.3f} fF, C_res = {c2*1e15:.3f} fF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
