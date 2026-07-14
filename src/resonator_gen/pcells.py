"""Helpers for KLayout / KQCircuits PCell user-package registration."""

from __future__ import annotations

import sys
from pathlib import Path

from resonator_gen.logging_config import get_logger

logger = get_logger(__name__)


def user_package_path() -> Path:
    """Return the path of the bundled KQC user package.

    Notes
    -----
    In the KLayout GUI, register this directory via
    **KQCircuits → Add User Package**, then **Reload Libraries**.
    """
    root = Path(__file__).resolve().parents[2]
    return root / "klayout_package" / "resonator_gen_kqc"


def register_gui_pcells() -> None:
    """Register resonator_gen PCells into the KQC Element Library.

    Required for headless ``ReadoutResonator.create(...)`` use; in the
    KLayout GUI the user-package mechanism performs the equivalent step.
    Idempotent: re-registration of an existing PCell name is skipped.
    """
    from kqcircuits.elements.element import Element
    from kqcircuits.pya_resolver import pya
    from kqcircuits.util.library_helper import load_libraries, to_library_name

    load_libraries(path=Element.LIBRARY_PATH)
    library = pya.Library.library_by_name(Element.LIBRARY_NAME)
    if library is None:  # pragma: no cover - load_libraries guarantees this
        raise RuntimeError(f"KQC library {Element.LIBRARY_NAME!r} is not registered")

    pkg_parent = str(user_package_path().parent)
    if pkg_parent not in sys.path:
        sys.path.insert(0, pkg_parent)

    from resonator_gen_kqc.elements.capacitive_coupler import CapacitiveCouplerElement
    from resonator_gen_kqc.elements.readout_resonator import ReadoutResonator

    layout = library.layout()
    for pcell_class in (ReadoutResonator, CapacitiveCouplerElement):
        name = to_library_name(pcell_class.__name__)
        if name in layout.pcell_names():
            continue
        layout.register_pcell(name, pcell_class())
        logger.info("Registered PCell %s in %s", name, Element.LIBRARY_NAME)
