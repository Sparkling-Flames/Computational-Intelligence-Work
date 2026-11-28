"""Score every scheduled game and export the complete lines to the local board."""
from collections import Counter
import json
from statistics import median

from open_field import HERE, OPPONENTS, RESULT, SEEDS, VERSIONS as ENGINES, verify
from experiment import ROOT, flat
from Team01 import INITIAL, advance, moves
from review import _can_win_now, _winner
from diagnose_loss import danger

VERSIONS=("frozen","trained")
LABEL={"frozen":"护子版","trained":"重训版"}
POINTS={"A":2,"=":1,"D":0}


def same_position(board,history,seed):
    result={}
    for version in VERSIONS:
        player=ENGINES[version](seed)
        player.max_visits=1600
        player.budget=lambda:float("inf")
        player.history=history.copy()
        move=flat(player.play_attacker(board))
        depth,_,_=danger(board,move,history)
        result[version]=dict(move=move,forced_defender_win_depth=depth)
    return result


def main():
    games=json.loads(RESULT.read_text())
    expected={(o,s,v) for o in OPPONENTS for s in SEEDS for v in VERSIONS}
    index={(g["opponent"],g["seed"],g["version"]):g for g in games}
    assert len(games)==len(expected) and set(index)==expected
    summary={"rules":"Attack from official initial position, 60s per side, 2/1/0",
             "seeds":list(SEEDS),"workers":8,"opponents":{},"technical_ends":[],"loss_checks":[],
             "tLut_source":"https://github.com/MatteoFasulo/Tablut/blob/a56a1c2693187402df4b3378e2bfb7cbab1cfda3/whiteheuristics.py",
             "UCT_source":"https://github.com/pbsinclair42/MCTS/blob/f4b6226ce06840e51b66bdca4bedbe2c4c143012/mcts.py",
             "tLut_adapter":"Original white_fitness and weights, official course move generator and adjudication. Shared evaluation for one-ply greedy and easyAI iterative negamax.",
             "UCT_adapter":"Original adversarial UCT, default random playouts to terminal, course state and whole-game time manager.",
             "cold_1600":"Fresh tree, at most 1600 visits, full review. Depth zero means no proven defender win within three replies/plies after the attack move."}
    cases=[]
    for opponent in OPPONENTS:
        results={}
        for version in VERSIONS:
            group=[index[opponent,seed,version] for seed in SEEDS]
            counts=Counter(g["winner"] for g in group)
            results[version]={"WDL":[counts[w] for w in ("A","=","D")],
                              "points":sum(POINTS[g["winner"]] for g in group)}
            choices_missed=choices=0
            for g in group:
                log=g["plies"]
                technical=any(w in g["referee"].lower() for w in ("exceeded","exception","illegal","invalid"))
                if technical:
                    summary["technical_ends"].append([opponent,g["seed"],version,g["referee"]])
                    continue
                verify(g)
                b=INITIAL
                history={(b,True)}
                prefix=[]
                rows=[]
                for i,r in enumerate(log):
                    m=flat(r["move"])
                    child=advance(b,m)
                    if i%2==1 and _can_win_now(b,False):
                        choices+=1
                        choices_missed+=_winner(child)!="D"
                    if i%2==0:
                        rows.append((i,b,m,history.copy()))
                    prefix.append(81*m[0]+m[1])
                    b=child
                    history.add((b,i%2==1))
                label=LABEL[version]
                outcome={"A":"攻胜","D":"守胜","=":"和棋"}[g["winner"]]
                note=f"双方整局各 60 秒，{len(log)} 手，{outcome}。"
                at=0
                if g["winner"]=="D":
                    # Nearest avoidable refutation within the last four attacker turns.
                    miss=None
                    for i,b,m,h in reversed(rows[-4:]):
                        depth,_,_=danger(b,m,h,flat(log[i+1]["move"]) if i+1<len(log) else None)
                        if not depth:
                            continue
                        other=next((n for n in moves(b,True) if n!=m and not danger(b,n,h)[0]),None)
                        if other:
                            miss=dict(ply=i+1,depth=depth,played=m,alternative=other,
                                      cold_1600=same_position(b,h,g["seed"]))
                            at=i
                            note+=f" 第 {i+1} 手后守方可在 {depth} 手内强胜。另走 {divmod(other[0],9)} → {divmod(other[1],9)} 可避开三手内强败。"
                            break
                    summary["loss_checks"].append(dict(opponent=opponent,version=version,seed=g["seed"],miss=miss))
                cases.append(dict(group=f"跨对手检验 · {opponent}",label=f"{label} 对 {opponent} · {g['seed']} · {outcome}",
                                  moves=prefix,at=at,note=note,result=g["winner"]))
            results[version].update(defender_win_in_one=choices,missed_by_defender=choices_missed,
                                    median_plies=median(len(g["plies"]) for g in group))
        diffs=[POINTS[index[opponent,s,"trained"]["winner"]]-POINTS[index[opponent,s,"frozen"]["winner"]] for s in SEEDS]
        results["paired_trained_better_equal_worse"]=[sum(d>0 for d in diffs),diffs.count(0),sum(d<0 for d in diffs)]
        summary["opponents"][opponent]=results
    summary["total_points"]={v:sum(r[v]["points"] for r in summary["opponents"].values()) for v in VERSIONS}
    (HERE/"open_field_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    (ROOT/"棋盘分析"/"open-field.js").write_text("const openFieldCases="+json.dumps(cases,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf8")
    print(json.dumps(summary["opponents"]))


if __name__=="__main__":
    main()
