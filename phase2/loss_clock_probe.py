"""Independent move-65 PUCT runs with fixed per-move wall-clock limits."""
import json
import platform
from time import perf_counter

from diagnose_loss import HERE, flat, forced_win
from experiment import replay
from puct import PUCTPlayer


def main():
    games = json.loads((HERE / "results.json").read_text(encoding="utf8"))["games"]
    game = next(g for g in games if g["variant"] == "PUCTPlayer"
                and g["side"] == "A" and len(g["plies"]) == 72)
    grid, history = replay([p["move"] for p in game["plies"][:64]])
    board = "".join(map("".join, grid))
    safe_example = (39, 38)
    assert not forced_win(board, safe_example, history, 7)
    runs = []
    for limit in (0.88, 2.0, 4.0, 8.0):
        player = PUCTPlayer(seed=11)
        player.history = history.copy()
        player.budget = lambda: limit
        player.adaptive_time = False
        start = perf_counter()
        choice = player.play_attacker(grid)
        spent = perf_counter() - start
        proof = forced_win(board, flat(choice), history, 7, flat(game["plies"][65]["move"]))
        row = dict(budget=limit, seconds=round(spent, 5), move=choice,
                   forced_defender_win_within_7=bool(proof), visits=player.visits,
                   move_visits=player.root_visits[flat(choice)], depth=player.depth,
                   safe_example_rank=player.root_order.index(safe_example) + 1,
                   safe_example_visits=player.root_visits[safe_example])
        runs.append(row)
        print(row, flush=True)
    output = dict(python=platform.python_version(), variant="PUCTPlayer", seed=11,
                  ply=65, safe_example=[[4, 3], [4, 2]], runs=runs)
    (HERE / "loss_clock_probe.json").write_text(json.dumps(output, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
