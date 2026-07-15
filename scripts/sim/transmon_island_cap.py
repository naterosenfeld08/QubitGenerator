"""Elmer electrostatic capacitance simulation of one Cooper-group transmon island.

The Cooper chip is negative tone: drawn polygons on 1/0 are etched gaps and the
undrawn region is superconducting metal (ground). A transmon island is the metal
patch isolated by a moat gap. Its self-capacitance to ground, C_Sigma, sets the
charging energy EC = e^2 / (2 C_Sigma).

Geometry reproduces build_cooper_qubits.build_transmon_left exactly (island 55 um,
neck 30x5 um, link 20x35 um, moat 20 um), placed in a grounded box on silicon.
Net 1 = island+neck+link (the qubit node). Everything else in the metal plane is
ground. The junction break is left open (electrostatic C sees the JJ as open).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from kqcircuits.pya_resolver import pya
from kqcircuits.simulations.simulation import Simulation
from kqcircuits.simulations.port import InternalPort
from kqcircuits.simulations.export.elmer.elmer_export import export_elmer
from kqcircuits.simulations.export.elmer.elmer_solution import ElmerCapacitanceSolution
from kqcircuits.simulations.export.elmer.mesh_size_helpers import refine_metal_edges

# Drawn transmon dimensions (um) -- identical to build_cooper_qubits.py.
ISLAND = 55.0
NECK_L = 30.0
NECK_W = 5.0
LINK_L = 20.0
LINK_W = 35.0
MOAT = 20.0
JJ_BREAK = 5.0


def _dbox(x1, y1, x2, y2):
    return pya.DBox(x1, y1, x2, y2)


class TransmonIsland(Simulation):
    def build(self):
        dbu = self.layout.dbu

        # Island centered on the origin; +x toward the resonator claw/link.
        isl_x1, isl_x2 = -ISLAND, 0.0
        isl_y1, isl_y2 = -ISLAND / 2.0, ISLAND / 2.0
        island = _dbox(isl_x1, isl_y1, isl_x2, isl_y2)
        # Link toward the claw (truncated, enclosed by the moat with clearance).
        link = _dbox(isl_x2, -LINK_W / 2.0, isl_x2 + LINK_L, LINK_W / 2.0)
        # Neck toward the JJ/ground.
        neck = _dbox(isl_x1 - NECK_L, -NECK_W / 2.0, isl_x1, NECK_W / 2.0)

        keep = pya.Region([p.to_itype(dbu) for p in (island, link, neck)])

        moat = pya.Region(
            _dbox(isl_x1 - NECK_L - JJ_BREAK, isl_y1 - MOAT, isl_x2 + LINK_L + JJ_BREAK, isl_y2 + MOAT).to_itype(dbu)
        )
        gap = moat - keep

        self.cell.shapes(self.get_layer("base_metal_gap_wo_grid")).insert(gap)
        # Signal net on the island; capacitance is to the surrounding ground plane.
        self.ports.append(InternalPort(1, signal_location=pya.DPoint(isl_x1 + ISLAND / 2.0, 0.0)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/kqc_island"))
    args = parser.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    layout = pya.Layout()
    # Grounded box generously larger than the moat for a realistic ground reference.
    box = pya.DBox(-260, -220, 220, 220)
    sim = TransmonIsland(layout, box=box, name="transmon_island")

    # Single pass (MacPorts Elmer lacks MMG adaptive remeshing); refine the mesh
    # at metal edges instead, where the electric field concentrates.
    sol = ElmerCapacitanceSolution(
        p_element_order=3,
        maximum_passes=1,
        minimum_passes=1,
        mesh_size=refine_metal_edges(size=3.0, slope=0.3),
    )
    workflow = {
        "run_gmsh": True,
        "run_gmsh_gui": False,
        "run_elmergrid": True,
        "run_elmer": True,
        "run_paraview": False,
        "gmsh_n_threads": 4,
        "elmer_n_processes": 1,
        "elmer_n_threads": 2,
        "python_executable": sys.executable,
    }
    script = export_elmer([(sim, sol)], out, file_prefix="batch", workflow=workflow)
    print("Exported:", script)
    result = subprocess.run(["bash", Path(script).name], cwd=str(Path(script).parent),
                            capture_output=True, text=True)
    print("\n".join(result.stdout.splitlines()[-25:]))
    if result.returncode != 0:
        print("---- STDERR ----")
        print("\n".join(result.stderr.splitlines()[-25:]))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
