"""Lightweight W/D/L value model for nonterminal Tablut positions.

Inputs to fit/evaluate_games are (states, result) pairs. Each state is (board,
attack_to_move), and result is "D", "=", or "A". Fit on whole training games;
retain disjoint games for evaluation. Only fitting requires NumPy.
"""

import json
from math import exp, log, tanh
from pathlib import Path

from Team01 import EDGE, RAYS, evaluate


OUTCOMES = ("D", "=", "A")
FEATURES = ("intercept", "defender_turn", "attackers_lost", "defenders_lost",
            "king_distance_from_center", "king_reach", "open_rays",
            "adjacent_attackers", "single_guard_rays", "single_attacker_rays",
            "defender_turn_x_open_rays")


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


def nonterminal(states):
    return [(b, a) for b, a in states
            if "K" in b and b.index("K") not in EDGE and b.count("A") >= 2]


class ValueModel:
    def __init__(self, weights, prior):
        self.weights = weights
        self.prior = prior

    @classmethod
    def fit(cls, games):
        import numpy as np

        x, labels, weights = [], [], []
        for states, result in games:
            positions = nonterminal(states)
            for board, attack in positions:
                x.append(features(board, attack))
                labels.append(OUTCOMES.index(result))
                weights.append(1 / len(positions))
        if not x:
            raise ValueError("Training games must contain nonterminal positions")
        x = np.asarray(x, dtype=float)
        w = np.asarray(weights, dtype=float)
        w /= w.sum()
        y = np.eye(3)[labels]
        # Fixed 3% label smoothing permits finite class probabilities in tiny pilots.
        targets = 0.97*y + 0.01
        prior = (w @ targets).tolist()
        mean = w @ x[:, 1:]
        scale = np.maximum(np.sqrt(w @ (x[:, 1:]-mean)**2), 0.15)
        x[:, 1:] = (x[:, 1:] - mean) / scale
        coeff = np.zeros((3, x.shape[1]))
        coeff[:, 0] = np.log(prior)
        for _ in range(240):
            z = x @ coeff.T
            p = np.exp(z-z.max(axis=1, keepdims=True))
            p /= p.sum(axis=1, keepdims=True)
            gradient = ((p - targets)*w[:, None]).T @ x
            gradient[:, 1:] += 0.05*coeff[:, 1:]
            coeff -= 0.25*gradient
        # Fold training normalization into the deployable affine parameters.
        coeff[:, 1:] /= scale
        coeff[:, 0] -= coeff[:, 1:] @ mean
        return cls(coeff.tolist(), prior)

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

    def evaluate_games(self, games):
        """Average position metrics within each game, then average across games."""
        keys = ("wdl_log_loss", "prior_wdl_log_loss", "score_mse", "prior_score_mse",
                "static_score_mse", "blended_score_mse")
        sums = dict.fromkeys(keys, 0.)
        count = positions_count = 0
        for states, result in games:
            positions = nonterminal(states)
            if not positions:
                continue
            count += 1
            positions_count += len(positions)
            label = OUTCOMES.index(result)
            actual = (1., 0.5, 0.)[label]
            for board, attack in positions:
                p = self.probabilities(board, attack)
                score = p[0] + 0.5*p[1]
                prior_score = self.prior[0] + 0.5*self.prior[1]
                static = (1+tanh(evaluate(board, board.index("K")) / 35))/2
                metrics = (-log(max(p[label], 1e-15)), -log(self.prior[label]),
                           (score-actual)**2, (prior_score-actual)**2,
                           (static-actual)**2, ((static+score)/2-actual)**2)
                for k, v in zip(keys, metrics):
                    sums[k] += v / len(positions)
        if not count:
            raise ValueError("Evaluation games must contain nonterminal positions")
        return {"games": count, "positions": positions_count,
                **{k: v/count for k,v in sums.items()}}

    def save(self, path):
        data = dict(features=FEATURES, outcomes=OUTCOMES, weights=self.weights, prior=self.prior)
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if tuple(data["features"]) != FEATURES or tuple(data["outcomes"]) != OUTCOMES:
            raise ValueError("Incompatible value model features or outcome order")
        return cls(data["weights"], data["prior"])
