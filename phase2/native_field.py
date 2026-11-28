"""Independent native Java players. Compile rule adjustments in a temporary directory."""
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from attack_series import HERE, VERSIONS, Recorder, Tablut, verify, enclosure
from experiment import coords, flat
from Team01 import INITIAL, advance

SEEDS=range(12021,12029)
ENGINES=("randytli","kurz")
RESULT=HERE/"native_field_matches.json"


def java_tool(name):
    configured=Path(os.environ.get("JAVA_HOME",""))/"bin"/(name+".exe")
    return str(configured) if configured.exists() else shutil.which(name)


def compile_engine(engine,dest):
    src=HERE/"opponents"/engine
    dest.mkdir()
    for filename in ("AI","Board","Piece","Player","Square","Move","Utils"):
        code=(src/(filename+".java")).read_text(encoding="utf8")
        if filename=="Board":
            code=code.replace("private Piece _turn;","CourseBridge.History prior;\n    private Piece _turn;")
            code=code.replace("_turn = model._turn;","_turn = model._turn; prior = model.prior; _moveCount=model._moveCount;")
            start=code.index("void makeMove(Square from, Square to) {")
            end=code.index("\n    }",start)
            code=code[:start]+"""void makeMove(Square from, Square to) {
        CourseBridge.transition(this,from,to);
        _turn=_turn.opponent();
        _moveCount++;
        Square king=kingPosition();
        String key=encodedBoard();
        if (king==null) _winner=BLACK;
        else if (king.isEdge() || pieceLocations(BLACK).size()<2) _winner=WHITE;
        else if ((prior!=null && prior.contains(key)) || legalMoves(_turn).isEmpty()) _winner=EMPTY;
        prior=new CourseBridge.History(key,prior);"""+code[end:]
            if engine=="kurz":
                code=code.replace("_state.set(p, s.col(), s.row());","if (p==EMPTY && get(s)==KING) _state.setKing(null);\n        _state.set(p, s.col(), s.row());")
                code=code.replace("(to != THRONE || get(from) == KING)","to != THRONE")
                code=code.replace("get(m.to()) != EMPTY || m.to() == THRONE","get(m.to()) != EMPTY")
                code=code.replace("                    moves.add(m);","                    if (m.to()!=THRONE) moves.add(m);")
            else:
                code=code.replace("if (!from.isRookMove(to))","if (to==THRONE || !from.isRookMove(to))")
        if filename=="AI":
            if engine=="kurz":
                code=code.replace('throw error("Invalid winner.");','tmpScore = 0; // course draw')
            else:
                code=code.replace("if (board.winner() == BLACK)","if (board.winner() == EMPTY) return 0;\n        if (board.winner() == BLACK)")
        (dest/(filename+".java")).write_text(code,encoding="utf8")
    files=[str(p) for p in dest.glob("*.java")]+[str(HERE/"native_engines"/"CourseBridge.java")]
    subprocess.run([java_tool("javac"),"-encoding","UTF-8","-d",str(dest),*files],check=True)


class Engine:
    depth=nodes=0
    def __init__(self,classes,seed):
        self.proc=subprocess.Popen([java_tool("java"),"-Xmx256m","-cp",str(classes),"tablut.CourseBridge",str(seed)],
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        self.previous=INITIAL
        assert self.proc.stdout.readline().strip()=="READY "+INITIAL+"/."

    def ask(self,command):
        self.proc.stdin.write(command+"\n")
        self.proc.stdin.flush()
        line=self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"Java engine exited with status {self.proc.poll()}")
        return line.strip()

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()
        self.proc.stdout.close()

    def play_defender(self,grid):
        board="".join(map("".join,grid))
        a,= [i for i,p in enumerate(self.previous) if p=="A" and board[i]!="A"]
        b,= [i for i,p in enumerate(board) if p=="A" and self.previous[i]!="A"]
        assert self.ask(str(81*a+b)).split()[1]==board+"/."
        encoded,current=self.ask("choose").split()
        move=divmod(int(encoded),81)
        self.previous=advance(board,move)
        assert current.split("/")[0]==self.previous
        return coords(move)


def play(job):
    classes,engine,seed,version=job
    enclosure.cache_clear()
    defender=Engine(Path(classes)/engine,seed+1)
    game,log,out=Tablut(),[],StringIO()
    try:
        with redirect_stdout(out):
            game.play(Recorder(VERSIONS[version](seed),log),Recorder(defender,log))
    finally:
        defender.close()
    g=dict(opponent=engine,seed=seed,version=version,winner=game.winner or "=",referee=out.getvalue(),
           final_board="".join(map("".join,game.board)),plies=log)
    if "exceeded" not in g["referee"].lower():
        verify(g)
    return g


def rule_check(classes):
    from attack_trial import next_positions
    # Compare complete successor sets and terminal outcomes to the independent course
    # referee at several positions from a prior game outside the historic ply-55 probe.
    sample=json.loads((HERE/"open_field_matches.json").read_text())[0]
    official=Tablut()
    official.past_positions=[official.compute_zobrist_hash(True)]
    engine=Engine(classes,0)
    compared=0
    try:
        for i,ply in enumerate(sample["plies"][:32]):
            attack=i%2==0
            if i in (0,1,8,15,24,31):
                actual=dict(entry.split(":") for entry in engine.ask("children").split())
                expected={}
                for m,after in next_positions(official,attack):
                    after.past_positions=after.past_positions.copy()
                    with redirect_stdout(StringIO()):
                        ended=after.check_if_game_over(not attack)
                    a,b=flat(m)
                    expected[str(81*a+b)]="".join(map("".join,after.board))+"/"+((after.winner or "=") if ended else ".")
                assert actual==expected,(classes,i,len(actual),len(expected),set(actual.items())^set(expected.items()))
                compared+=len(actual)
            a,b=flat(ply["move"])
            engine.ask(str(81*a+b))
            assert official.make_move(attack,ply["move"])
            assert not official.check_if_game_over(not attack)
    finally:
        engine.close()
    return compared


def main():
    records=json.loads(RESULT.read_text()) if RESULT.exists() else []
    done={(g["opponent"],g["seed"],g["version"]) for g in records}
    with TemporaryDirectory() as build:
        for engine in ENGINES:
            dest=Path(build)/engine
            compile_engine(engine,dest)
            print(engine,"checked successors",rule_check(dest),flush=True)
        jobs=[(build,e,s,("frozen","trained")[(i+j+k)%2]) for i,s in enumerate(SEEDS) for j,e in enumerate(ENGINES) for k in (0,1)]
        with ProcessPoolExecutor(max_workers=6) as pool:
            for g in pool.map(play,[j for j in jobs if j[1:] not in done]):
                records.append(g)
                tmp=RESULT.with_suffix(".part")
                tmp.write_text(json.dumps(records,separators=(",",":")))
                tmp.replace(RESULT)
                print(len(records),g["opponent"],g["seed"],g["version"],g["winner"],len(g["plies"]),flush=True)


if __name__=="__main__":
    main()
