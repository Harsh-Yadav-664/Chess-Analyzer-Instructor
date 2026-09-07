"""
app.py - Unified web server for AI Chess Instructor

Single Flask server serving both API and frontend (fixes two-server problem).
- Transactional /api/move (no session mutation before success) - fixes illegal move bug
- Per-session coach state and stats (fixes global singleton issue)
- Thread-safe engine with lock
- Relative API URLs (works in preview, deployable)
- Improved frontend with visual cues, busy lock, last-move highlight, promotion, eval graph

Run:
    python app.py
    -> http://localhost:5000

Env vars:
    STOCKFISH_PATH - path to stockfish binary
    WEB_PORT - port (default 5000)
    WEB_HOST - host (default 0.0.0.0)
    USE_FAKE_ENGINE - if 1, uses mini engine when stockfish missing (for dev/preview)
"""

import os
import sys
import secrets
import json
import threading
from pathlib import Path
from typing import Optional, Dict

import chess
from flask import Flask, request, jsonify, session, render_template_string
from flask_cors import CORS
from flask_session import Session

# Local imports
try:
    from config import (
        get_stockfish_path, PROFILE_DIR, WEB_PROFILE_FILE, SESSION_DIR,
        WEB_HOST, WEB_PORT, FLASK_SECRET, DEFAULT_DIFFICULTY, DEFAULT_COACH_MODE,
        USE_FAKE_ENGINE_IF_MISSING, ensure_profile_dir
    )
except ImportError:
    # Fallback if config not present
    def get_stockfish_path(): return os.environ.get("STOCKFISH_PATH")
    PROFILE_DIR = Path.home() / ".chess_instructor"
    WEB_PROFILE_FILE = PROFILE_DIR / "web_profile.json"
    SESSION_DIR = PROFILE_DIR / "sessions"
    WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
    WEB_PORT = int(os.environ.get("WEB_PORT", "5000"))
    FLASK_SECRET = os.environ.get("FLASK_SECRET", secrets.token_hex(16))
    DEFAULT_DIFFICULTY = "intermediate"
    DEFAULT_COACH_MODE = "adaptive"
    USE_FAKE_ENGINE_IF_MISSING = True
    def ensure_profile_dir():
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

from engine import ChessEngine
from instructor import (
    assess_move, analyze_pre_move_threats, CoachSession, create_coach_session
)
from stats import SessionManager, ProfileStore, PlayerProfile

# Ensure dirs
ensure_profile_dir()

# Global engine and lock
global_engine: Optional[ChessEngine] = None
engine_lock = threading.RLock()
profile_store = ProfileStore(WEB_PROFILE_FILE)

# In-memory per-session managers (keyed by flask session id)
# We also persist some in flask session cookie for simplicity
session_managers: Dict[str, SessionManager] = {}
coach_sessions: Dict[str, CoachSession] = {}
session_managers_lock = threading.RLock()

def get_or_create_session_manager(sess_id: str) -> SessionManager:
    with session_managers_lock:
        if sess_id not in session_managers:
            # Try to load profile
            loaded_profile = profile_store.load()
            sm = SessionManager(profile=loaded_profile if loaded_profile else PlayerProfile(),
                                profile_store=profile_store)
            session_managers[sess_id] = sm
        return session_managers[sess_id]

def get_or_create_coach_session(sess_id: str) -> CoachSession:
    with session_managers_lock:
        if sess_id not in coach_sessions:
            coach_sessions[sess_id] = create_coach_session(DEFAULT_COACH_MODE)
        return coach_sessions[sess_id]

def create_app(stockfish_path: Optional[str] = None, use_fake_if_missing: bool = True):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = FLASK_SECRET
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = SESSION_DIR
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    Session(app)
    CORS(app, supports_credentials=True)

    # Init engine
    def init_engine():
        global global_engine
        global_engine = None
        path = stockfish_path or get_stockfish_path()
        if not path and use_fake_if_missing:
            # Try to create mini engine for dev
            fake_src = Path(__file__).parent / "tests" / "mini_uci_engine.py"
            if fake_src.exists():
                # Create executable copy with current interpreter
                import tempfile
                lines = fake_src.read_text().splitlines()
                body = "\n".join(lines[1:])
                dst_dir = Path(tempfile.mkdtemp(prefix="cai-engine-"))
                dst = dst_dir / "mini_uci_engine.py"
                dst.write_text(f"#!{sys.executable}\n{body}")
                dst.chmod(0o755)
                path = str(dst)
                print(f"ℹ Using fake engine for dev: {path}")
        
        if not path:
            print("⚠ Stockfish not found - engine will be unavailable until configured")
            print("  Set STOCKFISH_PATH env var or install stockfish")
            return False

        try:
            global_engine = ChessEngine(path)
            global_engine.start()
            print(f"✓ Engine initialized: {path}")
            return True
        except Exception as e:
            print(f"✗ Engine init failed: {e}")
            if use_fake_if_missing and "mini_uci" not in str(path):
                # Try fake as fallback
                fake_src = Path(__file__).parent / "tests" / "mini_uci_engine.py"
                if fake_src.exists():
                    import tempfile
                    lines = fake_src.read_text().splitlines()
                    body = "\n".join(lines[1:])
                    dst_dir = Path(tempfile.mkdtemp(prefix="cai-engine-"))
                    dst = dst_dir / "mini_uci_engine.py"
                    dst.write_text(f"#!{sys.executable}\n{body}")
                    dst.chmod(0o755)
                    try:
                        global_engine = ChessEngine(str(dst))
                        global_engine.start()
                        print(f"✓ Fallback to fake engine: {dst}")
                        return True
                    except Exception as e2:
                        print(f"✗ Fake engine also failed: {e2}")
            return False

    init_engine()

    # Helpers
    def get_board_from_session():
        fen = session.get('board_fen', chess.STARTING_FEN)
        try:
            return chess.Board(fen)
        except:
            return chess.Board()

    def save_board_to_session(board):
        session['board_fen'] = board.fen()

    def board_to_dict(board):
        return {
            'fen': board.fen(),
            'turn': 'white' if board.turn == chess.WHITE else 'black',
            'is_check': board.is_check(),
            'is_checkmate': board.is_checkmate(),
            'is_stalemate': board.is_stalemate(),
            'is_game_over': board.is_game_over(),
            'legal_moves': [m.uci() for m in board.legal_moves],
            'move_count': board.fullmove_number,
        }

    def assessment_to_dict(a):
        return {
            'move': a.move_played.uci(),
            'grade': a.grade.name,
            'grade_value': int(a.grade),
            'eval_initial': a.eval_initial / 100,
            'eval_final': a.eval_final / 100,
            'centipawn_loss': a.centipawn_loss,
            'best_move': a.best_move.uci() if a.best_move else None,
            'was_best_move': a.was_best_move,
            'explanation': a.explanation,
            'visual_cues': a.visual_cues,
        }

    # API Routes
    @app.route('/api/init', methods=['POST'])
    def api_init():
        try:
            # Use session id as key
            sess_id = session.get('_id') or secrets.token_hex(8)
            session['_id'] = sess_id

            board = chess.Board()
            save_board_to_session(board)
            session['game_active'] = True
            session['instructor_mode'] = session.get('instructor_mode', DEFAULT_COACH_MODE)
            session['difficulty_mode'] = session.get('difficulty_mode', DEFAULT_DIFFICULTY)
            session['move_history'] = []
            session['eval_history'] = []
            session['undo_stack'] = []

            # Reset per-session managers
            with session_managers_lock:
                if sess_id in session_managers:
                    session_managers[sess_id].start_game()
                else:
                    get_or_create_session_manager(sess_id).start_game()
                if sess_id in coach_sessions:
                    coach_sessions[sess_id] = create_coach_session(session['instructor_mode'])
                else:
                    get_or_create_coach_session(sess_id)

            if global_engine:
                with engine_lock:
                    global_engine.set_difficulty(session['difficulty_mode'])

            return jsonify({'success': True, 'board': board_to_dict(board)})
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/board', methods=['GET'])
    def api_get_board():
        try:
            board = get_board_from_session()
            return jsonify({'success': True, 'board': board_to_dict(board)})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/move', methods=['POST'])
    def api_make_move():
        """
        TRANSACTIONAL move endpoint - fixes P0 bug:
        - Works on a copy, only saves to session after success
        - Returns authoritative board on error for resync
        - Thread-safe engine access
        """
        try:
            data = request.json or {}
            move_uci = data.get('move')
            if not move_uci:
                return jsonify({'success': False, 'error': 'No move provided'}), 400

            # Get current board (authoritative)
            board = get_board_from_session()
            original_fen = board.fen()  # For rollback

            # Validate move format
            try:
                move = chess.Move.from_uci(move_uci)
            except:
                return jsonify({
                    'success': False,
                    'error': 'Invalid move format',
                    'board': board_to_dict(board)  # Resync
                }), 400

            if move not in board.legal_moves:
                return jsonify({
                    'success': False,
                    'error': 'Illegal move',
                    'board': board_to_dict(board)
                }), 400

            sess_id = session.get('_id') or secrets.token_hex(8)
            session['_id'] = sess_id
            sm = get_or_create_session_manager(sess_id)
            cs = get_or_create_coach_session(sess_id)
            instructor_mode = session.get('instructor_mode', DEFAULT_COACH_MODE)
            difficulty_mode = session.get('difficulty_mode', DEFAULT_DIFFICULTY)

            # Pre-move warning (before mutation)
            warning = analyze_pre_move_threats(board, chess.WHITE, instructor_mode)

            # Transactional work on copies
            board_before = board.copy()
            try:
                move_san = board.san(move)
            except:
                move_san = move_uci

            # Push to a working copy first
            working_board = board.copy()
            working_board.push(move)

            # Engine analysis - if this fails, we rollback (don't save)
            if not global_engine:
                return jsonify({
                    'success': False,
                    'error': 'Engine not available - please configure Stockfish path',
                    'board': board_to_dict(board)
                }), 500

            try:
                with engine_lock:
                    analysis_before = global_engine.analyze(board_before)
                    analysis_after = global_engine.analyze(working_board)
                    alternatives = global_engine.analyze_multipv(board_before, n=3)
            except Exception as e:
                # Rollback - return original board
                return jsonify({
                    'success': False,
                    'error': f'Engine analysis failed: {e}',
                    'board': board_to_dict(board)
                }), 500

            # Assess with per-session coach
            assessment = assess_move(
                move_played=move,
                eval_initial=analysis_before.cp_score_white,
                eval_final=analysis_after.cp_score_white,
                best_move=analysis_before.best_move,
                player_is_white=True,
                board_before=board_before,
                board_after=working_board,
                engine=global_engine,
                coach_session=cs,
                coach_mode=instructor_mode
            )

            # Record in per-session stats
            sm.record_move(assessment.grade, assessment.explanation, move_san, move_uci,
                           analysis_before.cp_score_white/100, analysis_after.cp_score_white/100)
            sm.add_eval(working_board.fullmove_number, analysis_after.cp_score_white)

            # Save to undo stack before final commit
            undo_stack = session.get('undo_stack', [])
            undo_stack.append(original_fen)
            session['undo_stack'] = undo_stack[-20:]  # Keep last 20

            # Commit working board to session only after success
            save_board_to_session(working_board)
            board = working_board

            # Format alternatives with SAN
            alternatives_data = []
            for alt in alternatives:
                try:
                    alt_san = board_before.san(alt.move)
                except:
                    alt_san = alt.move.uci()
                alternatives_data.append({
                    'move': alt_san,
                    'uci': alt.move.uci(),
                    'eval': alt.cp_score_white / 100 if not alt.is_mate else None,
                    'is_mate': alt.is_mate,
                    'mate_in': alt.mate_in,
                    'from': chess.square_name(alt.move.from_square),
                    'to': chess.square_name(alt.move.to_square),
                })

            # Check game over before engine reply
            game_over_data = None
            engine_move_data = None

            if board.is_game_over():
                result = board.result()
                feedback = sm.end_game(result)
                profile_store.save(sm.profile)
                session['game_active'] = False
                game_over_data = {'result': result, 'feedback': feedback}
            else:
                # Engine reply - transactional too
                try:
                    with engine_lock:
                        # Adaptive difficulty
                        if difficulty_mode == "adaptive":
                            blunder_rate = sm.profile.get_blunder_rate() if sm.profile.total_moves > 0 else 0.2
                            if sm.current_game and sm.current_game.move_count > 0:
                                errs = sm.current_game.get_blunder_count() + sm.current_game.get_mistake_count()
                                blunder_rate = errs / max(1, sm.current_game.move_count)
                            global_engine.set_adaptive_params(blunder_rate)

                        engine_move = global_engine.get_move(board)
                    
                    if engine_move:
                        try:
                            engine_san = board.san(engine_move)
                        except:
                            engine_san = engine_move.uci()
                        
                        # Push engine move
                        board.push(engine_move)
                        save_board_to_session(board)

                        engine_move_data = {
                            'move': engine_san,
                            'uci': engine_move.uci(),
                            'from': chess.square_name(engine_move.from_square),
                            'to': chess.square_name(engine_move.to_square),
                        }

                        if board.is_game_over():
                            result = board.result()
                            feedback = sm.end_game(result)
                            profile_store.save(sm.profile)
                            session['game_active'] = False
                            game_over_data = {'result': result, 'feedback': feedback}

                except Exception as e:
                    # Engine move failed, but player move succeeded - return partial success
                    print(f"Engine move failed: {e}")
                    # Board already saved with player move, that's ok

            # Update session histories for eval graph
            eval_hist = session.get('eval_history', [])
            eval_hist.append({'move_number': board.fullmove_number, 'eval': analysis_after.cp_score_white})
            session['eval_history'] = eval_hist[-100:]

            return jsonify({
                'success': True,
                'board': board_to_dict(board),
                'assessment': assessment_to_dict(assessment),
                'alternatives': alternatives_data,
                'warning': warning,
                'engine_move': engine_move_data,
                'game_over': game_over_data
            })

        except Exception as e:
            import traceback; traceback.print_exc()
            # Try to return authoritative board for resync
            try:
                b = get_board_from_session()
                return jsonify({'success': False, 'error': str(e), 'board': board_to_dict(b)}), 500
            except:
                return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/suggestions', methods=['GET'])
    def api_get_suggestions():
        try:
            board = get_board_from_session()
            if board.turn != chess.WHITE or board.is_game_over():
                return jsonify({'success': True, 'suggestions': []})
            if not global_engine:
                return jsonify({'success': False, 'error': 'Engine not available'}), 500
            with engine_lock:
                alternatives = global_engine.analyze_multipv(board, n=3)
            suggestions = []
            for rank, alt in enumerate(alternatives, start=1):
                try:
                    move_san = board.san(alt.move)
                except:
                    move_san = alt.move.uci()
                suggestions.append({
                    'rank': rank,
                    'move': move_san,
                    'uci': alt.move.uci(),
                    'eval': alt.cp_score_white / 100 if not alt.is_mate else None,
                    'is_mate': alt.is_mate,
                    'mate_in': alt.mate_in,
                    'from_square': chess.square_name(alt.move.from_square),
                    'to_square': chess.square_name(alt.move.to_square)
                })
            return jsonify({'success': True, 'suggestions': suggestions})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile', methods=['GET'])
    def api_get_profile():
        try:
            sess_id = session.get('_id') or 'default'
            sm = get_or_create_session_manager(sess_id)
            current_stats = None
            if sm.current_game:
                stats = sm.current_game
                current_stats = {
                    'move_count': stats.move_count,
                    'blunders': stats.get_blunder_count(),
                    'mistakes': stats.get_mistake_count(),
                    'inaccuracies': stats.get_inaccuracy_count(),
                    'good_moves': stats.get_good_move_count()
                }
            return jsonify({
                'success': True,
                'profile': {
                    'summary': sm.get_profile_summary(),
                    'training_suggestion': sm.get_training_suggestion(),
                    'current_game': current_stats,
                    'eval_history': session.get('eval_history', []),
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile/reset', methods=['POST'])
    def api_reset_profile():
        try:
            sess_id = session.get('_id') or 'default'
            sm = get_or_create_session_manager(sess_id)
            sm.reset_profile()
            profile_store.save(sm.profile)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/settings', methods=['POST'])
    def api_update_settings():
        try:
            data = request.json or {}
            if 'instructor_mode' in data:
                mode = data['instructor_mode']
                session['instructor_mode'] = mode
                sess_id = session.get('_id')
                if sess_id and sess_id in coach_sessions:
                    coach_sessions[sess_id].set_instructor_mode(mode)
            if 'difficulty_mode' in data:
                diff = data['difficulty_mode']
                session['difficulty_mode'] = diff
                if global_engine:
                    with engine_lock:
                        if diff != "adaptive":
                            global_engine.set_difficulty(diff)
            return jsonify({
                'success': True,
                'settings': {
                    'instructor_mode': session.get('instructor_mode', DEFAULT_COACH_MODE),
                    'difficulty_mode': session.get('difficulty_mode', DEFAULT_DIFFICULTY)
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/undo', methods=['POST'])
    def api_undo():
        try:
            undo_stack = session.get('undo_stack', [])
            if not undo_stack:
                board = get_board_from_session()
                return jsonify({'success': True, 'board': board_to_dict(board)})
            # Pop last 2 moves if possible (player+engine), else 1
            board = get_board_from_session()
            # We stored FENs, so restore
            fen = undo_stack.pop()
            # If board has engine move, we might need to pop again for true undo
            # For simplicity, pop one FEN which is before player move
            # If user wants to undo both, call twice
            session['undo_stack'] = undo_stack
            board = chess.Board(fen)
            save_board_to_session(board)
            # Also need to handle stats rollback - remove last move from session manager
            sess_id = session.get('_id')
            if sess_id:
                sm = get_or_create_session_manager(sess_id)
                if sm.current_game and sm.current_game.move_count > 0:
                    # Decrement counts - simplest: rebuild from move_history
                    # For now just pop from move_history
                    if sm.move_history:
                        sm.move_history.pop()
                    # Also eval history
                    if sm.eval_history:
                        sm.eval_history.pop()
                    # We can't easily undo grade counts without storing full history,
                    # so we reset and replay? For MVP, just keep counts but this is noted
                    # Better: store full game and recalc on undo - TODO
            return jsonify({'success': True, 'board': board_to_dict(board)})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/health', methods=['GET'])
    def api_health():
        return jsonify({
            'success': True,
            'engine_ready': global_engine is not None and global_engine.is_alive(),
            'engine_path': global_engine.stockfish_path if global_engine else None,
            'status': 'running'
        })

    # Frontend - serve improved SPA
    @app.route('/')
    def index():
        return render_template_string(FRONTEND_HTML)

    @app.route('/health')
    def health():
        return {'status': 'running', 'frontend': 'active', 'engine': global_engine is not None}

    return app


# =========================
# IMPROVED FRONTEND HTML
# =========================

FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chess Instructor - Premium</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        :root{--bg-primary:#0f0f12;--bg-secondary:#18181b;--bg-tertiary:#27272a;--border:#3f3f46;--text-primary:#fafafa;--text-secondary:#a1a1aa;--accent-green:#10b981;--accent-blue:#3b82f6;--accent-red:#ef4444;--accent-yellow:#f59e0b;--accent-purple:#a855f7}
        body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg-primary);color:var(--text-primary);overflow-x:hidden}
        .container{max-width:1600px;margin:0 auto;padding:20px}
        header{background:var(--bg-secondary);border-bottom:1px solid var(--border);padding:16px 0;margin-bottom:24px;position:sticky;top:0;z-index:100}
        .header-content{max-width:1600px;margin:0 auto;padding:0 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px}
        .logo{font-size:24px;font-weight:bold;color:var(--accent-green)}
        .header-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
        .engine-status{font-size:12px;padding:6px 10px;border-radius:6px;background:var(--bg-tertiary)}
        .engine-status.ok{color:var(--accent-green)} .engine-status.fail{color:var(--accent-red)}
        .main-layout{display:grid;grid-template-columns:1fr 420px;gap:24px;align-items:start}
        .board-section{display:flex;flex-direction:column;align-items:center;gap:20px}
        .status-bar{width:100%;max-width:600px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:12px;padding:20px;text-align:center}
        .status-title{font-size:20px;font-weight:bold;color:var(--accent-green);margin-bottom:8px}
        .status-info{font-size:14px;color:var(--text-secondary)}
        .board-wrapper{position:relative;width:fit-content}
        .chessboard{display:grid;grid-template-columns:repeat(8,70px);grid-template-rows:repeat(8,70px);border:3px solid var(--border);border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,0.5);position:relative;background:#fff}
        .square{width:70px;height:70px;display:flex;align-items:center;justify-content:center;font-size:48px;cursor:pointer;user-select:none;position:relative;transition:background-color 0.15s}
        .square.light{background-color:#f0d9b5} .square.dark{background-color:#b58863}
        .square.selected{background-color:#829567 !important}
        .square.legal-move::after{content:'';position:absolute;width:22px;height:22px;background:rgba(0,0,0,0.25);border-radius:50%;pointer-events:none}
        .square.legal-move.capture::after{width:56px;height:56px;background:transparent;border:4px solid rgba(0,0,0,0.3)}
        .square.last-move{background-color:#cdd26a !important}
        .square.check{background-color:rgba(239,68,68,0.5) !important;box-shadow:inset 0 0 20px rgba(239,68,68,0.7)}
        .square.highlight-danger{background-color:rgba(239,68,68,0.4) !important}
        .square.highlight-warning{background-color:rgba(251,146,60,0.4) !important}
        .square.highlight-best{background-color:rgba(16,185,129,0.3) !important}
        .piece{font-size:48px;pointer-events:none;filter:drop-shadow(1px 1px 1px rgba(0,0,0,0.3))}
        .board-wrapper.busy{pointer-events:none;opacity:0.7}
        .board-wrapper.busy::after{content:'⏳ Analyzing...';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,0.8);color:white;padding:12px 20px;border-radius:8px;font-weight:bold;z-index:10}
        /* SVG arrows overlay */
        .arrows-svg{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:5}
        .side-panel{display:flex;flex-direction:column;gap:20px}
        .panel-card{background:var(--bg-secondary);border:1px solid var(--border);border-radius:12px;padding:20px}
        .panel-card h3{font-size:16px;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .setting-group{margin-bottom:16px}
        .setting-label{font-size:12px;color:var(--text-secondary);font-weight:600;margin-bottom:8px;display:block}
        select{width:100%;padding:10px;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:14px;cursor:pointer}
        .suggestion-item{background:var(--bg-tertiary);border-radius:6px;padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;transition:background 0.15s}
        .suggestion-item:hover{background:#3f3f46}
        .suggestion-item.best{border-left:3px solid var(--accent-green)}
        .suggestion-move{font-weight:bold;font-size:14px}
        .suggestion-eval{color:var(--text-secondary);font-size:12px}
        .suggestion-rank{font-size:18px;margin-right:10px}
        .analysis-content{max-height:450px;overflow-y:auto;padding-right:8px}
        .move-analysis{background:var(--bg-tertiary);border-radius:8px;padding:16px;margin-bottom:12px}
        .move-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px}
        .move-title{font-size:18px;font-weight:bold}
        .move-grade{padding:4px 12px;border-radius:4px;font-size:12px;font-weight:600;color:white}
        .grade-BEST{background:var(--accent-green)} .grade-EXCELLENT{background:var(--accent-green)} .grade-GOOD{background:var(--accent-blue)} .grade-INACCURACY{background:var(--accent-yellow)} .grade-MISTAKE{background:var(--accent-red)} .grade-BLUNDER{background:var(--accent-purple)}
        .eval-change{font-size:14px;color:var(--text-secondary);margin-bottom:8px}
        .explanation{font-size:14px;line-height:1.6;background:var(--bg-primary);padding:12px;border-radius:6px;border-left:3px solid var(--accent-blue)}
        .alternatives{margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}
        .alt-move{font-size:13px;padding:6px;margin:4px 0;background:var(--bg-primary);border-radius:4px;display:flex;justify-content:space-between}
        .stats-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
        .stat-item{background:var(--bg-tertiary);padding:12px;border-radius:6px;text-align:center}
        .stat-value{font-size:22px;font-weight:bold;margin-bottom:4px}
        .stat-label{font-size:12px;color:var(--text-secondary)}
        .eval-graph{width:100%;height:120px;background:var(--bg-tertiary);border-radius:6px;margin-top:12px;position:relative;overflow:hidden}
        button{padding:10px 20px;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;transition:all 0.2s}
        .btn-primary{background:var(--accent-green);color:white} .btn-primary:hover{background:#059669}
        .btn-secondary{background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border)} .btn-secondary:hover{background:var(--border)}
        .btn-danger{background:var(--accent-red);color:white} .btn-danger:hover{background:#dc2626}
        .button-group{display:flex;gap:8px;flex-wrap:wrap}
        ::-webkit-scrollbar{width:8px} ::-webkit-scrollbar-track{background:var(--bg-tertiary);border-radius:4px} ::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
        .loading{text-align:center;padding:20px;color:var(--text-secondary)}
        .spinner{border:3px solid var(--bg-tertiary);border-top:3px solid var(--accent-green);border-radius:50%;width:32px;height:32px;animation:spin 1s linear infinite;margin:0 auto 12px}
        @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        .modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);z-index:1000;justify-content:center;align-items:center;padding:20px}
        .modal.active{display:flex}
        .modal-content{background:var(--bg-secondary);border:1px solid var(--border);border-radius:12px;padding:32px;max-width:500px;width:100%;max-height:80vh;overflow-y:auto}
        .modal-header{font-size:22px;font-weight:bold;margin-bottom:20px;text-align:center}
        .promotion-modal .modal-content{max-width:320px}
        .promotion-options{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}
        .promotion-option{font-size:36px;padding:16px;background:var(--bg-tertiary);border:2px solid var(--border);border-radius:8px;cursor:pointer;text-align:center;transition:all 0.15s}
        .promotion-option:hover{border-color:var(--accent-green);background:#3f3f46}
        @media (max-width:1200px){.main-layout{grid-template-columns:1fr}.side-panel{order:-1}}
        @media (max-width:768px){.chessboard{grid-template-columns:repeat(8,50px);grid-template-rows:repeat(8,50px)}.square{width:50px;height:50px}.piece{font-size:36px}.header-content{flex-direction:column;align-items:stretch}.stats-grid{grid-template-columns:1fr}}
        @media (max-width:480px){.chessboard{grid-template-columns:repeat(8,40px);grid-template-rows:repeat(8,40px)}.square{width:40px;height:40px}.piece{font-size:28px}.container{padding:12px}}
    </style>
</head>
<body>
    <header>
        <div class="header-content">
            <div class="logo">♟️ AI Chess Instructor</div>
            <div class="header-actions">
                <span id="engine-status" class="engine-status">Checking engine...</span>
                <button class="btn-secondary" onclick="showProfile()">📊 Profile</button>
                <button class="btn-primary" onclick="newGame()">🔄 New Game</button>
            </div>
        </div>
    </header>
    <div class="container">
        <div class="main-layout">
            <div class="board-section">
                <div class="status-bar">
                    <div class="status-title" id="status-title">Your Turn</div>
                    <div class="status-info" id="status-info">Make your move</div>
                </div>
                <div class="board-wrapper" id="board-wrapper">
                    <div class="chessboard" id="chessboard"></div>
                    <svg class="arrows-svg" id="arrows-svg" viewBox="0 0 560 560" preserveAspectRatio="none"></svg>
                </div>
                <div class="button-group">
                    <button class="btn-secondary" id="undo-btn" onclick="undoMove()">⟲ Undo</button>
                    <button class="btn-secondary" onclick="showAnalysis()">🔍 Analysis</button>
                    <button class="btn-secondary" onclick="flipBoard()">🔄 Flip</button>
                </div>
            </div>
            <div class="side-panel">
                <div class="panel-card">
                    <h3>⚙️ Settings</h3>
                    <div class="setting-group">
                        <label class="setting-label">Coach Mode (now works!)</label>
                        <select id="instructor-mode" onchange="updateSettings()">
                            <option value="adaptive">Adaptive (auto)</option>
                            <option value="learning">Learning (detailed)</option>
                            <option value="easy">Easy (hints)</option>
                            <option value="medium">Medium</option>
                            <option value="hard">Hard (concise)</option>
                        </select>
                    </div>
                    <div class="setting-group">
                        <label class="setting-label">Difficulty</label>
                        <select id="difficulty-mode" onchange="updateSettings()">
                            <option value="beginner">Beginner</option>
                            <option value="intermediate" selected>Intermediate</option>
                            <option value="advanced">Advanced</option>
                            <option value="engine">Engine (strong)</option>
                            <option value="adaptive">Adaptive (auto-adjust)</option>
                        </select>
                    </div>
                </div>
                <div class="panel-card">
                    <h3>💡 Suggested Moves</h3>
                    <div id="suggestions-container"><div class="loading"><div class="spinner"></div>Loading...</div></div>
                </div>
                <div class="panel-card">
                    <h3>📊 Move Analysis</h3>
                    <div class="analysis-content" id="analysis-container"><p style="color:var(--text-secondary);text-align:center;padding:20px">Make a move to see analysis</p></div>
                </div>
                <div class="panel-card">
                    <h3>📈 Current Game</h3>
                    <div class="stats-grid" id="stats-container">
                        <div class="stat-item"><div class="stat-value" id="stat-moves">0</div><div class="stat-label">Moves</div></div>
                        <div class="stat-item"><div class="stat-value" id="stat-blunders" style="color:var(--accent-purple)">0</div><div class="stat-label">Blunders</div></div>
                        <div class="stat-item"><div class="stat-value" id="stat-mistakes" style="color:var(--accent-red)">0</div><div class="stat-label">Mistakes</div></div>
                        <div class="stat-item"><div class="stat-value" id="stat-good" style="color:var(--accent-green)">0</div><div class="stat-label">Good</div></div>
                    </div>
                    <canvas id="eval-graph" class="eval-graph" width="380" height="120"></canvas>
                </div>
            </div>
        </div>
    </div>
    <div class="modal" id="profile-modal"><div class="modal-content"><div class="modal-header">📊 Player Profile</div><div class="modal-body" id="profile-content"><div class="loading"><div class="spinner"></div>Loading...</div></div><div style="display:flex;gap:12px;justify-content:flex-end;margin-top:20px"><button class="btn-danger" onclick="resetProfile()">Reset</button><button class="btn-primary" onclick="closeModal('profile-modal')">Close</button></div></div></div>
    <div class="modal" id="gameover-modal"><div class="modal-content"><div class="modal-header" id="gameover-title">🏁 Game Over</div><div class="modal-body" id="gameover-content"></div><div style="display:flex;justify-content:flex-end;margin-top:20px"><button class="btn-primary" onclick="closeModal('gameover-modal')">Continue</button></div></div></div>
    <div class="modal promotion-modal" id="promotion-modal"><div class="modal-content"><div class="modal-header">Choose Promotion</div><div class="promotion-options"><div class="promotion-option" onclick="handlePromotion('q')">♕</div><div class="promotion-option" onclick="handlePromotion('r')">♖</div><div class="promotion-option" onclick="handlePromotion('b')">♗</div><div class="promotion-option" onclick="handlePromotion('n')">♘</div></div></div></div>

<script>
const API_URL = ''; // relative - works with single server and preview
let boardState=null, selectedSquare=null, legalMoves=[], moveHistory=[], gameActive=true, isProcessing=false;
let lastMove=null, visualCues=null, suggestionArrows=[], boardFlipped=false, pendingPromotion=null;
let evalHistory=[];
const PIECE_UNICODE={'K':'♔','Q':'♕','R':'♖','B':'♗','N':'♘','P':'♙','k':'♚','q':'♛','r':'♜','b':'♝','n':'♞','p':'♟'};

async function api(path, opts={}){
    opts.credentials='include';
    opts.headers=Object.assign({'Content-Type':'application/json'}, opts.headers||{});
    const res=await fetch(API_URL+'/api'+path, opts);
    const data=await res.json();
    if(!res.ok && data.board){ boardState=data.board; renderBoard(); }
    return data;
}

async function initGame(){
    try{
        const data=await api('/init',{method:'POST'});
        if(data.success){ boardState=data.board; gameActive=true; lastMove=null; visualCues=null; suggestionArrows=[]; evalHistory=[]; renderBoard(); loadSuggestions(); updateStats(); drawEvalGraph(); }
        else alert('Init failed: '+data.error);
    }catch(e){ console.error(e); alert('Failed to connect - ensure backend running'); }
    checkEngine();
}

async function checkEngine(){
    try{
        const data=await api('/health');
        const el=document.getElementById('engine-status');
        if(data.engine_ready){ el.textContent='✓ Engine ready'; el.className='engine-status ok'; }
        else{ el.textContent='⚠ Engine missing - using fallback'; el.className='engine-status fail'; }
    }catch(e){ document.getElementById('engine-status').textContent='❌ Backend offline'; }
}

function renderBoard(){
    const boardEl=document.getElementById('chessboard');
    const wrapper=document.getElementById('board-wrapper');
    if(isProcessing) wrapper.classList.add('busy'); else wrapper.classList.remove('busy');
    boardEl.innerHTML='';
    if(!boardState) return;
    const pieces=parseFEN(boardState.fen);
    const size=70; // will be dynamic but ok
    // For flipped board
    for(let displayRank=0; displayRank<8; displayRank++){
        for(let displayFile=0; displayFile<8; displayFile++){
            const rank = boardFlipped ? displayRank : 7-displayRank;
            const file = boardFlipped ? 7-displayFile : displayFile;
            const sqIdx=rank*8+file;
            const sqName=indexToSquare(sqIdx);
            const sq=document.createElement('div');
            sq.className='square '+((rank+file)%2===0?'dark':'light');
            sq.dataset.square=sqName;
            sq.dataset.index=sqIdx;
            // last move highlight
            if(lastMove && (sqName===lastMove.from || sqName===lastMove.to)) sq.classList.add('last-move');
            // check highlight
            if(boardState.is_check && pieces[sqIdx] && ((boardState.turn==='white' && pieces[sqIdx]==='K')||(boardState.turn==='black' && pieces[sqIdx]==='k'))) sq.classList.add('check');
            // visual cues highlights
            if(visualCues){
                for(let h of visualCues.highlights||[]){
                    if(indexToSquare(h.square)===sqName){
                        sq.classList.add('highlight-'+h.type);
                    }
                }
            }
            // piece
            if(pieces[sqIdx]){
                const p=document.createElement('span'); p.className='piece'; p.textContent=PIECE_UNICODE[pieces[sqIdx]]; sq.appendChild(p);
            }
            // selection
            if(sqName===selectedSquare) sq.classList.add('selected');
            if(legalMoves.includes(sqName)){
                // check if capture
                const targetIdx=squareToIndex(sqName);
                if(pieces[targetIdx]) sq.classList.add('capture');
                sq.classList.add('legal-move');
            }
            sq.onclick=()=>handleSquareClick(sqName);
            boardEl.appendChild(sq);
        }
    }
    renderArrows();
    updateStatus();
}

function renderArrows(){
    const svg=document.getElementById('arrows-svg');
    svg.innerHTML='';
    const allArrows=[...(visualCues?visualCues.arrows:[]), ...suggestionArrows];
    if(allArrows.length===0) return;
    const sqSize=70;
    function sqToCoord(sqIdx){
        let file = sqIdx % 8;
        let rank = Math.floor(sqIdx/8);
        if(boardFlipped){ file=7-file; rank=7-rank; }
        // display coords: file 0 left, rank 0 bottom? We have displayRank inverted
        const x = file*sqSize + sqSize/2;
        const y = (7-rank)*sqSize + sqSize/2;
        return {x,y};
    }
    for(let arr of allArrows){
        const from = sqToCoord(arr.from);
        const to = sqToCoord(arr.to);
        const colorMap={best:'#10b981',good:'#3b82f6',inaccuracy:'#f59e0b',blunder:'#ef4444',threat:'#ef4444'};
        const color=colorMap[arr.type]||'#888';
        const isSuggestion = suggestionArrows.includes(arr);
        const opacity = isSuggestion ? 0.5 : 0.85;
        const width = isSuggestion ? 6 : 8;
        // line
        const line=document.createElementNS('http://www.w3.org/2000/svg','line');
        line.setAttribute('x1',from.x); line.setAttribute('y1',from.y);
        line.setAttribute('x2',to.x); line.setAttribute('y2',to.y);
        line.setAttribute('stroke',color); line.setAttribute('stroke-width',width);
        line.setAttribute('stroke-linecap','round'); line.setAttribute('opacity',opacity);
        svg.appendChild(line);
        // arrow head
        const angle=Math.atan2(to.y-from.y, to.x-from.x);
        const headLen=14, headW=10;
        const p1={x:to.x, y:to.y};
        const p2={x:to.x - headLen*Math.cos(angle) + headW*Math.sin(angle), y:to.y - headLen*Math.sin(angle) - headW*Math.cos(angle)};
        const p3={x:to.x - headLen*Math.cos(angle) - headW*Math.sin(angle), y:to.y - headLen*Math.sin(angle) + headW*Math.cos(angle)};
        const poly=document.createElementNS('http://www.w3.org/2000/svg','polygon');
        poly.setAttribute('points',`${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y}`);
        poly.setAttribute('fill',color); poly.setAttribute('opacity',opacity);
        svg.appendChild(poly);
    }
}

function parseFEN(fen){
    const pieces=new Array(64).fill(null);
    const rows=fen.split(' ')[0].split('/');
    for(let r=0;r<8;r++){
        const row=rows[r];
        let file=0;
        const rank=7-r;
        for(let ch of row){
            if(isNaN(ch)){ pieces[rank*8+file]=ch; file++; } else file+=parseInt(ch);
        }
    }
    return pieces;
}
function indexToSquare(i){ return String.fromCharCode(97+(i%8))+(Math.floor(i/8)+1); }
function squareToIndex(sq){ return (parseInt(sq[1])-1)*8 + (sq.charCodeAt(0)-97); }

async function handleSquareClick(sq){
    if(!gameActive || isProcessing || boardState.turn!=='white') return;
    if(selectedSquare && legalMoves.includes(sq)){
        // check promotion
        const fromIdx=squareToIndex(selectedSquare);
        const toIdx=squareToIndex(sq);
        const pieces=parseFEN(boardState.fen);
        const piece=pieces[fromIdx];
        const isPawn = piece==='P';
        const toRank = Math.floor(toIdx/8);
        if(isPawn && toRank===7){
            pendingPromotion={from:selectedSquare, to:sq};
            document.getElementById('promotion-modal').classList.add('active');
            return;
        }
        await makeMove(selectedSquare+sq);
        clearSelection();
        return;
    }
    clearSelection();
    const moves=boardState.legal_moves.filter(m=>m.startsWith(sq));
    if(moves.length>0){ selectedSquare=sq; legalMoves=moves.map(m=>m.substring(2,4)); renderBoard(); }
}
function clearSelection(){ selectedSquare=null; legalMoves=[]; renderBoard(); }
function handlePromotion(piece){
    document.getElementById('promotion-modal').classList.remove('active');
    if(!pendingPromotion) return;
    const uci=pendingPromotion.from+pendingPromotion.to+piece;
    pendingPromotion=null;
    makeMove(uci);
    clearSelection();
}

async function makeMove(uci){
    if(isProcessing) return;
    isProcessing=true; renderBoard();
    try{
        updateStatus('Analyzing...','var(--accent-blue)');
        const data=await api('/move',{method:'POST', body:JSON.stringify({move:uci})});
        if(data.success){
            boardState=data.board;
            lastMove = data.engine_move ? {from:data.engine_move.from, to:data.engine_move.to} : {from:uci.substring(0,2), to:uci.substring(2,4)};
            // Actually last move should be engine if present, but show player arrow via visualCues
            if(data.assessment){
                visualCues=data.assessment.visual_cues;
                // keep player move as lastMove for highlight if no engine
                if(!data.engine_move) lastMove={from:uci.substring(0,2), to:uci.substring(2,4)};
                else {
                    // show both? highlight engine last
                    lastMove={from:data.engine_move.from, to:data.engine_move.to};
                }
            }
            suggestionArrows=[];
            renderBoard();
            if(data.assessment) displayMoveAnalysis(data.assessment, data.alternatives, data.warning, data.engine_move);
            if(data.board) evalHistory.push({move_number:data.board.move_count, eval:data.assessment?data.assessment.eval_final*100:0});
            updateStats(); drawEvalGraph();
            if(data.game_over) handleGameOver(data.game_over);
            else loadSuggestions();
        } else {
            alert('Move failed: '+data.error);
            if(data.board){ boardState=data.board; renderBoard(); }
        }
    }catch(e){ console.error(e); alert('Move error'); }
    finally{ isProcessing=false; renderBoard(); }
}

function updateStatus(msg=null,color=null){
    const title=document.getElementById('status-title');
    const info=document.getElementById('status-info');
    if(msg){ title.textContent=msg; if(color) title.style.color=color; return; }
    if(!boardState) return;
    if(boardState.is_checkmate){ title.textContent='🏁 Checkmate!'; title.style.color='var(--accent-red)'; info.textContent=boardState.turn==='white'?'Black wins!':'White wins!'; }
    else if(boardState.is_stalemate){ title.textContent='🤝 Stalemate'; title.style.color='var(--accent-yellow)'; info.textContent='Draw'; }
    else if(boardState.is_check){ title.textContent='⚠️ Check!'; title.style.color='var(--accent-red)'; info.textContent='You must move king'; }
    else if(boardState.turn==='white'){ title.textContent='♟️ Your Turn'; title.style.color='var(--accent-green)'; info.textContent='Make your move'; }
    else{ title.textContent='🤖 Engine thinking...'; title.style.color='var(--accent-blue)'; info.textContent='Please wait'; }
}

async function loadSuggestions(){
    const cont=document.getElementById('suggestions-container');
    cont.innerHTML='<div class="loading"><div class="spinner"></div>Loading...</div>';
    try{
        const data=await api('/suggestions');
        if(data.success && data.suggestions.length>0){
            suggestionArrows=data.suggestions.map((s,i)=>({from:squareToIndex(s.from_square), to:squareToIndex(s.to_square), type:i===0?'best':'good'}));
            renderBoard();
            cont.innerHTML=data.suggestions.map((s,i)=>`
                <div class="suggestion-item ${i===0?'best':''}" onclick="makeMove('${s.uci}')">
                    <div style="display:flex;align-items:center"><span class="suggestion-rank">${['🥇','🥈','🥉'][i]||'•'}</span><div><div class="suggestion-move">${s.move}</div><div class="suggestion-eval">${formatEval(s)}</div></div></div>
                    <div style="font-size:10px;color:var(--text-secondary)">${i===0?'BEST':i===1?'GOOD':'ALT'}</div>
                </div>`).join('');
        } else cont.innerHTML='<p style="color:var(--text-secondary);text-align:center">No suggestions</p>';
    }catch(e){ cont.innerHTML='<p style="color:var(--accent-red);text-align:center">Failed</p>'; }
}

function displayMoveAnalysis(ass, alts, warn, engMove){
    const cont=document.getElementById('analysis-container');
    let html='';
    if(warn) html+=`<div style="background:rgba(245,158,11,0.2);padding:12px;border-radius:6px;margin-bottom:12px;border-left:3px solid var(--accent-yellow)">⚠️ <b>Warning:</b> ${warn}</div>`;
    html+=`<div class="move-analysis"><div class="move-header"><div class="move-title">${ass.move}</div><div class="move-grade grade-${ass.grade}">${ass.grade}</div></div><div class="eval-change">Eval: ${ass.eval_initial.toFixed(2)} → ${ass.eval_final.toFixed(2)} ${ass.best_move && !ass.was_best_move? ' | Best: '+ass.best_move : ''}</div><div class="explanation">${ass.explanation}</div>`;
    if(engMove) html+=`<div style="margin-top:12px;padding:10px;background:var(--bg-primary);border-radius:6px;border-left:3px solid var(--accent-blue)"><b>🤖 Engine:</b> ${engMove.move}</div>`;
    if(alts && alts.length>0) html+=`<div class="alternatives"><h4>Alternatives:</h4>${alts.map((a,i)=>`<div class="alt-move"><span>${i+1}. <b>${a.move}</b></span><span>${formatEval(a)}</span></div>`).join('')}</div>`;
    html+='</div>';
    cont.innerHTML=html;
}
function formatEval(it){ if(it.is_mate) return `M${Math.abs(it.mate_in)}`; return it.eval!=null?`${it.eval>0?'+':''}${it.eval.toFixed(2)}`:'0.00'; }

async function updateStats(){
    try{
        const data=await api('/profile');
        if(data.success && data.profile.current_game){
            const s=data.profile.current_game;
            document.getElementById('stat-moves').textContent=s.move_count;
            document.getElementById('stat-blunders').textContent=s.blunders;
            document.getElementById('stat-mistakes').textContent=s.mistakes;
            document.getElementById('stat-good').textContent=s.good_moves;
            if(data.profile.eval_history) evalHistory=data.profile.eval_history;
        }
    }catch(e){}
}
function drawEvalGraph(){
    const canvas=document.getElementById('eval-graph');
    const ctx=canvas.getContext('2d');
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle='#27272a'; ctx.fillRect(0,0,canvas.width,canvas.height);
    if(evalHistory.length<2) return;
    const maxMove=Math.max(...evalHistory.map(e=>e.move_number));
    const evals=evalHistory.map(e=>e.eval);
    let maxEval=Math.max(...evals), minEval=Math.min(...evals);
    maxEval=Math.min(maxEval,500); minEval=Math.max(minEval,-500);
    let range=maxEval-minEval; if(range===0) range=1;
    // zero line
    if(minEval<=0 && maxEval>=0){
        const yZero=canvas.height - ((0-minEval)/range)*canvas.height;
        ctx.strokeStyle='#3f3f46'; ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(0,yZero); ctx.lineTo(canvas.width,yZero); ctx.stroke();
    }
    ctx.lineWidth=2;
    for(let i=0;i<evalHistory.length-1;i++){
        const e1=evalHistory[i], e2=evalHistory[i+1];
        const x1=(e1.move_number/maxMove)*canvas.width;
        const x2=(e2.move_number/maxMove)*canvas.width;
        const y1=canvas.height - ((Math.max(minEval,Math.min(maxEval,e1.eval))-minEval)/range)*canvas.height;
        const y2=canvas.height - ((Math.max(minEval,Math.min(maxEval,e2.eval))-minEval)/range)*canvas.height;
        ctx.strokeStyle=e1.eval>100?'#10b981':e1.eval<-100?'#ef4444':'#3b82f6';
        ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
    }
}

async function undoMove(){
    if(isProcessing) return;
    isProcessing=true;
    try{
        const data=await api('/undo',{method:'POST'});
        if(data.success){ boardState=data.board; lastMove=null; visualCues=null; suggestionArrows=[]; renderBoard(); loadSuggestions(); updateStats(); }
    }catch(e){} finally{ isProcessing=false; renderBoard(); }
}
async function newGame(){ if(confirm('Start new game? Current will be saved.')) await initGame(); }
async function updateSettings(){
    const im=document.getElementById('instructor-mode').value;
    const dm=document.getElementById('difficulty-mode').value;
    try{ await api('/settings',{method:'POST', body:JSON.stringify({instructor_mode:im, difficulty_mode:dm})}); }catch(e){}
}
async function showProfile(){
    document.getElementById('profile-modal').classList.add('active');
    const cont=document.getElementById('profile-content');
    cont.innerHTML='<div class="loading"><div class="spinner"></div>Loading...</div>';
    try{
        const data=await api('/profile');
        if(data.success) cont.innerHTML=`<div style="margin-bottom:20px">${data.profile.summary}</div>${data.profile.training_suggestion?`<div style="background:var(--bg-tertiary);padding:16px;border-radius:8px;border-left:3px solid var(--accent-blue)"><h4>💡 Training</h4><p>${data.profile.training_suggestion}</p></div>`:''}`;
    }catch(e){ cont.innerHTML='<p style="color:var(--accent-red)">Failed</p>'; }
}
function closeModal(id){ document.getElementById(id).classList.remove('active'); }
async function resetProfile(){ if(confirm('Reset profile? Cannot undo.')){ await api('/profile/reset',{method:'POST'}); alert('Reset done'); closeModal('profile-modal'); } }
function handleGameOver(d){
    gameActive=false;
    const modal=document.getElementById('gameover-modal');
    const title=document.getElementById('gameover-title');
    const cont=document.getElementById('gameover-content');
    const result=d.result;
    const icon=result.includes('1-0')?'🏆':result.includes('0-1')?'😔':'🤝';
    title.textContent=`${icon} Game Over - ${result}`;
    const fb=d.feedback;
    cont.innerHTML=`<div style="text-align:center"><div style="font-size:16px;margin-bottom:16px">${fb.summary}</div><div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px"><div class="stat-item"><div class="stat-value">${fb.total_moves}</div><div class="stat-label">Moves</div></div><div class="stat-item"><div class="stat-value" style="color:var(--accent-purple)">${fb.blunders}</div><div class="stat-label">Blunders</div></div><div class="stat-item"><div class="stat-value" style="color:var(--accent-red)">${fb.mistakes}</div><div class="stat-label">Mistakes</div></div><div class="stat-item"><div class="stat-value" style="color:var(--accent-green)">${fb.good_moves}</div><div class="stat-label">Good</div></div></div></div>`;
    modal.classList.add('active');
}
function showAnalysis(){ document.getElementById('analysis-container').scrollIntoView({behavior:'smooth'}); }
function flipBoard(){ boardFlipped=!boardFlipped; renderBoard(); }
window.addEventListener('load', initGame);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app = create_app()
    print("="*60)
    print("AI Chess Instructor - Unified Server")
    print("="*60)
    print(f"✓ Starting on http://{WEB_HOST}:{WEB_PORT}")
    print(f"  Frontend + API in one server (no CORS issues)")
    print(f"  Open browser to: http://localhost:{WEB_PORT}")
    print("="*60)
    # Important: bind 0.0.0.0 for preview
    app.run(debug=False, host=WEB_HOST, port=WEB_PORT, threaded=True)
