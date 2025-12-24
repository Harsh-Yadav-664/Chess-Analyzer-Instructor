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
    best_move: Optional[chess.Move]  # None if engine provided no PV
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
        # White wants higher eval; loss = how much eval dropped
        return eval_initial - eval_final
    else:
        # Black wants lower eval; loss = how much eval increased
        return eval_final - eval_initial


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
    
    # Handle mate-level swings explicitly (walked into mate or missed mate)
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


def _generate_explanation(
    grade: MoveGrade,
    centipawn_loss: int,
    has_best_move: bool
) -> str:
    # Generates explanation without SAN strings (main.py handles move display)
    if grade == MoveGrade.BEST:
        return "Perfect! You found the best move."
    
    loss = max(0, centipawn_loss)
    
    # Check if this was a mate-related swing
    is_mate_swing = loss >= MATE_THRESHOLD
    
    if grade == MoveGrade.EXCELLENT:
        if has_best_move:
            return "Excellent! The engine's top pick was marginally better."
        return "Excellent move!"
    
    elif grade == MoveGrade.GOOD:
        if has_best_move:
            return "Solid choice. The engine's top pick was slightly stronger."
        return "Solid choice."
    
    elif grade == MoveGrade.INACCURACY:
        if has_best_move:
            return f"Slight inaccuracy (~{loss}cp). A better move was available."
        return f"Slight inaccuracy (~{loss}cp)."
    
    elif grade == MoveGrade.MISTAKE:
        if has_best_move:
            return f"Mistake! Lost ~{loss}cp. A much stronger move was available."
        return f"Mistake! Lost ~{loss}cp."
    
    else:  # BLUNDER
        if is_mate_swing:
            return "Blunder! This move critically affects the game outcome."
        if has_best_move:
            return f"Blunder! Lost ~{loss}cp. There was a critical move here."
        return f"Blunder! Lost ~{loss}cp."


def assess_move(
    move_played: chess.Move,
    eval_initial: int,
    eval_final: int,
    best_move: Optional[chess.Move],
    player_is_white: bool
) -> MoveAssessment:
    # No board parameter needed — operates only on moves and numeric evals
    # SAN conversion happens in main.py where the board state is available
    
    # Handle None best_move gracefully
    was_best = (move_played == best_move) if best_move is not None else False
    has_best_move = best_move is not None
    
    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)
    explanation = _generate_explanation(grade, cp_loss, has_best_move)
    
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