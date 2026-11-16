/* WARRIOR: Arms (battlefield at dusk), Fury (blood storm and flame), Protection (fortress wall in the rain). */
/* ================================== ARMS: battlefield at dusk ================================== */
(()=>{
  const self={cls:'WARRIOR',tree:1,id:'warrior_arms',name:'ARMS'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0420','#12083a','#1e0c50','#32115c','#521660','#78205c','#a02c52','#b8383e']);
  const GRD=c.ramp(['#2a1238','#1c0c2c','#140a22','#0c0618','#07030e']);
  const INK=c('#07030e'),HALO=c('#c8423e'),SUNC=['#c8423e','#e0693a','#f08a3a','#ffa850'].map(c);
  const RIM=c('#8a3a36'),COOL=c('#3a2068'),STEEL=c('#2a1850'),BLADE=c('#1c1038');
  const BAN=[c('#4a0f2a'),c('#7a1a3a'),c('#a82a48')],TRIM=c('#b0702a'),POLE=c('#1c1038');
  const CLV=c('#3a2068'),CLW=c('#a02c52');
  const STAR=['#3a2a78','#7a7ad0','#e0e6ff'].map(c);
  const EMBC=['#ffd98a','#ff9a3a','#d4572f','#8a2458'].map(c);
  const GLINT=c('#ffd98a'),GLINT2=c('#f08a3a'),GRASS=c('#2a1850'),DIRT=c('#2a1238'),FLET=c('#7a1a3a');
  const HOR=150,SUNX=104,SUNY=148,SUNR=11;
  const RIDGE=[];for(let x=0;x<W;x++)RIDGE.push(HOR-2-fl(2.5*vn(x,13,1)+2*vn(x+300,5,2)+(h2(x,3,4)>.965?2:0)));
  const gx=x=>Math.exp(-Math.pow((x-SUNX)/70,2));
  const mask=new Uint8Array(W*H); // 1 = open sky, 2 = open ground, 0 = silhouette (never tinted)
  const SPEARS=[];{const r=rng(21);for(let x=3;x<W;x+=2+fl(r()*5))SPEARS.push({x,h:5+fl(r()*10),pen:r()>.45?2+fl(r()*3):0,ph:r()});
    [[22,24],[60,30],[96,22],[132,28]].forEach(([x,h])=>SPEARS.push({x,h,pen:6,ph:r()}))}
  const STARS=[];{const r=rng(8);for(let i=0;i<30;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*70),ph:r(),k:1+fl(r()*2)})}
  const TUFTS=[];{const r=rng(14);for(let i=0;i<34;i++)TUFTS.push({x:3+fl(r()*150),y:160+fl(r()*70),ph:r()})}
  const EMB=emberList(5,44,150,232,50,120,.5,.9);
  const FSP=[[24,-1],[132,1]],FSPH=64;
  const CROWS=[{cx:62,cy:70,rx:16,ry:7,ph:0,k:1},{cx:66,cy:76,rx:12,ry:5,ph:.4,k:1},{cx:50,cy:62,rx:18,ry:6,ph:.7,k:-1},{cx:112,cy:88,rx:11,ry:4,ph:.2,k:1}];
  const FOG=c('#2a1850');
  const sil=(p,x,y,col)=>{p.put(x,y,col);if(x>=0&&x<W&&y>=0&&y<H)mask[fl(y)*W+fl(x)]=0};
  function sword(p){
    const cx=78;
    for(let y=114;y<=206;y++){const hw=y<150?3:Math.max(0,3*(1-(y-150)/56));const x0=Math.round(cx-hw),x1=Math.round(cx+hw);
      for(let x=x0;x<=x1;x++){let col=INK;if(hw>=1&&x===x1)col=RIM;else if(hw>=1&&x===x0)col=COOL;sil(p,x,y,col)}}
    for(let y=118;y<=165;y++)sil(p,cx,y,STEEL);
    for(let x=66;x<=90;x++){const yy=(x<69||x>87)?109:111;for(let k=0;k<3;k++)sil(p,x,yy+k,k===0&&x>78?RIM:INK)}
    for(let y=98;y<=110;y++){for(let x=77;x<=79;x++)sil(p,x,y,(y%3===0)?STEEL:INK)}
    for(let dy=-3;dy<=3;dy++)for(let dx=-3;dx<=3;dx++)if(dx*dx+dy*dy<=9)sil(p,cx+dx,95+dy,(dx>0&&dy<=0&&dx*dx+dy*dy>5)?RIM:INK);
    // dirt mound and a long shadow toward the left (the sun is on the right)
    for(let dx=-7;dx<=7;dx++){const hh=Math.round(2.2*(1-Math.abs(dx)/8));for(let k=0;k<=hh;k++)p.put(cx+dx,206-k+1,DIRT)}
    for(let x=18;x<=77;x++){const a=(1-(77-x)/62)*.7;p.dput(x,207,INK,a);p.dput(x,208,INK,a*.7)}
  }
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){const r=RIDGE[x];
      if(y<r){p.put(x,y,ramp(SKY,Math.pow(y/HOR,1.25)*(.34+.66*gx(x)),x,y));mask[y*W+x]=1}
      else{p.put(x,y,ramp(GRD,clamp((y-HOR)/(H-HOR)+.22*(tnoise(x/9,y/5,100,100,6)-.5)),x,y));mask[y*W+x]=2}}
    for(let dy=-SUNR;dy<=0;dy++)for(let dx=-SUNR;dx<=SUNR;dx++){if(dx*dx+dy*dy>SUNR*SUNR+SUNR*.6)continue;
      const x=SUNX+dx,y=SUNY+dy;if(x<0||x>=W||y>=RIDGE[x])continue;const k=(dy+SUNR)/SUNR;
      p.put(x,y,SUNC[k<.28?0:k<.6?1:k<.85?2:3]);mask[y*W+x]=0}
    for(const s of SPEARS){const b=RIDGE[s.x];for(let k=1;k<=s.h;k++)sil(p,s.x,b-k,INK);if(s.pen>=6){sil(p,s.x-1,b-s.h-1,INK);sil(p,s.x+1,b-s.h-1,INK)}}
    // arrows stuck in the field
    {const r=rng(33);for(let i=0;i<16;i++){const x=6+fl(r()*144),y=168+fl(r()*56),L=7+fl(r()*5),ln=r()<.5?-1:1;
      for(let k=0;k<=L;k++)p.put(x+ln*(k>>2),y-k,STEEL);p.put(x+ln*((L)>>2)-1,y-L,FLET);p.put(x+ln*((L)>>2)+1,y-L+1,FLET);p.put(x+ln*((L)>>2)-1,y-L+2,FLET)}}
    // rocks
    {const r=rng(44);for(let i=0;i<12;i++){const x=4+fl(r()*148),y=160+fl(r()*70),w=2+fl(r()*3);for(let k=0;k<w;k++){p.put(x+k,y,STEEL);if(k>0&&k<w-1)p.put(x+k,y-1,GRASS)}}}
    // two leaning spears in the near ground, pennants added live
    for(const[x0,lean]of FSP){for(let k=0;k<=FSPH;k++){const x=x0+Math.round(lean*k/FSPH*6);sil(p,x,234-k,INK);if(k>FSPH-9&&k<FSPH-2){sil(p,x+1,234-k,INK)}}
      const tx=x0+Math.round(lean*6);for(let k=0;k<4;k++)sil(p,tx+(k>1?1:0),234-FSPH-k+1,STEEL)}
    sword(p);
    for(const px of [10,146]){for(let y=84;y<=206;y++){sil(p,px,y,POLE);sil(p,px+1,y,y%4===0?STEEL:POLE)}
      sil(p,px,82,TRIM);sil(p,px+1,82,TRIM);sil(p,px,81,POLE);sil(p,px+1,81,POLE);
      for(let x=px-9;x<=px+10;x++)sil(p,x,96,POLE);sil(p,px-9,95,TRIM);sil(p,px+10,95,TRIM)}
    self.base=p;
  }
  function banner(p,cx,top,len,wid,ph,t){
    for(let r=0;r<len;r++){const u=r/(len-1),sway=Math.round(1.8*u*Math.sin(TAU*(t-u*.7+ph)));
      const notch=r>len-8?(r-(len-8)):0;
      for(let i=0;i<wid;i++){if(notch>0&&Math.abs(i-(wid-1)/2)<notch*.5)continue;
        const x=cx-fl(wid/2)+i+sway;let col=i<wid*.34?BAN[0]:i>wid*.7?BAN[2]:BAN[1];
        if(i===0||i===wid-1||r===0)col=TRIM;
        p.put(x,top+r,col);mask[(top+r)*W+x]=0}
      if(r===14){const m=[[-2,-2],[-1,-1],[0,0],[1,1],[2,2],[2,-2],[1,-1],[-1,1],[-2,2]];for(const[ax,ay]of m)p.put(cx+sway+ax,top+14+ay,TRIM)}}
  }
  function draw(p,f,N){
    const t=f/N,hb=1+.07*Math.sin(TAU*t);
    for(let y=SUNY-58;y<SUNY+36;y++)for(let x=SUNX-60;x<=SUNX+60;x++){if(x<0||x>=W||y<0||y>=H)continue;
      const d=Math.hypot(x-SUNX,(y-SUNY)*1.25);if(d>=58)continue;const a=Math.pow(1-d/58,1.7)*.5*hb,m=mask[y*W+x];
      if(m===1)p.tint(x,y,HALO,a,.55);else if(m===2&&y<SUNY+34)p.tint(x,y,HALO,a*.5,.4)}
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.8?STAR[2]:v>.1?STAR[1]:STAR[0])}
    const layers=[{y0:14,y1:100,P:52,sx:13,sy:4.2,seed:3,thr:.64,gain:3.2},{y0:58,y1:140,P:78,sx:13,sy:3.6,seed:9,thr:.62,gain:3.4}];
    for(const L of layers)for(let y=L.y0;y<L.y1;y++){const fy=(y-L.y0)/(L.y1-L.y0);
      for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
        const d=tnoise((x+L.P*t)/L.sx,y/L.sy,L.P/L.sx,64,L.seed),m=tnoise(x/40,y/22,8,64,L.seed+7),v=d*.7+m*.5-L.thr;
        if(v>0)p.tint(x,y,mixc(CLV,CLW,clamp(fy*(.5+.8*gx(x)))),v*L.gain,.78)}}
    for(const s of SPEARS){if(!s.pen)continue;const b=RIDGE[s.x],top=b-s.h-(s.pen>=6?1:0);
      const len=s.pen>=6?5+Math.round(1.6*(1+Math.sin(TAU*(2*t+s.ph*3)))):1+Math.round(s.pen*.5*(1+Math.sin(TAU*(2*t+s.ph*3)))*.6+.5);
      for(let k=1;k<=len;k++)p.put(s.x-k,top+(k>3?1:0),INK)}
    for(const g of TUFTS){const sx=Math.round(1.3*Math.sin(TAU*(t+g.ph)));p.put(g.x,g.y,GRASS);p.put(g.x+sx,g.y-1,GRASS);p.put(g.x-1+sx*2,g.y-2,GRASS);p.put(g.x+1,g.y,GRASS)}
    for(const[x0,lean]of FSP){const tx=x0+Math.round(lean*6),ty=234-FSPH+2;for(let k=1;k<=7;k++)p.put(tx-k,ty+Math.round(1.3*Math.sin(TAU*(2*t-k*.12))*(k/7))+(k>4?1:0),BAN[1])}
    for(let y=176;y<H;y++){const dp=(y-176)/(H-176);for(let x=0;x<W;x++){if(mask[y*W+x]!==2)continue;
      const d=tnoise((x+78*t)/13,y/7,6,64,20),v=d-.62+.1*dp;if(v>0)p.tint(x,y,FOG,v*2.2,.55)}}
    for(const b of CROWS){const a=TAU*(b.k*t+b.ph),x=b.cx+b.rx*Math.cos(a),y=b.cy+b.ry*Math.sin(a),up=Math.sin(TAU*(4*t+b.ph*3))>0;
      p.put(x,y,INK);p.put(x-1,y+(up?-1:1),INK);p.put(x+1,y+(up?-1:1),INK);p.put(x-2,y+(up?-2:1),INK);p.put(x+2,y+(up?-2:1),INK)}
    banner(p,10,98,46,11,0,t);banner(p,146,98,40,11,.3,t);
    // cloth tied to the guard, blowing left
    for(let i=0;i<16;i++){const yy=113+Math.round(1.6*Math.sin(TAU*(t-i*.07))*(i/15)+i*.1);p.put(65-i,yy,BAN[1]);p.put(65-i,yy+1,i%3===0?BAN[0]:BAN[2])}
    // glint climbing the blade once a loop
    const g=(t-.18)/.5;if(g>=0&&g<=1){const gy=Math.round(202-84*g);for(let k=-3;k<=3;k++){const a=1-Math.abs(k)/4;p.put(78,gy+k,GLINT,a*.9);p.put(79,gy+k,GLINT2,a*.5)}
      if(g>.1&&g<.9){p.put(76,gy,GLINT,.7);p.put(80,gy,GLINT,.7);p.put(78,gy-4,GLINT,.6);p.put(78,gy+4,GLINT,.6)}}
    emberDraw(p,EMB,t,-9,EMBC);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== FURY: blood storm and flame ================================== */
(()=>{
  const self={cls:'WARRIOR',tree:2,id:'warrior_fury',name:'FURY'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const CLOUD=c.ramp(['#05020c','#0e0314','#1a0418','#2a061c','#420820','#640c26','#8a1430','#a81c34']);
  const FIRE=c.ramp(['#1a0418','#3a0719','#590a1f','#7d0f25','#a3182b','#d03a2a','#ff7a2a','#ffc14a']);
  const SPIRE=c('#04010a'),SPRIM=['#3a0719','#7d0f25','#a3182b'].map(c);
  const BOLT=c('#fff1f5'),BG=['#ffb3c8','#ff4d88','#c02a6a'].map(c);
  const EMBC=['#ffc14a','#ff7a2a','#ff4d88','#a3182b'].map(c);
  const BASEY=186,MOONX=106,SP=[[8,10,30],[27,8,20],[46,12,40],[66,8,24],[86,11,34],[104,8,18],[121,13,44],[141,9,28],[154,7,22]];
  const yS=new Int16Array(W);
  for(let x=0;x<W;x++){let m=0;for(const[cx,w,h]of SP){const v=h*(1-Math.abs(x-cx)/w);if(v>m)m=v}yS[x]=BASEY-Math.max(m,4+fl(3*vn(x,9,7)))+(h2(x,5,8)>.82?1:0)}
  function mkBolt(seed,x0,yEnd,drift){const r=rng(seed),pts=[];let x=x0;
    for(let y=0;y<=yEnd;y++){if(r()<.6)x+=(r()<.5+drift?1:-1)*(r()<.2?2:1);pts.push([x,y])}
    const forks=[];[.32,.55,.74].forEach((q,i)=>{const s=pts[fl(q*yEnd)],dir=i%2?1:-1,len=14+fl(r()*14),fk=[];let fx=s[0],fy=s[1];
      for(let k=0;k<len;k++){if(k%2===0)fx+=dir;fy+=1;if(r()<.3)fx+=dir;fk.push([fx,fy])}forks.push(fk)});return{pts,forks}}
  const STRIKES=[{t:3/24,b:mkBolt(71,112,128,.06)},{t:15/24,b:mkBolt(93,40,104,-.04)}];
  const flashLvl=a=>a<0?0:a<1?1:a<2?.55:a<3?.9:a<4?.6:a<5.5?.35:a<7?.18:a<9?.08:0;
  const boltOn=a=>a>=0&&(a<1||(a>=2&&a<3));
  const EMB=emberList(17,46,176,236,60,130,.45,.85),SPARK=emberList(19,22,120,200,30,70,.25,.45);
  const mask=new Uint8Array(W*H);
  function build(){
    const p=new Px();
    for(let x=0;x<W;x++)for(let y=0;y<H;y++){if(y>=yS[x]){p.put(x,y,SPIRE);mask[y*W+x]=0}else mask[y*W+x]=1}
    self.base=p;
  }
  function cloudN(x,y,t){const a=TAU*t;
    return .5*tnoise(x/44+.5*Math.cos(a),y/17+.5*Math.sin(a),64,64,1)+.3*tnoise(x/21-.6*Math.cos(a+1),y/8.5+.6*Math.sin(a+1),64,64,2)+.2*tnoise((x+26*t)/6.5,y/3.6,4,64,3)}
  function envAt(x,t){const a=TAU*t;return tnoise(x/13+.35*Math.cos(a),.35*Math.sin(a),64,64,5)}
  function bolt(p,b,t0){
    for(const[x,y]of b.pts){p.dput(x-1,y,BG[0],.7);p.dput(x+1,y,BG[0],.7);p.dput(x-2,y,BG[1],.45);p.dput(x+2,y,BG[1],.45);p.put(x,y,BOLT)}
    for(const fk of b.forks)for(const[x,y]of fk){p.dput(x-1,y,BG[1],.5);p.dput(x+1,y,BG[1],.5);p.put(x,y,BG[0])}}
  function draw(p,f,N){
    const t=f/N;let L=0;for(const s of STRIKES)L=Math.max(L,flashLvl(frac(t-s.t)*24));
    for(let y=0;y<BASEY;y++){const gy=y/BASEY;
      for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
        const n=cloudN(x,y,t),c0=clamp((n-.3)*1.7),cl=c0*c0*(3-2*c0),dm=Math.hypot(x-106,(y-50)*1.04),
          disc=dm<14?(dm>12?.26:.36-.14*(dm/14)):0;
        const v=cl*(.38+.5*gy)+.24*gy*gy+disc*(1-cl*.92)+L*(.08+.34*cl);
        p.put(x,y,ramp(CLOUD,v*.95,x,y,3))}}
    for(const s of STRIKES)if(boltOn(frac(t-s.t)*24))bolt(p,s.b);
    // spire rims catch the flash and the fire
    for(let x=0;x<W;x++){const y=yS[x];p.put(x,y,SPRIM[L>.5?2:L>.15?1:0])}
    // flame: tileable noise scrolled one whole period per loop, so it rises forever and loops clean
    const FHC=new Float64Array(W);for(let x=0;x<W;x++)FHC[x]=46+42*envAt(x,t);
    for(let y=120;y<H;y++){const yb=H-1-y,sw=2.6*Math.sin(TAU*(t+y*.012));
      for(let x=0;x<W;x++){
        const hn=yb/FHC[x],xs=x+sw;
        const d=.6*tnoise(xs/4.2,(y+56*t)/13,40,4,1)+.4*tnoise(xs/2.6,(y+64*t)/7,60,8,2);
        const I=d*1.5+.2-hn*1.1;
        if(I>.34)p.put(x,y,ramp(FIRE,clamp((I-.34)/1.25),x,y));
        else if(I>.18&&dith(x,y,(I-.18)/.16))p.put(x,y,FIRE[1])}}
    emberDraw(p,EMB,t,10,EMBC);emberDraw(p,SPARK,t,-6,[EMBC[0],EMBC[1],EMBC[1]]);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== PROTECTION: fortress wall in the rain ================================== */
(()=>{
  const self={cls:'WARRIOR',tree:3,id:'warrior_protection',name:'PROTECTION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKYP=c.ramp(['#04030c','#080620','#0c0a30','#121248','#1a1c5e']);
  const WALL=c.ramp(['#080620','#0c0a30','#121248','#1a1c5e','#24287a']);
  const MORT=c('#04030a'),STEELR=c('#3d4a8a'),STEEL2=c('#5a6aa8'),STEEL3=c('#8fa0d8'),CYAN=c('#22e0ff'),FIELD=c('#0c0a30'),BAR=c('#1a1c5e');
  const MOON=c('#24287a'),CLC=c('#1a1c5e');
  const RAIN=[c('#5a6aa8'),c('#8fa0d8')],RIP=c('#6a8ad0'),WOOD=c('#4a2a14'),TFLAME=['#c25a1c','#ff8a2a','#ffd27a'].map(c),TLIGHT=c('#c25a1c'),TREF=c('#ff8a2a');
  const WALLTOP=60,CX=78;
  const mask=new Uint8Array(W*H); // 1 = open sky
  const hw=y=>{if(y<86||y>178)return-1;if(y<=118){const k=y-86;return 31-(k<5?5-k:0)}const u=(y-118)/60;return 31*Math.pow(1-Math.pow(u,1.5),.7)};
  const inS=(x,y)=>{const w=hw(y);return w>=0&&Math.abs(x-CX)<=Math.round(w)};
  const OUT=[],RIM2=[];
  {const edge=[];for(let y=86;y<=178;y++)for(let x=CX-32;x<=CX+32;x++){if(!inS(x,y))continue;if(!inS(x-1,y)||!inS(x+1,y)||!inS(x,y-1)||!inS(x,y+1))edge.push([x,y])}
   const set=new Set(edge.map(([x,y])=>x+','+y));
   for(let y=86;y<=178;y++)for(let x=CX-32;x<=CX+32;x++){if(!inS(x,y)||set.has(x+','+y))continue;
     if(set.has((x-1)+','+y)||set.has((x+1)+','+y)||set.has(x+','+(y-1))||set.has(x+','+(y+1)))RIM2.push([x,y])}
   const cy=132;edge.forEach(e=>e.push((Math.atan2(e[1]-cy,e[0]-CX)/TAU+1.25)%1));edge.sort((a,b)=>a[2]-b[2]);edge.forEach(e=>OUT.push(e))}
  const RAINS=[];{const r=rng(61);for(let i=0;i<58;i++){const far=i%3!==0;RAINS.push({x:r()*W,y:r()*H,c:far?1:2,len:far?4:6})}}
  const RIPS=[];{const r=rng(73);for(let i=0;i<9;i++)RIPS.push({x:6+fl(r()*144),y:222+fl(r()*10),ph:r(),lf:.3})}
  const CLOUDS=null;
  const TORCH=[{x:8,fy:102,id:1},{x:148,fy:102,id:2}];
  const SPARKS=emberList(23,12,92,106,20,40,.3,.5);
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const mer=y>=44&&y<WALLTOP&&((x+6)%24)<14,wall=y>=WALLTOP||mer;
      if(!wall){p.put(x,y,ramp(SKYP,Math.pow(y/WALLTOP,1.3),x,y));const dm=Math.hypot(x-34,(y-18)*1.1);if(dm<30&&dith(x,y,Math.pow(1-dm/30,1.5)*.45))p.put(x,y,MOON,.7);mask[y*W+x]=1;continue}
      const cy=y<WALLTOP?y+(WALLTOP-44):y,course=fl((y-WALLTOP+16)/9),ry=(y-WALLTOP+16)%9,xo=(course%2)*9,bx=fl((x+xo)/18),vx=(x+xo)%18;
      const bt=h2(bx,course,3),g=clamp(.62-.5*(y-WALLTOP)/(H-WALLTOP))+(bt-.5)*.34+(ry===0?.18:ry===7?-.1:0);
      if(ry===8||(vx===17&&ry<8))p.put(x,y,MORT);else p.put(x,y,ramp(WALL,g,x,y));
      if(h2(x,y,11)>.992)p.put(x,y,WALL[ry<4?3:1])}
    for(let y=WALLTOP;y<WALLTOP+3;y++)for(let x=0;x<W;x++){if(y===WALLTOP)p.put(x,y,STEELR);else if(dith(x,y,y===WALLTOP+1?.6:.25))p.put(x,y,MORT)}
    for(let y=44;y<48;y++)for(let x=0;x<W;x++){if(((x+6)%24)<14){if(y===44)p.put(x,y,STEELR)}}
    // the carved shield: a recessed field, two steel rims, bars, a boss ringed with rivets
    for(let y=86;y<=178;y++)for(let x=CX-32;x<=CX+32;x++){if(!inS(x,y))continue;p.put(x,y,ramp([FIELD,WALL[1],WALL[2]],clamp(.18+.5*(1-(y-86)/92)*.5),x,y))}
    for(let y=88;y<=176;y++)for(let x=CX-32;x<=CX+32;x++){if(!inS(x,y))continue;if(y===118||(Math.abs(x-CX)<=0&&y>90))p.put(x,y,BAR)}
    for(let y=-12;y<=12;y++)for(let x=-12;x<=12;x++){const d=Math.hypot(x,y);if(d<=10&&d>8.4)p.put(CX+x,125+y,STEELR);else if(d<=8.4)p.put(CX+x,125+y,ramp([WALL[1],WALL[2],WALL[3]],clamp(.8-d/11),CX+x,125+y))}
    for(let k=0;k<8;k++){const a=k*TAU/8;p.put(CX+Math.round(Math.cos(a)*14),125+Math.round(Math.sin(a)*14),STEEL2)}
    for(const[x,y]of OUT)p.put(x,y,STEEL2);for(const[x,y]of RIM2)p.put(x,y,ramp([FIELD,STEELR],.5,x,y));
    self.base=p;
  }
  function torch(p,t,f,tc){
    const hs=hash(tc.id*131+f*17),base=tc.fy+3,ht=11+(hs<.3?1:0)-(hs>.82?1:0)+Math.round(1.3*Math.sin(TAU*(2*t+tc.id*.37))),lean=Math.round(1.4*Math.sin(TAU*(t+tc.id*.21)));
    for(let y=base+1;y<=base+17;y++){p.put(tc.x,y,WOOD);p.put(tc.x+1,y,WOOD);p.put(tc.x-1,y,y%6===0?STEELR:WOOD)}
    for(let x=tc.x-3;x<=tc.x+3;x++)p.put(x,base+1,STEELR);p.put(tc.x-4,base+2,STEELR);p.put(tc.x+4,base+2,STEELR);
    for(let r=0;r<ht;r++){const u=r/ht,wid=Math.max(1,Math.round(5.6*Math.pow(1-u,.7))+(r<2?1:0)),dx=Math.round(lean*u*u*1.6);
      for(let i=0;i<wid;i++){const x=tc.x+1-((wid-1)>>1)+i+dx,y=base-r,edge=(i===0||i===wid-1)&&wid>2;
        p.put(x,y,u<.25?(edge?TFLAME[1]:TFLAME[2]):u<.55?(edge?TFLAME[0]:TFLAME[1]):(edge?TFLAME[0]:TFLAME[1]))}}
  }
  function draw(p,f,N){
    const t=f/N;
    // slow moon-lit clouds scrolling left, two periods, in the sky strip
    for(let y=4;y<WALLTOP-2;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const d=tnoise((x+78*t)/13,y/3.4,6,64,5),m=tnoise(x/40,y/20,8,64,12),v=d*.7+m*.5-.66;if(v>0)p.tint(x,y,CLC,v*3.4,.8)}
    // shield pulse: a head runs once round the rim each loop, a faint breath under it
    const br=.2+.1*Math.sin(TAU*t),head=frac(t);
    OUT.forEach(([x,y,u],i)=>{const d=frac(head-u),k=d<.26?1-d/.26:0;
      if(k>0)p.put(x,y,mixc(STEEL3,CYAN,k>.7?(k-.7)/.3:0),.35+.6*k);else p.dput(x,y,STEEL3,br*.6);
      if(k>.25){const ox=Math.sign(x-CX),oy=y<132?-1:1;p.dput(x+ox,y,STEEL2,k*.5);p.dput(x,y+oy,STEEL2,k*.4)}});
    RIM2.forEach(([x,y],i)=>{const u=OUT[Math.min(OUT.length-1,Math.round(i*OUT.length/RIM2.length))][2],d=frac(head-u);if(d<.12)p.dput(x,y,STEEL3,(1-d/.12)*.7)});
    // torch light on the bricks, flickering by frame
    for(const tc of TORCH){const hs=hash(tc.id*977+f*13),A=.62+.14*hs,R=34,cy=tc.fy-2;
      for(let y=cy-R;y<=cy+R;y++)for(let x=tc.x-R;x<=tc.x+R;x++){if(x<0||x>=W||y<0||y>=H)continue;if(mask[y*W+x]===1&&y<WALLTOP)continue;
        const d=Math.hypot(x-tc.x,(y-cy)*1.1);if(d>=R)continue;p.tint(x,y,TLIGHT,Math.pow(1-d/R,1.6)*A,.5)}}
    // rain over the wall
    for(const r of RAINS){const yw=((r.y+r.c*H*t)%H+H)%H;
      for(let k=0;k<r.len;k++){const x=((r.x-.2*(yw-k))%W+W)%W;p.put(x,yw-k,RAIN[k===0?1:0],k===0?.9:r.c===1?.38:.55)}}
    // wet flagstones: shimmer rows, torch streaks, ripples
    const step=fl(t*6);
    for(let y=214;y<H;y++){const dp=(y-214)/(H-214);
      for(let k=0;k<2;k++){if(hash(y*17+k*101+step*7)>.5)continue;const x0=fl(hash(y*31+k*7+step)*W),ln=3+fl(hash(y+k+step)*(4+dp*6));for(let i=0;i<ln;i++)p.put((x0+i)%W,y,RIP,.28+dp*.2)}
      for(const tc of TORCH){if(hash(y*13+step+tc.id*5)<.34)continue;p.put(tc.x+fl(hash(y*3+step+tc.id)*3)-1,y,TREF,.45-dp*.15)}}
    for(const rp of RIPS){const age=frac(t-rp.ph);if(age>=rp.lf)continue;const u=age/rp.lf,r=1+6*u,ry=Math.max(1,r*.35);
      for(let a=0;a<18;a++){const th=a*TAU/18;p.dput(rp.x+Math.cos(th)*r,rp.y+Math.sin(th)*ry,RIP,(1-u)*.95)}}
    for(const tc of TORCH)torch(p,t,f,tc);
    emberDraw(p,SPARKS.map(s=>Object.assign({},s,{x:s.x%2?148:8})),t,0,[TFLAME[2],TFLAME[1],TFLAME[0]]);
  }
  self.draw=draw;return TBG.add(self);
})();

