#!/usr/bin/env python3
"""Compile content.html into slides with the neutral skin.

Usage: python3 build.py <content.html> <slides.html>

All structure lives in the shared engine (html_mcp_web.slides); this directory holds
only the skin.
"""
import sys
from pathlib import Path

from html_mcp_web.slides import build

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(Path(sys.argv[1]), Path(sys.argv[2]), Path(__file__).parent)
