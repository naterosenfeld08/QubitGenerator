"""Frequency ↔ length calibration for CPW resonators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from resonator_gen.constants import C_MPS, DEFAULT_EPS_EFF, DEFAULT_SUBSTRATE_EPS_R

ModeName = Literal["quarter", "half"]


@dataclass(frozen=True)
class Calibration:
    """Map target frequency to resonator electrical length.

    Parameters
    ----------
    eps_eff :
        Effective relative permittivity of the CPW mode.
    kinetic_inductance_override_v_phi_m_s :
        If set, override the phase velocity ``c / sqrt(eps_eff)`` entirely
        (use when kinetic inductance dominates the correction).
    coupler_dL_um :
        Effective electrical length (µm) attributed to the coupler, subtracted
        from the geometric body budget so the total electrical length hits the
        mode target.
    substrate_eps_r :
        Bulk substrate permittivity (documentation / future EM export).
    """

    eps_eff: float = DEFAULT_EPS_EFF
    kinetic_inductance_override_v_phi_m_s: float | None = None
    coupler_dL_um: float = 0.0
    substrate_eps_r: float = DEFAULT_SUBSTRATE_EPS_R

    def phase_velocity_m_s(self) -> float:
        """Return phase velocity in m/s."""
        if self.kinetic_inductance_override_v_phi_m_s is not None:
            return self.kinetic_inductance_override_v_phi_m_s
        if self.eps_eff <= 0.0:
            raise ValueError(f"eps_eff must be positive, got {self.eps_eff}")
        return C_MPS / (self.eps_eff**0.5)

    def wavelength_um(self, frequency_hz: float) -> float:
        """Return full guided wavelength in micrometres."""
        if frequency_hz <= 0.0:
            raise ValueError(f"frequency_hz must be positive, got {frequency_hz}")
        return self.phase_velocity_m_s() / frequency_hz * 1e6

    def target_length_um(self, frequency_hz: float, mode: ModeName = "quarter") -> float:
        """Return mode target electrical length in micrometres.

        Notes
        -----
        Coupler loading is *not* subtracted here. Callers that size the
        meander/spiral body should subtract ``coupler_dL_um`` (and any
        physical coupler path length) from this value.
        """
        wavelength_um = self.wavelength_um(frequency_hz)
        if mode == "quarter":
            return wavelength_um / 4.0
        if mode == "half":
            return wavelength_um / 2.0
        raise ValueError(f"Unsupported mode {mode!r}; expected 'quarter' or 'half'")

    def body_length_um(self, frequency_hz: float, mode: ModeName = "quarter") -> float:
        """Return geometric body length after coupler electrical correction."""
        return self.target_length_um(frequency_hz, mode=mode) - self.coupler_dL_um

    def frequency_hz_from_length(self, length_um: float, mode: ModeName = "quarter") -> float:
        """Invert ``target_length_um`` (includes coupler_dL in electrical length)."""
        if length_um <= 0.0:
            raise ValueError(f"length_um must be positive, got {length_um}")
        v_phi = self.phase_velocity_m_s()
        length_m = length_um * 1e-6
        if mode == "quarter":
            return v_phi / (4.0 * length_m)
        if mode == "half":
            return v_phi / (2.0 * length_m)
        raise ValueError(f"Unsupported mode {mode!r}; expected 'quarter' or 'half'")
