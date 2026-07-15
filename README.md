# Resonator Gen

Parametric λ/4 (and λ/2) CPW readout resonators for superconducting chips, built as a thin layer on [KQCircuits](https://github.com/iqm-finland/KQCircuits).

## Features

- Frequency → length via a first-class `Calibration` (`eps_eff`, kinetic inductance override, coupler `dL`)
- Meander / spiral bodies wrapping KQC `Meander` and `SpiralResonatorPolygon` (analytic length solve, no trailing filler)
- Capacitive finger coupler (`FingerCapacitorSquare`)
- YAML-driven multi-resonator chip export to GDS/OASIS
- Optional KLayout GUI PCells via a KQC user package

## Requirements

- Python ≥ 3.10 (3.13 recommended; system 3.9 cannot install modern `kqcircuits`)
- `kqcircuits` 4.9.x, `klayout`, `numpy`, `scipy`, `pydantic`, `PyYAML`

## Install

```bash
# example with MacPorts Python 3.13
/opt/local/bin/python3.13 -m pip install -e ".[dev]"
```

Verify:

```bash
python -c "from kqcircuits.elements.meander import Meander; from resonator_gen import ChipConfig; print('ok')"
```

## Quick start

```python
from resonator_gen import ChipConfig, Chip

cfg = ChipConfig.from_yaml("configs/test_chip_v1.yaml")
chip = Chip(cfg)
chip.build()
chip.write_gds("out/test_chip_v1.gds")
chip.report()
```

CLI:

```bash
python scripts/build_chip.py configs/test_chip_v1.yaml -o out/test_chip_v1.gds
python scripts/sweep_lengths.py --eps-eff 6.35
```

## KLayout GUI PCells

1. Install KQCircuits (Salt package or `setup_within_klayout.py`).
2. **KQCircuits → Add User Package** → point at `klayout_package/resonator_gen_kqc`.
3. Restart KLayout / **Reload Libraries**.
4. Place `ReadoutResonator` from the Element library; edit `frequency_ghz`, CPW, coupler, and orientation.

Ensure headless `resonator_gen` is importable from KLayout’s Python (same env or `PYTHONPATH`).

## Defaults

| Parameter | Default |
|-----------|---------|
| CPW `w` / `g` | 30 µm / 20 µm |
| Bend radius | 220 µm |
| Pitch | 220 µm |
| `eps_eff` | 6.35 (matches 4.0–5.5 GHz table) |
| Mode | λ/4 (`quarter`) |
| Coupler | capacitive finger |
| Termination | `short` |

## Tests

```bash
python -m pytest -q
```

## EM simulation (Cooper chip)

Requires [Elmer](https://www.csc.fi/web/elmer) (`sudo port install elmerfem` on MacPorts) and `gmsh` (`pip install gmsh`). Run the full readout report:

```bash
python scripts/sim/cooper_chip_report.py
```

Output: `out/sim/cooper_readout_report.md` (island C_Σ, CPW Z₀, readout C_m, f_r, Q_c, g, χ).

## Non-goals (v1)

Automatic area vs coupling optimization. Full-chip 3-D eigenmode (VectorHelmholtz) is deferred; v1 uses Elmer electrostatics + lumped readout model.
