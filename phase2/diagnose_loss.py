"""Find short forced defender wins in the recorded 72-ply PUCT attack loss."""
import json
from pathlib import Path
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "required_files"))
from Team01 import INITIAL, advance, moves
from review import _can_win_now, _winner


def flat(move):
    return tuple(r * 9 + c for r, c in move)


def packed(move):
    return move[0] * 81 + move[1]


def display(move):
    return "→".join("(%d,%d)" % divmod(s, 9) for s in move)


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


def forced_win(board, attack_move, history, depth, preferred=None):
    """Prove a defender win in at most depth further plies (depth odd)."""
    if depth == 3:
        distance, line, count = danger(board, attack_move, history, preferred)
        return (line[0], count) if distance else None
    child = advance(board, attack_move)
    if _winner(child) or (child, False) in history:
        return None
    if _can_win_now(child, False):
        return direct_win(child), 0
    choices = sorted(moves(child, False), key=lambda m: (m != preferred, child[m[0]] != "K"))
    for first in choices:
        second = advance(child, first)
        if _winner(second) or (second, True) in history:
            continue
        seen = history | {(child, False), (second, True)}
        blocks = list(moves(second, True))
        for block in blocks:
            if not forced_win(second, block, seen, depth - 2):
                break
        else:
            if blocks:
                return first, len(blocks)
    return None

def main():
    games = json.loads((HERE / "results.json").read_text(encoding="utf8"))["games"]
    game = next(g for g in games if g["variant"] == "PUCTPlayer" and
                g["side"] == "A" and g["winner"] == "D" and len(g["plies"]) == 72)
    played = [flat(p["move"]) for p in game["plies"]]
    board = INITIAL
    history = {(board, True)}
    keys = []
    for i, move in enumerate(played):
        attack = i % 2 == 0
        if attack:
            loss, line, blocks = danger(board, move, history, played[i+1])
            if "--verify-prefix" in sys.argv and i < 64:
                assert not forced_win(board, move, history, 7, played[i + 1])
            if i == 64:
                first, count = forced_win(board, move, history, 7, played[i + 1])
                assert not forced_win(board, move, history, 5)
                alternative = (39, 38)
                assert alternative in moves(board, True)
                assert not forced_win(board, alternative, history, 7)
                child = advance(board, alternative)
                second = advance(child, first)
                seen = history | {(child, False), (second, True)}
                block = next(m for m in moves(second, True) if not forced_win(second, m, seen, 5))
                msg = (f"实战 {display(move)} 后，守方 {display(first)} 腾开国王左侧。攻方此后全部 "
                       f"{count} 种回应都让守方能再于五手内获胜。若先走 {display(alternative)}，"
                       f"经枚举，守方 {len(list(moves(child, False)))} 种应对都不能强制在七手内取胜。"
                       f"例如守方仍走 {display(first)}，攻方可 {display(block)} 补上通道。更远胜负未定。")
                keys.append(dict(ply=i + 1, text=msg, forcedIn=7, alternative=packed(alternative),
                                 alternativeLine=list(map(packed, [alternative, first, block])),
                                 line=[packed(first)], attackOptions=len(list(moves(board, True)))))
                print(i + 1, msg, flush=True)
            if i == 66:
                first, count = forced_win(board, move, history, 5, played[i + 1])
                legal = list(moves(board, True))
                distances = [danger(board, m, history)[0] or
                             (5 if forced_win(board, m, history, 5, first) else 0) for m in legal]
                assert not loss and 0 not in distances
                msg = (f"实战 {display(move)} 后国王 {display(first)}。攻方 {count} 种合法应对"
                       f"都挡不住守方再于三手内取胜。即使改选，本手 {len(legal)} 种攻法中，"
                       f"{distances.count(3)} 种让守方三手内赢，另 {distances.count(5)} 种至多延至五手。")
                keys.append(dict(ply=i + 1, text=msg, forcedIn=5, alternative=None, safeCount=0,
                                 line=[packed(first)], attackOptions=len(legal)))
                print(i + 1, msg, flush=True)
            if loss:
                legal = list(moves(board, True))
                checks = {m: danger(board, m, history)[0] for m in legal}
                safe = [m for m in legal if not checks[m]]
                # Prefer illustrating a defence with the same attacker.
                safe.sort(key=lambda m: (m[0] != move[0], m))
                msg = "实战攻方走 "+display(move)+"。"
                if loss == 1:
                    msg += "守方有一步胜着 "+display(line[0])+"。"
                else:
                    msg += ("守方可走 "+display(line[0])+"，攻方 "+str(blocks)
                            +" 种合法应对之后守方都能一步获胜。例："+display(line[1])
                            +"，守方 "+display(line[2])+"。")
                if safe:
                    msg += (f"攻方当时有 {len(safe)}/{len(legal)} 手可避免上述深度内的强败，"
                            +"例如 "+display(safe[0])+"；更长变化未定。")
                else:
                    fast = sum(v == 1 for v in checks.values())
                    if fast == len(legal):
                        msg += f"攻方全部 {fast} 种合法着法均允许守方下一手取胜。"
                    else:
                        msg += f"攻方 {len(legal)} 种着法中，{fast} 种允许一步赢，其余允许三手内赢。"
                keys.append(dict(ply=i+1, text=msg, forcedIn=loss, attackOptions=len(legal),
                                 safeCount=len(safe), alternative=packed(safe[0]) if safe else None,
                                 line=list(map(packed,line))))
                print(i+1,msg,flush=True)
        assert move in moves(board, attack)
        board = advance(board, move)
        history.add((board, not attack))
    assert _winner(board) == "D"
    remaining = {"A": 60.0, "D": 60.0}
    clock = []
    for row in game["plies"]:
        side = row["side"]
        clock.append(dict(before=round(remaining[side], 6), spent=row["seconds"]))
        remaining[side] -= row["seconds"]
    data = dict(moves=list(map(packed,played)), keys=keys, clock=clock)
    (ROOT/"棋盘分析"/"loss-data.js").write_text(
        "const lossReview = "+json.dumps(data,ensure_ascii=False,indent=2)+";\n",encoding="utf8")


if __name__ == "__main__":
    main()

