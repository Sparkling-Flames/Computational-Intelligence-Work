"use strict";
const game=createTablut(), $=id=>document.getElementById(id);
const pack=(a,b)=>a*81+b, point=s=>Math.floor(s/9)+","+s%9;
const notation=m=>"("+point(Math.floor(m/81))+") → ("+point(m%81)+")";
const nameOf=s=>s==="A"?"攻方":"守方";
const base=[pack(27,28),pack(22,20),pack(28,19)], gift=pack(31,32), take=pack(3,21);
const cases=[
  ["标准开局",[],0,"比较两条争夺 (2,1) 的路线。点击己方棋子可查看合法落点。"],
  ["开局 · 一手抵达",[pack(37,19),pack(22,20),take],0,"攻方可从 (4,1) 一手抵达 (2,1)。点击下一手，查看守方若照常出动外卫，攻方如何夹吃。"],
  ["救子 · 远撤与反夹",[...base,pack(20,24),pack(5,23),pack(31,22)],3,"守卫受到夹击威胁。此线先远撤到 (2,6)，随后借外卫反夹追兵。"],
  ["弃子 · 出王后被擒",[...base,gift,take,pack(40,22),pack(5,23)],3,"守方放弃 (2,2)。观察国王走到 (2,4) 后，攻方怎样借刚才吃子的棋形成横夹。"],
  ["弃子 · 贴城出王",[...base,gift,take,pack(40,31),pack(21,30)],3,"同样接受弃子，国王改停在 (3,4)。攻方能封住左侧逃线，交换后的价值仍待判断。"],
  ["拒吃 · 先封出口",[...base,gift,pack(37,28)],4,"攻方可以从 (4,1) 到 (3,1)，提前封路，同时保留从 (0,3) 夹吃外卫的机会。"]
];
const lossIndex=cases.length;
if (typeof lossReview!=="undefined") {
  const focus=lossReview.keys.find(k=>k.ply===65)||lossReview.keys[0];
  cases.push(["72 手败局 · 完整复盘",lossReview.moves,focus?focus.ply-1:0,"点击关键手可回到该手落子前，查看实战选择与三引擎记录。"]);
}
if (clockSample.example) {
  cases.push(["训练自弈 · 样本 "+clockSample.example.seed,clockSample.example.moves,0,
    "第一轮训练采集的完整棋谱。双方均为普通 Python PUCT，每手至多 "+clockSample.visits+
    " 次树访问，开局按访问量采样。右侧可以用浏览器引擎重新分析。"]);
}
const audits=clockReview.cases;
for (const c of (typeof refutationCases==="undefined"?[]:refutationCases)) {
  cases.push([c.label,c.moves,c.at,c.note,null,c.group]);
}
for (const c of (typeof nativeFieldCases==="undefined"?[]:nativeFieldCases)) {
  cases.push([c.label,c.moves,c.at,c.note,null,c.group]);
}
for (const c of (typeof openFieldCases==="undefined"?[]:openFieldCases)) {
  cases.push([c.label,c.moves,c.at,c.note,null,c.group]);
}
for (const c of (typeof attackSeriesCases==="undefined"?[]:attackSeriesCases)) {
  cases.push([c.label,c.moves,c.at,c.note,null,c.group]);
}
for (const g of (typeof attackTrials==="undefined"?[]:attackTrials)) {
  const end=g.winner==="="?"和棋":nameOf(g.winner)+"胜";
  const label=g.version==="supported"?"封锁与护子":"通道封锁";
  const focus=g.forced_replies?g.moves.length-3:0;
  const detail=g.forced_replies?"第 "+(focus+1)+" 手落子后，守方全部 "+g.forced_replies+" 种合法应对都允许攻方下一手擒王。":"";
  cases.push(["攻方迭代 · "+label+" · "+g.seed+" · "+end,g.moves,focus,
    "标准开局，攻方对 easyAI，双方各 60 秒。全局 "+g.moves.length+" 手，"+end+"。"+detail]);
}
for (const c of (typeof generation2Checks==="undefined"?[]:generation2Checks)) {
  cases.push([c.label,c.moves,c.cursor,c.note]);
}
for (const g of (typeof generation2Games==="undefined"?[]:generation2Games)) {
  const end=g.winner==="="?"和棋":nameOf(g.winner)+"胜";
  const note=g.loss?"第 "+g.loss.ply+" 手实战 "+notation(pack(...g.loss.played))+
    " 允许对方五手内强胜；"+notation(pack(...g.loss.alternative))+" 能避开这个深度的强败。":"";
  cases.push(["二代对 easyAI · "+g.seed+" · 二代执"+nameOf(g.side),g.moves,(g.loss?.ply??1)-1,
    "双方整局各 60 秒，"+g.moves.length+" 手，"+end+"。"+note]);
}
cases.push(["诱饵 · 吃子后擒王",[...trapReview.moves.slice(0,33),trapReview.take,trapReview.wins[0]],33,
  "攻方上一手送出一子。点「下一手」查看守方吃子，再点一次查看擒王。此处 53 种守法中有 52 种允许攻方下一手擒王。"]);
cases.push(["诱饵 · 攻方实战漏胜",trapReview.moves,33,
  "守方实战走 (4,5) → (4,6)，是唯一能避免下一手被擒的走法。攻方第 35 手漏掉强胜，守方第 46 手逃王。"]);
cases.push(["诱饵 · 最强应对后的续手",[...trapReview.moves.slice(0,34),...trapReview.follow],34,
  "攻方走 (3,8) → (3,7) 形成双威胁。守方全部 39 种合法回应都会在下一手丢王。点击下一手查看其中一条变化。"]);
const switches=audits.filter(c=>c.before.top[0].move.join()!==c.after.top[0].move.join());
const examples=new Set([...audits.filter(c=>!switches.includes(c)),...switches.filter(c=>c.policy==="conditional").slice(0,3),
  ...switches.filter(c=>c.policy==="baseline").slice(0,2),
  ...switches.filter(c=>c.was_loss5 || c.now_loss5).slice(0,3)]);
for (const c of examples) {
  cases.push(["加时复盘 · "+(c.policy==="conditional"?"新":"旧")+"时钟 · "+c.seed+" · 第 "+c.ply+" 手",[...c.prefix,pack(...c.after.top[0].move)],
    c.prefix.length,"返回第 "+c.ply+" 手落子前可查看两次搜索记录。",c]);
}
const workerURL=URL.createObjectURL(new Blob([createTablut.toString(),"\n",searchPosition.toString(),
  "\nconst session={}; onmessage=e=>{session.id=e.data.id; if (!e.data.stop) searchPosition(e.data,session);};"],{type:"text/javascript"}));
let job=0, inherited=0; const workers=new Map(), rates=new Map();
let states=[],cursor=0,selected=null,choice=null,rows=[],samples=[],worker=null,timer=null,started=0;
let clocks,auto=false,expired="",elapsed=0,lastDepth=0,nodes=0,visits=0,progress="",message="";
const match=()=>$("mode").value==="match", current=()=>states[cursor];
const automatic=()=>$("mode").value!=="study";
const onLoss=()=>+$("scenario").value===lossIndex;
const sampleRate=r=>r.n?100*r.wins/r.n:null;
const percent=v=>v==null?"—":v.toFixed(1)+"%";
function visitShare(n,total) {
  if (!n || !total) return "0%";
  const share=100*n/total;
  return share<0.01?"<0.01%":share.toFixed(2)+"%";
}
const proofText=r=>!r.proof?"—":r.value===100?"胜":r.value===0?"负":"和";
function onOriginalLine() {
  return onLoss() && states.slice(1,cursor+1).every((s,i)=>s.move===lossReview.moves[i]);
}
function storeAnalysis() {
  if (rows.length) current().snapshot={rows,samples,choice,lastDepth,nodes,visits,inherited,elapsed};
}
function after(states,move) {
  const prev=states[states.length-1], board=game.play(prev.board,move), side=game.other(prev.side);
  let result=game.winner(board);
  if (!result && (states.some(s=>s.board===board && s.side===side) || !game.moves(board,side).length)) result="=";
  return {board,side,result,move};
}
function halt(charge=true) {
  if (worker) {
    elapsed=performance.now()-started;
    if (charge && match()) {
      clocks[current().side]-=elapsed;
      if (clocks[current().side]<=0) expired=current().side;
    }
    if (elapsed>0 && visits>inherited) rates.set(worker,(visits-inherited)/elapsed);
    worker.postMessage({id:++job,stop:true}); worker=null;
  }
  clearInterval(timer); timer=null;
}
function clearAnalysis() {
  rows=[]; samples=[]; choice=null; selected=null; lastDepth=0; nodes=0; visits=0; inherited=0; elapsed=0; progress=""; message="";
}
function load() {
  halt(false); for (const w of workers.values()) w.terminate(); workers.clear(); rates.clear(); auto=false; expired=""; clocks={A:60000,D:60000};
  clearAnalysis();
  if (match()) $("scenario").value="0";
  const item=cases[+$("scenario").value];
  states=[{board:game.initial,side:"A",result:"",move:null}];
  for (const move of item[1]) {
    const prev=states[states.length-1];
    if (prev.result || !game.moves(prev.board,prev.side).includes(move)) throw Error("棋谱走法不合法 "+notation(move));
    states.push(after(states,move));
  }
  cursor=item[2]; render();
}
function advance(move) {
  if (expired || current().result || !game.moves(current().board,current().side).includes(move)) return;
  storeAnalysis();
  const r=rows.find(row=>row.move===move);
  states=states.slice(0,cursor+1);
  const nextState=after(states,move);
  if (r) nextState.analysis="预计得分 "+formatRate(r)+" / "+r.n+" 次访问 / 全部 "+visits+" 次 / "+(elapsed/1000).toFixed(2)+" 秒";
  states.push(nextState); cursor++; clearAnalysis(); render();
}
function jump(position) {
  halt(); auto=false; storeAnalysis();cursor=position;clearAnalysis();
  const cached=current().snapshot;
  if (cached) {
    ({rows,samples,choice,lastDepth,nodes,visits,inherited,elapsed}=cached);
    message="已保存的本手分析";
  }
  render();
}
function navigate(delta) { jump(cursor+delta); }
function squareClick(square) {
  if (auto || match() || current().result) return;
  const {board,side}=current(), move=selected===null ? null : pack(selected,square);
  if (move!==null && game.moves(board,side).includes(move)) { halt(); advance(move); return; }
  const alternatives=rows.slice(0,5).filter(r=>r.move%81===square);
  if (selected===null && alternatives.length) {
    const index=alternatives.findIndex(r=>r.move===choice);
    choice=alternatives[(index+1)%alternatives.length].move;
    drawBoard();drawAnalysis();return;
  }
  selected=game.owns(board[square],side) && selected!==square ? square : null;
  choice=null; drawBoard(); drawAnalysis();
}
function drawBoard() {
  const {board,move,side}=current(), legal=selected===null?[]:game.moves(board,side).filter(m=>Math.floor(m/81)===selected);
  const preview=choice??(selected===null?rows[0]?.move:null);
  const frag=document.createDocumentFragment();
  for (let i=0;i<81;i++) {
    const b=document.createElement("button"), y=Math.floor(i/9),x=i%9,p=board[i];
    b.className="cell"+((y+x)%2?" alt":"")+(x===0||x===8||y===0||y===8?" edge":"")+(i===40?" castle":"");
    if (move!=null && (Math.floor(move/81)===i || move%81===i)) b.classList.add("last");
    if (selected===i || preview!=null && Math.floor(preview/81)===i) b.classList.add("from");
    if (preview!=null && preview%81===i) b.classList.add("to");
    if (legal.includes(pack(selected,i))) b.classList.add("legal");
    const title={A:"攻子",D:"守卫",K:"国王",X:"空城堡",".":"空格"}[p];
    b.setAttribute("aria-label",point(i)+" "+title); b.title=point(i)+" "+title;
    if ("ADK".includes(p)) {
      const disk=document.createElement("span");disk.className="piece "+p;
      disk.textContent=p==="K"?"王":""; b.append(disk);
    } else if (p==="X") b.textContent="◇";
    const labels=rows.slice(0,5).map((r,idx)=>({r,rank:idx+1})).filter(({r})=>
      r.move%81===i && (selected===null || Math.floor(r.move/81)===selected));
    if (labels.length) {
      const active=labels.find(({r})=>r.move===choice)||labels[0];
      const wrap=document.createElement("span");wrap.className="badges";
      const badge=document.createElement("span");badge.className="badge"+(active.rank===1?" lead":"");
      const rank=document.createElement("b");rank.textContent="#"+active.rank+(labels.length>1?" +"+(labels.length-1):"");
      badge.append(rank,percent(sampleRate(active.r)));wrap.append(badge);b.append(wrap);
      b.title=labels.map(({r,rank})=>"#"+rank+" "+notation(r.move)+" "+percent(sampleRate(r))).join("\n");
      b.setAttribute("aria-label",b.title);
    }
    b.onclick=()=>squareClick(i); frag.append(b);
  }
  $("board").replaceChildren(frag);
}
const formatRate=r=>r.value==null?"待采样":r.value.toFixed(1)+"%"+(r.proof?" ✓":"");
function clockText() {
  $("clocks").innerHTML=match()?["A","D"].map(s=>{
    const spent=worker && s===current().side?performance.now()-started:0;
    return '<span class="clock">'+nameOf(s)+" "+(Math.max(0,clocks[s]-spent)/1000).toFixed(1)+" s</span>";
  }).join(""):"";
}
function updateStatus() {
  clockText();
  const seconds=(worker?performance.now()-started:elapsed)/1000;
  $("status").textContent=message || (worker?"搜索中 · ":"")+(progress || (rows.length?"已停止":"等待分析"));
  $("metrics").textContent="用时 "+seconds.toFixed(1)+(match()?"":" / 60")+" s　·　"+(visits-inherited).toLocaleString()+" 次新增 / "+inherited.toLocaleString()+" 次继承　·　本手最深 "+lastDepth+" 手";
}
function drawAnalysis() {
  const shown=choice==null?rows[0]:rows.find(r=>r.move===choice);
  const displayed=$("showAll").checked?rows:rows.slice(0,5);
  $("rows").replaceChildren(...displayed.map((r,i)=>{
    const tr=document.createElement("tr");
    if (shown && r.move===shown.move) tr.className="selected";
    const td=tr.insertCell(),button=document.createElement("button");
    button.textContent=(i+1)+"　"+notation(r.move);
    button.onclick=()=>{choice=r.move;selected=null;drawAnalysis();drawBoard();};
    td.append(button); tr.insertCell().textContent=percent(sampleRate(r));
    tr.insertCell().textContent=r.n.toLocaleString()+" · "+visitShare(r.n,visits);
    tr.insertCell().textContent=r.rate==null?"—":r.rate.toLocaleString();
    tr.insertCell().textContent=proofText(r);return tr;
  }));
  $("choice").textContent=shown?notation(shown.move):"";
  $("replyCoverage").textContent=shown?.replyCount!=null?
    "已访问或已判定 "+shown.checkedReplies+" / "+shown.replyCount+" 种合法应对，列出前三。":
    shown?.proof?"当前候选结果已证。":"展开对手层后显示。";
  $("replies").replaceChildren(...(shown?.replies||[]).map(r=>{
    const tr=document.createElement("tr");
    tr.insertCell().textContent=notation(r.move);
    tr.insertCell().textContent=percent(sampleRate(r))+(r.proof==null?"":" · 已证"+(r.proof===0?"胜":r.proof===1?"负":"和"));
    tr.insertCell().textContent=r.n.toLocaleString();
    tr.insertCell().textContent=r.next==null?"—":notation(r.next);
    return tr;
  }));
  $("line").textContent=shown?"树中主要变化　"+shown.line.map(notation).join("　/　"):"开始分析后可查看候选及主要变化。";
  if (shown) {
    const before=game.features(current().board), after=game.features(game.play(current().board,shown.move));
    const score=shown.n?100*(shown.wins+0.5*shown.draws)/shown.n:null;
    $("evidence").textContent="样本 "+shown.wins+" 胜 / "+shown.draws+" 和 / "+(shown.n-shown.wins-shown.draws)+" 负，得分率 "+percent(score)+"。策略先验 "+percent(100*shown.prior)+"，访问占比 "+percent(visits?100*shown.n/visits:null)+"。走后国王直达方向 "+before.lanes+" → "+after.lanes+"，攻子 "+before.attackers+" → "+after.attackers+"，守卫 "+before.defenders+" → "+after.defenders+"。";
  } else $("evidence").textContent="选取候选可查看胜和负、棋盘变化和计算分配。";
  const canvas=$("trend"), w=canvas.width=Math.max(250,canvas.clientWidth*2), h=canvas.height=138;
  const ctx=canvas.getContext("2d");ctx.clearRect(0,0,w,h);ctx.strokeStyle="#c7c2d7";
  ctx.beginPath();ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();
  const pts=shown?samples.map(s=>[s.ms,s.values.get(shown.move)]).filter(p=>p[1]!=null):[];
  ctx.strokeStyle="#6354b0";ctx.fillStyle="#6354b0";ctx.lineWidth=3;
  const points=pts.map(([t,v])=>[8+t/Math.max(1,pts[pts.length-1][0])*(w-16),8+(100-v)/100*(h-16)]);
  ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();
  for (const [x,y] of points) {ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();}
  $("trendLabel").textContent=pts.length?"样本胜率 · "+pts.slice(-3).map(([t,v])=>(t/1000).toFixed(2)+"s / "+v.toFixed(1)+"%").join("　"):"横轴为用时，纵轴为当前方样本胜率（0–100%）";
  $("apply").disabled=automatic() || !shown || !!current().result;
}
function drawReplay() {
  const survivors=clockReview.lengths.filter(n=>n>cursor);
  const left=survivors.reduce((sum,n)=>sum+Math.ceil((n-cursor)/2),0);
  $("lengthEstimate").textContent=current().result?"":(survivors.length?
    "校准自弈中 "+survivors.length+" / "+clockReview.lengths.length+" 局走到本手；含本手在内，行棋方平均还走 "+(left/survivors.length).toFixed(1)+" 手。":
    "样本均已在此手之前结束，余手估计使用保守预留。");
  if (!current().result && clockSample.selfplay) {
    const subset=clockSample.selfplay.filter(n=>n>cursor);
    const mean=subset.reduce((s,n)=>s+Math.ceil((n-cursor)/2),0)/subset.length;
    $("lengthEstimate").textContent+=" 离线训练自弈另计："+subset.length+" / "+clockSample.selfplay.length+
      " 局走到本手"+(subset.length?"，行棋方平均还走 "+mean.toFixed(1)+" 手。":"。");
  }
  const slider=$("scrubber");
  slider.max=states.length-1;slider.value=cursor;
  slider.disabled=match()||auto||states.length<2;
  $("position").textContent=cursor+" / "+(states.length-1);
  $("keys").replaceChildren();
  const audit=cases[+$("scenario").value][4];
  if (audit && cursor===audit.prefix.length && audit.prefix.every((m,i)=>states[i+1].move===m)) {
    const describe=s=>s.top.map(r=>notation(pack(...r.move))+" "+formatAuditScore(r.score)+"（"+r.visits+" 访）").join("，");
    const outcome=loss=>loss?"对手五手内可强胜":"未发现对手五手内强胜";
    $("caseText").textContent="基础预算 "+audit.base.toFixed(2)+" 秒时，"+describe(audit.before)+
      "。实耗 "+audit.seconds.toFixed(2)+" 秒后，"+describe(audit.after)+"。加时前选着"+outcome(audit.was_loss5)+
      "，加时后选着"+outcome(audit.now_loss5)+"。百分比为 Python 静态估值回传的预计得分。";
    if (audit.alternatives) $("caseText").textContent+=" 全部 "+audit.alternatives+" 种走法中，"+
      audit.escapes.length+" 种可避开五手强败。";
    if (!auto) for (const move of new Set([pack(...audit.before.top[0].move),pack(...audit.after.top[0].move)])) {
      const btn=document.createElement("button");btn.textContent="试走 "+notation(move);
      btn.onclick=()=>{halt();advance(move);};$("keys").append(btn);
    }
  }
  const isOriginal=onOriginalLine();
  if (onLoss()) for (const key of lossReview.keys) {
    const btn=document.createElement("button");
    btn.textContent="第 "+key.ply+" 手";btn.title=key.text;btn.disabled=auto;
    btn.onclick=()=>{
      const prefix=states.slice(1,key.ply);
      if (prefix.length!==key.ply-1 || !prefix.every((s,i)=>s.move===lossReview.moves[i])) load();
      jump(key.ply-1);
    };
    $("keys").append(btn);
  }
  const entry=isOriginal && typeof lossComparison!=="undefined"?lossComparison[cursor+1]:null;
  $("comparison").hidden=!entry;
  $("compareRows").replaceChildren();
  if (entry) for (const e of entry) {
    const tr=document.createElement("tr");
    tr.insertCell().textContent=e.name+" · "+notation(e.move)+(e.losesWithinSeven==null?"":
      e.losesWithinSeven?" · 守方七手内可强胜":" · 避开七手强败");
    tr.insertCell().textContent=e.seconds.toFixed(2)+" s";
    tr.insertCell().textContent=e.nodes.toLocaleString()+" / "+(e.visits==null?"—":e.visits.toLocaleString());
    tr.insertCell().textContent=e.depth;
    $("compareRows").append(tr);
  }
  if (isOriginal) {
    const key=lossReview.keys.find(k=>k.ply===cursor+1),next=lossReview.moves[cursor];
    const clock=lossReview.clock?.[cursor];
    const timing=clock?"实战时钟："+nameOf(current().side)+"剩余 "+clock.before.toFixed(2)+" 秒，本手使用 "+clock.spent.toFixed(2)+" 秒。":"";
    $("caseText").textContent=timing+(key?.text||(next!=null?"实战下一手 "+notation(next)+"。":"棋谱结束。"));
    const control=clockReview.control;
    if (control && cursor+1===control.ply) {
      const detail=(s,loss)=>s.visits.toLocaleString()+" 访选 "+notation(pack(...s.top[0].move))+
        (loss?"，守方七手内可强胜":"，避开守方七手内强胜");
      $("caseText").textContent+=" 同树定访问复查："+detail(control.before,control.was_loss7)+
        "；"+detail(control.after,control.now_loss7)+"。";
    }
    if (key?.alternative!=null && !auto) {
      const btn=document.createElement("button");
      btn.textContent="试走防线 "+notation(key.alternative);
      btn.onclick=()=>{halt();advance(key.alternative);};
      $("keys").append(btn);
    }
  }
  if (onLoss() && states.length<lossReview.moves.length+1 && !auto) {
    const btn=document.createElement("button");
    btn.textContent="返回原棋谱";
    btn.onclick=()=>{
      const firstDifferent=states.slice(1).findIndex((s,i)=>s.move!==lossReview.moves[i]);
      const to=firstDifferent<0?cursor:firstDifferent;
      load();jump(to);
    };
    $("keys").append(btn);
  }
}
function render() {
  $("wideRoot").disabled=!!worker || automatic();
  const s=current(), ended=expired||s.result;
  $("turn").textContent=expired?nameOf(expired)+"超时 · "+nameOf(game.other(expired))+"胜":
    s.result==="="?"和棋":s.result?nameOf(s.result)+"胜":"第 "+(cursor+1)+" 手 · "+nameOf(s.side)+"行棋";
  $("perspective").textContent=nameOf(s.side)+"视角";
  $("hint").textContent=match()?"自动对弈按双方独立时钟扣时，可暂停。":"点击棋子再点落点可试走。落点标有 + 时，点击可切换不同起点的候选。";
  const item=cases[+$("scenario").value];
  $("caseTitle").textContent=item[0]+(cursor?"　·　上手 "+notation(s.move):"");
  $("caseText").textContent=item[3];
  $("record").replaceChildren(...states.slice(1).map((s,i)=>{const entry=document.createElement("div");entry.textContent=(i+1)+". "+notation(s.move)+(s.analysis?"　"+s.analysis:"");return entry;}));if (states.length===1) $("record").textContent="初始局面";
  $("scenario").disabled=match(); $("back").disabled=match()||auto||cursor===0;
  $("next").disabled=match()||auto||cursor===states.length-1;
  $("run").textContent=automatic()?"自动对弈":"分析本手 · 60 秒"; $("run").disabled=!!worker||!!ended;
  $("stop").disabled=!worker && !auto;
  drawReplay(); drawBoard(); drawAnalysis(); updateStatus();
}
function formatAuditScore(score) {return score==null?"—":(100*score).toFixed(1)+"%";}
function budget() {
  const s=current(), k=s.board.indexOf("K"), seen=clockReview.lengths.filter(n=>n>cursor);
  const prior=Math.max(9,30-Math.floor((Math.floor(cursor/2)+1)/2));
  const remaining=(2*prior+seen.reduce((sum,n)=>sum+Math.ceil((n-cursor)/2),0))/(2+seen.length);
  let contested=false;
  if (k>=0 && ![31,39,40,41,49].includes(k)) {
    for (const [dy,dx] of [[0,1],[1,0],[0,-1],[-1,0]]) {
      let blocks=0, guard=false;
      for (let y=Math.floor(k/9)+dy,x=k%9+dx;y>=0&&y<9&&x>=0&&x<9;y+=dy,x+=dx) {
        const p=s.board[y*9+x];
        if (p!=="." && p!=="X") blocks++;
        if (p==="D") guard=true;
      }
      if (guard && blocks<=2) contested=true;
    }
  }
  const middle=cursor>=14 && remaining>=5;
  const factor=contested?1.85:k===40 && cursor<14?0.70:middle?1.45:1;
  const usable=Math.max(0,clocks[s.side]-600);
  return {limit:Math.max(1,Math.min(usable*0.25,usable*factor/remaining)),discount:middle?0.20:0.50};
}
function finishTurn() {
  const move=rows[0]?.move ?? game.moves(current().board,current().side)[0];
  halt();
  if (expired) {auto=false;render();return;}
  advance(move);
  if (current().result) auto=false;
  if (auto) startSearch(); else render();
}
function contenders(rows) {
  return rows.filter(r=>!r.proof).slice(0,3).filter(r=>r.n>=20);
}
function extraFraction(earlier,later) {
  if (!earlier?.length || later.length<2) return 0;
  const lead=later[0];
  if (!later.slice(1).some(r=>Math.abs(r.value-lead.value)<=5)) return 0;
  const moving=earlier[0].move!==lead.move || later.some(r=>
    earlier.some(prev=>prev.move===r.move && Math.abs(prev.value-r.value)>=2));
  return moving?0.45:0.15;
}
function startSearch() {
  if (worker || expired || current().result) return;
  clearAnalysis(); const s=current(), {limit,discount}=budget(); auto=automatic();started=performance.now();
  function finishAnalysis(allSolved) {
    if (automatic()) finishTurn();
    else {halt();message=allSolved?"全部候选已证":"本手 60 秒分析完成";render();}
  }
  const pool=automatic()?s.side:"study";
  let earlier=null, extension=0, checked=false;
  if (!workers.has(pool)) workers.set(pool,new Worker(workerURL));
  worker=workers.get(pool); const id=++job, priorRate=rates.get(worker);
  const active=worker;
  worker.onmessage=e=>{
    if (worker!==active) return;
    const data=e.data; if(data.id!==id) return; inherited=data.inherited; nodes=data.nodes;visits=data.visits;progress="PUCT 搜索 · "+nodes.toLocaleString()+" 个树节点";
    if (data.rows) {
      const previous=new Map(rows.map(r=>[r.move,r.n])), previousMs=samples.at(-1)?.ms;
      rows=data.rows;lastDepth=data.depth;
      if (extension) progress+=" · 候选接近，加时复核";
      for (const r of rows) r.rate=previous.has(r.move) && data.ms>previousMs?
        Math.round(1000*(r.n-previous.get(r.move))/(data.ms-previousMs)):null;
      samples.push({ms:data.ms,values:new Map(rows.map(r=>[r.move,sampleRate(r)]))});
      if (samples.length>240) samples=samples.filter((_,i)=>i%2===0 || i===samples.length-1);
      drawAnalysis(); drawBoard(); updateStatus();
      if ((match() && data.solved) || data.allSolved || data.timedOut) finishAnalysis(data.allSolved);
    }
  };
  worker.onerror=e=>{if (worker!==active) return;halt();auto=false;message="分析中止 · "+e.message;render();};
  worker.postMessage({id,board:s.board,side:s.side,history:states.slice(0,cursor+1).map(s=>s.board+s.side),exploreAll:!match(),wideRoot:!automatic() && $("wideRoot").checked,limitMs:match()?Infinity:60000});
  timer=setInterval(()=>{
    const credit=priorRate ? Math.min(limit*discount,inherited/priorRate) : 0;
    const base=limit-credit, spent=performance.now()-started;
    if (match() && rows.length && !checked && spent>=0.45*base) {
      if (!earlier) earlier={visits,rows:contenders(rows)};
      else if (spent>=0.80*base && visits>earlier.visits) {
        extension=extraFraction(earlier.rows,contenders(rows)); checked=true;
        if (extension && (clocks[s.side]-600)*0.25>base) progress+=" · 候选接近，加时复核";
        else extension=0;
      }
    }
    const deadline=Math.max(1,Math.min((clocks[s.side]-600)*0.25,base*(1+extension)));
    if (match() && performance.now()-started>=deadline) finishTurn();
    else if (!match() && performance.now()-started>=60000) finishAnalysis(false);
    else updateStatus();
  },match()?25:150);
  render();
}
const seriesGroups=new Map();
for (const [i,item] of cases.entries()) {
  const option=new Option(item[0],i);
  const groupName=item[5];
  if (!groupName) {
    $("scenario").add(option);
    continue;
  }
  if (!seriesGroups.has(groupName)) {
    const group=document.createElement("optgroup");
    group.label=groupName;
    $("scenario").append(group);
    seriesGroups.set(groupName,group);
  }
  seriesGroups.get(groupName).append(option);
}
if (typeof lossReview!=="undefined") $("scenario").value=String(lossIndex);
for (const key of [".xticks",".yticks"]) document.querySelector(key).innerHTML=Array.from({length:9},(_,i)=>"<span>"+i+"</span>").join("");
$("scenario").onchange=load; $("mode").onchange=load; $("reset").onclick=load;
$("back").onclick=()=>navigate(-1);$("next").onclick=()=>navigate(1);
$("scrubber").oninput=e=>jump(Number(e.target.value));
$("showAll").onchange=drawAnalysis;
$("run").onclick=startSearch;
$("stop").onclick=()=>{halt();auto=false;message=match()?"对弈已暂停":"分析已停止";render();};
$("apply").onclick=()=>{const move=choice??rows[0]?.move;if (move!=null) {halt();advance(move);}};
load();


