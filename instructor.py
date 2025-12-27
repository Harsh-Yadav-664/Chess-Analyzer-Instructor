from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Tuple
import chess


# ===========================
# Core Types
# ===========================

class MoveGrade(IntEnum):
    BLUNDER = 1
    MISTAKE = 2
    INACCURACY = 3
    GOOD = 4
    EXCELLENT = 5
    BEST = 6


MATE_THRESHOLD = 50000

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


# ===========================
# Core Helpers
# ===========================

def _calculate_centipawn_loss(eval_initial, eval_final, is_white):
    return (eval_initial - eval_final) if is_white else (eval_final - eval_initial)


def _to_player_eval(cp, is_white):
    return cp if is_white else -cp


def _determine_grade(cp_loss, was_best):
    if was_best:
        return MoveGrade.BEST
    loss = max(0, cp_loss)
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


def _generate_fallback_explanation(grade, cp_loss, has_best):
    if grade == MoveGrade.BEST:
        return "This was the best move."
    if grade == MoveGrade.EXCELLENT:
        return "Excellent move."
    if grade == MoveGrade.GOOD:
        return "A solid move."
    if grade == MoveGrade.INACCURACY:
        return "A small inaccuracy."
    if grade == MoveGrade.MISTAKE:
        return "This move weakened your position."
    return "This move seriously weakened your position."


# ===========================
# Phase 2 — Tactical Detectors
# ===========================

def _detect_missed_mate(e0, e1, is_white):
    if _to_player_eval(e0, is_white) >= MATE_THRESHOLD and \
       _to_player_eval(e1, is_white) < MATE_THRESHOLD:
        return "You missed a forced checkmate."
    return None


def _detect_allowed_mate(e0, e1, is_white):
    if _to_player_eval(e0, is_white) > -MATE_THRESHOLD and \
       _to_player_eval(e1, is_white) <= -MATE_THRESHOLD:
        return "You allowed a forced checkmate."
    return None


def _detect_hung_piece(before, after, color):
    opp = not color
    for sq in chess.SQUARES:
        p = after.piece_at(sq)
        if not p or p.color != color:
            continue
        if after.is_attacked_by(opp, sq) and \
           not after.is_attacked_by(color, sq) and \
           not before.is_attacked_by(opp, sq):
            return f"You left your {chess.piece_name(p.piece_type).capitalize()} undefended."
    return None


def _detect_material_loss(before, after, color):
    def mat(b):
        return sum(len(b.pieces(pt, color)) * v for pt, v in PIECE_VALUES.items())
    if mat(before) - mat(after) >= 200:
        return "You lost material on this move."
    return None


# ===========================
# Phase 3.1 — Threat Labeling
# ===========================

def _detect_threat_type(board, color):
    opp = not color
    if board.turn == opp:
        for mv in board.legal_moves:
            board.push(mv)
            if board.is_checkmate():
                board.pop()
                return "This move failed to stop a mate threat."
            board.pop()

    for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
        for sq in board.pieces(pt, color):
            if board.is_attacked_by(opp, sq) and not board.is_attacked_by(color, sq):
                return f"Your {chess.piece_name(pt).capitalize()} can be captured."
    return None


# ===========================
# Phase 3 — Constraint Analysis
# ===========================

def _opponent_can_mate_in_one(board):
    for mv in board.legal_moves:
        board.push(mv)
        is_mate = board.is_checkmate()
        board.pop()
        if is_mate:
            return True
    return False


def _get_moves_avoiding_immediate_mate(board):
    safe = []
    for mv in board.legal_moves:
        board.push(mv)
        can_be_mated = _opponent_can_mate_in_one(board)
        board.pop()
        if not can_be_mated:
            safe.append(mv)
    return safe


def analyze_constraints(board_before, move, e0, e1, is_white, engine=None):
    pe0 = _to_player_eval(e0, is_white)
    pe1 = _to_player_eval(e1, is_white)

    legal_moves = list(board_before.legal_moves)

    if len(legal_moves) == 1:
        return "This was the only legal move.", MoveGrade.BEST, False

    if pe0 <= -MATE_THRESHOLD:
        return "Checkmate was unavoidable.", None, False

    if pe0 <= -800:
        return "The position was already lost.", None, False

    safe = _get_moves_avoiding_immediate_mate(board_before)
    if len(safe) == 1 and move in safe:
        return "This was the only move to avoid checkmate.", MoveGrade.BEST, False
    if len(safe) == 0:
        return "No move could prevent checkmate.", None, False

    if pe0 >= -100 and pe1 <= -300:
        return "This move failed to address the threat.", None, True

    return None, None, False


# ===========================
# Phase 4 — Pre-Move Nudges
# ===========================

def _has_mate_threat(board, color):
    if board.turn != color:
        return False
    if board.is_check():
        return False
    
    test = board.copy()
    try:
        test.push(chess.Move.null())
    except:
        return False
    
    for mv in test.legal_moves:
        test.push(mv)
        if test.is_checkmate():
            test.pop()
            return True
        test.pop()
    return False


def _king_safety(board, color):
    if board.is_check():
        return True
    k = board.king(color)
    if k is None:
        return False
    return len(board.attackers(not color, k)) >= 2


def _get_hanging_piece_name(board, color):
    opp = not color
    for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
        for sq in board.pieces(pt, color):
            if board.is_attacked_by(opp, sq) and not board.is_attacked_by(color, sq):
                return chess.piece_name(pt).capitalize()
    return None


_adaptive = {"blunders": 0, "good_moves": 0}


def update_adaptive_state(grade):
    if grade in (MoveGrade.BLUNDER, MoveGrade.MISTAKE):
        _adaptive["blunders"] += 1
        _adaptive["good_moves"] = 0
    elif grade in (MoveGrade.GOOD, MoveGrade.EXCELLENT, MoveGrade.BEST):
        _adaptive["good_moves"] += 1
        if _adaptive["good_moves"] >= 3:
            _adaptive["blunders"] = max(0, _adaptive["blunders"] - 1)


def reset_adaptive_state():
    _adaptive["blunders"] = 0
    _adaptive["good_moves"] = 0


def analyze_pre_move_threats(board, color, mode):
    if mode == "adaptive":
        b = _adaptive["blunders"]
        mode = "learning" if b >= 5 else "easy" if b >= 3 else "medium" if b >= 1 else "hard"

    if mode == "hard":
        return "There is a forced threat." if _has_mate_threat(board, color) else None

    if mode == "medium":
        return "This position is dangerous." if _has_mate_threat(board, color) else None

    if mode == "easy":
        if _has_mate_threat(board, color):
            return "A checkmate threat exists."
        if _king_safety(board, color):
            return "Your King position may be unsafe."
        p = _get_hanging_piece_name(board, color)
        if p:
            return "A piece may be in danger."
        return None

    if mode == "learning":
        if _has_mate_threat(board, color):
            return "Opponent threatens checkmate."
        p = _get_hanging_piece_name(board, color)
        if p:
            return f"Your {p} is under threat."
        if _king_safety(board, color):
            return "Your King may be vulnerable."
        return None

    return None


# ===========================
# Public API
# ===========================

def assess_move(
    move_played,
    eval_initial,
    eval_final,
    best_move,
    player_is_white,
    board_before=None,
    board_after=None,
    engine=None
) -> MoveAssessment:

    was_best = move_played == best_move if best_move else False
    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)

    explanation = None
    threat_failure = False

    if board_before:
        exp, override, threat_failure = analyze_constraints(
            board_before, move_played, eval_initial, eval_final, player_is_white, engine
        )
        if exp:
            explanation = exp
        if override:
            grade = override

    if threat_failure and board_after:
        color = chess.WHITE if player_is_white else chess.BLACK
        threat_exp = _detect_threat_type(board_after, color)
        if threat_exp:
            explanation = threat_exp

    if not explanation and board_before and board_after:
        color = chess.WHITE if player_is_white else chess.BLACK
        for fn in (
            lambda: _detect_missed_mate(eval_initial, eval_final, player_is_white),
            lambda: _detect_allowed_mate(eval_initial, eval_final, player_is_white),
            lambda: _detect_hung_piece(board_before, board_after, color),
            lambda: _detect_material_loss(board_before, board_after, color),
        ):
            r = fn()
            if r:
                explanation = r
                break

    if not explanation:
        explanation = _generate_fallback_explanation(grade, cp_loss, best_move is not None)

    return MoveAssessment(
        move_played, grade, eval_initial, eval_final,
        cp_loss, best_move, was_best, explanation
    )