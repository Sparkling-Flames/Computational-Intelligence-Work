"""Official 60 s self-play. Fit on the first three games, then compare held-out seeds."""
import argparse
from contextlib import redirect_stdout
import io
import json
from experiment import HERE, PUCTPlayer, Recorder, Tablut
from clock_trial import ConditionalClock


CALIBRATION = (3101, 3103, 3105)
HOLDOUT = (3201, 3203, 3205)
RESULT = HERE / "midgame_clock_results.json"


class ClockRecorder(Recorder):
    def call(self, attack, grid):
        move = super().call(attack, grid)
        p = self.player
        self.log[-1].update(base_seconds=round(p.base_seconds, 4),
                            expected=getattr(p, "expected_moves", None),
                            before=p.base_snapshot, after=p.end_snapshot)
        return move


def game(seed, policy, lengths):
    log, referee, output = [], Tablut(), io.StringIO()
    players = []
    for value in (seed, seed+1):
        p = ConditionalClock(value, lengths) if policy == "conditional" else PUCTPlayer(value)
        p.trace_clock = True
        players.append(ClockRecorder(p, log))
    with redirect_stdout(output):
        referee.play(*players)
    message = output.getvalue()
    assert not any(s in message.lower() for s in ("exception", "illegal", "exceeded")), message
    return dict(seed=seed, policy=policy, winner=referee.winner or "=", plies=log, referee=message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("calibration", "holdout"))
    args = parser.parse_args()
    data = json.loads(RESULT.read_text()) if RESULT.exists() else []
    schedule = [(s, "calibration") for s in CALIBRATION] if args.stage == "calibration" else [
        (s, policy) for i, s in enumerate(HOLDOUT)
        for policy in (("conditional", "baseline") if i%2 == 0 else ("baseline", "conditional"))]
    lengths = [len(g["plies"]) for g in data if g["policy"] == "calibration"]
    if args.stage == "holdout" and len(lengths) != len(CALIBRATION):
        raise ValueError("Complete calibration first")
    for seed, policy in schedule:
        if any(g["seed"] == seed and g["policy"] == policy for g in data):
            continue
        g = game(seed, policy, lengths)
        data.append(g)
        tmp = RESULT.with_suffix(".part")
        tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf8")
        tmp.replace(RESULT)
        print(seed, policy, len(g["plies"]), g["winner"],
              [round(60-sum(r["seconds"] for r in g["plies"] if r["side"] == side), 2)
               for side in ("A", "D")], flush=True)


if __name__ == "__main__":
    main()
