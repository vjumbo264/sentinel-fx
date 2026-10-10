#!/usr/bin/env python3
"""Standalone entry point. Equivalent to: python -m sentinel_engine.validate <file>
Usage: pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
       python tools/validate_pack.py <pack.pairpack.json> [--mode fast|full]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
from sentinel_engine.validate import main
if __name__ == "__main__":
    main()
