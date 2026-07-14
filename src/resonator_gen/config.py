"""Pydantic configuration models and YAML loaders."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from resonator_gen.calibration import Calibration
from resonator_gen.constants import (
    DEFAULT_BEND_RADIUS_UM,
    DEFAULT_CPW_GAP_UM,
    DEFAULT_CPW_WIDTH_UM,
    DEFAULT_EPS_EFF,
    DEFAULT_PITCH_RATIO_MIN,
    DEFAULT_PITCH_UM,
    DEFAULT_RADIUS_RATIO_MIN,
    DEFAULT_SUBSTRATE_EPS_R,
)


class CpwConfig(BaseModel):
    """CPW cross-section and default meander spacing."""

    width_um: float = DEFAULT_CPW_WIDTH_UM
    gap_um: float = DEFAULT_CPW_GAP_UM
    bend_radius_um: float = DEFAULT_BEND_RADIUS_UM
    pitch_um: float = DEFAULT_PITCH_UM


class CalibrationConfig(BaseModel):
    """Serializable calibration section."""

    eps_eff: float = DEFAULT_EPS_EFF
    substrate_eps_r: float = DEFAULT_SUBSTRATE_EPS_R
    kinetic_inductance_override_v_phi_m_s: float | None = None
    coupler_dL_um: float = 0.0

    def to_calibration(self) -> Calibration:
        """Convert to a runtime :class:`~resonator_gen.calibration.Calibration`."""
        return Calibration(
            eps_eff=self.eps_eff,
            kinetic_inductance_override_v_phi_m_s=self.kinetic_inductance_override_v_phi_m_s,
            coupler_dL_um=self.coupler_dL_um,
            substrate_eps_r=self.substrate_eps_r,
        )


class ConstraintsConfig(BaseModel):
    """Soft/hard design-rule settings."""

    radius_ratio_min: float = DEFAULT_RADIUS_RATIO_MIN
    pitch_ratio_min: float = DEFAULT_PITCH_RATIO_MIN
    hard_fail: bool = False


class CouplerSpec(BaseModel):
    """Capacitive finger coupler parameters."""

    topology: Literal["finger"] = "finger"
    finger_number: int = 5
    finger_width_um: float = 5.0
    finger_gap_um: float = 3.0
    finger_length_um: float = 20.0
    ground_padding_um: float = 20.0


class PlacementSpec(BaseModel):
    """Anchor placement for a resonator relative to the chip origin."""

    x_um: float
    y_um: float
    orientation_deg: float = 90.0
    meander_span_um: float = 1200.0


class ResonatorSpec(BaseModel):
    """One readout resonator on the chip."""

    name: str
    frequency_hz: float
    mode: Literal["quarter", "half"] = "quarter"
    geometry: Literal["meander", "spiral"] = "meander"
    termination: Literal["short", "open"] = "short"
    bend_radius_um: float | None = None
    pitch_um: float | None = None
    meanders: int = -1
    n_bridges: int = 0
    coupler: CouplerSpec = Field(default_factory=CouplerSpec)
    placement: PlacementSpec

    @field_validator("frequency_hz")
    @classmethod
    def _positive_frequency(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError("frequency_hz must be positive")
        return value


class FeedlineSpec(BaseModel):
    """Feedline polyline in chip coordinates (µm)."""

    path_um: list[list[float]]

    @field_validator("path_um")
    @classmethod
    def _enough_points(cls, value: list[list[float]]) -> list[list[float]]:
        if len(value) < 2:
            raise ValueError("feedline.path_um needs at least two points")
        for pt in value:
            if len(pt) != 2:
                raise ValueError("each feedline point must be [x_um, y_um]")
        return value


class ChipConfig(BaseModel):
    """Full chip specification loaded from YAML/TOML-equivalent dict."""

    name: str
    cpw: CpwConfig = Field(default_factory=CpwConfig)
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    constraints: ConstraintsConfig = Field(default_factory=ConstraintsConfig)
    feedline: FeedlineSpec
    resonators: list[ResonatorSpec] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ChipConfig:
        """Load and validate a chip configuration from a YAML file."""
        with Path(path).open(encoding="utf-8") as handle:
            data: dict[str, Any] = yaml.safe_load(handle)
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Write this configuration to YAML."""
        payload = self.model_dump(mode="python")
        with Path(path).open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False)
