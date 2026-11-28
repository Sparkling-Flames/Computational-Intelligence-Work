// The page and its offline Web Worker use the same rules.
function createTablut() {
  const initial = ["...AAA...", "....A....", "....D....", "A...D...A",
    "AADDKDDAA", "A...D...A", "....D....", "....A....", "...AAA..."].join("");
  const rays = Array.from({length:81}, (_, square) =>
    [[-1,0],[0,-1],[1,0],[0,1]].map(([dy,dx]) => {
      const path = [];
      let y = Math.floor(square/9) + dy, x = square%9 + dx;
      while (y>=0 && y<9 && x>=0 && x<9) {
        path.push(y*9+x); y+=dy; x+=dx;
      }
      return path;
    }));
  const owns = (piece, side) => side === "A" ? piece === "A" : piece === "D" || piece === "K";
  const other = side => side === "A" ? "D" : "A";
  const edge = s => s<9 || s>=72 || s%9===0 || s%9===8;
  function moves(board,side) {
    const result = [];
    for (let from=0; from<81; from++) {
      if (!owns(board[from],side)) continue;
      for (const ray of rays[from]) for (const to of ray) {
        if (board[to]==="X") continue;
        if (board[to]!==".") break;
        result.push(from*81+to);
      }
    }
    return result;
  }
  function play(board, move) {
    const from=Math.floor(move/81), to=move%81, cells=board.split("");
    const piece=cells[from];
    cells[from]=from===40 ? "X" : ".";
    cells[to]=piece;
    for (const [near,far] of rays[to]) {
      if (far===undefined) continue;
      const victim=cells[near], partner=cells[far];
      if (piece!=="A") {
        if (victim==="A" && "DKX".includes(partner)) cells[near]=".";
      } else if (victim==="D") {
        if (partner==="A" || partner==="X" || (far===40 && partner==="K" &&
            rays[40].filter(ray=>cells[ray[0]]==="A").length===3)) cells[near]=".";
      } else if (victim==="K") {
        const central=near===40 || rays[40].some(ray=>ray[0]===near);
        if (central ? rays[near].every(ray=>"AX".includes(cells[ray[0]])) : partner==="A") cells[near]=".";
      }
    }
    return cells.join("");
  }
  function winner(board) {
    const k=board.indexOf("K");
    if (k<0) return "A";
    if (edge(k) || board.indexOf("A",board.indexOf("A")+1)<0) return "D";
    return "";
  }
  function features(board) {
    const k=board.indexOf("K");
    let lanes=0, mobility=0, adjacent=0, defenders=0, attackers=0;
    for (const piece of board) {
      if (piece==="D") defenders++;
      if (piece==="A") attackers++;
    }
    if (k>=0) for (const ray of rays[k]) {
      if (board[ray[0]]==="A") adjacent++;
      for (const cell of ray) {
        if (board[cell]==="X") continue;
        if (board[cell]!==".") break;
        mobility++;
        if (!edge(k) && edge(cell)) lanes++;
      }
    }
    return {lanes,mobility,adjacent,defenders,attackers};
  }
  function evaluate(board,side) {
    const f=features(board);
    const score=5*(f.defenders-8)-3*(f.attackers-16)+2*f.mobility+
      18*f.lanes-4*f.adjacent;
    return side==="D" ? score : -score;
  }
  return {initial,owns,other,moves,play,winner,features,evaluate};
}

async function searchPosition({board,side,history,exploreAll=false,wideRoot=false,limitMs=Infinity,id},session) {
  const game=createTablut(), start=performance.now(), past=new Set(history);
  const mode=String(exploreAll)+":"+wideRoot;
  let root=session?.root;
  if (root && session.mode===mode && session.history.length<=history.length &&
      session.history.every((key,i)=>key===history[i])) {
    for (const key of history.slice(session.history.length))
      root=root?.children?.find(c=>c.board+c.side===key);
  } else root=null;
  root=root || node(board,side,null,1);
  const inherited=root.n;
  let positions=0,depth=0,nextReport=0,nextYield=start+20;
  const stack=[root];
  while (stack.length) {
    const p=stack.pop();positions++;
    if (p.children) stack.push(...p.children);
  }
  if (session) Object.assign(session,{root,history,mode});
  const shortlist=new WeakMap();
  function node(board,side,move,prior) {
    return {board,side,move,prior,n:0,points:0,draws:0,children:null,proof:null};
  }
  function expand(parent,seen) {
    const children=game.moves(parent.board,parent.side).map(move=>{
      const next=game.play(parent.board,move), turn=game.other(parent.side);
      const victor=game.winner(next);
      const child=node(next,turn,move,0);
      if (victor) child.proof=victor===turn?1:0;
      else if (seen.has(next+turn)) child.proof=0.5;
      else if (!game.moves(next,turn).length) child.proof=0.5;
      const estimate=child.proof===null ? game.evaluate(next,parent.side) : 80*(0.5-child.proof);
      child.prior=Math.exp(Math.min(3,Math.max(-3,estimate/18)));
      return child;
    });
    const total=children.reduce((sum,c)=>sum+c.prior,0);
    for (const c of children) c.prior=0.8*c.prior/total+0.2/children.length;
    parent.children=children;positions+=children.length;
    updateProof(parent);
  }
  function updateProof(p) {
    if (p.children.some(c=>c.proof===0)) p.proof=1;
    else if (p.children.every(c=>c.proof!==null))
      p.proof=p.children.length ? 1-Math.min(...p.children.map(c=>c.proof)) : 0.5;
  }
  function pick(parent,ply) {
    const interval=ply===0?3:6;
    if (wideRoot && ply<=1 && parent.n>=parent.children.length && parent.n%interval===0) {
      let contenders=shortlist.get(parent);
      // Study-only allocation. Re-evaluate the shortlist so a low-visit challenger can enter.
      if (!contenders?.length || parent.n%72===0) {
        const uncertainty=Math.sqrt(Math.log1p(parent.n));
        const priority=c=>(c.n?1-c.points/c.n:0.5)+uncertainty/Math.sqrt(c.n+1);
        contenders=parent.children.filter(c=>c.proof===null)
          .map(c=>({c,score:priority(c)})).sort((a,b)=>b.score-a.score).slice(0,5).map(r=>r.c);
        shortlist.set(parent,contenders);
      }
      let least=null;
      for (const c of contenders) if (c.proof===null && (!least || c.n<least.n)) least=c;
      if (least) return least;
    }
    let best=null,bestScore=-Infinity;
    for (const c of parent.children) {
      if (c.proof!==null) continue;
      // Visit every root alternative once before concentrating on promising branches.
      const coverage=parent===root && !c.n ? 2 : 0;
      const q=c.n ? 1-c.points/c.n : 0.5;
      const u=1.7*c.prior*Math.sqrt(parent.n+1)/(1+c.n);
      if (coverage+q+u>bestScore) {bestScore=coverage+q+u;best=c;}
    }
    return best;
  }
  function playout(b,turn,seen) {
    // Both sides take immediate king wins; otherwise mix positional and random play.
    for (;;) {
      const legal=game.moves(b,turn);
      if (!legal.length) return "=";
      const k=b.indexOf("K");
      let chosen=null;
      for (const m of legal) {
        const to=m%81;
        if (turn==="D" && Math.floor(m/81)===k &&
            (to<9 || to>=72 || to%9===0 || to%9===8)) return "D";
        if (turn==="A" && Math.abs((to%9)-(k%9))+Math.abs(Math.floor(to/9)-Math.floor(k/9))===1) {
          if (game.play(b,m).indexOf("K")<0) return "A";
        }
      }
      const count=Math.random()<0.30 ? 1 : 3;
      let high=-Infinity;
      for (let i=0;i<count;i++) {
        const m=legal[Math.floor(Math.random()*legal.length)];
        const next=game.play(b,m),value=game.evaluate(next,turn);
        if (value>high) {high=value;chosen=next;}
      }
      b=chosen;
      const winner=game.winner(b);
      if (winner) return winner;
      turn=game.other(turn);
      if (seen.has(b+turn)) return "=";
      seen.add(b+turn);
    }
  }
  function iteration() {
    const path=[root],seen=new Set(past);
    let p=root;
    while (p.proof===null || (p===root && exploreAll)) {
      if (!p.children) {
        // At the storage limit keep sampling full games through the retained tree.
        if ((!p.n && p!==root) || positions>=250000) break;
        expand(p,seen);
        if (p.proof!==null) break;
      }
      p=pick(p,path.length-1);path.push(p);seen.add(p.board+p.side);
    }
    depth=Math.max(depth,path.length-1);
    const outcome=p.proof===null ? playout(p.board,p.side,seen) :
      p.proof===0.5 ? "=" : p.proof===1 ? p.side : game.other(p.side);
    for (let i=path.length-1;i>=0;i--) {
      const v=path[i];v.n++;v.points+=outcome==="="?0.5:Number(outcome===v.side);
      if (outcome==="=") v.draws++;
      if (v.children) updateProof(v);
    }
  }
  function rank(a,b,parent=root) {
    const category=c=>c.proof===0 ? 3 : c.proof===1 ? 0 : 2;
    return category(b)-category(a) || (parent.proof===0.5 ? Number(b.proof===0.5)-Number(a.proof===0.5):0) ||
      b.n-a.n || b.prior-a.prior;
  }
  function report() {
    const rows=root.children.slice().sort(rank).map(c=>{
      const line=[c.move];let p=c;
      while (p.children?.length) {
        p=p.children.slice().sort((a,b)=>rank(a,b,p))[0];
        if (!p.n && p.proof===null) break;
        line.push(p.move);
      }
      const replies=(c.children||[]).filter(r=>r.n || r.proof!==null).sort((a,b)=>rank(a,b,c)).slice(0,3).map(r=>{
        const continuation=r.children?.slice().sort((a,b)=>rank(a,b,r))[0];
        return {move:r.move,n:r.n,wins:Math.round(r.n-r.points-r.draws/2),proof:r.proof,
          next:continuation && (continuation.n || continuation.proof!==null)?continuation.move:null};
      });
      return {move:c.move,replies,replyCount:c.children?.length??null,
        checkedReplies:c.children?.filter(r=>r.n || r.proof!==null).length??0,
        value:c.proof!==null ? 100*(1-c.proof) : c.n ? 100*(1-c.points/c.n) : null,
        n:c.n,draws:c.draws,wins:Math.round(c.n-c.points-c.draws/2),prior:c.prior,proof:c.proof!==null,line};
    });
    postMessage({id,rows,nodes:positions,depth,visits:root.n,inherited,solved:root.proof!==null,
      allSolved:root.children.every(c=>c.proof!==null),ms:performance.now()-start,
      timedOut:performance.now()-start>=limitMs});
  }
  if (!root.children) expand(root,past);
  report();
  while ((root.proof===null || (exploreAll && root.children.some(c=>c.proof===null))) &&
         performance.now()-start<limitMs) {
    iteration();
    if (session && performance.now()>=nextYield) {
      await new Promise(resolve=>setTimeout(resolve,0));
      if (session.id!==id) return;
      nextYield=performance.now()+20;
    }
    if (performance.now()>=nextReport) {report();nextReport=performance.now()+350;}
  }
  report();
}
