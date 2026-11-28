"""Run both search variants with the official referee, one game at a time."""
import contextlib
from copy import deepcopy
import io
import json
import platform
import sys
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "required_files"))
from Team01 import Player, INITIAL, EDGE, advance, moves
from Tablut import Tablut
from puct import PUCTPlayer
from review import ReviewedPlayer


def flat(move):
    return tuple(r * 9 + c for r, c in move)


def coords(move):
    return [list(divmod(i, 9)) for i in move]


def replay(prefix):
    game = Tablut()
    game.past_positions = [game.compute_zobrist_hash(True)]
    history = {(INITIAL, True)}
    for i, move in enumerate(prefix):
        attack = i % 2 == 0
        assert game.make_move(attack, move)
        assert not game.check_if_game_over(not attack)
        history.add(("".join(map("".join, game.board)), not attack))
    return game.board, history


def winner(board):
    king = board.find("K")
    if king < 0:
        return True
    if king in EDGE or board.count("A") < 2:
        return False
    return None


def forced_in_three(board, attack, history):
    """Enumerate all winning first moves, so alternative solutions also get credit."""
    wins = set()
    for first in moves(board, attack):
        child = advance(board, first)
        result = winner(child)
        if result is not None:
            if result == attack:
                wins.add(first)
            continue
        if (child, not attack) in history:
            continue
        replies = list(moves(child, not attack))
        if not replies:
            continue
        for reply in replies:
            second = advance(child, reply)
            result = winner(second)
            if result == attack:
                continue
            if result is not None or (second, attack) in history or not any(
                winner(advance(second, last)) == attack for last in moves(second, attack)
            ):
                break
        else:
            wins.add(first)
    return wins


VARIANTS = (PUCTPlayer, ReviewedPlayer)


def probes():
    games = json.loads((ROOT / "baseline_results.json").read_text())["games"]
    positions = [(g["baseline_side"], [p["move"] for p in g["plies"][:-3]]) for g in games]
    positions.append(("outer_guard", [[[3, 0], [3, 1]], [[2, 4], [2, 2]], [[3, 1], [2, 1]]]))
    records = []
    for case, prefix in positions:
        grid, history = replay(prefix)
        attack = len(prefix) % 2 == 0
        solutions = None if case == "outer_guard" else forced_in_three("".join(map("".join, grid)), attack, history)
        if solutions is not None:
            original = next(g for g in games if g["baseline_side"] == case)
            assert flat(original["plies"][-3]["move"]) in solutions
        for cls in VARIANTS:
            for budget in (0.10, 0.50, 1.90):
                for seed in (11, 29, 47):
                    player = cls(seed=seed)
                    player.history = history.copy()
                    player.budget = lambda: budget
                    player.adaptive_time = False
                    start = perf_counter()
                    move = (player.play_attacker if attack else player.play_defender)(grid)
                    spent = perf_counter() - start
                    row = dict(case=case, variant=cls.__name__, seed=seed, budget=budget,
                               seconds=round(spent, 5), move=move, visits=player.visits,
                               forced=flat(move) in solutions if solutions is not None else None)
                    if case == "outer_guard":
                        row["ranks"] = {str(coords(candidate)): player.root_order.index(candidate)+1
                                        for candidate in ((20, 11), (20, 24), (31, 32), (20, 22))}
                    records.append(row)
    return records


class Recorder:
    def __init__(self, player, log):
        self.player, self.log = player, log

    def call(self, attack, grid):
        method = self.player.play_attacker if attack else self.player.play_defender
        start = perf_counter()
        move = method(grid)
        row = dict(side="A" if attack else "D", move=move, seconds=round(perf_counter()-start, 6),
                   depth=self.player.depth, nodes=self.player.nodes)
        if isinstance(self.player, PUCTPlayer):
            row.update(visits=self.player.visits, inherited_visits=self.player.inherited_visits,
                       new_visits=self.player.new_visits, extra_tree_seconds=round(self.player.extra_seconds, 4),
                       search_first=coords(self.player.root_order[0]))
        if isinstance(self.player, ReviewedPlayer):
            row["review"] = getattr(self.player, "review_reason", None)
        self.log.append(row)
        return move

    def play_attacker(self, grid):
        return self.call(True, grid)

    def play_defender(self, grid):
        return self.call(False, grid)


def match(cls, side):
    game = Tablut()
    log = []
    trial, frozen = Recorder(cls(seed=11), log), Recorder(Player(), log)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        game.play(trial, frozen) if side == "A" else game.play(frozen, trial)
    print(cls.__name__, side, game.winner, len(log), output.getvalue().strip(), flush=True)
    return dict(variant=cls.__name__, side=side, winner=game.winner, seed=11,
                referee=output.getvalue().splitlines(), plies=log)


def check_longer_win():
    """Replay the proof of the alternative move on the attack puzzle."""
    class CaptureTree(PUCTPlayer):
        def _expand(self, node, path_keys, deadline):
            if not hasattr(self, "root"):
                self.root = node
            return super()._expand(node, path_keys, deadline)

    game = Tablut()
    game.past_positions = [game.compute_zobrist_hash(True)]
    records = json.loads((ROOT / "baseline_results.json").read_text())["games"]
    prefix = next(r["plies"][:-3] for r in records if r["baseline_side"] == "A")
    player = CaptureTree(seed=11)
    for row in prefix:
        attack = row["side"] == "A"
        assert game.make_move(attack, row["move"]) and not game.check_if_game_over(not attack)
        player.history.add(("".join(map("".join, game.board)), not attack))
    player.budget = lambda: 5.0
    player.adaptive_time = False
    first = flat(player.play_attacker(game.board))
    assert player.root.proof == 1
    lengths = []

    def verify(referee, node, ply):
        legal = list(moves(node.board, node.attack))
        if ply == 0:
            choices = [first]
        elif node.attack:
            choices = [next(m for m, c in node.children.items() if c.proof == -1)]
        else:
            choices = legal
        for move in choices:
            child = deepcopy(referee)
            assert child.make_move(node.attack, coords(move))
            if child.check_if_game_over(not node.attack):
                assert child.winner == "A"
                lengths.append(ply+1)
            else:
                verify(child, node.children[move], ply+1)

    verify(game, player.root, 0)
    return dict(move=coords(first), min_plies=min(lengths), max_plies=max(lengths),
                terminal_branches=len(lengths))


if __name__ == "__main__":
    result = dict(python=platform.python_version(), probes=probes(), games=[])
    target = HERE / "results.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for cls in VARIANTS:
        for side in ("A", "D"):
            result["games"].append(match(cls, side))
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["verified_attack_line"] = check_longer_win()
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
