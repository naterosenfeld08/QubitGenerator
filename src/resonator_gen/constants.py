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

# Relative frequency round-trip tolerance (0.01 %).
FREQUENCY_ROUNDTRIP_REL_TOL: float = 1e-4
