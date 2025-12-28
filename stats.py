"""
Phase 6 — Meta Learning & Feedback

This module observes completed move assessments and generates summaries.
It does NOT analyze boards, suggest moves, or call the engine.

Input: MoveGrade + explanation string
Output: Statistics and coaching summaries
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import IntEnum


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
        return {
            "games_played": self.games_played,
            "total_moves": self.total_moves,
            "aggregate_grades": self.aggregate_grades,
            "aggregate_categories": self.aggregate_categories
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'PlayerProfile':
        p = PlayerProfile()
        p.games_played = data.get("games_played", 0)
        p.total_moves = data.get("total_moves", 0)
        p.aggregate_grades = {int(k): v for k, v in data.get("aggregate_grades", {}).items()}
        p.aggregate_categories = data.get("aggregate_categories", {})
        return p


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
    
    # Overall performance
    error_total = blunders + mistakes + inaccuracies
    if error_total == 0:
        lines.append("Excellent game with no significant errors.")
    elif blunders >= 3:
        lines.append(f"Difficult game with {blunders} blunders.")
    elif blunders >= 1:
        lines.append(f"Game had {blunders} blunder(s) and {mistakes} mistake(s).")
    elif mistakes >= 2:
        lines.append(f"Solid game with {mistakes} mistakes to review.")
    else:
        lines.append("Generally accurate play.")
    
    # Main issue
    main_issue = stats.get_most_common_category()
    if main_issue and stats.categories.get(main_issue, 0) >= 2:
        label = CATEGORY_LABELS.get(main_issue, main_issue)
        lines.append(f"Most issues came from {label}.")
    
    # Good moves note
    if good_moves >= stats.move_count * 0.7:
        lines.append("Majority of moves were good or better.")
    
    return " ".join(lines)


def generate_profile_summary(profile: PlayerProfile) -> str:
    """Generate a player profile snapshot."""
    if profile.games_played == 0:
        return "No games played yet."
    
    lines = []
    
    lines.append(f"Games played: {profile.games_played}")
    lines.append(f"Total moves: {profile.total_moves}")
    
    error_rate = profile.get_error_rate()
    blunder_rate = profile.get_blunder_rate()
    
    if blunder_rate < 0.05:
        lines.append("Strength: Avoids major blunders.")
    elif blunder_rate > 0.15:
        lines.append("Weakness: Frequent blunders.")
    
    if error_rate < 0.2:
        lines.append("Overall: Accurate player.")
    elif error_rate > 0.4:
        lines.append("Overall: Many errors to work on.")
    
    main_issue = profile.get_most_common_issue()
    if main_issue:
        label = CATEGORY_LABELS.get(main_issue, main_issue)
        lines.append(f"Frequent issue: {label}.")
    
    return " ".join(lines)


def generate_training_suggestion(profile: PlayerProfile) -> Optional[str]:
    """Generate a high-level training suggestion."""
    if profile.total_moves < 20:
        return None
    
    main_issue = profile.get_most_common_issue()
    if not main_issue:
        return None
    
    suggestions = {
        "mate_threats": "Practice recognizing checkmate patterns.",
        "piece_safety": "Focus on keeping pieces defended.",
        "forks": "Study knight fork patterns.",
        "pins": "Work on recognizing pin vulnerabilities.",
        "skewers": "Practice avoiding skewer tactics.",
        "discovered_attacks": "Watch for discovered attack setups.",
        "back_rank": "Practice back rank mate prevention.",
        "overloaded_defenders": "Focus on piece coordination.",
        "forced_positions": "Study defensive technique in critical positions.",
        "lost_positions": "Work on avoiding early disadvantages.",
        "material_loss": "Focus on piece safety and exchanges.",
    }
    
    return suggestions.get(main_issue)


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
# Session Manager
# ===========================

class SessionManager:
    """Manages current game stats and player profile."""
    
    def __init__(self):
        self.current_game: Optional[GameStats] = None
        self.profile = PlayerProfile()
    
    def start_game(self):
        """Start tracking a new game."""
        self.current_game = GameStats()
    
    def record_move(self, grade: MoveGrade, explanation: str):
        """Record a move in the current game."""
        if self.current_game is None:
            self.start_game()
        self.current_game.record_move(grade, explanation)
    
    def end_game(self, result: Optional[str] = None) -> dict:
        """End current game and get feedback."""
        if self.current_game is None:
            return {"summary": "No game in progress."}
        
        feedback = generate_game_feedback(self.current_game, result)
        self.profile.add_game(self.current_game)
        self.current_game = None
        
        return feedback
    
    def get_profile_summary(self) -> str:
        return generate_profile_summary(self.profile)
    
    def get_training_suggestion(self) -> Optional[str]:
        return generate_training_suggestion(self.profile)
    
    def reset_profile(self):
        """Clear all historical data."""
        self.profile = PlayerProfile()
    
    def get_current_stats(self) -> Optional[GameStats]:
        return self.current_game


# ===========================
# Module-level instance
# ===========================

_session = SessionManager()


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