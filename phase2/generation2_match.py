"""Color-swapped standard openings, official clocks, then an independent loss audit."""
import json
from contextlib import redirect_stdout
from io import StringIO
from experiment import HERE, ROOT, Recorder, Tablut, flat
from generation2 import MODEL, ValueModel, fixtures, GAMES
from clock_trial import ConditionalClock
from easyai_opponent import ExternalAB
from Team01 import INITIAL, advance, moves
from review_clock_choices import forced_after
from diagnose_loss import forced_win

RESULT = HERE/"generation2_match.json"


def audit(log, losing, horizon=3):
    board, attack, seen = INITIAL, True, set()
    for ply, r in enumerate(log,1):
        seen.add((board,attack))
        move = flat(r["move"])
        def loses(m):
            if attack:
                return bool(forced_win(board,m,seen,horizon))
            return forced_after(board,attack,m,seen,horizon)
        if r["side"]==losing and loses(move):
            alternative = next((m for m in moves(board,attack)
                                if not loses(m)),None)
            if alternative is not None:
                return dict(ply=ply, played=move, alternative=alternative, horizon=horizon)
        board, attack = advance(board,move), not attack
    return None


def main():
    records=json.loads(RESULT.read_text()) if RESULT.exists() else []
    for seed, side in [(6101,"A"),(6101,"D"),(6103,"D"),(6103,"A")]:
        if any(g["seed"]==seed and g["puct_side"]==side for g in records):
            continue
        p=ConditionalClock(seed)
        p.value_model=ValueModel.load(MODEL)
        log=[]
        ours, theirs = Recorder(p,log), Recorder(ExternalAB(),log)
        g=Tablut()
        out=StringIO()
        with redirect_stdout(out):
            g.play(ours,theirs) if side=="A" else g.play(theirs,ours)
        message=out.getvalue()
        assert not any(s in message.lower() for s in ("illegal","exception")), message
        loser={"A":"D","D":"A"}.get(g.winner)
        loss=audit(log,loser) if loser and "exceeded" not in message.lower() else None
        records.append(dict(seed=seed,puct_side=side,winner=g.winner or "=",referee=message,plies=log,
                            first_avoidable_loss_within_three=loss))
        tmp=RESULT.with_suffix(".part")
        tmp.write_text(json.dumps(records,separators=(",",":")))
        tmp.replace(RESULT)
        print(seed,side,g.winner,len(log),loss,flush=True)
    cases=[]
    for g in records:
        loser={"A":"D","D":"A"}.get(g["winner"])
        if "first_avoidable_loss_within_five" not in g:
            g["first_avoidable_loss_within_five"]=(audit(g["plies"],loser,5)
                if loser and "exceeded" not in g["referee"].lower() else None)
        cases.append(dict(seed=g["seed"],side=g["puct_side"],winner=g["winner"],
                          moves=[81*m[0]+m[1] for r in g["plies"] for m in [flat(r["move"])]],
                          loss=g["first_avoidable_loss_within_five"]))
    tmp=RESULT.with_suffix(".part")
    tmp.write_text(json.dumps(records,separators=(",",":")))
    tmp.replace(RESULT)
    js="const generation2Games = "+json.dumps(cases,separators=(",",":"))+";\n"
    path=HERE/"generation2_validation.json"
    if path.exists():
        v=json.loads(path.read_text())
        reply=v["guard_reply"]
        follow=v["chains"]["candidate"][0]["repair"]["follow"]
        checks=[dict(moves=fixtures()["defend"]+[39*81+38,81*reply["move"][0]+reply["move"][1],
                                                 81*follow[0]+follow[1]],cursor=64,
                     label="二代检验 · 第 65 手补防",
                     note=f"守方应对已排除五手内被反杀的分支。实测这条变化中，攻方 {reply['legal_answers']} 种续手里有 {reply['escapes_within_three']} 种可挡住三手强败。")]
        if v["blind"]:
            sample=v["blind"][0]
            games={g["seed"]:g for g in json.loads(GAMES.read_text())}
            record=games[sample["seed"]]
            pick=sample["candidate"]["move"]
            checks.append(dict(moves=record["moves"][:sample["ply"]-1]+[81*pick[0]+pick[1]],
                cursor=sample["ply"]-1,label="二代盲测 · 样本 "+str(sample["seed"]),
                note="查看模型实际选着。此局面经枚举有 "+str(len(sample["solutions"]))+" 种三手内强胜着。"))
            for miss in v["blind_defence"]:
                if miss["candidate"]["ok"]:
                    continue
                move=miss["candidate"]["move"]
                choices="、".join(str(divmod(a,9))+" → "+str(divmod(b,9)) for a,b in miss["escapes"])
                checks.append(dict(moves=games[miss["seed"]]["moves"][:miss["ply"]-1]+[81*move[0]+move[1]],
                    cursor=miss["ply"]-1,label="二代盲测漏防 · 样本 "+str(miss["seed"]),
                    note="下一手是二代在 640 访下的选择，允许对手三手内强胜。能避开该强败的走法为 "+choices+"。"))
        js+="const generation2Checks = "+json.dumps(checks,ensure_ascii=False,separators=(",",":"))+";\n"
    (ROOT/"棋盘分析"/"generation2-games.js").write_text(js,encoding="utf8")


if __name__=="__main__":
    main()
