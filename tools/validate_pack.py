#!/usr/bin/env python3
"""Standalone wrapper for the SENTINEL-FX pack validator.
Usage: python tools/validate_pack.py <file.pairpack.json> [--mode fast|full]
Equivalent to: python -m sentinel_engine.validate <file> [--mode ...]
(The engine package must be importable: pip install the engine/ directory,
 or run from the repo root with engine/ on PYTHONPATH.)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from sentinel_engine.validate import main

if __name__ == "__main__":
    main()
