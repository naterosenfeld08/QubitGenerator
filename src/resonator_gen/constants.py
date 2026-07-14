"""Physical defaults and constraint multipliers for resonator_gen.

All library-wide numeric defaults live here (or in YAML configs). Do not
scatter magic numbers through geometry code.
"""

from __future__ import annotations

# Speed of light in vacuum (m/s).
C_MPS: float = 299_792_458.0

# Default CPW cross-section (µm). Matches KQCircuits Element a/b defaults.
DEFAULT_CPW_WIDTH_UM: float = 10.0
DEFAULT_CPW_GAP_UM: float = 6.0

# Default bend radius and meander pitch (µm).
DEFAULT_BEND_RADIUS_UM: float = 100.0
DEFAULT_PITCH_UM: float = 100.0

# Soft design-rule multipliers vs. (w + 2·g).
DEFAULT_RADIUS_RATIO_MIN: float = 3.0
DEFAULT_PITCH_RATIO_MIN: float = 3.0

# Silicon substrate relative permittivity (bulk).
DEFAULT_SUBSTRATE_EPS_R: float = 11.9

# Nominal effective permittivity for vacuum-above Si CPW (tuned to match
# the project's 4.0–5.5 GHz / mm λ/4 table).
DEFAULT_EPS_EFF: float = 6.35

# Geometry length tolerance used in verification.
# KLayout path annotations quantize near the database unit (~1 nm); allow 5 nm.
LENGTH_TOL_UM: float = 5e-3

# Verification tolerance for auto-placed resonators: solved spans are not
# round numbers, so meanders have more corners and each annotation vertex
# rounds to the 1 nm grid. This is measurement quantization of the length
# report, not geometry error (the analytic length solve is exact).
AUTO_LENGTH_TOL_UM: float = 5e-2

# Relative frequency round-trip tolerance (0.01 %).
FREQUENCY_ROUNDTRIP_REL_TOL: float = 1e-4

# KQCircuits layers (face 1t1) used for keepout extraction from placed cells.
GAP_LAYER: tuple[int, int] = (130, 1)
AVOIDANCE_LAYER: tuple[int, int] = (133, 1)

# KQC Element `margin` default: protection-layer margin around drawn geometry.
KQC_PROTECTION_MARGIN_UM: float = 5.0

# Straight lead between the coupler tap and the meander start
# (mirrored by the auto-placement anchor computation; keep in sync).
COUPLER_LEAD_UM: float = 50.0

# Auto-placement search parameters.
PLACEMENT_GRID_STEP_RATIO: float = 0.5  # grid step = ratio * bend radius
PLACEMENT_REFINE_POINTS: int = 17
PLACEMENT_BISECT_ITERATIONS: int = 60
SPIRAL_ASPECT_RATIO_MAX: float = 2.0
SPIRAL_LENGTH_TOL_UM: float = 1.0
