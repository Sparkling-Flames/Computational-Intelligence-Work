"""Paired matches with an unchanged 23% review slot and an in-tree fixed-policy control."""
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from attack_series import HERE, ConditionalClock, MODEL, ValueModel, Recorder, Tablut, verify, enclosure
from attacker import SupportedAttack
from diagnose_loss import danger
from native_field import Engine, compile_engine, rule_check
from review import _can_win_now, _winner
from Team01 import advance

SEEDS=range(13401,13409)
OPPONENTS=("kurz","PUCT")
RESULT=HERE/"refutation_field_matches.json"


class DynamicAttack(SupportedAttack):
    event=None

    def _choose(self,grid,attack):
        self.event=None
        return super()._choose(grid,attack)

    def review(self,board,attack,ordered_moves,deadline):
        fixed=super().review(board,attack,ordered_moves,deadline)
        if fixed is None:
            return None
        event=self.event=dict(fixed=fixed,status="no_slack",tested=0)
        if perf_counter()>=deadline or len(ordered_moves)<2:
            return fixed
        children=self._root.children
        if children[fixed].proof is not None:
            event["status"]="tree_proof"
            return fixed
        def mean(m):
            n=children[m]
            return -n.total/n.visits if n.visits else -n.value
        # Once the king leaves the throne, escape threats take priority even
        # with a clear search leader. At the throne, inspect close choices only.
        if board[40]=="K" and abs(mean(ordered_moves[0])-mean(ordered_moves[1]))>0.10:
            event["status"]="clear"
            return fixed
        try:
            depth,line,_=danger(board,fixed,self.history,deadline=deadline)
            event["tested"]+=1
            if not depth:
                event["status"]="no_refutation"
                return fixed
            event.update(depth=depth,line=line,status="no_verified_alternative")
            for move in ordered_moves:
                if perf_counter()>=deadline:
                    raise TimeoutError
                if move==fixed or children[move].proof==1:
                    continue
                child=children[move].board
                if _winner(child)=="D":
                    continue
                alt_depth,_,_=danger(board,move,self.history,deadline=deadline)
                event["tested"]+=1
                if not alt_depth:
                    event.update(status="changed",replacement=move)
                    return move
        except TimeoutError:
            event["status"]="out_of_time"
        return fixed


class AttackRecorder(Recorder):
    def call(self,attack,grid):
        m=super().call(attack,grid)
        self.log[-1]["review_event"]=getattr(self.player,"event",None)
        return m


def play(job):
    path,opponent,seed,version=job
    enclosure.cache_clear()
    attacker=(DynamicAttack if version=="dynamic" else SupportedAttack)(seed)
    if opponent=="kurz":
        defender=Engine(Path(path),seed+1)
    else:
        defender=ConditionalClock(seed+1)
        defender.value_model=ValueModel.load(MODEL)
    game,log,out=Tablut(),[],StringIO()
    try:
        with redirect_stdout(out):
            game.play(AttackRecorder(attacker,log),Recorder(defender,log))
    finally:
        if opponent=="kurz":
            defender.close()
    g=dict(opponent=opponent,seed=seed,version=version,winner=game.winner or "=",referee=out.getvalue(),
           final_board="".join(map("".join,game.board)),plies=log)
    if "exceeded" not in g["referee"].lower():
        verify(g)
    return g


def main():
    data=json.loads(RESULT.read_text()) if RESULT.exists() else []
    done={(g["opponent"],g["seed"],g["version"]) for g in data}
    with TemporaryDirectory() as build:
        classes=Path(build)/"kurz"
        compile_engine("kurz",classes)
        print("verified successors",rule_check(classes),flush=True)
        jobs=[(str(classes),o,s,("fixed","dynamic")[(i+j+k)%2]) for i,s in enumerate(SEEDS)
              for j,o in enumerate(OPPONENTS) for k in (0,1)]
        with ProcessPoolExecutor(max_workers=8) as pool:
            for g in pool.map(play,[j for j in jobs if j[1:] not in done]):
                data.append(g)
                tmp=RESULT.with_suffix(".part")
                tmp.write_text(json.dumps(data,separators=(",",":")))
                tmp.replace(RESULT)
                print(len(data),g["opponent"],g["seed"],g["version"],g["winner"],flush=True)


if __name__=="__main__":
    main()
