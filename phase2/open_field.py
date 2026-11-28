"""Frozen attack versions, five defenders, official whole-game clocks.

Upstream dependencies are confined to the benchmark. tLut white_fitness and its
published weights: MatteoFasulo/Tablut a56a1c2693187402df4b3378e2bfb7cbab1cfda3.
Two-player UCT: pbsinclair42/MCTS f4b6226ce06840e51b66bdca4bedbe2c4c143012.
"""
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from functools import lru_cache
from io import StringIO
import gc
import json
import random
import sys

import numpy as np
from attack_series import HERE, VERSIONS, ExternalAB, ConditionalClock, ValueModel, MODEL, Recorder, Tablut, verify, enclosure
from easyai_opponent import SearchBoard
from experiment import winner
from Team01 import WIN, advance, moves

sys.path.insert(0,str(HERE/"opponents"/"tlut"))
from board import Board
from whiteheuristics import white_fitness
from opponents.sinclair.mcts import mcts

SEEDS=range(9101,9105)
OPPONENTS=("tLut-search","UCT","tLut-greedy","easyAI","PUCT")
RESULT=HERE/"open_field_matches.json"
TRANSLATE=bytes.maketrans(b".DAKX",bytes(range(5)))


@lru_cache(maxsize=32768)
def tlut_value(board):
    original=Board(9,9,"WHITE")
    original.pieces=np.frombuffer(board.encode("ascii").translate(TRANSLATE),dtype=np.uint8).reshape(9,9)
    original.get_black()
    original.get_white()
    return float(white_fitness(original))


class TlutBoard(SearchBoard):
    def scoring(self):
        outcome=self.terminal_score()
        if outcome is not None:
            return outcome
        value=tlut_value(self.board)
        return -value if self.attack else value


class TlutSearch(ExternalAB):
    search_board=TlutBoard


class TlutGreedy(ExternalAB):
    def __init__(self,seed):
        super().__init__()
        self.rng=random.Random(seed)

    def select(self,board,attack,seconds):
        options=list(moves(board,attack))
        self.rng.shuffle(options)
        self.depth,self.nodes=1,len(options)
        def score(move):
            child=advance(board,move)
            outcome=winner(child)
            if outcome is not None:
                return WIN if outcome==attack else -WIN
            if (child,not attack) in self.history or next(moves(child,not attack),None) is None:
                return 0
            return -tlut_value(child) if attack else tlut_value(child)
        return max(options,key=score)


class State:
    """Sinclair's two-player API. Positive reward always denotes a defender win."""
    def __init__(self,board,attack,prior):
        self.board,self.attack=board,attack
        self.repeated=(board,attack) in prior
        self.history=prior|{(board,attack)}
        self.outcome=winner(board)
        self.actions=None

    def getPossibleActions(self):
        if self.actions is None:
            self.actions=list(moves(self.board,self.attack))
        return self.actions

    def isTerminal(self):
        return self.outcome is not None or self.repeated or not self.getPossibleActions()

    def takeAction(self,move):
        return State(advance(self.board,move),not self.attack,self.history)

    def getCurrentPlayer(self):
        return -1 if self.attack else 1

    def getReward(self):
        return -1 if self.outcome is True else 1 if self.outcome is False else 0


class UCT(ExternalAB):
    def select(self,board,attack,seconds):
        root=State(board,attack,self.history-{(board,attack)})
        search=mcts(timeLimit=max(1,1000*seconds))
        move=search.search(root)
        self.nodes=search.root.numVisits
        return move


def play(job):
    name,seed,version=job
    tlut_value.cache_clear()
    enclosure.cache_clear()
    gc.collect()
    attacker=VERSIONS[version](seed)
    if name=="PUCT":
        defender=ConditionalClock(seed+1)
        defender.value_model=ValueModel.load(MODEL)
    elif name=="tLut-greedy":
        defender=TlutGreedy(seed+1)
    else:
        defender={"UCT":UCT,"tLut-search":TlutSearch,"easyAI":ExternalAB}[name]()
    game,log,out=Tablut(),[],StringIO()
    random.seed(seed+1)
    with redirect_stdout(out):
        game.play(Recorder(attacker,log),Recorder(defender,log))
    record=dict(opponent=name,seed=seed,version=version,winner=game.winner or "=",referee=out.getvalue(),
                plies=log,final_board="".join(map("".join,game.board)))
    if "exceeded" not in record["referee"].lower():
        verify(record)
    return record


def main():
    records=json.loads(RESULT.read_text()) if RESULT.exists() else []
    done={(g["opponent"],g["seed"],g["version"]) for g in records}
    variants=("frozen","trained")
    schedule=[(name,seed,variants[(i+j+k)%2]) for j,seed in enumerate(SEEDS)
              for i,name in enumerate(OPPONENTS) for k in (0,1)]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for g in pool.map(play,[x for x in schedule if x not in done]):
            records.append(g)
            tmp=RESULT.with_suffix(".part")
            tmp.write_text(json.dumps(records,separators=(",",":")))
            tmp.replace(RESULT)
            print(len(records),g["opponent"],g["seed"],g["version"],g["winner"],len(g["plies"]),flush=True)


if __name__=="__main__":
    main()
