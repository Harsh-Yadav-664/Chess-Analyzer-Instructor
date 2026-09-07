#!/usr/bin/env python3
"""
tests/smoke_web_api.py

End-to-end smoke test of the web backend (web_integrator.py) using a fake UCI
engine instead of Stockfish, so it runs anywhere python-chess + Flask are
installed.

Run from the repository root:
    python tests/smoke_web_api.py            # (requires flask, flask-cors,
                                             #  flask-session, python-chess)

It exercises:

  1. test_sequential_game_is_consistent()  -- the NORMAL path. Plays 1.e4/Nf3
     then 200 random plies; asserts every move is accepted, the server board
     always matches a local python-chess mirror, and endpoints respond.

  2. demo_failed_move_corrupts_session()   -- reproduces the KNOWN BUG that
     made the web UI report "Illegal move": if anything fails after the player's
     move is pushed (engine not available, analysis crash, timeout), the server
     session is already mutated, so the board the browser shows and the board
     the server stores permanently disagree and later legal moves are rejected.

Exit code is 0 when the consistency test passes (the bug demo is printed, not
asserted, so this file doubles as a regression harness once the rollback bug is
fixed -- at that point the demo should stop reproducing and can be deleted).
"""
import os
import sys
import random
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import chess  # noqa: E402

import web_integrator as wi  # noqa: E402

FAKE_ENGINE_SRC = Path(__file__).resolve().parent / "mini_uci_engine.py"


def _make_fake_engine_path() -> str:
    """Create an executable copy of the fake engine whose shebang points at the
    *current* interpreter (the one with python-chess installed)."""
    lines = FAKE_ENGINE_SRC.read_text().splitlines()
    body = "\n".join(lines[1:])  # drop the generic #!/usr/bin/env shebang
    dst_dir = Path(tempfile.mkdtemp(prefix="cai-engine-"))
    dst = dst_dir / "mini_uci_engine.py"
    dst.write_text(f"#!{sys.executable}\n{body}")
    dst.chmod(0o755)
    return str(dst)


def _make_client(engine_available: bool):
    """Return (client, stub). engine_available=False -> engine stays None
    (simulates a machine where Stockfish could not start)."""
    if engine_available:
        wi.global_engine = wi.ChessEngine(_make_fake_engine_path(), depth=2)
        wi.global_engine.start()
    else:
        wi.global_engine = None
    client = wi.app.test_client()
    return client


def test_sequential_game_is_consistent():
    client = _make_client(engine_available=True)

    r = client.post("/api/init")
    assert r.json["success"], r.json

    local = chess.Board()
    moves_played = 0
    rnd = random.Random(42)

    # The exact scenario from the bug report: 1.e4 then 2.Nf3
    for uci in ("e2e4", "g1f3"):
        d = client.post("/api/move", json={"move": uci}).json
        assert d["success"], f"{uci} unexpectedly rejected: {d}"
        local.push(chess.Move.from_uci(uci))
        em = d["engine_move"]
        if em:
            local.push(chess.Move.from_uci(em["uci"]))
        assert chess.Board(d["board"]["fen"]).fen() == local.fen(), "FEN mismatch"
        moves_played += 1

    # Random play until 200 plies or game over -- every request must succeed
    # and the server board must mirror python-chess exactly.
    while not local.is_game_over() and moves_played < 200:
        wmove = rnd.choice(list(local.legal_moves))
        d = client.post("/api/move", json={"move": wmove.uci()}).json
        assert d["success"], f"{wmove.uci()} unexpectedly rejected: {d}"
        local.push(wmove)
        em = d["engine_move"]
        if em:
            ev = chess.Move.from_uci(em["uci"])
            assert ev in local.legal_moves, f"engine reply {ev} illegal locally"
            local.push(ev)
        assert chess.Board(d["board"]["fen"]).fen() == local.fen(), (
            f"FEN mismatch after {wmove.uci()} / {em and em['uci']}"
        )
        moves_played += 1

    print(f"[PASS] sequential game: {moves_played} plies, 0 rejections, "
          f"server FEN == local mirror the whole way")

    p = client.get("/api/profile").json
    assert p["success"]
    assert p["profile"]["current_game"]["move_count"] == moves_played
    print("[PASS] /api/profile stats tracked all moves")



def demo_failed_move_corrupts_session():
    """Reproduce the 'Illegal move after first pawn move' bug.

    With the engine unavailable (the exact state a user hits when the backend
    or Stockfish fails to start), POST /api/move pushes + SAVES the player's
    move to the session board *before* discovering the engine is missing.
    The browser still shows the original board; the server now thinks it is
    Black's turn, so every subsequent White move is answered with
    'Illegal move'.
    """
    client = _make_client(engine_available=False)
    client.post("/api/init")

    d1 = client.post("/api/move", json={"move": "e2e4"}).json
    print(f"[BUG-DEMO] first move e2e4 -> success={d1.get('success')} "
          f"error={d1.get('error')}")

    b = client.get("/api/board").json["board"]
    print(f"[BUG-DEMO] session board after the failed move is BLACK to move: "
          f"{b['fen']}")
    print(f"[BUG-DEMO] UI still shows the pre-move board -> everything the "
          f"player does next is 'Illegal move'")

    d2 = client.post("/api/move", json={"move": "g1f3"}).json
    print(f"[BUG-DEMO] next attempt g1f3 -> success={d2.get('success')} "
          f"error={d2.get('error')}")

    bug_present = (d1.get("success") is False and d2.get("error") == "Illegal move")
    print("[BUG-DEMO] result:", "REPRODUCED — session mutated before analysis "
          "succeeds (needs rollback/locking fix)" if bug_present
          else "no longer reproducible — rollback fix appears to work")
    return bug_present


if __name__ == "__main__":
    test_sequential_game_is_consistent()
    print()
    demo_failed_move_corrupts_session()
    print()
    print("Smoke test finished.")
