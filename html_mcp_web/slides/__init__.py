"""The slide engine: one builder and one skeleton stylesheet shared by every skin.

A skin is a directory holding ``skin.css`` (variable overrides and any chrome of its
own) and, optionally, ``assets/`` with images its chrome refers to and ``skin.json``
naming which chrome slots those images fill. Structure, spacing, page kinds, and
speaker-script placement come from here and change for every skin at once.
"""

from .build import build, main

__all__ = ["build", "main"]
