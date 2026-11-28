"""Course-rule adapter around the unmodified easyAI 2.0.12 alpha-beta search."""
from time import perf_counter
import sys
from experiment import HERE, coords, winner
from clock_trial import ConditionalClock
from Team01 import Player, WIN, advance, evaluate, moves

sys.path.insert(0, str(HERE/"opponents"/"easyAI-2.0.12-py3-none-any.whl"))
from easyAI import Negamax


class SearchBoard:
    def __init__(self, board, attack, history, deadline, first):
        self.board, self.attack, self.deadline = board, attack, deadline
        self.history = history - {(board,attack)}
        self.stack = []
        self.first = first
        self.nodes = 0

    def switch_player(self):
        self.attack = not self.attack

    def make_move(self, move):
        self.nodes += 1
        if self.nodes % 32 == 0 and perf_counter() >= self.deadline:
            raise TimeoutError
        self.history.add((self.board,self.attack))
        self.stack.append(self.board)
        self.board = advance(self.board,move)

    def unmake_move(self, move):
        self.board = self.stack.pop()
        self.history.remove((self.board,self.attack))

    def possible_moves(self):
        legal = list(moves(self.board,self.attack))
        if not self.stack and self.first in legal:
            legal.remove(self.first)
            legal.insert(0,self.first)
        return legal

    def terminal_score(self):
        result = winner(self.board)
        if result is not None:
            return WIN if result == self.attack else -WIN
        if (self.board,self.attack) in self.history or next(moves(self.board,self.attack),None) is None:
            return 0
        return None

    def is_over(self):
        return self.terminal_score() is not None

    def scoring(self):
        score = self.terminal_score()
        if score is not None:
            return score
        value = evaluate(self.board,self.board.index("K"))
        return -value if self.attack else value


class ExternalAB(Player):
    lengths = (25,57,35)
    budget = ConditionalClock.budget
    search_board = SearchBoard

    def select(self, board, attack, seconds):
        deadline = perf_counter()+seconds
        chosen = next(moves(board,attack))
        self.depth = self.nodes = 0
        for depth in range(1,65):
            state = self.search_board(board,attack,self.history,deadline,chosen)
            search = Negamax(depth)
            try:
                pick = search(state)
            except TimeoutError:
                self.nodes += state.nodes
                break
            self.depth, chosen = depth, pick
            self.nodes += state.nodes
            if abs(search.alpha)>=WIN or perf_counter()>=deadline:
                break
        return chosen

    def _choose(self, grid, attack):
        start = perf_counter()
        self.position = "".join(map("".join,grid))
        self.side_offset = int(not attack)
        self.turns += 1
        self.history.add((self.position,attack))
        chosen = self.select(self.position,attack,self.budget())
        self.history.add((advance(self.position,chosen),not attack))
        self.remaining -= perf_counter()-start
        return coords(chosen)
