"""Refit a clean parent, generate its self-play, then fit and freeze the next value model."""
from concurrent.futures import ProcessPoolExecutor
import json
from train_selfplay_value import HERE, states_for, play_game, ValueModel
from Team01 import INITIAL, advance

GAMES = HERE / "generation2_games.json"
MODEL = HERE / "generation2_value.json"
CLEAN = HERE / "generation2_parent.json"


def symmetries(board, attack):
    rows = tuple(board[i:i+9] for i in range(0,81,9))
    for _ in range(4):
        yield "".join(rows), attack
        yield "".join(row[::-1] for row in rows), attack
        rows = tuple(map("".join,zip(*rows[::-1])))


def fixtures():
    old = json.loads((HERE/"selfplay_games.json").read_text())["games"]
    trap = next(g["moves"] for g in old if g["seed"]==1006)
    loss = next(g for g in json.loads((HERE/"results.json").read_text())["games"]
                if g["variant"]=="PUCTPlayer" and g["side"]=="A" and len(g["plies"])==72)
    prefix = [81*(9*a+b)+9*c+d for r in loss["plies"][:64] for ((a,b),(c,d)) in [r["move"]]]
    return {"bait":trap[:32], "recognize":trap[:33], "continue":trap[:34],
            "defend":prefix, "reply_to_guard":prefix+[39*81+38,29*81+11]}


def position(prefix):
    b, a = INITIAL, True
    seen = {(b,a)}
    for m in prefix:
        b,a = advance(b,divmod(m,81)),not a
        seen.add((b,a))
    return b,a,seen


def protected():
    return {s for prefix in fixtures().values() for s in symmetries(*position(prefix)[:2])}


def eligible(g, reserved):
    return not any(s in reserved for s in states_for(g)[0])


def old_training(reserved):
    old = json.loads((HERE/"selfplay_games.json").read_text())["games"]
    return [g for g in old if g["split"]=="train" and eligible(g,reserved)]


def generate(seed):
    parent = ValueModel.load(CLEAN)
    return play_game(seed, visits=320, attack_model=parent, defend_model=parent, reuse_tree=True)


def main():
    reserved=protected()
    old=old_training(reserved)
    ValueModel.fit(list(map(states_for,old))).save(CLEAN)
    games=json.loads(GAMES.read_text()) if GAMES.exists() else []
    done={g["seed"] for g in games}
    with ProcessPoolExecutor(max_workers=5) as pool:
        for g in pool.map(generate,[s for s in range(5000,5064) if s not in done]):
            games.append(g)
            tmp=GAMES.with_suffix(".part")
            tmp.write_text(json.dumps(games,separators=(",",":")))
            tmp.replace(GAMES)
            if len(games)%8==0: print("self-play",len(games),flush=True)
    new=[g for g in games if g["seed"]<5048 and eligible(g,reserved)]
    training=list(map(states_for,old+new))
    model=ValueModel.fit(training)
    model.save(MODEL)
    seen={v for states,_ in training for b,a in states for v in symmetries(b,a)} | reserved
    tests=[([(b,a) for b,a in states if (b,a) not in seen],y)
           for g in games if g["seed"]>=5048 for states,y in [states_for(g)]]
    result=dict(clean_old_games=len(old), new_training_games=len(new), visits=320,
                train_seeds=[g["seed"] for g in new], holdout_seeds=list(range(5048,5064)),
                parent=ValueModel.load(CLEAN).evaluate_games(tests), candidate=model.evaluate_games(tests))
    (HERE/"generation2_metrics.json").write_text(json.dumps(result,indent=2))
    print(result["parent"],result["candidate"],flush=True)


if __name__=="__main__":
    main()
