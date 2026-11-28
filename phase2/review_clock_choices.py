"""Audit close decisions from uninterrupted official-game searches, with bounded tactical proofs."""
from collections import Counter
import json
from time import perf_counter
from experiment import ROOT, HERE, PUCTPlayer, flat, replay
from diagnose_loss import forced_win
from midgame_clock import RESULT
from Team01 import INITIAL, advance, moves
from review import _winner, _can_win_now


def forced_after(board, attack, candidate, history, depth):
    """Can the opponent force a win within depth further plies? A repetition is a draw."""
    target = not attack
    winning_side = "A" if target else "D"

    def solve(b, turn, seen, left):
        result = _winner(b)
        if result:
            return result == winning_side
        key = (b, turn)
        if key in seen:
            return False
        if left == 1:
            assert turn == target
            return _can_win_now(b, turn)
        if turn == target and _can_win_now(b, turn):
            return True
        legal = list(moves(b, turn))
        if not legal:
            return False
        path = seen | {key}
        children = (solve(advance(b, m), not turn, path, left-1) for m in legal)
        return any(children) if turn == target else all(children)

    return solve(advance(board, candidate), target, history, depth)


def close(row):
    if not row["before"]:
        return False
    pair = row["before"]["top"]
    return (len(pair) == 2 and all(c["visits"] >= 20 and c["proof"] is None for c in pair)
            and abs(pair[0]["score"]-pair[1]["score"]) <= 0.05)


def recorded_loss_control():
    """Positive-control position, chosen independently of the new official games."""
    game = next(g for g in json.loads((HERE/"results.json").read_text())["games"]
                if g["variant"] == "PUCTPlayer" and g["side"] == "A" and len(g["plies"]) == 72)
    prefix = [row["move"] for row in game["plies"][:64]]
    grid, history = replay(prefix)
    board = "".join(map("".join,grid))
    p = PUCTPlayer(seed=11, max_visits=8000)
    p.history = history
    start = perf_counter()
    p._tree(board, True, float("inf"))
    before = p.snapshot(p._root)
    seconds = perf_counter()-start
    root = p._root
    # The board, turn, history and tree are identical at both checkpoints.
    p._matching_reply = lambda board, attack: root
    p.max_visits = 16000
    p._tree(board, True, float("inf"))
    total = perf_counter()-start
    after = p.snapshot(p._root)
    checks = {m:bool(forced_win(board, m, history, 7)) for m in
              (before["top"][0]["move"], after["top"][0]["move"])}
    return dict(ply=65, before=before, after=after, seconds=[seconds,total],
                was_loss7=checks[before["top"][0]["move"]], now_loss7=checks[after["top"][0]["move"]])


def main():
    games = json.loads(RESULT.read_text())
    cases, counts = [], {label:Counter() for label in ("conditional","baseline")}
    stable_sides = set()
    for g in games:
        policy = g["policy"]
        if policy not in counts:
            continue
        tally = counts[policy]
        board, attack, history, prefix = INITIAL, True, set(), []
        for ply, row in enumerate(g["plies"], 1):
            move = flat(row["move"])
            history.add((board, attack))
            if row["before"]:
                tally["extended_to_base_cutoff"] += 1
            if close(row):
                tally["close"] += 1
                before = tuple(row["before"]["top"][0]["move"])
                changed = before != move
                tally["changed"] += changed
                # Audit every switch and the first stable middle-game decision per side.
                if changed or (policy == "conditional" and ply >= 15 and attack not in stable_sides):
                    if not changed:
                        stable_sides.add(attack)
                    checks = {m: forced_after(board, attack, m, history, 5) for m in {before, move}}
                    options = list(moves(board,attack)) if checks[before] and checks[move] else []
                    escapes = [m for m in options if not forced_after(board,attack,m,history,5)]
                    cases.append(dict(seed=g["seed"], policy=policy, ply=ply, side=row["side"], prefix=prefix.copy(),
                                      base=row["base_seconds"], seconds=row["seconds"], before=row["before"],
                                      after=row["after"], was_loss5=checks[before], now_loss5=checks[move],
                                      alternatives=len(options), escapes=escapes))
            assert move in moves(board, attack)
            prefix.append(move[0]*81+move[1])
            board = advance(board, move)
            attack = not attack
    out = dict(counts=dict(counts), cases=cases, control=recorded_loss_control(),
               lengths=[len(g["plies"]) for g in games if g["policy"] == "calibration"])
    target = ROOT / "棋盘分析" / "clock-review.js"
    target.write_text("const clockReview = "+json.dumps(out, separators=(",", ":"))+";\n", encoding="utf8")
    print(counts)
    for c in cases:
        print(c["seed"], c["policy"], c["ply"], c["before"]["top"][0]["move"], c["after"]["top"][0]["move"],
              c["was_loss5"], c["now_loss5"])


if __name__ == "__main__":
    main()
