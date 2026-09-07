"""
Stockfish engine wrapper.

Provides clean interface for:
- Position analysis (single best move)
- Multi-PV analysis (top N moves)
- Engine move generation with configurable skill
- Skill level and depth control per difficulty mode
- Thread-safe access via internal lock
- Auto-detection of Stockfish binary via config.py
"""

import chess
import chess.engine
import threading
from dataclasses import dataclass
from typing import Optional, List

try:
    from config import get_stockfish_path, ENGINE_DEPTH, ENGINE_THREADS
except ImportError:
    # Fallback if config not available (legacy)
    def get_stockfish_path():
        return None
    ENGINE_DEPTH = 12
    ENGINE_THREADS = 1


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
DIFFICULTY_PRESETS = {
    "beginner":     {"depth": 3,  "skill": 2,  "move_time": 0.3},
    "intermediate": {"depth": 8,  "skill": 8,  "move_time": 0.8},
    "advanced":     {"depth": 14, "skill": 16, "move_time": 1.0},
    "engine":       {"depth": 20, "skill": 20, "move_time": 1.5},
    "adaptive":     {"depth": 8,  "skill": 8,  "move_time": 0.8},
}

MATE_THRESHOLD = 50000


class ChessEngine:
    def __init__(self, stockfish_path: Optional[str] = None, depth: int = None, num_threads: int = None):
        # Auto-detect if not provided
        if stockfish_path is None:
            stockfish_path = get_stockfish_path()
        
        self.stockfish_path = stockfish_path
        self.depth = depth if depth is not None else ENGINE_DEPTH
        self.skill_level = 20
        self.move_time = 1.0
        self.num_threads = num_threads if num_threads is not None else ENGINE_THREADS
        self._engine: Optional[chess.engine.SimpleEngine] = None
        self._lock = threading.RLock()  # For thread safety

    def start(self) -> None:
        with self._lock:
            if self._engine is None:
                if not self.stockfish_path:
                    raise FileNotFoundError(
                        "Stockfish not found. Install stockfish or set STOCKFISH_PATH env var. "
                        "See https://stockfishchess.org/download/"
                    )
                self._engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
                self._apply_skill()

    def stop(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                except Exception:
                    pass
                self._engine = None

    def _apply_skill(self) -> None:
        """Push current skill level and threads to engine."""
        if self._engine is None:
            return
        try:
            self._engine.configure({"Threads": self.num_threads})
            if self.skill_level < 20:
                self._engine.configure({
                    "UCI_LimitStrength": True,
                    "UCI_Elo": self._skill_to_elo(self.skill_level)
                })
            else:
                self._engine.configure({
                    "UCI_LimitStrength": False
                })
        except Exception:
            pass

    def _skill_to_elo(self, skill: int) -> int:
        """Map 0-20 skill to rough Elo range 500-2800."""
        return 500 + int((skill / 20) * 2300)

    def set_difficulty(self, mode: str) -> None:
        """Apply a named difficulty preset."""
        with self._lock:
            preset = DIFFICULTY_PRESETS.get(mode)
            if preset is None:
                return
            self.depth = preset["depth"]
            self.skill_level = preset["skill"]
            self.move_time = preset["move_time"]
            self._apply_skill()

    def set_adaptive_params(self, blunder_rate: float) -> None:
        """Adjust difficulty dynamically based on blunder rate (0.0 to 1.0)."""
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
        """Analyze position and return best move with evaluation. Thread-safe."""
        with self._lock:
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
        """Analyze position and return top N moves. Thread-safe."""
        with self._lock:
            if self._engine is None:
                raise RuntimeError("Engine not started.")
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
        """Get engine's move. Thread-safe."""
        with self._lock:
            if self._engine is None:
                raise RuntimeError("Engine not started.")
            t = time_limit if time_limit is not None else self.move_time
            result = self._engine.play(board, chess.engine.Limit(time=t))
            return result.move

    def is_alive(self) -> bool:
        return self._engine is not None

    def __enter__(self) -> 'ChessEngine':
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.stop()
        return False
