"""Held-out offers, exact short refutations and fixed-work controls for the attack series."""
import json
from contextlib import redirect_stdout
from io import StringIO
from attack_candidates import hook_replies, proof_after_refusal, forced_capture
from attack_series import HERE, SupportedAttack, ExternalAB, Tablut, Recorder, verify
from attack_series_training import DATA
from generation2 import MODEL, GAMES, ValueModel, protected, old_training, states_for, symmetries, position
from generation2_validation import fixtures
from easyai_opponent import SearchBoard, Negamax
from puct import PUCTPlayer
from experiment import flat,coords
from Team01 import moves,advance
from review import _winner,_can_win_now
from review_clock_choices import forced_after
from time import perf_counter


class FixedAB(ExternalAB):
    def select(self,board,attack,seconds):
        first=None
        self.nodes=0
        for level in (1,2):
            state=SearchBoard(board,attack,self.history,float("inf"),first)
            first=Negamax(level)(state)
            self.nodes+=state.nodes
        self.depth=2
        return first


def fixed_game(seed):
    p=SupportedAttack(seed)
    p.max_visits=320
    p.budget=lambda:float("inf")
    g,log,out=Tablut(),[],StringIO()
    with redirect_stdout(out):
        g.play(Recorder(p,log),Recorder(FixedAB(),log))
    verify(dict(plies=log,winner=g.winner or "=",final_board="".join(map("".join,g.board))))
    return dict(seed=seed,winner=g.winner or "=",moves=[r["move"] for r in log])


def offer_at(b,h):
    if _can_win_now(b,True):
        return None
    for m in moves(b,True):
        c=hook_replies(b,m,h,float("inf"))
        if c and any(not _winner(a) and (a,True) not in h and not _can_win_now(a,True) for _,a in c[1]):
            return m,c
    return None


def assess(b,h,m,c):
    child,replies,bites=c
    history=h|{(child,False)}
    by_move=dict(replies)
    def loses_now(reply):
        after=by_move[reply]
        return not _winner(after) and (after,True) not in h and _can_win_now(after,True)
    catch=set(bites)
    remaining={r:a.count("A") for r,a in replies}
    greedy=[r for r,n in remaining.items() if n==min(remaining.values())]
    out=dict(legal=len(replies),bites=bites,greedy_bite=sum(r in catch for r in greedy)/len(greedy))
    try:
        out["win_within_five"]=proof_after_refusal(c,h,perf_counter()+2)
    except TimeoutError:
        out["win_within_five"]=None
    out["defender_can_force_three"]=forced_after(b,True,m,h,3)
    if out["defender_can_force_three"]:
        out["safer_alternative"]=next((v for v in moves(b,True) if not forced_after(b,True,v,h,3)),None)
    easy=FixedAB()
    easy.history=history.copy()
    ab=easy.select(child,False,0)
    out["ab"] = dict(move=ab,bite=ab in catch,allows_capture=loses_now(ab))
    out["ab_one_second"]=timed_reply(c,h)
    for visits in (40,640):
        trials=[]
        for seed in (61,62,63,64):
            p=PUCTPlayer(seed,max_visits=visits,value_model=ValueModel.load(MODEL))
            p.history=history.copy()
            p._tree(child,False,float("inf"))
            move=p.root_order[0]
            trials.append(dict(seed=seed,move=move,bite=move in catch,allows_capture=loses_now(move)))
        out[str(visits)]=trials
    return out


def timed_reply(candidate,history):
    child,replies,bites=candidate
    p=ExternalAB()
    p.history=history|{(child,False)}
    m=p.select(child,False,1.0)
    after=dict(replies)[m]
    seen=p.history|{(after,True)}
    result=_winner(after)
    if result or (after,True) in history:
        forced=result=="D"
    else:
        answers=list(moves(after,True))
        forced=bool(answers)
        for answer in answers:
            next_board=advance(after,answer)
            if _winner(next_board) or (next_board,False) in seen or not _can_win_now(next_board,False):
                forced=False
                break
    return dict(move=m,bite=m in bites,depth=p.depth,forces_win_within_three=forced)


def main():
    fresh=json.loads(DATA.read_text())
    reserved=protected()
    gen2_ids=json.loads((HERE/"generation2_metrics.json").read_text())["train_seeds"]
    gen3_ids=json.loads((HERE/"attack_series_value_metrics.json").read_text())["new_train_seeds"]
    train=old_training(reserved)+[g for g in json.loads(GAMES.read_text()) if g["seed"] in gen2_ids]
    train.extend(g for g in fresh if g["seed"] in gen3_ids)
    seen=reserved|{v for g in train for b,a in states_for(g)[0] for v in symmetries(b,a)}
    cases=[]
    for g in fresh:
        if g["seed"]<8158:
            continue
        # First matching non-training position per game from ply 15, in board move order.
        for i in range(14,len(g["moves"]),2):
            b,_,h=position(g["moves"][:i])
            if (b,True) in seen:
                continue
            found=offer_at(b,h)
            if found:
                m,c=found
                cases.append(dict(seed=g["seed"],ply=i+1,offer=m,**assess(b,h,m,c)))
                break
    controls=[fixed_game(s) for s in (6101,7221,7222,7223) for _ in range(2)]
    fixed=fixtures()
    b,_,h=position(fixed["bait"])
    known=hook_replies(b,(49,51),h,float("inf"))
    assert known and proof_after_refusal(known,h,float("inf"))
    g=next(g for g in json.loads((HERE/"attack_trial_results.json").read_text())
           if g["version"]=="supported" and g["seed"]==6101)
    b,_,h=position([81*u+v for r in g["plies"][:52] for u,v in [flat(r["move"])]])
    win=forced_capture(b,h,moves(b,True),float("inf"))
    assert win==(18,9)
    result=dict(holdout_games=16,offers=cases,fixed_controls=controls,
                known_bait_proved=True,ply53_win=win)
    (HERE/"attack_series_checks.json").write_text(json.dumps(result,separators=(",",":")))
    print("offers",len(cases),"controls",[(g["seed"],g["winner"],len(g["moves"])) for g in controls])


if __name__=="__main__":
    main()
