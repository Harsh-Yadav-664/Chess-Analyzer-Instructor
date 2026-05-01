"""
PHASE 2 — Tactical Awareness (Completed)

This module answers:
"WHY was this move bad?"

Design rules:
- No engine calls here
- No GUI logic
- Pure analysis using python-chess + eval numbers
- Tactical explanations override generic ones
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
import chess


# ---------------------------
# Grading scale (higher = better)
# ---------------------------
class MoveGrade(IntEnum):
    BLUNDER = 1
    MISTAKE = 2
    INACCURACY = 3
    GOOD = 4
    EXCELLENT = 5
    BEST = 6


# ---------------------------
# Constants
# ---------------------------

# Mate scores from Stockfish are huge (±100000)
MATE_THRESHOLD = 50000

# Rough material values (centipawns)
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900
}


# ---------------------------
# Data container
# ---------------------------
@dataclass(frozen=True)
class MoveAssessment:
    move_played: chess.Move
    grade: MoveGrade
    eval_initial: int
    eval_final: int
    centipawn_loss: int
    best_move: Optional[chess.Move]
    was_best_move: bool
    explanation: str


# ---------------------------
# Core math helpers
# ---------------------------

def _calculate_centipawn_loss(eval_initial: int, eval_final: int, player_is_white: bool) -> int:
    # Positive = position got worse for the player
    return (eval_initial - eval_final) if player_is_white else (eval_final - eval_initial)


def _to_player_eval(cp_score_white: int, player_is_white: bool) -> int:
    # Convert White-POV eval to player perspective
    return cp_score_white if player_is_white else -cp_score_white


def _determine_grade(cp_loss: int, was_best_move: bool) -> MoveGrade:
    # BEST move always wins
    if was_best_move:
        return MoveGrade.BEST

    loss = max(0, cp_loss)

    # Mate-level collapse
    if loss >= MATE_THRESHOLD:
        return MoveGrade.BLUNDER

    if loss <= 10:
        return MoveGrade.EXCELLENT
    elif loss <= 25:
        return MoveGrade.GOOD
    elif loss <= 50:
        return MoveGrade.INACCURACY
    elif loss <= 100:
        return MoveGrade.MISTAKE
    else:
        return MoveGrade.BLUNDER


# ---------------------------
# PHASE 2 — Tactical Detectors
# ---------------------------

def _detect_missed_mate(eval_initial: int, eval_final: int) -> Optional[str]:
    # Player had a forced mate and lost it
    if abs(eval_initial) >= MATE_THRESHOLD and abs(eval_final) < MATE_THRESHOLD:
        return "You missed a forced checkmate."
    return None


def _detect_allowed_mate(board_after: chess.Board, eval_final: int, player_is_white: bool) -> Optional[str]:
    # Player allowed opponent to deliver mate
    losing_side = chess.WHITE if eval_final < 0 else chess.BLACK
    player_color = chess.WHITE if player_is_white else chess.BLACK

    if abs(eval_final) >= MATE_THRESHOLD and losing_side == player_color:
        return "You allowed a forced checkmate."
    return None


def _detect_hung_piece(board_before: chess.Board, board_after: chess.Board, player_color: chess.Color) -> Optional[str]:
    # Detect newly hung piece (attacked, undefended, newly exposed)

    opponent = not player_color

    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece is None or piece.color != player_color:
            continue

        attacked = board_after.is_attacked_by(opponent, square)
        defended = board_after.is_attacked_by(player_color, square)
        was_attacked_before = board_before.is_attacked_by(opponent, square)

        if attacked and not defended and not was_attacked_before:
            piece_name = piece.symbol().upper()
            return f"You hung your {piece_name}. It is undefended and can be captured."

    return None


def _detect_material_loss(board_before: chess.Board, board_after: chess.Board, player_color: chess.Color) -> Optional[str]:
    # Detect material loss via capture

    def material(board: chess.Board, color: chess.Color) -> int:
        total = 0
        for piece_type, value in PIECE_VALUES.items():
            total += len(board.pieces(piece_type, color)) * value
        return total

    before = material(board_before, player_color)
    after = material(board_after, player_color)

    if before - after >= 200:
        return "You lost material due to this move."

    return None


# ---------------------------
# PHASE 3 — Constraint Analysis
# ---------------------------

def _opponent_can_mate_in_one(board: chess.Board) -> bool:
    # Check if side to move can deliver checkmate in one move
    for move in board.legal_moves:
        board.push(move)
        is_mate = board.is_checkmate()
        board.pop()
        if is_mate:
            return True
    return False


def _get_moves_avoiding_immediate_mate(board: chess.Board) -> list:
    # Return list of moves that don't allow opponent to mate in 1
    safe_moves = []
    for move in board.legal_moves:
        board.push(move)
        can_be_mated = _opponent_can_mate_in_one(board)
        board.pop()
        if not can_be_mated:
            safe_moves.append(move)
    return safe_moves


def _all_moves_lose(board_before: chess.Board, player_is_white: bool, engine) -> bool:
    # Check if all alternatives keep eval <= -800 (player POV). Max 3 moves.
    if engine is None:
        return False
    
    checked = 0
    for move in board_before.legal_moves:
        if checked >= 3:
            break
        checked += 1
        test_board = board_before.copy()
        test_board.push(move)
        try:
            result = engine.analyze(test_board)
            alt_eval = _to_player_eval(result.cp_score_white, player_is_white)
            if alt_eval > -800:
                return False
        except:
            return False  # Assume not lost on error
    return True


def _get_viable_alternatives(board_before: chess.Board, move_played: chess.Move,
                             played_eval: int, player_is_white: bool, engine) -> int:
    # Count moves within 200cp of played move. Limited to 6 moves.
    legal_moves = list(board_before.legal_moves)
    if len(legal_moves) > 6:
        return 2  # Assume multiple viable when too many to check
    
    viable_count = 0
    for move in legal_moves:
        if move == move_played:
            viable_count += 1
            continue
        test_board = board_before.copy()
        test_board.push(move)
        try:
            result = engine.analyze(test_board)
            alt_eval = _to_player_eval(result.cp_score_white, player_is_white)
            if alt_eval >= played_eval - 200:
                viable_count += 1
        except:
            viable_count += 1  # Assume viable on error
    return viable_count


def _saving_move_exists(board_before: chess.Board, move_played: chess.Move,
                        player_is_white: bool, engine) -> bool:
    # Check if any alternative keeps position reasonable. Max 3 moves.
    checked = 0
    for move in board_before.legal_moves:
        if move == move_played:
            continue
        if checked >= 3:
            break
        checked += 1
        test_board = board_before.copy()
        test_board.push(move)
        try:
            result = engine.analyze(test_board)
            alt_eval = _to_player_eval(result.cp_score_white, player_is_white)
            if alt_eval >= -100:
                return True
        except:
            pass
    return False


def analyze_constraints(
    board_before: chess.Board,
    move_played: chess.Move,
    eval_initial: int,
    eval_final: int,
    player_is_white: bool,
    engine=None
) -> Optional[str]:
    # Detect forced positions. Priority: FORCED LOSS > ONLY MOVE > IGNORED THREAT
    
    player_eval_before = _to_player_eval(eval_initial, player_is_white)
    player_eval_after = _to_player_eval(eval_final, player_is_white)
    
    legal_moves = list(board_before.legal_moves)
    
    # --- 1. FORCED LOSS ---
    # Must be losing AND all alternatives also lose
    if player_eval_before <= -800:
        if _all_moves_lose(board_before, player_is_white, engine):
            return "The position was already lost."
    
    # --- 2. ONLY MOVE ---
    if len(legal_moves) == 1:
        return "This was the only move."
    
    # Only move that avoids immediate mate
    moves_avoiding_mate = _get_moves_avoiding_immediate_mate(board_before)
    if len(moves_avoiding_mate) == 1 and move_played in moves_avoiding_mate:
        return "This was the only move."
    
    # Only viable move by eval (needs engine)
    if engine is not None and len(legal_moves) <= 6:
        viable_count = _get_viable_alternatives(
            board_before, move_played, player_eval_after, player_is_white, engine
        )
        if viable_count == 1:
            return "This was the only move."
    
    # --- 3. IGNORED THREAT ---
    if player_eval_before >= -100 and player_eval_after <= -300:
        if engine is not None:
            if _saving_move_exists(board_before, move_played, player_is_white, engine):
                return "This move failed to stop the threat."
    
    return None


# ---------------------------
# Public API
# ---------------------------

def assess_move(
    move_played: chess.Move,
    eval_initial: int,
    eval_final: int,
    best_move: Optional[chess.Move],
    player_is_white: bool,
    board_before: Optional[chess.Board] = None,
    board_after: Optional[chess.Board] = None,
    engine=None
) -> MoveAssessment:
    """
    Full move assessment with tactical reasoning.
    Phase 2 COMPLETE. Phase 3 constraint analysis added.
    """

    was_best = (move_played == best_move) if best_move else False
    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)

    # Default explanation (fallback)
    explanation = "This move caused a significant evaluation drop."

    # Tactical overrides (priority-based)
    if board_before and board_after:
        player_color = chess.WHITE if player_is_white else chess.BLACK

        for detector in (
            lambda: _detect_missed_mate(eval_initial, eval_final),
            lambda: _detect_allowed_mate(board_after, eval_final, player_is_white),
            lambda: _detect_hung_piece(board_before, board_after, player_color),
            lambda: _detect_material_loss(board_before, board_after, player_color),
        ):
            result = detector()
            if result:
                explanation = result
                break

    # Constraint analysis (highest priority, overrides all)
    if board_before is not None:
        constraint_explanation = analyze_constraints(
            board_before=board_before,
            move_played=move_played,
            eval_initial=eval_initial,
            eval_final=eval_final,
            player_is_white=player_is_white,
            engine=engine
        )
        if constraint_explanation is not None:
            explanation = constraint_explanation

    return MoveAssessment(
        move_played=move_played,
        grade=grade,
        eval_initial=eval_initial,
        eval_final=eval_final,
        centipawn_loss=cp_loss,
        best_move=best_move,
        was_best_move=was_best,
        explanation=explanation
    )