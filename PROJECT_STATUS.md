# AI Chess Instructor — Repository Audit & Status

**Date:** 2026-09-07
**Branch:** `arena/01a07afd-chess-analyzer-instructor` (squashed history: single commit `2483402 "web integration initial phase"`)
**Method:** full source review of every file + live end-to-end run of the web backend against a fake UCI engine (no real Stockfish available in this sandbox, GUI not runnable headless). Findings marked **[verified]** were actually executed; the rest are code review.

> ⚠️ **Note on the PRD:** there is **no PRD / idea document anywhere in this repository** (no README, no docs, no past commits). The phase/feature mapping below is *reconstructed* from code comments, module docstrings, and the notes you pasted. Please share the actual PRD to confirm, especially the "100% complete" claim.

---

## 1. What is in the repo

| File | Lines | Role | Status |
|---|---|---|---|
| `engine.py` | 217 | Stockfish UCI wrapper: analyze, multi-PV, skill presets (beginner→engine, adaptive), Elo limiting, threads | Solid, engine-agnostic |
| `instructor.py` | 1097 | Tactical assessment brain: ~15 detectors (missed mate, hung piece, forks, pins, skewers, discovery, center, king safety, development…), explanation builder w/ verbosity by level, visual-cue generator, **adaptive coach state** | Core logic, currently the enhanced version |
| `instructor_no_tact_analysis_V1.py` | 365 | Earlier variant ("Phase 2 tactical awareness", has mate-avoidance helpers) | **Superseded by `instructor.py`** — dead code kept around |
| `stats.py` | 429 | GameStats, PlayerProfile, explanation→category classification, game/profile summaries, training suggestions, **module-level singleton session** | Works, but singleton is a web problem (see §4) |
| `gui.py` | 1845 | Full desktop app (PyQt6): board w/ arrows & highlights, suggestions, eval graph, undo/redo, branch analysis, profile + game-summary dialogs, adaptive difficulty | Feature-complete desktop app |
| `main_CLI_Output.py` | 244 | Phase-1 terminal game loop (UCI/SAN input, colored assessment) | Legacy demo |
| `web.py` | 1238 | **Frontend server** (Flask on port 5001) — one big self-contained HTML/CSS/JS SPA string | Initial web UI |
| `web_integrator.py` | 541 | **Backend API server** (Flask on port 5000) — `/api/*` endpoints wiring engine + instructor + stats, session FEN, web profile persistence | Initial web backend |
| `output.html` | 74 | Syntax-highlighted HTML export of some code (pygments artifact) | **Junk — deletable** |
| `chess_profile.json` | 16 | Stray profile written into the repo root by an old run | **Junk — deletable, and shows old int-key format** |
| `__pycache__/*.pyc` | — | Compiled bytecode | **Committed by mistake — should be gitignored** |

Also present: **no** `README`, `requirements.txt`, `.gitignore`, or tests (before this audit added `tests/`).

---

## 2. What has been built (feature coverage)

Reconstructed against your phased plan + the PRD items you quoted:

| Capability | Where | State |
|---|---|---|
| Phase 1 MVP: play White vs Stockfish in terminal, UCI/SAN input | `main_CLI_Output.py` | Done (legacy) |
| Tactical "why was that bad?" explanations | `instructor.py` (`_build_explanation` + detectors) | Done |
| Pattern training: forks, pins, skewers, discoveries, back-rank, overload, etc. | `instructor.py`, `stats.py` categories | Done |
| Move grading (Best→Blunder), eval before/after, best-move shown | `instructor.py` `assess_move` | Done |
| Adaptive coach: strictness follows recent mistakes | `instructor.py` `_current_mode`/`_move_history` | Done **but module-global (web-unsafe)** |
| Adaptive engine difficulty | `engine.py` `set_adaptive_params` | Desktop wired (`gui._apply_adaptive_difficulty`); **web never calls it** |
| Desktop GUI: click-move board, arrows/highlights, suggestions, eval graph, undo/redo, branch analysis, dialogs, profile | `gui.py` | Done — this is the polished app |
| Profile persistence | `gui.py` `save/load_profile`, `web_integrator.py` `save/load_web_profile`, `stats.py` `PlayerProfile.to/from_dict` | Done **but duplicated outside `stats.py`** |
| Meta-learning summaries, training recommendation | `stats.py` | Done |
| Web platform: browser board vs Stockfish w/ live feedback | `web.py` + `web_integrator.py` | **Initial phase — rough edges (see §4)** |
| Opening detection / opening coaching (your "Phase 2" leftover) | — | ❌ Not present anywhere |
| Local LLM / neural-network coach (your "Phase 2" leftover) | — | ❌ Not present anywhere (only keyword-hint explanations) |
| "ChatGPT+notepad list of fixes" | — | ❌ Not in repo — need you to paste it |

---

## 3. What actually works (verified)

Ran `tests/smoke_web_api.py` against the real backend pipeline (`engine.py` protocol layer → `web_integrator.py` API → `stats.py`) using a tiny in-repo fake UCI engine:

- **[verified]** Full sequential game flow: `POST /api/init` → `POST /api/move` … → engine reply, board FEN, analysis, alternatives, stats, `/api/profile`. **200 random plies, 0 rejections, server FEN identical to an independent python-chess mirror on every single move.**
- **[verified]** The exact reported opening works: 1.e4 → engine reply → 2.Nf3 accepted.
- **[verified]** Stats tracking and `/api/profile` endpoint work; game-over path calls `end_game` + profile save.
- **[verified by review]** Desktop GUI contains the full premium feature set (board arrows from `visual_cues`, suggestion arrows, eval graph, undo/redo, branch analysis) that the web UI is missing.

**Conclusion: the core chess/instructor engine logic is in good shape.** The pain you remember is concentrated in the web layer, and the *specific* "can't move pieces / says illegal" failure is reproducible (below).

---

## 4. Confirmed issues (by severity)

### A. Web move reliability — the "movement is so bad / says illegal" bug

**A1. `POST /api/move` mutates the session board before the move is actually safe — no rollback.** `web_integrator.py` does `board.push(move)` + `save_board_to_session(board)` *first*, then only afterwards checks the engine / runs analysis / gets the engine reply. Any failure (engine not started, Stockfish crash, analysis timeout, exception) leaves the game **half-moved**: the browser still shows the old board, but the server session is now on Black's turn with your pawn already pushed. Every subsequent White move is answered **`Illegal move`** — forever, until a new game.

- **[verified reproduction]** With the engine unavailable (exactly what a user sees if the backend/Stockfish failed to start):
  1. `e2e4` → `success: false, error: 'Engine not available'` … **but the server board was already mutated** to Black-to-move.
  2. `g1f3` → `success: false, error: 'Illegal move'`.
  - This is literally "after one pawn move, the next one says illegal". (Script: `tests/smoke_web_api.py → demo_failed_move_corrupts_session`)

**A2. The board has no busy lock — rapid/double clicks race two `/api/move` requests.** Analysis is slow (depth-8+ eval of before *and* after + 3-line multi-PV + 1s engine reply = seconds per move), the status bar says "analyzing", but the board stays clickable and `handleSquareClick`/`makeMove` have no in-flight guard. Flask's dev server is threaded, both requests read the same session FEN, both validate, both push, **last-write-wins** → the board the UI shows and the board the server stores diverge → next move "Illegal". The desktop app avoids this by disabling the board during analysis (`set_interaction_enabled(False)`); the web port dropped that protection.

**Fix direction for A (P0):** make `/api/move` transactional — work on a copy, save session state only after analysis + engine reply succeed (or restore FEN on any exception); add a per-session "move in progress" flag; add a client-side busy lock so clicks during analysis are ignored; on failure return the *authoritative* board so the UI resyncs.

### B. Architecture issues you flagged earlier — both still present

**B1. `instructor.py` adaptive state is module-level globals.** Confirmed: `_current_mode = "hard"` and `_move_history` at module scope (lines ~161–196), mutated by `assess_move → _update_adaptive_mode`, read by `_determine_grade`. Fine for one desktop game; for a web server every user/session shares one coach mode and one history — `reset_adaptive_state()` from one user's new game resets another user's mode. Same for **`stats.py` `_session` singleton**: all web users share one profile + current game (web endpoints call the module-level `start_game()/record_move()/get_session()`).

**B2. Profile persistence is duplicated in the UI/API layer instead of a storage layer.** Confirmed: `gui.py` has `save_profile()/load_profile()` and `web_integrator.py` has `save_web_profile()/load_web_profile()`; `stats.py` only has `to_dict/from_dict`. Persistence belongs in `stats.py` (e.g. `ProfileStore.load/save(path)`) so both apps + future per-user web storage use one implementation.

### C. Web ≠ desktop feature parity (why the web "felt like shit" vs the local app)

Static review of `web.py` frontend vs `gui.py`:

| Desktop GUI | Web UI today |
|---|---|
| Arrows & highlights from `assessment.visual_cues` drawn on board | `visual_cues` are returned by the API but **never rendered** — no arrows/highlights at all |
| Suggestion arrows on the board (top 3) | Suggestions are a text list only, no arrows on board |
| Last-move square highlight | `.last-move` CSS class exists but is **never applied** |
| Eval graph over the game | Missing (only current ±eval text) |
| SAN move labels + engine move clearly announced w/ grade | Move title shows raw UCI (`e1g1` not `O-O`); engine reply has no on-screen label |
| Undo/redo with stats consistency | Undo pops server moves but **does not roll back recorded stats/assessments**; redo missing |
| Branch analysis dialog | Missing |
| Board coordinate labels | `.coordinates` CSS unused |
| "Analyzing…" disables board | No busy lock (see A2) |
| Promotion picker (queen auto) | Promotion not handled client-side — `a7a8` w/o piece → rejected |

**C-extra. "Coach Mode" dropdown does nothing in either app.** Confirmed by review: there is no `set_current_mode()`; `_determine_grade` always reads the adaptive `_current_mode` global which is only changed by `_update_adaptive_mode`. Selecting Learning/Easy/Medium/Hard only changes the label. (Your earlier reviewer suggestion — pass mode into `assess_move` — is the fix.)

**C-extra 2. "Difficulty: Adaptive" does nothing on the web.** `engine.set_adaptive_params()` is never called from `web_integrator.py` (desktop does it per move in `_apply_adaptive_difficulty`).

### D. Config / deployment / repo hygiene

1. **Stockfish path is hardcoded** to a Windows absolute path in `gui.py`, `web_integrator.py`, *and* `main_CLI_Output.py` (`D:\CODE\PROJECTS\…`). Breaks any other machine; the web backend refuses to start everywhere but that one folder. Needs env-var/auto-detect/config.
2. **Two servers to run, hardcoded `http://localhost:5000/api` in the frontend** (`web.py` line ~721). Works only when both run on the same machine. No proxy, no configurable API base → can't deploy or preview from another host; origin/port coupling means the "web tool" isn't actually web-usable yet.
3. **Single global `ChessEngine` shared by all sessions/requests**, and the object itself is used from GUI threads on desktop too. python-chess `SimpleEngine` is not thread-safe; concurrent analyses (A2) can corrupt engine state. Flask `debug=True` also spawns a reloader child → two engines. For multi-user: per-session engine or a serialized engine pool + engine isolation.
4. **Session FEN is the only per-user state**; everything else (profile, coach mode, game stats) is process-global (ties to B1). Filesystem sessions in `~/.chess_instructor` are a fine dev default but no per-user profiles yet.
5. **Repo hygiene:** `__pycache__/`, `chess_profile.json`, `output.html` committed; no `.gitignore`, no `requirements.txt`, no `README`. `chess_profile.json` uses int JSON keys while `stats.to_dict()` emits string keys — a stale artifact from an older writer.

---

## 5. What still needs to be done (the real backlog)

From your last notes, the open work is:

1. **Phase-2 leftovers from your PRD:** opening detection (naming/eco + opening-principle coaching — note `_detect_development_issue` only gives generic opening tips today), and the **local LLM / neural-network coach** (currently explanations are keyword templates only). ❌ absent.
2. **The "ChatGPT + notepad list of fixes"** you refer to — not in this repo; needs to be re-shared so it can be checked item-by-item. ❌ absent.
3. **Your two web-migration review findings** — confirmed still open: kill module-global adaptive state (`instructor.py`) / global stats singleton (`stats.py`) by moving state into per-game/per-session objects passed into `assess_move(...)`; centralize profile persistence in a `stats.py` storage layer.
4. **The web movement/illegal-move bugs** (A1/A2) — the thing that made the web version unusable; root cause found and reproduced; fix is contained (transactional move endpoint + client busy lock + resync on error).
5. **Web parity + polish** (table in §C) and the config/deploy items (§D).

### Recommended order

| Priority | Task | Files |
|---|---|---|
| P0 | Transactional `/api/move` (no session mutation before success) + client busy-lock + error resync | `web_integrator.py`, `web.py` |
| P0 | Make `assess_move` take explicit `mode`/`history` (or a small `CoachSession`); stop mutating globals | `instructor.py` + both callers |
| P0 | Per-user state: replace `stats._session` singleton with a per-session/per-game object owned by the backend | `stats.py`, `web_integrator.py`, `gui.py` |
| P1 | Profile storage layer in `stats.py`; delete duplicated `save/load` in `gui.py` + `web_integrator.py` | `stats.py`, `gui.py`, `web_integrator.py` |
| P1 | Engine path via env/config; single-server or proxied deploy; wire adaptive difficulty + coach-mode dropdown on web | all |
| P1 | Web parity: render visual-cue arrows/highlights, suggestion arrows, last-move, SAN labels, busy state; fix undo/stats | `web.py` (+ maybe split to real assets) |
| P2 | Repo hygiene: `.gitignore`, `requirements.txt`, `README`, delete junk, adopt `tests/` | repo root |
| P2 | Opening detection, then LLM/neural coach | new modules |

---

## Appendix — how this audit ran

Deps used for verification: `python-chess`, `flask`, `flask-cors`, `flask-session` (venv, Python 3.11). Real Stockfish unavailable → `tests/mini_uci_engine.py` (a legal-move-returning UCI engine) substitutes through the normal `chess.engine` protocol.

```
python tests/smoke_web_api.py
# [PASS] sequential game: 200 plies, 0 rejections, server FEN == local mirror
# [BUG-DEMO] REPRODUCED — failed move leaves session half-mutated → "Illegal move"
```

To run the apps yourself (current, pre-fix state):

```
# Desktop (needs PyQt6 + Stockfish path set in gui.py)
python gui.py

# Web — two terminals:
python web_integrator.py     # API on :5000  (needs Stockfish path)
python web.py                # UI   on :5001  → http://localhost:5001
```
