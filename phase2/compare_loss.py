"""Re-search selected positions in the recorded 72-ply loss (60 seconds per decision)."""
import argparse
import gc
import json
from time import perf_counter

from experiment import HERE, ROOT, Player, PUCTPlayer, ReviewedPlayer, flat, replay
from diagnose_loss import forced_win


class AnalysisClock:
    # The original Alpha-Beta implementation writes its deadline on entry.
    @property
    def deadline(self):
        return self.analysis_deadline

    @deadline.setter
    def deadline(self, value):
        self.analysis_deadline = self.started + 60


class AnalysisAB(AnalysisClock, Player):
    pass


def compare(plies):
    records = json.loads((HERE / "results.json").read_text())["games"]
    game = next(g for g in records if g["variant"] == "PUCTPlayer" and g["side"] == "A")
    assert len(game["plies"]) == 72 and game["winner"] == "D"
    target = ROOT / "棋盘分析" / "comparison.js"
    prefix = "const lossComparison = "
    data = json.loads(target.read_text(encoding="utf8").removeprefix(prefix).strip().removesuffix(";")) if target.exists() else {}
    for ply in plies:
        board, history = replay([r["move"] for r in game["plies"][:ply-1]])
        entries = []
        for name, cls in (("普通 PUCT", PUCTPlayer), ("战术复核", ReviewedPlayer), ("Alpha–Beta", AnalysisAB)):
            gc.collect()
            player = cls() if cls is AnalysisAB else cls(seed=11)
            player.turns = (ply-1)//2
            player.history = history.copy()
            player.budget = lambda: 60.0
            player.adaptive_time = False
            player.started = perf_counter()
            reply = (player.play_attacker if ply%2 else player.play_defender)(board)
            seconds = perf_counter() - player.started
            a,b = flat(reply)
            entries.append(dict(name=name, move=81*a+b, seconds=round(seconds,3),
                                nodes=player.nodes, visits=getattr(player,"visits",None),
                                depth=player.depth, review=getattr(player,"review_reason",None)))
            if ply == 65:
                entries[-1]["losesWithinSeven"] = bool(forced_win(
                    "".join(map("".join,board)), (a,b), history, 7, flat(game["plies"][ply]["move"])))
            print(ply, name, reply, round(seconds,2), player.depth, flush=True)
            data[str(ply)] = entries
            target.write_text(prefix+json.dumps(data,ensure_ascii=False,indent=2)+";\n",encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plies", type=int, nargs="+")
    compare(parser.parse_args().plies)
