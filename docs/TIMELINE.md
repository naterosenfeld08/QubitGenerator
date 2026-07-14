# Project Timeline

Chronological record of what was built in `resonator_gen`, in the order it happened. Each entry names the milestone, what changed, and why.

## 1. Initial planning: parametric CPW resonator generator

Starting point: hand-drawn meander resonators in KLayout, built by manually summing arc lengths and straight sections, then padding with an ad-hoc trailing segment to hit a target length. This did not scale across frequencies and produced unparametrized, asymmetric geometry.

Decision: build a thin domain-specific layer on top of **KQCircuits** (IQM's open-source KLayout extension) rather than reimplementing CPW geometry, bend solving, or PCell infrastructure from scratch.

Verified against the installed KQCircuits release (4.9.11, since 4.9.12 was not yet on PyPI) that:

- `Meander` takes a start point, end point, target `length`, and bend radius `r`, and solves analytically (closed-form, falling back to `scipy.optimize.brentq` for partial-turn cases) for the meander width that hits the target length exactly.
- `WaveguideCoplanar`, `SpiralResonatorPolygon`, and `FingerCapacitorSquare` provide the remaining primitives needed (arbitrary CPW paths, compact spiral bodies, capacitive coupling).

Two design defaults were locked in for safety, given the requester's inexperience with the domain:

- **Mode**: λ/4 (`quarter`), matching the target frequency table (4.0–5.5 GHz mapping to 7.44–5.41 mm at ε_eff ≈ 6.35).
- **Coupler topology**: capacitive finger end-coupling via `FingerCapacitorSquare`, matching existing KQCircuits demo chips, with a calibratable electrical length correction (`coupler_dL_um`) rather than a hardcoded geometric offset.

## 2. Milestone 1 — Repository scaffold

Set up Python packaging (`pyproject.toml`), pinned `kqcircuits==4.9.11` (`~=4.9.12` was requested but unavailable on PyPI at the time), and confirmed the runtime needed Python ≥ 3.10 — the system interpreter was 3.9, so a MacPorts Python 3.13 install was used instead.

Created the constants module (`constants.py`) as the single home for physical defaults: CPW width/gap (10 µm / 6 µm), bend radius and pitch (100 µm each), substrate ε_r (11.9), and the length-verification tolerance.

## 3. Milestone 2 — Calibration and constraints

Implemented `Calibration` (`calibration.py`): frequency → target electrical length via `L = v_phi / (4f)` for λ/4 (or `/(2f)` for λ/2), with `v_phi = c / sqrt(eps_eff)` unless overridden directly by a kinetic-inductance-derived phase velocity. Added `coupler_dL_um` as a first-class, config-driven correction rather than a magic number in geometry code.

Implemented `constraints.py`: soft-warn / hard-fail checks for bend radius and meander pitch against `ratio_min * (w + 2g)`, so violations are never silent.

## 4. Milestone 3 — Centerline analytics

Implemented `centerline.py`: `StraightSegment`, `ArcSegment`, and `Centerline`, with length as `Σs_i + Σr_i θ_i` — an analytic invariant of the path, never measured from GDS polygons. Added a numeric-integration cross-check (`numeric_length_um`) used only in tests, plus a general corner-to-centerline conversion (`corner_path_from_points`) with circular fillets for future use beyond the meander wrapper.

## 5. Milestone 4 — Coupler and CPW cross-section

Implemented `cpw.py` (mapping our `width_um`/`gap_um`/`bend_radius_um` naming onto KQCircuits' `a`/`b`/`r`) and `couplers.py` (`CapacitiveCoupler`, wrapping `FingerCapacitorSquare`, exposing `effective_length_um` that combines physical finger length with the calibrated `coupler_dL_um`).

## 6. Milestone 5 — Meander and spiral resonators, chip assembly

Implemented `resonators/meander.py` (`MeanderResonator`) and `resonators/spiral.py` (`SpiralResonator`), each wrapping the corresponding KQCircuits element and computing a length budget (`resonators/base.py`) that splits the calibrated target length into coupler correction and geometric body length — no trailing filler segments anywhere.

Implemented `chip.py` (`Chip`): draws a feedline, places each configured resonator, and reports target vs. actual length per resonator. Implemented `config.py` (`ChipConfig`, `ResonatorSpec`, `CouplerSpec`, `PlacementSpec`, `FeedlineSpec`) as Pydantic v2 models loaded from YAML, and the example `configs/test_chip_v1.yaml` covering the four target frequencies (4.0/4.5/5.0/5.5 GHz).

## 7. Milestone 6 — KLayout GUI PCells and CLIs

Implemented the KQCircuits user-package layout under `klayout_package/resonator_gen_kqc/` (`ReadoutResonator` and `CapacitiveCouplerElement` PCells), so parameters are editable in the KLayout GUI element library after **Add User Package → Reload Libraries**.

Added `scripts/build_chip.py` (YAML → GDS) and `scripts/sweep_lengths.py` (frequency → length verification table), both thin wrappers around `resonator_gen.cli`.

Verified end-to-end: **24 tests passing**, sample chip built to `out/test_chip_v1.gds`, CLI output confirming realized lengths within nanometres of target for all four frequencies.

## 8. First practical use: understanding and exporting the generated chip

Walked through basic usage: which CLI command builds the chip, what the resonator ordering means physically (left-to-right on the demo feedline corresponds to *increasing* frequency, i.e. *decreasing* physical length: R0 at 4.0 GHz is the longest/leftmost), and what the five GDS layers represent (`130/1` gap metal for fabrication; `133/1` ground-grid avoidance, `135/1` waveguide-path annotation, `154/1` ports, `225/0` refpoints — all bookkeeping, not fabricated metal).

## 9. Integrating with an existing chip design

The user had a separate, hand-drawn base chip (`Qubit(Correct).gds`, on layers `1/0` and `1/1`) and wanted the generated resonators merged into it. Wrote `scripts/merge_resonators_into_chip.py`: copies specific resonator cells (`R0`–`R3`) from a resonator_gen GDS into an existing chip, remapping the KQCircuits gap layer onto the target chip's metal/gap layer, with configurable placement offset (`--dx`/`--dy`) and an explicit refusal to overwrite the base chip in place.

## 10. Publishing to GitHub

Initialized git in the (previously non-version-controlled) project directory, wrote a `.gitignore` excluding generated GDS/OASIS output and build artifacts, and pushed the initial commit to a new public repository: `https://github.com/naterosenfeld08/QubitGenerator`.

## 11. Planning keepout-aware auto-placement

A follow-up feature request: instead of manually picking `(x, y)` anchor points for each resonator, automatically find where on the chip a resonator should go given a fixed coupler tap point/direction, a target length, and a set of keepouts (other resonators, the feedline, bond pads, chip edge).

The request explicitly scoped out a general Eikonal/Fast-Marching cost-field approach and biarc/freeform-curve fitting — the actual problem is exact keepout-distance clearance, solvable with KLayout's native `Region` boolean and sizing operations on exact polygon geometry, with no rasterization or PDE solve needed.

Resolved four open questions before coding: (1) added `DieSpec` and `KeepoutEntry` to config, since neither existed yet; (2) clearance defaults to the existing `pitch_ratio_min * (w + 2g)` floor rather than a second independent parameter; (3) the coupler tap direction remains fixed (no direction search) — only corridor length, width, and meander-vs-spiral choice are automatic; (4) confirmed search latency is dominated by microsecond-scale closed-form/`brentq` width evaluations and sub-millisecond Region booleans, keeping full searches in the 10–100 ms range (acceptable for both GUI PCell edits and batch builds).

Confirmed that KQCircuits' `Meander.build()` computes its width-solving math in local closures with no introspectable API, so the width formulas (`bend_length_increment`, `meander_length_increment`) were mirrored as pure functions in a new module, with a dedicated parity test holding them accountable against the actual installed KQCircuits geometry rather than trusting the duplication blindly.

## 12. Implementing keepout-aware auto-placement

Added `src/resonator_gen/keepouts.py` (`KeepoutSet`): exact, integer-database-unit Region algebra — union keepouts, grow by clearance, subtract from the die interior. Added `src/resonator_gen/routing.py` (`find_anchored_placement`, `PlacementResult`, `PlacementInfeasibleError`): the anchored corridor search, working in a local frame with the coupler tap at the origin and the fixed direction along +x, using a deterministic grid scan over corridor length with local refinement, and a spiral fallback for keep-in regions too irregular for a meander.

Extended `config.py` with `DieSpec`, `KeepoutEntry`, and `PlacementSpec.mode: "manual" | "auto"` (manual mode is unchanged from the original release — full backward compatibility with `configs/test_chip_v1.yaml`). Extended `chip.py` to build the keepout set once per chip build, solve placement for each `auto`-mode resonator in config order, and feed each newly placed resonator's own footprint back into the keepout set before placing the next one.

Extended the `ReadoutResonator` GUI PCell with a `placement_mode` parameter, so the same auto-solve is available interactively in KLayout (measured regeneration time: ~8 ms per parameter edit — well under the "should feel instant" bar).

Verified with a new `configs/test_chip_v1_auto.yaml` (the same four frequencies, now placed automatically) and 25 new tests: clearance exactness (checked with KLayout's own `separation_check`, not hand-rolled distance math), meander-width-math parity against installed KQCircuits (50 random cases), anchored-rectangle correctness on synthetic regions with hand-computable answers (open rectangle, notch, L-shape, region with a hole), meander-vs-spiral geometry selection, an end-to-end auto-placed four-frequency regression with zero pairwise spacing violations, a deliberately overcrowded-die failure-path test asserting full diagnostic fields are populated, and GDS build-determinism across repeated runs.

Final state: **49 tests passing**, auto-placed sample chip built to `out/test_chip_v1_auto.gds`.

## 13. Documentation and commit

Added this timeline document and a companion mathematical/engineering reference (`docs/MATH_REFERENCE.md`), then committed both feature additions (auto-placement) and documentation to the GitHub repository.
