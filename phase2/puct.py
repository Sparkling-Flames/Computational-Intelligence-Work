"""Experimental PUCT with static leaf evaluation from the frozen Alpha-Beta player.

Each sample is the backed-up value of a tree leaf, not a simulated game outcome.
All values on a node are from the perspective of the player to move there.
"""

from dataclasses import dataclass
from math import exp, sqrt, tanh
from random import Random
from time import perf_counter

from Team01 import EDGE, Player, advance, evaluate, moves


@dataclass(slots=True)
class Node:
    board: str
    attack: bool
    value: float = 0.0
    prior: float = 0.0
    visits: int = 0
    total: float = 0.0
    proof: int | None = None
    children: dict | None = None


def propagate(node):
    if any(c.proof == -1 for c in node.children.values()):
        node.proof = 1
    elif all(c.proof is not None for c in node.children.values()):
        node.proof = max((-c.proof for c in node.children.values()), default=0)


def contenders(root):
    unresolved = (c for c in root.children.values() if c.proof is None)
    ranked = sorted(unresolved, key=lambda c: c.visits, reverse=True)[:3]
    return {c.board: (1 - c.total / c.visits) / 2 for c in ranked if c.visits >= 20}


def extension_share(earlier, later):
    if not earlier or len(later) < 2:
        return 0.0
    leader = next(iter(later))
    if all(abs(score - later[leader]) > 0.05 for key, score in later.items() if key != leader):
        return 0.0
    moving = leader != next(iter(earlier)) or any(
        abs(later[key] - earlier[key]) >= 0.02 for key in later.keys() & earlier.keys())
    return 1.0 if moving else 1/3


def ordered_moves(root):
    def rank(move):
        c = root.children[move]
        viable = c.proof == -root.proof if root.proof is not None else c.proof != 1
        return viable, c.visits, c.prior
    return sorted(root.children, key=rank, reverse=True)


class PUCTPlayer(Player):
    static_evaluation = staticmethod(evaluate)
    review_fraction = 0.0
    adaptive_time = True
    reuse_discount = 0.5
    trace_clock = False

    def __init__(self, seed=0, value_model=None, max_visits=None, reuse_tree=True):
        super().__init__()
        self.random = Random(seed)
        self.value_model = value_model
        self.max_visits = max_visits
        self.reuse_tree = reuse_tree
        self._retained = self._root = None
        self._expected_history = set()
        self._visits_per_second = 0.
        self.inherited_visits = self.new_visits = 0
        self.visits = 0
        self.root_order = []
        self.root_visits = {}
        self.root_priors = {}

    def budget(self):
        return max(0, self.remaining - 0.5) / max(9, 30 - self.turns // 2)

    def review(self, board, attack, ordered_moves, deadline):
        return None

    def retain_move(self, move):
        """Keep every reply below the move actually played, including sampled moves."""
        if self.reuse_tree and self._root and self._root.children:
            self._retained = self._root.children[move]
            self._expected_history = self.history | {(self._retained.board, self._retained.attack)}
        self._root = None

    def _matching_reply(self, board, attack):
        if not self._retained or not self._retained.children:
            return None
        if self.history != self._expected_history | {(board, attack)}:
            return None
        return next((c for c in self._retained.children.values()
                     if c.board == board and c.attack == attack), None)

    def _expand(self, node, path_keys, deadline):
        children = {}
        options = list(moves(node.board, node.attack))
        self.random.shuffle(options)
        for i, move in enumerate(options):
            if i % 8 == 0 and perf_counter() >= deadline:
                raise TimeoutError
            board = advance(node.board, move)
            attack = not node.attack
            child = Node(board, attack)
            king = board.find("K")
            if king < 0 or king in EDGE or board.count("A") < 2:
                child.proof = 1 if attack == (king < 0) else -1
            elif (board, attack) in path_keys or next(moves(board, attack), None) is None:
                child.proof = 0
            if child.proof is None:
                raw = self.static_evaluation(board, king) * (-1 if attack else 1)
                child.value = tanh(raw / 35)
                child.prior = exp(max(-3, min(3, -raw / 18)))
            else:
                child.value = child.proof
                child.prior = exp(-3 * child.proof)
            children[move] = child
        weight = sum(c.prior for c in children.values())
        for child in children.values():
            child.prior = 0.8 * child.prior / weight + 0.2 / len(children)
        node.children = children
        self.nodes += len(children)
        propagate(node)

    def _tree(self, board, attack, deadline, extra_time=0.0):
        start = perf_counter()
        first_check = start + 0.45 * (deadline - start)
        last_check = start + 0.80 * (deadline - start)
        previous = None
        base_deadline = deadline
        self.base_snapshot = None
        self.extra_seconds = 0.0
        root = self._matching_reply(board, attack) or Node(board, attack)
        self._retained = None
        self._root = root if self.reuse_tree else None
        self.inherited_visits = root.visits
        self.depth = self.visits = 0
        self.nodes = 1
        try:
            if root.children is None:
                self._expand(root, self.history, deadline)
            while root.proof is None and perf_counter() < deadline:
                if (self.trace_clock and self.extra_seconds and self.base_snapshot is None
                        and perf_counter() >= base_deadline):
                    self.base_snapshot = self.snapshot(root)
                if self.max_visits is not None and root.visits >= self.max_visits:
                    break
                if extra_time and root.visits % 16 == 0 and perf_counter() >= first_check:
                    if previous is None:
                        previous = contenders(root)
                        first_check = last_check
                    else:
                        self.extra_seconds = extra_time * extension_share(previous, contenders(root))
                        deadline += self.extra_seconds
                        extra_time = 0.0
                path = [root]
                path_keys = self.history.copy()
                node = root
                while node.children is not None and node.proof is None:
                    scale = 1.7 * sqrt(node.visits + 1)
                    def priority(c):
                        mean = -c.total / c.visits if c.visits else 0.0
                        return (node is root and c.visits == 0,
                                mean + scale * c.prior / (1 + c.visits))
                    node = max((c for c in node.children.values() if c.proof is None),
                               key=priority)
                    path.append(node)
                    path_keys.add((node.board, node.attack))
                if node.visits and node.proof is None:
                    self._expand(node, path_keys, deadline)
                if node.proof is None and self.value_model is not None and not node.visits:
                    node.value = (node.value + self.value_model.value(node.board, node.attack)) / 2
                value = node.value if node.proof is None else node.proof
                for ancestor in reversed(path):
                    if ancestor.children is not None:
                        propagate(ancestor)
                    if ancestor.proof is not None:
                        value = ancestor.proof
                    ancestor.visits += 1
                    ancestor.total += value
                    value = -value
                self.depth = max(self.depth, len(path) - 1)
        except TimeoutError:
            pass
        self.visits = root.visits
        self.new_visits = self.visits - self.inherited_visits
        if root.children is None:
            self.root_order = list(moves(board, attack))
            self.root_visits = dict.fromkeys(self.root_order, 0)
            self.root_priors = {}
            return False

        self.root_order = ordered_moves(root)
        self.end_snapshot = self.snapshot(root) if self.trace_clock else None
        self.root_visits = {m: c.visits for m, c in root.children.items()}
        self.root_priors = {m: c.prior for m, c in root.children.items()}
        return root.proof is not None

    @staticmethod
    def snapshot(root):
        rows = []
        for move in ordered_moves(root)[:2]:
            child = root.children[move]
            value = child.proof if child.proof is not None else (
                child.total / child.visits if child.visits else None)
            rows.append(dict(move=move, visits=child.visits, proof=child.proof,
                             score=None if value is None else round((1-value)/2, 6)))
        return dict(visits=root.visits, top=rows)

    def _choose(self, grid, attack):
        start = perf_counter()
        self.review_reason = None
        board = "".join(map("".join, grid))
        self.turns += 1
        self.history.add((board, attack))
        allowance = self.budget()
        warm = self._matching_reply(board, attack)
        if warm and self._visits_per_second and self.max_visits is None:
            allowance -= min(allowance*self.reuse_discount, warm.visits/self._visits_per_second)
        self.base_seconds = allowance
        self.deadline = start + allowance
        tree_fraction = 1 - self.review_fraction
        extra = 0.0
        if self.adaptive_time and self.max_visits is None:
            extra = max(0.0, min(0.45 * allowance, (self.remaining - 0.6) * 0.25 - allowance))
        proved = self._tree(board, attack, start + allowance * tree_fraction, extra * tree_fraction)
        self.deadline += self.extra_seconds / tree_fraction
        if self.new_visits:
            self._visits_per_second = self.new_visits / max(1e-6, perf_counter()-start)
        chosen = self.root_order[0]
        if self.review_fraction and not proved and perf_counter() < self.deadline:
            reviewed = self.review(board, attack, self.root_order, self.deadline)
            if reviewed is not None:
                chosen = reviewed
        self.retain_move(chosen)
        self.history.add((advance(board, chosen), not attack))
        self.remaining -= perf_counter() - start
        return [list(divmod(square, 9)) for square in chosen]
