"""Paired, prospectively scheduled official games. Preserve repeated seeds as separate trials."""
import gc
import json
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
from attacker import SupportedAttack, enclosure
from attack_candidates import FinishAttack, CertifiedHook, RetrainedFinish
from attack_trial import verify
from easyai_opponent import ExternalAB
from clock_trial import ConditionalClock
from experiment import HERE, Recorder, Tablut
from generation2 import ValueModel, MODEL

VERSIONS = {"frozen":SupportedAttack, "finish":FinishAttack, "hook":CertifiedHook, "trained":RetrainedFinish}
BLOCKS = [("easyAI",6101,1),("easyAI",7221,1),("easyAI",7222,1),("PUCT",7321,1),
          ("easyAI",6101,2),("easyAI",7223,1),("easyAI",7224,1),("PUCT",7322,1)]
RESULT=HERE/"attack_series_matches.json"


class EventRecorder(Recorder):
    def call(self, attack, grid):
        move=super().call(attack,grid)
        self.log[-1]["review_events"]=getattr(self.player,"events",None)
        return move


def play(arg):
    opponent,seed,repeat,variant=arg
    enclosure.cache_clear()
    gc.collect()
    if variant=="gen2":
        attacker=ConditionalClock(seed)
        attacker.value_model=ValueModel.load(MODEL)
    else:
        attacker=VERSIONS[variant](seed)
    if opponent=="easyAI":
        defender=ExternalAB()
    else:
        defender=ConditionalClock(seed+1)
        defender.value_model=ValueModel.load(MODEL)
    game,log,out=Tablut(),[],StringIO()
    with redirect_stdout(out):
        game.play(EventRecorder(attacker,log),Recorder(defender,log))
    record=dict(opponent=opponent,seed=seed,repeat=repeat,version=variant,winner=game.winner or "=",
                plies=log,referee=out.getvalue(),final_board="".join(map("".join,game.board)))
    if "exceeded" not in record["referee"].lower():
        verify(record)
    return record


def key(g):
    return g["opponent"],g["seed"],g["repeat"],g["version"]


def main():
    data=json.loads(RESULT.read_text()) if RESULT.exists() else []
    done={key(g) for g in data}
    variants=list(VERSIONS)
    # Rotate version order across seed blocks and run different seeds concurrently.
    schedule=[(*block,variants[(i+r)%4]) for r in range(4) for i,block in enumerate(BLOCKS)]
    schedule.extend((*block,"gen2") for block in BLOCKS)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for game in pool.map(play,[s for s in schedule if s not in done]):
            data.append(game)
            tmp=RESULT.with_suffix(".part")
            tmp.write_text(json.dumps(data,separators=(",",":")))
            tmp.replace(RESULT)
            print(len(data),key(game),game["winner"],len(game["plies"]),flush=True)


if __name__=="__main__":
    main()
