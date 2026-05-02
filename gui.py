"""
AI Chess Instructor - Premium Edition
Full featured chess training application with modern UI
All bugs fixed + Profile persistence implemented
"""

import sys
import math
import chess
import json
import os
from typing import Optional, List, Tuple
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QTextEdit, QMessageBox, QDialog,
    QComboBox, QGroupBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QRect, QPointF, QThread, pyqtSignal, QPoint, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QPolygonF, QPixmap, QPen, QIcon

from engine import ChessEngine, DIFFICULTY_PRESETS
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

# Profile persistence - saved in user's home directory
PROFILE_DIR = Path.home() / ".chess_instructor"
PROFILE_FILE = PROFILE_DIR / "profile.json"


# =========================
# PREMIUM VISUALS
# =========================

# Board colors - Premium style
LIGHT_SQUARE = QColor(240, 217, 181)
DARK_SQUARE = QColor(181, 136, 99)
HIGHLIGHT_SQUARE = QColor(130, 151, 105, 180)
LAST_MOVE_HIGHLIGHT = QColor(205, 210, 106, 140)
CHECK_HIGHLIGHT = QColor(220, 38, 38, 160)
LEGAL_MOVE_DOT = QColor(0, 0, 0, 60)

# Premium piece set
PIECE_UNICODE = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
}

GRADE_COLORS = {
    MoveGrade.BEST: "#10b981",
    MoveGrade.EXCELLENT: "#10b981",
    MoveGrade.GOOD: "#3b82f6",
    MoveGrade.INACCURACY: "#f59e0b",
    MoveGrade.MISTAKE: "#ef4444",
    MoveGrade.BLUNDER: "#a855f7",
}

# Theatre mode colors
THEATRE_BG = QColor(15, 15, 18)
PANEL_BG = QColor(24, 24, 27)
PANEL_BORDER = QColor(39, 39, 42)
TEXT_PRIMARY = QColor(250, 250, 250)
TEXT_SECONDARY = QColor(161, 161, 170)
ACCENT_GREEN = QColor(16, 185, 129)
ACCENT_BLUE = QColor(59, 130, 246)


# =========================
# PROFILE PERSISTENCE - FIXED
# =========================

def save_profile():
    """Save profile to persistent storage in user's home directory."""
    try:
        # Create directory if it doesn't exist
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        
        session = get_session()
        data = session.profile.to_dict()
        
        # Save with pretty formatting
        with open(PROFILE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✓ Profile saved to {PROFILE_FILE}")
        return True
    except Exception as e:
        print(f"✗ Failed to save profile: {e}")
        return False


def load_profile():
    """Load profile from persistent storage."""
    if not PROFILE_FILE.exists():
        print("ℹ No existing profile found, starting fresh")
        return False
    
    try:
        with open(PROFILE_FILE, 'r') as f:
            data = json.load(f)
        
        from stats import PlayerProfile
        session = get_session()
        session.profile = PlayerProfile.from_dict(data)
        
        print(f"✓ Profile loaded from {PROFILE_FILE}")
        print(f"  Games: {session.profile.games_played}, Moves: {session.profile.total_moves}")
        return True
    except Exception as e:
        print(f"✗ Failed to load profile: {e}")
        return False


# =========================
# PREMIUM PROFILE DIALOG
# =========================

class ProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Player Profile")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
            }
            QLabel {
                color: #fafafa;
            }
            QGroupBox {
                color: #fafafa;
                border: 2px solid #27272a;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
            }
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 8px 16px;
                color: #fafafa;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("📊 Player Statistics")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Profile file location info
        info_label = QLabel(f"📁 Profile saved at: {PROFILE_FILE}")
        info_label.setFont(QFont("Consolas", 8))
        info_label.setStyleSheet("color: #71717a; padding: 4px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        profile_group = QGroupBox("Profile Summary")
        profile_layout = QVBoxLayout(profile_group)
        self.profile_label = QLabel()
        self.profile_label.setWordWrap(True)
        self.profile_label.setFont(QFont("Arial", 11))
        profile_layout.addWidget(self.profile_label)
        layout.addWidget(profile_group)

        training_group = QGroupBox("Training Recommendation")
        training_layout = QVBoxLayout(training_group)
        self.training_label = QLabel()
        self.training_label.setWordWrap(True)
        self.training_label.setFont(QFont("Arial", 11))
        training_layout.addWidget(self.training_label)
        layout.addWidget(training_group)

        stats_group = QGroupBox("Current Session")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        self.stats_label.setFont(QFont("Arial", 10))
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(stats_group)

        button_layout = QHBoxLayout()
        reset_btn = QPushButton("🔄 Reset Profile")
        reset_btn.clicked.connect(self._reset_profile)
        button_layout.addWidget(reset_btn)
        
        close_btn = QPushButton("✓ Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        self._refresh()

    def _refresh(self):
        profile_text = get_profile_summary()
        self.profile_label.setText(profile_text if profile_text else "No data yet. Play some games!")

        suggestion = get_training_suggestion()
        self.training_label.setText(suggestion if suggestion else "Play more games to get personalized suggestions.")

        session = get_session()
        if session.current_game:
            stats = session.current_game
            self.stats_label.setText(
                f"<b>Moves played:</b> {stats.move_count}<br>"
                f"<span style='color:#a855f7'>Blunders:</span> {stats.get_blunder_count()} | "
                f"<span style='color:#ef4444'>Mistakes:</span> {stats.get_mistake_count()} | "
                f"<span style='color:#f59e0b'>Inaccuracies:</span> {stats.get_inaccuracy_count()}"
            )
        else:
            self.stats_label.setText("No game in progress.")

    def _reset_profile(self):
        reply = QMessageBox.question(
            self, "Reset Profile",
            "Are you sure you want to reset all historical data?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            reset_profile()
            if save_profile():
                self._refresh()
                QMessageBox.information(self, "Profile Reset", 
                    "Your profile has been reset successfully and saved to disk.")
            else:
                QMessageBox.warning(self, "Save Failed", 
                    "Profile was reset but could not be saved to disk.")


# =========================
# PREMIUM GAME SUMMARY DIALOG
# =========================

class GameSummaryDialog(QDialog):
    def __init__(self, feedback: dict, result: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Game Summary")
        self.setMinimumWidth(450)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
            }
            QLabel {
                color: #fafafa;
            }
            QGroupBox {
                color: #fafafa;
                border: 2px solid #27272a;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #10b981;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                color: #fafafa;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Result with icon
        result_icon = "🏆" if "1-0" in result or "White wins" in result else "🤝" if "1/2" in result else "📊"
        result_label = QLabel(f"<h1>{result_icon} {result}</h1>")
        result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(result_label)

        # Statistics card
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #27272a;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        stats_layout = QVBoxLayout(stats_frame)
        
        stats_html = (
            f"<div style='text-align: center;'>"
            f"<p style='font-size: 14px;'><b>Total moves:</b> {feedback.get('total_moves', 0)}</p>"
            f"<hr style='border: 1px solid #3f3f46;'>"
            f"<table style='width: 100%; margin-top: 8px;'>"
            f"<tr>"
            f"<td style='color:#a855f7; padding: 4px;'><b>Blunders</b></td>"
            f"<td style='text-align: right; padding: 4px;'>{feedback.get('blunders', 0)}</td>"
            f"</tr>"
            f"<tr>"
            f"<td style='color:#ef4444; padding: 4px;'><b>Mistakes</b></td>"
            f"<td style='text-align: right; padding: 4px;'>{feedback.get('mistakes', 0)}</td>"
            f"</tr>"
            f"<tr>"
            f"<td style='color:#f59e0b; padding: 4px;'><b>Inaccuracies</b></td>"
            f"<td style='text-align: right; padding: 4px;'>{feedback.get('inaccuracies', 0)}</td>"
            f"</tr>"
            f"<tr>"
            f"<td style='color:#10b981; padding: 4px;'><b>Good moves</b></td>"
            f"<td style='text-align: right; padding: 4px;'>{feedback.get('good_moves', 0)}</td>"
            f"</tr>"
            f"</table>"
            f"</div>"
        )
        stats_label = QLabel(stats_html)
        stats_label.setWordWrap(True)
        stats_layout.addWidget(stats_label)
        layout.addWidget(stats_frame)

        # Analysis
        summary_group = QGroupBox("📝 Performance Analysis")
        summary_layout = QVBoxLayout(summary_group)
        summary_label = QLabel(feedback.get('summary', ''))
        summary_label.setWordWrap(True)
        summary_label.setFont(QFont("Arial", 11))
        summary_layout.addWidget(summary_label)
        layout.addWidget(summary_group)

        # Training suggestion
        suggestion = get_training_suggestion()
        if suggestion:
            suggestion_group = QGroupBox("💡 Next Steps")
            suggestion_layout = QVBoxLayout(suggestion_group)
            suggestion_label = QLabel(suggestion)
            suggestion_label.setWordWrap(True)
            suggestion_label.setFont(QFont("Arial", 11))
            suggestion_layout.addWidget(suggestion_label)
            layout.addWidget(suggestion_group)

        close_btn = QPushButton("✓ Continue")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# =========================
# PREMIUM BOARD WIDGET
# =========================

class ChessBoardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.board: Optional[chess.Board] = None
        self.selected_square = None
        self.legal_destinations: List[int] = []
        self.last_move = None
        self.visual_cues = None
        self.suggestion_arrows = []
        self.on_move_callback = None
        self.interaction_enabled = True
        self.show_coordinates = True

        self.square_size = 70
        self.margin = 24
        total_size = 8 * self.square_size + 2 * self.margin
        self.setFixedSize(total_size, total_size)
        
        self.setStyleSheet("""
            ChessBoardWidget {
                background-color: transparent;
                border-radius: 8px;
            }
        """)

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

    def set_suggestion_arrows(self, arrows):
        self.suggestion_arrows = arrows
        self.update()

    def clear_suggestion_arrows(self):
        self.suggestion_arrows = []
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Draw board shadow
        shadow_rect = QRect(self.margin + 2, self.margin + 2, 
                          8 * self.square_size, 8 * self.square_size)
        painter.fillRect(shadow_rect, QColor(0, 0, 0, 40))

        if self.show_coordinates:
            self._draw_coordinates(painter)

        for sq in chess.SQUARES:
            self._draw_square(painter, sq)

        if self.board.is_check():
            king_sq = self.board.king(self.board.turn)
            if king_sq is not None:
                self._draw_check_highlight(painter, king_sq)

        if self.visual_cues:
            for h in self.visual_cues.get("highlights", []):
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

        for arrow in self.suggestion_arrows:
            try:
                self._draw_arrow(painter, arrow["from"], arrow["to"], arrow["type"], is_suggestion=True)
            except:
                pass

        if self.visual_cues:
            for a in self.visual_cues.get("arrows", []):
                try:
                    self._draw_arrow(painter, a["from"], a["to"], a["type"], is_suggestion=False)
                except:
                    pass

        painter.end()

    def _draw_coordinates(self, painter):
        painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        painter.setPen(QColor(120, 120, 120))

        files = "abcdefgh"

        for file_idx in range(8):
            x = self.margin + file_idx * self.square_size + self.square_size // 2
            y_bottom = self.margin + 8 * self.square_size + 18
            painter.drawText(QRect(x - 12, y_bottom - 12, 24, 24),
                           Qt.AlignmentFlag.AlignCenter, files[file_idx])
            y_top = 6
            painter.drawText(QRect(x - 12, y_top, 24, 24),
                           Qt.AlignmentFlag.AlignCenter, files[file_idx])

        for rank_idx in range(8):
            y = self.margin + (7 - rank_idx) * self.square_size + self.square_size // 2
            x_left = 6
            painter.drawText(QRect(x_left, y - 12, 18, 24),
                           Qt.AlignmentFlag.AlignCenter, str(rank_idx + 1))
            x_right = self.margin + 8 * self.square_size + 6
            painter.drawText(QRect(x_right, y - 12, 18, 24),
                           Qt.AlignmentFlag.AlignCenter, str(rank_idx + 1))

    def _draw_square(self, painter, sq):
        x = self.margin + chess.square_file(sq) * self.square_size
        y = self.margin + (7 - chess.square_rank(sq)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)

        if self.last_move and sq in (self.last_move.from_square, self.last_move.to_square):
            color = LAST_MOVE_HIGHLIGHT
        elif sq == self.selected_square:
            color = HIGHLIGHT_SQUARE
        else:
            is_light = (chess.square_file(sq) + chess.square_rank(sq)) % 2
            color = LIGHT_SQUARE if is_light else DARK_SQUARE

        painter.fillRect(rect, color)

    def _draw_check_highlight(self, painter, king_sq):
        x = self.margin + chess.square_file(king_sq) * self.square_size
        y = self.margin + (7 - chess.square_rank(king_sq)) * self.square_size
        
        for i in range(3):
            alpha = 40 - i * 10
            margin = i * 2
            glow_rect = QRect(x - margin, y - margin, 
                            self.square_size + margin * 2, 
                            self.square_size + margin * 2)
            painter.fillRect(glow_rect, QColor(220, 38, 38, alpha))
        
        rect = QRect(x, y, self.square_size, self.square_size)
        painter.fillRect(rect, CHECK_HIGHLIGHT)

    def _draw_highlight(self, painter, square, highlight_type):
        x = self.margin + chess.square_file(square) * self.square_size
        y = self.margin + (7 - chess.square_rank(square)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)
        
        if highlight_type == "danger":
            color = QColor(239, 68, 68, 120)
        else:
            color = QColor(251, 146, 60, 100)
        
        painter.fillRect(rect, color)

    def _draw_arrow(self, painter, from_sq, to_sq, arrow_type, is_suggestion=False):
        from_x = self.margin + chess.square_file(from_sq) * self.square_size + self.square_size // 2
        from_y = self.margin + (7 - chess.square_rank(from_sq)) * self.square_size + self.square_size // 2
        to_x = self.margin + chess.square_file(to_sq) * self.square_size + self.square_size // 2
        to_y = self.margin + (7 - chess.square_rank(to_sq)) * self.square_size + self.square_size // 2

        alpha = 120 if is_suggestion else 240

        COLOR_MAP = {
            "best": QColor(16, 185, 129, alpha),
            "good": QColor(59, 130, 246, alpha),
            "inaccuracy": QColor(245, 158, 11, alpha),
            "blunder": QColor(239, 68, 68, alpha),
            "threat": QColor(239, 68, 68, alpha),
        }
        color = COLOR_MAP.get(arrow_type, QColor(120, 120, 120, alpha))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        dx = to_x - from_x
        dy = to_y - from_y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 5:
            return

        angle = math.atan2(dy, dx)
        shaft_w = 14 if not is_suggestion else 12
        head_w = 28 if not is_suggestion else 24
        head_len = 22 if not is_suggestion else 18

        shorten = 20
        from_x += math.cos(angle) * shorten
        from_y += math.sin(angle) * shorten
        to_x -= math.cos(angle) * shorten
        to_y -= math.sin(angle) * shorten

        dx = to_x - from_x
        dy = to_y - from_y
        length = math.sqrt(dx * dx + dy * dy)
        if length < head_len:
            return

        shaft_end = length - head_len

        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        px = -sin_a * shaft_w / 2
        py = cos_a * shaft_w / 2

        points = QPolygonF()
        points.append(QPointF(from_x + px, from_y + py))
        points.append(QPointF(from_x - px, from_y - py))
        points.append(QPointF(from_x + cos_a * shaft_end - px,
                              from_y + sin_a * shaft_end - py))
        points.append(QPointF(
            from_x + cos_a * shaft_end + py * head_w / shaft_w,
            from_y + sin_a * shaft_end - px * head_w / shaft_w
        ))
        points.append(QPointF(to_x, to_y))
        points.append(QPointF(
            from_x + cos_a * shaft_end - py * head_w / shaft_w,
            from_y + sin_a * shaft_end + px * head_w / shaft_w
        ))
        points.append(QPointF(from_x + cos_a * shaft_end + px,
                              from_y + sin_a * shaft_end + py))
        painter.drawPolygon(points)

    def _draw_dot(self, painter, sq):
        cx = self.margin + chess.square_file(sq) * self.square_size + self.square_size // 2
        cy = self.margin + (7 - chess.square_rank(sq)) * self.square_size + self.square_size // 2
        
        has_piece = self.board.piece_at(sq) is not None
        
        if has_piece:
            painter.setPen(QPen(QColor(0, 0, 0, 80), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(cx - 28, cy - 28, 56, 56)
        else:
            painter.setBrush(QBrush(QColor(0, 0, 0, 70)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - 12, cy - 12, 24, 24)

    def _draw_piece(self, painter, sq, piece):
        x = self.margin + chess.square_file(sq) * self.square_size
        y = self.margin + (7 - chess.square_rank(sq)) * self.square_size
        rect = QRect(x, y, self.square_size, self.square_size)
        
        painter.setFont(QFont("Segoe UI Symbol", 48))
        
        if piece.color:
            painter.setPen(QColor(80, 80, 80))
            shadow_rect = QRect(x + 2, y + 2, self.square_size, self.square_size)
            painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, PIECE_UNICODE[piece.symbol()])
            painter.setPen(QColor(255, 255, 255))
        else:
            painter.setPen(QColor(200, 200, 200))
            shadow_rect = QRect(x + 2, y + 2, self.square_size, self.square_size)
            painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, PIECE_UNICODE[piece.symbol()])
            painter.setPen(QColor(0, 0, 0))
        
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, PIECE_UNICODE[piece.symbol()])

    def mousePressEvent(self, event):
        if not self.interaction_enabled or not self.board or self.board.turn != chess.WHITE:
            return

        file = int((event.position().x() - self.margin) // self.square_size)
        rank = 7 - int((event.position().y() - self.margin) // self.square_size)

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
            self.clear_suggestion_arrows()
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
# ENGINE WORKER THREAD
# =========================

class EngineWorker(QThread):
    analysis_done = pyqtSignal(object, object, list)
    engine_move_ready = pyqtSignal(object, int)

    def __init__(self, engine, board_before, board_after, board_for_reply,
                 difficulty_mode, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.board_before = board_before
        self.board_after = board_after
        self.board_for_reply = board_for_reply
        self.difficulty_mode = difficulty_mode

    def run(self):
        import random

        try:
            analysis_before = self.engine.analyze(self.board_before)
            analysis_after = self.engine.analyze(self.board_after)
            alternatives = self.engine.analyze_multipv(self.board_before, n=3)
        except Exception:
            self.analysis_done.emit(None, None, [])
            return

        self.analysis_done.emit(analysis_before, analysis_after, alternatives)

        random_chance = {
            "beginner": 0.40,
            "intermediate": 0.10,
            "advanced": 0.00,
            "engine": 0.00,
            "adaptive": 0.15,
        }.get(self.difficulty_mode, 0.0)

        try:
            if random_chance > 0.0 and random.random() < random_chance:
                legal = list(self.board_for_reply.legal_moves)
                engine_move = random.choice(legal) if legal else None
            else:
                engine_move = self.engine.get_move(self.board_for_reply)
        except Exception:
            engine_move = None

        eval_after = 0
        if engine_move:
            try:
                test_board = self.board_for_reply.copy()
                test_board.push(engine_move)
                result = self.engine.analyze(test_board)
                eval_after = result.cp_score_white
            except:
                pass

        self.engine_move_ready.emit(engine_move, eval_after)


# =========================
# SUGGESTION WORKER
# =========================

class SuggestionWorker(QThread):
    suggestions_ready = pyqtSignal(list)

    def __init__(self, engine, board, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.board = board

    def run(self):
        try:
            alternatives = self.engine.analyze_multipv(self.board, n=3)
            self.suggestions_ready.emit(alternatives)
        except Exception:
            self.suggestions_ready.emit([])


# =========================
# BRANCH ANALYSIS DIALOG
# =========================

class BranchAnalysisDialog(QDialog):
    def __init__(self, board: chess.Board, engine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Branch Analysis")
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)

        self.board = board
        self.engine = engine

        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
            }
            QLabel {
                color: #fafafa;
            }
            QTextEdit {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 12px;
                color: #fafafa;
            }
            QPushButton {
                background-color: #10b981;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                color: #fafafa;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("🔍 Alternative Move Analysis")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        info_label = QLabel("Top 5 moves from current position, ranked by engine evaluation:")
        info_label.setFont(QFont("Arial", 10))
        info_label.setStyleSheet("color: #a1a1aa;")
        layout.addWidget(info_label)

        self.alternatives_text = QTextEdit()
        self.alternatives_text.setReadOnly(True)
        self.alternatives_text.setFont(QFont("Consolas", 10))
        layout.addWidget(self.alternatives_text)

        close_btn = QPushButton("✓ Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._analyze()

    def _analyze(self):
        if self.engine is None:
            self.alternatives_text.setPlainText("Engine not available.")
            return

        try:
            alternatives = self.engine.analyze_multipv(self.board, n=5)
        except Exception as e:
            self.alternatives_text.setPlainText(f"Analysis failed: {e}")
            return

        if not alternatives:
            self.alternatives_text.setPlainText("No alternatives found.")
            return

        html = """
        <table style='width:100%; border-collapse: collapse; margin-top: 8px;'>
            <tr style='background:#3f3f46; font-weight:bold; color:#fafafa;'>
                <td style='padding: 8px;'>#</td>
                <td style='padding: 8px;'>Move</td>
                <td style='padding: 8px;'>Eval</td>
                <td style='padding: 8px;'>Quality</td>
            </tr>
        """

        best_cp = alternatives[0].cp_score_white

        for rank, alt in enumerate(alternatives, start=1):
            try:
                move_san = self.board.san(alt.move)
            except:
                move_san = alt.move.uci()

            if alt.is_mate:
                eval_str = f"M{abs(alt.mate_in)}" if alt.mate_in else "M?"
                quality = "BEST"
                color = "#10b981"
            else:
                eval_str = f"{alt.cp_score_white / 100:+.2f}"
                loss = best_cp - alt.cp_score_white
                if rank == 1:
                    quality, color = "BEST", "#10b981"
                elif loss <= 25:
                    quality, color = "GOOD", "#3b82f6"
                elif loss <= 50:
                    quality, color = "INACCURACY", "#f59e0b"
                else:
                    quality, color = "MISTAKE", "#ef4444"

            bg = "#27272a" if rank % 2 == 0 else "#1f1f23"
            html += f"""
            <tr style='background:{bg}; border-bottom: 1px solid #3f3f46;'>
                <td style='padding: 8px;'>{rank}</td>
                <td style='padding: 8px; font-weight: bold;'>{move_san}</td>
                <td style='padding: 8px;'>{eval_str}</td>
                <td style='padding: 8px; color:{color}; font-weight: bold;'>{quality}</td>
            </tr>
            """

        html += "</table>"
        self.alternatives_text.setHtml(html)


# =========================
# MAIN WINDOW - THEATRE MODE
# =========================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("♟️ AI Chess Instructor - Premium Edition")
        self.setMinimumSize(1400, 900)

        # Load profile at startup
        load_profile()

        self.instructor_mode = "adaptive"
        self.difficulty_mode = "intermediate"
        self.board = chess.Board()
        self.engine: Optional[ChessEngine] = None
        self.player_is_white = True
        self.undo_stack: List[str] = []
        self.redo_stack: List[str] = []
        self.game_active = False

        self._worker = None
        self._suggestion_worker = None
        self._pending_warning = None
        self._pending_move = None
        self._pending_move_san = None
        self._current_suggestions = []

        self.eval_history: List[Tuple[int, int]] = []

        self._build_ui()
        self._init_engine()
        self.board_widget.set_board(self.board)
        self._start_new_game()

    def _build_ui(self):
        """Theatre mode layout with premium styling."""
        root = QWidget()
        self.setCentralWidget(root)
        
        root.setStyleSheet(f"""
            QWidget {{
                background-color: {THEATRE_BG.name()};
                color: {TEXT_PRIMARY.name()};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QLabel {{
                color: {TEXT_PRIMARY.name()};
            }}
            QPushButton {{
                background-color: {PANEL_BG.name()};
                border: 1px solid {PANEL_BORDER.name()};
                border-radius: 6px;
                padding: 8px 16px;
                color: {TEXT_PRIMARY.name()};
                font-weight: 500;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: #3f3f46;
                border-color: #52525b;
            }}
            QPushButton:pressed {{
                background-color: #27272a;
            }}
            QPushButton:disabled {{
                background-color: #1f1f23;
                color: #52525b;
                border-color: #27272a;
            }}
            QComboBox {{
                background-color: {PANEL_BG.name()};
                border: 1px solid {PANEL_BORDER.name()};
                border-radius: 6px;
                padding: 6px 12px;
                color: {TEXT_PRIMARY.name()};
                min-width: 120px;
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {TEXT_SECONDARY.name()};
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {PANEL_BG.name()};
                border: 1px solid {PANEL_BORDER.name()};
                selection-background-color: #3f3f46;
                padding: 4px;
            }}
            QTextEdit {{
                background-color: {PANEL_BG.name()};
                border: 1px solid {PANEL_BORDER.name()};
                border-radius: 6px;
                padding: 12px;
                color: {TEXT_PRIMARY.name()};
                selection-background-color: #3f3f46;
            }}
            QScrollBar:vertical {{
                background: {PANEL_BG.name()};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #3f3f46;
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #52525b;
            }}
            QGroupBox {{
                border: 1px solid {PANEL_BORDER.name()};
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px;
                font-weight: 600;
                background-color: {PANEL_BG.name()};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: {TEXT_PRIMARY.name()};
            }}
        """)
        
        layout = QHBoxLayout(root)
        layout.setSpacing(24)
        layout.setContentsMargins(24, 24, 24, 24)

        board_container = QVBoxLayout()
        board_container.addStretch()
        self.board_widget = ChessBoardWidget()
        self.board_widget.on_move_callback = self._handle_player_move
        board_container.addWidget(self.board_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        board_container.addStretch()
        layout.addLayout(board_container, stretch=2)

        panel = QVBoxLayout()
        panel.setSpacing(16)
        layout.addLayout(panel, stretch=1)

        self.status = QLabel("⏳ Starting...")
        self.status.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"""
            padding: 16px;
            background-color: {PANEL_BG.name()};
            border: 1px solid {PANEL_BORDER.name()};
            border-radius: 8px;
            color: {ACCENT_GREEN.name()};
        """)
        panel.addWidget(self.status)

        settings_group = QGroupBox("⚙️ Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(12)

        coach_row = QHBoxLayout()
        coach_label = QLabel("Coach Mode:")
        coach_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        coach_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        coach_row.addWidget(coach_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["adaptive", "learning", "easy", "medium", "hard"])
        self.mode_combo.setCurrentText(self.instructor_mode)
        self.mode_combo.currentTextChanged.connect(self._on_instructor_mode_changed)
        coach_row.addWidget(self.mode_combo)
        settings_layout.addLayout(coach_row)

        diff_row = QHBoxLayout()
        diff_label = QLabel("Difficulty:")
        diff_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        diff_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        diff_row.addWidget(diff_label)
        self.difficulty_combo = QComboBox()
        self.difficulty_combo.addItems(["beginner", "intermediate", "advanced", "engine", "adaptive"])
        self.difficulty_combo.setCurrentText(self.difficulty_mode)
        self.difficulty_combo.currentTextChanged.connect(self._on_difficulty_changed)
        diff_row.addWidget(self.difficulty_combo)
        settings_layout.addLayout(diff_row)

        panel.addWidget(settings_group)

        suggestions_group = QGroupBox("💡 Suggested Moves")
        suggestions_layout = QVBoxLayout(suggestions_group)
        self.suggestions_label = QLabel("Analyzing position...")
        self.suggestions_label.setWordWrap(True)
        self.suggestions_label.setFont(QFont("Consolas", 10))
        self.suggestions_label.setStyleSheet(f"padding: 8px; color: {TEXT_PRIMARY.name()};")
        suggestions_layout.addWidget(self.suggestions_label)
        panel.addWidget(suggestions_group)

        analysis_group = QGroupBox("📊 Move Analysis")
        analysis_layout = QVBoxLayout(analysis_group)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        scroll_area.setWidget(self.output)
        
        analysis_layout.addWidget(scroll_area)
        panel.addWidget(analysis_group)

        eval_group = QGroupBox("📈 Position Evaluation")
        eval_layout = QVBoxLayout(eval_group)
        self.eval_graph_label = QLabel()
        self.eval_graph_label.setFixedHeight(140)
        self.eval_graph_label.setStyleSheet(f"""
            background: {PANEL_BG.name()};
            border: 1px solid {PANEL_BORDER.name()};
            border-radius: 6px;
        """)
        eval_layout.addWidget(self.eval_graph_label)
        panel.addWidget(eval_group)

        self.stats_bar = QLabel("")
        self.stats_bar.setFont(QFont("Arial", 9))
        self.stats_bar.setStyleSheet(f"""
            color: {TEXT_SECONDARY.name()};
            padding: 8px;
            background-color: {PANEL_BG.name()};
            border-radius: 6px;
        """)
        panel.addWidget(self.stats_bar)

        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)
        
        self.undo_btn = QPushButton("⟲ Undo")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self._undo)
        btn_row1.addWidget(self.undo_btn)

        self.redo_btn = QPushButton("⟳ Redo")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self._redo)
        btn_row1.addWidget(self.redo_btn)

        new_game_btn = QPushButton("🔄 New Game")
        new_game_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_BLUE.name()};
                border: none;
            }}
            QPushButton:hover {{
                background-color: #2563eb;
            }}
        """)
        new_game_btn.clicked.connect(self._new_game)
        btn_row1.addWidget(new_game_btn)
        
        panel.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(8)
        
        profile_btn = QPushButton("📊 Profile")
        profile_btn.clicked.connect(self._show_profile)
        btn_row2.addWidget(profile_btn)

        branch_btn = QPushButton("🔍 Analysis")
        branch_btn.clicked.connect(self._show_branch_dialog)
        btn_row2.addWidget(branch_btn)

        panel.addLayout(btn_row2)

        panel.addStretch()

    def _init_engine(self):
        try:
            self.engine = ChessEngine(STOCKFISH_PATH, depth=ENGINE_DEPTH)
            self.engine.start()
            self.engine.set_difficulty(self.difficulty_mode)
            print(f"✓ Engine initialized: Stockfish")
        except FileNotFoundError:
            QMessageBox.critical(
                self, "Engine Not Found",
                f"Stockfish engine not found at:\n{STOCKFISH_PATH}\n\n"
                "Please update STOCKFISH_PATH in gui.py to point to your Stockfish executable."
            )
            self.engine = None
        except Exception as e:
            QMessageBox.critical(self, "Engine Error", f"Failed to start engine:\n{e}")
            self.engine = None

    def _on_instructor_mode_changed(self, mode: str):
        self.instructor_mode = mode
        self._update_status_display()

    def _on_difficulty_changed(self, mode: str):
        self.difficulty_mode = mode
        if self.engine:
            if mode == "adaptive":
                self._apply_adaptive_difficulty()
            else:
                self.engine.set_difficulty(mode)
        self._update_status_display()

    def _apply_adaptive_difficulty(self):
        if self.engine is None:
            return
        session = get_session()
        if session.current_game and session.current_game.move_count > 0:
            stats = session.current_game
            error_moves = stats.get_blunder_count() + stats.get_mistake_count()
            blunder_rate = error_moves / stats.move_count
        else:
            blunder_rate = 0.2
        self.engine.set_adaptive_params(blunder_rate)

    def _get_mode_display(self):
        if self.instructor_mode == "adaptive":
            return f"Adaptive ({get_current_mode().capitalize()})"
        return self.instructor_mode.capitalize()

    def _update_status_display(self):
        mode_str = self._get_mode_display()
        diff_str = self.difficulty_mode.capitalize()
        
        if self.board.is_check():
            icon = "⚠️"
            status_text = f"{icon} CHECK!"
            color = "#ef4444"
        elif self.board.turn == chess.WHITE:
            icon = "♟️"
            status_text = f"{icon} Your Turn"
            color = ACCENT_GREEN.name()
        else:
            icon = "🤖"
            status_text = f"{icon} Engine Thinking..."
            color = ACCENT_BLUE.name()
        
        self.status.setText(
            f"<div style='text-align: center;'>"
            f"<h2 style='margin: 0; color: {color};'>{status_text}</h2>"
            f"<p style='margin: 4px 0 0 0; font-size: 11px; color: {TEXT_SECONDARY.name()};'>"
            f"Coach: {mode_str} • Difficulty: {diff_str}"
            f"</p>"
            f"</div>"
        )

    def _update_status(self, text):
        self.status.setText(text)

    def _show_message(self, text):
        self.output.setPlainText(text)

    def _update_stats_bar(self):
        session = get_session()
        if session.current_game:
            stats = session.current_game
            self.stats_bar.setText(
                f"<b>Moves:</b> {stats.move_count} • "
                f"<span style='color:#a855f7'>Blunders:</span> {stats.get_blunder_count()} • "
                f"<span style='color:#ef4444'>Mistakes:</span> {stats.get_mistake_count()} • "
                f"<span style='color:#10b981'>Good:</span> {stats.get_good_move_count()}"
            )
        else:
            self.stats_bar.setText("")

    def _update_eval_graph(self):
        if not self.eval_history:
            self.eval_graph_label.clear()
            return

        width = self.eval_graph_label.width()
        height = self.eval_graph_label.height()

        if width <= 0 or height <= 0:
            return

        pixmap = QPixmap(width, height)
        pixmap.fill(PANEL_BG)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = 12
        graph_left = margin
        graph_right = width - margin
        graph_top = margin
        graph_bottom = height - margin
        graph_width = graph_right - graph_left
        graph_height = graph_bottom - graph_top

        max_move = max(m for m, _ in self.eval_history)
        min_move = 0

        evals = [e for _, e in self.eval_history]
        max_eval = max(evals)
        min_eval = min(evals)

        display_max = min(max_eval, 500)
        display_min = max(min_eval, -500)
        eval_range = display_max - display_min

        if eval_range == 0:
            eval_range = 1

        if display_min <= 0 <= display_max:
            y_zero = graph_bottom - int(((0 - display_min) / eval_range) * graph_height)
            painter.setPen(QPen(PANEL_BORDER, 2))
            painter.drawLine(graph_left, y_zero, graph_right, y_zero)

        points = []
        for move_num, cp_eval in self.eval_history:
            clamped = max(display_min, min(display_max, cp_eval))
            x = graph_left + int(((move_num - min_move) / max(1, max_move - min_move)) * graph_width)
            y = graph_bottom - int(((clamped - display_min) / eval_range) * graph_height)
            points.append(QPoint(x, y))

        for i in range(len(points) - 1):
            eval_val = self.eval_history[i][1]
            if eval_val > 100:
                color = ACCENT_GREEN
            elif eval_val < -100:
                color = QColor(239, 68, 68)
            else:
                color = ACCENT_BLUE
            
            painter.setPen(QPen(color, 3))
            painter.drawLine(points[i], points[i + 1])

        for point in points:
            painter.setBrush(QBrush(TEXT_PRIMARY))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(point, 4, 4)

        painter.end()
        self.eval_graph_label.setPixmap(pixmap)

    def _start_new_game(self):
        start_game()
        self.game_active = True
        self._update_status_display()
        self._show_message("♟️ New game started. Make your move!")
        self._update_stats_bar()
        self._load_suggestions()

    def _load_suggestions(self):
        if self.engine is None or not self.board or self.board.turn != chess.WHITE:
            return

        self.suggestions_label.setText("⏳ Analyzing position...")
        
        self._suggestion_worker = SuggestionWorker(self.engine, self.board.copy(), self)
        self._suggestion_worker.suggestions_ready.connect(self._on_suggestions_ready)
        self._suggestion_worker.start()

    def _on_suggestions_ready(self, alternatives):
        self._current_suggestions = alternatives
        
        if not alternatives:
            self.suggestions_label.setText("No suggestions available.")
            return

        arrows = []
        html_lines = []

        for rank, alt in enumerate(alternatives, start=1):
            try:
                move_san = self.board.san(alt.move)
            except:
                continue

            if alt.is_mate:
                eval_str = f"M{abs(alt.mate_in)}" if alt.mate_in else "M?"
            else:
                eval_str = f"{alt.cp_score_white / 100:+.2f}"

            if rank == 1:
                arrow_type = "best"
                color = "#10b981"
                label = "BEST"
                icon = "🥇"
            elif rank == 2:
                arrow_type = "good"
                color = "#3b82f6"
                label = "GOOD"
                icon = "🥈"
            else:
                arrow_type = "good"
                color = "#3b82f6"
                label = "ALT"
                icon = "🥉"

            arrows.append({
                "from": alt.move.from_square,
                "to": alt.move.to_square,
                "type": arrow_type
            })

            html_lines.append(
                f"<div style='margin: 4px 0; padding: 6px; background: #27272a; border-radius: 4px;'>"
                f"{icon} <span style='color:{color}; font-weight: bold;'>{move_san}</span> "
                f"<span style='color: #a1a1aa;'>({eval_str})</span> "
                f"<span style='color:{color}; font-size: 10px;'>[{label}]</span>"
                f"</div>"
            )

        self.board_widget.set_suggestion_arrows(arrows)
        self.suggestions_label.setText("".join(html_lines))

    def _check_game_over(self):
        """FIXED: No duplicate summary - only show dialog once."""
        if not self.board.is_game_over():
            return False

        self.board_widget.set_interaction_enabled(False)
        self.board_widget.clear_suggestion_arrows()
        self.game_active = False

        result = self.board.result()

        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            self._update_status(f"🏁 Checkmate! {winner} wins!")
        elif self.board.is_stalemate():
            self._update_status("🤝 Draw by stalemate")
        elif self.board.is_insufficient_material():
            self._update_status("🤝 Draw - insufficient material")
        else:
            self._update_status(f"🏁 Game over: {result}")

        # Get feedback and save profile
        feedback = end_game(result)
        save_profile()

        # Show dialog - ONLY summary display point
        dialog = GameSummaryDialog(feedback, result, self)
        dialog.exec()

        # FIXED: Removed duplicate append to output panel
        # Previously was: self.output.append(f"\n\n<b>Game Summary:</b><br>{summary}")
        # Now summary only shows in dialog

        return True

    def _handle_player_move(self, move: chess.Move):
        if self.engine is None:
            self._show_message("❌ Engine not available.")
            return
        if self.board.is_game_over():
            return

        self.redo_stack.clear()
        self.board_widget.set_interaction_enabled(False)
        self.undo_btn.setEnabled(False)
        self._update_status("⏳ Analyzing your move...")
        self.suggestions_label.setText("⏳ Analyzing...")

        self.undo_stack.append(self.board.fen())

        warning = analyze_pre_move_threats(
            self.board,
            chess.WHITE if self.player_is_white else chess.BLACK,
            self.instructor_mode
        )
        self._pending_warning = warning
        self._pending_move = move
        self._pending_move_san = self.board.san(move)

        board_before = self.board.copy()
        board_after = self.board.copy()
        board_after.push(move)

        self.board.push(move)
        board_for_reply = self.board.copy()

        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(move)

        self._worker = EngineWorker(
            engine=self.engine,
            board_before=board_before,
            board_after=board_after,
            board_for_reply=board_for_reply,
            difficulty_mode=self.difficulty_mode,
            parent=self
        )
        self._worker.analysis_done.connect(
            lambda ab, aa, alts: self._on_analysis_done(ab, aa, alts, board_before, board_after, move)
        )
        self._worker.engine_move_ready.connect(self._on_engine_move_ready)
        self._worker.start()

    def _on_analysis_done(self, analysis_before, analysis_after, alternatives,
                          board_before, board_after, move):
        move_number = board_after.fullmove_number
        self.eval_history.append((move_number, analysis_after.cp_score_white))
        self._update_eval_graph()

        if analysis_before is None:
            self._show_message("❌ Engine analysis failed.")
            self.board_widget.set_interaction_enabled(True)
            return

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

        record_move(assessment.grade, assessment.explanation)
        self._update_stats_bar()

        if self.difficulty_mode == "adaptive":
            self._apply_adaptive_difficulty()

        best_san = None
        if assessment.best_move and assessment.best_move != move:
            try:
                best_san = board_before.san(assessment.best_move)
            except Exception:
                pass

        grade_color = GRADE_COLORS.get(assessment.grade, "#fafafa")
        grade_icon = {
            MoveGrade.BEST: "🏆",
            MoveGrade.EXCELLENT: "⭐",
            MoveGrade.GOOD: "✓",
            MoveGrade.INACCURACY: "⚠️",
            MoveGrade.MISTAKE: "❌",
            MoveGrade.BLUNDER: "💥"
        }.get(assessment.grade, "•")

        html = f"""
        <div style='background: #27272a; padding: 16px; border-radius: 8px; margin-bottom: 12px;'>
            <h2 style='margin: 0 0 12px 0; color: {grade_color};'>
                {grade_icon} {self._pending_move_san} - {assessment.grade.name}
            </h2>
            <table style='width: 100%; margin-bottom: 12px;'>
                <tr>
                    <td style='color: #a1a1aa; padding: 4px;'>Evaluation:</td>
                    <td style='text-align: right; padding: 4px; font-weight: bold;'>
                        {assessment.eval_initial / 100:+.2f} → {assessment.eval_final / 100:+.2f}
                    </td>
                </tr>
        """

        if best_san and not assessment.was_best_move:
            html += f"""
                <tr>
                    <td style='color: #a1a1aa; padding: 4px;'>Best move:</td>
                    <td style='text-align: right; padding: 4px;'>
                        <span style='color: #10b981; font-weight: bold;'>{best_san}</span>
                    </td>
                </tr>
            """

        html += f"""
            </table>
            <div style='background: #18181b; padding: 12px; border-radius: 6px; border-left: 3px solid {grade_color};'>
                {assessment.explanation}
            </div>
        </div>
        """

        if alternatives:
            html += """
            <div style='background: #27272a; padding: 16px; border-radius: 8px;'>
                <h3 style='margin: 0 0 12px 0;'>📋 Alternative Moves</h3>
                <table style='width: 100%; border-collapse: collapse;'>
            """
            
            best_alt_cp = alternatives[0].cp_score_white if alternatives else 0
            played_uci = move.uci()

            for rank_i, alt in enumerate(alternatives, start=1):
                try:
                    alt_san = board_before.san(alt.move)
                except Exception:
                    alt_san = alt.move.uci()

                if alt.is_mate:
                    score_str = f"M{abs(alt.mate_in)}" if alt.mate_in else "M?"
                    label = "BEST"
                    label_color = "#10b981"
                else:
                    score_str = f"{alt.cp_score_white / 100:+.2f}"
                    cp_loss_vs_best = (
                        (best_alt_cp - alt.cp_score_white)
                        if self.player_is_white
                        else (alt.cp_score_white - best_alt_cp)
                    )
                    if rank_i == 1:
                        label, label_color = "BEST", "#10b981"
                    elif cp_loss_vs_best <= 25:
                        label, label_color = "GOOD", "#3b82f6"
                    elif cp_loss_vs_best <= 50:
                        label, label_color = "INACCURACY", "#f59e0b"
                    else:
                        label, label_color = "MISTAKE", "#ef4444"

                marker = " ✓" if alt.move.uci() == played_uci else ""
                bg = "#1f1f23" if rank_i % 2 else "#27272a"

                html += f"""
                    <tr style='background: {bg};'>
                        <td style='padding: 8px; font-weight: bold;'>{rank_i}.</td>
                        <td style='padding: 8px; font-weight: bold;'>{alt_san}{marker}</td>
                        <td style='padding: 8px; text-align: right;'>{score_str}</td>
                        <td style='padding: 8px; text-align: right; color: {label_color}; font-weight: bold;'>{label}</td>
                    </tr>
                """

            html += "</table></div>"

        if self._pending_warning:
            html = f"""
            <div style='background: #422006; padding: 12px; border-radius: 6px; border-left: 3px solid #f59e0b; margin-bottom: 12px;'>
                ⚠️ <b>Warning:</b> {self._pending_warning}
            </div>
            """ + html

        self.output.setHtml(html)

        if assessment.visual_cues:
            self.board_widget.set_visual_cues(assessment.visual_cues)
        else:
            self.board_widget.set_visual_cues(None)

        if self._check_game_over():
            self.undo_btn.setEnabled(True)
            return

        self._update_status("🤖 Engine thinking...")

    def _on_engine_move_ready(self, engine_move, eval_after_engine):
        if engine_move:
            move_number = self.board.fullmove_number + 1
            self.eval_history.append((move_number, eval_after_engine))
            self._update_eval_graph()

        if not engine_move or self.board.is_game_over():
            self.board_widget.set_interaction_enabled(True)
            self.undo_btn.setEnabled(len(self.undo_stack) > 0)
            if not self._check_game_over():
                self._update_status_display()
                self._load_suggestions()
            return

        board_before_engine = self.board.copy()

        try:
            engine_analysis_before = self.engine.analyze(board_before_engine)
            best_for_engine = engine_analysis_before.best_move
            eval_before_engine = engine_analysis_before.cp_score_white
        except:
            best_for_engine = None
            eval_before_engine = 0

        engine_san = self.board.san(engine_move)
        self.board.push(engine_move)

        board_after_engine = self.board.copy()

        engine_assessment = assess_move(
            move_played=engine_move,
            eval_initial=eval_before_engine,
            eval_final=eval_after_engine,
            best_move=best_for_engine,
            player_is_white=False,
            board_before=board_before_engine,
            board_after=board_after_engine,
            engine=self.engine
        )

        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(engine_move)

        engine_grade_color = GRADE_COLORS.get(engine_assessment.grade, "#fafafa")
        engine_grade_text = f"""
        <div style='background: #1f1f23; padding: 12px; border-radius: 6px; margin-top: 12px; border-left: 3px solid #3b82f6;'>
            <b>🤖 Engine plays:</b> <span style='color: {engine_grade_color}; font-weight: bold;'>{engine_san}</span>
            <span style='color: #a1a1aa;'>[{engine_assessment.grade.name}]</span>
        </div>
        """

        current_html = self.output.toHtml()
        self.output.setHtml(current_html + engine_grade_text)

        self.board_widget.set_interaction_enabled(True)
        self.undo_btn.setEnabled(len(self.undo_stack) > 0)

        if not self._check_game_over():
            self._update_status_display()
            self._load_suggestions()

    def _undo(self):
        if not self.undo_stack:
            return

        self.redo_stack.append(self.board.fen())

        fen = self.undo_stack.pop()
        self.board = chess.Board(fen)
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_visual_cues(None)
        self.board_widget.set_interaction_enabled(True)

        self.undo_btn.setEnabled(len(self.undo_stack) > 0)
        self.redo_btn.setEnabled(len(self.redo_stack) > 0)
        self._show_message("⟲ Move undone.")
        self._update_status_display()
        self._load_suggestions()

    def _redo(self):
        if not self.redo_stack:
            return

        self.undo_stack.append(self.board.fen())

        fen = self.redo_stack.pop()
        self.board = chess.Board(fen)
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_visual_cues(None)
        self.board_widget.set_interaction_enabled(True)

        self.undo_btn.setEnabled(len(self.undo_stack) > 0)
        self.redo_btn.setEnabled(len(self.redo_stack) > 0)
        self._show_message("⟳ Move redone.")
        self._update_status_display()
        self._load_suggestions()

    def _new_game(self):
        self.eval_history.clear()
        self._update_eval_graph()

        if self.game_active:
            end_game(None)
            save_profile()

        self.board = chess.Board()
        self.board_widget.set_board(self.board)
        self.board_widget.set_last_move(None)
        self.board_widget.set_visual_cues(None)
        self.board_widget.clear_suggestion_arrows()
        self.board_widget.set_interaction_enabled(True)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.undo_btn.setEnabled(False)
        self.redo_btn.setEnabled(False)
        reset_adaptive_state()

        if self.engine:
            if self.difficulty_mode == "adaptive":
                self.engine.set_difficulty("intermediate")
            else:
                self.engine.set_difficulty(self.difficulty_mode)

        self._start_new_game()

    def _show_profile(self):
        dialog = ProfileDialog(self)
        dialog.exec()

    def _show_branch_dialog(self):
        if self.engine is None:
            QMessageBox.warning(self, "No Engine", "Engine not available.")
            return
        dialog = BranchAnalysisDialog(self.board, self.engine, self)
        dialog.exec()

    def closeEvent(self, event):
        """Auto-save profile on exit."""
        if self.game_active:
            end_game(None)
        
        # Save profile before closing
        if save_profile():
            print("✓ Profile saved on exit")
        
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
    app.setStyle('Fusion')
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()