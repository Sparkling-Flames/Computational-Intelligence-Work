"""Attack-side PUCT with a positional evaluation of the king's escape routes."""
from functools import lru_cache
from math import tanh
from pathlib import Path
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "required_files"))
from value_model import ValueModel
from clock_trial import ConditionalClock
from Team01 import RAYS, EDGE, advance, evaluate, moves
from review import _can_win_now, _winner


@lru_cache(maxsize=32768)
def enclosure(board, king):
    score = evaluate(board, king)
    # A line blocked only by a royal guard can open without the attackers moving.
    for ray in RAYS[king]:
        blockers = [board[s] for s in ray if board[s] in "AD"]
        if blockers == ["D"]:
            score += 15
        for s in ray:
            if board[s] not in ".X":
                break
            if s in EDGE or board[s] == "X":
                continue
            cross = RAYS[s][2:] if s % 9 == king % 9 else RAYS[s][:2]
            for route in cross:
                if all(board[t] in ".X" for t in route):
                    score += 4
    # Move reserve pieces off the distant edge to cover the adjacent files.
    for square, piece in enumerate(board):
        if piece == "A":
            y, x = divmod(square, 9)
            distance = abs(y - king//9) + abs(x - king%9)
            score -= max(0, 5-distance)
            if square not in EDGE:
                score -= 2
    return score


class Attacker(ConditionalClock):
    attack_evaluation = staticmethod(enclosure)
    attack_review_fraction = 0.0

    def __init__(self, seed=0):
        super().__init__(seed)
        self.value_model = ValueModel.load(HERE / "generation2_value.json")

    def _choose(self, grid, attack):
        self.static_evaluation = self.attack_evaluation if attack else evaluate
        self.review_fraction = self.attack_review_fraction if attack else 0.0
        return super()._choose(grid, attack)


def material_and_routes(board, king):
    return enclosure(board, king) + 6*(16-board.count("A")) - 7*(8-board.count("D"))


class SupportedAttack(Attacker):
    attack_evaluation = staticmethod(material_and_routes)
    attack_review_fraction = 0.23

    def review(self, board, attack, ordered_moves, deadline):
        if not attack or not self._root or not self._root.children:
            return None
        # Inspect the defender's full reply set before preferring an apparent gain.
        best, best_score = ordered_moves[0], float("-inf")
        for move in ordered_moves[:10]:
            if perf_counter() >= deadline:
                break
            node = self._root.children[move]
            if node.proof is not None:
                if node.proof == -1:
                    return move
                score = -node.proof
            else:
                child = node.board
                worst = 1.0
                for reply in moves(child, False):
                    if perf_counter() >= deadline:
                        return best
                    after = advance(child, reply)
                    result = _winner(after)
                    if result == "D":
                        worst = -1.0
                        break
                    if (after, True) in self.history:
                        value = 0.0
                    elif result == "A" or _can_win_now(after, True):
                        value = 1.0
                    else:
                        value = -tanh(material_and_routes(after, after.index("K"))/35)
                    worst = min(worst, value)
                mean = -node.total/node.visits if node.visits else -node.value
                score = worst if worst == -1 else 0.55*mean + 0.45*worst
            if score > best_score:
                best, best_score = move, score
        return best


# The official runner constructs Player() for each side.
Player = SupportedAttack
