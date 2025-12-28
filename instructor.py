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


def _is_real_capture_threat(board, square, color):
    piece = board.piece_at(square)
    if not piece or piece.color != color:
        return False
    
    opp = not color
    attackers = board.attackers(opp, square)
    if not attackers:
        return False
    
    victim_value = PIECE_VALUES.get(piece.piece_type, 0)
    defenders = board.attackers(color, square)
    is_defended = bool(defenders)
    
    for attacker_sq in attackers:
        attacker = board.piece_at(attacker_sq)
        if not attacker:
            continue
        
        if board.is_pinned(opp, attacker_sq):
            pin_mask = board.pin(opp, attacker_sq)
            if not pin_mask & chess.BB_SQUARES[square]:
                continue
        
        attacker_value = PIECE_VALUES.get(attacker.piece_type, 0)
        
        if not is_defended:
            return True
        
        if victim_value > attacker_value:
            return True
    
    return False


def _get_threatened_piece_type(board, color):
    for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
        for sq in board.pieces(pt, color):
            if _is_real_capture_threat(board, sq, color):
                return pt
    return None


def _king_safety_critical(board, color):
    if board.is_check():
        return True
    
    k = board.king(color)
    if k is None:
        return False
    
    opp = not color
    attackers = board.attackers(opp, k)
    return len(attackers) >= 2


def _is_forced_position(board):
    count = 0
    for _ in board.legal_moves:
        count += 1
        if count > 2:
            return False
    return True


_adaptive = {"blunders": 0, "good_moves": 0}


def _update_adaptive_state(grade):
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


def get_current_mode():
    b = _adaptive["blunders"]
    if b >= 5:
        return "learning"
    if b >= 3:
        return "easy"
    if b >= 1:
        return "medium"
    return "hard"


def _resolve_mode(mode):
    if mode == "adaptive":
        return get_current_mode()
    return mode


def analyze_pre_move_threats(board, color, mode):
    mode = _resolve_mode(mode)
    
    if mode == "hard":
        if _has_mate_threat(board, color):
            return "There is a forced threat."
        return None
    
    if mode == "medium":
        if _has_mate_threat(board, color):
            return "This position is dangerous."
        return None
    
    if mode == "easy":
        if _has_mate_threat(board, color):
            return "A checkmate threat exists."
        
        threatened = _get_threatened_piece_type(board, color)
        if threatened == chess.QUEEN:
            return "A major piece may be in danger."
        if threatened == chess.ROOK:
            return "A major piece may be in danger."
        if threatened in [chess.BISHOP, chess.KNIGHT]:
            return "A piece may be in danger."
        
        if _king_safety_critical(board, color):
            return "Your King position may be unsafe."
        
        return None
    
    if mode == "learning":
        if _has_mate_threat(board, color):
            return "Opponent threatens checkmate."
        
        threatened = _get_threatened_piece_type(board, color)
        if threatened:
            name = chess.piece_name(threatened).capitalize()
            return f"Your {name} is under threat."
        
        if _king_safety_critical(board, color):
            return "Your King may be vulnerable."
        
        if _is_forced_position(board):
            return "You have very few options."
        
        return None
    
    return None


# ===========================
# Phase 5 — Tactical Pattern Attribution
# ===========================

def _is_winning_capture(board, attacker_sq, target_sq):
    attacker = board.piece_at(attacker_sq)
    target = board.piece_at(target_sq)
    if not attacker or not target:
        return False
    
    target_color = target.color
    attacker_value = PIECE_VALUES.get(attacker.piece_type, 0)
    target_value = PIECE_VALUES.get(target.piece_type, 0)
    
    defenders = board.attackers(target_color, target_sq)
    defenders_excluding_target = chess.SquareSet(sq for sq in defenders if sq != target_sq)
    
    if not defenders_excluding_target:
        return True
    
    if target_value > attacker_value:
        return True
    
    return False


def _count_fork_targets(board, attacker_sq, victim_color):
    attacker = board.piece_at(attacker_sq)
    if not attacker:
        return 0
    
    attacks = board.attacks(attacker_sq)
    count = 0
    
    for sq in attacks:
        piece = board.piece_at(sq)
        if not piece or piece.color != victim_color:
            continue
        if PIECE_VALUES.get(piece.piece_type, 0) < 300:
            continue
        if _is_winning_capture(board, attacker_sq, sq):
            count += 1
    
    return count


def _detect_new_fork(board_before, board_after, player_color):
    opp = not player_color
    
    for sq in chess.SQUARES:
        opp_piece = board_after.piece_at(sq)
        if not opp_piece or opp_piece.color != opp:
            continue
        
        targets_after = _count_fork_targets(board_after, sq, player_color)
        if targets_after < 2:
            continue
        
        opp_piece_before = board_before.piece_at(sq)
        if opp_piece_before and opp_piece_before.color == opp:
            targets_before = _count_fork_targets(board_before, sq, player_color)
            if targets_before >= 2:
                continue
        
        return "This move allowed a fork."
    
    return None


def _detect_new_pin(board_before, board_after, player_color, move_played):
    opp = not player_color
    
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if not piece or piece.color != player_color:
            continue
        if piece.piece_type == chess.KING:
            continue
        
        if not board_after.is_pinned(player_color, sq):
            continue
        
        king_sq = board_after.king(player_color)
        if king_sq is None:
            continue
        
        pin_mask = board_after.pin(player_color, sq)
        if not pin_mask:
            continue
        
        pinner_sq = None
        for potential_pinner in chess.SQUARES:
            if potential_pinner not in pin_mask:
                continue
            pinner = board_after.piece_at(potential_pinner)
            if pinner and pinner.color == opp:
                if pinner.piece_type in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
                    pinner_sq = potential_pinner
                    break
        
        if pinner_sq is None:
            continue
        
        piece_before = board_before.piece_at(sq)
        if piece_before and piece_before.color == player_color:
            if board_before.is_pinned(player_color, sq):
                continue
        
        pinned_value = PIECE_VALUES.get(piece.piece_type, 0)
        if pinned_value < 300:
            continue
        
        is_attacked = board_after.is_attacked_by(opp, sq)
        
        defends_something = False
        piece_attacks = board_after.attacks(sq)
        for defended_sq in piece_attacks:
            defended_piece = board_after.piece_at(defended_sq)
            if defended_piece and defended_piece.color == player_color:
                if board_after.is_attacked_by(opp, defended_sq):
                    defends_something = True
                    break
        
        if is_attacked or defends_something:
            return "This move allowed a pin."
    
    return None


def _detect_skewer(board_after, player_color):
    opp = not player_color
    
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if not piece or piece.color != opp:
            continue
        if piece.piece_type not in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
            continue
        
        attacks = board_after.attacks(sq)
        
        for target_sq in attacks:
            target = board_after.piece_at(target_sq)
            if not target or target.color != player_color:
                continue
            target_val = PIECE_VALUES.get(target.piece_type, 0)
            if target_val < 500:
                continue
            
            file_diff = chess.square_file(target_sq) - chess.square_file(sq)
            rank_diff = chess.square_rank(target_sq) - chess.square_rank(sq)
            
            if file_diff == 0 and rank_diff == 0:
                continue
            
            file_step = 0 if file_diff == 0 else file_diff // abs(file_diff)
            rank_step = 0 if rank_diff == 0 else rank_diff // abs(rank_diff)
            
            behind_file = chess.square_file(target_sq) + file_step
            behind_rank = chess.square_rank(target_sq) + rank_step
            
            while 0 <= behind_file <= 7 and 0 <= behind_rank <= 7:
                behind_sq = chess.square(behind_file, behind_rank)
                behind_piece = board_after.piece_at(behind_sq)
                if behind_piece:
                    if behind_piece.color == player_color:
                        behind_val = PIECE_VALUES.get(behind_piece.piece_type, 0)
                        if 0 < behind_val < target_val:
                            return "This move allowed a skewer."
                    break
                behind_file += file_step
                behind_rank += rank_step
    
    return None


def _detect_discovered_attack(board_before, board_after, player_color, move_played):
    opp = not player_color
    
    moved_from = move_played.from_square
    moved_piece_before = board_before.piece_at(moved_from)
    
    if not moved_piece_before or moved_piece_before.color != player_color:
        return None
    
    for opp_sq in chess.SQUARES:
        opp_piece = board_after.piece_at(opp_sq)
        if not opp_piece or opp_piece.color != opp:
            continue
        if opp_piece.piece_type not in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
            continue
        
        opp_piece_before = board_before.piece_at(opp_sq)
        if not opp_piece_before or opp_piece_before.color != opp:
            continue
        if opp_piece_before.piece_type != opp_piece.piece_type:
            continue
        
        attacks_before = board_before.attacks(opp_sq)
        if moved_from in attacks_before:
            continue
        
        attacks_after = board_after.attacks(opp_sq)
        new_attacks = attacks_after - attacks_before
        
        if not new_attacks:
            continue
        
        for target_sq in new_attacks:
            target = board_after.piece_at(target_sq)
            if target and target.color == player_color:
                if PIECE_VALUES.get(target.piece_type, 0) >= 300:
                    try:
                        ray = chess.ray(opp_sq, target_sq)
                        if moved_from in ray:
                            return "This move allowed a discovered attack."
                    except:
                        pass
    
    return None


def _detect_back_rank_weakness(board_after, player_color):
    opp = not player_color
    
    king_sq = board_after.king(player_color)
    if king_sq is None:
        return None
    
    back_rank = 0 if player_color == chess.WHITE else 7
    if chess.square_rank(king_sq) != back_rank:
        return None
    
    king_file = chess.square_file(king_sq)
    second_rank = 1 if player_color == chess.WHITE else 6
    
    blocked_count = 0
    checked_count = 0
    for f in [king_file - 1, king_file, king_file + 1]:
        if f < 0 or f > 7:
            continue
        checked_count += 1
        sq = chess.square(f, second_rank)
        piece = board_after.piece_at(sq)
        if piece and piece.color == player_color:
            blocked_count += 1
    
    if checked_count == 0 or blocked_count < checked_count:
        return None
    
    for opp_sq in chess.SQUARES:
        opp_piece = board_after.piece_at(opp_sq)
        if not opp_piece or opp_piece.color != opp:
            continue
        if opp_piece.piece_type not in [chess.ROOK, chess.QUEEN]:
            continue
        
        attacks = board_after.attacks(opp_sq)
        for f in range(8):
            back_sq = chess.square(f, back_rank)
            if back_sq in attacks:
                return "This move exposed a back rank weakness."
    
    return None


def _detect_new_hanging_piece(board_before, board_after, player_color):
    opp = not player_color
    
    for sq in chess.SQUARES:
        piece_after = board_after.piece_at(sq)
        if not piece_after or piece_after.color != player_color:
            continue
        
        if piece_after.piece_type == chess.KING:
            continue
        
        if PIECE_VALUES.get(piece_after.piece_type, 0) < 300:
            continue
        
        if not board_after.is_attacked_by(opp, sq):
            continue
        if board_after.is_attacked_by(player_color, sq):
            continue
        
        piece_before = board_before.piece_at(sq)
        if piece_before and piece_before.color == player_color:
            was_attacked = board_before.is_attacked_by(opp, sq)
            was_defended = board_before.is_attacked_by(player_color, sq)
            if was_attacked and not was_defended:
                continue
        
        return "This move left a piece hanging."
    
    return None


def _detect_overloaded_defender(board_before, board_after, player_color, move_played):
    opp = not player_color
    
    moved_to = move_played.to_square
    moved_piece = board_after.piece_at(moved_to)
    if not moved_piece or moved_piece.color != player_color:
        return None
    
    for sq in chess.SQUARES:
        piece_after = board_after.piece_at(sq)
        if not piece_after or piece_after.color != player_color:
            continue
        if sq == moved_to:
            continue
        
        if not board_after.is_attacked_by(opp, sq):
            continue
        
        defenders_before = board_before.attackers(player_color, sq)
        defenders_after = board_after.attackers(player_color, sq)
        
        if not defenders_before:
            continue
        
        lost_defenders = defenders_before - defenders_after
        if not lost_defenders:
            continue
        
        for defender_sq in lost_defenders:
            defender_before = board_before.piece_at(defender_sq)
            if not defender_before or defender_before.color != player_color:
                continue
            
            defender_still_exists = board_after.piece_at(defender_sq)
            if not defender_still_exists or defender_still_exists.color != player_color:
                continue
            
            defender_attacks_before = board_before.attacks(defender_sq)
            defender_attacks_after = board_after.attacks(defender_sq)
            
            defended_before_count = 0
            for potential_sq in defender_attacks_before:
                potential_piece = board_before.piece_at(potential_sq)
                if potential_piece and potential_piece.color == player_color:
                    if board_before.is_attacked_by(opp, potential_sq):
                        defended_before_count += 1
            
            if defended_before_count >= 2:
                if moved_to in defender_attacks_after:
                    return "This move overloaded a defender."
    
    return None


def _detect_new_mate_threat(board_after, player_color):
    opp = not player_color
    if board_after.turn != opp:
        return None
    
    for mv in board_after.legal_moves:
        board_after.push(mv)
        is_mate = board_after.is_checkmate()
        board_after.pop()
        if is_mate:
            return "This move allowed a mate threat."
    
    return None


def detect_tactical_pattern(board_before, board_after, player_color, move_played, threat_already_detected=False):
    if not threat_already_detected:
        result = _detect_new_mate_threat(board_after, player_color)
        if result:
            return result
    
    result = _detect_new_fork(board_before, board_after, player_color)
    if result:
        return result
    
    result = _detect_new_pin(board_before, board_after, player_color, move_played)
    if result:
        return result
    
    result = _detect_skewer(board_after, player_color)
    if result:
        return result
    
    result = _detect_discovered_attack(board_before, board_after, player_color, move_played)
    if result:
        return result
    
    result = _detect_back_rank_weakness(board_after, player_color)
    if result:
        return result
    
    result = _detect_new_hanging_piece(board_before, board_after, player_color)
    if result:
        return result
    
    result = _detect_overloaded_defender(board_before, board_after, player_color, move_played)
    if result:
        return result
    
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
    constraint_found = False
    mate_threat_detected = False

    if board_before:
        exp, override, threat_failure = analyze_constraints(
            board_before, move_played, eval_initial, eval_final, player_is_white, engine
        )
        if exp:
            explanation = exp
            constraint_found = True
        if override:
            grade = override

    if threat_failure and board_after:
        color = chess.WHITE if player_is_white else chess.BLACK
        threat_exp = _detect_threat_type(board_after, color)
        if threat_exp:
            explanation = threat_exp
            if "mate" in threat_exp.lower():
                mate_threat_detected = True

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
                if "mate" in r.lower():
                    mate_threat_detected = True
                break

    if not explanation and not constraint_found and board_before and board_after:
        if grade in (MoveGrade.INACCURACY, MoveGrade.MISTAKE, MoveGrade.BLUNDER):
            color = chess.WHITE if player_is_white else chess.BLACK
            pattern_exp = detect_tactical_pattern(
                board_before, board_after, color, move_played,
                threat_already_detected=mate_threat_detected
            )
            if pattern_exp:
                explanation = pattern_exp

    if not explanation:
        explanation = _generate_fallback_explanation(grade, cp_loss, best_move is not None)

    _update_adaptive_state(grade)

    return MoveAssessment(
        move_played, grade, eval_initial, eval_final,
        cp_loss, best_move, was_best, explanation
    )