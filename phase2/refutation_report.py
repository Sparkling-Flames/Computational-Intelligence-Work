"""Classify actual overrides with the independent official-referee oracle."""
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import json

from refutation_field import HERE, RESULT, SEEDS, OPPONENTS, danger, verify
from native_field_review import official_refutation, packed
from experiment import ROOT, Tablut, flat
from Team01 import INITIAL, advance, moves


def main():
    games=json.loads(RESULT.read_text())
    versions=("fixed","dynamic")
    index={(g["opponent"],g["seed"],g["version"]):g for g in games}
    assert len(index)==len(games)==len(SEEDS)*len(OPPONENTS)*2
    report=dict(seeds=list(SEEDS),workers=8,scores={},paired={},events={},changes=[],misses=[],technical=[])
    cases=[]
    points={"A":2,"=":1,"D":0}
    for opponent in OPPONENTS:
        for version in versions:
            stats=Counter()
            results=Counter()
            statuses=Counter()
            for seed in SEEDS:
                g=index[opponent,seed,version]
                results[g["winner"]]+=1
                if any(s in g["referee"].lower() for s in ("exceeded","exception","illegal","invalid")):
                    report["technical"].append([opponent,version,seed,g["referee"]])
                    continue
                verify(g)
                b=INITIAL
                h={(b,True)}
                root=Tablut()
                root.past_positions=[root.compute_zobrist_hash(True)]
                prefix=[]
                changes=[]
                misses=0
                for i,row in enumerate(g["plies"]):
                    m=flat(row["move"])
                    if i%2==0:
                        stats["attack_plies"]+=1
                        event=row["review_event"]
                        if event:
                            statuses[event["status"]]+=1
                            if event.get("depth"):
                                stats["witness_found"]+=1
                            if event["status"]=="changed":
                                before=tuple(event["fixed"])
                                assert tuple(event["replacement"])==m
                                with redirect_stdout(StringIO()):
                                    loss=official_refutation(root,before)
                                    after=official_refutation(root,m)
                                assert loss==event["depth"] and after==0
                                changes.append(i+1)
                                fixed_log=index[opponent,seed,"fixed"]["plies"]
                                same_prefix=(len(fixed_log)>i and all(r["move"]==s["move"] for r,s in zip(fixed_log[:i],g["plies"][:i])))
                                report["changes"].append(dict(opponent=opponent,seed=seed,ply=i+1,fixed=before,
                                    dynamic=m,line=event["line"],depth=loss,winner=g["winner"],
                                    paired_fixed_same_prefix=same_prefix,paired_fixed_move=flat(fixed_log[i]["move"]) if same_prefix else None))
                                cases.append(dict(group="反驳搜索 · 已证实改手",label=f"{opponent} · {seed} · 第 {i+1} 手若照固定复核",
                                    moves=prefix+[packed(before)]+[packed(n) for n in event["line"]],at=i,
                                    note=f"这是固定复核原选的变化。守方可在 {loss} 手内强胜。"))
                        depth,_,_=danger(b,m,h)
                        if depth and any(not danger(b,n,h)[0] for n in moves(b,True) if n!=m):
                            misses+=1
                            report["misses"].append(dict(opponent=opponent,seed=seed,ply=i+1,version=version,
                                depth=depth,move=m,review_status=event["status"] if event else None,
                                new_visits=row["new_visits"],inherited=row["inherited_visits"]))
                    b=advance(b,m)
                    h.add((b,i%2==1))
                    prefix.append(packed(m))
                    with redirect_stdout(StringIO()):
                        assert root.make_move(i%2==0,row["move"])
                        root.check_if_game_over(i%2==1)
                stats["avoidable_losses"]+=misses
                stats["games_with_miss"]+=bool(misses)
                outcome={"A":"攻胜","D":"守胜","=":"和棋"}[g["winner"]]
                label="固定复核" if version=="fixed" else "动态反驳"
                cases.append(dict(group="配对反驳实验 · "+opponent,label=f"{label} 对 {opponent} · {seed} · {outcome}",
                    moves=prefix,at=changes[0]-1 if changes else 0,
                    note="实战全谱。"+("经裁判验证避开短程强败的手数："+", ".join(map(str,changes)) if changes else "")))
            report["scores"][opponent+" "+version]=dict(wdl=[results[w] for w in ("A","=","D")],
                points=sum(points[w]*n for w,n in results.items()),**stats)
            if version=="dynamic":
                report["events"][opponent]=statuses
        diffs=[points[index[opponent,s,"dynamic"]["winner"]]-points[index[opponent,s,"fixed"]["winner"]] for s in SEEDS]
        report["paired"][opponent]=[sum(d>0 for d in diffs),diffs.count(0),sum(d<0 for d in diffs)]
    (HERE/"refutation_summary.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    (ROOT/"棋盘分析"/"refutation-field.js").write_text("const refutationCases="+json.dumps(cases,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf8")
    print(report["scores"],report["paired"],"confirmed changes",len(report["changes"]))


if __name__=="__main__":
    main()
