"""Aggregate prespecified blocks separately and export representative lines to the board."""
from collections import Counter
from itertools import combinations
import json
from statistics import mean
from attack_series import BLOCKS, VERSIONS, RESULT, HERE, key, verify
from attack_series_checks import DATA, assess
from attack_candidates import hook_replies
from experiment import ROOT, flat, forced_in_three
from generation2 import position, fixtures
from diagnose_loss import danger


def packed(move):
    return 81*move[0]+move[1]


def line(game):
    return [packed(flat(r["move"])) for r in game["plies"]]


def first_difference(a,b):
    return next((i+1 for i,(x,y) in enumerate(zip(a,b)) if x!=y),
                min(len(a),len(b))+1 if len(a)!=len(b) else None)


def historical_probes():
    from generation2_validation import safe
    lines=fixtures()
    hardest=json.loads((HERE/"generation2_validation.json").read_text())["guard_reply"]["move"]
    lines["hard_reply"]=lines["defend"]+[packed((39,38)),packed(hardest)]
    outcomes={}
    for version,engine in VERSIONS.items():
        selected={}
        for name in ("bait","continue","defend","hard_reply"):
            b,a,h=position(lines[name])
            p=engine(11)
            p.history=h.copy()
            p.max_visits=1600
            p.budget=lambda:float("inf")
            move=flat(p._choose(b,True))
            if name=="bait":
                ok=move==(49,51)
            elif name=="continue":
                ok=move in forced_in_three(b,a,h)
            else:
                ok=safe(tuple(lines[name]),move,7 if name=="defend" else 5)
            selected[name]=dict(move=move,ok=ok)
        outcomes[version]=selected
    return outcomes


def main():
    data=json.loads(RESULT.read_text())
    versions=["gen2",*VERSIONS]
    assert {key(g) for g in data}=={(*block,v) for block in BLOCKS for v in versions}
    assert len(data)==len(BLOCKS)*len(versions)
    indexed={key(g):g for g in data}
    for g in data:
        assert "illegal" not in g["referee"].lower() and "exception" not in g["referee"].lower()
        if "exceeded" not in g["referee"].lower():
            verify(g)
    report={"scores":{},"events":{},"timed_repeats":{},"paired":{}}
    cases=[]
    points={"A":2,"=":1,"D":0}
    for v in versions:
        report["scores"][v]={}
        group=[g for g in data if g["version"]==v]
        for label,subset in (("easyAI_new",[g for g in group if g["opponent"]=="easyAI" and g["seed"]!=6101]),
                             ("PUCT_new",[g for g in group if g["opponent"]=="PUCT"]),
                             ("easyAI_repeat",[g for g in group if g["seed"]==6101])):
            report["scores"][v][label]=dict(Counter(g["winner"] for g in subset))
        events=[r["review_events"] for g in group for r in g["plies"][::2] if r["review_events"]]
        report["events"][v]=dict(choices=Counter(e["choice"] for e in events),
            found=sum(e["hooks_found"] for e in events),rejected=sum(e["rejected"] for e in events),
            time_limited=sum(e["hook_timeout"] for e in events))
        a,b=sorted((g for g in group if g["seed"]==6101),key=lambda g:g["repeat"])
        first=first_difference(line(a),line(b))
        report["timed_repeats"][v]=dict(first_different_ply=first,outcomes=[a["winner"],b["winner"]])
        if v=="frozen":
            for g in (a,b):
                cases.append(dict(label=f"同种子复跑 · 6101 · 第 {g['repeat']} 局",moves=line(g),
                    at=(first or 1)-1,note=f"每方 60 秒，双方策略与种子相同。首次走法分歧在第 {first} 手。" if first else "两局棋谱完全相同。"))
    for v,base in (("frozen","gen2"),("finish","frozen"),("hook","finish"),("trained","finish")):
        diffs=[points[indexed[(*b,v)]["winner"]]-points[indexed[(*b,base)]["winner"]]
               for b in BLOCKS if b[1]!=6101]
        report["paired"][v]=dict(against=base,better=sum(d>0 for d in diffs),
                                  equal=diffs.count(0),worse=sum(d<0 for d in diffs),points=sum(diffs))
    check=json.loads((HERE/"attack_series_checks.json").read_text())
    offers=check["offers"]
    report["offers"]=dict(positions=len(offers),proven=sum(c["win_within_five"] is True for c in offers),
        unknown=sum(c["win_within_five"] is None for c in offers),
        avoidable_short_losses=sum(bool(c.get("safer_alternative")) for c in offers),
        random_mean_bite=mean(len(c["bites"])/c["legal"] for c in offers),
        greedy_mean_bite=mean(c["greedy_bite"] for c in offers),
        ab_bites=sum(c["ab"]["bite"] for c in offers),
        ab_one_second_bites=sum(c["ab_one_second"]["bite"] for c in offers),
        ab_one_second_punishments=sum(c["ab_one_second"]["forces_win_within_three"] for c in offers),
        puct_bites={k:sum(r["bite"] for c in offers for r in c[k]) for k in ("40","640")})
    board,_,history=position(fixtures()["bait"])
    move=(49,51)
    report["historical_offer"]=assess(board,history,move,hook_replies(board,move,history,float("inf")))
    report["historical_probes_1600_cold"]=historical_probes()
    controls=check["fixed_controls"]
    report["fixed_work"]=dict(identical_pairs=sum(g["moves"]==h["moves"] for g,h in zip(controls[::2],controls[1::2])),
        unique_lines=len({str(g["moves"]) for g in controls}),
        different_seed_divergence=[first_difference(g["moves"],h["moves"]) for g,h in combinations(controls[::2],2)])
    fresh={g["seed"]:g for g in json.loads(DATA.read_text())}
    for c in offers:
        if not c.get("safer_alternative"): continue
        prefix=fresh[c["seed"]]["moves"][:c["ply"]-1]
        b,_,h=position(prefix)
        depth,pv,_=danger(b,tuple(c["offer"]),h)
        if depth==3:
            cases.append(dict(label=f"盲测诱饵 · {c['seed']} · 拒吃反胜",
                moves=prefix+[packed(c["offer"])]+list(map(packed,pv)),at=len(prefix),
                note="攻方设饵后，守方拒吃，三手内可强胜。点击下一手查看一条经枚举的变化。"))
            break
    labels={"gen2":"二代","frozen":"护子","finish":"收尾","hook":"认证诱饵","trained":"重训收尾"}
    for opponent,seed,repeat in BLOCKS:
        for v in versions:
            g=indexed[(opponent,seed,repeat,v)]
            outcome={"A":"攻胜","D":"守胜","=":"和棋"}[g["winner"]]
            cases.append(dict(label=f"配对对局 · {labels[v]} 对 {opponent} · {seed}/{repeat} · {outcome}",
                              group=f"{opponent} · 种子 {seed} · 第 {repeat} 局",
                              moves=line(g),at=0,note=f"标准开局，每方整局 60 秒。第 {repeat} 次运行，{len(g['plies'])} 手，{outcome}。"))
    (HERE/"attack_series_summary.json").write_text(json.dumps(report,indent=2))
    (ROOT/"棋盘分析"/"attack-series.js").write_text(
        "const attackSeriesCases="+json.dumps(cases,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":
    main()
