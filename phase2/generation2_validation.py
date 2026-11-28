"""Frozen tactical checks and blind three-ply continuations on disjoint positions."""
from functools import lru_cache
import json
from statistics import median
from experiment import HERE, PUCTPlayer, forced_in_three, winner, flat
from generation2 import GAMES, MODEL, CLEAN, ValueModel, position, fixtures, old_training, protected, symmetries, states_for
from diagnose_loss import forced_win, danger
from easyai_opponent import ExternalAB
from clock_trial import ConditionalClock
from Team01 import advance, moves
from review import _can_win_now
from review_clock_choices import forced_after


def puct(model, seed, visits):
    return PUCTPlayer(seed=seed,value_model=model,max_visits=visits)


def pick(player,prefix):
    board,attack,history=position(prefix)
    player.history=history
    if isinstance(player,ExternalAB):
        return player.select(board,attack,2.0)
    player._tree(board,attack,float("inf"))
    return player.root_order[0]


def packed(m):
    return 81*m[0]+m[1]


@lru_cache(None)
def safe(prefix,move,horizon):
    board,attack,history=position(prefix)
    assert attack
    return not forced_win(board,move,history,horizon)


def hardest(prefix):
    board,attack,history=position(prefix)
    assert not attack
    rows=[]
    candidates=0
    for move in moves(board,False):
        child=advance(board,move)
        if winner(child) is not None or (child,True) in history:
            continue
        candidates+=1
        if forced_after(board,False,move,history,5):
            continue
        seen=history|{(child,True)}
        answers=list(moves(child,True))
        escapes=[m for m in answers if not danger(child,m,seen)[0]]
        if answers:
            rows.append((len(escapes),move,len(answers),escapes))
    return min(rows),candidates,len(rows)


def fixed(player, lines, fork):
    rows={}
    for key in ("bait","recognize","continue","defend","hard_reply"):
        prefix=lines[key]
        move=pick(player,prefix)
        if key=="bait":
            ok=move==(49,51)
        elif key=="recognize":
            ok=move==(41,42)
        elif key=="continue":
            ok=move in fork
        else:
            ok=safe(tuple(prefix),move,7 if key=="defend" else 5)
        rows[key]=dict(move=move,ok=ok)
    return rows


def chain(model,seed,lines,first_key,next_key,prescribed,good):
    p=puct(model,seed,16000)
    first=pick(p,lines[first_key])
    # Selecting a known move counterfactually makes a continuation probe even if the root failed.
    p.retain_move(prescribed)
    second=pick(p,lines[next_key])
    return dict(first=first,follow=second,inherited=p.inherited_visits,
                both=first==prescribed and good(second),follow_ok=good(second))


def unseen_cases(records, seen):
    cases=[]
    for g in records:
        if g["seed"]<5048: continue
        # One non-immediate forced win per game, chosen before asking either tested model.
        for i in range(len(g["moves"])-3,max(5,len(g["moves"])-10),-1):
            prefix=g["moves"][:i]
            b,a,h=position(prefix)
            if (b,a) in seen or _can_win_now(b,a): continue
            solutions=forced_in_three(b,a,h)
            if solutions:
                cases.append((g["seed"],prefix,solutions))
                break
    return cases


def blind_defence(records,seen,models):
    trials=[]
    for g in records:
        if g["seed"]<5048:
            continue
        for i in range(len(g["moves"])-4,max(5,len(g["moves"])-16),-1):
            prefix=g["moves"][:i]
            b,a,h=position(prefix)
            if (b,a) in seen or _can_win_now(b,a):
                continue
            legal=list(moves(b,a))
            escapes=[]
            # Stop testing this position once too many moves survive the horizon.
            for m in legal:
                if not forced_after(b,a,m,h,3):
                    escapes.append(m)
                    if len(escapes)*4>len(legal):
                        break
            if not escapes or len(escapes)*4>len(legal):
                continue
            trial=dict(seed=g["seed"],ply=i+1,side="A" if a else "D",legal=len(legal),escapes=escapes)
            for label,model in models.items():
                m=pick(puct(model,11,640),prefix)
                trial[label]=dict(move=m,ok=m in escapes)
            trials.append(trial)
            break
    return trials


def clock_checks(result):
    old=next(g for g in json.loads((HERE/"results.json").read_text())["games"]
             if g["variant"]=="PUCTPlayer" and g["side"]=="A" and len(g["plies"])==72)
    clock_games=[g for g in json.loads((HERE/"midgame_clock_results.json").read_text())
                 if g["policy"]=="conditional" and len(g["plies"])>=35]
    def left(g,n):
        return 60-sum(r["seconds"] for r in g["plies"][:n] if r["side"]=="A")
    lines=fixtures()
    lines["hard_reply"]=lines["defend"]+[packed((39,38)),packed(result["guard_reply"]["move"])]
    clocks={"bait":median(left(g,32) for g in clock_games),"defend":left(old,64)}
    out={}
    for engine in ("candidate","easyAI"):
        out[engine]={}
        for first,nextkey,expected in (("bait","continue",(49,51)),("defend","hard_reply",(39,38))):
            p=ExternalAB() if engine=="easyAI" else ConditionalClock(11)
            if engine=="candidate": p.value_model=ValueModel.load(MODEL)
            p.remaining=clocks[first]
            p.turns=len(lines[first])//2
            logs=[]
            for key in (first,nextkey):
                board,attack,h=position(lines[key])
                p.history=h
                before=p.remaining
                m=flat(p.play_attacker([list(board[i:i+9]) for i in range(0,81,9)]))
                if key in ("bait","continue"):
                    ok = m == ((35,34) if key=="continue" else expected)
                else:
                    ok = safe(tuple(lines[key]),m,7 if key=="defend" else 5)
                logs.append(dict(key=key,move=m,ok=ok,remaining=before,seconds=before-p.remaining,
                                 depth=p.depth,visits=getattr(p,"visits",None)))
            out[engine][first]=logs
    result["match_clock_replay"]=out


def main():
    records=json.loads(GAMES.read_text())
    reserved=protected()
    fit_ids=json.loads((HERE/"generation2_metrics.json").read_text())["train_seeds"]
    training=old_training(reserved)+[g for g in records if g["seed"] in fit_ids]
    seen={v for g in training for b,a in states_for(g)[0] for v in symmetries(b,a)}
    lines=fixtures()
    repair=lines["defend"]+[packed((39,38))]
    (count,reply,total,escapes),n,viable=hardest(repair)
    lines["hard_reply"]=repair+[packed(reply)]
    assert all(position(prefix)[:2] not in seen for prefix in lines.values())
    fork=forced_in_three(*position(lines["continue"]))
    result=dict(guard_reply=dict(move=reply,nonterminal_options=n,avoid_forced_capture_in_five=viable,legal_answers=total,
                                 escapes_within_three=count,escapes=escapes),fixed={},chains={},blind=[])
    cases=unseen_cases(records,seen|reserved)
    models={"parent":ValueModel.load(CLEAN),"candidate":ValueModel.load(MODEL)}
    for label,model in models.items():
        result["fixed"][label]=[fixed(puct(model,s,16000),lines,fork) for s in (11,29,47)]
        result["chains"][label]=[dict(seed=s,
            trap=chain(model,s,lines,"bait","continue",(49,51),lambda m:m in fork),
            repair=chain(model,s,lines,"defend","hard_reply",(39,38),
                         lambda m:safe(tuple(lines["hard_reply"]),m,5))) for s in (11,29,47)]
        print(label,result["chains"][label],flush=True)
    result["fixed"]["easyAI_2s"]=fixed(ExternalAB(),lines,fork)
    for seed,prefix,solutions in cases:
        b,a,h=position(prefix)
        trial=dict(seed=seed,ply=len(prefix)+1,side="A" if a else "D",solutions=sorted(solutions))
        for label,model in models.items():
            p=puct(model,11,640)
            m=pick(p,prefix)
            won=0
            replies=[]
            if m in solutions:
                child=advance(b,m)
                replies=list(moves(child,not a))
                for r in replies:
                    nxt=prefix+[packed(m),packed(r)]
                    assert position(nxt)[:2] not in seen
                    f=pick(p,nxt)
                    assert winner(advance(position(nxt)[0],f))==a
                    won+=1
            trial[label]=dict(move=m,ok=m in solutions,winning_finishes=won,replies=len(replies))
        result["blind"].append(trial)
    clock_checks(result)
    result["blind_defence"]=blind_defence(records,seen|reserved,models)
    (HERE/"generation2_validation.json").write_text(json.dumps(result,indent=2))
    print("blind",len(cases),{k:sum(r[k]["ok"] for r in result["blind"]) for k in models})


if __name__=="__main__":
    main()
