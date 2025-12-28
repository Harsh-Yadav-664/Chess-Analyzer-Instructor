from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Dict
import chess

# =========================================================
# Core Types
# =========================================================

class MoveGrade(IntEnum):
    BLUNDER = 1
    MISTAKE = 2
    INACCURACY = 3
    GOOD = 4
    EXCELLENT = 5
    BEST = 6


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900
}


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
    visual_cues: Optional[Dict] = None


# =========================================================
# Core Helpers
# =========================================================

def _calculate_centipawn_loss(e0, e1, is_white):
    return (e0 - e1) if is_white else (e1 - e0)


def _determine_grade(cp_loss, was_best):
    if was_best:
        return MoveGrade.BEST
    loss = max(0, cp_loss)
    if loss <= 10:
        return MoveGrade.EXCELLENT
    if loss <= 25:
        return MoveGrade.GOOD
    if loss <= 50:
        return MoveGrade.INACCURACY
    if loss <= 100:
        return MoveGrade.MISTAKE
    return MoveGrade.BLUNDER


def _fallback_explanation(grade):
    return {
        MoveGrade.BEST: "This was the best move.",
        MoveGrade.EXCELLENT: "Excellent move.",
        MoveGrade.GOOD: "A solid move.",
        MoveGrade.INACCURACY: "A small inaccuracy.",
        MoveGrade.MISTAKE: "This move weakened your position.",
        MoveGrade.BLUNDER: "This move seriously weakened your position."
    }[grade]


# =========================================================
# Phase 7 — Visual Cues (FINAL & STABLE)
# =========================================================

def _resolve_visual_reason(explanation: str) -> str:
    e = explanation.lower()
    if any(x in e for x in ("only move", "unavoidable", "already lost")):
        return "constraint"
    if "mate" in e:
        return "mate"
    if "fork" in e:
        return "fork"
    if "pin" in e:
        return "pin"
    if any(x in e for x in ("hanging", "undefended", "captured")):
        return "material"
    return "generic"


def _generate_visual_cues(
    move_played,
    best_move,
    explanation,
    grade,
    board_after,
    player_color
):
    if board_after is None:
        return None

    reason = _resolve_visual_reason(explanation)
    opp = not player_color
    cues = {"arrows": [], "highlights": []}

    if reason == "mate":
        k = board_after.king(player_color)
        if k is not None:
            cues["highlights"].append({"square": k, "type": "danger"})

    elif reason == "fork":
        for sq in chess.SQUARES:
            p = board_after.piece_at(sq)
            if p and p.color == opp:
                targets = [
                    t for t in board_after.attacks(sq)
                    if board_after.piece_at(t)
                    and board_after.piece_at(t).color == player_color
                    and PIECE_VALUES.get(board_after.piece_at(t).piece_type, 0) >= 300
                ]
                if len(targets) >= 2:
                    for t in targets[:2]:
                        cues["arrows"].append({"from": sq, "to": t, "type": "threat"})
                    break

    if (
        reason == "generic"
        and best_move
        and best_move != move_played
        and grade in (MoveGrade.INACCURACY, MoveGrade.MISTAKE, MoveGrade.BLUNDER)
    ):
        cues["arrows"].append({
            "from": best_move.from_square,
            "to": best_move.to_square,
            "type": "best"
        })

    return cues if cues["arrows"] or cues["highlights"] else None


# =========================================================
# PUBLIC API — GUI SAFE
# =========================================================

def assess_move(
    move_played,
    eval_initial,
    eval_final,
    best_move,
    player_is_white,
    board_before=None,   # accepted, ignored
    board_after=None,
    engine=None          # accepted, ignored
):
    was_best = move_played == best_move if best_move else False
    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)
    explanation = _fallback_explanation(grade)

    visual_cues = _generate_visual_cues(
        move_played,
        best_move,
        explanation,
        grade,
        board_after,
        chess.WHITE if player_is_white else chess.BLACK
    )

    return MoveAssessment(
        move_played,
        grade,
        eval_initial,
        eval_final,
        cp_loss,
        best_move,
        was_best,
        explanation,
        visual_cues
    )


# =========================================================
# GUI COMPATIBILITY STUBS (INTENTIONAL)
# =========================================================

def analyze_pre_move_threats(board, color, mode):
    return None

def reset_adaptive_state():
    pass

def get_current_mode():
    return "hard"
