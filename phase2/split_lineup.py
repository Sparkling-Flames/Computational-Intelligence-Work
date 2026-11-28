"""Compare two attackers with the same frozen defender; reuse all defensive results."""
import json
from random_league import HERE, DEFENSES, main as tournament

FIELD=(*DEFENSES,"trained-defense")
PLAN=HERE/"split_lineup_schedule.json"
GAMES=HERE/"split_lineup_games.json"
POINTS={"A":2,"=":1,"D":0}


def compare(games):
    paired={}
    for g in games:
        if g["version"] in ("dynamic","trained"):
            block=paired.setdefault((g["opponent"],g["seed"]),{})
            assert g["version"] not in block
            block[g["version"]]=POINTS[g["winner"]]
    out={}
    for name in (*FIELD,"total"):
        rows=[v for (o,_),v in paired.items() if name=="total" or o==name]
        delta=[r["dynamic"]-r["trained"] for r in rows]
        out[name]=dict(pairs=len(rows),dynamic=sum(r["dynamic"] for r in rows),
                       trained=sum(r["trained"] for r in rows),
                       better_equal_worse=[sum(d>0 for d in delta),delta.count(0),sum(d<0 for d in delta)])
    return out


if __name__=="__main__":
    old=json.loads((HERE/"random_league_games.json").read_text())+json.loads((HERE/"random_league_trained_defense.json").read_text())
    tournament(PLAN,GAMES,("dynamic","trained"),FIELD,range(3000000,4000000))
    fresh=json.loads(GAMES.read_text())
    schedule=json.loads(PLAN.read_text())
    assert {tuple(j) for j in schedule["jobs"]}=={(g["opponent"],g["seed"],g["version"]) for g in fresh}
    assert len(fresh)==64
    result=dict(old=compare(old),new=compare(fresh),combined=compare(old+fresh),
                old_common_defense=2*sum(g["winner"]=="D" for g in old if g["opponent"]=="trained-defense")
                                  +sum(g["winner"]=="=" for g in old if g["opponent"]=="trained-defense"),
                technical=[(g["opponent"],g["seed"],g["version"],g["referee"]) for g in fresh if
                    any(w in g["referee"].lower() for w in ("invalid","illegal","exception","exceeded"))])
    (HERE/"split_lineup_summary.json").write_text(json.dumps(result,indent=2))
    print(result["new"],result["technical"],flush=True)
