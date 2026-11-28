"""Generate complete, seed-replayable Tablut games for leaf-value learning."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import random
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "required_files"))
from Tablut import Tablut
from Team01 import INITIAL
from puct import PUCTPlayer


def choose_move(player, board, attack, rng, explore):
    # This offline experiment caps visits rather than wall time.
    proven = player._tree(board, attack, float("inf"))
    if explore and not proven:
        candidates = [m for m in player.root_order[:6] if player.root_visits[m]]
        if candidates:
            return rng.choices(candidates, [player.root_visits[m] for m in candidates])[0]
    return player.root_order[0]


def play_game(seed, visits=160, attack_model=None, defend_model=None, opening_plies=8,
              reuse_tree=False):
    start = perf_counter()
    referee = Tablut()
    referee.past_positions = [referee.compute_zobrist_hash(True)]
    history = {(INITIAL, True)}
    players = {True: PUCTPlayer(seed, value_model=attack_model, max_visits=visits, reuse_tree=reuse_tree),
               False: PUCTPlayer(seed+1, value_model=defend_model, max_visits=visits, reuse_tree=reuse_tree)}
    for player in players.values():
        player.history = history
    rng = random.Random(seed)
    record = []
    output = StringIO()
    with redirect_stdout(output):
        while True:
            attack = len(record) % 2 == 0
            board = "".join(map("".join, referee.board))
            src, dst = choose_move(players[attack], board, attack, rng, len(record)<opening_plies)
            players[attack].retain_move((src, dst))
            if not referee.make_move(attack, [divmod(src, 9), divmod(dst, 9)]):
                raise ValueError(f"Illegal move in seed {seed} at ply {len(record)+1}")
            record.append(src * 81 + dst)
            if referee.check_if_game_over(not attack):
                break
            history.add(("".join(map("".join, referee.board)), not attack))
    return dict(seed=seed, winner=referee.winner or "=", moves=record,
                seconds=round(perf_counter()-start, 4))


def generate(args):
    seed, visits, opening = args
    game = play_game(seed, visits, opening_plies=opening)
    game["split"] = "validation" if seed % 4 == 3 else "train"
    return game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=64)
    parser.add_argument("--first-seed", type=int, default=1000)
    parser.add_argument("--visits", type=int, default=160)
    parser.add_argument("--opening-plies", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", type=Path, default=HERE / "selfplay_games.json")
    args = parser.parse_args()
    if args.count < 1 or args.visits < 1 or args.workers < 1 or args.opening_plies < 0:
        parser.error("count, visits and workers must be positive; opening-plies must be nonnegative")
    config = dict(first_seed=args.first_seed, visits=args.visits, opening_plies=args.opening_plies)
    dataset = dict(**config, games=[])
    if args.output.exists():
        dataset = json.loads(args.output.read_text(encoding="utf8"))
        if any(dataset.get(k) != v for k,v in config.items()):
            raise ValueError("Output path contains a different generation configuration")
    wanted = set(range(args.first_seed, args.first_seed + args.count))
    present = {g["seed"] for g in dataset["games"]}
    pending = sorted(wanted - present)
    if not pending:
        return
    inputs = [(seed, args.visits, args.opening_plies) for seed in pending]
    tmp = args.output.with_suffix(".part")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for game in pool.map(generate, inputs):
            dataset["games"].append(game)
            tmp.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",",":")), encoding="utf8")
            tmp.replace(args.output)
            print(f"{len(dataset['games'])}/{args.count}: seed={game['seed']} "
                  f"winner={game['winner']} plies={len(game['moves'])}", flush=True)


if __name__ == "__main__":
    main()
