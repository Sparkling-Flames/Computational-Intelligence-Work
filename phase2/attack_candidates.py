"""Experimental attack reviews. Only completed proofs may override the fallback."""
from time import perf_counter
from attacker import SupportedAttack, ValueModel, HERE
from Team01 import advance, moves
from review import _winner, _can_win_now


def before(deadline):
    if perf_counter() >= deadline:
        raise TimeoutError


def forced_capture(board, history, options, deadline):
    """Find an attack that wins now or after every legal defender reply."""
    for move in options:
        before(deadline)
        child = advance(board,move)
        result = _winner(child)
        if result == "A":
            return move
        if result or (child,False) in history:
            continue
        had_reply = False
        for reply in moves(child,False):
            before(deadline)
            had_reply = True
            after = advance(child,reply)
            if _winner(after) or (after,True) in history or not _can_win_now(after,True):
                break
        else:
            if had_reply:
                return move
    return None


def hook_replies(board, move, history, deadline):
    """Capture of the offered attacker is bait only if it allows immediate king capture."""
    child = advance(board,move)
    if _winner(child) or (child,False) in history:
        return None
    replies, bites = [], []
    for reply in moves(child,False):
        before(deadline)
        after = advance(child,reply)
        terminal = _winner(after)
        repeated = (after,True) in history
        if child[move[1]]=="A" and after[move[1]]!="A" and not terminal and not repeated and _can_win_now(after,True):
            bites.append(reply)
        replies.append((reply,after))
    return (child,replies,bites) if bites else None


def proof_after_refusal(candidate,history,deadline):
    child,replies,bites = candidate
    for reply,after in replies:
        before(deadline)
        if reply in bites:
            continue
        if _winner(after) or (after,True) in history:
            return False
        if not _can_win_now(after,True):
            seen = history | {(child,False),(after,True)}
            if forced_capture(after,seen,moves(after,True),deadline) is None:
                return False
    return True


class FinishAttack(SupportedAttack):
    check_hooks = False

    def review(self, board, attack, ordered_moves, deadline):
        start = perf_counter()
        duration = max(0,deadline-start)
        self.events = dict(hooks_found=0, rejected=0, hook_timeout=False, choice="fallback")
        try:
            win = forced_capture(board,self.history,ordered_moves,start+0.35*duration)
            if win is not None:
                self.events["choice"]="forced_three"
                return win
        except TimeoutError:
            pass
        if self.check_hooks:
            cap=start+0.55*duration
            try:
                for move in ordered_moves[:10]:
                    candidate = hook_replies(board,move,self.history,cap)
                    if candidate:
                        self.events["hooks_found"]+=1
                        if proof_after_refusal(candidate,self.history,cap):
                            self.events["choice"]="proved_hook"
                            return move
                        self.events["rejected"]+=1
            except TimeoutError:
                self.events["hook_timeout"]=True
        return super().review(board,attack,ordered_moves,deadline)

    def _choose(self, grid, attack):
        self.events = None
        return super()._choose(grid,attack)


class CertifiedHook(FinishAttack):
    check_hooks = True


class RetrainedFinish(FinishAttack):
    def __init__(self, seed):
        super().__init__(seed)
        self.value_model=ValueModel.load(HERE/"attack_series_value.json")
