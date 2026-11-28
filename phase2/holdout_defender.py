"""Held-out opponent for the clock experiment. Freeze its policy before play."""
from collections import deque
from functools import lru_cache

from easyai_opponent import ExternalAB, SearchBoard
from Team01 import EDGE, RAYS


@lru_cache(maxsize=16384)
def escape_distance(board):
    """Shortest number of legal king slides to the edge with other pieces fixed."""
    king = board.index("K")
    queue = deque([(king, 0)])
    seen = {king}
    while queue:
        source, depth = queue.popleft()
        if source in EDGE:
            return depth
        for ray in RAYS[source]:
            for target in ray:
                if board[target] in "AD":
                    break
                if target == 40 or target in seen:
                    continue
                if target in EDGE:
                    return depth + 1
                seen.add(target)
                queue.append((target, depth + 1))
    return 81


class RouteBoard(SearchBoard):
    def scoring(self):
        outcome = self.terminal_score()
        if outcome is not None:
            return outcome
        slides = min(escape_distance(self.board), 5)
        # One slide outranks the entire possible change in normalized material.
        score = 3 - slides + self.board.count("D") / 32 - self.board.count("A") / 64
        return -score if self.attack else score


class RouteAB(ExternalAB):
    search_board = RouteBoard

    def __init__(self, seed=0):
        super().__init__()
        # The upstream search has deterministic move ordering.
        escape_distance.cache_clear()
