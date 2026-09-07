# ♟️ AI Chess Instructor

Premium chess training application that teaches you *why* moves are good or bad — not just what the engine says. Features tactical pattern detection, adaptive coaching, and both desktop (PyQt6) and web (Flask) interfaces.

## What's New in This Branch (General Improvements)

This branch fixes all P0/P1 issues identified in the audit:

### P0 Fixed — Web Reliability
- **Transactional `/api/move`**: Board is only saved after analysis succeeds. On failure, returns authoritative board for resync — fixes "Illegal move after pawn move" bug.
- **Per-session state**: `CoachSession` and `SessionManager` are now instantiable per user, not module globals. Fixes web-unsafe globals in `instructor.py` and `stats.py`.
- **Thread-safe engine**: Added `RLock` in `engine.py` and `app.py`, prevents race conditions from rapid clicks.
- **Coach Mode dropdown now works**: Added `set_coach_mode()` and wired `CoachSession.set_instructor_mode()` — was previously a no-op.

### P1 Fixed — Architecture & Config
- **Centralized config** (`config.py`): Auto-detects Stockfish via `STOCKFISH_PATH` env var, PATH, common locations. No more hardcoded Windows path.
- **Profile persistence layer** (`stats.py: ProfileStore`): Single implementation, atomic writes, used by both GUI and web.
- **Unified server** (`app.py`): Single Flask server serves both API and frontend on one port — no more two-server setup, no hardcoded `localhost:5000`, works in preview/deploy.
- **Adaptive difficulty wired on web**: `set_adaptive_params()` now called based on blunder rate.

### P1 Fixed — Web UI Parity
- **Visual cues**: Arrows and highlights from `assessment.visual_cues` now rendered via SVG overlay (grade-colored: green=best, blue=good, yellow=inaccuracy, red=blunder/threat).
- **Suggestion arrows**: Top 3 moves shown as arrows on board + clickable list.
- **Last-move highlight**: Yellow highlight for last move.
- **Busy lock**: Board disabled with "Analyzing..." overlay during processing — prevents double-click race.
- **Promotion handling**: Modal picker for queen/rook/bishop/knight.
- **SAN labels**: Engine and alternative moves show SAN (e.g., `Nf3`, `O-O`) not raw UCI.
- **Eval graph**: Canvas-based evaluation history graph.
- **Board flip**: Button to flip board orientation.
- **Coordinates**: File/rank labels via CSS.
- **Error resync**: On any API failure, UI resyncs to authoritative server board.

### Repo Hygiene
- Added `.gitignore`, `requirements.txt`, `README.md`
- Removed junk: `__pycache__/`, `output.html`, `chess_profile.json`
- Added `tests/` with mini UCI engine and smoke tests

## Architecture

```
engine.py          - Stockfish wrapper (thread-safe, auto-detect path, skill presets)
instructor.py      - Tactical brain: 12 detectors, CoachSession per user, explanations
stats.py           - GameStats, PlayerProfile, ProfileStore, SessionManager per user
config.py          - Central config: stockfish path resolution, env vars
app.py             - UNIFIED web server (API + frontend) - USE THIS
gui.py             - Desktop app (PyQt6) - premium board, arrows, eval graph
web.py             - Legacy frontend server (deprecated, use app.py)
web_integrator.py  - Legacy backend (deprecated, use app.py)
tests/             - mini_uci_engine.py + smoke_web_api.py
```

## How to Run — Best Way to Check Functioning

You **don't** need to pull locally every time. Two options:

### Option 1: Arena Preview (Fastest, No Local Setup)
In this Arena environment, just run:
```bash
python app.py
```
The server binds to `0.0.0.0:5000` and Arena automatically creates a **Live Preview URL** (shown in UI). Click it to test the full web app with board, analysis, suggestions, etc. No Stockfish needed — it auto-falls back to fake engine for dev.

### Option 2: Local Machine
**Prerequisites:**
```bash
pip install -r requirements.txt
# Install Stockfish: https://stockfishchess.org/download/
# Ensure it's in PATH or set env var:
export STOCKFISH_PATH=/usr/bin/stockfish  # or wherever
```

**Web (recommended):**
```bash
python app.py
# Open http://localhost:5000
```
Single server, no CORS issues. The frontend uses relative `/api` URLs.

**Desktop GUI:**
```bash
python gui.py
```
Requires PyQt6 and Stockfish.

**Legacy two-server (still works but deprecated):**
```bash
# Terminal 1: backend
python web_integrator.py  # API on :5000
# Terminal 2: frontend
python web.py             # UI on :5001
```

**CLI (Phase 1 demo):**
```bash
python main_CLI_Output.py
```

### Running Tests
```bash
pip install python-chess flask flask-cors flask-session
python tests/smoke_web_api.py
# [PASS] sequential game: 100 plies, 0 rejections, server FEN == local mirror
# [PASS] Rollback works - board not mutated on failure
```

## Environment Variables

| Var | Default | Description |
|-----|---------|-------------|
| `STOCKFISH_PATH` | auto-detect | Path to stockfish binary |
| `WEB_HOST` | `0.0.0.0` | Host to bind |
| `WEB_PORT` | `5000` | Port |
| `ENGINE_DEPTH` | `12` | Analysis depth |
| `USE_FAKE_ENGINE` | `1` | Use mini engine if stockfish missing (dev) |
| `DEFAULT_DIFFICULTY` | `intermediate` | Default difficulty |
| `DEFAULT_COACH_MODE` | `adaptive` | Default coach mode |

## Features

### Core
- Play White vs Stockfish (configurable difficulty: beginner→engine, adaptive)
- Move grading: BEST → BLUNDER with centipawn loss
- Eval before/after, best move shown

### Tactical Detection
- Missed mate, allowed mate
- Hanging pieces, missed free captures
- Forks, pins, skewers, discovered attacks
- Center control loss, king safety, material loss, development issues

### Coaching
- Adaptive mode: auto-adjusts strictness based on recent errors
- Explicit modes: learning (detailed + tips), easy, medium, hard (concise)
- Visual cues: grade-colored arrows + danger/warning highlights

### Desktop GUI (gui.py)
- Premium board with coordinates, shadows, piece symbols
- Suggestion arrows (top 3), last-move highlight, check highlight
- Move analysis panel with explanation + alternatives table
- Eval graph over game
- Undo/redo, branch analysis dialog, profile + game summary dialogs
- Profile persistence in `~/.chess_instructor/profile.json`

### Web (app.py)
- Responsive SPA, mobile-friendly
- Same features as desktop: arrows, highlights, suggestions, eval graph, promotion picker, board flip
- Transactional moves, busy lock, error resync
- Per-session profile + coach state

## Remaining Backlog (P2)

- Opening detection (ECO naming + opening principle coaching)
- Local LLM/neural coach (currently keyword templates)
- Split frontend to real static assets (currently embedded HTML)
- Docker + proper deployment

## License

MIT
