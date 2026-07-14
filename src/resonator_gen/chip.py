"""Chip assembly: feedline + N resonators → GDS/OASIS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resonator_gen.calibration import Calibration
from resonator_gen.config import ChipConfig, ResonatorSpec
from resonator_gen.cpw import CpwCrossSection
from resonator_gen.logging_config import get_logger
from resonator_gen.resonators.base import ResonatorBuildResult
from resonator_gen.resonators.meander import MeanderResonator
from resonator_gen.resonators.spiral import SpiralResonator

logger = get_logger(__name__)


class Chip:
    """Assemble a feedline and readout resonators from a :class:`ChipConfig`."""

    def __init__(self, config: ChipConfig) -> None:
        self.config = config
        self._specs: list[ResonatorSpec] = list(config.resonators)
        self._layout: Any | None = None
        self._top_cell: Any | None = None
        self._results: list[ResonatorBuildResult] = []
        self._built = False

    def add_resonator(self, spec: ResonatorSpec) -> None:
        """Append a resonator specification before :meth:`build`."""
        if self._built:
            raise RuntimeError("Cannot add resonators after build()")
        self._specs.append(spec)

    @property
    def calibration(self) -> Calibration:
        """Runtime calibration object."""
        return self.config.calibration.to_calibration()

    def build(self) -> None:
        """Generate KLayout cells for the feedline and all resonators."""
        from kqcircuits.elements.waveguide_coplanar import WaveguideCoplanar
        from kqcircuits.pya_resolver import pya

        layout = pya.Layout()
        # Prefer KQC default layers when available.
        try:
            from kqcircuits import defaults as kqc_defaults

            _ = kqc_defaults  # layers registered on first Element.create
        except Exception:  # pragma: no cover - defensive
            pass

        top = layout.create_cell(self.config.name)
        cross = CpwCrossSection.from_config(self.config.cpw)
        path = [
            pya.DPoint(float(x), float(y)) for x, y in self.config.feedline.path_um
        ]
        feed = WaveguideCoplanar.create(layout, path=path, **cross.as_kqc_kwargs())
        top.insert(pya.DCellInstArray(feed.cell_index(), pya.DTrans(0, False, 0, 0)))

        results: list[ResonatorBuildResult] = []
        for spec in self._specs:
            if spec.geometry == "meander":
                builder = MeanderResonator(spec)
            elif spec.geometry == "spiral":
                builder = SpiralResonator(spec)
            else:
                raise ValueError(f"Unknown geometry {spec.geometry!r}")
            result = builder.build_standalone(
                layout,
                self.calibration,
                self.config.cpw,
                constraints=self.config.constraints,
            )
            top.insert(pya.DCellInstArray(result.cell_instance.cell_index(), pya.DTrans(0, False, 0, 0)))
            results.append(result)

        self._layout = layout
        self._top_cell = top
        self._results = results
        self._built = True
        logger.info("Built chip %s with %d resonators", self.config.name, len(results))

    def write_gds(self, path: str | Path) -> None:
        """Export the chip to GDSII."""
        self._require_built()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert self._layout is not None
        options = self._layout.get_info(0) if False else None  # keep for future
        _ = options
        self._layout.write(str(path))
        logger.info("Wrote GDS %s", path)

    def write_oas(self, path: str | Path) -> None:
        """Export the chip to OASIS."""
        self._require_built()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert self._layout is not None
        self._layout.write(str(path))
        logger.info("Wrote OASIS %s", path)

    def report(self) -> list[ResonatorBuildResult]:
        """Return build results and log target vs actual lengths."""
        self._require_built()
        for result in self._results:
            delta = result.actual_length_um - result.body_length_um
            logger.info(
                "%s f=%.3f GHz target=%.3f µm body=%.3f µm actual=%.6f µm Δbody=%.6f µm",
                result.name,
                result.frequency_hz / 1e9,
                result.target_length_um,
                result.body_length_um,
                result.actual_length_um,
                delta,
            )
        return list(self._results)

    def _require_built(self) -> None:
        if not self._built:
            raise RuntimeError("Call build() before export/report")
