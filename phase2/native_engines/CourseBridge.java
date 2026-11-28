package tablut;

import java.io.*;
import java.util.*;
import static tablut.Piece.*;
import static tablut.Square.sq;

/** Stdio transport in place of the upstream GUI/controller. */
class Controller {
    final Board position = new Board();
    final Random rng;
    Move chosen;
    Controller(long seed) { rng = new Random(seed); }
    Board board() { return position; }
    int randInt(int n) { return rng.nextInt(n); }
    void reportMove(Move m) { chosen = m; }
}

public class CourseBridge {
    static final int[] DX = {0,-1,0,1}, DY = {-1,0,1,0};
    static final class History {
        final String key;
        final History prior;
        History(String key, History prior) { this.key=key; this.prior=prior; }
        boolean contains(String current) {
            for (History h=this; h!=null; h=h.prior) if (current.equals(h.key)) return true;
            return false;
        }
    }
    static Square offset(Square s, int dir, int steps) {
        int x=s.col()+DX[dir]*steps, y=s.row()+DY[dir]*steps;
        return x>=0 && x<9 && y>=0 && y<9 ? sq(x,y) : null;
    }
    static int around(Board b, Square s, boolean emptyThrone) {
        int n=0;
        for (int d=0;d<4;d++) {
            Square t=offset(s,d,1);
            if (t!=null && (b.get(t)==BLACK || (emptyThrone && t==Board.THRONE && b.get(t)==EMPTY))) n++;
        }
        return n;
    }
    static void transition(Board b, Square from, Square to) {
        Piece p=b.get(from);
        b.put(EMPTY,from);
        b.put(p,to);
        for (int d=0;d<4;d++) {
            Square near=offset(to,d,1), far=offset(to,d,2);
            if (far==null) continue;
            Piece victim=b.get(near), partner=b.get(far);
            boolean castle=far==Board.THRONE && partner==EMPTY;
            boolean capture;
            if (p!=BLACK) capture=victim==BLACK && (partner.side()==WHITE || castle);
            else if (victim==WHITE) capture=partner==BLACK || castle ||
                (far==Board.THRONE && partner==KING && around(b,far,false)==3);
            else if (victim==KING && Math.abs(near.col()-4)+Math.abs(near.row()-4)<=1)
                capture=around(b,near,true)==4;
            else capture=victim==KING && partner==BLACK;
            if (capture) b.put(EMPTY,near);
        }
    }
    static String cells(Board b) {
        StringBuilder s=new StringBuilder(81);
        for (Square t:Square.SQUARE_LIST) {
            Piece p=b.get(t);
            s.append(p==BLACK?'A':p==WHITE?'D':p==KING?'K':t==Board.THRONE?'X':'.');
        }
        return s.toString();
    }
    static String state(Board b) {
        Piece w=b.winner();
        return cells(b)+"/"+(w==null?".":w==BLACK?"A":w==WHITE?"D":"=");
    }
    static int packed(Move m) { return 81*m.from().index()+m.to().index(); }
    public static void main(String[] args) throws Exception {
        Controller c=new Controller(Long.parseLong(args[0]));
        Board b=c.board();
        b.prior=new History(b.encodedBoard(),null);
        AI ai=new AI(WHITE,c);
        System.out.println("READY "+state(b));
        BufferedReader in=new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line=in.readLine())!=null) {
            if (line.equals("children")) {
                StringJoiner out=new StringJoiner(" ");
                for (Move m:b.legalMoves(b.turn())) {
                    Board child=new Board(b);
                    child.makeMove(m);
                    out.add(packed(m)+":"+state(child));
                }
                System.out.println(out);
            } else {
                Move m;
                if (line.equals("choose")) {
                    c.chosen=null;
                    ai.myMove();
                    m=Objects.requireNonNull(c.chosen);
                } else {
                    int n=Integer.parseInt(line);
                    m=Move.mv(sq(n/81),sq(n%81));
                }
                if (!b.legalMoves(b.turn()).contains(m)) throw new IllegalArgumentException("illegal "+m);
                b.makeMove(m);
                System.out.println(packed(m)+" "+state(b));
            }
        }
    }
}
