"""
Stockfish engine wrapper.

Provides clean interface for:
- Position analysis (single best move)
- Multi-PV analysis (top N moves)
- Engine move generation with configurable skill
- Skill level and depth control per difficulty mode
"""

import chess
import chess.engine
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass(frozen=True)
class AnalysisResult:
    cp_score_white: int
    best_move: Optional[chess.Move]
    is_mate: bool
    mate_in: Optional[int]


@dataclass(frozen=True)
class MultiPVResult:
    """One line from a multi-pv analysis."""
    move: chess.Move
    cp_score_white: int
    is_mate: bool
    mate_in: Optional[int]


# Difficulty presets
# Each maps to (depth, skill_level, move_time)
# Skill level: 0 (weakest) to 20 (strongest) — Stockfish UCI_LimitStrength
DIFFICULTY_PRESETS = {
    "beginner":     {"depth": 3,  "skill": 2,  "move_time": 0.5},
    "intermediate": {"depth": 8,  "skill": 8,  "move_time": 1.0},
    "advanced":     {"depth": 14, "skill": 16, "move_time": 1.0},
    "engine":       {"depth": 20, "skill": 20, "move_time": 2.0},
    "adaptive":     {"depth": 8,  "skill": 8,  "move_time": 1.0},
}

MATE_THRESHOLD = 50000


class ChessEngine:
    def __init__(self, stockfish_path: str, depth: int = 15):
        self.stockfish_path = stockfish_path
        self.depth = depth
        self.skill_level = 20
        self.move_time = 1.0
        self._engine: Optional[chess.engine.SimpleEngine] = None

    def start(self) -> None:
        if self._engine is None:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
            self._apply_skill()

    def stop(self) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def _apply_skill(self) -> None:
        """Push current skill level to engine. Called after start and after skill changes."""
        if self._engine is None:
            return
        try:
            if self.skill_level < 20:
                self._engine.configure({
                    "UCI_LimitStrength": True,
                    "UCI_Elo": self._skill_to_elo(self.skill_level)
                })
            else:
                self._engine.configure({
                    "UCI_LimitStrength": False
                })
        except:
            pass

    def _skill_to_elo(self, skill: int) -> int:
        """Map 0-20 skill to rough Elo range 500-2800."""
        return 500 + int((skill / 20) * 2300)

    def set_difficulty(self, mode: str) -> None:
        """
        Apply a named difficulty preset.
        Called by GUI when mode dropdown changes.
        """
        preset = DIFFICULTY_PRESETS.get(mode)
        if preset is None:
            return

        self.depth = preset["depth"]
        self.skill_level = preset["skill"]
        self.move_time = preset["move_time"]
        self._apply_skill()

    def set_adaptive_params(self, blunder_rate: float) -> None:
        """
        Adjust difficulty dynamically based on blunder rate.
        Called by GUI in adaptive mode after each move.

        blunder_rate: fraction of moves that were blunders/mistakes (0.0 to 1.0)
        """
        if blunder_rate >= 0.4:
            self.set_difficulty("beginner")
        elif blunder_rate >= 0.25:
            self.set_difficulty("intermediate")
        elif blunder_rate >= 0.1:
            self.set_difficulty("advanced")
        else:
            self.set_difficulty("engine")

    def _parse_score(self, score: chess.engine.PovScore):
        """Convert PovScore to (cp_white, is_mate, mate_in)."""
        white_score = score.white()

        if white_score.is_mate():
            mate_in = white_score.mate()
            cp = MATE_THRESHOLD if mate_in > 0 else -MATE_THRESHOLD
            return cp, True, mate_in

        cp = white_score.score()
        if cp is None:
            cp = 0
        return cp, False, None

    def analyze(self, board: chess.Board) -> AnalysisResult:
        """Analyze position and return best move with evaluation."""
        if self._engine is None:
            raise RuntimeError("Engine not started.")

        info = self._engine.analyse(board, chess.engine.Limit(depth=self.depth))

        pv = info.get("pv", [])
        best_move = pv[0] if pv else None

        cp, is_mate, mate_in = self._parse_score(info["score"])

        return AnalysisResult(
            cp_score_white=cp,
            best_move=best_move,
            is_mate=is_mate,
            mate_in=mate_in
        )

    def analyze_multipv(self, board: chess.Board, n: int = 3) -> List[MultiPVResult]:
        """
        Analyze position and return top N moves with evaluations.
        Used for alternative move display in side panel.
        """
        if self._engine is None:
            raise RuntimeError("Engine not started.")

        # Clamp n to number of legal moves
        legal_count = len(list(board.legal_moves))
        n = min(n, legal_count)

        if n <= 0:
            return []

        results = []
        try:
            infos = self._engine.analyse(
                board,
                chess.engine.Limit(depth=self.depth),
                multipv=n
            )

            # Stockfish returns a list when multipv > 1
            if isinstance(infos, dict):
                infos = [infos]

            for info in infos:
                pv = info.get("pv", [])
                if not pv:
                    continue

                move = pv[0]
                cp, is_mate, mate_in = self._parse_score(info["score"])

                results.append(MultiPVResult(
                    move=move,
                    cp_score_white=cp,
                    is_mate=is_mate,
                    mate_in=mate_in
                ))

        except Exception:
            pass

        return results

    def get_move(self, board: chess.Board, time_limit: float = None) -> Optional[chess.Move]:
        """Get engine's move. Uses instance move_time if time_limit not specified."""
        if self._engine is None:
            raise RuntimeError("Engine not started.")

        t = time_limit if time_limit is not None else self.move_time
        result = self._engine.play(board, chess.engine.Limit(time=t))
        return result.move

    def __enter__(self) -> 'ChessEngine':
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.stop()
        return False