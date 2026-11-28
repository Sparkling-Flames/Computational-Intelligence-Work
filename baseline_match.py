"""Run both colors sequentially under the unmodified course referee."""
import contextlib
import io
import json
import platform
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "required_files"))
from Tablut import Tablut
from Team01 import Player


class RecordedPlayer(Player):
    def __init__(self, log, baseline):
        super().__init__()
        self.log = log
        if not baseline:
            self.depth_limit = 2

    def _choose(self, grid, attack):
        start = perf_counter()
        move = super()._choose(grid, attack)
        self.log.append(dict(side="A" if attack else "D", move=move, depth=self.depth,
                             nodes=self.nodes, seconds=round(perf_counter() - start, 6)))
        return move


def run(baseline_side):
    game = Tablut()
    log = []
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        game.play(RecordedPlayer(log, baseline_side == "A"),
                  RecordedPlayer(log, baseline_side == "D"))
    king = next(((r, c) for r, row in enumerate(game.board)
                 for c, piece in enumerate(row) if piece == "K"), None)
    result = dict(baseline_side=baseline_side, winner=game.winner,
                  referee=output.getvalue().splitlines(), final_king=king,
                  final_board=game.board, plies=log)
    print(baseline_side, result["referee"], len(log), flush=True)
    return result


if __name__ == "__main__":
    results = dict(python=platform.python_version(), opponent="same evaluation, depth capped at 2",
                   games=[run(side) for side in ("A", "D")])
    (ROOT / "baseline_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
