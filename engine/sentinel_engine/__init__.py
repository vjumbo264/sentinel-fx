"""sentinel_engine — public engine for SENTINEL-FX pair packs.

The SAME code is used by training AIs, the validator, and the live bot,
so training and live behavior are identical by construction.

Install:
    pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
"""
try:
    from .dsl import ENGINE_VERSION, compute_features, validate_dsl
except ImportError:
    ENGINE_VERSION = "0.2.0"
    def compute_features(*a, **k): pass
    def validate_dsl(*a, **k): pass
try:
    from .pack import Pack, load_pack, pack_checksum, verify_checksum
    from .check import check_bundle
    from .bundle import load_bundle, verify_bundle
except ImportError:
    pass

__version__ = ENGINE_VERSION
__all__ = [
    "ENGINE_VERSION", "__version__", "compute_features", "validate_dsl",
    "Pack", "load_pack", "pack_checksum", "verify_checksum",
    "check_bundle", "load_bundle", "verify_bundle",
    "indicators", "rules", "models", "news", "sandbox", "pack", "validate",
]
