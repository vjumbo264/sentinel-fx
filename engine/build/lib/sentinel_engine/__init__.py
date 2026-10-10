"""sentinel_engine — public engine for SENTINEL-FX pair packs.

The SAME code is used by training AIs, the validator, and the live bot,
so training and live behavior are identical by construction.

Install:
    pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
"""
from .dsl import ENGINE_VERSION, compute_features, validate_dsl
from .pack import Pack, load_pack, pack_checksum, verify_checksum

__version__ = ENGINE_VERSION
__all__ = [
    "ENGINE_VERSION", "__version__", "compute_features", "validate_dsl",
    "Pack", "load_pack", "pack_checksum", "verify_checksum",
    "indicators", "rules", "models", "news", "sandbox", "pack", "validate",
]
