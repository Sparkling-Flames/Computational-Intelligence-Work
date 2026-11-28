"""Balanced per-role standings. Previously observed seeds remain a separate check."""
from collections import Counter
import json
from contextlib import redirect_stdout
from io import StringIO
from experiment import Tablut
from native_field_review import official_refutation
from random_league import ATTACKS, DEFENSES, HERE, PLAN, RESULT, verify
from league_defense import RESULT as DEFENSE_RESULT

NAMES={"dynamic":"动态反驳版","frozen":"护子版","trained":"重训版","hook":"认证诱饵版","finish":"短程杀棋版",
       "gen2":"二代 PUCT","easyAI":"easyAI","PUCT":"二代 PUCT","trained-defense":"重训守方",
       "tLut-search":"tLut 多手","tLut-greedy":"tLut 一手","kurz":"Kurz","randytli":"Randy Li","UCT":"Sinclair UCT"}


def write_tables(result):
    rows=["# Tablut 随机配对赛","",
          "标准开局，每方整局 60 秒，胜／和／负计 2／1／0 分。种子 "+", ".join(map(str,result["seeds"]))+"。",
          "","## 执攻积分","","每个守方列满分 8 分，四组配对。","",
          "| 攻方 | "+" | ".join(NAMES[o] for o in DEFENSES)+" | 胜／和／负 | 总分（56） |",
          "|---|"+"---:|"*(len(DEFENSES)+2)]
    for v,s in sorted(result["attack"].items(),key=lambda x:-x[1]["points"]):
        cells=[str(result["attack_by_opponent"][v][o]["points"]) for o in DEFENSES]
        rows.append("| "+" | ".join([NAMES[v],*cells,"／".join(map(str,s["wdl"])),str(s["points"])])+" |")
    rows+=["","加入重训守方后，各攻方都有 30 局，前七种守法各四局，重训守方两局。下表另给出八种守法各取前两种子的等权比较。","","| 攻方 | 30 局积分（60） | 八种守法等权（32） |","|---|---:|---:|"]
    for v in ATTACKS:
        rows.append(f"| {NAMES[v]} | {result['attack_all'][v]['points']} | {result['attack_eight_common'][v]['points']} |")
    rows+=["","## 执守积分","","各守方只取赛前抽出的前两个种子，每个攻方出现两次，合计 14 局。","",
           "| 守方 | 胜／和／负 | 积分（28） |","|---|---:|---:|"]
    for o,s in sorted(result["defense_common"].items(),key=lambda x:-x[1]["points"]):
        rows.append(f"| {NAMES[o]} | {'／'.join(map(str,s['wdl']))} | {s['points']} |")
    rows+=["","## 攻守各占一半","","两侧采用相同两个种子，每版执攻、执守各 14 局。动态、护子、杀棋、诱饵和二代共用同一个守方策略。",
           "","| 版本 | 攻分（28） | 守分（28） | 总分（56） |","|---|---:|---:|---:|"]
    for v,s in sorted(result["both_common"].items(),key=lambda x:-x[1]["points"]):
        rows.append(f"| {NAMES[v]} | {s['attack']} | {s['defense']} | {s['points']} |")
    rows+=["","[赛前赛程](random_league_schedule.json) · [含历史分组、逐对手积分及改手索引的汇总](random_league_summary.json) · [主赛棋谱](random_league_games.json) · [补充守方棋谱](random_league_trained_defense.json)"]
    (HERE/"随机配对赛结果.md").write_text("\n".join(rows)+"\n",encoding="utf8")


def stats(games,side):
    c=Counter(g["winner"] for g in games)
    w,d,l=c[side],c["="],c["A" if side=="D" else "D"]
    return dict(wdl=[w,d,l],points=2*w+d,maximum=2*len(games))


def main():
    plan=json.loads(PLAN.read_text())
    games=json.loads(RESULT.read_text())+json.loads(DEFENSE_RESULT.read_text())
    seeds=plan["seeds"]
    early=seeds[:2]
    keys={(g["opponent"],g["seed"],g["version"]) for g in games}
    expected={tuple(j) for j in plan["jobs"]}|{("trained-defense",s,v) for s in early for v in ATTACKS}
    assert len(games)==len(keys) and keys==expected
    faults=[]
    for g in games:
        if any(w in g["referee"].lower() for w in ("invalid","illegal","exception","exceeded")):
            faults.append([g["opponent"],g["version"],g["seed"],g["referee"]])
        else:
            verify(g)
    result=dict(seeds=seeds,technical=faults,attack={},defense_common={},both_common={},attack_by_opponent={},
                defense_full={},historical={},dynamic_pairings={},attack_split={},attack_all={},attack_eight_common={})
    score=lambda g: {"A":2,"=":1,"D":0}[g["winner"]]
    for o in (*DEFENSES,"trained-defense"):
        field=[g for g in games if g["opponent"]==o]
        result["defense_common"][o]=stats([g for g in field if g["seed"] in early],"D")
        result["defense_full"][o]=stats(field,"D")
    for v in ATTACKS:
        result["attack_all"][v]=stats([g for g in games if g["version"]==v],"A")
        result["attack_eight_common"][v]=stats([g for g in games if g["version"]==v and g["seed"] in early],"A")
        field=[g for g in games if g["version"]==v and g["opponent"] in DEFENSES]
        a=stats(field,"A")
        result["attack"][v]=a
        result["attack_by_opponent"][v]={o:stats([g for g in field if g["opponent"]==o],"A") for o in DEFENSES}
        result["attack_split"][v]={key:stats([g for g in field if (g["opponent"] in ("kurz","PUCT"))==dev],"A")
                                   for key,dev in (("previous_dynamic_field",True),("other_five",False))}
        o={"trained":"trained-defense","easyAI":"easyAI"}.get(v,"PUCT")
        common=stats([g for g in field if g["seed"] in early],"A")
        defend=result["defense_common"][o]
        result["both_common"][v]=dict(attack=common["points"],defense=defend["points"],
                                      points=common["points"]+defend["points"],maximum=56)
        if v=="dynamic":continue
        active={(g["opponent"],g["seed"]):score(g) for g in games if g["version"]=="dynamic"}
        dif=[active[g["opponent"],g["seed"]]-score(g) for g in field]
        result["dynamic_pairings"][v]=[sum(d>0 for d in dif),dif.count(0),sum(d<0 for d in dif)]
    for name in ("attack_series_matches","open_field_matches","native_field_matches","refutation_field_matches"):
        data=json.loads((HERE/(name+".json")).read_text())
        eligible=[g for g in data if g["seed"]!=6101]
        result["historical"][name]={v:stats([g for g in eligible if g["version"]==v],"A")
                                    for v in sorted({g["version"] for g in eligible})}
    changed=[]
    for g in games:
        if g["version"]!="dynamic":
            continue
        for i,row in enumerate(g["plies"]):
            ev=row.get("review_event") or {}
            if ev.get("status")!="changed":continue
            root=Tablut()
            root.past_positions=[root.compute_zobrist_hash(True)]
            with redirect_stdout(StringIO()):
                for j,prior in enumerate(g["plies"][:i]):
                    assert root.make_move(j%2==0,prior["move"])
                    assert not root.check_if_game_over(j%2==1)
                assert official_refutation(root,ev["fixed"])==ev["depth"]
                assert official_refutation(root,ev["replacement"])==0
            changed.append(dict(opponent=g["opponent"],seed=g["seed"],ply=i+1,depth=ev["depth"],winner=g["winner"]))
    result["dynamic_overrides"]=changed
    (HERE/"random_league_summary.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    write_tables(result)
    for k in ("attack","defense_common","both_common","dynamic_pairings","technical"):print(k,result[k])


if __name__=="__main__":
    main()
