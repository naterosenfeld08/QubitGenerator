"""Minimal KQCircuits->Elmer capacitance run to verify the toolchain end-to-end.

Two coplanar metal pads on a silicon substrate; expect a 2x2 capacitance matrix.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from kqcircuits.pya_resolver import pya
from kqcircuits.simulations.simulation import Simulation
from kqcircuits.simulations.port import InternalPort
from kqcircuits.simulations.export.elmer.elmer_export import export_elmer
from kqcircuits.simulations.export.elmer.elmer_solution import ElmerCapacitanceSolution


class TwoPads(Simulation):
    def build(self):
        dbu = self.layout.dbu
        box_region = pya.Region(self.box.to_itype(dbu))
        pad1 = pya.Region(pya.DBox(-100, -50, -20, 50).to_itype(dbu))
        pad2 = pya.Region(pya.DBox(20, -50, 100, 50).to_itype(dbu))
        gap = box_region - pad1 - pad2
        self.cell.shapes(self.get_layer("base_metal_gap_wo_grid")).insert(gap)
        self.ports.append(InternalPort(1, signal_location=pya.DPoint(-60, 0)))
        self.ports.append(InternalPort(2, signal_location=pya.DPoint(60, 0)))


def main() -> int:
    out = Path("/tmp/kqc_test")
    out.mkdir(parents=True, exist_ok=True)
    layout = pya.Layout()
    box = pya.DBox(-250, -200, 250, 200)
    sim = TwoPads(layout, box=box, name="two_pads")

    sol = ElmerCapacitanceSolution(p_element_order=2, maximum_passes=1, percent_error=0.02)
    workflow = {
        "run_gmsh": True,
        "run_gmsh_gui": False,
        "run_elmergrid": True,
        "run_elmer": True,
        "run_paraview": False,
        "gmsh_n_threads": 2,
        "elmer_n_processes": 1,
        "elmer_n_threads": 1,
        "python_executable": sys.executable,
    }
    script = export_elmer([(sim, sol)], out, file_prefix="batch", workflow=workflow)
    print("Exported script:", script)

    # Execute the generated workflow (gmsh mesh + ElmerGrid + ElmerSolver).
    result = subprocess.run(
        ["bash", str(Path(script).name)],
        cwd=str(Path(script).parent),
        capture_output=True,
        text=True,
    )
    print("---- STDOUT (tail) ----")
    print("\n".join(result.stdout.splitlines()[-40:]))
    print("---- STDERR (tail) ----")
    print("\n".join(result.stderr.splitlines()[-40:]))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
