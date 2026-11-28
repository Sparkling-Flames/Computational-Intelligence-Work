"""Generate a new self-play batch with the frozen generation-two teacher."""
import json
from math import log
from concurrent.futures import ProcessPoolExecutor
from generation2 import (HERE, MODEL, GAMES, ValueModel, eligible, old_training, play_game,
                         protected, states_for, symmetries)

NEW_MODEL = HERE / "attack_series_value.json"
DATA = HERE / "attack_series_selfplay.json"


def shifted_prior(parent, new):
    # Isolate how much can be gained just by changing the outcome base rates.
    weights = [row.copy() for row in parent.weights]
    for i,row in enumerate(weights):
        row[0] += log(new.prior[i]/parent.prior[i])
    return ValueModel(weights,new.prior)


def generate(seed):
    parent = ValueModel.load(MODEL)
    return play_game(seed, visits=320, attack_model=parent, defend_model=parent, reuse_tree=True)


def main():
    games = json.loads(DATA.read_text()) if DATA.exists() else []
    done = {g["seed"] for g in games}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for g in pool.map(generate, [s for s in range(8110,8174) if s not in done]):
            games.append(g)
            tmp = DATA.with_suffix(".part")
            tmp.write_text(json.dumps(games,separators=(",",":")))
            tmp.replace(DATA)
    reserved = protected()
    old_ids = json.loads((HERE/"generation2_metrics.json").read_text())["train_seeds"]
    prior = old_training(reserved) + [g for g in json.loads(GAMES.read_text()) if g["seed"] in old_ids]
    fresh = [g for g in games if g["seed"] < 8158 and eligible(g,reserved)]
    train = [states_for(g) for g in prior+fresh]
    new = ValueModel.fit(train)
    new.save(NEW_MODEL)
    seen = reserved | {v for states,_ in train for b,a in states for v in symmetries(b,a)}
    hold = [([(b,a) for b,a in states if (b,a) not in seen],y)
            for g in games if g["seed"]>=8158 for states,y in [states_for(g)]]
    parent = ValueModel.load(MODEL)
    report = dict(new_train_seeds=[g["seed"] for g in fresh], holdout_seeds=list(range(8158,8174)),
                  parent=parent.evaluate_games(hold), candidate=new.evaluate_games(hold),
                  parent_adjusted_for_prior=shifted_prior(parent,new).evaluate_games(hold))
    (HERE/"attack_series_value_metrics.json").write_text(json.dumps(report,indent=2))
    print("completed",len(games),report["candidate"],flush=True)


if __name__=="__main__":
    main()
