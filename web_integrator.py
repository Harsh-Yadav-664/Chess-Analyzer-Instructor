"""
web_integrator.py
Backend connector for AI Chess Instructor web interface.

Provides Flask API endpoints that connect to existing engine, instructor, and stats modules.
Handles all chess logic, analysis, and persistence for the web frontend.
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import chess
import chess.pgn
from datetime import datetime
import os
import secrets
from pathlib import Path
import json

# Import existing backend modules
from engine import ChessEngine
from instructor import (
    assess_move,
    analyze_pre_move_threats,
    reset_adaptive_state,
    get_current_mode,
    MoveGrade
)
from stats import (
    start_game,
    record_move,
    end_game,
    get_profile_summary,
    get_training_suggestion,
    reset_profile,
    get_session
)

# =========================
# CONFIGURATION
# =========================

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = Path.home() / '.chess_instructor' / 'sessions'
app.config['SESSION_PERMANENT'] = False

# Ensure session directory exists
app.config['SESSION_FILE_DIR'].mkdir(parents=True, exist_ok=True)

Session(app)
CORS(app, supports_credentials=True)

# Engine configuration
STOCKFISH_PATH = r"D:\CODE\PROJECTS\Chess Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe"
ENGINE_DEPTH = 15

# Global engine instance (shared across all sessions)
global_engine = None

# Profile storage
PROFILE_DIR = Path.home() / ".chess_instructor"
PROFILE_FILE = PROFILE_DIR / "web_profile.json"


# =========================
# ENGINE INITIALIZATION
# =========================

def init_engine():
    """Initialize the global Stockfish engine."""
    global global_engine
    try:
        global_engine = ChessEngine(STOCKFISH_PATH, depth=ENGINE_DEPTH)
        global_engine.start()
        print("✓ Engine initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to initialize engine: {e}")
        return False


# =========================
# HELPER FUNCTIONS
# =========================

def get_board_from_session():
    """Get current board state from session."""
    fen = session.get('board_fen', chess.STARTING_FEN)
    return chess.Board(fen)


def save_board_to_session(board):
    """Save board state to session."""
    session['board_fen'] = board.fen()


def get_session_data(key, default=None):
    """Get data from session with default."""
    return session.get(key, default)


def set_session_data(key, value):
    """Set data in session."""
    session[key] = value


def board_to_dict(board):
    """Convert board to JSON-friendly dictionary."""
    return {
        'fen': board.fen(),
        'turn': 'white' if board.turn == chess.WHITE else 'black',
        'is_check': board.is_check(),
        'is_checkmate': board.is_checkmate(),
        'is_stalemate': board.is_stalemate(),
        'is_game_over': board.is_game_over(),
        'legal_moves': [move.uci() for move in board.legal_moves],
        'move_count': board.fullmove_number,
    }


def move_assessment_to_dict(assessment):
    """Convert MoveAssessment to dictionary."""
    return {
        'move': assessment.move_played.uci(),
        'grade': assessment.grade.name,
        'grade_value': int(assessment.grade),
        'eval_initial': assessment.eval_initial / 100,
        'eval_final': assessment.eval_final / 100,
        'centipawn_loss': assessment.centipawn_loss,
        'best_move': assessment.best_move.uci() if assessment.best_move else None,
        'was_best_move': assessment.was_best_move,
        'explanation': assessment.explanation,
        'visual_cues': assessment.visual_cues,
    }


def save_web_profile():
    """Save profile to disk (web-specific file)."""
    try:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        session_obj = get_session()
        data = session_obj.profile.to_dict()
        with open(PROFILE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Failed to save profile: {e}")
        return False


def load_web_profile():
    """Load profile from disk."""
    if not PROFILE_FILE.exists():
        return False
    try:
        with open(PROFILE_FILE, 'r') as f:
            data = json.load(f)
        from stats import PlayerProfile
        session_obj = get_session()
        session_obj.profile = PlayerProfile.from_dict(data)
        return True
    except Exception as e:
        print(f"Failed to load profile: {e}")
        return False


# =========================
# API ENDPOINTS
# =========================

@app.route('/api/init', methods=['POST'])
def api_init():
    """Initialize a new game session."""
    try:
        # Load profile if exists
        load_web_profile()
        
        # Reset board
        board = chess.Board()
        save_board_to_session(board)
        
        # Reset game state
        set_session_data('game_active', True)
        set_session_data('move_history', [])
        set_session_data('eval_history', [])
        set_session_data('instructor_mode', 'adaptive')
        set_session_data('difficulty_mode', 'intermediate')
        
        # Start new game in stats
        start_game()
        reset_adaptive_state()
        
        # Set engine difficulty
        if global_engine:
            global_engine.set_difficulty('intermediate')
        
        return jsonify({
            'success': True,
            'board': board_to_dict(board),
            'message': 'Game initialized successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/board', methods=['GET'])
def api_get_board():
    """Get current board state."""
    try:
        board = get_board_from_session()
        return jsonify({
            'success': True,
            'board': board_to_dict(board)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/move', methods=['POST'])
def api_make_move():
    """Make a move and get analysis."""
    try:
        data = request.json
        move_uci = data.get('move')
        
        if not move_uci:
            return jsonify({'success': False, 'error': 'No move provided'}), 400
        
        board = get_board_from_session()
        
        # Validate move
        try:
            move = chess.Move.from_uci(move_uci)
        except:
            return jsonify({'success': False, 'error': 'Invalid move format'}), 400
        
        if move not in board.legal_moves:
            return jsonify({'success': False, 'error': 'Illegal move'}), 400
        
        # Get pre-move warning
        instructor_mode = get_session_data('instructor_mode', 'adaptive')
        warning = analyze_pre_move_threats(board, chess.WHITE, instructor_mode)
        
        # Save state before move
        board_before = board.copy()
        move_san = board.san(move)
        
        # Make the move
        board.push(move)
        save_board_to_session(board)
        
        # Analyze the move
        if not global_engine:
            return jsonify({'success': False, 'error': 'Engine not available'}), 500
        
        analysis_before = global_engine.analyze(board_before)
        analysis_after = global_engine.analyze(board)
        alternatives = global_engine.analyze_multipv(board_before, n=3)
        
        # Assess move quality
        assessment = assess_move(
            move_played=move,
            eval_initial=analysis_before.cp_score_white,
            eval_final=analysis_after.cp_score_white,
            best_move=analysis_before.best_move,
            player_is_white=True,
            board_before=board_before,
            board_after=board,
            engine=global_engine
        )
        
        # Record in stats
        record_move(assessment.grade, assessment.explanation)
        
        # Add to move history
        move_history = get_session_data('move_history', [])
        move_history.append({
            'move': move_san,
            'uci': move_uci,
            'grade': assessment.grade.name,
            'eval_before': analysis_before.cp_score_white / 100,
            'eval_after': analysis_after.cp_score_white / 100,
        })
        set_session_data('move_history', move_history)
        
        # Add to eval history
        eval_history = get_session_data('eval_history', [])
        eval_history.append({
            'move_number': board.fullmove_number,
            'eval': analysis_after.cp_score_white
        })
        set_session_data('eval_history', eval_history)
        
        # Format alternatives
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
                'mate_in': alt.mate_in
            })
        
        # Check if game over
        game_over_data = None
        if board.is_game_over():
            result = board.result()
            feedback = end_game(result)
            save_web_profile()
            set_session_data('game_active', False)
            
            game_over_data = {
                'result': result,
                'feedback': feedback
            }
        
        # Get engine move if game continues
        engine_move_data = None
        if not board.is_game_over():
            difficulty_mode = get_session_data('difficulty_mode', 'intermediate')
            engine_move = global_engine.get_move(board)
            
            if engine_move:
                engine_san = board.san(engine_move)
                board.push(engine_move)
                save_board_to_session(board)
                
                engine_move_data = {
                    'move': engine_san,
                    'uci': engine_move.uci()
                }
                
                # Check game over after engine move
                if board.is_game_over():
                    result = board.result()
                    feedback = end_game(result)
                    save_web_profile()
                    set_session_data('game_active', False)
                    
                    game_over_data = {
                        'result': result,
                        'feedback': feedback
                    }
        
        return jsonify({
            'success': True,
            'board': board_to_dict(board),
            'assessment': move_assessment_to_dict(assessment),
            'alternatives': alternatives_data,
            'warning': warning,
            'engine_move': engine_move_data,
            'game_over': game_over_data
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/suggestions', methods=['GET'])
def api_get_suggestions():
    """Get top move suggestions for current position."""
    try:
        board = get_board_from_session()
        
        if board.turn != chess.WHITE:
            return jsonify({'success': True, 'suggestions': []})
        
        if not global_engine:
            return jsonify({'success': False, 'error': 'Engine not available'}), 500
        
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
        
        return jsonify({
            'success': True,
            'suggestions': suggestions
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profile', methods=['GET'])
def api_get_profile():
    """Get player profile data."""
    try:
        profile_summary = get_profile_summary()
        training_suggestion = get_training_suggestion()
        
        session_obj = get_session()
        current_stats = None
        if session_obj.current_game:
            stats = session_obj.current_game
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
                'summary': profile_summary,
                'training_suggestion': training_suggestion,
                'current_game': current_stats
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profile/reset', methods=['POST'])
def api_reset_profile():
    """Reset player profile."""
    try:
        reset_profile()
        save_web_profile()
        
        return jsonify({
            'success': True,
            'message': 'Profile reset successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    """Update game settings."""
    try:
        data = request.json
        
        if 'instructor_mode' in data:
            set_session_data('instructor_mode', data['instructor_mode'])
        
        if 'difficulty_mode' in data:
            difficulty = data['difficulty_mode']
            set_session_data('difficulty_mode', difficulty)
            if global_engine:
                global_engine.set_difficulty(difficulty)
        
        return jsonify({
            'success': True,
            'settings': {
                'instructor_mode': get_session_data('instructor_mode'),
                'difficulty_mode': get_session_data('difficulty_mode')
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/undo', methods=['POST'])
def api_undo():
    """Undo last move (both player and engine)."""
    try:
        board = get_board_from_session()
        
        # Undo last 2 moves (player + engine)
        if len(board.move_stack) >= 2:
            board.pop()
            board.pop()
        elif len(board.move_stack) == 1:
            board.pop()
        
        save_board_to_session(board)
        
        return jsonify({
            'success': True,
            'board': board_to_dict(board)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/new-game', methods=['POST'])
def api_new_game():
    """Start a new game."""
    return api_init()


@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint."""
    return jsonify({
        'success': True,
        'engine_ready': global_engine is not None,
        'status': 'running'
    })


# =========================
# MAIN
# =========================

if __name__ == '__main__':
    print("=" * 50)
    print("AI Chess Instructor - Web Backend")
    print("=" * 50)
    
    # Initialize engine
    if init_engine():
        print("✓ Backend ready")
        print("✓ Starting Flask server...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    else:
        print("✗ Failed to start - engine initialization failed")
        print("  Please check STOCKFISH_PATH in web_integrator.py")