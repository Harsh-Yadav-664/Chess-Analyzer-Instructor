"""
web.py - Legacy frontend server, now wraps unified app.py

DEPRECATED: Use app.py directly (single server on :5000).
This file kept for backward compat - it just re-exports the unified app.
"""

try:
    from app import create_app, FRONTEND_HTML
    app = create_app()
    print("DEPRECATED: web.py is legacy. Use app.py (unified server) instead.")
except ImportError as e:
    # Fallback minimal
    from flask import Flask, render_template_string
    app = Flask(__name__)
    FRONTEND_HTML = "<h1>AI Chess Instructor</h1><p>Please run app.py instead: python app.py</p>"
    @app.route('/')
    def index():
        return render_template_string(FRONTEND_HTML)

if __name__ == '__main__':
    print("="*50)
    print("DEPRECATED: web.py is legacy frontend only.")
    print("Use app.py for unified server: python app.py")
    print("="*50)
    print("✓ Starting legacy frontend on http://localhost:5001")
    print("  Note: You still need backend on :5000 (web_integrator.py or app.py)")
    print("="*50)
    app.run(host='0.0.0.0', port=5001, threaded=True)
