#!/usr/bin/env python3
"""
run_web.py - Simple launcher for web version
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app import create_app
from config import WEB_HOST, WEB_PORT

if __name__ == '__main__':
    app = create_app()
    print(f"Starting AI Chess Instructor on http://{WEB_HOST}:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, threaded=True)
