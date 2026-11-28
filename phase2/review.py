"""A bounded tactical check of PUCT's root alternatives using the course rules."""

from time import perf_counter

from puct import PUCTPlayer
from Team01 import EDGE, RAYS, advance, moves


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


class ReviewedPlayer(PUCTPlayer):
    review_fraction = 0.25

    def review(self, board, attack, ordered_moves, deadline):
        player = "A" if attack else "D"
        losing = set()
        active = []
        threats = []
        self.review_reason = "keep ranking"
        self.review_replies = 0
        for move in ordered_moves:
            if perf_counter() >= deadline:
                break
            child = advance(board, move)
            winner = _winner(child)
            if winner == player:
                self.review_reason = "immediate win"
                return move
            if winner or (child, not attack) in self.history:
                if winner:
                    losing.add(move)
                continue
            if _can_win_now(child, not attack):
                losing.add(move)
                continue
            # A concrete threat also qualifies a low-visit candidate for early
            # review. Its opponent still gets every legal response in the proof.
            entry = (move, child)
            if _can_win_now(child, attack):
                threats.append(entry)
            else:
                active.append(entry)

        for move, child in threats + active:
            replies = moves(child, not attack)
            saw_reply = False
            for reply in replies:
                if perf_counter() >= deadline:
                    break
                saw_reply = True
                self.review_replies += 1
                after = advance(child, reply)
                winner = _winner(after)
                if winner == player:
                    continue
                if (winner or (after, attack) in self.history
                        or not _can_win_now(after, attack)):
                    break
            else:
                if saw_reply:
                    self.review_reason = "forced win in three plies"
                    return move
            if perf_counter() >= deadline:
                break

        for move in ordered_moves:
            if move not in losing:
                if move != ordered_moves[0]:
                    self.review_reason = "avoid immediate loss"
                return move
        return ordered_moves[0]
