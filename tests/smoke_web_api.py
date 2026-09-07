#!/usr/bin/env python3
"""
tests/smoke_web_api.py - End-to-end smoke test of web backend
Uses fake UCI engine so it runs without Stockfish.
"""
import os
import sys
import random
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import chess
import app as web_app_module  # new unified app

FAKE_ENGINE_SRC = Path(__file__).resolve().parent / "mini_uci_engine.py"

def _make_fake_engine_path() -> str:
    lines = FAKE_ENGINE_SRC.read_text().splitlines()
    body = "\n".join(lines[1:])
    dst_dir = Path(tempfile.mkdtemp(prefix="cai-engine-"))
    dst = dst_dir / "mini_uci_engine.py"
    dst.write_text(f"#!{sys.executable}\n{body}")
    dst.chmod(0o755)
    return str(dst)

def _make_client(engine_available: bool):
    fake_path = _make_fake_engine_path() if engine_available else None
    # init app with fake engine
    # When engine_available=False, we want no engine at all to test rollback
    use_fake = engine_available
    app_instance = web_app_module.create_app(stockfish_path=fake_path, use_fake_if_missing=use_fake)
    client = app_instance.test_client()
    return client, app_instance

def test_sequential_game_is_consistent():
    client, _ = _make_client(engine_available=True)
    r = client.post("/api/init")
    assert r.json["success"], r.json
    local = chess.Board()
    moves_played = 0
    rnd = random.Random(42)
    for uci in ("e2e4", "g1f3"):
        d = client.post("/api/move", json={"move": uci}).json
        assert d["success"], f"{uci} unexpectedly rejected: {d}"
        local.push(chess.Move.from_uci(uci))
        em = d["engine_move"]
        if em:
            local.push(chess.Move.from_uci(em["uci"]))
        assert chess.Board(d["board"]["fen"]).fen() == local.fen(), "FEN mismatch"
        moves_played += 1
    while not local.is_game_over() and moves_played < 100:
        wmove = rnd.choice(list(local.legal_moves))
        d = client.post("/api/move", json={"move": wmove.uci()}).json
        assert d["success"], f"{wmove.uci()} unexpectedly rejected: {d}"
        local.push(wmove)
        em = d["engine_move"]
        if em:
            ev = chess.Move.from_uci(em["uci"])
            assert ev in local.legal_moves, f"engine reply {ev} illegal locally"
            local.push(ev)
        assert chess.Board(d["board"]["fen"]).fen() == local.fen(), f"FEN mismatch after {wmove.uci()} / {em and em['uci']}"
        moves_played += 1
    print(f"[PASS] sequential game: {moves_played} plies, 0 rejections, server FEN == local mirror")
    p = client.get("/api/profile").json
    assert p["success"]
    print("[PASS] /api/profile stats tracked")

def demo_failed_move_corrupts_session():
    """This should NOT reproduce after fix - transactional move endpoint"""
    client, _ = _make_client(engine_available=False)
    client.post("/api/init")
    d1 = client.post("/api/move", json={"move": "e2e4"}).json
    print(f"[CHECK] first move e2e4 with no engine -> success={d1.get('success')} error={d1.get('error')}")
    b = client.get("/api/board").json["board"]
    print(f"[CHECK] session board after failed move: {b['fen']}")
    # After fix, board should still be starting position (rollback)
    is_start = b['fen'] == chess.STARTING_FEN
    if is_start:
        print("[PASS] Rollback works - board not mutated on failure")
    else:
        print("[FAIL] Rollback failed - board mutated")
    return not is_start

if __name__ == "__main__":
    test_sequential_game_is_consistent()
    print()
    bug_present = demo_failed_move_corrupts_session()
    print()
    if bug_present:
        print("Smoke test finished with rollback failure.")
        sys.exit(1)
    else:
        print("Smoke test finished - all good.")
