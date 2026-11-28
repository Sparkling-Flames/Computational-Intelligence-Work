"""Standalone Tablut player. The course runner constructs one Player per side."""

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
WIN = 10000


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


class Player:
    def __init__(self):
        self.remaining = 60.0
        self.turns = 0
        self.history = {(INITIAL, True)}
        self.depth_limit = 64
        self.depth = self.nodes = 0

    def play_attacker(self, board):
        return self._choose(board, True)

    def play_defender(self, board):
        return self._choose(board, False)

    def _search(self, board, attack, depth, alpha, beta, ply):
        self.nodes += 1
        if self.nodes % 64 == 0 and perf_counter() >= self.deadline:
            raise TimeoutError
        king = board.find("K")
        if king < 0 or king in EDGE or board.count("A") < 2:
            return WIN - ply if attack == (king < 0) else ply - WIN
        key = (board, attack)
        if key in self.history:
            return 0
        if depth == 0:
            if next(moves(board, attack), None) is None:
                return 0
            score = evaluate(board, king)
            return -score if attack else score

        best = -WIN
        self.history.add(key)
        try:
            for move in moves(board, attack):
                score = -self._search(advance(board, move), not attack, depth - 1,
                                      -beta, -alpha, ply + 1)
                best = max(best, score)
                alpha = max(alpha, best)
                if alpha >= beta:
                    break
        finally:
            self.history.remove(key)
        return best if best != -WIN else 0

    def _choose(self, grid, attack):
        start = perf_counter()
        board = "".join(map("".join, grid))
        self.history.add((board, attack))
        self.turns += 1
        available = max(0, self.remaining - 0.5)
        self.deadline = start + available / max(9, 30 - self.turns // 2)
        ordered = list(moves(board, attack))
        chosen = ordered[0]
        self.depth = self.nodes = 0
        for depth in range(1, self.depth_limit + 1):
            best = -WIN
            scores = {}
            try:
                for move in ordered:
                    if perf_counter() >= self.deadline:
                        raise TimeoutError
                    score = -self._search(advance(board, move), not attack, depth - 1,
                                          -WIN, -best, 1)
                    scores[move] = score
                    best = max(best, score)
                    if score == WIN - 1:
                        break
            except TimeoutError:
                break
            # Stable sorting keeps an established best ahead of equal pruning bounds.
            ordered.sort(key=lambda m: scores.get(m, -WIN), reverse=True)
            self.depth, chosen = depth, ordered[0]
            if best >= WIN - depth:
                break
        self.history.add((advance(board, chosen), not attack))
        self.remaining -= perf_counter() - start
        return [list(divmod(square, 9)) for square in chosen]
