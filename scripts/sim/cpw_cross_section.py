"""Elmer 2-D cross-section of a coplanar waveguide (CPW).

Extracts per-unit-length capacitance ``Cs`` and inductance ``Ls``, then derives
characteristic impedance ``Z0 = sqrt(Ls/Cs)`` and phase velocity
``v_phi = 1/sqrt(Ls*Cs)``.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from kqcircuits.pya_resolver import pya
from kqcircuits.simulations.cross_section_simulation import CrossSectionSimulation
from kqcircuits.simulations.export.elmer.elmer_solution import ElmerCrossSectionSolution

from _elmer_run import default_workflow, load_results, run_batch


class CpwCrossSection(CrossSectionSimulation):
    """Single CPW mode cross-section (lateral x, depth y; metal at y=0)."""

    def __init__(self, layout, *, center_width_um: float, gap_um: float, name: str, **kwargs):
        self.center_width_um = center_width_um
        self.gap_um = gap_um
        super().__init__(layout, name=name, **kwargs)

    def build(self):
        dbu = self.layout.dbu
        w = self.center_width_um
        g = self.gap_um
        half_window = 250.0
        sub_depth = 500.0
        vac_height = 500.0
        metal_t = 0.2

        def box(x1, y1, x2, y2) -> pya.Region:
            return pya.Region(pya.DBox(x1, y1, x2, y2).to_itype(dbu))

        self.insert_layer("silicon", box(-half_window, -sub_depth, half_window, 0.0), "silicon")
        self.insert_layer("vacuum", box(-half_window, 0.0, half_window, vac_height), "vacuum")

        hw = w / 2.0
        ground = box(-half_window, 0.0, -hw - g, metal_t) + box(hw + g, 0.0, half_window, metal_t)
        signal = box(-hw, 0.0, hw, metal_t)
        self.insert_layer("metal_ground", ground, "pec", excitation=0)
        self.insert_layer("metal_signal", signal, "pec", excitation=1)


def run_case(center_width_um: float, gap_um: float, out_dir: Path) -> dict:
    layout = pya.Layout()
    name = f"cpw_{int(center_width_um)}_{int(gap_um)}"
    sim = CpwCrossSection(layout, center_width_um=center_width_um, gap_um=gap_um, name=name)
    sol = ElmerCrossSectionSolution(
        p_element_order=3,
        maximum_passes=1,
        minimum_passes=1,
        mesh_size={"global_max": 80.0, "metal_*": 5.0, "silicon": 30.0},
    )
    run_batch([(sim, sol)], out_dir, prefix="cpw", workflow=default_workflow())
    res = load_results(out_dir, name)
    cs = res["Cs"][0][0]
    ls = res["Ls"][0][0]
    z0 = math.sqrt(ls / cs)
    v_phi = 1.0 / math.sqrt(ls * cs)
    eps_eff = (3e8 / v_phi) ** 2
    return {
        "name": name,
        "center_width_um": center_width_um,
        "gap_um": gap_um,
        "Cs_F_per_m": cs,
        "Ls_H_per_m": ls,
        "Z0_ohm": z0,
        "v_phi_m_s": v_phi,
        "eps_eff": eps_eff,
        "raw": res,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width-um", type=float, default=30.0)
    parser.add_argument("--gap-um", type=float, default=20.0)
    parser.add_argument("--out", type=Path, default=Path("/tmp/kqc_cpw"))
    args = parser.parse_args(argv)
    result = run_case(args.width_um, args.gap_um, args.out)
    print(f"CPW {result['center_width_um']}/{result['gap_um']} um:")
    print(f"  Z0 = {result['Z0_ohm']:.2f} ohm")
    print(f"  v_phi = {result['v_phi_m_s']:.3e} m/s")
    print(f"  eps_eff = {result['eps_eff']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
