"""
Minimal GUI shell for AI Chess Instructor.
"""

import sys
import math
import chess
from typing import Optional, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QTextEdit, QMessageBox, QDialog, QDialogButtonBox,
    QComboBox, QGroupBox
)
from PyQt6.QtCore import Qt, QRect, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QPolygonF

from engine import ChessEngine
from instructor import (
    assess_move,
    analyze_pre_move_threats,
    reset_adaptive_state,
    get_current_mode,
    MoveGrade
)
from stats import (
    start_game,
    record_move,
    end_game,
    get_profile_summary,
    get_training_suggestion,
    reset_profile,
    get_session
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
# PROFILE DIALOG
# =========================

class ProfileDialog(QDialog):
    """Dialog to show player profile and training suggestions."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Player Profile")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        layout = QVBoxLayout(self)
        
        # Profile summary
        profile_group = QGroupBox("Profile Summary")
        profile_layout = QVBoxLayout(profile_group)
        self.profile_label = QLabel()
        self.profile_label.setWordWrap(True)
        self.profile_label.setFont(QFont("Arial", 11))
        profile_layout.addWidget(self.profile_label)
        layout.addWidget(profile_group)
        
        # Training suggestion
        training_group = QGroupBox("Training Suggestion")
        training_layout = QVBoxLayout(training_group)
        self.training_label = QLabel()
        self.training_label.setWordWrap(True)
        self.training_label.setFont(QFont("Arial", 11))
        training_layout.addWidget(self.training_label)
        layout.addWidget(training_group)
        
        # Session stats
        stats_group = QGroupBox("Current Session")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        self.stats_label.setFont(QFont("Arial", 10))
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(stats_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        reset_btn = QPushButton("Reset Profile")
        reset_btn.clicked.connect(self._reset_profile)
        button_layout.addWidget(reset_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        self._refresh()
    
    def _refresh(self):
        profile_text = get_profile_summary()
        self.profile_label.setText(profile_text if profile_text else "No data yet.")
        
        suggestion = get_training_suggestion()
        self.training_label.setText(suggestion if suggestion else "Play more games to get suggestions.")
        
        session = get_session()
        if session.current_game:
            stats = session.current_game
            self.stats_label.setText(
                f"Current game: {stats.move_count} moves\n"
                f"Blunders: {stats.get_blunder_count()} | "
                f"Mistakes: {stats.get_mistake_count()} | "
                f"Inaccuracies: {stats.get_inaccuracy_count()}"
            )
        else:
            self.stats_label.setText("No game in progress.")
    
    def _reset_profile(self):
        reply = QMessageBox.question(
            self,
            "Reset Profile",
            "Are you sure you want to reset all historical data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            reset_profile()
            self._refresh()


# =========================
# GAME SUMMARY DIALOG
# =========================

class GameSummaryDialog(QDialog):
    """Dialog shown at end of game with summary and feedback."""
    
    def __init__(self, feedback: dict, result: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Game Summary")
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        
        # Result
        result_label = QLabel(f"Result: {result}")
        result_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(result_label)
        
        layout.addSpacing(10)
        
        # Stats
        stats_text = (
            f"Total moves: {feedback.get('total_moves', 0)}\n"
            f"Blunders: {feedback.get('blunders', 0)}\n"
            f"Mistakes: {feedback.get('mistakes', 0)}\n"
            f"Inaccuracies: {feedback.get('inaccuracies', 0)}\n"
            f"Good moves: {feedback.get('good_moves', 0)}"
        )
        stats_label = QLabel(stats_text)
        stats_label.setFont(QFont("Consolas", 11))
        layout.addWidget(stats_label)
        
        layout.addSpacing(10)
        
        # Summary
        summary_group = QGroupBox("Analysis")
        summary_layout = QVBoxLayout(summary_group)
        summary_label = QLabel(feedback.get('summary', ''))
        summary_label.setWordWrap(True)
        summary_label.setFont(QFont("Arial", 11))
        summary_layout.addWidget(summary_label)
        layout.addWidget(summary_group)
        
        # Training suggestion
        suggestion = get_training_suggestion()
        if suggestion:
            suggestion_group = QGroupBox("Suggestion")
            suggestion_layout = QVBoxLayout(suggestion_group)
            suggestion_label = QLabel(suggestion)
            suggestion_label.setWordWrap(True)
            suggestion_label.setFont(QFont("Arial", 11))
            suggestion_layout.addWidget(suggestion_label)
            layout.addWidget(suggestion_group)
        
        # Close button
        close_btn = QPushButton("OK")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


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
        self.visual_cues = None
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

    def set_visual_cues(self, cues):
        self.visual_cues = cues
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

        # Draw highlights BEFORE pieces
        if self.visual_cues:
            highlights = self.visual_cues.get("highlights", [])
            for h in highlights:
                try:
                    self._draw_highlight(painter, h["square"], h["type"])
                except:
                    pass

        for sq in self.legal_destinations:
            self._draw_dot(painter, sq)

        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece:
                self._draw_piece(painter, sq, piece)

        # Draw arrows AFTER pieces
        if self.visual_cues:
            arrows = self.visual_cues.get("arrows", [])
            for a in arrows:
                try:
                    self._draw_arrow(painter, a["from"], a["to"], a["type"])
                except:
                    pass

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

    def _draw_highlight(self, painter, square, highlight_type):
        x = chess.square_file(square) * self.square_size
        y = (7 - chess.square_rank(square)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)
        
        if highlight_type == "danger":
            color = QColor(255, 0, 0, 100)
        else:
            color = QColor(255, 165, 0, 100)
        
        painter.fillRect(rect, color)

    def _draw_arrow(self, painter, from_sq, to_sq, arrow_type):
        from_x = chess.square_file(from_sq) * self.square_size + self.square_size // 2
        from_y = (7 - chess.square_rank(from_sq)) * self.square_size + self.square_size // 2
        to_x = chess.square_file(to_sq) * self.square_size + self.square_size // 2
        to_y = (7 - chess.square_rank(to_sq)) * self.square_size + self.square_size // 2
        
        if arrow_type == "best":
            color = QColor(0, 200, 0, 180)
        else:
            color = QColor(255, 0, 0, 180)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        
        dx = to_x - from_x
        dy = to_y - from_y
        length = math.sqrt(dx * dx + dy * dy)
        
        if length < 5:
            return
        
        angle = math.atan2(dy, dx)
        
        shaft_width = 8
        head_width = 20
        head_length = 15
        
        shaft_end = length - head_length
        
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        perp_x = -sin_a * shaft_width / 2
        perp_y = cos_a * shaft_width / 2
        
        points = QPolygonF()
        points.append(QPointF(from_x + perp_x, from_y + perp_y))
        points.append(QPointF(from_x - perp_x, from_y - perp_y))
        points.append(QPointF(from_x + cos_a * shaft_end - perp_x, from_y + sin_a * shaft_end - perp_y))
        points.append(QPointF(from_x + cos_a * shaft_end + perp_y * head_width / shaft_width, 
                            from_y + sin_a * shaft_end - perp_x * head_width / shaft_width))
        points.append(QPointF(to_x, to_y))
        points.append(QPointF(from_x + cos_a * shaft_end - perp_y * head_width / shaft_width, 
                            from_y + sin_a * shaft_end + perp_x * head_width / shaft_width))
        points.append(QPointF(from_x + cos_a * shaft_end + perp_x, from_y + sin_a * shaft_end + perp_y))
        
        painter.drawPolygon(points)

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

        self.instructor_mode = "adaptive"
        self.board = chess.Board()
        self.engine: Optional[ChessEngine] = None
        self.player_is_white = True
        self.undo_fen = None
        self.game_active = False

        self._build_ui()
        self._init_engine()
        
        self.board_widget.set_board(self.board)
        self._start_new_game()

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

        # Status
        self.status = QLabel("Starting...")
        self.status.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.status.setWordWrap(True)
        side.addWidget(self.status)

        # Mode selector
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Mode:")
        mode_label.setFont(QFont("Arial", 10))
        mode_layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["adaptive", "learning", "easy", "medium", "hard"])
        self.mode_combo.setCurrentText(self.instructor_mode)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        side.addLayout(mode_layout)

        # Output
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        side.addWidget(self.output)

        # Game stats bar
        self.stats_bar = QLabel("")
        self.stats_bar.setFont(QFont("Arial", 9))
        self.stats_bar.setStyleSheet("color: #666;")
        side.addWidget(self.stats_bar)

        # Buttons
        btn_layout1 = QHBoxLayout()
        
        self.undo_btn = QPushButton("Undo Move")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self._undo)
        btn_layout1.addWidget(self.undo_btn)

        new_game_btn = QPushButton("New Game")
        new_game_btn.clicked.connect(self._new_game)
        btn_layout1.addWidget(new_game_btn)
        
        side.addLayout(btn_layout1)

        btn_layout2 = QHBoxLayout()
        
        profile_btn = QPushButton("Player Profile")
        profile_btn.clicked.connect(self._show_profile)
        btn_layout2.addWidget(profile_btn)
        
        side.addLayout(btn_layout2)

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

    def _on_mode_changed(self, mode: str):
        self.instructor_mode = mode
        self._update_status_display()

    def _update_status_display(self):
        mode_display = self._get_mode_display()
        if self.board.is_check():
            self._update_status(f"White to move - CHECK | Mode: {mode_display}")
        else:
            self._update_status(f"White to move | Mode: {mode_display}")

    def _update_status(self, text):
        self.status.setText(text)

    def _get_mode_display(self):
        if self.instructor_mode == "adaptive":
            return f"adaptive ({get_current_mode()})"
        return self.instructor_mode

    def _show_message(self, text):
        self.output.setPlainText(text)

    def _update_stats_bar(self):
        session = get_session()
        if session.current_game:
            stats = session.current_game
            self.stats_bar.setText(
                f"Moves: {stats.move_count} | "
                f"Blunders: {stats.get_blunder_count()} | "
                f"Mistakes: {stats.get_mistake_count()} | "
                f"Good: {stats.get_good_move_count()}"
            )
        else:
            self.stats_bar.setText("")

    def _show_profile(self):
        dialog = ProfileDialog(self)
        dialog.exec()

    def _start_new_game(self):
        start_game()
        self.game_active = True
        self._update_status(f"White to move | Mode: {self._get_mode_display()}")
        self._show_message("Game ready. Click a piece to start.")
        self._update_stats_bar()

    def _check_game_over(self):
        if not self.board.is_game_over():
            return False
        
        self.board_widget.set_interaction_enabled(False)
        self.game_active = False
        
        result = self.board.result()
        
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            self._update_status(f"Checkmate! {winner} wins!")
        elif self.board.is_stalemate():
            self._update_status("Draw by stalemate")
        elif self.board.is_insufficient_material():
            self._update_status("Draw - insufficient material")
        else:
            self._update_status(f"Game over: {result}")
        
        # End game and get feedback
        feedback = end_game(result)
        
        # Show game summary dialog
        dialog = GameSummaryDialog(feedback, result, self)
        dialog.exec()
        
        # Also update output panel
        summary = feedback.get('summary', '')
        self.output.append(f"\n\n<b>Game Summary:</b><br>{summary}")
        
        return True

    def _handle_player_move(self, move):
        if self.engine is None:
            self._show_message("Engine not available.")
            return

        if self.board.is_game_over():
            return

        warning = analyze_pre_move_threats(
            self.board,
            chess.WHITE if self.player_is_white else chess.BLACK,
            self.instructor_mode
        )

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

        # Record move for stats
        record_move(assessment.grade, assessment.explanation)
        self._update_stats_bar()

        move_san = self.board.san(move)
        best_san = None
        if assessment.best_move and assessment.best_move != move:
            try:
                best_san = self.board.san(assessment.best_move)
            except:
                pass

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

        # Set visual cues from assessment
        if assessment.visual_cues:
            self.board_widget.set_visual_cues(assessment.visual_cues)
        else:
            self.board_widget.set_visual_cues(None)

        self.board.push(move)
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(move)

        if self._check_game_over():
            self.undo_btn.setEnabled(True)
            return

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
            self._update_status_display()

    def _undo(self):
        if not self.undo_fen:
            return

        self.board = chess.Board(self.undo_fen)
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_visual_cues(None)
        self.board_widget.set_interaction_enabled(True)
        self.undo_fen = None
        self.undo_btn.setEnabled(False)
        self._show_message("Move undone.")
        self._update_status_display()

    def _new_game(self):
        # If game is active, end it first
        if self.game_active:
            end_game(None)
        
        self.board = chess.Board()
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_visual_cues(None)
        self.board_widget.set_interaction_enabled(True)
        self.undo_fen = None
        self.undo_btn.setEnabled(False)
        reset_adaptive_state()
        
        self._start_new_game()

    def closeEvent(self, event):
        # End current game if active
        if self.game_active:
            end_game(None)
        
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