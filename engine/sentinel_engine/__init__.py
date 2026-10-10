"""SENTINEL-FX engine - single source of truth for all calculations.

Used identically by training AIs, the validator (tools/validate_pack.py)
and the live bot. Semantic versioning; DSL ops are append-only.
"""
__version__ = "1.0.0"

from . import indicators, dsl, checksum  # noqa: F401
