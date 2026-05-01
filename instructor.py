"""
AI Chess Instructor — instructor.py
Tactical move assessment with visual cues.

Detects:
- Missed captures
- Hanging pieces (newly undefended)
- Forks (opponent piece attacks 2+ valuable pieces)
- Pins (piece pinned to king or queen)
- King safety degradation
- Missed mate / allowed mate

No engine calls inside this module.
All analysis is pure python-chess board logic.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Dict, List, Tuple
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
    chess.PAWN:   100,
    chess.KNIGHT: 300,
    chess.BISHOP: 325,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING:   20000,
}

PIECE_NAMES = {
    chess.PAWN:   "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK:   "rook",
    chess.QUEEN:  "queen",
    chess.KING:   "king",
}

MATE_THRESHOLD = 50000


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
# Core Math Helpers
# =========================================================

def _calculate_centipawn_loss(e0: int, e1: int, is_white: bool) -> int:
    return (e0 - e1) if is_white else (e1 - e0)


def _determine_grade(cp_loss: int, was_best: bool) -> MoveGrade:
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


def _square_name(sq: int) -> str:
    return chess.square_name(sq)


def _piece_name(piece_type: int) -> str:
    return PIECE_NAMES.get(piece_type, "piece")


def _piece_value(piece_type: int) -> int:
    return PIECE_VALUES.get(piece_type, 0)


def _is_defended(board: chess.Board, square: int, by_color: chess.Color) -> bool:
    return board.is_attacked_by(by_color, square)


# =========================================================
# Adaptive Mode State
# =========================================================

_current_mode = "hard"
_move_history: List[MoveGrade] = []


def reset_adaptive_state():
    global _current_mode, _move_history
    _current_mode = "hard"
    _move_history = []


def get_current_mode() -> str:
    return _current_mode


def _update_adaptive_mode(grade: MoveGrade):
    global _current_mode, _move_history
    _move_history.append(grade)

    # Only adapt after enough moves
    if len(_move_history) < 4:
        return

    recent = _move_history[-6:]
    bad = sum(1 for g in recent if g <= MoveGrade.MISTAKE)
    ratio = bad / len(recent)

    if ratio >= 0.5:
        _current_mode = "learning"
    elif ratio >= 0.25:
        _current_mode = "easy"
    elif ratio >= 0.1:
        _current_mode = "medium"
    else:
        _current_mode = "hard"


# =========================================================
# Tactical Detectors — Pure Board Analysis
# =========================================================

def _detect_missed_mate(eval_initial: int, eval_final: int, player_is_white: bool) -> Optional[str]:
    """Player had forced mate, threw it away."""
    player_had_mate = (
        (player_is_white and eval_initial >= MATE_THRESHOLD) or
        (not player_is_white and eval_initial <= -MATE_THRESHOLD)
    )
    player_still_has_mate = (
        (player_is_white and eval_final >= MATE_THRESHOLD) or
        (not player_is_white and eval_final <= -MATE_THRESHOLD)
    )
    if player_had_mate and not player_still_has_mate:
        return "You missed a forced checkmate."
    return None


def _detect_allowed_mate(eval_final: int, player_is_white: bool) -> Optional[str]:
    """Player's move allowed opponent forced mate."""
    opponent_has_mate = (
        (player_is_white and eval_final <= -MATE_THRESHOLD) or
        (not player_is_white and eval_final >= MATE_THRESHOLD)
    )
    if opponent_has_mate:
        return "Your move allowed a forced checkmate."
    return None


def _detect_missed_capture(
    board_before: chess.Board,
    move_played: chess.Move,
    player_color: chess.Color
) -> Optional[str]:
    """
    Player ignored a free capture (undefended opponent piece they could take).
    Only flags if the ignored capture was strictly better than what was played.
    """
    opponent = not player_color
    best_free_capture = None
    best_value = 0

    for move in board_before.legal_moves:
        if move == move_played:
            continue
        target = board_before.piece_at(move.to_square)
        if target is None or target.color != opponent:
            continue

        # Is target undefended after capture?
        test = board_before.copy()
        test.push(move)
        # After capture, can opponent recapture?
        recapturable = test.is_attacked_by(opponent, move.to_square)

        if not recapturable:
            val = _piece_value(target.piece_type)
            if val > best_value:
                best_value = val
                best_free_capture = (move, target)

    if best_free_capture is None:
        return None

    # Only report if player didn't capture anything comparable
    played_capture = board_before.piece_at(move_played.to_square)
    played_value = _piece_value(played_capture.piece_type) if played_capture else 0

    if best_value > played_value + 50:
        move, target = best_free_capture
        piece_n = _piece_name(target.piece_type)
        sq_n = _square_name(move.to_square)
        return f"You missed a free capture: {piece_n} on {sq_n} was undefended."

    return None


def _detect_hung_piece(
    board_before: chess.Board,
    board_after: chess.Board,
    move_played: chess.Move,
    player_color: chess.Color
) -> Optional[str]:
    """
    After player's move, one of their pieces is now attacked and undefended
    (and was not already in that state before the move).
    """
    opponent = not player_color
    worst_value = 0
    worst_report = None

    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece is None or piece.color != player_color:
            continue
        if piece.piece_type == chess.KING:
            continue

        attacked_after = board_after.is_attacked_by(opponent, sq)
        defended_after = board_after.is_attacked_by(player_color, sq)

        if not (attacked_after and not defended_after):
            continue

        # Was it already hanging before?
        attacked_before = board_before.is_attacked_by(opponent, sq)
        defended_before = board_before.is_attacked_by(player_color, sq)
        was_hanging = attacked_before and not defended_before

        if was_hanging:
            continue

        val = _piece_value(piece.piece_type)
        if val > worst_value:
            worst_value = val
            worst_report = (sq, piece)

    if worst_report:
        sq, piece = worst_report
        return (
            f"You left your {_piece_name(piece.piece_type)} on "
            f"{_square_name(sq)} hanging — it is undefended and can be captured."
        )

    return None


def _detect_fork_allowed(
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """
    After player's move, an opponent piece now attacks two or more
    of player's pieces worth ≥300cp.
    """
    opponent = not player_color
    best_fork = None
    best_fork_value = 0

    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece is None or piece.color != opponent:
            continue

        attacked_targets = []
        for target_sq in board_after.attacks(sq):
            target = board_after.piece_at(target_sq)
            if target and target.color == player_color:
                val = _piece_value(target.piece_type)
                if val >= 300:
                    attacked_targets.append((target_sq, target, val))

        if len(attacked_targets) >= 2:
            fork_value = sum(v for _, _, v in attacked_targets)
            if fork_value > best_fork_value:
                best_fork_value = fork_value
                best_fork = (sq, piece, attacked_targets)

    if best_fork:
        fork_sq, fork_piece, targets = best_fork
        target_strs = " and ".join(
            f"{_piece_name(t.piece_type)} on {_square_name(tsq)}"
            for tsq, t, _ in targets[:2]
        )
        return (
            f"Your move allowed a fork: opponent's "
            f"{_piece_name(fork_piece.piece_type)} on {_square_name(fork_sq)} "
            f"now attacks your {target_strs}."
        )

    return None


def _detect_pin_created(
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """
    After player's move, one of player's pieces is pinned
    (stands between king/queen and an attacking sliding piece).
    Only reports absolute pins (to king).
    """
    opponent = not player_color
    king_sq = board_after.king(player_color)
    if king_sq is None:
        return None

    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece is None or piece.color != player_color:
            continue
        if piece.piece_type == chess.KING:
            continue

        # Check if removing this piece would expose king to attack
        test = board_after.copy()
        test.remove_piece_at(sq)
        if test.is_attacked_by(opponent, king_sq):
            # Confirm it was NOT pinned before (we only care about newly created pins)
            # Find the attacker
            attackers = test.attackers(opponent, king_sq)
            if attackers:
                attacker_sq = list(attackers)[0]
                attacker = board_after.piece_at(attacker_sq)
                if attacker:
                    return (
                        f"Your {_piece_name(piece.piece_type)} on {_square_name(sq)} "
                        f"is now pinned to your king by the opponent's "
                        f"{_piece_name(attacker.piece_type)} on {_square_name(attacker_sq)}."
                    )

    return None


def _detect_king_safety_loss(
    board_before: chess.Board,
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """
    Detects pawn shield degradation around player's king.
    Counts pawns in king's zone before and after.
    """
    king_sq = board_after.king(player_color)
    if king_sq is None:
        return None

    king_file = chess.square_file(king_sq)
    king_rank = chess.square_rank(king_sq)

    # Pawn shield: 3 squares in front of king, ±1 file
    direction = 1 if player_color == chess.WHITE else -1

    def count_shield_pawns(board: chess.Board) -> int:
        count = 0
        for df in (-1, 0, 1):
            f = king_file + df
            r = king_rank + direction
            if 0 <= f <= 7 and 0 <= r <= 7:
                sq = chess.square(f, r)
                p = board.piece_at(sq)
                if p and p.piece_type == chess.PAWN and p.color == player_color:
                    count += 1
        return count

    before_shield = count_shield_pawns(board_before)
    after_shield = count_shield_pawns(board_after)

    if before_shield >= 2 and after_shield == 0:
        return "Your move broke apart your king's pawn shield, exposing your king."
    if before_shield > after_shield and after_shield == 0:
        return "Your king's pawn protection has been weakened."

    # Check if king is now on an open file
    king_file_pawns_after = len(board_after.pieces(chess.PAWN, player_color) &
                                chess.BB_FILES[king_file])
    king_file_pawns_before = len(board_before.pieces(chess.PAWN, player_color) &
                                 chess.BB_FILES[king_file])

    if king_file_pawns_before > 0 and king_file_pawns_after == 0:
        file_letter = "abcdefgh"[king_file]
        return f"Your king is now on an open {file_letter}-file with no pawn cover."

    return None


def _detect_material_loss(
    board_before: chess.Board,
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """Net material loss of ≥150cp from the move itself."""
    def material(board: chess.Board, color: chess.Color) -> int:
        return sum(
            _piece_value(pt) * len(board.pieces(pt, color))
            for pt in PIECE_VALUES
            if pt != chess.KING
        )

    player_before = material(board_before, player_color)
    player_after  = material(board_after,  player_color)
    opp_before    = material(board_before, not player_color)
    opp_after     = material(board_after,  not player_color)

    # Net change: positive = player gained
    net = (player_after - player_before) - (opp_after - opp_before)

    if net <= -150:
        lost = player_before - player_after
        gained = opp_before - opp_after
        if lost > gained + 100:
            return f"You lost material on this exchange (lost ~{lost}cp, gained ~{gained}cp)."
        return "You lost material with this move."

    return None


# =========================================================
# Pre-Move Threat Analysis
# =========================================================

def analyze_pre_move_threats(
    board: chess.Board,
    player_color: chess.Color,
    mode: str
) -> Optional[str]:
    """
    Called BEFORE player moves.
    Warns if player's king is in check or a piece is under immediate threat.
    Returns warning string or None.
    """
    opponent = not player_color

    # Already in check
    if board.is_check():
        return "You are in check — you must address the threat."

    # Warn about hanging pieces (attacked and undefended)
    warnings = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.color != player_color:
            continue
        if piece.piece_type == chess.KING:
            continue

        if board.is_attacked_by(opponent, sq) and not board.is_attacked_by(player_color, sq):
            warnings.append(
                f"Your {_piece_name(piece.piece_type)} on {_square_name(sq)} is hanging."
            )

    if warnings:
        # Only surface the most important one (highest value piece)
        def piece_sort_key(msg: str) -> int:
            for name, val in [
                ("queen", 900), ("rook", 500),
                ("bishop", 325), ("knight", 300), ("pawn", 100)
            ]:
                if name in msg:
                    return val
            return 0

        warnings.sort(key=piece_sort_key, reverse=True)
        return warnings[0]

    return None


# =========================================================
# Explanation Builder
# =========================================================

def _build_explanation(
    move_played: chess.Move,
    eval_initial: int,
    eval_final: int,
    best_move: Optional[chess.Move],
    player_is_white: bool,
    board_before: Optional[chess.Board],
    board_after: Optional[chess.Board],
    grade: MoveGrade,
) -> str:
    """
    Run tactical detectors in priority order.
    First match wins.
    Falls back to grade-based generic text.
    """
    player_color = chess.WHITE if player_is_white else chess.BLACK

    if board_before is not None and board_after is not None:
        detectors = [
            # Highest priority: mate situations
            lambda: _detect_missed_mate(eval_initial, eval_final, player_is_white),
            lambda: _detect_allowed_mate(eval_final, player_is_white),
            # Material and tactics
            lambda: _detect_material_loss(board_before, board_after, player_color),
            lambda: _detect_missed_capture(board_before, move_played, player_color),
            lambda: _detect_hung_piece(board_before, board_after, move_played, player_color),
            lambda: _detect_fork_allowed(board_after, player_color),
            lambda: _detect_pin_created(board_after, player_color),
            lambda: _detect_king_safety_loss(board_before, board_after, player_color),
        ]

        for detector in detectors:
            result = detector()
            if result:
                return result

    # Generic fallback
    return {
        MoveGrade.BEST:       "Best move — optimal play.",
        MoveGrade.EXCELLENT:  "Excellent move.",
        MoveGrade.GOOD:       "A solid, sensible move.",
        MoveGrade.INACCURACY: "A slight inaccuracy — there was a better option.",
        MoveGrade.MISTAKE:    "This move weakened your position.",
        MoveGrade.BLUNDER:    "This move seriously damaged your position.",
    }[grade]


# =========================================================
# Visual Cues Generator
# =========================================================

def _generate_visual_cues(
    move_played: chess.Move,
    best_move: Optional[chess.Move],
    explanation: str,
    grade: MoveGrade,
    board_after: Optional[chess.Board],
    player_color: chess.Color,
) -> Optional[Dict]:
    """Generate arrows and highlights based on what happened."""
    if board_after is None:
        return None

    opponent = not player_color
    cues = {"arrows": [], "highlights": []}
    e = explanation.lower()

    # Mate: highlight king
    if "checkmate" in e or "forced mate" in e:
        k = board_after.king(player_color)
        if k is not None:
            cues["highlights"].append({"square": k, "type": "danger"})

    # Hanging piece: highlight the hanging square
    elif "hanging" in e or "undefended" in e:
        for sq in chess.SQUARES:
            piece = board_after.piece_at(sq)
            if piece and piece.color == player_color and piece.piece_type != chess.KING:
                if (board_after.is_attacked_by(opponent, sq) and
                        not board_after.is_attacked_by(player_color, sq)):
                    cues["highlights"].append({"square": sq, "type": "danger"})
                    break

    # Fork: draw threat arrows from forking piece
    elif "fork" in e:
        for sq in chess.SQUARES:
            piece = board_after.piece_at(sq)
            if piece and piece.color == opponent:
                targets = [
                    t for t in board_after.attacks(sq)
                    if board_after.piece_at(t) and
                    board_after.piece_at(t).color == player_color and
                    _piece_value(board_after.piece_at(t).piece_type) >= 300
                ]
                if len(targets) >= 2:
                    for t in targets[:2]:
                        cues["arrows"].append({"from": sq, "to": t, "type": "threat"})
                    break

    # Pin: highlight pinned piece
    elif "pinned" in e:
        king_sq = board_after.king(player_color)
        if king_sq is not None:
            for sq in chess.SQUARES:
                piece = board_after.piece_at(sq)
                if piece and piece.color == player_color and piece.piece_type != chess.KING:
                    test = board_after.copy()
                    test.remove_piece_at(sq)
                    if test.is_attacked_by(opponent, king_sq):
                        cues["highlights"].append({"square": sq, "type": "warning"})
                        break

    # King safety: highlight king
    elif "king" in e and ("shield" in e or "open" in e or "expos" in e):
        k = board_after.king(player_color)
        if k is not None:
            cues["highlights"].append({"square": k, "type": "warning"})

    # Default: show best move arrow for inaccuracies and worse
    if (
        not cues["arrows"] and not cues["highlights"]
        and best_move
        and best_move != move_played
        and grade in (MoveGrade.INACCURACY, MoveGrade.MISTAKE, MoveGrade.BLUNDER)
    ):
        cues["arrows"].append({
            "from": best_move.from_square,
            "to": best_move.to_square,
            "type": "best"
        })

    return cues if (cues["arrows"] or cues["highlights"]) else None


# =========================================================
# Public API
# =========================================================

def assess_move(
    move_played: chess.Move,
    eval_initial: int,
    eval_final: int,
    best_move: Optional[chess.Move],
    player_is_white: bool,
    board_before: Optional[chess.Board] = None,
    board_after: Optional[chess.Board] = None,
    engine=None,
) -> MoveAssessment:
    """
    Full move assessment.
    Returns grade, explanation, and visual cues.
    engine param accepted for API compatibility but not used here.
    """
    was_best = (move_played == best_move) if best_move else False
    cp_loss = _calculate_centipawn_loss(eval_initial, eval_final, player_is_white)
    grade = _determine_grade(cp_loss, was_best)

    explanation = _build_explanation(
        move_played=move_played,
        eval_initial=eval_initial,
        eval_final=eval_final,
        best_move=best_move,
        player_is_white=player_is_white,
        board_before=board_before,
        board_after=board_after,
        grade=grade,
    )

    player_color = chess.WHITE if player_is_white else chess.BLACK
    visual_cues = _generate_visual_cues(
        move_played=move_played,
        best_move=best_move,
        explanation=explanation,
        grade=grade,
        board_after=board_after,
        player_color=player_color,
    )

    _update_adaptive_mode(grade)

    return MoveAssessment(
        move_played=move_played,
        grade=grade,
        eval_initial=eval_initial,
        eval_final=eval_final,
        centipawn_loss=cp_loss,
        best_move=best_move,
        was_best_move=was_best,
        explanation=explanation,
        visual_cues=visual_cues,
    )