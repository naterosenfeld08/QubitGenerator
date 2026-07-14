"""Helpers for KLayout / KQCircuits PCell user-package registration."""

from __future__ import annotations

from pathlib import Path


def user_package_path() -> Path:
    """Return the path of the bundled KQC user package.

    Notes
    -----
    In the KLayout GUI, register this directory via
    **KQCircuits → Add User Package**, then **Reload Libraries**.
    """
    root = Path(__file__).resolve().parents[2]
    return root / "klayout_package" / "resonator_gen_kqc"
