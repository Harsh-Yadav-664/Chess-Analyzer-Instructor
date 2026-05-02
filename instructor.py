"""
AI Chess Instructor — instructor.py
Enhanced tactical move assessment with improved explanations and visual cues.

Features:
- Deep tactical pattern detection (forks, pins, skewers, discoveries, etc.)
- Context-aware explanations with chess principles
- Adaptive verbosity based on player level
- Rich visual feedback system
- Pattern-based learning hints
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

# Center squares for positional analysis
CENTER_SQUARES = {chess.E4, chess.D4, chess.E5, chess.D5}
EXTENDED_CENTER = {chess.C3, chess.D3, chess.E3, chess.F3,
                   chess.C4, chess.F4, chess.C5, chess.F5,
                   chess.C6, chess.D6, chess.E6, chess.F6}


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
    """Calculate centipawn loss from perspective of player."""
    return (e0 - e1) if is_white else (e1 - e0)


def _determine_grade(cp_loss: int, was_best: bool) -> MoveGrade:
    """
    Grade a move based on centipawn loss.
    Thresholds adjust based on current adaptive mode.
    """
    if was_best:
        return MoveGrade.BEST

    loss = max(0, cp_loss)

    if loss >= MATE_THRESHOLD:
        return MoveGrade.BLUNDER

    mode = get_current_mode()

    # Adaptive strictness
    if mode == "learning":
        if loss <= 20:
            return MoveGrade.EXCELLENT
        if loss <= 40:
            return MoveGrade.GOOD
        if loss <= 80:
            return MoveGrade.INACCURACY
        if loss <= 150:
            return MoveGrade.MISTAKE
        return MoveGrade.BLUNDER

    elif mode == "easy":
        if loss <= 15:
            return MoveGrade.EXCELLENT
        if loss <= 30:
            return MoveGrade.GOOD
        if loss <= 60:
            return MoveGrade.INACCURACY
        if loss <= 120:
            return MoveGrade.MISTAKE
        return MoveGrade.BLUNDER

    elif mode == "medium":
        if loss <= 10:
            return MoveGrade.EXCELLENT
        if loss <= 25:
            return MoveGrade.GOOD
        if loss <= 50:
            return MoveGrade.INACCURACY
        if loss <= 100:
            return MoveGrade.MISTAKE
        return MoveGrade.BLUNDER

    else:  # "hard"
        if loss <= 5:
            return MoveGrade.EXCELLENT
        if loss <= 15:
            return MoveGrade.GOOD
        if loss <= 35:
            return MoveGrade.INACCURACY
        if loss <= 75:
            return MoveGrade.MISTAKE
        return MoveGrade.BLUNDER


def _square_name(sq: int) -> str:
    """Get algebraic name of square (e.g., 'e4')."""
    return chess.square_name(sq)


def _piece_name(piece_type: int) -> str:
    """Get human-readable piece name."""
    return PIECE_NAMES.get(piece_type, "piece")


def _piece_value(piece_type: int) -> int:
    """Get material value of piece type."""
    return PIECE_VALUES.get(piece_type, 0)


# =========================================================
# Adaptive Mode State
# =========================================================

_current_mode = "hard"
_move_history: List[MoveGrade] = []


def reset_adaptive_state():
    """Reset adaptive mode tracking (called on new game)."""
    global _current_mode, _move_history
    _current_mode = "hard"
    _move_history = []


def get_current_mode() -> str:
    """Get current adaptive mode level."""
    return _current_mode


def _update_adaptive_mode(grade: MoveGrade):
    """Adjust coaching strictness based on recent move quality."""
    global _current_mode, _move_history
    _move_history.append(grade)
    
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
# Enhanced Tactical Detectors
# =========================================================

def _detect_missed_mate(eval_initial: int, eval_final: int, player_is_white: bool) -> Optional[str]:
    """Detect if player had checkmate and missed it."""
    player_had_mate = (
        (player_is_white and eval_initial >= MATE_THRESHOLD) or
        (not player_is_white and eval_initial <= -MATE_THRESHOLD)
    )
    player_still_has_mate = (
        (player_is_white and eval_final >= MATE_THRESHOLD) or
        (not player_is_white and eval_final <= -MATE_THRESHOLD)
    )
    
    if player_had_mate and not player_still_has_mate:
        return "You missed a forced checkmate sequence. Always look for checkmate before making other moves."
    
    return None


def _detect_allowed_mate(eval_final: int, player_is_white: bool) -> Optional[str]:
    """Detect if player's move allowed opponent's checkmate."""
    opponent_has_mate = (
        (player_is_white and eval_final <= -MATE_THRESHOLD) or
        (not player_is_white and eval_final >= MATE_THRESHOLD)
    )
    
    if opponent_has_mate:
        return "This move allows your opponent to force checkmate. Always check for opponent's checkmate threats before moving."
    
    return None


def _detect_missed_capture(
    board_before: chess.Board,
    move_played: chess.Move,
    player_color: chess.Color
) -> Optional[str]:
    """Detect if player missed a free (undefended) capture."""
    opponent = not player_color
    best_free_capture = None
    best_value = 0

    for move in board_before.legal_moves:
        if move == move_played:
            continue
        
        target = board_before.piece_at(move.to_square)
        if target is None or target.color != opponent:
            continue
        
        # Check if it's truly free
        test = board_before.copy()
        test.push(move)
        recapturable = test.is_attacked_by(opponent, move.to_square)
        
        if not recapturable:
            val = _piece_value(target.piece_type)
            if val > best_value:
                best_value = val
                best_free_capture = (move, target)

    if best_free_capture is None:
        return None

    played_capture = board_before.piece_at(move_played.to_square)
    played_value = _piece_value(played_capture.piece_type) if played_capture else 0

    if best_value > played_value + 50:
        move, target = best_free_capture
        return (
            f"You missed a free {_piece_name(target.piece_type)} on {_square_name(move.to_square)}. "
            f"Always scan for undefended enemy pieces before moving."
        )
    
    return None


def _detect_hung_piece(
    board_before: chess.Board,
    board_after: chess.Board,
    move_played: chess.Move,
    player_color: chess.Color
) -> Optional[str]:
    """Detect if player left a piece hanging (newly undefended)."""
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

        # Check if it was already hanging before
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
            f"Your {_piece_name(piece.piece_type)} on {_square_name(sq)} is now hanging — "
            f"it's attacked but undefended. Always check if your pieces remain protected after moving."
        )
    
    return None


def _detect_fork_allowed(
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """Detect if player's move allowed opponent to create a fork."""
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
                if val >= 300:  # Only count valuable pieces
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
            f"Your move allowed a fork: the opponent's {_piece_name(fork_piece.piece_type)} "
            f"on {_square_name(fork_sq)} now attacks your {target_strs}. "
            f"Watch for enemy pieces that can attack multiple targets simultaneously."
        )
    
    return None


def _detect_pin_created(
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """Detect if player's piece is now pinned to the king."""
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

        # Test if moving this piece exposes king
        test = board_after.copy()
        test.remove_piece_at(sq)
        
        if test.is_attacked_by(opponent, king_sq):
            attackers = test.attackers(opponent, king_sq)
            if attackers:
                attacker_sq = list(attackers)[0]
                attacker = board_after.piece_at(attacker_sq)
                if attacker:
                    return (
                        f"Your {_piece_name(piece.piece_type)} on {_square_name(sq)} "
                        f"is pinned to your king by the opponent's "
                        f"{_piece_name(attacker.piece_type)} on {_square_name(attacker_sq)}. "
                        f"Pinned pieces have limited mobility and are vulnerable."
                    )
    
    return None


def _detect_skewer(
    board_before: chess.Board,
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """
    Detect skewer: high-value piece attacked, low-value piece behind it.
    If high-value piece moves, low-value piece gets captured.
    """
    opponent = not player_color
    SLIDING = {chess.BISHOP, chess.ROOK, chess.QUEEN}
    HIGH_VALUE_THRESHOLD = 500

    for opp_sq in chess.SQUARES:
        opp_piece = board_after.piece_at(opp_sq)
        if opp_piece is None or opp_piece.color != opponent:
            continue
        if opp_piece.piece_type not in SLIDING:
            continue

        for attack_sq in board_after.attacks(opp_sq):
            front_piece = board_after.piece_at(attack_sq)
            if front_piece is None or front_piece.color != player_color:
                continue
            if _piece_value(front_piece.piece_type) < HIGH_VALUE_THRESHOLD:
                continue

            # Check if this is a new threat
            already_before = board_before.is_attacked_by(opponent, attack_sq)
            if already_before:
                before_attackers = board_before.attackers(opponent, attack_sq)
                same_attacker_before = opp_sq in before_attackers
                if same_attacker_before:
                    continue

            # Find piece behind
            opp_file = chess.square_file(opp_sq)
            opp_rank = chess.square_rank(opp_sq)
            att_file = chess.square_file(attack_sq)
            att_rank = chess.square_rank(attack_sq)

            df = att_file - opp_file
            dr = att_rank - opp_rank

            steps = max(abs(df), abs(dr))
            if steps == 0:
                continue
            
            df = df // steps
            dr = dr // steps

            cur_file = att_file + df
            cur_rank = att_rank + dr
            found_behind = None

            while 0 <= cur_file <= 7 and 0 <= cur_rank <= 7:
                behind_sq = chess.square(cur_file, cur_rank)
                behind_piece = board_after.piece_at(behind_sq)
                if behind_piece is not None:
                    if behind_piece.color == player_color:
                        behind_val = _piece_value(behind_piece.piece_type)
                        front_val = _piece_value(front_piece.piece_type)
                        if behind_val < front_val:
                            found_behind = (behind_sq, behind_piece)
                    break
                cur_file += df
                cur_rank += dr

            if found_behind:
                behind_sq, behind_piece = found_behind
                return (
                    f"Your {_piece_name(front_piece.piece_type)} on {_square_name(attack_sq)} "
                    f"is being skewered by the opponent's {_piece_name(opp_piece.piece_type)}. "
                    f"If it moves, your {_piece_name(behind_piece.piece_type)} on {_square_name(behind_sq)} "
                    f"will be captured. Look for ways to break the skewer or protect the back piece."
                )

    return None


def _detect_discovered_attack(
    board_before: chess.Board,
    board_after: chess.Board,
    move_played: chess.Move,
    player_color: chess.Color
) -> Optional[str]:
    """Detect if moving created a discovered attack opportunity."""
    # Check if moving the piece opened up an attack line
    from_sq = move_played.from_square
    
    # Get pieces behind the moved piece that could now attack
    for potential_attacker_sq in chess.SQUARES:
        piece = board_after.piece_at(potential_attacker_sq)
        if piece is None or piece.color != player_color:
            continue
        if piece.piece_type not in {chess.BISHOP, chess.ROOK, chess.QUEEN}:
            continue
        
        # Check if this piece now attacks something valuable it couldn't before
        attacks_after = board_after.attacks(potential_attacker_sq)
        attacks_before = board_before.attacks(potential_attacker_sq)
        
        new_attacks = attacks_after - attacks_before
        
        for target_sq in new_attacks:
            target = board_after.piece_at(target_sq)
            if target and target.color != player_color:
                if _piece_value(target.piece_type) >= 300:
                    return (
                        f"Good! Your move created a discovered attack: your "
                        f"{_piece_name(piece.piece_type)} on {_square_name(potential_attacker_sq)} "
                        f"now attacks the opponent's {_piece_name(target.piece_type)} "
                        f"on {_square_name(target_sq)}."
                    )
    
    return None


def _detect_center_control_loss(
    board_before: chess.Board,
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """Detect meaningful loss of center control."""
    def center_influence(board: chess.Board, color: chess.Color) -> int:
        score = 0
        for sq in CENTER_SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == color:
                score += 2
            if board.is_attacked_by(color, sq):
                score += 1
        return score

    before_score = center_influence(board_before, player_color)
    after_score = center_influence(board_after, player_color)

    if before_score < 2:
        return None

    loss = before_score - after_score

    if loss >= 3:
        return (
            "Your move significantly weakened your center control. "
            "The center squares (e4, d4, e5, d5) are crucial for piece mobility and board control. "
            "Try to maintain presence in the center whenever possible."
        )
    if loss == 2:
        return (
            "Your move reduced your control of the center. "
            "Central control gives your pieces more options and restricts your opponent."
        )

    return None


def _detect_king_safety_loss(
    board_before: chess.Board,
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """Detect if king safety was compromised."""
    king_sq = board_after.king(player_color)
    if king_sq is None:
        return None

    king_file = chess.square_file(king_sq)
    king_rank = chess.square_rank(king_sq)
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
        return (
            "Your move destroyed your king's pawn shield, leaving it exposed to attacks. "
            "Keep pawns in front of your castled king for protection, especially in the middlegame."
        )
    if before_shield > after_shield and after_shield <= 1:
        return (
            "Your king's pawn protection has been weakened. "
            "Be cautious about moving pawns near your king as it creates weaknesses."
        )

    # Check for open file to king
    king_file_pawns_after = len(board_after.pieces(chess.PAWN, player_color) & chess.BB_FILES[king_file])
    king_file_pawns_before = len(board_before.pieces(chess.PAWN, player_color) & chess.BB_FILES[king_file])

    if king_file_pawns_before > 0 and king_file_pawns_after == 0:
        file_letter = "abcdefgh"[king_file]
        return (
            f"Your king is now on an open {file_letter}-file with no pawn cover. "
            f"This makes your king vulnerable to enemy rooks and queens on this file."
        )

    return None


def _detect_material_loss(
    board_before: chess.Board,
    board_after: chess.Board,
    player_color: chess.Color
) -> Optional[str]:
    """Detect unfavorable material exchange."""
    def material(board: chess.Board, color: chess.Color) -> int:
        return sum(
            _piece_value(pt) * len(board.pieces(pt, color))
            for pt in PIECE_VALUES
            if pt != chess.KING
        )

    player_before = material(board_before, player_color)
    player_after = material(board_after, player_color)
    opp_before = material(board_before, not player_color)
    opp_after = material(board_after, not player_color)

    net = (player_after - player_before) - (opp_after - opp_before)

    if net <= -150:
        lost = player_before - player_after
        gained = opp_before - opp_after
        if lost > gained + 100:
            return (
                f"You lost material in this exchange (gave up ~{lost/100:.1f} points, gained ~{gained/100:.1f}). "
                f"Before trading pieces, calculate if the exchange is favorable or at least equal."
            )
        return (
            "You lost material with this move. "
            "Try to maintain material equality or gain an advantage in trades."
        )
    
    return None


def _detect_development_issue(
    board_before: chess.Board,
    board_after: chess.Board,
    move_played: chess.Move,
    player_color: chess.Color
) -> Optional[str]:
    """Detect poor development choices in opening."""
    # Only relevant in opening (first ~10 moves)
    if board_after.fullmove_number > 10:
        return None
    
    moved_piece = board_before.piece_at(move_played.from_square)
    if moved_piece is None:
        return None
    
    # Moving same piece twice in opening
    if moved_piece.piece_type in {chess.KNIGHT, chess.BISHOP}:
        # Check if this piece already moved
        back_rank = 0 if player_color == chess.WHITE else 7
        from_rank = chess.square_rank(move_played.from_square)
        
        if from_rank != back_rank:
            # Piece already moved before
            # Count undeveloped pieces
            undeveloped = 0
            for sq in chess.SQUARES:
                if chess.square_rank(sq) != back_rank:
                    continue
                p = board_before.piece_at(sq)
                if p and p.color == player_color and p.piece_type in {chess.KNIGHT, chess.BISHOP}:
                    undeveloped += 1
            
            if undeveloped >= 2:
                return (
                    f"You're moving your {_piece_name(moved_piece.piece_type)} again while other pieces aren't developed. "
                    f"In the opening, try to develop all your pieces before moving the same piece twice."
                )
    
    # Moving queen out too early
    if moved_piece.piece_type == chess.QUEEN and board_after.fullmove_number <= 5:
        return (
            "Bringing your queen out too early can be risky — "
            "it can be attacked by developing moves, losing you time. "
            "Usually it's better to develop knights and bishops first."
        )
    
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
    Analyze position BEFORE player moves to warn about immediate threats.
    Returns warning string if significant threat exists.
    """
    opponent = not player_color

    if board.is_check():
        return "You are in check — you must block, move your king, or capture the attacking piece."

    # Check for hanging pieces
    warnings = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.color != player_color:
            continue
        if piece.piece_type == chess.KING:
            continue
        
        if board.is_attacked_by(opponent, sq) and not board.is_attacked_by(player_color, sq):
            warnings.append((_piece_value(piece.piece_type), sq, piece))

    if warnings:
        warnings.sort(reverse=True)
        _, sq, piece = warnings[0]
        return (
            f"Warning: Your {_piece_name(piece.piece_type)} on {_square_name(sq)} "
            f"is currently hanging (undefended). Consider protecting it or moving it to safety."
        )

    return None


# =========================================================
# Enhanced Explanation Builder
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
    Build rich, context-aware explanation for the move.
    Prioritizes specific tactical feedback over generic messages.
    """
    player_color = chess.WHITE if player_is_white else chess.BLACK

    if board_before is not None and board_after is not None:
        # Priority order: critical issues first, then positives, then general
        detectors = [
            # Critical threats
            lambda: _detect_missed_mate(eval_initial, eval_final, player_is_white),
            lambda: _detect_allowed_mate(eval_final, player_is_white),
            
            # Material issues
            lambda: _detect_material_loss(board_before, board_after, player_color),
            lambda: _detect_missed_capture(board_before, move_played, player_color),
            lambda: _detect_hung_piece(board_before, board_after, move_played, player_color),
            
            # Tactical patterns
            lambda: _detect_fork_allowed(board_after, player_color),
            lambda: _detect_pin_created(board_after, player_color),
            lambda: _detect_skewer(board_before, board_after, player_color),
            
            # Positives (discovered attacks)
            lambda: _detect_discovered_attack(board_before, board_after, move_played, player_color),
            
            # Positional issues
            lambda: _detect_king_safety_loss(board_before, board_after, player_color),
            lambda: _detect_center_control_loss(board_before, board_after, player_color),
            lambda: _detect_development_issue(board_before, board_after, move_played, player_color),
        ]

        for detector in detectors:
            result = detector()
            if result:
                return _adjust_explanation_verbosity(result, grade)

    # Fallback to generic evaluation-based feedback
    base_messages = {
        MoveGrade.BEST: (
            "Perfect! This is the engine's top choice. You found the strongest continuation."
        ),
        MoveGrade.EXCELLENT: (
            "Excellent move! This is nearly as good as the best option and maintains your advantage."
        ),
        MoveGrade.GOOD: (
            "Good move. This is a solid, reasonable choice that keeps you in the game."
        ),
        MoveGrade.INACCURACY: (
            "Slight inaccuracy. While not terrible, there was a better option available. "
            "Review the suggested move to understand what you could have improved."
        ),
        MoveGrade.MISTAKE: (
            "This move worsened your position significantly. "
            "Take time to analyze what went wrong and what the better alternative was."
        ),
        MoveGrade.BLUNDER: (
            "Serious mistake! This move heavily damages your position. "
            "Study the suggested best move carefully to understand the critical difference."
        ),
    }

    return _adjust_explanation_verbosity(base_messages[grade], grade)


def _adjust_explanation_verbosity(explanation: str, grade: MoveGrade) -> str:
    """
    Adjust explanation detail level based on adaptive mode.
    
    learning: Full detail with chess principles
    easy:     Moderate detail with hints
    medium:   Standard detail
    hard:     Concise, expert-level
    """
    mode = get_current_mode()

    # Good moves stay concise regardless
    if grade >= MoveGrade.GOOD:
        if mode == "hard":
            return explanation.split('.')[0] + '.'
        return explanation

    # For errors, add educational content based on mode
    if mode == "hard":
        # Concise for strong players
        return explanation.split('.')[0] + '.'

    elif mode == "medium":
        # Standard detail
        return explanation

    elif mode in ("easy", "learning"):
        # Add teaching hints for common patterns
        hints = {
            "hanging": (
                " 💡 Tip: Before moving a piece that's defending another, "
                "always check if you're leaving something unprotected."
            ),
            "fork": (
                " 💡 Tip: Watch for enemy knights and queens — they're the best forking pieces. "
                "Try to keep valuable pieces on different colors/lines when possible."
            ),
            "pin": (
                " 💡 Tip: Pinned pieces have very limited mobility. "
                "You can often exploit pins by attacking the pinned piece repeatedly."
            ),
            "skewer": (
                " 💡 Tip: A skewer forces a valuable piece to move, exposing a piece behind it. "
                "When attacked, check if moving creates further problems."
            ),
            "king": (
                " 💡 Tip: Your king's safety is paramount. Keep the pawn shield intact, "
                "avoid opening files toward your king, and castle early to find safety."
            ),
            "center": (
                " 💡 Tip: Control of the center (e4, d4, e5, d5) is a fundamental chess principle. "
                "Pieces in the center control more squares and have more mobility."
            ),
            "material": (
                " 💡 Tip: Material values: Pawn=1, Knight/Bishop=3, Rook=5, Queen=9. "
                "Try to win material or at least trade equal values."
            ),
            "mate": (
                " 💡 Tip: Checkmate is the ultimate goal. Before every move, check: "
                "Can I deliver checkmate? Can my opponent?"
            ),
            "develop": (
                " 💡 Tip: In the opening, develop your pieces efficiently. "
                "Get knights and bishops out, control the center, castle early, and connect your rooks."
            ),
        }

        lower = explanation.lower()
        for keyword, hint in hints.items():
            if keyword in lower:
                if mode == "learning":
                    return explanation + hint
                elif mode == "easy" and grade <= MoveGrade.MISTAKE:
                    return explanation + hint

    return explanation


# =========================================================
# Visual Cues — Grade-colored arrows
# =========================================================

def _grade_to_arrow_color(grade: MoveGrade) -> str:
    """
    Convert move grade to arrow color type.
    Green  = Best / Excellent
    Blue   = Good
    Yellow = Inaccuracy
    Red    = Mistake / Blunder
    """
    if grade in (MoveGrade.BEST, MoveGrade.EXCELLENT):
        return "best"
    if grade == MoveGrade.GOOD:
        return "good"
    if grade == MoveGrade.INACCURACY:
        return "inaccuracy"
    return "blunder"


def _generate_visual_cues(
    move_played: chess.Move,
    best_move: Optional[chess.Move],
    explanation: str,
    grade: MoveGrade,
    board_after: Optional[chess.Board],
    player_color: chess.Color,
) -> Optional[Dict]:
    """
    Generate visual feedback (arrows and highlights) based on position and explanation.
    """
    if board_after is None:
        return None

    opponent = not player_color
    cues = {"arrows": [], "highlights": []}
    e = explanation.lower()

    # Played move arrow — colored by grade
    arrow_type = _grade_to_arrow_color(grade)
    cues["arrows"].append({
        "from": move_played.from_square,
        "to": move_played.to_square,
        "type": arrow_type,
    })

    # Best move arrow (green) when player didn't play best
    if (
        best_move
        and best_move != move_played
        and grade in (MoveGrade.INACCURACY, MoveGrade.MISTAKE, MoveGrade.BLUNDER)
    ):
        cues["arrows"].append({
            "from": best_move.from_square,
            "to": best_move.to_square,
            "type": "best",
        })

    # Tactical pattern highlights
    if "checkmate" in e or "forced mate" in e:
        k = board_after.king(player_color)
        if k is not None:
            cues["highlights"].append({"square": k, "type": "danger"})

    elif "hanging" in e or "undefended" in e:
        # Highlight hanging pieces
        for sq in chess.SQUARES:
            piece = board_after.piece_at(sq)
            if piece and piece.color == player_color and piece.piece_type != chess.KING:
                if (board_after.is_attacked_by(opponent, sq) and
                        not board_after.is_attacked_by(player_color, sq)):
                    cues["highlights"].append({"square": sq, "type": "danger"})
                    break

    elif "fork" in e:
        # Show fork arrows
        for sq in chess.SQUARES:
            piece = board_after.piece_at(sq)
            if piece and piece.color == opponent:
                targets = [
                    t for t in board_after.attacks(sq)
                    if board_after.piece_at(t)
                    and board_after.piece_at(t).color == player_color
                    and _piece_value(board_after.piece_at(t).piece_type) >= 300
                ]
                if len(targets) >= 2:
                    for t in targets[:2]:
                        cues["arrows"].append({"from": sq, "to": t, "type": "threat"})
                    break

    elif "pinned" in e or "pin" in e:
        # Highlight pinned piece
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

    elif "skewer" in e:
        # Highlight skewered piece
        for sq in chess.SQUARES:
            piece = board_after.piece_at(sq)
            if piece and piece.color == player_color:
                if _piece_value(piece.piece_type) >= 500:
                    if board_after.is_attacked_by(opponent, sq):
                        cues["highlights"].append({"square": sq, "type": "warning"})
                        break

    elif "king" in e and ("shield" in e or "open" in e or "expos" in e):
        # Highlight exposed king
        k = board_after.king(player_color)
        if k is not None:
            cues["highlights"].append({"square": k, "type": "warning"})

    elif "center" in e:
        # Highlight lost center control
        for sq in CENTER_SQUARES:
            if not board_after.is_attacked_by(player_color, sq):
                piece = board_after.piece_at(sq)
                if piece is None or piece.color != player_color:
                    cues["highlights"].append({"square": sq, "type": "warning"})

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
    Comprehensive move assessment with tactical detection and rich feedback.
    
    Args:
        move_played: The move that was played
        eval_initial: Position evaluation before move (centipawns, white perspective)
        eval_final: Position evaluation after move (centipawns, white perspective)
        best_move: Engine's recommended best move
        player_is_white: Whether the player is white
        board_before: Board state before the move
        board_after: Board state after the move
        engine: Chess engine instance (optional, for future use)
    
    Returns:
        MoveAssessment with grade, explanation, and visual cues
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

    # Update adaptive mode based on performance
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