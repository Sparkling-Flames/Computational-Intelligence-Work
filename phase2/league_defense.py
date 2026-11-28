"""Only run the missing trained defense. All other defender results already exist."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import random
from random_league import ATTACKS, HERE, PLAN, play

RESULT=HERE/"random_league_trained_defense.json"


def main():
    plan=json.loads(PLAN.read_text())
    # The first two drawn seeds, chosen before looking at scores, give a common
    # 14-game sample for every defender without replaying their existing games.
    jobs=[("trained-defense",s,v) for s in plan["seeds"][:2] for v in ATTACKS]
    random.Random(plan["master"]+1).shuffle(jobs)
    records=json.loads(RESULT.read_text()) if RESULT.exists() else []
    done={(g["opponent"],g["seed"],g["version"]) for g in records}
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(play,None,j) for j in jobs if j not in done]
        for future in as_completed(futures):
            records.append(future.result())
            tmp=RESULT.with_suffix(".part")
            tmp.write_text(json.dumps(records,separators=(",",":")))
            tmp.replace(RESULT)
            print(len(records),flush=True)


if __name__=="__main__":
    main()
