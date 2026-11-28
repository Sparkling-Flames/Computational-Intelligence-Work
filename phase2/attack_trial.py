"""Play the revised attacker against the frozen external defender and replay the result."""
import argparse
from contextlib import redirect_stdout
from copy import copy
from io import StringIO
import json
from experiment import HERE, ROOT, Recorder, Tablut, flat
from attacker import Attacker, SupportedAttack
from easyai_opponent import ExternalAB

RESULT = HERE/"attack_trial_results.json"


def verify(game):
    replay = Tablut()
    replay.past_positions = [replay.compute_zobrist_hash(True)]
    rows = game["plies"]
    with redirect_stdout(StringIO()):
        for i,row in enumerate(rows):
            attack = i % 2 == 0
            assert replay.make_move(attack,row["move"])
            ended = replay.check_if_game_over(not attack)
            assert bool(ended) == (i == len(rows)-1)
    assert (replay.winner or "=") == game["winner"]
    assert "".join(map("".join,replay.board)) == game["final_board"]
    if game["winner"] == "A":
        assert "K" not in game["final_board"]
    for side in "AD":
        assert sum(r["seconds"] for r in rows if r["side"] == side) <= 60


def next_positions(referee, attack):
    # Enumerate using only the official move validator; a legal move replaces its board.
    for source,piece in enumerate("".join(map("".join,referee.board))):
        if piece not in ("A" if attack else "DK"):
            continue
        for target in range(81):
            candidate=copy(referee)
            candidate.past_positions=referee.past_positions.copy()
            move=[list(divmod(source,9)),list(divmod(target,9))]
            if candidate.make_move(attack,move):
                yield move,candidate


def finish_proof(game):
    referee=Tablut()
    referee.past_positions=[referee.compute_zobrist_hash(True)]
    for i,r in enumerate(game["plies"][:-2]):
        assert referee.make_move(i%2==0,r["move"])
        assert not referee.check_if_game_over(i%2!=0)
    answers=[]
    for reply,after in next_positions(referee,False):
        if after.check_if_game_over(True):
            return []
        win=next((m for m,end in next_positions(after,True)
                  if end.check_if_game_over(False) and end.winner=="A"),None)
        if win is None:
            return []
        answers.append(dict(reply=reply,capture=win))
    return answers


def play(seed,version):
    log,game,output=[],Tablut(),StringIO()
    with redirect_stdout(output):
        cls={"enclosure":Attacker,"supported":SupportedAttack}[version]
        game.play(Recorder(cls(seed),log),Recorder(ExternalAB(),log))
    result=dict(seed=seed,version=version,winner=game.winner or "=",referee=output.getvalue(),
                plies=log,final_board="".join(map("".join,game.board)))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("seeds",type=int,nargs="+")
    args=parser.parse_args()
    games=json.loads(RESULT.read_text()) if RESULT.exists() else []
    for seed in args.seeds:
        if any(g["version"]==args.version and g["seed"]==seed for g in games):
            continue
        g=play(seed,args.version)
        games.append(g)
        tmp=RESULT.with_suffix(".part")
        tmp.write_text(json.dumps(games,separators=(",",":")))
        tmp.replace(RESULT)
        print(seed,g["version"],len(g["plies"]),g["winner"],g["referee"],flush=True)
        verify(g)
    records=[]
    for g in games:
        if g["winner"]=="A":
            with redirect_stdout(StringIO()):
                g["forced_finish"]=finish_proof(g)
        records.append(dict(seed=g["seed"],version=g["version"],winner=g["winner"],
                            forced_replies=len(g.get("forced_finish",[])),
                            moves=[81*a+b for r in g["plies"] for a,b in [flat(r["move"])]]))
    tmp=RESULT.with_suffix(".part")
    tmp.write_text(json.dumps(games,separators=(",",":")))
    tmp.replace(RESULT)
    (ROOT/"棋盘分析"/"attack-trials.js").write_text("const attackTrials="+json.dumps(records)+";\n")


if __name__=="__main__":
    main()
