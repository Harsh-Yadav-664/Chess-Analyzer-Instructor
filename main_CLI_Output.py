# Game loop and CLI interface.

import chess
from engine import ChessEngine
from instructor import assess_move, MoveGrade


# =============================================================================
# CONFIGURATION — Stockfish location and engine info
# =============================================================================

STOCKFISH_PATH = r"D:\CODE\PROJECTS\Chess Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe"  # macOS Homebrew default

ENGINE_DEPTH = 15       # Analysis depth (15 is good balance of speed/quality)
ENGINE_MOVE_TIME = 1.0  # Seconds for engine to think when playing


# =============================================================================
# DISPLAY FUNCTIONS — All output logic here
# =============================================================================

# ANSI color codes for terminal
class Colors:
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


GRADE_COLORS = {
    MoveGrade.BEST: Colors.GREEN,
    MoveGrade.EXCELLENT: Colors.GREEN,
    MoveGrade.GOOD: Colors.BLUE,
    MoveGrade.INACCURACY: Colors.YELLOW,
    MoveGrade.MISTAKE: Colors.RED,
    MoveGrade.BLUNDER: Colors.MAGENTA,
}


def display_board(board: chess.Board) -> None:
    """Print the board with coordinates."""
    print()
    # unicode() gives nice piece symbols; borders=True adds rank/file labels
    print(board.unicode(borders=True))
    print()


def display_welcome() -> None:
    print("\n" + "=" * 55)
    print("-♔-  AI CHESS INSTRUCTOR — Phase 1 MVP  -♚-")
    print("=" * 55)
    print("  You play WHITE. Engine plays BLACK.")
    print("  Enter moves in UCI (e2e4) or SAN (e4, Nf3, O-O)")
    print("  Type 'quit' to exit, 'board' to redraw board")
    print("=" * 55 + "\n")


def display_assessment(board: chess.Board, assessment) -> None:
    """Print move assessment with color-coded grade."""
    # SAN conversion done here with correct board state (BEFORE the move)
    move_san = board.san(assessment.move_played)
    
    # Handle best_move being None
    if assessment.best_move is not None:
        best_move_san = board.san(assessment.best_move)
    else:
        best_move_san = None
    
    color = GRADE_COLORS.get(assessment.grade, "")
    
    print(f"\n{'─' * 55}")
    print(f"  Move played: {Colors.BOLD}{move_san}{Colors.RESET}")
    print(f"  Evaluation:  {assessment.eval_initial/100:+.2f}  →  {assessment.eval_final/100:+.2f}")
    print(f"  Grade:       {color}{assessment.grade.name}{Colors.RESET}")
    
    if not assessment.was_best_move and best_move_san is not None:
        print(f"  Best was:    {best_move_san}")
    
    print(f"\n  {assessment.explanation}")
    print(f"{'─' * 55}\n")


def display_engine_move(move_san: str) -> None:
    """Announce the engine's move."""
    print(f"\n  Engine plays: {Colors.BOLD}{move_san}{Colors.RESET}\n")


def display_game_over(board: chess.Board) -> None:
    """Print game result."""
    print("\n" + "=" * 55)
    print(f"  GAME OVER — {board.result()}")
    
    if board.is_checkmate():
        winner = "Black" if board.turn == chess.WHITE else "White"
        print(f"  {winner} wins by checkmate!")
    elif board.is_stalemate():
        print("  Draw by stalemate.")
    elif board.is_insufficient_material():
        print("  Draw by insufficient material.")
    elif board.can_claim_fifty_moves():
        print("  Draw by fifty-move rule.")
    
    print("=" * 55 + "\n")


# =============================================================================
# INPUT FUNCTIONS — All input logic here
# =============================================================================

def get_player_move(board: chess.Board) -> chess.Move:
    """
    Prompt player for a move and validate it.
    
    Accepts:
    - UCI format: e2e4, g1f3, e7e8q (promotion)
    - SAN format: e4, Nf3, O-O, e8=Q
    
    Returns: A legal chess.Move
    Raises: KeyboardInterrupt if player types 'quit'
    """
    while True:
        try:
            user_input = input("  Your move: ").strip()
        except EOFError:
            raise KeyboardInterrupt
        
        if not user_input:
            continue
        
        lower_input = user_input.lower()
        
        # Special commands
        if lower_input == "quit":
            raise KeyboardInterrupt
        if lower_input == "board":
            display_board(board)
            continue
        
        # Try parsing as UCI first (e2e4)
        try:
            move = chess.Move.from_uci(user_input)
            if move in board.legal_moves:
                return move
            else:
                print("  ⚠ Illegal move. Try again.")
                continue
        except ValueError:
            pass  # Not valid UCI, try SAN
        
        # Try parsing as SAN (e4, Nf3, O-O)
        try:
            move = board.parse_san(user_input)
            return move  # parse_san only returns legal moves
        except ValueError:
            pass
        
        print("  ⚠ Invalid format. Use e2e4 or Nf3. Type 'board' to see position.")


# =============================================================================
# GAME LOOP — How it works
# =============================================================================

def play_game(engine: ChessEngine) -> None:
    board = chess.Board()
    player_is_white = True  # For MVP, player is always White
    
    display_welcome()
    display_board(board)
    
    while not board.is_game_over():
        
        if board.turn == chess.WHITE:
            # === PLAYER'S TURN ===
            
            # 1. Analyze BEFORE player moves (to get best move + baseline eval)
            analysis_initial = engine.analyze(board)
            
            # 2. Get player's move
            player_move = get_player_move(board)
            
            # 3. Analyze position AFTER player's move
            #    (Use a copy so we don't modify board yet)
            board_copy = board.copy()
            board_copy.push(player_move)
            analysis_final = engine.analyze(board_copy)
            
            # 4. Generate assessment (no board needed, pure move/eval logic)
            assessment = assess_move(
                move_played=player_move,
                eval_initial=analysis_initial.cp_score_white,
                eval_final=analysis_final.cp_score_white,
                best_move=analysis_initial.best_move,
                player_is_white=player_is_white
            )
            
            # 5. Display assessment (pass board for SAN conversion)
            display_assessment(board, assessment)
            
            # 6. Now actually apply the move
            board.push(player_move)
            display_board(board)
        
        else:
            # === ENGINE'S TURN ===
            print("  Engine is thinking...")
            engine_move = engine.get_move(board, time_limit=ENGINE_MOVE_TIME)
            
            # Get SAN before pushing
            engine_move_san = board.san(engine_move)
            
            board.push(engine_move)
            display_engine_move(engine_move_san)
            display_board(board)
    
    display_game_over(board)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    print(f"\n  Starting Chess Instructor...")
    print(f"  Stockfish path: {STOCKFISH_PATH}")
    
    try:
        # 'with' ensures engine.stop() is called even if we crash
        with ChessEngine(STOCKFISH_PATH, depth=ENGINE_DEPTH) as engine:
            play_game(engine)
            
    except FileNotFoundError:
        print(f"\n  ❌ ERROR: Stockfish not found at '{STOCKFISH_PATH}'")
        print("  Please update STOCKFISH_PATH in main.py")
        print("  Download from: https://stockfishchess.org/download/\n")
        
    except KeyboardInterrupt:
        print("\n\n  Goodbye! 👋\n")


if __name__ == "__main__":
    main()