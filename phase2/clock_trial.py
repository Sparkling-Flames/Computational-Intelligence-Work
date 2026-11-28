"""Experimental 60-second match clock fitted to completed game lengths."""
from math import ceil
from puct import PUCTPlayer
from Team01 import CENTRAL, RAYS


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
