"""Frozen, balanced attack benchmark. Persist randomized schedule before any game."""
import gc
import json
import random
import secrets
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from attack_series import HERE, VERSIONS, ExternalAB, ConditionalClock, ValueModel, MODEL, Recorder, Tablut, verify, enclosure
from native_field import Engine, compile_engine, rule_check
from open_field import TlutGreedy, TlutSearch, UCT, tlut_value
from refutation_field import DynamicAttack, AttackRecorder

ATTACKS=("dynamic","frozen","trained","finish","hook","gen2","easyAI")
DEFENSES=("kurz","PUCT","easyAI","tLut-search","tLut-greedy","UCT","randytli")
PLAN=HERE/"random_league_schedule.json"
RESULT=HERE/"random_league_games.json"


def gen2(seed):
    p=ConditionalClock(seed)
    p.value_model=ValueModel.load(MODEL)
    return p


def play(build,job):
    opponent,seed,version=job
    enclosure.cache_clear()
    tlut_value.cache_clear()
    gc.collect()
    game=Tablut()
    random.seed(seed+1)
    if version=="easyAI":
        attacker=ExternalAB()
    else:
        attacker={**VERSIONS,"dynamic":DynamicAttack,"gen2":gen2}[version](seed)
    if opponent in ("kurz","randytli"):
        defender=Engine(Path(build)/opponent,seed+1)
    elif opponent=="trained-defense":
        defender=VERSIONS["trained"](seed+1)
    elif opponent in ("PUCT","tLut-greedy"):
        defender=(gen2 if opponent=="PUCT" else TlutGreedy)(seed+1)
    else:
        defender={"easyAI":ExternalAB,"tLut-search":TlutSearch,"UCT":UCT}[opponent]()
    log,out=[],StringIO()
    try:
        with redirect_stdout(out):
            game.play(AttackRecorder(attacker,log),Recorder(defender,log))
    finally:
        if isinstance(defender,Engine):
            defender.close()
    g=dict(opponent=opponent,seed=seed,version=version,winner=game.winner or "=",plies=log,
           referee=out.getvalue(),final_board="".join(map("".join,game.board)))
    if not any(w in g["referee"].lower() for w in ("exceeded","exception","illegal","invalid")):
        verify(g)
    return g


def main(plan_path=PLAN,result_path=RESULT,attacks=ATTACKS,defenses=DEFENSES,seed_range=range(1000000,2000000)):
    if not plan_path.exists():
        master=secrets.randbits(32)
        rng=random.Random(master)
        seeds=rng.sample(seed_range,4)
        schedule=[]
        for seed in seeds:
            block=[[o,seed,v] for o in defenses for v in attacks]
            rng.shuffle(block)
            schedule.extend(block)
        plan_path.write_text(json.dumps(dict(master=master,seeds=seeds,jobs=schedule),indent=2))
    jobs=json.loads(plan_path.read_text())["jobs"]
    records=json.loads(result_path.read_text()) if result_path.exists() else []
    done={(g["opponent"],g["seed"],g["version"]) for g in records}
    with TemporaryDirectory() as build:
        for e in ("kurz","randytli"):
            dest=Path(build)/e
            compile_engine(e,dest)
            print(e,rule_check(dest),flush=True)
        with ProcessPoolExecutor(max_workers=10) as pool:
            futures=[pool.submit(play,build,j) for j in jobs if tuple(j) not in done]
            for future in as_completed(futures):
                records.append(future.result())
                tmp=result_path.with_suffix(".part")
                tmp.write_text(json.dumps(records,separators=(",",":")))
                tmp.replace(result_path)
                if len(records)%10==0: print(len(records),flush=True)


if __name__=="__main__":
    main()
