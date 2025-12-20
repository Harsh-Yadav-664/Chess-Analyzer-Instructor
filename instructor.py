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


@dataclass(frozen=True)
class MoveAssessment:
    move_played: chess.Move
    move_san: str               # Human-readable: "Nf3", "e4", "O-O"
    grade: MoveGrade
    eval_initial: int            # Centipawns (White's perspective)
    eval_final: int             # Centipawns (White's perspective)
    centipawn_loss: int         # How much player lost (from their perspective)
    best_move: chess.Move
    best_move_san: str          # Human-readable best move
    was_best_move: bool
    explanation: str


def _calculate_centipawn_loss(
    eval_initial: int,
    eval_final: int,
    player_is_white: bool
) -> int:
    """
    RETURNS: Positive = player's position got worse
             Zero/Negative = player's position stayed same or improved
    """
    if player_is_white:
        return eval_initial - eval_final
    else:
        return eval_initial - eval_final


def _determine_grade(centipawn_loss: int, was_best_move: bool) -> MoveGrade:
    """
    Convert centipawn loss to a human-meaningful grade.
    
    THRESHOLDS based on chess.com/lichess conventions:
    - Best: Played the engine's top choice
    - Excellent: Within 10cp of best (basically optimal for humans)
    - Good: Within 25cp (solid, no real improvement needed)
    - Inaccuracy: 25-50cp lost (small slip, worth noting)
    - Mistake: 50-100cp lost (real error, needs attention)
    - Blunder: 100+ cp lost (serious error, game-changing)
    
    # FUTURE: Make thresholds configurable per skill level.
    # Beginners shouldn't be told a 30cp move is an "inaccuracy."
    """
    if was_best_move:
        return MoveGrade.BEST
    
    # Clamp to 0 — improving the position shouldn't lower grade
    loss = max(0, centipawn_loss)
    
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


def _generate_explanation(
    grade: MoveGrade,
    centipawn_loss: int,
    best_move_san: str,
    move_san: str
) -> str:
    if grade == MoveGrade.BEST:
        return "Perfect! You found the best move."
    
    loss = max(0, centipawn_loss)
    
    if grade == MoveGrade.EXCELLENT:
        return f"Excellent! {best_move_san} was marginally better."
    
    elif grade == MoveGrade.GOOD:
        return f"Solid choice. {best_move_san} was the engine's top pick."
    
    elif grade == MoveGrade.INACCURACY:
        return f"Slight inaccuracy (~{loss}cp). Consider {best_move_san}."
    
    elif grade == MoveGrade.MISTAKE:
        return f"Mistake! Lost ~{loss}cp. {best_move_san} was much stronger."
    
    else:  # BLUNDER
        return f"Blunder! Lost ~{loss}cp. {best_move_san} was critical here."


def assess_move(
    board: chess.Board,
    move_played: chess.Move,
    eval_initial: int,
    eval_final: int,
    best_move: chess.Move,
    player_is_white: bool
) -> MoveAssessment:

    # Convert moves to human-readable notation while we have the board
    move_san = board.san(move_played)
    best_move_san = board.san(best_move)
    
    was_best = (move_played == best_move)
    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)
    explanation = _generate_explanation(grade, cp_loss, best_move_san, move_san)
    
    return MoveAssessment(
        move_played=move_played,
        move_san=move_san,
        grade=grade,
        eval_initial=eval_initial,
        eval_final=eval_final,
        centipawn_loss=cp_loss,
        best_move=best_move,
        best_move_san=best_move_san,
        was_best_move=was_best,
        explanation=explanation
    )