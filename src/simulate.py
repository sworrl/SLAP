#!/usr/bin/env python3
"""
SLAP Simulation Mode

Quick launcher for testing without hardware.
Equivalent to: python run.py --simulate --debug
"""

import sys
from pathlib import Path

# Add slap package to path
sys.path.insert(0, str(Path(__file__).parent))

# Import and run with simulation flags
sys.argv.extend(["--simulate", "--debug"])

from run import main

if __name__ == "__main__":
    main()
