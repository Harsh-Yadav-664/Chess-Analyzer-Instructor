"""
Minimal GUI shell for AI Chess Instructor.

ARCHITECTURE:
This file is a THIN LAYER that replaces main.py's CLI loop with a visual interface.
It does NOT contain any chess logic, evaluation, or grading.
All intelligence comes from engine.py and instructor.py.

RESPONSIBILITIES:
- Render chessboard and pieces
- Handle mouse clicks → convert to chess.Move
- Call engine.analyze() and assess_move() (existing logic)
- Display results in a text panel
- Handle undo (one level)

NON-RESPONSIBILITIES:
- No evaluation math
- No grading logic  
- No SAN generation (except for display, using board state)
- No direct Stockfish communication (goes through ChessEngine)

NOTE: UI will briefly freeze during engine analysis.
This is acceptable for MVP. Production would use QThread.
"""

import sys
import chess
from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QTextEdit, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush

from engine import ChessEngine
from instructor import assess_move, MoveGrade


# =============================================================================
# CONFIGURATION — Must match your system
# =============================================================================

STOCKFISH_PATH = r"D:\CODE\PROJECTS\Chess Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe"
ENGINE_DEPTH = 15
ENGINE_MOVE_TIME = 1.0


# =============================================================================
# VISUAL CONSTANTS — Simple colors, no theming
# =============================================================================

LIGHT_SQUARE = QColor(240, 217, 181)      # Cream
DARK_SQUARE = QColor(181, 136, 99)        # Brown
HIGHLIGHT_SQUARE = QColor(130, 151, 105)  # Green (selected piece)
LAST_MOVE_HIGHLIGHT = QColor(205, 210, 106)  # Yellow-green (last move)
LEGAL_MOVE_DOT = QColor(0, 0, 0, 50)      # Semi-transparent dot

# Unicode chess pieces — works on most systems without image files
PIECE_UNICODE = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
}

# Grade display colors (match CLI colors conceptually)
GRADE_COLORS = {
    MoveGrade.BEST: "#22c55e",
    MoveGrade.EXCELLENT: "#22c55e",
    MoveGrade.GOOD: "#3b82f6",
    MoveGrade.INACCURACY: "#eab308",
    MoveGrade.MISTAKE: "#ef4444",
    MoveGrade.BLUNDER: "#a855f7",
}


# =============================================================================
# CHESSBOARD WIDGET — Rendering + Click Handling
# =============================================================================

class ChessBoardWidget(QWidget):
    """
    Custom widget that draws the chessboard and handles piece selection/movement.
    
    This widget is DUMB — it only:
    - Draws squares and pieces based on a chess.Board
    - Tracks which square is selected
    - Converts clicks to chess.Move objects
    - Calls a callback when a move is made
    
    It does NOT validate moves beyond checking legality via python-chess.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Board reference — set externally via set_board()
        self.board: Optional[chess.Board] = None
        
        # Interaction state
        self.selected_square: Optional[int] = None
        self.legal_destinations: List[int] = []
        self.last_move: Optional[chess.Move] = None
        
        # Callback when player makes a move: receives chess.Move
        self.on_move_callback = None
        
        # Track if interaction is enabled (disabled during engine turn/game over)
        self.interaction_enabled = True
        
        # Fixed square size for simplicity
        self.square_size = 64
        board_pixels = self.square_size * 8
        self.setFixedSize(board_pixels, board_pixels)
    
    def set_board(self, board: chess.Board) -> None:
        """
        Update the board state and trigger repaint.
        Called by MainWindow after any board change.
        """
        self.board = board
        self.clear_selection()
        self.update()  # Qt method — schedules repaint
    
    def set_last_move(self, move: Optional[chess.Move]) -> None:
        """Highlight the last move made."""
        self.last_move = move
        self.update()
    
    def set_interaction_enabled(self, enabled: bool) -> None:
        """Enable or disable player interaction."""
        self.interaction_enabled = enabled
        if not enabled:
            self.clear_selection()
    
    def clear_selection(self) -> None:
        """Deselect any selected piece."""
        self.selected_square = None
        self.legal_destinations = []
        self.update()
    
    # -------------------------------------------------------------------------
    # Coordinate conversion helpers
    # -------------------------------------------------------------------------
    
    def _square_to_coords(self, square: int) -> Tuple[int, int]:
        """
        Convert chess square (0-63) to pixel coordinates.
        Board is drawn with White at bottom (rank 0 at bottom).
        """
        file = chess.square_file(square)  # 0-7 (a-h)
        rank = chess.square_rank(square)  # 0-7 (1-8)
        
        x = file * self.square_size
        y = (7 - rank) * self.square_size  # Flip: rank 7 at top
        
        return x, y
    
    def _coords_to_square(self, x: float, y: float) -> Optional[int]:
        """
        Convert pixel coordinates to chess square.
        Returns None if outside board.
        """
        file = int(x // self.square_size)
        rank = 7 - int(y // self.square_size)  # Flip back
        
        if 0 <= file <= 7 and 0 <= rank <= 7:
            return chess.square(file, rank)
        return None
    
    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------
    
    def paintEvent(self, event) -> None:
        """
        Draw the board, highlights, and pieces.
        Called automatically by Qt when update() is triggered.
        """
        if self.board is None:
            return
        
        painter = QPainter(self)
        
        # Draw all 64 squares
        for square in chess.SQUARES:
            self._draw_square(painter, square)
        
        # Draw legal move indicators (dots on destination squares)
        for dest_square in self.legal_destinations:
            self._draw_legal_move_dot(painter, dest_square)
        
        # Draw pieces
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece:
                self._draw_piece(painter, square, piece)
        
        painter.end()
    
    def _draw_square(self, painter: QPainter, square: int) -> None:
        """Draw a single square with appropriate background color."""
        x, y = self._square_to_coords(square)
        rect = QRect(x, y, self.square_size, self.square_size)
        
        # Determine color based on state (priority order)
        if square == self.selected_square:
            color = HIGHLIGHT_SQUARE
        elif self.last_move and (square == self.last_move.from_square or 
                                  square == self.last_move.to_square):
            color = LAST_MOVE_HIGHLIGHT
        else:
            # Standard checkerboard pattern
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            is_light = (file + rank) % 2 == 1
            color = LIGHT_SQUARE if is_light else DARK_SQUARE
        
        painter.fillRect(rect, color)
    
    def _draw_legal_move_dot(self, painter: QPainter, square: int) -> None:
        """Draw a small dot indicating a legal destination."""
        x, y = self._square_to_coords(square)
        center_x = x + self.square_size // 2
        center_y = y + self.square_size // 2
        
        # Check if there's a piece to capture (draw ring instead of dot)
        if self.board.piece_at(square):
            # Draw a ring around capturable piece
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(LEGAL_MOVE_DOT))
            painter.drawEllipse(center_x - 28, center_y - 28, 56, 56)
            # Cut out center
            painter.setBrush(QBrush(self._get_square_color(square)))
            painter.drawEllipse(center_x - 22, center_y - 22, 44, 44)
        else:
            # Simple dot for empty square
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(LEGAL_MOVE_DOT))
            painter.drawEllipse(center_x - 10, center_y - 10, 20, 20)
    
    def _get_square_color(self, square: int) -> QColor:
        """Get the base color of a square (for ring cutout)."""
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        is_light = (file + rank) % 2 == 1
        return LIGHT_SQUARE if is_light else DARK_SQUARE
    
    def _draw_piece(self, painter: QPainter, square: int, piece: chess.Piece) -> None:
        """Draw a piece using Unicode symbol."""
        x, y = self._square_to_coords(square)
        rect = QRect(x, y, self.square_size, self.square_size)
        
        symbol = PIECE_UNICODE.get(piece.symbol(), '?')
        
        # Large font for visibility
        font = QFont("Segoe UI Symbol", 40)  # Good Unicode support on Windows
        painter.setFont(font)
        
        # White pieces: white fill with dark outline effect
        # Black pieces: just dark (Unicode filled symbols)
        if piece.color == chess.WHITE:
            painter.setPen(QColor(255, 255, 255))
        else:
            painter.setPen(QColor(0, 0, 0))
        
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)
    
    # -------------------------------------------------------------------------
    # Mouse Interaction
    # -------------------------------------------------------------------------
    
    def mousePressEvent(self, event) -> None:
        """
        Handle click: either select a piece or make a move.
        
        Two-click interface:
        1. First click on own piece → select it, show legal moves
        2. Second click on legal destination → make move
        
        Clicking elsewhere clears selection.
        """
        # Guard: no board set
        if self.board is None:
            return
        
        # Guard: interaction disabled (engine thinking or game over)
        if not self.interaction_enabled:
            return
        
        # Guard: not player's turn (White for MVP)
        if self.board.turn != chess.WHITE:
            return
        
        pos = event.position()
        clicked_square = self._coords_to_square(pos.x(), pos.y())
        
        if clicked_square is None:
            return
        
        # Case 1: Clicked on a legal destination → make the move
        if clicked_square in self.legal_destinations:
            move = self._create_move(self.selected_square, clicked_square)
            self.clear_selection()
            
            if self.on_move_callback:
                self.on_move_callback(move)
            return
        
        # Case 2: Clicked on own piece → select it
        piece = self.board.piece_at(clicked_square)
        if piece and piece.color == self.board.turn:
            self.selected_square = clicked_square
            self.legal_destinations = self._get_legal_destinations(clicked_square)
            self.update()
            return
        
        # Case 3: Clicked elsewhere → clear selection
        self.clear_selection()
    
    def _get_legal_destinations(self, from_square: int) -> List[int]:
        """Get all squares this piece can legally move to."""
        destinations = []
        for move in self.board.legal_moves:
            if move.from_square == from_square:
                destinations.append(move.to_square)
        return destinations
    
    def _create_move(self, from_sq: int, to_sq: int) -> chess.Move:
        """
        Create a Move object, handling pawn promotion.
        Auto-promotes to Queen for simplicity (standard in casual play).
        """
        piece = self.board.piece_at(from_sq)
        
        # Check for pawn promotion
        if piece and piece.piece_type == chess.PAWN:
            to_rank = chess.square_rank(to_sq)
            if (piece.color == chess.WHITE and to_rank == 7) or \
               (piece.color == chess.BLACK and to_rank == 0):
                return chess.Move(from_sq, to_sq, promotion=chess.QUEEN)
        
        return chess.Move(from_sq, to_sq)


# =============================================================================
# MAIN WINDOW — Game Orchestration
# =============================================================================

class MainWindow(QMainWindow):
    """
    Main application window. Orchestrates the game loop.
    
    This is the GUI equivalent of play_game() in main.py.
    It coordinates between:
    - ChessBoardWidget (user input)
    - ChessEngine (analysis and engine moves)  
    - instructor.assess_move() (grading)
    - Display panels (output)
    """
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Chess Instructor — Phase 2 MVP")
        
        # Core state
        self.board = chess.Board()
        self.engine: Optional[ChessEngine] = None
        self.player_is_white = True  # Locked for MVP
        
        # Undo state: stores FEN before player's move
        # Only ONE level of undo — stores state before the last (player + engine) move pair
        self.undo_fen: Optional[str] = None
        
        # Build UI components
        self._create_ui()
        
        # Initialize engine (uses existing ChessEngine class)
        self._init_engine()
        
        # Set initial state
        self.board_widget.set_board(self.board)
        self._update_status("White to move")
        self._show_message("Game ready. Click a piece to select, then click destination.")
    
    def _create_ui(self) -> None:
        """Build the window layout."""
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Horizontal layout: board on left, info panel on right
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(20)
        
        # --- Chess Board ---
        self.board_widget = ChessBoardWidget()
        self.board_widget.on_move_callback = self._handle_player_move
        main_layout.addWidget(self.board_widget)
        
        # --- Info Panel ---
        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_panel.setFixedWidth(320)
        
        # Status label (whose turn, check, game over)
        self.status_label = QLabel("Starting...")
        self.status_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.status_label.setWordWrap(True)
        info_layout.addWidget(self.status_label)
        
        # Assessment display (main feedback area)
        self.assessment_display = QTextEdit()
        self.assessment_display.setReadOnly(True)
        self.assessment_display.setFont(QFont("Consolas", 10))
        self.assessment_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, 
            QSizePolicy.Policy.Expanding
        )
        info_layout.addWidget(self.assessment_display)
        
        # Buttons
        self.undo_button = QPushButton("⟲ Undo Move")
        self.undo_button.clicked.connect(self._handle_undo)
        self.undo_button.setEnabled(False)  # Disabled until a move is made
        info_layout.addWidget(self.undo_button)
        
        new_game_btn = QPushButton("New Game")
        new_game_btn.clicked.connect(self._handle_new_game)
        info_layout.addWidget(new_game_btn)
        
        main_layout.addWidget(info_panel)
    
    def _init_engine(self) -> None:
        """
        Start the Stockfish engine.
        Uses ChessEngine.start() directly (not context manager) 
        because GUI needs persistent access across multiple moves.
        """
        try:
            self.engine = ChessEngine(STOCKFISH_PATH, depth=ENGINE_DEPTH)
            self.engine.start()
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "Engine Not Found",
                f"Stockfish not found at:\n{STOCKFISH_PATH}\n\n"
                "Please update STOCKFISH_PATH in gui.py"
            )
            self.engine = None
        except Exception as e:
            QMessageBox.critical(self, "Engine Error", f"Failed to start engine:\n{e}")
            self.engine = None
    
    # -------------------------------------------------------------------------
    # Status and Display Updates
    # -------------------------------------------------------------------------
    
    def _update_status(self, text: str) -> None:
        """Update the status label."""
        self.status_label.setText(text)
    
    def _show_message(self, text: str) -> None:
        """Display plain text in assessment area."""
        self.assessment_display.setPlainText(text)
    
    def _show_assessment(self, board_before: chess.Board, assessment) -> None:
        """
        Format and display move assessment as HTML.
        
        IMPORTANT: SAN conversion happens HERE using board_before,
        which is the board state BEFORE the player's move.
        This is the correct context for move notation.
        """
        # Convert moves to SAN using pre-move board state
        move_san = board_before.san(assessment.move_played)
        
        # Handle best_move being None (rare edge case)
        if assessment.best_move is not None:
            best_san = board_before.san(assessment.best_move)
        else:
            best_san = None
        
        # Format evaluation (centipawns → pawns)
        eval_before = assessment.eval_initial / 100
        eval_after = assessment.eval_final / 100
        
        # Grade color
        grade_color = GRADE_COLORS.get(assessment.grade, "#000000")
        
        # Build HTML
        html = f"""
        <div style="font-family: Consolas, monospace;">
        <p><b>Your move:</b> <span style="font-size: 14pt;">{move_san}</span></p>
        <p><b>Eval:</b> {eval_before:+.2f} → {eval_after:+.2f}</p>
        <p><b>Grade:</b> <span style="color: {grade_color}; font-weight: bold; font-size: 12pt;">
            {assessment.grade.name}</span></p>
        """
        
        if not assessment.was_best_move and best_san is not None:
            html += f'<p><b>Best was:</b> {best_san}</p>'
        
        html += f'<p style="margin-top: 10px;">{assessment.explanation}</p>'
        html += "</div>"
        
        self.assessment_display.setHtml(html)
    
    def _append_engine_move(self, move_san: str) -> None:
        """Append engine's move to the assessment display."""
        current = self.assessment_display.toHtml()
        self.assessment_display.setHtml(
            current + f'<p><b>Engine plays:</b> <span style="font-size: 14pt;">{move_san}</span></p>'
        )
    
    def _check_game_over(self) -> bool:
        """
        Check if game has ended and update status accordingly.
        Returns True if game is over, False otherwise.
        """
        if not self.board.is_game_over():
            return False
        
        # Disable board interaction
        self.board_widget.set_interaction_enabled(False)
        
        # Determine result and display
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            self._update_status(f"Checkmate! {winner} wins!")
        elif self.board.is_stalemate():
            self._update_status("Draw by stalemate")
        elif self.board.is_insufficient_material():
            self._update_status("Draw — insufficient material")
        elif self.board.can_claim_fifty_moves():
            self._update_status("Draw — fifty move rule")
        elif self.board.is_repetition():
            self._update_status("Draw — threefold repetition")
        else:
            self._update_status(f"Game over: {self.board.result()}")
        
        return True
    
    # -------------------------------------------------------------------------
    # Core Game Flow
    # -------------------------------------------------------------------------
    
    def _handle_player_move(self, move: chess.Move) -> None:
        """
        Process player's move through the full analysis pipeline.
        
        COMPLETE FLOW:
        a) Save undo state (FEN before any changes)
        b) Analyze position BEFORE player move
        c) Analyze position AFTER player move (on a copy)
        d) Call assess_move() from instructor
        e) Display assessment to player
        f) Apply player move to actual board
        g) Update board widget with player's move highlight
        h) Check if player's move ended the game
        i) If not game over: engine makes its move
        j) Update board widget with engine's move highlight
        k) Check if engine's move ended the game
        l) Update status for next turn
        """
        # Guard: no engine available
        if self.engine is None:
            self._show_message("Engine not available. Cannot analyze moves.")
            return
        
        # Guard: game already over
        if self.board.is_game_over():
            return
        
        # ===== (a) SAVE UNDO STATE =====
        # Store FEN before any changes so we can restore later
        self.undo_fen = self.board.fen()
        
        # ===== (b) ANALYZE BEFORE PLAYER MOVE =====
        # Get evaluation and best move for current position
        analysis_before = self.engine.analyze(self.board)
        
        # Keep a copy of board state for SAN conversion later
        # (need pre-move state to generate correct notation)
        board_before = self.board.copy()
        
        # ===== (c) ANALYZE AFTER PLAYER MOVE =====
        # Apply move to a COPY to get post-move evaluation
        board_after = self.board.copy()
        board_after.push(move)
        analysis_after = self.engine.analyze(board_after)
        
        # ===== (d) CALL ASSESS_MOVE FROM INSTRUCTOR =====
        # This is the existing instructor logic — GUI does NOT grade
        assessment = assess_move(
            move_played=move,
            eval_initial=analysis_before.cp_score_white,
            eval_final=analysis_after.cp_score_white,
            best_move=analysis_before.best_move,
            player_is_white=self.player_is_white,
            board_before=board_before,
            board_after=board_after
        )

        
        # ===== (e) DISPLAY ASSESSMENT =====
        # SAN conversion happens here with correct board state
        self._show_assessment(board_before, assessment)
        
        # ===== (f) APPLY PLAYER MOVE TO ACTUAL BOARD =====
        self.board.push(move)
        
        # ===== (g) UPDATE BOARD WIDGET =====
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(move)
        
        # ===== (h) CHECK IF PLAYER'S MOVE ENDED GAME =====
        if self._check_game_over():
            # Game over — enable undo so player can try different move
            self.undo_button.setEnabled(True)
            return
        
        # ===== (i) ENGINE MAKES ITS MOVE =====
        self._update_status("Engine thinking...")
        self.board_widget.set_interaction_enabled(False)
        
        # Force UI update so "thinking" message appears before blocking call
        QApplication.processEvents()
        
        # Get and apply engine's move
        engine_move = self.engine.get_move(self.board, time_limit=ENGINE_MOVE_TIME)
        
        # Guard: engine failed to return a move (shouldn't happen, but be safe)
        if engine_move is None:
            self._update_status("Engine error — White to move")
            self.board_widget.set_interaction_enabled(True)
            self.undo_button.setEnabled(True)
            return
        
        # Get SAN BEFORE pushing (need current board state for notation)
        engine_san = self.board.san(engine_move)
        
        # Apply engine move
        self.board.push(engine_move)
        
        # ===== (j) UPDATE BOARD WIDGET WITH ENGINE MOVE =====
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(engine_move)
        self._append_engine_move(engine_san)
        
        # ===== (k) CHECK IF ENGINE'S MOVE ENDED GAME =====
        if self._check_game_over():
            self.undo_button.setEnabled(True)
            return
        
        # ===== (l) UPDATE STATUS FOR NEXT TURN =====
        self.board_widget.set_interaction_enabled(True)
        self.undo_button.setEnabled(True)
        
        if self.board.is_check():
            self._update_status("White to move — CHECK")
        else:
            self._update_status("White to move")
    
    # -------------------------------------------------------------------------
    # Undo and New Game
    # -------------------------------------------------------------------------
    
    def _handle_undo(self) -> None:
        """
        Undo the last move pair (player move + engine response).
        
        Only ONE level of undo:
        - Restores board to state before player's last move
        - Clears undo state (can't undo again until next move)
        - Re-enables board interaction
        """
        # Guard: no undo state available
        if self.undo_fen is None:
            return
        
        # Restore board to pre-move state
        self.board = chess.Board(self.undo_fen)
        
        # Update widget
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)  # Clear last move highlight
        self.board_widget.set_interaction_enabled(True)
        
        # Clear undo state — only one level allowed
        self.undo_fen = None
        self.undo_button.setEnabled(False)
        
        # Update display
        self._update_status("White to move")
        self._show_message("Move undone. Your turn.")
    
    def _handle_new_game(self) -> None:
        """Reset everything to starting position."""
        # Reset board
        self.board = chess.Board()
        
        # Update widget
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_interaction_enabled(True)
        
        # Clear undo state
        self.undo_fen = None
        self.undo_button.setEnabled(False)
        
        # Update display
        self._update_status("White to move")
        self._show_message("New game started. Click a piece to begin.")
    
    # -------------------------------------------------------------------------
    # Cleanup — CRITICAL for proper engine shutdown
    # -------------------------------------------------------------------------
    
    def closeEvent(self, event) -> None:
        """
        Clean up resources when window is closed.
        
        CRITICAL: Engine runs as a subprocess. If we don't call stop(),
        Stockfish will keep running as a zombie process, consuming memory.
        """
        if self.engine is not None:
            try:
                self.engine.stop()
            except Exception:
                # Ignore errors during shutdown — we're closing anyway
                pass
            self.engine = None
        
        # Accept the close event (allows window to close)
        event.accept()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """Launch the GUI application."""
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    # Start Qt event loop — blocks until window is closed
    sys.exit(app.exec())


if __name__ == "__main__":
    main()