#Engine wrapper for Stockfish integration.
import chess
import chess.engine
from dataclasses import dataclass
from typing import Optional

# 100 centipawns = 1 pawn unit
@dataclass(frozen=True)
class AnalysisResult:
    cp_score_white: int       # From White's perspective, always
    best_move: chess.Move       # Engine's recommended move
    is_mate: bool               # True if forced mate exists
    mate_in: Optional[int]      # Moves to mate (+ = White mates, - = Black mates)


class ChessEngine:
    # Wused class and not func bcz : Engine process lifecycle management.
    # Starting/stopping Stockfish is expensive; we want to do it once.
    
    def __init__(self, stockfish_path: str, depth: int = 15):
        # more depth is better but slower so 15 is balanced
        self.stockfish_path = stockfish_path
        self.depth = depth
        self._engine: Optional[chess.engine.SimpleEngine] = None
    
    def start(self) -> None:
        # Initialize engine process. Called automatically by __enter__.
        if self._engine is None:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
    
    def stop(self) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None
    
    def analyze(self, board: chess.Board) -> AnalysisResult:        
        # using white perspective for consistency for now
        if self._engine is None:
            raise RuntimeError("Engine not started. Use 'with' statement or call start().")
        
        # Analyze to fixed depth (consistent analysis quality)
        info = self._engine.analyse(board, chess.engine.Limit(depth=self.depth))
        
        # .white() gives score from White's perspective regardless of whose turn
        score = info["score"].white()
        
        # Best move is first move of principal variation
        best_move = info["pv"][0]
        
        # Handle mate scores specially
        if score.is_mate():
            mate_in = score.mate()  # Positive = White mates in N, negative = Black mates
            # Use large centipawn value for mate (preserves comparison math)
            # 100000 = "definitely winning" without overflow issues
            score_cp = 100000 if mate_in > 0 else -100000
            return AnalysisResult(
                cp_score_white=score_cp,
                best_move=best_move,
                is_mate=True,
                mate_in=mate_in
            )
        
        return AnalysisResult(
            cp_score_white=score.score(),
            best_move=best_move,
            is_mate=False,
            mate_in=None
        )
    
    def get_move(self, board: chess.Board, time_limit: float = 1.0) -> chess.Move:
        """
        separated from analyze() bcz: 
        - analyze() uses depth limit (consistent evaluation)
        - get_move() uses time limit (responsive play)
        - Different parameters for different purposes
        Args:
            # time_limit: Max seconds for engine to think
        """
        if self._engine is None:
            raise RuntimeError("Engine not started. Use 'with' statement or call start().")
        
        result = self._engine.play(board, chess.engine.Limit(time=time_limit))
        return result.move

    # Context manager protocol — enables 'with' statement
    def __enter__(self) -> 'ChessEngine':
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.stop()
        return False  # Don't suppress exceptions