/* SHAMAN: Elemental (lava crags under chain lightning), Enhancement (windfury gale on a ridge), Restoration (night waterfall pool). */
/* ================================== ELEMENTAL: lava crags under chain lightning ================================== */
(()=>{
  const self={cls:'SHAMAN',tree:1,id:'shaman_elemental',name:'ELEMENTAL'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0418','#14061c','#1a0418','#2a0824','#40102c']);
  const LAVA=c.ramp(['#1a0418','#40101e','#6e1820','#a8281e','#e0561e','#ff7a2a','#ffb04a','#ffe08a']);
  const CYR=c.ramp(['#0a3a5a','#1480a8','#22e0ff','#9af4ff','#f0ffff']);
  const ROCK=c('#07030e'),FAR=c('#12082a'),FARRIM=c('#3a1030'),CLV=c('#2a1850'),CLW=c('#1a6a8a');
  const SPR=c('#05020c'),SPRIM=c('#2a1850'),SPRIM2=['#1480a8','#22e0ff'].map(c);
  const EMBC=['#ffb04a','#ff7a2a','#a8281e','#40101e'].map(c);
  const HOR=150;
  const FARR=[];for(let x=0;x<W;x++)FARR.push(HOR-fl(10*vn(x,17,3)+5*vn(x+90,6,4)+(h2(x,1,2)>.96?2:0)));
  const NEAR=[];for(let x=0;x<W;x++){const s=fl(vn(x,21,5)*14+vn(x+40,7,6)*7);NEAR.push(188-s+(((x>>2)&1)&&h2(x,2,3)>.7?1:0))}
  const TOT=[{x:26,b:190,h:78,w:7},{x:78,b:180,h:100,w:9},{x:130,b:188,h:70,w:7}];
  const mask=new Uint8Array(W*H); // 1 = open sky, 2 = lit ground (far crags), 0 = silhouette
  const CRK=[];{const r=rng(91);
    for(let i=0;i<14;i++){let x=6+r()*144,y=NEAR[fl(x)]+3+r()*10;const pts=[],n=10+fl(r()*18);
      for(let k=0;k<n&&y<H-1;k++){pts.push([fl(x),fl(y)]);x+=(r()-.5)*3.2;y+=r()<.7?1:0}
      CRK.push({pts,ph:r(),k:1+fl(r()*2)})}}
  const EMB=emberList(7,54,0,150,70,120,.5,.9).map(e=>({...e,D:-e.D}));
  const RISE=emberList(9,18,150,236,30,70,.4,.7);
  function line(pts,x0,y0,x1,y1){let dx=Math.abs(x1-x0),dy=Math.abs(y1-y0),sx=x0<x1?1:-1,sy=y0<y1?1:-1,e=dx-dy;
    for(;;){pts.push([x0,y0]);if(x0===x1&&y0===y1)break;const e2=2*e;if(e2>-dy){e-=dy;x0+=sx}if(e2<dx){e+=dx;y0+=sy}}}
  function zig(r,x0,y0,x1,y1,jit,depth){
    if(depth===0||(Math.abs(x1-x0)<2&&Math.abs(y1-y0)<3))return[[x0,y0],[x1,y1]];
    const mx=(x0+x1)/2+(r()-.5)*jit,my=(y0+y1)/2+(r()-.5)*jit*.5;
    const a=zig(r,x0,y0,mx,my,jit*.55,depth-1),b=zig(r,mx,my,x1,y1,jit*.55,depth-1);return a.concat(b)}
  function mkHop(seed,x0,y0,x1,y1,nf){const r=rng(seed),cp=zig(r,x0,y0,x1,y1,Math.max(10,Math.hypot(x1-x0,y1-y0)*.35),4),pts=[];
    for(let i=1;i<cp.length;i++)line(pts,Math.round(cp[i-1][0]),Math.round(cp[i-1][1]),Math.round(cp[i][0]),Math.round(cp[i][1]));
    const forks=[];for(let q=0;q<nf;q++){const s=pts[fl((.2+.6*r())*pts.length)];const ex=s[0]+(r()-.5)*40,ey=s[1]+8+r()*18,fk=[],cp2=zig(r,s[0],s[1],ex,ey,8,2);
      for(let i=1;i<cp2.length;i++)line(fk,Math.round(cp2[i-1][0]),Math.round(cp2[i-1][1]),Math.round(cp2[i][0]),Math.round(cp2[i][1]));forks.push(fk)}
    return{pts,forks}}
  const tip=i=>[TOT[i].x,TOT[i].b-TOT[i].h-3];
  const CHAIN=[mkHop(3,10,0,...tip(0),1),mkHop(5,...tip(0),...tip(1),2),mkHop(8,...tip(1),...tip(2),1),mkHop(12,...tip(2),146,176,2)];
  const CHAIN2=[mkHop(31,96,0,...tip(1),2),mkHop(34,...tip(1),...tip(0),1),mkHop(37,...tip(0),30,176,1)];
  const sil=(p,x,y,col)=>{p.put(x,y,col);if(x>=0&&x<W&&y>=0&&y<H)mask[fl(y)*W+fl(x)]=0};
  function totem(p,t){const cx=t.x,top=t.b-t.h,w=t.w;
    for(let y=top;y<=t.b;y++){const u=(y-top)/t.h,hw=Math.round(w*(.6+.55*u)),k=(y-top)%12,groove=k<2&&y>top+14,step=(y-top)%24<2?1:0;
      for(let x=cx-hw-step;x<=cx+hw+step;x++){let col=SPR;
        if(x===cx-hw-step&&!groove)col=SPRIM;
        if(groove&&Math.abs(x-cx)<hw-1&&((x+y)&1))col=SPRIM;
        if(x===cx&&y>top+16&&k>3&&u<.9)col=SPRIM;
        sil(p,x,y,col)}}
    // carved face block with brow and beak under the cap
    for(let k=0;k<4;k++)for(let x=cx-2+k;x<=cx+2-k;x++)sil(p,x,top+10+k,SPRIM);
    for(let k=0;k<7;k++){sil(p,cx-w-1-(k>>1),top-k+1,SPR);sil(p,cx+w+1+(k>>1),top-k+1,SPR);sil(p,cx-w-2-(k>>1),top-k+1,SPR);sil(p,cx+w+2+(k>>1),top-k+1,SPR)}
    for(let y=top-9;y<top;y++){sil(p,cx,y,SPR);if(y>top-6){sil(p,cx-1,y,SPR);sil(p,cx+1,y,SPR)}}
    for(let dx=-w-4;dx<=w+4;dx++)for(let k=0;k<3;k++)sil(p,cx+dx,t.b-k+1,SPR)}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<FARR[x]){const g=Math.pow(y/HOR,1.5);p.put(x,y,ramp(SKY,g*.9,x,y));mask[y*W+x]=1}
      else{p.put(x,y,ramp(SKY,.1+.1*tnoise(x/9,y/5,64,64,2),x,y)),mask[y*W+x]=2;
        if(y===FARR[x])p.put(x,y,FARRIM);else if(y<FARR[x]+3&&dith(x,y,.4))p.put(x,y,FAR);else if(y>FARR[x]+3)p.put(x,y,FAR);}}
    for(let x=0;x<W;x++)for(let y=NEAR[x];y<H;y++)sil(p,x,y,ROCK);
    // crack-free rim light on the near crags
    for(let x=0;x<W;x++)p.put(x,NEAR[x],FARRIM);
    for(const t of TOT)totem(p,t);
    self.base=p;
  }
  function boltDraw(p,b,fa){
    for(const[x,y]of b.pts){p.dput(x-1,y,CYR[1],.55);p.dput(x+1,y,CYR[1],.55);if(fa>1)p.dput(x,y,CYR[3],.5);p.put(x,y,fa>1?CYR[4]:CYR[3])}
    for(const fk of b.forks)for(const[x,y]of fk){p.dput(x-1,y,CYR[0],.5);p.put(x,y,CYR[2])}}
  function draw(p,f,N){
    const t=f/N,a=TAU*t;
    // hops: event 1 at frame 4, event 2 at frame 16; each hop lasts 3 frames and the next starts 1 frame later
    const act=[];let flash=0;
    [[0,CHAIN],[12,CHAIN2]].forEach(([f0,ch])=>ch.forEach((b,i)=>{const s=(f-f0-i+N)%N;if(s<4){act.push([b,s===1||s===2?2:1]);flash=Math.max(flash,s===0?.6:s===1?.9:s===2?.6:.3)}}));
    for(let y=0;y<HOR;y++){const gy=y/HOR;
      for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
        const n=.55*tnoise(x/38+.5*Math.cos(a),y/14+.5*Math.sin(a),64,64,4)+.45*tnoise((x+39*t)/13,y/6,3,64,5)-.42;
        if(n>0)p.tint(x,y,mixc(CLV,CLW,clamp(flash*1.4*n*2+gy*.2)),n*2.2,.6)}}
    // magma glow cast up from the far ridge
    for(let y=HOR-40;y<HOR+10;y++)for(let x=0;x<W;x++){const m=mask[y*W+x],hb=.7+.3*Math.sin(a+x*.05);
      const d=(y-(FARR[x]-30))/40;if(d<0)continue;
      if(m===1)p.tint(x,y,LAVA[3],d*d*.5*hb,.45)}
    // lava crack networks, each pulsing on its own phase: bright when fresh, cooling to dull red
    for(const k of CRK){const v=.5+.5*Math.sin(TAU*(k.k*t+k.ph)),h=v*v;
      k.pts.forEach(([x,y],i)=>{const hot=clamp(.12+.8*h*(1-.4*(i/k.pts.length)));
        p.put(x,y,ramp(LAVA,hot*.85,x,y,2));if(h>.5&&i%3===0)p.dput(x,y-1,LAVA[2],h*.5)})}
    // a slow magma river across the foot of the crags
    for(let y=218;y<H;y++)for(let x=0;x<W;x++){const m=mask[y*W+x];
      const edge=220+5*Math.sin(x*.07+1)+3*Math.sin(x*.19);if(y<edge)continue;
      const d=tnoise((x+153*t)/9,y/4,17,64,6)*.6+tnoise((x-155*t)/5,y/3,31,64,7)*.4;
      p.put(x,y,ramp(LAVA,clamp(.05+.38*d*d*2.2-.08*(y-edge)/20),x,y,2))}
    for(const t of TOT){const top=t.b-t.h,ph=.5+.5*Math.sin(a*2+t.x);
      for(const s of[-1,1]){p.put(t.x+s*2,top+8,CYR[ph>.7?3:2]);p.put(t.x+s*3,top+7,CYR[ph>.7?3:2]);p.put(t.x+s*(t.w+3),top-3,ph>.5?SPRIM2[1]:SPRIM2[0])}p.put(t.x,top-9,CYR[1])}
    for(const[b,fa]of act)boltDraw(p,b,fa);
    if(flash>0)for(const[b]of act)for(const[x,y]of b.pts)if((x+y)%3===0)for(let dy=-3;dy<=3;dy+=2)for(let dx=-3;dx<=3;dx+=2){const xx=x+dx,yy=y+dy;
      if(xx<0||xx>=W||yy<0||yy>=H||mask[yy*W+xx]===0)continue;p.tint(xx,yy,CYR[1],.12*flash,.4)}
    emberDraw(p,EMB,t,8,EMBC);emberDraw(p,RISE,t,-4,[EMBC[0],EMBC[1],EMBC[1]]);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== ENHANCEMENT: windfury gale on a ridge ================================== */
(()=>{
  const self={cls:'SHAMAN',tree:2,id:'shaman_enhancement',name:'ENHANCEMENT'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0430','#12083a','#1a0c4a','#2a1060','#4a1466','#7a1a72','#a82284']);
  const ICE=c.ramp(['#1a2c6a','#2e508c','#5a8cc8','#9ad0ff','#d8f0ff']);
  const PINK=['#ff2e97','#a82284','#7a1a72'].map(c);
  const ROCK=c('#07030e'),FARC=c('#12083a'),RIM=c('#3a2068'),CLV=c('#2a1850'),CLW=c('#7a1a72'),GRV=c('#1c1038'),CARV=c('#0a0418');
  const SPK=['#ffffff','#d8f0ff','#ffe9c0','#ff9a5a'].map(c);
  const RAINC=['#2e508c','#5a8cc8'].map(c);
  const CX=78,TOP=80,BASE=208,SLOPE=W/H;
  const RING=[{y:108,rx:19,ry:5,k:1,ph:0},{y:138,rx:30,ry:8,k:-1,ph:.3},{y:168,rx:42,ry:11,k:1,ph:.6},{y:196,rx:30,ry:8,k:-1,ph:.1}];
  const FR=[],RID=[];for(let x=0;x<W;x++){FR.push(168-fl(6*vn(x,23,5)+3*vn(x+70,7,6)));
    RID.push(204-fl(4*vn(x,19,2)+2*vn(x+50,6,3)+(Math.abs(x-CX)<24?7*Math.pow(1-Math.abs(x-CX)/24,1.4):0)))}
  const mask=new Uint8Array(W*H); // 1 sky, 2 far ridge, 3 near ground, 0 totem silhouette
  const T=new Uint8Array(W*H);
  const tset=(x,y)=>{x=fl(x);y=fl(y);if(x>=0&&x<W&&y>=0&&y<H)T[y*W+x]=1};
  const inT=(x,y)=>x>=0&&x<W&&y>=0&&y<H&&T[y*W+x]===1;
  const TUFT=[];{const r=rng(6);for(let i=0;i<70;i++){const x=1+fl(r()*154);TUFT.push({x,y:RID[x]+1,h:3+fl(r()*4),ph:r()})}}
  const RAIN=[];{const r=rng(12);for(let i=0;i<64;i++)RAIN.push({x:r()*W,y:r()*H,L:4+fl(r()*3),far:r()>.4})}
  const SPARKS=[];{const r=rng(40);for(let i=0;i<14;i++){const rr=RING[fl(r()*4)],ang=Math.PI*(.05+.9*r());SPARKS.push({ph:r(),x:CX-Math.cos(ang)*rr.rx,y:rr.y+Math.sin(ang)*rr.ry,vx:-(8+r()*16),vy:6+r()*10,col:fl(r()*3.99)})}}
  function line(pts,x0,y0,x1,y1){let dx=Math.abs(x1-x0),dy=Math.abs(y1-y0),sx=x0<x1?1:-1,sy=y0<y1?1:-1,e=dx-dy;
    for(;;){pts.push([x0,y0]);if(x0===x1&&y0===y1)break;const e2=2*e;if(e2>-dy){e-=dy;x0+=sx}if(e2<dx){e+=dx;y0+=sy}}}
  function zig(r,x0,y0,x1,y1,jit,d){if(d===0||(Math.abs(x1-x0)<2&&Math.abs(y1-y0)<2))return[[x0,y0],[x1,y1]];
    const mx=(x0+x1)/2+(r()-.5)*jit,my=(y0+y1)/2+(r()-.5)*jit,a=zig(r,x0,y0,mx,my,jit*.55,d-1),b=zig(r,mx,my,x1,y1,jit*.55,d-1);return a.concat(b)}
  const ARC=(()=>{const r=rng(77),pts=[],a=[[CX-34,TOP-1],[CX-10,TOP-14],[CX+10,TOP-17],[CX+34,TOP-1]];
    for(let i=1;i<a.length;i++){const cp=zig(r,a[i-1][0],a[i-1][1],a[i][0],a[i][1],8,3);for(let j=1;j<cp.length;j++)line(pts,Math.round(cp[j-1][0]),Math.round(cp[j-1][1]),Math.round(cp[j][0]),Math.round(cp[j][1]))}return pts})();
  // wolf, facing right in a 30 x 16 box (grid row = y + 2): chunky body, deep chest, ears and snout, bushy tail, 2 px legs
  const POSE=[[[19,8,23,10,27,13],[17,8,21,10,24,13],[8,7,4,10,0,13],[10,8,7,10,4,13]],
    [[19,8,18,11,19,13],[17,8,15,11,15,13],[8,7,11,10,9,13],[10,8,13,10,12,13]],
    [[19,8,22,10,23,12],[17,8,19,11,18,13],[8,7,6,10,5,13],[10,8,10,11,9,13]]];
  const LIFT=[1,0,1];
  const WG=POSE.map(legs=>{const g=new Uint8Array(30*16),s=(x,y)=>{if(x>=0&&x<30&&y>=-2&&y<14)g[(y+2)*30+x]=1};
    for(let x=6;x<=22;x++){const t0=x<9?4:3,b0=8+(x>16?1:0)-(x<8?1:0);for(let y=t0;y<=b0;y++)s(x,y)}
    for(let x=21;x<=24;x++)for(let y=1;y<=7;y++)s(x,y);
    for(let x=23;x<=27;x++)for(let y=1;y<=5;y++)s(x,y);
    for(let x=27;x<=29;x++)for(let y=3;y<=4;y++)s(x,y);
    s(23,-1);s(23,0);s(24,0);s(25,-1);s(25,0);s(26,0);
    [[5,2,4],[4,1,4],[3,1,3],[2,0,2],[1,0,2],[0,0,1]].forEach(([x,y0,y1])=>{for(let y=y0;y<=y1;y++)s(x,y)});
    for(const L of legs){const pts=[];line(pts,L[0],L[1],L[2],L[3]);line(pts,L[2],L[3],L[4],L[5]);for(const[x,y]of pts){s(x,y);s(x+1,y)}}
    return g});
  function wolf(p,wx,fy,s,pose,t,ph){
    const g=WG[pose],ww=Math.ceil(30*s),hh=Math.ceil(16*s),at=(dx,dy)=>dx>=0&&dy>=0&&dx<ww&&dy<hh&&g[fl(dy/s)*30+fl(dx/s)]===1;
    const oy=fy-hh+1-Math.round(LIFT[pose]*s*1.5);
    for(let dy=0;dy<hh;dy++)for(let dx=0;dx<ww;dx++){if(!at(dx,dy))continue;
      p.put(wx+ww-1-dx,oy+dy,!at(dx,dy-1)?ICE[3]:ROCK)}
    p.put(wx+ww-1-Math.round(25*s),oy+Math.round(4*s),ICE[4]);
    for(let n=0;n<5;n++){const L=Math.round((16+n*5)*s),yy=oy+Math.round((4+n*1.4)*s);
      for(let i=2;i<L;i++){const al=1-i/L;p.dput(wx+ww+i,yy,n&1?ICE[1]:ICE[2],al*.8)}}
  }
  function build(){
    const p=new Px();
    // totem silhouette: shaft, plinth, head block with crown, two swept feathered wings
    for(let y=TOP+24;y<=BASE+2;y++){const u=(y-TOP-24)/(BASE-TOP-24),hw=Math.round(6+2.2*u)+(y>BASE-9?3:0);for(let x=CX-hw;x<=CX+hw;x++)tset(x,y)}
    for(let y=TOP+8;y<=TOP+24;y++){const hw=9-(y<TOP+10?2:0)-(y>TOP+21?3-(TOP+24-y):0);for(let x=CX-hw;x<=CX+hw;x++)tset(x,y)}
    for(let y=TOP-6;y<TOP+8;y++){const hw=Math.round((y-(TOP-6))*.55);for(let x=CX-hw;x<=CX+hw;x++)tset(x,y)}
    for(let y=TOP-14;y<TOP-6;y++){tset(CX,y);if(y>TOP-11)tset(CX+1,y),tset(CX-1,y)}
    for(const sd of[-1,1])for(let i=0;i<=27;i++){const top=TOP+12-i*.55,bot=TOP+19-i*.8+(i%5<2?2*(1-i/28):0);
      for(let y=Math.round(top);y<=Math.round(bot);y++)tset(CX+sd*(8+i),y)}
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<RID[x]){const g=Math.pow(y/BASE,1.9)*(.55+.4*Math.exp(-Math.pow((x-110)/80,2)));p.put(x,y,ramp(SKY,g*.95,x,y));mask[y*W+x]=1}
      if(y>=FR[x]&&y<RID[x]){p.put(x,y,y===FR[x]?PINK[2]:FARC);mask[y*W+x]=2}
      if(y>=RID[x]){p.put(x,y,(y>RID[x]+2&&h2(x,y,3)>.97)?RIM:ROCK);mask[y*W+x]=3}}
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){if(!T[y*W+x])continue;mask[y*W+x]=0;
      let col=ROCK;
      const rr=!inT(x+1,y),ll=!inT(x-1,y),up=!inT(x,y-1),dn=!inT(x,y+1);
      if(rr)col=ICE[2];else if(up)col=ICE[1];else if(ll)col=dith(x,y,.7)?PINK[0]:PINK[1];else if(dn)col=PINK[1];
      else if(!inT(x+2,y)||(!inT(x,y-2)&&x>CX))col=ICE[0];
      else if(!inT(x-2,y))col=PINK[2];
      else if(y>TOP+24&&y<BASE-8){const gy=(y-TOP-24)%16;if(gy<2&&Math.abs(x-CX)<5+((y-TOP)>>6))col=GRV;else if(x===CX&&gy>3)col=CARV}
      p.put(x,y,col)}
    // carved face: beak and brow
    for(let k=0;k<5;k++)for(let x=CX-2+((k+1)>>1);x<=CX+2-((k+1)>>1);x++)p.put(x,TOP+16+k,GRV);
    for(let x=CX-7;x<=CX+7;x++)if(Math.abs(x-CX)>2)p.put(x,TOP+12,CARV);
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,a=TAU*t;
    for(let y=6;y<RID[0]-20;y++){const gy=y/BASE;
      for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
        const d=tnoise((x+84*t)/14,y/3.6,6,64,3),m=tnoise(x/36,y/20,4,64,5),v=d*.7+m*.5-.64;
        if(v>0)p.tint(x,y,mixc(CLV,CLW,clamp(gy*1.3)),v*3.2,.78)}}
    for(const r of RAIN){const tr=H*t,y=((r.y+tr)%H),xx=r.x-SLOPE*tr;
      for(let i=0;i<r.L;i++){const yy=y-i,x=((xx+SLOPE*i)%W+W)%W,Y=((fl(yy)%H)+H)%H;if(mask[Y*W+fl(x)]===0)continue;p.dput(x,Y,RAINC[r.far?0:1],r.far?.55:.8)}}
    // far wolf behind the near ridge
    const pose=fl(frac(3*t)*4),ps=[0,2,1,2][pose];
    {const s=.7,span=W+80,x=fl(((90-span*(t+.5))%span+span)%span)-30,xi=Math.min(W-1,Math.max(0,x+10));wolf(p,x,FR[xi],s,ps,t,0)}
    // wind rings: faint full ellipse, two bright heads with a tapering trail; back half hidden by the totem
    const ring=front=>{for(const R of RING){const n=Math.round(R.rx*6),head=frac(R.k*t+R.ph);
      for(let i=0;i<n;i++){const th=TAU*i/n,s=Math.sin(th);if((s>=0)!==front)continue;
        const x=CX+Math.cos(th)*R.rx,y=R.y+s*R.ry,xi=fl(x),yi=fl(y);if(!front&&mask[yi*W+xi]===0)continue;
        const d=frac(2*(R.k>0?head-i/n:i/n-head)),u=d/.45;
        if(u<1){const col=u<.06?ICE[4]:u<.25?ICE[3]:u<.55?ICE[2]:ICE[1];
          if(front){p.put(x,y,col);p.put(x,y+1,u<.5?col:ICE[1])}else p.put(x,y,u<.3?ICE[2]:ICE[1])}
        else if(front)p.dput(x,y,ICE[0],.7);else p.dput(x,y,ICE[0],.5)}}};
    ring(false);ring(true);
    // glyphs and eyes pulse down the totem
    for(let g=0;g<4;g++){const y=TOP+46+g*18,v=.5+.5*Math.sin(a-g*.9),col=ICE[v>.8?4:v>.5?3:v>.25?2:1];
      p.put(CX,y-2,col);p.put(CX-1,y-1,col);p.put(CX+1,y-1,col);p.put(CX-2,y,col);p.put(CX+2,y,col);p.put(CX-1,y+1,col);p.put(CX+1,y+1,col);p.put(CX,y+2,col)}
    {const v=.5+.5*Math.sin(a+1);const col=ICE[v>.6?4:3];for(const sd of[-1,1]){p.put(CX+sd*4,TOP+13,col);p.put(CX+sd*5,TOP+12,col);p.put(CX+sd*3,TOP+13,ICE[2])}}
    // charge arc between the wing tips, lit 3 frames per loop, with a glint on each tip
    const af=(f-8+N)%N;
    if(af<3){const k=af===1?2:1;for(const[x,y]of ARC){p.dput(x-1,y,ICE[2],.6);p.dput(x+1,y,ICE[2],.6);p.put(x,y,k>1?ICE[4]:ICE[3])}
      for(const sd of[-1,1]){const tx=CX+sd*35,ty=TOP-1;p.put(tx,ty,SPK[0]);p.put(tx-1,ty,ICE[3]);p.put(tx+1,ty,ICE[3]);p.put(tx,ty-1,ICE[3]);p.put(tx,ty+1,ICE[3])}}
    // near wolf on the ridge, gale grass over it
    {const s=1,span=W+90,x=fl(((100-span*t)%span+span)%span)-40,xi=Math.min(W-1,Math.max(0,x+14));wolf(p,x,RID[xi]-1,s,ps,t,0)}
    for(const g of TUFT){const sw=Math.sin(TAU*(2*t+g.ph));for(let k=0;k<g.h;k++){const bend=Math.round((k*k*.14+.6*sw*k*.5)),col=k>g.h-2?GRV:ROCK;p.put(g.x-bend,g.y-k-1,col);p.put(g.x+1-bend,g.y-k-1,ROCK)}}
    for(let y=RID[0]-2;y<H;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==3)continue;
      const d=tnoise((x+78*t)/13,y/2.4,6,64,9)-.76;if(d>0&&y<BASE+8)p.tint(x,y,ICE[1],d*3,.45)}
    for(const s of SPARKS){const age=frac(t-s.ph);if(age>.16)continue;const u=age/.16;
      const x=s.x+s.vx*u,y=s.y+s.vy*u*u*2-s.vy*u*.5,al=1-u*u;
      p.dput(x,y,SPK[s.col],al);if(u<.5)p.dput(x+1,y,SPK[s.col],al*.5)}
    for(let x=0;x<W;x++)if(x%3!==0)p.dput(x,FR[x]-1,PINK[1],.5+.4*Math.sin(TAU*(t+x/W)));
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== RESTORATION: night waterfall pool ================================== */
(()=>{
  const self={cls:'SHAMAN',tree:3,id:'shaman_restoration',name:'RESTORATION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0630','#0c0a30','#12104a','#1a1c5e','#24287a']);
  const WAT=c.ramp(['#05020c','#0a0830','#0c1648','#14306a','#1480a8','#22e0ff']);
  const FALL=c.ramp(['#0c1648','#14306a','#1a5a8a','#1480a8','#5ac8e8','#c8f6ff']);
  const MOTE=c.ramp(['#0a4a44','#18a07a','#43ffb4','#b8ffe0']);
  const ROCK=c('#07030e'),ROCK2=c('#120a28'),RIM=c('#24287a'),MOSS=c('#0a3a40'),MIST=c('#5a8cc8'),MOON=c('#d8f0ff'),MOONS=c('#5a8cc8'),CY=c('#22e0ff'),CYL=c('#9af4ff'),STAR=['#24287a','#5a6aa8','#d8f0ff'].map(c);
  const FX0=58,FX1=92,LIP=46,POOL=172,IX=122,IB=206;
  const mask=new Uint8Array(W*H); // 1 = sky, 2 = fall, 3 = water, 0 = rock
  const LL=[],RR=[];for(let y=0;y<H;y++){const k=Math.max(0,(y-LIP)/(POOL-LIP));LL.push(Math.round(FX0-2*k+2*Math.sin(y*.3)*(y>LIP+10?1:0)));RR.push(Math.round(FX1+3*k))}
  const TOPL=[],TOPR=[];for(let x=0;x<W;x++){TOPL.push(0);TOPR.push(0)}
  const CLIFF=x=>x<FX0?LIP-4-fl(8*Math.pow(clamp((FX0-x)/40),.7)+3*vn(x,9,3)):LIP-6-fl(16*Math.pow(clamp((x-FX1)/50),.6)+3*vn(x+30,8,4));
  const STARS=[];{const r=rng(5);for(let i=0;i<22;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*34),ph:r()})}
  const MOTES=[];{const r=rng(14);for(let i=0;i<24;i++)MOTES.push({x:6+r()*144,y:96+r()*130,ax:2+r()*5,ay:2+r()*4,k:1+fl(r()*2),k2:1+fl(r()*2),ph:r(),ph2:r(),tw:fl(r()*3)+1})}
  const RISE=[];{const r=rng(21);for(let i=0;i<46;i++)RISE.push({x:10+r()*136,y:POOL+4+r()*60,D:90+r()*80,lf:.55+r()*.35,ph:r(),sw:r()*TAU,big:r()>.85})}
  const sil=(p,x,y,col)=>{p.put(x,y,col);if(x>=0&&x<W&&y>=0&&y<H)mask[fl(y)*W+fl(x)]=0};
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const top=CLIFF(x),inFall=x>=LL[Math.min(y,H-1)]&&x<=RR[Math.min(y,H-1)]&&y>=LIP;
      if(y<top||(x>=FX0&&x<=FX1&&y<LIP-1)){p.put(x,y,ramp(SKY,Math.pow(y/LIP,1.2)*.7+.1,x,y));mask[y*W+x]=1}
      else if(y>=POOL){p.put(x,y,ramp(WAT,clamp(.28-.12*Math.abs(x-78)/78-.1*(y-POOL)/(H-POOL)+.08*tnoise(x/8,y/3,64,64,3)),x,y));mask[y*W+x]=3}
      else if(inFall){p.put(x,y,WAT[2]);mask[y*W+x]=2}
      else{const g=clamp(.5-.4*(y-top)/(POOL-top)+.18*tnoise(x/6,y/5,64,64,8)),col=ramp([ROCK,ROCK2,ROCK2,RIM],g,x,y);const st=(tnoise(x/2.5,y/16,64,64,13)>.74&&h2(x,y>>2,5)>.3)?c('#2a1850'):col;p.put(x,y,st);sil(p,x,y,st)}}
    // moon with a halo
    for(let dy=-8;dy<=8;dy++)for(let dx=-8;dx<=8;dx++){const x=28+dx,y=22+dy,d=dx*dx+dy*dy;
      if(d<=40){const cres=(dx+2)*(dx+2)+(dy-1)*(dy-1)<=40;if(!cres)p.put(x,y,d>30?MOONS:MOON)}
      else if(d<150&&dith(x,y,(1-d/150)*.22)&&mask[y*W+x]===1)p.put(x,y,SKY[4])}
    // lip of the fall, mossy rims on the cliffs and a few boulders by the water
    for(let x=0;x<W;x++){const top=CLIFF(x);if(x<FX0-1||x>FX1+1)p.put(x,top+1,RIM)}
    for(let x=FX0-1;x<=FX1+1;x++)p.put(x,LIP,RIM);
    {const r=rng(47);for(let i=0;i<70;i++){const x=1+fl(r()*154),y=POOL-70+fl(r()*76);if(mask[y*W+x]===0)p.put(x,y,MOSS)}}
    // water totem on a rock in the pool: a slim pole with a wave crest and a glowing bead
    const cx=IX;
    for(let dx=-10;dx<=10;dx++){const hh=Math.round(7*Math.sqrt(Math.max(0,1-dx*dx/110)));for(let k=0;k<=hh;k++)sil(p,cx+dx,IB-k+2,k===hh?RIM:ROCK)}
    for(let y=IB-8;y>=IB-44;y--){const u=(IB-8-y)/36,hw=y<IB-30?1:2;for(let x=cx-hw;x<=cx+hw;x++)sil(p,x,y,x===cx+hw&&y%4?RIM:ROCK)}
    for(let k=0;k<5;k++){sil(p,cx-2-k,IB-44-(k<3?k:2)+(k>3?1:0)+2,ROCK);sil(p,cx+2+k,IB-44-(k<3?k:2)+(k>3?1:0)+2,ROCK)}
    for(let dy=-3;dy<=3;dy++)for(let dx=-3;dx<=3;dx++)if(dx*dx+dy*dy<=7)sil(p,cx+dx,IB-50+dy,ROCK);
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,a=TAU*t;
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.ph+t));p.put(s.x,s.y,v>.85?STAR[2]:v>0?STAR[1]:STAR[0])}
    // the fall: tileable streaks scrolled one whole period per loop
    for(let y=LIP;y<POOL;y++){const k=(y-LIP)/(POOL-LIP);
      for(let x=FX0-4;x<=FX1+4;x++){if(mask[y*W+x]!==2)continue;
        const d=tnoise(x/1.8,(y+72*t)/6,64,12,4)*.65+tnoise(x/3,(y+144*t)/9,64,16,5)*.35,edge=Math.min(x-LL[y],RR[y]-x)/5;
        const v=d*(.55+.35*clamp(edge))-.2+.1*k;
        p.put(x,y,ramp(FALL,clamp(v*1.05),x,y,2))}}
    // spring at the lip: a sheet of water feeding the fall
    for(let x=FX0;x<=FX1;x++)for(let y=LIP-3;y<LIP;y++){const d=tnoise((x+35*t)/5,y/2,7,64,6);p.dput(x,y,FALL[d>.55?4:2],.5+(y-LIP+3)*.15)}
    // pool surface: reflection shimmer then ripples
    for(let y=POOL;y<H;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==3)continue;
      const d=tnoise((x+52*t)/5.2,y/1.8,10,64,7)-.7;if(d>0&&Math.abs(x-78)<30)p.dput(x,y,WAT[4],d*2.5)}
    const rip=(cx,cy,R,k,ph,cols)=>{for(let j=0;j<k;j++){const u=frac(t*1+ph+j/k),r=3+R*u,al=1-u;
      const n=Math.round(r*5);for(let i=0;i<n;i++){const th=TAU*i/n,x=cx+Math.cos(th)*r,y=cy+Math.sin(th)*r*.3;
        if(Math.sin(th)<0&&u>.5)continue;const xi=fl(x),yi=fl(y);if(xi<0||xi>=W||yi<POOL||mask[yi*W+xi]!==3)continue;
        p.dput(x,y,cols[al>.55?1:0],clamp(al*1.4))}}};
    rip(78,POOL+6,50,3,0,[WAT[4],CYL]);rip(IX,IB+1,40,3,.3,[WAT[4],CY]);
    // mist rolling off the foot of the fall
    for(let y=130;y<POOL+22;y++)for(let x=0;x<W;x++){const m=mask[y*W+x];if(m===0)continue;
      const d=tnoise((x+78*t)/13,y/5,12,64,11)*.6+tnoise((x-52*t)/6.5,y/3,8,64,12)*.4,g=Math.exp(-Math.pow((x-74)/42,2))*Math.exp(-Math.pow((y-(POOL-4))/18,2)),v=d*g*1.6-.34;
      if(v>0)p.tint(x,y,MIST,v*1.8,.5)}
    // water totem bead pulses and throws a faint ring
    const pu=.5+.5*Math.sin(a);
    for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++)if(dx*dx+dy*dy<=4)p.put(IX+dx,IB-50+dy,dx*dx+dy*dy<=1?(pu>.6?CYL:CY):WAT[4]);
    for(let dy=-9;dy<=9;dy++)for(let dx=-9;dx<=9;dx++){const d=Math.hypot(dx,dy);if(d<5||d>9)continue;
      const x=IX+dx,y=IB-50+dy;if(mask[y*W+x]===1||mask[y*W+x]===3)p.tint(x,y,CY,(1-(d-5)/4)*.5*pu,.5)}
    // fireflies of bioluminescence
    for(const m of MOTES){const x=m.x+m.ax*Math.sin(TAU*(m.k*t+m.ph)),y=m.y+m.ay*Math.sin(TAU*(m.k2*t+m.ph2)),v=.5+.5*Math.sin(TAU*(m.tw*t+m.ph));
      if(fl(x)>=0&&fl(x)<W&&fl(y)>=0&&fl(y)<H&&mask[fl(y)*W+fl(x)]===0)continue;
      p.put(x,y,MOTE[v>.75?3:v>.4?2:1]);if(v>.7){p.dput(x-1,y,MOTE[1],.6);p.dput(x+1,y,MOTE[1],.6);p.dput(x,y-1,MOTE[1],.5)}}
    // healing rain falling up: it lifts off the pool and drifts in toward the spring at the lip
    for(const e of RISE){const age=frac(t-e.ph);if(age>=e.lf)continue;const u=age/e.lf;
      const x=e.x+(74-e.x)*.3*u+1.6*Math.sin(TAU*(u*.5+e.sw)),y=e.y-e.D*u,al=u<.15?u/.15:u>.6?(1-u)/.4:1,
        col=MOTE[u<.35?3:u<.7?2:1];if(fl(y)<0||fl(x)<0||fl(x)>=W)continue;if(mask[fl(y)*W+fl(x)]===0)continue;
      p.dput(x,y,col,al*.9);p.dput(x,y+1,MOTE[1],al*.5);if(e.big)p.dput(x+1,y,col,al*.5)}
  }
  self.draw=draw;return TBG.add(self);
})();
