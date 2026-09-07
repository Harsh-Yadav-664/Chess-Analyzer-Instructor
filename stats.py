"""
Phase 6 — Meta Learning & Feedback

This module observes completed move assessments and generates summaries.
It does NOT analyze boards, suggest moves, or call the engine.

Improved version:
- Added ProfileStore for centralized persistence (fixes duplicated save/load in gui.py and web_integrator.py)
- SessionManager is now instantiable per-user (fixes global singleton issue for web)
- Backward compatible with old module-level _session API
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import IntEnum
import json
from pathlib import Path


class MoveGrade(IntEnum):
    BLUNDER = 1
    MISTAKE = 2
    INACCURACY = 3
    GOOD = 4
    EXCELLENT = 5
    BEST = 6


# ===========================
# Explanation Categorization
# ===========================

CATEGORY_KEYWORDS = {
    "mate_threats": ["mate", "checkmate"],
    "piece_safety": ["hanging", "undefended", "en prise", "can be captured"],
    "forks": ["fork"],
    "pins": ["pin"],
    "skewers": ["skewer"],
    "discovered_attacks": ["discovered"],
    "back_rank": ["back rank"],
    "overloaded_defenders": ["overload"],
    "forced_positions": ["only move", "only legal", "unavoidable", "no move could"],
    "lost_positions": ["already lost", "position was lost"],
    "material_loss": ["lost material", "material loss"],
}


def _categorize_explanation(explanation: str) -> Optional[str]:
    """Map explanation text to a category by keyword matching."""
    if not explanation:
        return None
    lower = explanation.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return category
    return None


# ===========================
# Game Statistics
# ===========================

@dataclass
class GameStats:
    move_count: int = 0
    grades: Dict[int, int] = field(default_factory=dict)
    categories: Dict[str, int] = field(default_factory=dict)
    patterns: Dict[str, int] = field(default_factory=dict)
    
    def record_move(self, grade: MoveGrade, explanation: str):
        """Record a single move assessment."""
        self.move_count += 1
        g = int(grade)
        self.grades[g] = self.grades.get(g, 0) + 1
        category = _categorize_explanation(explanation)
        if category:
            self.categories[category] = self.categories.get(category, 0) + 1
    
    def get_grade_count(self, grade: MoveGrade) -> int:
        return self.grades.get(int(grade), 0)
    
    def get_blunder_count(self) -> int:
        return self.get_grade_count(MoveGrade.BLUNDER)
    
    def get_mistake_count(self) -> int:
        return self.get_grade_count(MoveGrade.MISTAKE)
    
    def get_inaccuracy_count(self) -> int:
        return self.get_grade_count(MoveGrade.INACCURACY)
    
    def get_error_count(self) -> int:
        return self.get_blunder_count() + self.get_mistake_count() + self.get_inaccuracy_count()
    
    def get_good_move_count(self) -> int:
        good = self.get_grade_count(MoveGrade.GOOD)
        excellent = self.get_grade_count(MoveGrade.EXCELLENT)
        best = self.get_grade_count(MoveGrade.BEST)
        return good + excellent + best
    
    def get_most_common_category(self) -> Optional[str]:
        if not self.categories:
            return None
        return max(self.categories, key=self.categories.get)
    
    def to_dict(self) -> dict:
        return {
            "move_count": self.move_count,
            "grades": self.grades,
            "categories": self.categories,
            "patterns": self.patterns
        }

    @staticmethod
    def from_dict(data: dict) -> 'GameStats':
        gs = GameStats()
        gs.move_count = data.get("move_count", 0)
        gs.grades = {int(k): v for k, v in data.get("grades", {}).items()}
        gs.categories = data.get("categories", {})
        gs.patterns = data.get("patterns", {})
        return gs


# ===========================
# Player Profile (Persistent)
# ===========================

@dataclass
class PlayerProfile:
    games_played: int = 0
    total_moves: int = 0
    aggregate_grades: Dict[int, int] = field(default_factory=dict)
    aggregate_categories: Dict[str, int] = field(default_factory=dict)
    
    def add_game(self, stats: GameStats):
        """Merge a completed game into the profile."""
        self.games_played += 1
        self.total_moves += stats.move_count
        for g, count in stats.grades.items():
            self.aggregate_grades[g] = self.aggregate_grades.get(g, 0) + count
        for cat, count in stats.categories.items():
            self.aggregate_categories[cat] = self.aggregate_categories.get(cat, 0) + count
    
    def get_most_common_issue(self) -> Optional[str]:
        if not self.aggregate_categories:
            return None
        return max(self.aggregate_categories, key=self.aggregate_categories.get)
    
    def get_error_rate(self) -> float:
        if self.total_moves == 0:
            return 0.0
        errors = sum(
            self.aggregate_grades.get(int(g), 0)
            for g in [MoveGrade.BLUNDER, MoveGrade.MISTAKE, MoveGrade.INACCURACY]
        )
        return errors / self.total_moves
    
    def get_blunder_rate(self) -> float:
        if self.total_moves == 0:
            return 0.0
        return self.aggregate_grades.get(int(MoveGrade.BLUNDER), 0) / self.total_moves
    
    def to_dict(self) -> dict:
        """Serialize profile to dictionary for JSON storage."""
        return {
            "games_played": self.games_played,
            "total_moves": self.total_moves,
            "aggregate_grades": {str(k): v for k, v in self.aggregate_grades.items()},
            "aggregate_categories": self.aggregate_categories
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'PlayerProfile':
        """Deserialize profile from dictionary (loaded from JSON)."""
        p = PlayerProfile()
        p.games_played = data.get("games_played", 0)
        p.total_moves = data.get("total_moves", 0)
        p.aggregate_grades = {int(k): v for k, v in data.get("aggregate_grades", {}).items()}
        p.aggregate_categories = data.get("aggregate_categories", {})
        return p


# ===========================
# Profile Persistence Layer (NEW - centralizes duplicated logic)
# ===========================

class ProfileStore:
    """Centralized profile persistence, replaces duplicated save/load in gui.py and web_integrator.py"""
    
    def __init__(self, profile_path: Optional[Path] = None):
        if profile_path is None:
            try:
                from config import PROFILE_DIR, PROFILE_FILE
                self.profile_dir = PROFILE_DIR
                self.profile_path = PROFILE_FILE
            except ImportError:
                self.profile_dir = Path.home() / ".chess_instructor"
                self.profile_path = self.profile_dir / "profile.json"
        else:
            self.profile_path = Path(profile_path)
            self.profile_dir = self.profile_path.parent

    def save(self, profile: PlayerProfile) -> bool:
        try:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            data = profile.to_dict()
            # Atomic write: write to temp then rename
            tmp = self.profile_path.with_suffix(".tmp")
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
            tmp.replace(self.profile_path)
            return True
        except Exception as e:
            print(f"Failed to save profile to {self.profile_path}: {e}")
            return False

    def load(self) -> Optional[PlayerProfile]:
        if not self.profile_path.exists():
            return None
        try:
            with open(self.profile_path, 'r') as f:
                data = json.load(f)
            return PlayerProfile.from_dict(data)
        except Exception as e:
            print(f"Failed to load profile from {self.profile_path}: {e}")
            return None

    def save_session(self, session: 'SessionManager') -> bool:
        return self.save(session.profile)

    def load_into_session(self, session: 'SessionManager') -> bool:
        profile = self.load()
        if profile:
            session.profile = profile
            return True
        return False


# ===========================
# Summary Generation
# ===========================

CATEGORY_LABELS = {
    "mate_threats": "mate threats",
    "piece_safety": "piece safety",
    "forks": "forks",
    "pins": "pins",
    "skewers": "skewers",
    "discovered_attacks": "discovered attacks",
    "back_rank": "back rank weakness",
    "overloaded_defenders": "overloaded defenders",
    "forced_positions": "forced positions",
    "lost_positions": "lost positions",
    "material_loss": "material loss",
}


def generate_game_summary(stats: GameStats, result: Optional[str] = None) -> str:
    """Generate a short end-of-game summary."""
    lines = []
    if stats.move_count == 0:
        return "No moves recorded."
    blunders = stats.get_blunder_count()
    mistakes = stats.get_mistake_count()
    inaccuracies = stats.get_inaccuracy_count()
    good_moves = stats.get_good_move_count()
    error_total = blunders + mistakes + inaccuracies
    if error_total == 0:
        lines.append("Excellent game with no significant errors!")
    elif blunders >= 3:
        lines.append(f"Challenging game with {blunders} blunders.")
    elif blunders >= 1:
        lines.append(f"Game had {blunders} blunder(s) and {mistakes} mistake(s).")
    elif mistakes >= 2:
        lines.append(f"Solid game with {mistakes} mistakes to review.")
    else:
        lines.append("Generally accurate play.")
    main_issue = stats.get_most_common_category()
    if main_issue and stats.categories.get(main_issue, 0) >= 2:
        label = CATEGORY_LABELS.get(main_issue, main_issue)
        lines.append(f"Focus area: {label}.")
    if good_moves >= stats.move_count * 0.7 and stats.move_count > 0:
        lines.append("Strong performance - majority of moves were good or better!")
    return " ".join(lines)


def generate_profile_summary(profile: PlayerProfile) -> str:
    """Generate a player profile snapshot."""
    if profile.games_played == 0:
        return "No games played yet. Start playing to build your profile!"
    lines = []
    lines.append(f"<b>Games played:</b> {profile.games_played}")
    lines.append(f"<b>Total moves:</b> {profile.total_moves}")
    error_rate = profile.get_error_rate()
    blunder_rate = profile.get_blunder_rate()
    lines.append("")
    if blunder_rate < 0.05:
        lines.append("✓ <b>Strength:</b> You avoid major blunders consistently.")
    elif blunder_rate > 0.15:
        lines.append("⚠ <b>Area to improve:</b> Reduce frequency of blunders.")
    if error_rate < 0.2:
        lines.append("✓ <b>Accuracy:</b> You play accurately overall.")
    elif error_rate > 0.4:
        lines.append("⚠ <b>Accuracy:</b> Many errors - focus on careful calculation.")
    else:
        lines.append("○ <b>Accuracy:</b> Room for improvement with consistent practice.")
    main_issue = profile.get_most_common_issue()
    if main_issue:
        label = CATEGORY_LABELS.get(main_issue, main_issue)
        lines.append(f"📌 <b>Most common issue:</b> {label}")
    return "<br>".join(lines)


def generate_training_suggestion(profile: PlayerProfile) -> Optional[str]:
    """Generate a high-level training suggestion based on profile."""
    if profile.total_moves < 20:
        return "Play more games to get personalized training recommendations."
    main_issue = profile.get_most_common_issue()
    if not main_issue:
        return "Keep playing and your patterns will emerge!"
    suggestions = {
        "mate_threats": "Practice checkmate pattern recognition with puzzles. Learn common mating patterns like back rank mate, smothered mate, and two rooks checkmate.",
        "piece_safety": "Focus on keeping your pieces defended. Before every move, check: Are all my pieces protected? Can my opponent capture anything for free?",
        "forks": "Study knight fork patterns and tactics. Practice spotting when enemy pieces can attack multiple targets at once.",
        "pins": "Work on recognizing pin vulnerabilities. Be aware of when your pieces are pinned to your king or queen, and avoid creating pins against yourself.",
        "skewers": "Practice avoiding skewer tactics. When your valuable piece is attacked, check what's behind it on the same line.",
        "discovered_attacks": "Study discovered attack patterns. Watch for pieces that could create threats when they move out of the way.",
        "back_rank": "Practice back rank mate prevention. Always ensure your king has an escape square, or keep a defender on the back rank.",
        "overloaded_defenders": "Focus on piece coordination. Ensure important squares are defended by multiple pieces, not just one overworked piece.",
        "forced_positions": "Study defensive technique in critical positions. Sometimes accepting a small disadvantage is better than trying to avoid it and making things worse.",
        "lost_positions": "Work on avoiding early disadvantages. Study opening principles: develop pieces, control center, castle early, connect rooks.",
        "material_loss": "Practice calculating exchanges before trading pieces. Count material values: Pawn=1, Knight/Bishop=3, Rook=5, Queen=9.",
    }
    return suggestions.get(main_issue, "Continue practicing and analyzing your games!")


def generate_game_feedback(stats: GameStats, result: Optional[str] = None) -> dict:
    """Generate complete game feedback package."""
    return {
        "summary": generate_game_summary(stats, result),
        "blunders": stats.get_blunder_count(),
        "mistakes": stats.get_mistake_count(),
        "inaccuracies": stats.get_inaccuracy_count(),
        "good_moves": stats.get_good_move_count(),
        "main_issue": stats.get_most_common_category(),
        "total_moves": stats.move_count
    }


# ===========================
# Session Manager - Now instantiable per-user
# ===========================

class SessionManager:
    """Manages current game stats and player profile. Now safe to instantiate per session/user."""
    
    def __init__(self, profile: Optional[PlayerProfile] = None, profile_store: Optional[ProfileStore] = None):
        self.current_game: Optional[GameStats] = None
        self.profile = profile if profile is not None else PlayerProfile()
        self.profile_store = profile_store
        # For web: track eval history per session
        self.eval_history: List[Dict] = []
        self.move_history: List[Dict] = []
    
    def start_game(self):
        """Start tracking a new game."""
        self.current_game = GameStats()
        self.eval_history = []
        self.move_history = []
    
    def record_move(self, grade: MoveGrade, explanation: str, move_san: str = "", uci: str = "", eval_before: float = 0, eval_after: float = 0):
        """Record a move in the current game."""
        if self.current_game is None:
            self.start_game()
        self.current_game.record_move(grade, explanation)
        # Track for web
        self.move_history.append({
            "move": move_san,
            "uci": uci,
            "grade": grade.name if hasattr(grade, 'name') else str(grade),
            "eval_before": eval_before,
            "eval_after": eval_after,
        })
    
    def add_eval(self, move_number: int, eval_cp: int):
        self.eval_history.append({"move_number": move_number, "eval": eval_cp})
    
    def end_game(self, result: Optional[str] = None) -> dict:
        """End current game and get feedback."""
        if self.current_game is None:
            return {"summary": "No game in progress.", "total_moves": 0, "blunders": 0, "mistakes": 0, "inaccuracies": 0, "good_moves": 0}
        feedback = generate_game_feedback(self.current_game, result)
        self.profile.add_game(self.current_game)
        # Auto-save if store available
        if self.profile_store:
            self.profile_store.save(self.profile)
        self.current_game = None
        return feedback
    
    def get_profile_summary(self) -> str:
        return generate_profile_summary(self.profile)
    
    def get_training_suggestion(self) -> Optional[str]:
        return generate_training_suggestion(self.profile)
    
    def reset_profile(self):
        """Clear all historical data."""
        self.profile = PlayerProfile()
        self.current_game = None
        self.eval_history = []
        self.move_history = []
        if self.profile_store:
            self.profile_store.save(self.profile)
    
    def get_current_stats(self) -> Optional[GameStats]:
        return self.current_game

    def to_dict(self) -> dict:
        """Serialize session for storage (web)."""
        return {
            "profile": self.profile.to_dict(),
            "current_game": self.current_game.to_dict() if self.current_game else None,
            "eval_history": self.eval_history,
            "move_history": self.move_history
        }

    @staticmethod
    def from_dict(data: dict, profile_store: Optional[ProfileStore] = None) -> 'SessionManager':
        sm = SessionManager(profile_store=profile_store)
        if "profile" in data:
            sm.profile = PlayerProfile.from_dict(data["profile"])
        if data.get("current_game"):
            sm.current_game = GameStats.from_dict(data["current_game"])
        sm.eval_history = data.get("eval_history", [])
        sm.move_history = data.get("move_history", [])
        return sm


# ===========================
# Module-level instance (backward compat for desktop GUI)
# ===========================

_default_store = ProfileStore()
_session = SessionManager(profile_store=_default_store)
# Try to load existing profile on import
try:
    loaded = _default_store.load()
    if loaded:
        _session.profile = loaded
except Exception:
    pass


def start_game():
    _session.start_game()

def record_move(grade: MoveGrade, explanation: str):
    _session.record_move(grade, explanation)

def end_game(result: Optional[str] = None) -> dict:
    return _session.end_game(result)

def get_profile_summary() -> str:
    return _session.get_profile_summary()

def get_training_suggestion() -> Optional[str]:
    return _session.get_training_suggestion()

def reset_profile():
    _session.reset_profile()

def get_session() -> SessionManager:
    return _session

def create_new_session(profile_path: Optional[Path] = None) -> SessionManager:
    """Factory for per-user sessions (for web)."""
    store = ProfileStore(profile_path) if profile_path else ProfileStore()
    profile = store.load()
    return SessionManager(profile=profile, profile_store=store)
