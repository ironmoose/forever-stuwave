/* PRIEST: Discipline (cold shield dome over stone steps), Holy (starlit cathedral sky), Shadow (void sky, tendrils and one eye). */
/* ================================== DISCIPLINE: shield dome over stone steps ================================== */
(()=>{
  const self={cls:'PRIEST',tree:1,id:'priest_discipline',name:'DISCIPLINE'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#080520','#0c0a30','#101440','#16205a']);
  const STONE=c.ramp(['#07030e','#0c0a30','#121248','#1a2060','#243078','#34468c']);
  const DOME=c.ramp(['#0a1a40','#12306a','#1a4a8a','#2a7ab0','#5ac8e8','#9ae8ff','#e0faff','#ffffff']);
  const CY=c('#22e0ff'),MORT=c('#04030a'),STAR=['#3a4a9a','#8fa0d8','#e0faff'].map(c);
  const CX=78,BY=172,RX=64,RY=100,RCY=104;
  const mask=new Uint8Array(W*H); // 1 = open sky outside the dome
  const STARS=[];{const r=rng(5);for(let i=0;i<30;i++){const x=2+fl(r()*152),y=2+fl(r()*120);STARS.push({x,y,ph:r(),k:1+fl(r()*2)})}}
  const MOTES=emberList(9,26,100,176,40,90,.4,.8);
  const domeR=(x,y)=>Math.hypot((x-CX)/RX,(y-BY)/RY);
  const STEPH=10,STEPY=176;
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<STEPY){p.put(x,y,ramp(SKY,Math.pow(y/STEPY,1.4)*.8+.1*(tnoise(x/12,y/6,64,64,3)-.5),x,y));mask[y*W+x]=1}
      else p.put(x,y,ramp(STONE,.1+.06*tnoise(x/9,y/5,64,64,4),x,y)) }
    // stone steps: top face, front face with brick seams, widening toward the viewer
    for(let k=0;k<6;k++){
      const y0=STEPY+k*STEPH,hw=44+k*14;
      for(let y=y0;y<Math.min(H,y0+STEPH);y++)for(let x=CX-hw;x<=CX+hw;x++){
        if(x<0||x>=W)continue;const ry=y-y0,edge=Math.abs(x-CX)/hw;
        if(ry<3){p.put(x,y,ramp(STONE,clamp(.62-.3*edge*edge-ry*.05+(h2(x>>3,k,2)-.5)*.1),x,y))}
        else{const bx=fl((x+k*7)/17),vx=(x+k*7)%17;
          if(vx===16)p.put(x,y,MORT);else p.put(x,y,ramp(STONE,clamp(.34-.26*edge*edge+(h2(bx,k,3)-.5)*.16-(ry-3)*.012),x,y))}}
      for(let x=CX-hw;x<=CX+hw;x++){if(x>=0&&x<W&&y0<H)p.put(x,y0,STONE[4]);const yb=y0+STEPH-1;if(x>=0&&x<W&&yb<H)p.put(x,yb,MORT)}}
    for(let i=0;i<60;i++){const x=fl(h2(i,1,9)*W),y=STEPY+fl(h2(i,2,9)*(H-STEPY));if(dith(x,y,.5))p.put(x,y,STONE[1])}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N;
    for(const s of STARS){if(mask[s.y*W+s.x]!==1||domeR(s.x,s.y)<=1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.8?STAR[2]:v>.1?STAR[1]:STAR[0])}
    const breath=.5+.5*Math.sin(TAU*t);
    // dome body: dark core, fresnel toward the rim
    for(let y=BY-RY-2;y<=BY;y++)for(let x=CX-RX-2;x<=CX+RX+2;x++){
      if(x<0||x>=W||y<0)continue;const r=domeR(x,y);if(r>1)continue;
      const a=Math.pow(r,4.5)*.5+.05*(1-r)+.04*breath*Math.pow(r,2);
      p.tint(x,y,DOME[2],a,.7);
      // soft sheen on the upper left
      const sx=(x-CX+30)/26,sy=(y-BY+78)/10;if(sx*sx+sy*sy<1&&r>.55)p.tint(x,y,DOME[5],.28*(1-sx*sx-sy*sy),.5)}
    // ripple rings crossing the dome from a point inside it
    for(let n=0;n<2;n++){const u=frac(t+n*.5),R=5+88*u,al=Math.pow(1-u,1.3);
      for(let y=BY-RY;y<=BY;y++)for(let x=CX-RX;x<=CX+RX;x++){
        if(x<0||x>=W)continue;const r=domeR(x,y);if(r>.97)continue;
        const d=Math.hypot(x-CX,y-RCY)-R;
        if(d>-.8&&d<=.7)p.put(x,y,DOME[5],.8*al);
        else if(d>-2.6&&d<=-.8)p.dput(x,y,DOME[3],.55*al);
        else if(d>.7&&d<1.7)p.dput(x,y,DOME[2],.4*al)}}
    // rune lines: meridians and latitude arcs with a pulse running out from the base
    const head=frac(t);
    const rune=(r,a,seg)=>{const x=CX+RX*r*Math.cos(a),y=BY-RY*r*Math.sin(a);
      if(y>=BY-1)return;const d=frac(head-r),k=d<.35?1-d/.35:0;
      if(k>.05)p.put(x,y,mixc(DOME[4],DOME[7],k),.45+.5*k);else p.put(x,y,DOME[3],.3)};
    for(let k=1;k<=7;k++){const a=Math.PI*k/8;for(let s=0;s<190;s++){const r=.1+.86*s/190;if(fl(r*34)%3===2)continue;rune(r,a)}}
    for(const rr of[.34,.6,.84])for(let s=0;s<200;s++){const a=.08*Math.PI+.84*Math.PI*s/200;if(fl(a*rr*60)%4>=3)continue;rune(rr,a)}
    // sigil: ring and cross
    {const sy=BY-RY*.58,pu=.45+.4*breath;
      for(let a=0;a<40;a++){const th=a*TAU/40;p.put(CX+Math.cos(th)*8,sy+Math.sin(th)*8,DOME[5],pu)}
      for(let k=-5;k<=5;k++){p.put(CX+k,sy,DOME[5],pu);p.put(CX,sy+k,DOME[5],pu)}}
    // dome rim: bright edge with a travelling highlight
    for(let y=BY-RY-2;y<=BY;y++)for(let x=CX-RX-2;x<=CX+RX+2;x++){
      if(x<0||x>=W)continue;const r=domeR(x,y);if(r<.935||r>1.015)continue;
      const ang=Math.atan2(BY-y,x-CX)/Math.PI,d=frac(t-ang*.5),k=d<.25?1-d/.25:0;
      if(r>=.975)p.put(x,y,k>.3?DOME[7]:DOME[5],.7+.3*k);else p.dput(x,y,DOME[3],.7)}
    // base glow ring on the top step
    for(let a=0;a<160;a++){const th=Math.PI*a/160,x=CX+Math.cos(th)*RX,y=BY+Math.sin(th)*9;p.put(x,y,DOME[5],.8);p.dput(x,y+1,CY,.5)}
    for(let a=0;a<120;a++){const th=Math.PI*a/120,x=CX+Math.cos(th)*(RX-5),y=BY+1+Math.sin(th)*6;p.dput(x,y,DOME[4],.45)}
    for(let y=STEPY;y<H;y++)for(let x=0;x<W;x++){const d=Math.hypot((x-CX)/74,(y-BY)/62),a=Math.pow(clamp(1-d),1.5)*.38*(.8+.2*breath);if(a>.01)p.tint(x,y,DOME[2],a,.5)}
    emberDraw(p,MOTES,t,0,[DOME[6],DOME[5],DOME[4],DOME[2]]);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== HOLY: starlit cathedral sky ================================== */
(()=>{
  const self={cls:'PRIEST',tree:2,id:'priest_holy',name:'HOLY'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0420','#12083a','#1e0c50','#32185a','#4a2860']);
  const GOLD=c.ramp(['#3a2a30','#6a4a30','#a07a30','#d8a830','#ffd23f','#fff1c4']);
  const HAZE=c('#e8c880'),HAZE2=c('#b89850');
  const STONE=c.ramp(['#05020c','#0a0418','#120a28','#1c1038','#2a1850']);
  const TRIM=['#6a4a30','#a07a30'].map(c);
  const STARC=['#3a2a78','#8a80d0','#fff1c4'].map(c);
  const MOTEC=['#fff1c4','#ffd23f','#c89a30','#7a5a28'].map(c);
  const HX=78,HY=62,SPY=100,AX=12;
  const mask=new Uint8Array(W*H); // 1 = open sky inside the arch
  const STARS=[];{const r=rng(12);for(let i=0;i<34;i++)STARS.push({x:16+fl(r()*124),y:4+fl(r()*100),ph:r(),k:1+fl(r()*2)})}
  const MOTES=emberList(31,54,150,236,90,190,.5,.95);
  const inArch=(x,y,o)=>{const R=100;if(y>=SPY)return x>=AX+o&&x<=W-1-AX-o;
    return Math.hypot(x-(AX+o+R),y-SPY)<=R-(o?0:0)&&Math.hypot(x-(W-1-AX-o-R),y-SPY)<=R};
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<SPY+60&&inArch(x,y,0)){const dh=Math.hypot(x-HX,(y-HY)*.9);
        const v=Math.pow(clamp(y/190),1.2)*.55+.4*Math.pow(clamp(1-dh/70),2);
        p.put(x,y,ramp(SKY,v*.95,x,y));mask[y*W+x]=1}
      else if(y>=SPY+60&&x>=AX&&x<=W-1-AX){ // floor
        const fy=(y-SPY-60)/(H-SPY-60);p.put(x,y,ramp(STONE,.12+.25*fy,x,y))}
      else{p.put(x,y,ramp(STONE,.18+.5*Math.min(1,Math.abs(x-78)/78)*.4+(h2(x>>2,y>>2,4)-.5)*.1,x,y))}}
    // arch mouldings: a dim gold edge and an inner thin line
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const a=inArch(x,y,0),b=inArch(x,y,2);
      if(y<SPY+60){if(a&&!b)p.put(x,y,TRIM[0]);if(!a&&inArch(x,y,-2))p.put(x,y,STONE[4])}
      }
    // pillar bands
    for(let y=SPY;y<H;y+=22)for(let x=0;x<AX+2;x++){p.put(x,y,STONE[4]);p.put(W-1-x,y,STONE[4])}
    for(let y=SPY;y<H;y++){p.put(AX-1,y,STONE[4]);p.put(W-AX,y,STONE[4]);p.put(AX,y,TRIM[0]);p.put(W-1-AX,y,TRIM[0])}
    // floor: converging joins and receding rows
    for(let y=SPY+60;y<H;y++)for(let x=AX+1;x<W-1-AX;x++){
      const fy=(y-SPY-60+1)/(H-SPY-60);
      for(let k=-6;k<=6;k++){const lx=HX+k*(10+fy*28);if(Math.abs(x-lx)<.5&&dith(x,y,.45))p.put(x,y,STONE[4])}}
    for(let q=1;q<=6;q++){const y=SPY+60+fl(Math.pow(q/6,1.7)*(H-SPY-62));for(let x=AX+1;x<W-1-AX;x++)if(dith(x,y,.5))p.put(x,y,STONE[4])}
    for(const[sc,g]of[[.19,1],[.27,1],[.4,2],[.62,3],[1,3]])for(const sd of[-1,1]){
      const xc=HX+sd*(70*sc+10*sc),yb=162+70*sc,yt=yb-118*sc,hw=Math.max(1,Math.round(5*sc));
      for(let y=Math.round(yt);y<=yb;y++)for(let x=Math.round(xc-hw);x<=Math.round(xc+hw);x++){
        if(x<AX+1||x>=W-1-AX)continue;const e=(x-xc)*sd;p.put(x,y,e>=hw?TRIM[0]:e<-hw+1&&hw>1?STONE[Math.min(4,g+1)]:STONE[g]);mask[y*W+x]=0}
      for(let x=Math.round(xc-hw-1);x<=Math.round(xc+hw+1);x++){if(x>=AX+1&&x<W-1-AX){p.put(x,Math.round(yb),STONE[4]);p.put(x,Math.round(yt),STONE[4])}}}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,br=.5+.5*Math.sin(TAU*t);
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.8?STARC[2]:v>.1?STARC[1]:STARC[0])}
    // glow behind the halo and a shaft of light down the nave
    for(let y=0;y<H;y++)for(let x=AX;x<W-AX;x++){if(mask[y*W+x]!==1&&y<SPY+60)continue;
      const dh=Math.hypot(x-HX,(y-HY)*1.1),a=Math.pow(clamp(1-dh/54),2)*(.38+.1*br);
      if(a>.01)p.tint(x,y,GOLD[3],a,.55);
      if(y>HY+6){const sh=Math.abs(x-HX)/(8+(y-HY)*.12);if(sh<1)p.tint(x,y,GOLD[2],(1-sh)*.12*(1-(y-HY)/200),.5)}}
    // wings: three rows of tapered feathers along a swept arm, over a soft haze
    for(let y=60;y<160;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1&&y<SPY+60)continue;if(y>=SPY+60&&(x<AX||x>=W-AX))continue;
      const dx=Math.abs(x-HX)-5;if(dx<0||dx>72)continue;const u=dx/72,cy=104+10*u,d=Math.abs(y-cy)/(30-8*u);
      if(d<1)p.tint(x,y,HAZE2,Math.pow(1-d,2)*.3*(1-.4*u)*(.85+.15*br),.5)}
    for(const sd of[-1,1])for(let r=2;r>=0;r--)for(let i=0;i<9;i++){
      const u=i/8,bx=HX+sd*(6+u*56),by=96+r*5-26*Math.sin(u*Math.PI*.8)*(1-.15*r)+8*u*u;
      const ang=.15+.95*u+r*.13+.06*Math.sin(TAU*(t-u*.5+r*.2)),len=(40-20*u)*(1-r*.2)+3;
      const col=r===2?HAZE2:HAZE,al=r===0?.3:r===1?.25:.2;
      for(let k=0;k<=len;k++){const q=k/len,x=bx+sd*Math.cos(ang)*k,y=by+Math.sin(ang)*k,w=3.2*(1-q*.85)*(1-.12*r);
        for(let o=-2;o<=2;o++){const wv=Math.abs(o)/Math.max(.6,w);if(wv>1||x<AX+3||x>=W-AX-3||y<0||mask[fl(y)*W+fl(x)]!==1)continue;p.put(x-Math.sin(ang)*o*sd,y+Math.cos(ang)*o,wv>.7?GOLD[2]:col,al*(1-.3*wv)*(1-.4*q))}
        if(k%2===0&&x>AX+3&&x<W-AX-3)p.put(x,y,GOLD[4],.3*(1-q))}}
    // halo: gold ring, bright arc, pulse
    for(let a=0;a<120;a++){const th=a*TAU/120,x=HX+Math.cos(th)*19,y=HY+Math.sin(th)*5.4,fr=Math.sin(th)<0;
      p.put(x,y,fr?GOLD[5]:GOLD[3],.75+.25*br);if(fr)p.dput(x,y-1,GOLD[4],.5);else p.dput(x,y+1,GOLD[2],.4)}
    // light motes rising
    emberDraw(p,MOTES,t,4,MOTEC);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== SHADOW: void sky, tendrils and one eye ================================== */
(()=>{
  const self={cls:'PRIEST',tree:3,id:'priest_shadow',name:'SHADOW'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const VOID=c.ramp(['#05020c','#08031a','#0c0524','#12083a','#1a0c4e']);
  const PUR=c.ramp(['#12062a','#240a4a','#3a0f6e','#5a16a0','#7a1fd1']);
  const PINK=c.ramp(['#6a1060','#8a1e78','#c030a8','#ff4dd8','#ffa0ec']);
  const BLK=c('#030108'),WHITE=c('#ffe0f8');
  const EX=78,EY=112,EW=34;
  const STARS=[];{const r=rng(17);for(let i=0;i<30;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*232),ph:r(),k:1+fl(r()*2)})}
  const HALO=[];{const r=rng(23);for(let i=0;i<26;i++){const a=r()*TAU,k=1+r()*.5;HALO.push({x:EX+Math.cos(a)*50*k,y:EY+Math.sin(a)*30*k,ph:r(),k:1+fl(r()*2)})}}
  const WISP=emberList(41,14,120,236,50,110,.4,.8);
  const PI=Math.PI;
  const TEN=[ // far layer first
    {x:0,y:0,a:.62,len:52,curl:-.55,ph:.1,w:7,far:1},{x:155,y:0,a:PI-.62,len:52,curl:.55,ph:.6,w:7,far:1},
    {x:0,y:235,a:-.62,len:52,curl:.55,ph:.35,w:7,far:1},{x:155,y:235,a:-PI+.62,len:52,curl:-.55,ph:.85,w:7,far:1},
    {x:0,y:0,a:1.0,len:46,curl:.7,ph:0,w:15},{x:155,y:0,a:PI-1.0,len:46,curl:-.7,ph:.5,w:15},
    {x:0,y:235,a:-1.0,len:46,curl:-.7,ph:.25,w:15},{x:155,y:235,a:-PI+1.0,len:46,curl:.7,ph:.75,w:15},
    {x:0,y:92,a:.25,len:34,curl:.5,ph:.4,w:8},{x:155,y:150,a:PI-.25,len:34,curl:-.5,ph:.9,w:8}];
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const d=Math.hypot((x-EX)/78,(y-EY)/110),v=.1+.4*Math.pow(clamp(1-d),1.6)+.08*(tnoise(x/14,y/9,64,64,3)-.5);
      p.put(x,y,ramp(VOID,v*.9,x,y))}
    self.base=p;
  }
  function trace(T,t){
    const pts=[];let x=T.x,y=T.y,a=T.a;const n=T.len;
    for(let i=0;i<n;i++){const s=i/n;a+=T.curl*(.02+.17*s*s)+.1*Math.sin(TAU*(t-s*1.2+T.ph))*(.25+s);x+=2.2*Math.cos(a);y+=2.2*Math.sin(a);pts.push([x,y,s,a])}
    return pts}
  const disc=(p,x,y,r,col)=>{const R=Math.ceil(r);for(let dy=-R;dy<=R;dy++)for(let dx=-R;dx<=R;dx++)if(dx*dx+dy*dy<=r*r)p.put(x+dx,y+dy,col)};
  function tendril(p,T,t){
    const pts=trace(T,t),far=!!T.far,B=far?PUR[0]:PUR[1],C=far?BLK:PUR[0],R=far?PUR[1]:PUR[3];
    const wd=s=>T.w*Math.pow(1-s,.9)+.8;
    for(const[x,y,s]of pts)disc(p,x,y,wd(s)/2,B);
    for(const[x,y,s]of pts)if(wd(s)>4)disc(p,x+.6,y+.6,wd(s)/2-1.6,C);
    for(const[x,y,s,a]of pts){const r=wd(s)/2,nx=Math.sin(a),ny=-Math.cos(a);   // rim on the side facing up and left
      const sg=(nx+ny)<0?1:-1;p.put(x+nx*sg*(r-.2),y+ny*sg*(r-.2),R)}
    if(!far){const e=pts[pts.length-1],pu=.5+.5*Math.sin(TAU*(t+T.ph));p.put(e[0],e[1],pu>.5?PINK[4]:PINK[3]);p.dput(e[0]+1,e[1],PINK[2],pu);p.dput(e[0],e[1]-1,PINK[2],pu*.8)}}
  const open=t=>{const k=u=>u*u*(3-2*u);return t<.34?0:t<.42?k((t-.34)/.08):t<.66?1:t<.76?1-k((t-.66)/.1):0};
  function draw(p,f,N){
    const t=f/N,o=open(t);
    // void vortex: a dithered spiral swirling round the eye, dark at the core
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const dx=x-EX,dy=(y-EY)*.85,r=Math.hypot(dx,dy);if(r>100||r<4)continue;
      const th=Math.atan2(dy,dx),sw=.5+.5*Math.sin(3*th-.17*r-TAU*t),fall=Math.pow(clamp(1-r/100),1.3),
        n=tnoise((x+96*t)/16,y/10,6,64,8)*.5+.5;
      const a=fall*(.15+.8*sw*sw)*n;
      if(a>.02)p.tint(x,y,r<46?PUR[2]:PUR[1],Math.min(.7,a*1.6),.7);
      if(r<30)p.tint(x,y,BLK,(1-r/30)*.7,.8)}
    // pinpoint stars (pink), twinkling
    for(const s of STARS){const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.75?PINK[4]:v>0?PINK[3]:PINK[0],v>0?1:.8)}
    for(const T of TEN)tendril(p,T,t);
    // eye glow and pinpoint halo
    if(o>0)for(let y=EY-40;y<=EY+40;y++)for(let x=EX-60;x<=EX+60;x++){const d=Math.hypot((x-EX)/60,(y-EY)/30);if(d<1)p.tint(x,y,PINK[1],Math.pow(1-d,2)*.35*o,.5)}
    for(const h of HALO){const v=Math.sin(TAU*(h.k*t+h.ph));const a=(.18+.82*o)*(v>.3?1:.55);if(a>.3||v>.3)p.put(h.x,h.y,v>.6&&o>.5?PINK[4]:o>.3?PINK[3]:PINK[1],o>.05?1:.55)}
    // the eye: almond lid, sclera, iris, slit pupil
    for(let x=-EW;x<=EW;x++){const q=1-Math.pow(x/EW,2),xx=EX+x;
      if(o<.04){const ly=Math.round(3*q);if(dith(xx,EY,.55)){p.put(xx,EY-ly,PUR[2],.8);p.put(xx,EY+ly,PUR[1],.8)}continue}
      const lid=14*Math.pow(q,.9)*o;
      for(let y=-Math.ceil(lid);y<=Math.ceil(lid);y++){if(Math.abs(y)>lid)continue;
        const ix=x-3*Math.sin(TAU*t),ir=Math.hypot(ix,y*1.15),pr=Math.hypot(ix/2.1,y/(9*Math.max(.3,o)));
        let col=BLK;
        if(ir<9.5){col=ir>8?PINK[0]:ir>5.5?PINK[2]:PINK[3];if(ir<6.5&&Math.abs(ix)<4&&y<0&&ir>3)col=PINK[4]}
        if(pr<1)col=BLK;
        if(ir>=9.5)col=ramp([BLK,PUR[0]],.4-.4*Math.abs(y)/Math.max(1,lid),xx,EY+y);
        p.put(xx,EY+y,col)}
      const ly=Math.round(lid);p.put(xx,EY-ly,o>.5?PINK[3]:PINK[2]);p.put(xx,EY+ly,PINK[1]);if(ly>0)p.dput(xx,EY-ly-1,PINK[1],.6)}
    if(o>.15){p.put(EX-EW-1,EY,PINK[2]);p.put(EX+EW+1,EY,PINK[2]);p.put(EX-3-3*Math.sin(TAU*t),EY-4,WHITE)}
    emberDraw(p,WISP,t,-5,[PINK[4],PINK[3],PUR[4],PUR[3]]);
  }
  self.draw=draw;return TBG.add(self);
})();
