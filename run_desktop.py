#!/usr/bin/env python3
"""
run_desktop.py - Launcher for desktop GUI
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from gui import main
if __name__ == '__main__':
    main()
