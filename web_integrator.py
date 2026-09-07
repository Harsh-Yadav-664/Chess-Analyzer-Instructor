"""
web_integrator.py - Legacy backend, now wraps unified app.py

DEPRECATED: Use app.py directly (single server).
This file is kept for backward compatibility - it just creates the unified app.
"""

import os
import sys
from pathlib import Path

# Import unified app
try:
    from app import create_app, global_engine
    app = create_app()
    
    def init_engine():
        from app import global_engine as ge
        return ge is not None

    # Re-export for old imports
    global_engine = global_engine

except ImportError as e:
    print(f"Failed to import unified app: {e}")
    print("Falling back to legacy implementation...")
    # Fallback legacy - minimal
    from flask import Flask, request, jsonify, session
    from flask_cors import CORS
    from flask_session import Session
    import chess
    import secrets
    from config import get_stockfish_path, PROFILE_DIR, SESSION_DIR, WEB_PROFILE_FILE
    from engine import ChessEngine
    from instructor import assess_move, analyze_pre_move_threats, create_coach_session
    from stats import SessionManager, ProfileStore, PlayerProfile
    import threading

    app = Flask(__name__)
    app.config['SECRET_KEY'] = secrets.token_hex(16)
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = SESSION_DIR
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    Session(app)
    CORS(app, supports_credentials=True)

    global_engine = None
    engine_lock = threading.RLock()
    profile_store = ProfileStore(WEB_PROFILE_FILE)

    def init_engine():
        global global_engine
        path = get_stockfish_path()
        if not path:
            return False
        try:
            global_engine = ChessEngine(path)
            global_engine.start()
            return True
        except Exception as e:
            print(f"Engine init failed: {e}")
            return False

    @app.route('/api/health')
    def health():
        return jsonify({'success': True, 'engine_ready': global_engine is not None})

if __name__ == '__main__':
    print("="*50)
    print("DEPRECATED: web_integrator.py is legacy.")
    print("Use app.py instead: python app.py")
    print("="*50)
    if init_engine() or os.environ.get("USE_FAKE_ENGINE") == "1":
        app.run(host='0.0.0.0', port=5000, threaded=True)
    else:
        print("Engine not available")
