"""Tablut tournament player. The official referee constructs Player() per game.

The attacker uses a supported PUCT estimate and a bounded tactical review.
The defender uses PUCT with separately fitted outcome weights.
Both roles share the move rules and maintain their own search state.
"""

from dataclasses import dataclass
from functools import lru_cache
from math import ceil, exp, sqrt, tanh
from random import Random
from time import perf_counter


def _rays(square):
    row, col = divmod(square, 9)
    result = []
    for dy, dx in ((-1, 0), (0, -1), (1, 0), (0, 1)):
        y, x = row + dy, col + dx
        ray = []
        while 0 <= y < 9 and 0 <= x < 9:
            ray.append(y * 9 + x)
            y, x = y + dy, x + dx
        result.append(tuple(ray))
    return tuple(result)


RAYS = tuple(map(_rays, range(81)))
CENTRAL = {40, 39, 41, 31, 49}
EDGE = {i for i in range(81) if min(divmod(i, 9)) == 0 or max(divmod(i, 9)) == 8}
INITIAL = "".join(("...AAA...", "....A....", "....D....", "A...D...A",
                   "AADDKDDAA", "A...D...A", "....D....", "....A....", "...AAA..."))


def moves(board, attack):
    pieces = "A" if attack else "KD"
    for source, piece in enumerate(board):
        if piece not in pieces:
            continue
        for ray in RAYS[source]:
            for target in ray:
                if board[target] == ".":
                    yield source, target
                elif board[target] != "X":
                    break


def advance(board, move):
    source, target = move
    cells = list(board)
    piece = cells[source]
    cells[source] = "X" if source == 40 else "."
    cells[target] = piece
    for ray in RAYS[target]:
        if len(ray) < 2:
            continue
        near, far = ray[:2]
        victim, partner = cells[near], cells[far]
        if piece != "A":
            capture = victim == "A" and partner in "DKX"
        elif victim == "D":
            capture = partner in "AX" or (
                far == 40 and partner == "K" and
                sum(cells[r[0]] == "A" for r in RAYS[40]) == 3)
        elif victim == "K" and near in CENTRAL:
            capture = all(cells[r[0]] in "AX" for r in RAYS[near])
        else:
            capture = victim == "K" and partner == "A"
        if capture:
            cells[near] = "."
    return "".join(cells)


def evaluate(board, king):
    """Score from defender's perspective; ordinary material is secondary to escape."""
    lanes = reach = pressure = 0
    for ray in RAYS[king]:
        pressure += board[ray[0]] == "A"
        for square in ray:
            if board[square] not in ".X":
                break
            reach += board[square] == "."
            lanes += square in EDGE
    return 22 * lanes + 2 * reach - 4 * pressure + 6 * board.count("D") - 3 * board.count("A")


def _winner(board):
    king = board.find("K")
    if king < 0:
        return "A"
    if king in EDGE or board.count("A") < 2:
        return "D"
    return None


def _can_win_now(board, attack):
    king = board.index("K")
    if not attack:
        for ray in RAYS[king]:
            for square in ray:
                if board[square] not in ".X":
                    break
                if square in EDGE:
                    return True
        # A move can capture at most one attacker along each of four rays.
        if board.count("A") <= 5:
            return any(advance(board, m).count("A") < 2 for m in moves(board, False))
        return False

    # To capture the king, the moving attacker must land next to it. Enumerate
    # the first occupied square on each approach ray as a potential source.
    for king_ray in RAYS[king]:
        if not king_ray or board[king_ray[0]] != ".":
            continue
        target = king_ray[0]
        for approach in RAYS[target]:
            for source in approach:
                piece = board[source]
                if piece in ".X":
                    continue
                if piece == "A" and "K" not in advance(board, (source, target)):
                    return True
                break
    return False


def direct_win(board):
    return next(m for m in moves(board, False) if _winner(advance(board, m)) == "D")


def danger(board, attack_move, history, actual_reply=None, *, deadline=None):
    """Report the shortest defender win within 1 or 3 plies after attack_move."""
    child = advance(board, attack_move)
    if _winner(child) or (child, False) in history:
        return 0, [], 0
    if _can_win_now(child, False):
        return 1, [direct_win(child)], 0
    replies = list(moves(child, False))
    if actual_reply in replies:
        replies.remove(actual_reply)
        replies.insert(0, actual_reply)
    for first in replies:
        if deadline is not None and perf_counter() >= deadline:
            raise TimeoutError
        second = advance(child, first)
        if _winner(second) or (second, True) in history:
            continue
        blocks = list(moves(second, True))
        if not blocks:
            continue
        for block in blocks:
            if deadline is not None and perf_counter() >= deadline:
                raise TimeoutError
            third = advance(second, block)
            if (_winner(third) or (third, False) in history or third == child
                    or not _can_win_now(third, False)):
                break
        else:
            block = blocks[0]
            return 3, [first, block, direct_win(advance(second, block))], len(blocks)
    return 0, [], 0


def features(board, attack):
    king = board.index("K")
    row, col = divmod(king, 9)
    reach = clear = adjacent = guard = blocker = 0
    for ray in RAYS[king]:
        occupied = 0
        first = None
        adjacent += bool(ray) and board[ray[0]] == "A"
        for cell in ray:
            piece = board[cell]
            if piece in ".X":
                if first is None and piece == ".":
                    reach += 1
            else:
                occupied += 1
                if occupied == 2:
                    break
                first = piece
        clear += occupied == 0
        guard += occupied == 1 and first == "D"
        blocker += occupied == 1 and first == "A"
    turn = -1 if attack else 1
    return (1, turn, (16 - board.count("A")) / 16, (8 - board.count("D")) / 8,
            max(abs(row-4), abs(col-4)) / 4, reach / 16, clear / 4, adjacent / 4,
            guard / 4, blocker / 4, turn * clear / 4)


class ValueModel:
    """Three affine score rows in defender-win, draw, attacker-win order."""

    def __init__(self, weights):
        self.weights = weights

    def probabilities(self, board, attack):
        king = board.find("K")
        if king < 0:
            return (0., 0., 1.)
        if king in EDGE or board.count("A") < 2:
            return (1., 0., 0.)
        x = features(board, attack)
        scores = [sum(a*b for a,b in zip(row, x)) for row in self.weights]
        maximum = max(scores)
        probs = [exp(v-maximum) for v in scores]
        total = sum(probs)
        return tuple(p/total for p in probs)

    def value(self, board, attack):
        defend, _, attacking = self.probabilities(board, attack)
        return attacking - defend if attack else defend - attacking


ATTACK_WEIGHTS = (
    (
        0.03250550868825114, 0.03461352642977582, 0.23154900490338828,
        -0.228480719034958, -0.26004568330943345, -0.09040807892548837,
        1.0413503945786542, 0.012560659348628636, 0.04968091588213702,
        -0.5469206580462357, 0.7048621979828531,
    ),
    (
        -2.623751918168835, 0.021607320638536362, 2.364837144376876,
        -1.8842936580061365, 0.13564188843833289, 0.160867053350873,
        -0.298802895047588, -0.24472184205611186, -0.22381647121645556,
        0.15568661281921592, -0.38774311991637606,
    ),
    (
        -2.258198405307473, -0.05622084706831216, -2.596386149280266,
        2.112774377041094, 0.12440379487110072, -0.07045897442538458,
        -0.7425474995310659, 0.23216118270748312, 0.17413555533431863,
        0.39123404522701966, -0.3171190780664771,
    ),
)


DEFENSE_WEIGHTS = (
    (
        -0.036669557375238776, 0.025758129487419772, 0.18228949984959328,
        -0.25027751967455353, -0.1966258607492886, -0.2751441159841175,
        1.2778444799380304, 0.2184524998540261, 0.22911373509971938,
        -0.5239348342542832, 0.7100952984663856,
    ),
    (
        -2.210970333257209, 0.028937861042628764, 2.5784614115608933,
        -1.8538591050957094, 0.10270652528761942, 0.301075736875,
        -0.5696924085953551, -0.493605447150747, -0.47680049663912366,
        0.0723513544958393, -0.39342049604560936,
    ),
    (
        -2.232092379467504, -0.054695990530048526, -2.760750911410486,
        2.104136624770263, 0.09391933546166947, -0.02593162089088221,
        -0.7081520713426759, 0.2751529472967209, 0.2476867615394041,
        0.45158347975844443, -0.31667480242077617,
    ),
)


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


class PUCTPlayer:
    static_evaluation = staticmethod(evaluate)
    review_fraction = 0.0
    adaptive_time = True
    reuse_discount = 0.5
    trace_clock = False

    def __init__(self, seed=0, value_model=None, max_visits=None, reuse_tree=True):
        self.remaining = 60.0
        self.turns = 0
        self.history = {(INITIAL, True)}
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


class ConditionalClock(PUCTPlayer):
    # Official PUCT self-play seeds 3101, 3103 and 3105, before testing the clock.
    def __init__(self, seed=0, lengths=(25, 57, 35)):
        super().__init__(seed)
        self.lengths = lengths

    def _choose(self, grid, attack):
        self.position = "".join(map("".join, grid))
        self.side_offset = int(not attack)
        return super()._choose(grid, attack)

    def budget(self):
        played = 2*(self.turns-1) + self.side_offset
        remaining_moves = [ceil((n-played)/2) for n in self.lengths if n>played]
        # Two pseudo-observations prevent a single long game from setting the clock.
        prior = max(9, 30-self.turns//2)
        self.expected_moves = (2*prior + sum(remaining_moves))/(2+len(remaining_moves))
        board = self.position
        king = board.index("K")
        opening = king == 40 and played < 14
        contested = king not in CENTRAL and any(
            sum(board[i] not in ".X" for i in ray)<=2 and any(board[i]=="D" for i in ray)
            for ray in RAYS[king])
        middle = played >= 14 and self.expected_moves >= 5
        self.reuse_discount = 0.20 if middle else 0.50
        factor = 1.85 if contested else 0.70 if opening else 1.45 if middle else 1.0
        usable = max(0, self.remaining-0.6)
        return min(0.25*usable, factor*usable/self.expected_moves)


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


def material_and_routes(board, king):
    return enclosure(board, king) + 6*(16-board.count("A")) - 7*(8-board.count("D"))


class Attacker(ConditionalClock):
    attack_evaluation = staticmethod(enclosure)
    attack_review_fraction = 0.0

    def _choose(self, grid, attack):
        self.static_evaluation = self.attack_evaluation if attack else evaluate
        self.review_fraction = self.attack_review_fraction if attack else 0.0
        return super()._choose(grid, attack)


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


class Player:
    """Competition entry point. Each call returns [[from_row, from_col], [to_row, to_col]]."""

    def __init__(self):
        self._attacker = DynamicAttack()
        self._attacker.value_model = ValueModel(ATTACK_WEIGHTS)
        self._defender = ConditionalClock()
        self._defender.value_model = ValueModel(DEFENSE_WEIGHTS)

    def play_attacker(self, board):
        return self._attacker._choose(board, True)

    def play_defender(self, board):
        return self._defender._choose(board, False)
