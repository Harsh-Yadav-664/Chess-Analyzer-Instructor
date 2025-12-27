"""
Minimal GUI shell for AI Chess Instructor.
"""

import sys
import chess
from typing import Optional, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush

from engine import ChessEngine
from instructor import (
    assess_move,
    analyze_pre_move_threats,
    reset_adaptive_state,
    update_adaptive_state,
    MoveGrade
)


# =========================
# CONFIG
# =========================

STOCKFISH_PATH = r"D:\CODE\PROJECTS\Chess Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe"
ENGINE_DEPTH = 15
ENGINE_MOVE_TIME = 1.0


# =========================
# VISUALS
# =========================

LIGHT_SQUARE = QColor(240, 217, 181)
DARK_SQUARE = QColor(181, 136, 99)
HIGHLIGHT_SQUARE = QColor(130, 151, 105)
LAST_MOVE_HIGHLIGHT = QColor(205, 210, 106)
LEGAL_MOVE_DOT = QColor(0, 0, 0, 50)

PIECE_UNICODE = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
}

GRADE_COLORS = {
    MoveGrade.BEST: "#22c55e",
    MoveGrade.EXCELLENT: "#22c55e",
    MoveGrade.GOOD: "#3b82f6",
    MoveGrade.INACCURACY: "#eab308",
    MoveGrade.MISTAKE: "#ef4444",
    MoveGrade.BLUNDER: "#a855f7",
}


# =========================
# BOARD WIDGET
# =========================

class ChessBoardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.board: Optional[chess.Board] = None
        self.selected_square = None
        self.legal_destinations: List[int] = []
        self.last_move = None
        self.on_move_callback = None
        self.interaction_enabled = True

        self.square_size = 64
        self.setFixedSize(8 * self.square_size, 8 * self.square_size)

    def set_board(self, board: chess.Board):
        self.board = board
        self.selected_square = None
        self.legal_destinations = []
        self.update()

    def set_last_move(self, move):
        self.last_move = move
        self.update()

    def set_interaction_enabled(self, enabled):
        self.interaction_enabled = enabled
        if not enabled:
            self.selected_square = None
            self.legal_destinations = []
            self.update()

    def paintEvent(self, _):
        if not self.board:
            return

        painter = QPainter(self)

        for sq in chess.SQUARES:
            self._draw_square(painter, sq)

        for sq in self.legal_destinations:
            self._draw_dot(painter, sq)

        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece:
                self._draw_piece(painter, sq, piece)

        painter.end()

    def _draw_square(self, painter, sq):
        x = chess.square_file(sq) * self.square_size
        y = (7 - chess.square_rank(sq)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)

        if self.last_move and sq in (self.last_move.from_square, self.last_move.to_square):
            color = LAST_MOVE_HIGHLIGHT
        elif sq == self.selected_square:
            color = HIGHLIGHT_SQUARE
        else:
            color = LIGHT_SQUARE if (chess.square_file(sq) + chess.square_rank(sq)) % 2 else DARK_SQUARE

        painter.fillRect(rect, color)

    def _draw_dot(self, painter, sq):
        cx = chess.square_file(sq) * self.square_size + self.square_size // 2
        cy = (7 - chess.square_rank(sq)) * self.square_size + self.square_size // 2
        painter.setBrush(QBrush(LEGAL_MOVE_DOT))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - 10, cy - 10, 20, 20)

    def _draw_piece(self, painter, sq, piece):
        x = chess.square_file(sq) * self.square_size
        y = (7 - chess.square_rank(sq)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)

        painter.setFont(QFont("Segoe UI Symbol", 40))
        painter.setPen(QColor(255, 255, 255) if piece.color else QColor(0, 0, 0))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, PIECE_UNICODE[piece.symbol()])

    def mousePressEvent(self, event):
        if not self.interaction_enabled or not self.board or self.board.turn != chess.WHITE:
            return

        file = int(event.position().x() // self.square_size)
        rank = 7 - int(event.position().y() // self.square_size)
        if not (0 <= file <= 7 and 0 <= rank <= 7):
            return

        sq = chess.square(file, rank)

        if sq in self.legal_destinations:
            from_sq = self.selected_square
            to_sq = sq
            
            # Handle promotion
            piece = self.board.piece_at(from_sq)
            if piece and piece.piece_type == chess.PAWN:
                to_rank = chess.square_rank(to_sq)
                if (piece.color == chess.WHITE and to_rank == 7) or \
                   (piece.color == chess.BLACK and to_rank == 0):
                    move = chess.Move(from_sq, to_sq, promotion=chess.QUEEN)
                else:
                    move = chess.Move(from_sq, to_sq)
            else:
                move = chess.Move(from_sq, to_sq)
            
            self.selected_square = None
            self.legal_destinations = []
            self.update()
            if self.on_move_callback:
                self.on_move_callback(move)
            return

        piece = self.board.piece_at(sq)
        if piece and piece.color == chess.WHITE:
            self.selected_square = sq
            self.legal_destinations = [
                m.to_square for m in self.board.legal_moves if m.from_square == sq
            ]
            self.update()
        else:
            self.selected_square = None
            self.legal_destinations = []
            self.update()


# =========================
# MAIN WINDOW
# =========================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Chess Instructor")

        self.instructor_mode = "learning"
        self.board = chess.Board()
        self.engine: Optional[ChessEngine] = None
        self.player_is_white = True
        self.undo_fen = None

        self._build_ui()
        self._init_engine()
        
        self.board_widget.set_board(self.board)
        self._update_status("White to move")
        self._show_message("Game ready. Click a piece to start.")

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setSpacing(20)

        self.board_widget = ChessBoardWidget()
        self.board_widget.on_move_callback = self._handle_player_move
        layout.addWidget(self.board_widget)

        side = QVBoxLayout()
        layout.addLayout(side)

        self.status = QLabel("Starting...")
        self.status.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.status.setWordWrap(True)
        side.addWidget(self.status)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        side.addWidget(self.output)

        self.undo_btn = QPushButton("Undo Move")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self._undo)
        side.addWidget(self.undo_btn)

        new_game_btn = QPushButton("New Game")
        new_game_btn.clicked.connect(self._new_game)
        side.addWidget(new_game_btn)

    def _init_engine(self):
        try:
            self.engine = ChessEngine(STOCKFISH_PATH, depth=ENGINE_DEPTH)
            self.engine.start()
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "Engine Not Found",
                f"Stockfish not found at:\n{STOCKFISH_PATH}\n\nPlease update STOCKFISH_PATH in gui.py"
            )
            self.engine = None
        except Exception as e:
            QMessageBox.critical(self, "Engine Error", f"Failed to start engine:\n{e}")
            self.engine = None

    def _update_status(self, text):
        self.status.setText(text)

    def _show_message(self, text):
        self.output.setPlainText(text)

    def _check_game_over(self):
        if not self.board.is_game_over():
            return False
        
        self.board_widget.set_interaction_enabled(False)
        
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            self._update_status(f"Checkmate! {winner} wins!")
        elif self.board.is_stalemate():
            self._update_status("Draw by stalemate")
        elif self.board.is_insufficient_material():
            self._update_status("Draw - insufficient material")
        else:
            self._update_status(f"Game over: {self.board.result()}")
        
        return True

    def _handle_player_move(self, move):
        if self.engine is None:
            self._show_message("Engine not available.")
            return

        if self.board.is_game_over():
            return

        # Pre-move warning
        warning = analyze_pre_move_threats(
            self.board,
            chess.WHITE if self.player_is_white else chess.BLACK,
            self.instructor_mode
        )

        self.undo_fen = self.board.fen()

        # Analyze before
        analysis_before = self.engine.analyze(self.board)
        board_before = self.board.copy()

        # Analyze after
        board_after = self.board.copy()
        board_after.push(move)
        analysis_after = self.engine.analyze(board_after)

        # Get assessment
        assessment = assess_move(
            move_played=move,
            eval_initial=analysis_before.cp_score_white,
            eval_final=analysis_after.cp_score_white,
            best_move=analysis_before.best_move,
            player_is_white=self.player_is_white,
            board_before=board_before,
            board_after=board_after,
            engine=self.engine
        )

        # Update adaptive state
        update_adaptive_state(assessment.grade)

        # Get SAN before pushing
        move_san = self.board.san(move)
        best_san = None
        if assessment.best_move and assessment.best_move != move:
            try:
                best_san = self.board.san(assessment.best_move)
            except:
                pass

        # Build display
        grade_color = GRADE_COLORS.get(assessment.grade, "#000000")
        
        html = f"<b>Your move:</b> {move_san}<br>"
        html += f"<b>Eval:</b> {assessment.eval_initial/100:+.2f} → {assessment.eval_final/100:+.2f}<br>"
        html += f"<b>Grade:</b> <span style='color:{grade_color}'>{assessment.grade.name}</span><br>"
        
        if best_san and not assessment.was_best_move:
            html += f"<b>Best was:</b> {best_san}<br>"
        
        html += f"<br>{assessment.explanation}"
        
        if warning:
            html = f"<i>Note: {warning}</i><br><br>" + html

        self.output.setHtml(html)

        # Apply move
        self.board.push(move)
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(move)

        if self._check_game_over():
            self.undo_btn.setEnabled(True)
            return

        # Engine's turn
        self._update_status("Engine thinking...")
        self.board_widget.set_interaction_enabled(False)
        QApplication.processEvents()

        engine_move = self.engine.get_move(self.board, time_limit=ENGINE_MOVE_TIME)
        
        if engine_move:
            engine_san = self.board.san(engine_move)
            self.board.push(engine_move)
            self.board_widget.set_board(self.board)
            self.board_widget.set_last_move(engine_move)
            
            current_html = self.output.toHtml()
            self.output.setHtml(current_html + f"<br><b>Engine plays:</b> {engine_san}")

        self.board_widget.set_interaction_enabled(True)
        self.undo_btn.setEnabled(True)

        if not self._check_game_over():
            if self.board.is_check():
                self._update_status("White to move - CHECK")
            else:
                self._update_status("White to move")

    def _undo(self):
        if not self.undo_fen:
            return

        self.board = chess.Board(self.undo_fen)
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_interaction_enabled(True)
        self.undo_fen = None
        self.undo_btn.setEnabled(False)
        self._show_message("Move undone.")
        self._update_status("White to move")

    def _new_game(self):
        self.board = chess.Board()
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_interaction_enabled(True)
        self.undo_fen = None
        self.undo_btn.setEnabled(False)
        reset_adaptive_state()
        self._update_status("White to move")
        self._show_message("New game started.")

    def closeEvent(self, event):
        if self.engine:
            try:
                self.engine.stop()
            except:
                pass
        event.accept()


# =========================
# ENTRY
# =========================

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()