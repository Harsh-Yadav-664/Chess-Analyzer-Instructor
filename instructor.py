"""
FUTURE EXTENSIONS:
Add position-relative scaling (blunder in +10 matters less than in +0)
Add tactical pattern detection ("you missed a fork")
Plug in LLM for natural language explanations
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
import chess


class MoveGrade(IntEnum):
    # higher is better
    BLUNDER = 1
    MISTAKE = 2
    INACCURACY = 3
    GOOD = 4
    EXCELLENT = 5
    BEST = 6


# Threshold for detecting mate-level evaluation swings
MATE_THRESHOLD = 50000


@dataclass(frozen=True)
class MoveAssessment:
    move_played: chess.Move
    grade: MoveGrade
    eval_initial: int            # Centipawns (White's perspective)
    eval_final: int              # Centipawns (White's perspective)
    centipawn_loss: int          # How much player lost (from their perspective)
    best_move: Optional[chess.Move]
    was_best_move: bool
    explanation: str


def _calculate_centipawn_loss(
    eval_initial: int,
    eval_final: int,
    player_is_white: bool
) -> int:
    """
    RETURNS: Positive = player's position got worse
    """
    if player_is_white:
        return eval_initial - eval_final
    else:
        return eval_final - eval_initial


def _determine_grade(centipawn_loss: int, was_best_move: bool) -> MoveGrade:
    if was_best_move:
        return MoveGrade.BEST

    loss = max(0, centipawn_loss)

    if loss >= MATE_THRESHOLD:
        return MoveGrade.BLUNDER
    if loss <= 10:
        return MoveGrade.EXCELLENT
    if loss <= 25:
        return MoveGrade.GOOD
    if loss <= 50:
        return MoveGrade.INACCURACY
    if loss <= 100:
        return MoveGrade.MISTAKE
    return MoveGrade.BLUNDER


def _generate_explanation(
    grade: MoveGrade,
    centipawn_loss: int,
    has_best_move: bool
) -> str:
    if grade == MoveGrade.BEST:
        return "Perfect! You found the best move."

    loss = max(0, centipawn_loss)

    if grade == MoveGrade.EXCELLENT:
        return "Excellent! The engine's top pick was marginally better." if has_best_move else "Excellent move!"
    if grade == MoveGrade.GOOD:
        return "Solid choice. The engine's top pick was slightly stronger." if has_best_move else "Solid choice."
    if grade == MoveGrade.INACCURACY:
        return f"Slight inaccuracy (~{loss}cp). A better move was available." if has_best_move else f"Slight inaccuracy (~{loss}cp)."
    if grade == MoveGrade.MISTAKE:
        return f"Mistake! Lost ~{loss}cp. A much stronger move was available." if has_best_move else f"Mistake! Lost ~{loss}cp."
    return f"Blunder! Lost ~{loss}cp."


# =============================================================================
# TACTICAL ANALYSIS
# =============================================================================

def analyze_tactics(
    board_before: chess.Board,
    board_after: chess.Board,
    eval_initial: int,
    eval_final: int,
    best_move: Optional[chess.Move],
    player_is_white: bool
) -> Optional[str]:
    """
    Detect tactical reasons for a bad move.
    Returns explanation string or None.
    """

    player_color = chess.WHITE if player_is_white else chess.BLACK
    opponent_color = not player_color

    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)

    # ------------------------------------------------------------------
    # 1. MISSED MATE (corrected: must be mate FOR the player)
    # ------------------------------------------------------------------
    if player_is_white:
        had_mate = eval_initial >= MATE_THRESHOLD
        still_has_mate = eval_final >= MATE_THRESHOLD
    else:
        had_mate = eval_initial <= -MATE_THRESHOLD
        still_has_mate = eval_final <= -MATE_THRESHOLD

    if had_mate and not still_has_mate:
        return "You missed a forced checkmate."

    # ------------------------------------------------------------------
    # 2. HUNG PIECE
    # ------------------------------------------------------------------
    if cp_loss >= 100:
        for square in chess.SQUARES:
            piece = board_after.piece_at(square)
            if piece is None or piece.color != player_color:
                continue

            if board_after.is_attacked_by(opponent_color, square):
                if not board_after.is_attacked_by(player_color, square):
                    if not board_before.is_attacked_by(opponent_color, square):
                        return "You left a piece undefended and it can be captured."

    # ------------------------------------------------------------------
    # 3. UNFORCED ERROR
    # ------------------------------------------------------------------
    if cp_loss >= 300:
        return "This move caused a large evaluation drop without forcing pressure."

    return None


def assess_move(
    move_played: chess.Move,
    eval_initial: int,
    eval_final: int,
    best_move: Optional[chess.Move],
    player_is_white: bool,
    board_before: Optional[chess.Board] = None,
    board_after: Optional[chess.Board] = None
) -> MoveAssessment:

    was_best = (move_played == best_move) if best_move else False
    has_best_move = best_move is not None

    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)
    explanation = _generate_explanation(grade, cp_loss, has_best_move)

    if board_before and board_after:
        tactical_reason = analyze_tactics(
            board_before,
            board_after,
            eval_initial,
            eval_final,
            best_move,
            player_is_white
        )
        if tactical_reason:
            explanation = tactical_reason

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
