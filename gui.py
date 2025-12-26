"""
Minimal GUI shell for AI Chess Instructor.
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


STOCKFISH_PATH = r"D:\CODE\PROJECTS\Chess Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe"
ENGINE_DEPTH = 15
ENGINE_MOVE_TIME = 1.0


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


class ChessBoardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.board: Optional[chess.Board] = None
        self.selected_square: Optional[int] = None
        self.legal_destinations: List[int] = []
        self.last_move: Optional[chess.Move] = None
        self.on_move_callback = None
        self.interaction_enabled = True

        self.square_size = 64
        self.setFixedSize(8 * self.square_size, 8 * self.square_size)

    def set_board(self, board: chess.Board) -> None:
        self.board = board
        self.clear_selection()
        self.update()

    def set_last_move(self, move: Optional[chess.Move]) -> None:
        self.last_move = move
        self.update()

    def set_interaction_enabled(self, enabled: bool) -> None:
        self.interaction_enabled = enabled
        if not enabled:
            self.clear_selection()

    def clear_selection(self) -> None:
        self.selected_square = None
        self.legal_destinations = []
        self.update()

    def paintEvent(self, event) -> None:
        if self.board is None:
            return

        painter = QPainter(self)

        for square in chess.SQUARES:
            self._draw_square(painter, square)

        for square in self.legal_destinations:
            self._draw_legal_move_dot(painter, square)

        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece:
                self._draw_piece(painter, square, piece)

        painter.end()

    def _draw_square(self, painter, square):
        x = chess.square_file(square) * self.square_size
        y = (7 - chess.square_rank(square)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)

        if square == self.selected_square:
            color = HIGHLIGHT_SQUARE
        elif self.last_move and square in (self.last_move.from_square, self.last_move.to_square):
            color = LAST_MOVE_HIGHLIGHT
        else:
            color = LIGHT_SQUARE if (chess.square_file(square) + chess.square_rank(square)) % 2 else DARK_SQUARE

        painter.fillRect(rect, color)

    def _draw_legal_move_dot(self, painter, square):
        x = chess.square_file(square) * self.square_size + self.square_size // 2
        y = (7 - chess.square_rank(square)) * self.square_size + self.square_size // 2
        painter.setBrush(QBrush(LEGAL_MOVE_DOT))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(x - 10, y - 10, 20, 20)

    def _draw_piece(self, painter, square, piece):
        x = chess.square_file(square) * self.square_size
        y = (7 - chess.square_rank(square)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)
        painter.setFont(QFont("Segoe UI Symbol", 40))
        painter.setPen(QColor(255, 255, 255) if piece.color == chess.WHITE else QColor(0, 0, 0))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, PIECE_UNICODE[piece.symbol()])

    def mousePressEvent(self, event) -> None:
        if not self.interaction_enabled or self.board is None or self.board.turn != chess.WHITE:
            return

        file = int(event.position().x() // self.square_size)
        rank = 7 - int(event.position().y() // self.square_size)
        if not (0 <= file <= 7 and 0 <= rank <= 7):
            return

        square = chess.square(file, rank)

        if square in self.legal_destinations:
            move = chess.Move(self.selected_square, square)
            self.clear_selection()
            if self.on_move_callback:
                self.on_move_callback(move)
            return

        piece = self.board.piece_at(square)
        if piece and piece.color == self.board.turn:
            self.selected_square = square
            self.legal_destinations = [
                m.to_square for m in self.board.legal_moves if m.from_square == square
            ]
            self.update()
        else:
            self.clear_selection()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Chess Instructor")

        self.board = chess.Board()
        self.engine = None
        self.player_is_white = True
        self.undo_fen = None

        self._create_ui()
        self._init_engine()

        self.board_widget.set_board(self.board)
        self.status_label.setText("White to move")

    def _create_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        self.board_widget = ChessBoardWidget()
        self.board_widget.on_move_callback = self._handle_player_move
        layout.addWidget(self.board_widget)

        side = QVBoxLayout()
        layout.addLayout(side)

        self.status_label = QLabel()
        self.status_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        side.addWidget(self.status_label)

        self.assessment_display = QTextEdit()
        self.assessment_display.setReadOnly(True)
        side.addWidget(self.assessment_display)

        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self._handle_undo)
        self.undo_button.setEnabled(False)
        side.addWidget(self.undo_button)

    def _init_engine(self):
        self.engine = ChessEngine(STOCKFISH_PATH, depth=ENGINE_DEPTH)
        self.engine.start()

    def _handle_player_move(self, move: chess.Move) -> None:
        self.undo_fen = self.board.fen()

        analysis_before = self.engine.analyze(self.board)
        board_before = self.board.copy()

        board_after = self.board.copy()
        board_after.push(move)
        analysis_after = self.engine.analyze(board_after)

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

        self._show_assessment(board_before, assessment)

        self.board.push(move)
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(move)

        engine_move = self.engine.get_move(self.board, time_limit=ENGINE_MOVE_TIME)
        if engine_move:
            engine_san = self.board.san(engine_move)
            self.board.push(engine_move)
            self.board_widget.set_board(self.board)
            self.board_widget.set_last_move(engine_move)
            self.assessment_display.append(f"\nEngine plays: {engine_san}")

        self.undo_button.setEnabled(True)

    def _show_assessment(self, board_before, assessment):
        self.assessment_display.setHtml(
            f"<b>Grade:</b> {assessment.grade.name}<br>"
            f"<b>Explanation:</b> {assessment.explanation}"
        )

    def _handle_undo(self):
        if self.undo_fen:
            self.board = chess.Board(self.undo_fen)
            self.board_widget.set_board(self.board)
            self.undo_fen = None
            self.undo_button.setEnabled(False)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
