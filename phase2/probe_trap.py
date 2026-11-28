"""Replay seed 1006 and test defenders against the attack on ply 33."""
import json
from experiment import HERE, ROOT, PUCTPlayer, coords, replay
from Team01 import advance, moves
from review import _winner, _can_win_now


def main():
    games = json.loads((HERE / "selfplay_games.json").read_text())["games"]
    game = next(g for g in games if g["seed"] == 1006)
    grid, history = replay([coords(divmod(m, 81)) for m in game["moves"][:33]])
    board = "".join(map("".join, grid))
    legal = list(moves(board, False))
    losses, captures = set(), []
    for move in legal:
        child = advance(board, move)
        if child.count("A") < board.count("A"):
            captures.append(move)
        if not _winner(child) and (child, True) not in history and _can_win_now(child, True):
            losses.add(move)
    trials = {}
    for limit in (40, 160, 640):
        count = 0
        for seed in range(20):
            p = PUCTPlayer(seed, max_visits=limit)
            p.history = history
            p._tree(board, False, float("inf"))
            count += p.root_order[0] in losses
        trials[limit] = count
    assert len(legal) == 53 and len(losses) == 52 and captures == [(41,50)]
    assert set(legal)-losses == {divmod(game["moves"][33],81)}
    taker = advance(board, captures[0])
    wins = [m for m in moves(taker, True) if _winner(advance(taker,m)) == "A"]
    follow = [(35,34),(66,68),(31,32)]
    block = advance(board, divmod(game["moves"][33],81))
    fork = advance(block, follow[0])
    answers = list(moves(fork, False))
    assert len(answers) == 39 and follow[1] in answers
    for m in answers:
        reply = advance(fork, m)
        assert not _winner(reply) and (reply,True) not in history | {(block,True)}
        assert _can_win_now(reply,True)
    assert _winner(advance(advance(fork,follow[1]),follow[2])) == "A"
    packed = lambda m: 81*m[0]+m[1]
    data = dict(moves=game["moves"], take=packed(captures[0]), wins=list(map(packed,wins)),
                lossReplies=len(losses), legal=len(legal), trials=trials, seeds=20, follow=list(map(packed,follow)))
    (ROOT/"棋盘分析"/"trap-review.js").write_text(
        "const trapReview = "+json.dumps(data,separators=(",",":"))+";\n",encoding="utf8")
    print(trials, wins)


if __name__ == "__main__":
    main()
