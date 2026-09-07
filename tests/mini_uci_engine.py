#!/usr/bin/env python3
"""
tests/mini_uci_engine.py

A tiny, dependency-light UCI chess engine used ONLY for automated testing of the
AI Chess Instructor pipeline (engine.py / web_integrator.py) WITHOUT needing a
real Stockfish binary. It is not a strong player: every "best move" is simply
the first legal move in python-chess's move order with a cheap synthetic score.

Usage (from a shell):
    python -m chess.engine ...   # normally via engine.py -> point STOCKFISH_PATH here

It must be run with a Python interpreter that has `python-chess` installed
(e.g. the project venv). Keep it out of production configs.
"""

import sys
import chess

board = chess.Board()
multipv = 1


def send(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def handle_go() -> None:
    legal = list(board.legal_moves)
    if not legal:
        send("bestmove (none)")
        return
    n = min(multipv, len(legal))
    for i in range(1, n + 1):
        mv = legal[i - 1]
        score = 20 - i * 7  # deterministic synthetic cp score
        send(f"info depth 1 multipv {i} score cp {score} pv {mv.uci()}")
    send(f"bestmove {legal[0].uci()}")


def main() -> None:
    global board, multipv
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]

        if cmd == "uci":
            send("id name MiniUciTestEngine 1.0")
            send("id author chess-analyzer-instructor-tests")
            send("option name MultiPV type spin default 1 min 1 max 500")
            send("uciok")
        elif cmd == "isready":
            send("readyok")
        elif cmd == "ucinewgame":
            pass
        elif cmd == "setoption":
            if "multipv" in line.lower():
                try:
                    multipv = int(parts[-1])
                except (ValueError, IndexError):
                    pass
        elif cmd == "position":
            board = chess.Board()
            if len(parts) >= 2 and parts[1] == "startpos":
                if "moves" in parts:
                    for m in parts[parts.index("moves") + 1:]:
                        board.push(chess.Move.from_uci(m))
            elif len(parts) >= 2 and parts[1] == "fen":
                fen_tokens = []
                i = 2
                while i < len(parts) and parts[i] != "moves":
                    fen_tokens.append(parts[i])
                    i += 1
                board = chess.Board(" ".join(fen_tokens))
                if i < len(parts) and parts[i] == "moves":
                    for m in parts[i + 1:]:
                        board.push(chess.Move.from_uci(m))
        elif cmd == "go":
            handle_go()
        elif cmd == "quit":
            break


if __name__ == "__main__":
    main()
