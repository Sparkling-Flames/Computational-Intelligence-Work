"""Audit all attacking moves, including wins and mistakes the defender declined."""
import json
from contextlib import redirect_stdout
from io import StringIO

from attack_series import verify
from diagnose_loss import danger
from experiment import ROOT, flat, coords, Tablut
from attack_trial import next_positions
from generation2 import position, symmetries
from native_field import ENGINES, HERE, RESULT, SEEDS
from open_field_report import LABEL, POINTS, same_position
from Team01 import advance, moves, INITIAL
from review import _winner


def packed(m):
    return 81*m[0]+m[1]


def official_win_now(game):
    from copy import copy
    cells="".join(map("".join,game.board))
    # Ordinary defenders can win immediately by capture only with <=5 attackers
    # remaining (at most four captures on one move). Always try every king exit.
    if cells.count("A")<=5:
        return any(end.check_if_game_over(True) and end.winner=="D" for _,end in next_positions(game,False))
    king=cells.index("K")
    r,c=divmod(king,9)
    for to in (r*9,r*9+8,c,72+c):
        end=copy(game)
        end.past_positions=game.past_positions.copy()
        if end.make_move(False,coords((king,to))) and end.check_if_game_over(True) and end.winner=="D":
            return True
    return False


def official_refutation(root,move):
    from copy import copy
    game=copy(root)
    game.past_positions=root.past_positions.copy()
    assert game.make_move(True,coords(move))
    if game.check_if_game_over(False):
        return 0
    if official_win_now(game):
        return 1
    for _,reply in next_positions(game,False):
        if reply.check_if_game_over(True):
            continue
        for _,answer in next_positions(reply,True):
            if answer.check_if_game_over(False) or not official_win_now(answer):
                break
        else:
            return 3
    return 0


def check_example(g,miss):
    root=Tablut()
    root.past_positions=[root.compute_zobrist_hash(True)]
    with redirect_stdout(StringIO()):
        for i,row in enumerate(g["plies"][:miss["ply"]-1]):
            assert root.make_move(i%2==0,row["move"])
            assert not root.check_if_game_over(i%2==1)
        assert official_refutation(root,miss["played"])==miss["depth"]
        assert official_refutation(root,miss["alternative"])==0
        for p in miss["cold_1600"].values():
            assert official_refutation(root,p["move"])==p["forced_defender_win_depth"]


def review(g, excluded):
    prefix=[]
    b=INITIAL
    h={(b,True)}
    records=[]
    tested=0
    used=0.0
    log=g["plies"]
    for i,row in enumerate(log):
        m=flat(row["move"])
        if i%2==0 and (b,True) not in excluded:
            tested+=1
            reply=flat(log[i+1]["move"]) if i+1<len(log) else None
            depth,pv,_=danger(b,m,h,reply)
            if depth:
                alternative=next((n for n in moves(b,True) if n!=m and not danger(b,n,h)[0]),None)
                if alternative:
                    actual_uses_proof=(reply is not None and
                        (_winner(advance(advance(b,m),reply))=="D" if depth==1 else pv[0]==reply))
                    converted=actual_uses_proof and g["winner"]=="D" and len(log)<=i+1+depth
                    records.append(dict(ply=i+1,depth=depth,played=m,alternative=alternative,
                                        proof_line=pv,opponent_found_reply=actual_uses_proof,converted=converted,
                                        attack_seconds_before=round(60-used,6),move_seconds=row["seconds"],
                                        new_visits=row["new_visits"],inherited_visits=row["inherited_visits"]))
                    records[-1].update(board=b,cold_1600=same_position(b,h,g["seed"]))
        if i%2==0:
            used+=row["seconds"]
        prefix.append(packed(m))
        b=advance(b,m)
        h.add((b,i%2==1))
    return dict(opponent=g["opponent"],version=g["version"],seed=g["seed"],winner=g["winner"],
                tested_plies=tested,misses=records)


def main():
    games=json.loads(RESULT.read_text())
    past=json.loads((HERE/"open_field_matches.json").read_text())
    control=[g for g in past if g["opponent"]=="PUCT"]
    old=next(g for g in control if g["seed"]==9102 and g["version"]=="trained")
    b,a,_=position([packed(flat(r["move"])) for r in old["plies"][:54]])
    excluded=set(symmetries(b,a))
    assert len(games)==len(SEEDS)*len(ENGINES)*2
    assert {(g["opponent"],g["seed"],g["version"]) for g in games}=={(e,s,v) for e in ENGINES for s in SEEDS for v in LABEL}
    report=dict(sources={
        "randytli":"https://github.com/randytli/tablut/tree/b2e2fbe9db0b2a9f3abec1974ff6ee442a29d908",
        "kurz":"https://github.com/philipp-kurz/CS61B_P2_Tablut/tree/fccf85a00196dfae96b9ed29b7d00a08318930e1"},
        rule="Official initial position and 60 seconds per side. Whole-game audit excludes the historical ply-55 board and symmetries. Cold paired probe on every avoidable miss with identical history and seed.",
        rows=[],groups={},paired={},technical=[])
    cases=[]
    for g in games+control:
        if any(k in g["referee"].lower() for k in ("exception","invalid","illegal","exceeded")):
            report["technical"].append([g["opponent"],g["seed"],g["version"],g["referee"]])
            continue
        verify(g)
        row=review(g,excluded)
        report["rows"].append(row)
        if g["opponent"]=="PUCT":
            continue
        def priority(m):
            cold=m["cold_1600"]
            return (cold["trained"]["forced_defender_win_depth"]>0 and cold["frozen"]["forced_defender_win_depth"]==0,
                    m["converted"],m["depth"]==3)
        miss=max(row["misses"],key=priority,default=None)
        if miss:
            check_example(g,miss)
            row["official_checked_ply"]=miss["ply"]
        note=f"整局 {len(g['plies'])} 手。"
        if miss:
            alt=miss["alternative"]
            note+=f"第 {miss['ply']} 手后守方可在 {miss['depth']} 手内强胜。另走 {divmod(alt[0],9)} → {divmod(alt[1],9)} 可避开三手内强败。"
            note+=f" 实战落子前攻方约剩 {miss['attack_seconds_before']:.2f} 秒，本手新增 {miss['new_visits']} 次访问。"
        outcome={"A":"攻胜","D":"守胜","=":"和棋"}[g["winner"]]
        cases.append(dict(group="完整引擎 · "+g["opponent"],
            label=f"{LABEL[g['version']]} 对 {g['opponent']} · {g['seed']} · {outcome}",
            moves=[packed(flat(r["move"])) for r in g["plies"]],at=miss["ply"]-1 if miss else 0,note=note,result=g["winner"]))
    for e in (*ENGINES,"PUCT"):
        for v in LABEL:
            rows=[r for r in report["rows"] if r["opponent"]==e and r["version"]==v]
            matches=[g for g in games+control if g["opponent"]==e and g["version"]==v]
            group=dict(wdl=[sum(r["winner"]==w for r in matches) for w in ("A","=","D")],
                       unique_lines=len({tuple(packed(flat(r["move"])) for r in g["plies"]) for g in matches}),
                       games_with_miss=sum(bool(r["misses"]) for r in rows),
                       audited_moves=sum(r["tested_plies"] for r in rows))
            misses=[m for r in rows for m in r["misses"]]
            group.update(misses=len(misses),three_ply_only=sum(m["depth"]==3 for m in misses),
                         actual_forcing_replies=sum(m["opponent_found_reply"] for m in misses),
                         converted=sum(m["converted"] for m in misses))
            report["groups"][e+" "+v]=group
        index={(g["seed"],g["version"]):POINTS[g["winner"]] for g in games+control if g["opponent"]==e}
        diffs=[index[s,"trained"]-index[s,"frozen"] for s,v in index if v=="frozen"]
        report["paired"][e]=[sum(d>0 for d in diffs),diffs.count(0),sum(d<0 for d in diffs)]
    (HERE/"native_field_review.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    (ROOT/"棋盘分析"/"native-field.js").write_text("const nativeFieldCases="+json.dumps(cases,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf8")
    print(json.dumps(report["groups"]),report["paired"],report["technical"])


if __name__=="__main__":
    main()
