"""Logging helpers for resonator_gen (no library prints)."""

from __future__ import annotations

import logging


def get_logger(name: str = "resonator_gen") -> logging.Logger:
    """Return a namespaced logger.

    Parameters
    ----------
    name :
        Logger name, usually ``"resonator_gen.<module>"``.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    return logger
