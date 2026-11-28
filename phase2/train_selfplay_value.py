"""Fit generation one on complete self-play games, then play its frozen parent."""
import json
from pathlib import Path
from selfplay import play_game
from value_model import ValueModel
from Team01 import INITIAL, advance

HERE = Path(__file__).resolve().parent


def states_for(record):
    board, attack = INITIAL, True
    states = []
    for move in record["moves"]:
        states.append((board, attack))
        board = advance(board, divmod(move, 81))
        attack = not attack
    return states, record["winner"]


def main():
    data=json.loads((HERE/"selfplay_games.json").read_text())
    training, holdout = [], []
    for record in data["games"]:
        (training if record["split"]=="train" else holdout).append(states_for(record))
    assert len(training)==192 and len(holdout)==64
    model=ValueModel.fit(training)
    path=HERE/"selfplay_value.json"
    model.save(path)
    model=ValueModel.load(path)
    clock_file=HERE.parent/"棋盘分析"/"clock-data.js"
    prior_games=json.loads((HERE/"results.json").read_text())["games"]
    formal_lengths=[len(g["plies"]) for g in prior_games]
    first=data["games"][0]
    clocks=dict(training=formal_lengths,observed=formal_lengths,
                selfplay=[len(g["moves"]) for g in data["games"]],
                example=dict(seed=first["seed"],moves=first["moves"],winner=first["winner"]),
                visits=data["visits"])
    clock_file.write_text("const clockSample = "+json.dumps(clocks)+";\n",encoding="utf8")
    result=dict(training_games=len(training), holdout_games=len(holdout),
                holdout_metrics=model.evaluate_games(holdout),
                visits=data["visits"],opening_plies=data["opening_plies"],games=[])
    print("Holdout",result["holdout_metrics"],flush=True)
    for seed in range(2200,2208):
        for side in ("A","D"):
            game=play_game(seed, visits=data["visits"],
                           attack_model=model if side=="A" else None,
                           defend_model=model if side=="D" else None,
                           opening_plies=data["opening_plies"])
            game["learned_side"]=side
            result["games"].append(game)
            print(seed,side,game["winner"],len(game["moves"]),flush=True)
        (HERE/"selfplay_value_results.json").write_text(json.dumps(result,indent=2),encoding="utf8")


if __name__=="__main__":
    main()

