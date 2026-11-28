"""One frozen attack-clock candidate. No defender or value-model changes."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
import json
import random
from pathlib import Path
from tempfile import TemporaryDirectory

from refutation_field import DynamicAttack, AttackRecorder
from native_field import Engine, compile_engine, rule_check
from attack_series import HERE, Recorder, Tablut, verify, enclosure
from diagnose_loss import danger
from experiment import flat
from Team01 import INITIAL, advance, moves

SOURCES=("native_field_matches","refutation_field_matches","split_lineup_games")
PLAN=HERE/"tail_clock_plan.json"
GAMES=HERE/"tail_clock_games.json"
POINTS={"A":2,"=":1,"D":0}


def technical(g):
    return any(w in g["referee"].lower() for w in ("exceeded","invalid","illegal","exception"))


def plan():
    if not PLAN.exists():
        lengths=[len(g["plies"]) for name in SOURCES for g in json.loads((HERE/(name+".json")).read_text())
                 if not technical(g)]
        rng=random.Random(1202801)
        seeds=rng.sample(range(5000000,6000000),8)
        jobs=[(s,o,v) for s in seeds for o in ("kurz","RouteAB") for v in ("original","empirical")]
        rng.shuffle(jobs)
        PLAN.write_text(json.dumps(dict(sources=SOURCES,lengths=lengths,seeds=seeds,jobs=jobs,
            evaluation="Promote only on higher total points, fewer avoidable attack errors from ply 81, no time forfeits; inspect early errors and each opponent."),indent=2))
    return json.loads(PLAN.read_text())


def play(build,lengths,job):
    from holdout_defender import RouteAB
    seed,opponent,version=job
    attacker=DynamicAttack(seed)
    if version=="empirical":
        attacker.lengths=tuple(lengths)
    enclosure.cache_clear()
    defender=Engine(Path(build),seed+1) if opponent=="kurz" else RouteAB(seed+1)
    game,log,out=Tablut(),[],StringIO()
    try:
        with redirect_stdout(out):
            game.play(AttackRecorder(attacker,log),Recorder(defender,log))
    finally:
        if opponent=="kurz": defender.close()
    g=dict(seed=seed,opponent=opponent,version=version,winner=game.winner or "=",referee=out.getvalue(),
           final_board="".join(map("".join,game.board)),plies=log)
    if not technical(g): verify(g)
    return g


def report(games,design):
    assert {(g["seed"],g["opponent"],g["version"]) for g in games}==set(map(tuple,design["jobs"])) and len(games)==32
    results={}
    for g in games:
        key=g["opponent"]+" "+g["version"]
        c=results.setdefault(key,Counter())
        c[g["winner"]]+=1
        c["points"]+=POINTS[g["winner"]]
        if technical(g):
            c["technical"]+=1
            continue
        verify(g)
        b,h=INITIAL,{(INITIAL,True)}
        c["long_games"]+=len(g["plies"])>=81
        for i,r in enumerate(g["plies"]):
            m=flat(r["move"])
            if i%2==0:
                phase="late" if i>=80 else "early"
                c[phase+"_moves"]+=1
                if danger(b,m,h)[0] and any(not danger(b,n,h)[0] for n in moves(b,True) if n!=m):
                    c[phase+"_misses"]+=1
            b=advance(b,m)
            h.add((b,i%2==1))
    (HERE/"tail_clock_summary.json").write_text(json.dumps(results,indent=2))
    print(results)


if __name__=="__main__":
    design=plan()
    records=json.loads(GAMES.read_text()) if GAMES.exists() else []
    done={(g["seed"],g["opponent"],g["version"]) for g in records}
    with TemporaryDirectory() as build:
        dest=Path(build)/"kurz"
        compile_engine("kurz",dest)
        rule_check(dest)
        with ProcessPoolExecutor(max_workers=8) as pool:
            futures=[pool.submit(play,str(dest),design["lengths"],j) for j in design["jobs"] if tuple(j) not in done]
            for f in as_completed(futures):
                records.append(f.result())
                tmp=GAMES.with_suffix(".part")
                tmp.write_text(json.dumps(records,separators=(",",":")))
                tmp.replace(GAMES)
                print(len(records),flush=True)
    report(records,design)
