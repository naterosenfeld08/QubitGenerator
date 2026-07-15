#!/usr/bin/env python3
"""Run Elmer simulations for the Cooper chip and produce a readout-chain report.

Computes (from electrostatic Elmer + lumped circuit models):
  - Transmon charging energy EC and qubit frequency f_q (EJ placeholder)
  - CPW line parameters (Z0, eps_eff) for resonator and feedline
  - Resonator frequencies f_r (nominal length + claw-reroute correction)
  - Readout coupling capacitance C_m and external Q_c
  - Qubit–resonator coupling g and dispersive shift chi
  - Readout efficiency / SNR estimate for n=2 readout photons

Elmer batches are cached under ``out/sim/elmer/``; delete a subdirectory to
force re-meshing.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# Allow running as ``python scripts/sim/cooper_chip_report.py``.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.sim._elmer_run import load_results, run_batch, default_workflow

# Physical constants
H = 6.62607015e-34
E_CHARGE = 1.602176634e-19
C_LIGHT = 299792458.0

# Cooper chip design targets (from configs/test_chip_v1.yaml).
RESONATOR_TARGETS_GHZ = [4.0, 4.5, 5.0, 5.5]
EPS_EFF_NOMINAL = 6.35
CLAW_LENGTH_DELTA_UM = 180.0  # extra electrical length from claw reroute (estimate)

# Placeholder Josephson energy until JJ e-beam dimensions are final.
EJ_GHZ = 20.0

OUT_ROOT = _REPO / "out" / "sim"


@dataclass
class ReadoutReport:
    EC_MHz: float
    f_q_GHz: float
    EJ_GHz: float
    C_sigma_fF: float
    cpw_res_Z0_ohm: float
    cpw_res_eps_eff: float
    cpw_feed_Z0_ohm: float
    cpw_feed_eps_eff: float
    v_phi_m_s: float
    C_l_fF_per_um: float
    C_m_fF: float
    resonators: list[dict]
    g_MHz: float
    chi_MHz: float
    readout_photons: float
    SNR_estimate: float
    efficiency_estimate: float


def _run_script(rel: str, *args: str) -> None:
    cmd = [sys.executable, str(_REPO / rel), *args]
    subprocess.run(cmd, check=True)


def _ensure_island_cap(elmer_dir: Path) -> float:
    import shutil

    sub = elmer_dir / "island"
    res_path = sub / "transmon_island_project_results.json"
    if res_path.exists():
        return abs(load_results(sub, "transmon_island")["Cdata"]["C_Net1_Net1"][0])
    tmp = Path("/tmp/kqc_island/transmon_island_project_results.json")
    if tmp.exists():
        shutil.copytree("/tmp/kqc_island", sub, dirs_exist_ok=True)
        return abs(load_results(sub, "transmon_island")["Cdata"]["C_Net1_Net1"][0])
    subprocess.run(
        [sys.executable, str(_REPO / "scripts/sim/transmon_island_cap.py"), "--out", str(sub)],
        check=True,
    )
    return abs(load_results(sub, "transmon_island")["Cdata"]["C_Net1_Net1"][0])


def _ensure_cpw(elmer_dir: Path, w: float, g: float, tag: str) -> dict:
    sub = elmer_dir / f"cpw_{tag}"
    name = f"cpw_{int(w)}_{int(g)}"
    res_path = sub / f"{name}_project_results.json"
    if not res_path.exists():
        _run_script("scripts/sim/cpw_cross_section.py", "--width-um", str(w), "--gap-um", str(g), "--out", str(sub))
    res = load_results(sub, name)
    cs, ls = res["Cs"][0][0], res["Ls"][0][0]
    return {
        "Cs_F_per_m": cs,
        "Ls_H_per_m": ls,
        "Z0_ohm": math.sqrt(ls / cs),
        "v_phi_m_s": 1.0 / math.sqrt(ls * cs),
        "eps_eff": (C_LIGHT / (1.0 / math.sqrt(ls * cs))) ** 2,
    }


def _ensure_readout_cm(elmer_dir: Path) -> float:
    import shutil

    sub = elmer_dir / "readout"
    res_path = sub / "readout_coupling_project_results.json"
    if res_path.exists():
        return abs(load_results(sub, "readout_coupling")["Cdata"]["C_Net2_Net1"][0])
    tmp = Path("/tmp/kqc_readout/readout_coupling_project_results.json")
    if tmp.exists():
        shutil.copytree("/tmp/kqc_readout", sub, dirs_exist_ok=True)
        return abs(load_results(sub, "readout_coupling")["Cdata"]["C_Net2_Net1"][0])
    _run_script("scripts/sim/readout_coupling_cap.py")
    shutil.copytree("/tmp/kqc_readout", sub, dirs_exist_ok=True)
    return abs(load_results(sub, "readout_coupling")["Cdata"]["C_Net2_Net1"][0])


def _transmon_fq_GHz(c_sigma_F: float, ej_GHz: float) -> tuple[float, float]:
    ec_J = E_CHARGE**2 / (2.0 * c_sigma_F)
    ec_hz = ec_J / H
    ec_mhz = ec_hz / 1e6
    ej_hz = ej_GHz * 1e9
    # Deep-transmon limit (EJ >> EC): f_01 ≈ sqrt(2·EC·EJ)/h.
    fq_hz = math.sqrt(2.0 * ec_hz * ej_hz)
    return ec_mhz, fq_hz / 1e9


def _resonator_table(v_phi: float, c_l_f_per_m: float, c_m_f: float) -> list[dict]:
    rows = []
    for i, f_target in enumerate(RESONATOR_TARGETS_GHZ):
        f_hz = f_target * 1e9
        l_um = v_phi / (4.0 * f_hz) * 1e6
        # Bottom-right kept original claw; other three gained ~CLAW_LENGTH_DELTA_UM.
        rerouted = i < 3 or True  # all four now have claw architecture
        l_eff_um = l_um + (CLAW_LENGTH_DELTA_UM if rerouted else 0.0)
        f_sim_hz = v_phi / (4.0 * (l_eff_um * 1e-6))
        f_sim_ghz = f_sim_hz / 1e9
        # Shunt capacitance estimate for lambda/4 (order of magnitude).
        c_res_f = c_l_f_per_m * (l_eff_um * 1e-6) / math.pi
        q_c = max(c_res_f / c_m_f, 1.0)  # external Q from lumped C_m/C_res
        kappa_mhz = f_sim_hz / q_c / 1e6
        rows.append(
            {
                "name": f"R{i}",
                "f_target_GHz": f_target,
                "f_sim_GHz": round(f_sim_ghz, 4),
                "length_um": round(l_eff_um, 1),
                "C_res_fF": round(c_res_f * 1e15, 1),
                "Q_c": round(q_c, 1),
                "kappa_MHz": round(kappa_mhz, 3),
            }
        )
    return rows


def _coupling_and_readout(
    c_sigma_f: float,
    c_res_f: float,
    f_r_hz: float,
    f_q_hz: float,
    q_c: float,
    *,
    n_photons: float = 2.0,
) -> tuple[float, float, float, float]:
    """Return (g, chi, SNR_est, efficiency_est) in natural units with g/chi in Hz."""
    # Participation of island capacitance on the resonator node.
    beta = c_sigma_f / (c_sigma_f + c_res_f)
    g_hz = beta * math.sqrt(f_r_hz * f_q_hz) * 0.5  # galvanic-claw heuristic
    delta_hz = abs(f_r_hz - f_q_hz)
    chi_hz = g_hz**2 / delta_hz if delta_hz > 0 else 0.0
    kappa_hz = f_r_hz / q_c
    n_th = 0.5  # cold amplifier reference
    snr = (chi_hz / kappa_hz) ** 2 * n_photons / (n_th + 0.5) if kappa_hz > 0 else 0.0
    # Matching efficiency for resolved limit (chi >> kappa).
    eta = 4.0 * kappa_hz * (kappa_hz / 2.0) / (kappa_hz + kappa_hz / 2.0) ** 2 if kappa_hz > 0 else 0.0
    return g_hz / 1e6, chi_hz / 1e6, snr, min(eta, 1.0)


def build_report() -> ReadoutReport:
    elmer_dir = OUT_ROOT / "elmer"
    elmer_dir.mkdir(parents=True, exist_ok=True)

    c_sigma = _ensure_island_cap(elmer_dir)
    cpw_res = _ensure_cpw(elmer_dir, 30.0, 20.0, "res")
    cpw_feed = _ensure_cpw(elmer_dir, 25.0, 42.0, "feed")
    c_m = _ensure_readout_cm(elmer_dir)

    ec_mhz, f_q = _transmon_fq_GHz(c_sigma, EJ_GHZ)
    c_l_f_per_m = cpw_res["Cs_F_per_m"]
    c_l_fF_um = c_l_f_per_m * 1e-15 * 1e6
    resonators = _resonator_table(cpw_res["v_phi_m_s"], c_l_f_per_m, c_m)

    # Use R0 (4 GHz) for chip-level g, chi, SNR.
    r0 = resonators[0]
    c_res_f = r0["C_res_fF"] * 1e-15
    g, chi, snr, eta = _coupling_and_readout(
        c_sigma, c_res_f, r0["f_sim_GHz"] * 1e9, f_q * 1e9, r0["Q_c"]
    )

    return ReadoutReport(
        EC_MHz=round(ec_mhz, 2),
        f_q_GHz=round(f_q, 3),
        EJ_GHz=EJ_GHZ,
        C_sigma_fF=round(c_sigma * 1e15, 2),
        cpw_res_Z0_ohm=round(cpw_res["Z0_ohm"], 2),
        cpw_res_eps_eff=round(cpw_res["eps_eff"], 3),
        cpw_feed_Z0_ohm=round(cpw_feed["Z0_ohm"], 2),
        cpw_feed_eps_eff=round(cpw_feed["eps_eff"], 3),
        v_phi_m_s=cpw_res["v_phi_m_s"],
        C_l_fF_per_um=round(c_l_f_per_m * 1e9, 4),
        C_m_fF=round(c_m * 1e15, 3),
        resonators=resonators,
        g_MHz=round(g, 2),
        chi_MHz=round(chi, 2),
        readout_photons=2.0,
        SNR_estimate=round(snr, 3),
        efficiency_estimate=round(eta, 3),
    )


def write_report(report: ReadoutReport) -> Path:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    json_path = OUT_ROOT / "cooper_readout_report.json"
    md_path = OUT_ROOT / "cooper_readout_report.md"
    json_path.write_text(json.dumps(asdict(report), indent=2))

    lines = [
        "# Cooper chip readout simulation report",
        "",
        "Electrostatic Elmer (KQCircuits) + lumped readout model.",
        "",
        "## Transmon (island capacitance)",
        f"- C_sigma = **{report.C_sigma_fF} fF**",
        f"- EC/h = **{report.EC_MHz} MHz**",
        f"- EJ/h = **{report.EJ_GHz} GHz** (placeholder JJ; tune after e-beam)",
        f"- f_q ≈ **{report.f_q_GHz} GHz** (transmon limit)",
        "",
        "## CPW cross-sections (Elmer 2-D)",
        f"- Resonator 30/20 µm: Z0 = {report.cpw_res_Z0_ohm} Ω, eps_eff = {report.cpw_res_eps_eff}",
        f"- Feedline 25/42 µm: Z0 = {report.cpw_feed_Z0_ohm} Ω, eps_eff = {report.cpw_feed_eps_eff}",
        f"- C_l = {report.C_l_fF_per_um} fF/µm, v_phi = {report.v_phi_m_s:.3e} m/s",
        "",
        "## Readout coupling (feedline ↔ resonator islands)",
        f"- Mutual capacitance C_m = **{report.C_m_fF} fF** (200 µm islands, {132} µm separation)",
        "",
        "## Resonators (λ/4, claw reroute +180 µm)",
        "| Res | f_target | f_sim | L_eff | C_res | Q_c | κ/2π |",
        "|-----|----------|-------|-------|-------|-----|------|",
    ]
    for r in report.resonators:
        lines.append(
            f"| {r['name']} | {r['f_target_GHz']} | {r['f_sim_GHz']} | {r['length_um']} µm | "
            f"{r['C_res_fF']} fF | {r['Q_c']} | {r['kappa_MHz']} MHz |"
        )
    lines += [
        "",
        "## Dispersive readout (R0 reference)",
        f"- g/2π ≈ **{report.g_MHz} MHz** (island participation heuristic)",
        f"- χ/2π ≈ **{report.chi_MHz} MHz**",
        f"- SNR estimate (n={report.readout_photons} photons, n_th=0.5): **{report.SNR_estimate}**",
        f"- Matching efficiency estimate: **{report.efficiency_estimate}**",
        "",
        "## Notes",
        "- Full 3-D eigenmode (VectorHelmholtz) not run; f_r uses calibrated length + claw correction.",
        "- Dedicated readout taps not yet in GDS; C_m uses planar island model at 132 µm pullback.",
        "- Re-run after JJ sizing: set `EJ_GHZ` in this script or pass measured EJ.",
    ]
    md_path.write_text("\n".join(lines) + "\n")
    return md_path


def main() -> int:
    report = build_report()
    md = write_report(report)
    print(f"Wrote {md}")
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
