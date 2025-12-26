"""
Tactical Awareness Module

This module answers:
"WHY was this move bad?"

Design rules:
- Pure analysis using python-chess + eval numbers
- Constraint explanations override all others
- Tactical explanations override generic ones
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Tuple
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

MATE_THRESHOLD = 50000

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
    return (eval_initial - eval_final) if player_is_white else (eval_final - eval_initial)


def _to_player_eval(cp_score_white: int, player_is_white: bool) -> int:
    return cp_score_white if player_is_white else -cp_score_white


def _determine_grade(cp_loss: int, was_best_move: bool) -> MoveGrade:
    if was_best_move:
        return MoveGrade.BEST

    loss = max(0, cp_loss)

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
# Tactical Detectors
# ---------------------------

def _detect_missed_mate(eval_initial: int, eval_final: int, player_is_white: bool) -> Optional[str]:
    player_eval_before = _to_player_eval(eval_initial, player_is_white)
    player_eval_after = _to_player_eval(eval_final, player_is_white)
    
    if player_eval_before >= MATE_THRESHOLD and player_eval_after < MATE_THRESHOLD:
        return "You missed a forced checkmate."
    return None


def _detect_allowed_mate(eval_initial: int, eval_final: int, player_is_white: bool) -> Optional[str]:
    player_eval_before = _to_player_eval(eval_initial, player_is_white)
    player_eval_after = _to_player_eval(eval_final, player_is_white)
    
    if player_eval_before > -MATE_THRESHOLD and player_eval_after <= -MATE_THRESHOLD:
        return "You allowed a forced checkmate."
    return None


def _detect_hung_piece(board_before: chess.Board, board_after: chess.Board, player_color: chess.Color) -> Optional[str]:
    opponent = not player_color

    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece is None or piece.color != player_color:
            continue

        attacked = board_after.is_attacked_by(opponent, square)
        defended = board_after.is_attacked_by(player_color, square)
        was_attacked_before = board_before.is_attacked_by(opponent, square)

        if attacked and not defended and not was_attacked_before:
            piece_name = chess.piece_name(piece.piece_type).capitalize()
            return f"You left your {piece_name} undefended and it can be captured."

    return None


def _detect_material_loss(board_before: chess.Board, board_after: chess.Board, player_color: chess.Color) -> Optional[str]:
    def material(board: chess.Board, color: chess.Color) -> int:
        total = 0
        for piece_type, value in PIECE_VALUES.items():
            total += len(board.pieces(piece_type, color)) * value
        return total

    before = material(board_before, player_color)
    after = material(board_after, player_color)

    if before - after >= 200:
        return "You lost material on this move."

    return None


# ---------------------------
# Threat Labeling
# ---------------------------

def _detect_threat_type(board_after: chess.Board, player_color: chess.Color) -> Optional[str]:
    """Classify the most immediate opponent threat after the move."""
    opponent_color = not player_color
    
    # a) Mate threat - only check if it's opponent's turn
    if board_after.turn == opponent_color:
        for move in board_after.legal_moves:
            board_after.push(move)
            is_mate = board_after.is_checkmate()
            board_after.pop()
            if is_mate:
                return "This move failed to stop a mate threat."
    
    # b) Queen capture threat
    for square in board_after.pieces(chess.QUEEN, player_color):
        is_attacked = board_after.is_attacked_by(opponent_color, square)
        is_defended = board_after.is_attacked_by(player_color, square)
        if is_attacked and not is_defended:
            return "Your Queen was left en prise."
    
    # c) Rook capture threat
    for square in board_after.pieces(chess.ROOK, player_color):
        is_attacked = board_after.is_attacked_by(opponent_color, square)
        is_defended = board_after.is_attacked_by(player_color, square)
        if is_attacked and not is_defended:
            return "Your Rook can be captured."
    
    # d) Minor piece capture threat
    for piece_type in [chess.KNIGHT, chess.BISHOP]:
        for square in board_after.pieces(piece_type, player_color):
            is_attacked = board_after.is_attacked_by(opponent_color, square)
            is_defended = board_after.is_attacked_by(player_color, square)
            if is_attacked and not is_defended:
                piece_name = chess.piece_name(piece_type).capitalize()
                return f"Your {piece_name} can be captured."
    
    # e) Generic material threat (any undefended piece worth >= 200cp)
    for square in chess.SQUARES:
        piece = board_after.piece_at(square)
        if piece is None or piece.color != player_color:
            continue
        if piece.piece_type == chess.KING:
            continue
        value = PIECE_VALUES.get(piece.piece_type, 0)
        if value < 200:
            continue
        is_attacked = board_after.is_attacked_by(opponent_color, square)
        is_defended = board_after.is_attacked_by(player_color, square)
        if is_attacked and not is_defended:
            return "You allowed a material-winning capture."
    
    return None


# ---------------------------
# Constraint Analysis
# ---------------------------

def _opponent_can_mate_in_one(board: chess.Board) -> bool:
    for move in board.legal_moves:
        board.push(move)
        is_mate = board.is_checkmate()
        board.pop()
        if is_mate:
            return True
    return False


def _get_moves_avoiding_immediate_mate(board: chess.Board) -> list:
    safe_moves = []
    for move in board.legal_moves:
        board.push(move)
        can_be_mated = _opponent_can_mate_in_one(board)
        board.pop()
        if not can_be_mated:
            safe_moves.append(move)
    return safe_moves


def _all_moves_lose(board_before: chess.Board, player_is_white: bool, engine) -> bool:
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
            return False
    return True


def _all_moves_lead_to_mate(board_before: chess.Board, player_is_white: bool, engine) -> bool:
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
            if alt_eval > -MATE_THRESHOLD:
                return False
        except:
            return False
    return True


def _get_viable_alternatives(board_before: chess.Board, move_played: chess.Move,
                             played_eval: int, player_is_white: bool, engine) -> int:
    legal_moves = list(board_before.legal_moves)
    if len(legal_moves) > 6:
        return 2
    
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
            viable_count += 1
    return viable_count


def _saving_move_exists(board_before: chess.Board, move_played: chess.Move,
                        player_is_white: bool, engine) -> bool:
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
) -> Tuple[Optional[str], Optional[MoveGrade], bool]:
    """Returns (explanation, grade_override, is_threat_failure)."""
    
    player_eval_before = _to_player_eval(eval_initial, player_is_white)
    player_eval_after = _to_player_eval(eval_final, player_is_white)
    
    legal_moves = list(board_before.legal_moves)
    
    # --- ONLY ONE LEGAL MOVE ---
    if len(legal_moves) == 1:
        return ("This was the only legal move.", MoveGrade.BEST, False)
    
    # --- CHECKMATE WAS UNAVOIDABLE ---
    if player_eval_before <= -MATE_THRESHOLD:
        if engine is not None:
            if _all_moves_lead_to_mate(board_before, player_is_white, engine):
                return ("Checkmate was unavoidable.", None, False)
        return ("Checkmate was unavoidable.", None, False)
    
    # --- POSITION WAS ALREADY LOST ---
    if player_eval_before <= -800:
        if engine is not None and _all_moves_lose(board_before, player_is_white, engine):
            return ("The position was already lost.", None, False)
    
    # --- ONLY MOVE TO AVOID IMMEDIATE MATE ---
    moves_avoiding_mate = _get_moves_avoiding_immediate_mate(board_before)
    if len(moves_avoiding_mate) == 1 and move_played in moves_avoiding_mate:
        return ("This was the only move to avoid checkmate.", MoveGrade.BEST, False)
    if len(moves_avoiding_mate) == 0:
        return ("No move could prevent checkmate.", None, False)
    
    # --- ONLY VIABLE MOVE BY EVALUATION ---
    if engine is not None and len(legal_moves) <= 6:
        viable_count = _get_viable_alternatives(
            board_before, move_played, player_eval_after, player_is_white, engine
        )
        if viable_count == 1:
            return ("This was the only reasonable move.", MoveGrade.GOOD, False)
    
    # --- FAILED TO ADDRESS THREAT ---
    if player_eval_before >= -100 and player_eval_after <= -300:
        if engine is not None:
            if _saving_move_exists(board_before, move_played, player_is_white, engine):
                return ("This move failed to address the threat.", None, True)
    
    return (None, None, False)


# ---------------------------
# Fallback explanation generator
# ---------------------------

def _generate_fallback_explanation(grade: MoveGrade, cp_loss: int, has_best_move: bool) -> str:
    if grade == MoveGrade.BEST:
        return "This was the best move."
    elif grade == MoveGrade.EXCELLENT:
        if has_best_move:
            return "Excellent move. Very close to the engine's top choice."
        return "Excellent move."
    elif grade == MoveGrade.GOOD:
        return "A solid move."
    elif grade == MoveGrade.INACCURACY:
        if has_best_move:
            return "A small inaccuracy. A slightly better move was available."
        return "A small inaccuracy."
    elif grade == MoveGrade.MISTAKE:
        if has_best_move:
            return "This move overlooked a stronger alternative."
        return "This move weakened your position."
    else:
        if has_best_move:
            return "This move allowed a strong response from the opponent."
        return "This move seriously weakened your position."


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
    """Full move assessment with constraint, threat labeling, and tactical reasoning."""

    was_best = (move_played == best_move) if best_move else False
    has_best_move = best_move is not None
    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)
    
    explanation = None
    is_threat_failure = False
    
    # --- CONSTRAINT ANALYSIS (highest priority) ---
    if board_before is not None:
        constraint_explanation, grade_override, is_threat_failure = analyze_constraints(
            board_before=board_before,
            move_played=move_played,
            eval_initial=eval_initial,
            eval_final=eval_final,
            player_is_white=player_is_white,
            engine=engine
        )
        
        if constraint_explanation is not None:
            explanation = constraint_explanation
            if grade_override is not None:
                grade = grade_override
    
    # --- THREAT LABELING (replaces generic threat message) ---
    if is_threat_failure and board_after is not None:
        player_color = chess.WHITE if player_is_white else chess.BLACK
        threat_explanation = _detect_threat_type(board_after, player_color)
        if threat_explanation is not None:
            explanation = threat_explanation
    
    # --- TACTICAL ANALYSIS (if no constraint/threat found) ---
    if explanation is None and board_before is not None and board_after is not None:
        player_color = chess.WHITE if player_is_white else chess.BLACK

        tactical_checks = [
            lambda: _detect_missed_mate(eval_initial, eval_final, player_is_white),
            lambda: _detect_allowed_mate(eval_initial, eval_final, player_is_white),
            lambda: _detect_hung_piece(board_before, board_after, player_color),
            lambda: _detect_material_loss(board_before, board_after, player_color),
        ]
        
        for check in tactical_checks:
            result = check()
            if result:
                explanation = result
                break
    
    # --- FALLBACK (never leave empty) ---
    if explanation is None:
        explanation = _generate_fallback_explanation(grade, cp_loss, has_best_move)

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
