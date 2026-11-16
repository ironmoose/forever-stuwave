/* MAGE: Arcane (turning rune circle in a starfield), Fire (rolling inferno sky over lava veins), Frost (blizzard in an ice cave). */
/* ================================== ARCANE: rune circle in a starfield ================================== */
(()=>{
  const self={cls:'MAGE',tree:1,id:'mage_arcane',name:'ARCANE'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0418','#12083a','#1c0c52','#2a1170']);
  const VI=c.ramp(['#1c0c52','#34188a','#4a1f9a','#6d32c8','#8a44e0','#a855f7','#d0a8ff']);
  const CY=c.ramp(['#0a3a5a','#0e6a8a','#14a8c8','#22e0ff','#b8f8ff']);
  const STAR=['#3a2a78','#7a7ad0','#e0e6ff'].map(c);
  const CX=78,CYC=98,R=72,K=.5,ISY=166;
  const line=(p,x0,y0,x1,y1,col,a)=>{const n=Math.max(Math.abs(x1-x0),Math.abs(y1-y0),1);for(let i=0;i<=n;i++)p.put(Math.round(x0+(x1-x0)*i/n),Math.round(y0+(y1-y0)*i/n),col,a)};
  const SIL=c('#07030e'),DK=c('#12082a'),RIM=c('#2a1850');
  const SHARDS=[[26,176,5,0],[132,168,4,.3],[46,206,4,.6],[116,204,6,.15],[14,138,3,.8],[146,132,3,.45]];
  const STARS=[];{const r=rng(8);for(let i=0;i<34;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*230),ph:r(),k:1+fl(r()*2)})}
  const GL=[[[0,-3,0,3],[0,0,3,-3]],[[-3,-3,3,-3],[0,-3,0,3]],[[-3,3,0,-3],[0,-3,3,3],[-2,1,2,1]],[[0,-3,3,0],[3,0,0,3],[0,3,-3,0],[-3,0,0,-3]]];
  const MOTES=[];{const r=rng(31);for(let i=0;i<18;i++)MOTES.push({r:30+r()*66,k:i%3===0?-1:1,ph:r(),inc:.1+r()*.55,cy:i%2,big:r()>.7,dy:(r()-.5)*14})}
  const RISE=emberList(41,16,150,166,40,95,.5,.9).map(e=>Object.assign(e,{x:CX-56+e.x/W*112}));
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const neb=tnoise(x/24,y/13,8,20,3),band=Math.exp(-Math.pow((x-78+(y-118)*.55)/38,2));
      p.put(x,y,ramp(SKY,.08+.16*neb+.3*band*neb,x,y))}
    for(const s of STARS)p.put(s.x,s.y,STAR[0]);
    // distant tower on a far rock, right side
    for(let y=190;y<=222;y++)for(let x=116;x<=120;x++)p.put(x,y,DK);
    for(let k=0;k<7;k++){const hw=3-Math.floor(k*.45);for(let x=118-hw;x<=118+hw;x++)p.put(x,189-k,DK)}
    for(let x=110;x<=126;x++){const d=Math.abs(x-118);for(let y=222;y<=222+Math.floor(d*.35);y++)p.put(x,y,DK)}
    for(let y=190;y<=222;y+=3)p.put(120,y,RIM);
    self.base=p;
  }
  function island(p,t,cy){
    const ib=Math.round(1.6*Math.sin(TAU*t+2)),y0=ISY+ib,rx=40,ry=8;
    for(let y=y0-ry;y<=y0+56;y++){const u=(y-y0)/56;
      const hw=y<y0?rx*Math.sqrt(Math.max(0,1-Math.pow((y-y0)/ry,2))):rx*Math.pow(Math.max(0,1-u),.75)*(1+.12*(vn(y,3,4)-.5))-1;
      for(let x=Math.ceil(CX-hw);x<=CX+hw;x++){
        const top=y<y0,e=x<=CX-hw+1.2||x>=CX+hw-1.2;
        if(top){const d=Math.pow((x-CX)/rx,2)+Math.pow((y-y0)/ry,2);p.put(x,y,d>.82?VI[3]:SIL);continue}
        p.put(x,y,e&&x<CX?VI[4]:e?VI[2]:(y>y0+28||h2(x,y,5)>.8?(h2(x,y,5)>.9?SIL:DK):RIM))}}
    for(let x=CX-rx;x<=CX+rx;x++){const q=(x-CX)/rx,yy=y0+Math.round(ry*Math.sqrt(Math.max(0,1-q*q)));p.put(x,yy,VI[4])}
    const pu=.5+.5*Math.sin(TAU*t*2);
    for(let y=y0-ry;y<=y0+ry;y++)for(let x=CX-rx;x<=CX+rx;x++){const d=Math.pow((x-CX)/(rx*.8),2)+Math.pow((y-y0)/(ry*.8),2);if(d<1)p.tint(x,y,CY[2],(1-d)*(.5+.25*pu),.65)}
    for(let i=0;i<60;i++){const a=TAU*i/60;p.put(CX+26*Math.cos(a),y0+5.2*Math.sin(a),i%2?CY[3]:VI[5])}
    for(let i=0;i<30;i++){const a=TAU*i/30;p.put(CX+14*Math.cos(a),y0+2.8*Math.sin(a),CY[3])}
  }
  function shard(p,x,y,sz){
    for(let k=-sz;k<=sz;k++){const hw=Math.round((sz-Math.abs(k)*.9)*1.1);for(let i=-hw;i<=hw;i++)p.put(x+i,y+k,i===-hw&&hw>0?VI[4]:i===hw&&hw>1?VI[2]:SIL)}}
  function ellipse(p,cx,cy,r,front,back,step){
    const n=Math.ceil(TAU*r*1.3);for(let i=0;i<n;i++){if(step&&(i%step)>=step*.55)continue;const a=TAU*i/n,s=Math.sin(a);p.put(cx+r*Math.cos(a),cy+r*K*s,s>0?front:back)}}
  function draw(p,f,N){
    const t=f/N,cy=CYC+Math.round(1.6*Math.sin(TAU*t)),pr=(a,r,z)=>[CX+r*Math.cos(a),cy+(z||0)+r*K*Math.sin(a)];
    // light shaft under the floating disc
    for(let y=cy+22;y<ISY;y++){const u=(y-cy-22)/(ISY-cy-22),hw=50-10*u;
      for(let x=CX-hw;x<=CX+hw;x++){const e=1-Math.abs(x-CX)/hw;p.tint(x,y,VI[2],Math.min(1,e*1.4)*(.3+.3*u),.7);if(e>.6)p.dput(x,y,CY[1],(e-.6)*.7*(.4+.6*u))}}
    island(p,t,cy);for(const[sx,sy,sz,ph]of SHARDS)shard(p,sx,sy+Math.round(2*Math.sin(TAU*(t+ph))),sz);
    // twinkling stars
    for(const s of STARS){const v=Math.sin(TAU*(s.k*t+s.ph));if(v>.78)p.put(s.x,s.y,STAR[2]);else if(v>.05)p.put(s.x,s.y,STAR[1])}
    // disc body
    for(let y=cy-fl(R*K);y<=cy+R*K;y++)for(let x=CX-R;x<=CX+R;x++){const d=Math.pow((x-CX)/R,2)+Math.pow((y-cy)/(R*K),2);if(d<1)p.tint(x,y,SKY[0],.7+.2*(1-d),.9)}
    for(let y=cy-fl(R*K);y<=cy+R*K;y++)for(let x=CX-R;x<=CX+R;x++){const d=Math.pow((x-CX)/R,2)+Math.pow((y-cy)/(R*K),2);if(d<1&&d>.18)p.dput(x,y,VI[1],.2+.25*(1-d))}
    const back=MOTES.filter(m=>Math.sin(TAU*(m.k*t+m.ph))<=0);
    mote(p,back,t,cy,false);
    ellipse(p,CX,cy,R,VI[5],VI[3]);ellipse(p,CX,cy,R-2,VI[3],VI[1]);
    ellipse(p,CX,cy,R-8,VI[4],VI[2],2);
    ellipse(p,CX,cy,60,VI[4],VI[2]);ellipse(p,CX,cy,46,VI[4],VI[2]);ellipse(p,CX,cy,24,VI[5],VI[3]);
    // tick ring, one tick step per loop
    for(let i=0;i<48;i++){const a=TAU*(i/48+t/48),[x,y]=pr(a,R-4),s=Math.sin(a);p.put(x,y,s>0?VI[4]:VI[2])}
    // hexagram
    const rot=TAU*t/6-Math.PI/2;
    for(const o of [0,1]){const v=[0,1,2].map(i=>pr(rot+(o+2*i)*TAU/6,44));for(let i=0;i<3;i++){const a=v[i],b=v[(i+1)%3];line(p,a[0],a[1],b[0],b[1],VI[4])}}
    // sweep spoke and glyphs lighting in sequence
    const H0=TAU*t-Math.PI/2;
    {const a=pr(H0,24),b=pr(H0,60);for(let i=0;i<=24;i++)p.dput(a[0]+(b[0]-a[0])*i/24,a[1]+(b[1]-a[1])*i/24,CY[2],.55)}
    for(let i=0;i<24;i++){const a=TAU*(i/24+4/24*t),[gx,gy]=pr(a,53),d=frac((H0-a)/TAU),k=d<.3?1-d/.3:0,s=Math.sin(a);
      const col=k>.66?CY[4]:k>.33?CY[3]:k>0?CY[2]:s>0?VI[5]:VI[3];
      if(k>0)for(let dy=-4;dy<=4;dy++)for(let dx=-5;dx<=5;dx++)if(dx*dx+dy*dy*1.6<=22)p.tint(gx+dx,gy+dy,CY[1],k*.45*(1-(dx*dx+dy*dy)/30),.7);
      for(const[x0,y0,x1,y1]of GL[i%4])line(p,gx+x0,gy+Math.round(y0*.9),gx+x1,gy+Math.round(y1*.9),col)}
    // core
    const pu=.5+.5*Math.sin(TAU*t*2);
    for(let dy=-6;dy<=6;dy++)for(let dx=-8;dx<=8;dx++){const d=Math.hypot(dx,dy*1.8);if(d<8)p.tint(cx0(dx),cy+dy,CY[3],(1-d/8)*(.5+.3*pu),.8)}
    p.put(CX,cy,CY[4]);p.put(CX-1,cy,CY[3]);p.put(CX+1,cy,CY[3]);p.put(CX,cy-1,CY[3]);p.put(CX,cy+1,CY[3]);
    mote(p,MOTES.filter(m=>Math.sin(TAU*(m.k*t+m.ph))>0),t,cy,true);
    emberDraw(p,RISE,t,0,[CY[4],CY[3],VI[5],VI[3]]);
  }
  const cx0=dx=>CX+dx;
  function mote(p,list,t,cy,front){
    for(const m of list){const a0=TAU*(m.k*t+m.ph),cols=m.cy?[CY[4],CY[3],CY[2],CY[1]]:[VI[6],VI[5],VI[4],VI[3]];
      for(let j=4;j>=0;j--){const a=a0-m.k*j*.09,x=CX+m.r*Math.cos(a),y=cy+m.dy+m.r*m.inc*Math.sin(a);
        const col=cols[Math.min(3,j)];if(front||j>1)p.dput(x,y,col,front?1-j*.17:.6-j*.1);
        if(j===0&&m.big){p.put(x+1,y,cols[1],front?1:.6);p.put(x,y-1,cols[1],front?1:.6)}}}
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== FIRE: rolling inferno sky over lava veins ================================== */
(()=>{
  const self={cls:'MAGE',tree:2,id:'mage_fire',name:'FIRE'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKYF=c.ramp(['#12050a','#2a0e06','#4e1c06','#82300a','#bc500c','#e87012','#ff8a1c','#ffb62a','#ffd23f']);
  const ROCK=c.ramp(['#0a0406','#160808','#240e0a','#341610']);
  const VEIN=c.ramp(['#64200a','#b03a0a','#ff7a2a','#ffb02e','#ffd23f']);
  const RIV=[];{const xs=[-14,36,84,128,176];xs.forEach((x0,i)=>RIV.push({x0,hx:78+(i-2)*5,A:5+3*((i*7)%4),k:2.4+.5*i,ph:i*1.7,pp:i/5}))}
  const RV=new Float32Array(W*H),RP=new Float32Array(W*H),SPECK=[];
  const SIL=c('#07030a'),SMOKE=c('#12050a');
  const EMBC=['#ffd23f','#ffb02e','#ff7a2a','#b03a0a'].map(c);
  const HOR=156,VX=78,PEAK=76;
  const mask=new Uint8Array(W*H); // 1 sky, 2 ground, 0 silhouette
  const top=new Int16Array(W);
  
  const STREAMS=[[-1,.9,0],[1,1.1,.5],[0,.6,.25]];
  const EMB=emberList(7,44,110,236,60,130,.5,.9),SPK=emberList(12,16,PEAK+4,PEAK+14,40,90,.3,.55).map(e=>Object.assign(e,{x:VX-6+e.x/W*12}));
  function build(){
    const p=new Px();
    for(let x=0;x<W;x++){const dx=Math.abs(x-VX),cone=(HOR-PEAK)*Math.pow(Math.max(0,1-dx/92),1.25);
      let y=HOR-cone+(dx<8?(8-dx)*.7-1:0)+fl(2*vn(x,6,3)*(dx<84?1:0));
      const far=HOR-8-9*vn(x,11,9)-5*vn(x+80,4,2);y=Math.min(y,far);top[x]=Math.round(y)}
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y>=HOR){mask[y*W+x]=2;p.put(x,y,ramp(ROCK,.15+.5*tnoise(x/6,y/4,26,60,6)+.15*(y-HOR)/(H-HOR),x,y))}
      else if(y>=top[x]){mask[y*W+x]=0;p.put(x,y,SIL)}else mask[y*W+x]=1}
    // lava rivers converging on the volcano, in perspective
    for(const rv of RIV)for(let y=HOR;y<H;y++){const u=Math.pow((y-HOR)/(H-HOR),1.25),cx=rv.hx+(rv.x0-rv.hx)*u+rv.A*u*Math.sin(u*rv.k*3+rv.ph)*(1-.3*u),w=.5+2.3*u;
      for(let x=Math.floor(cx-w-3);x<=cx+w+3;x++){if(x<0||x>=W)continue;const d=Math.abs(x-cx),v=d<=w?1:Math.max(0,1-(d-w)/3)*.5,i=y*W+x;
        if(v>RV[i]){RV[i]=v;RP[i]=rv.pp+u*.9}}}
    {const r=rng(19);for(let i=0;i<46;i++){const y=HOR+3+fl(r()*(H-HOR-4)),x=fl(r()*W);if(RV[y*W+x]<.3)SPECK.push({x,y,ph:r(),k:1+fl(r()*2)})}}
    // crater lip
    for(let x=VX-9;x<=VX+9;x++){const y=top[x];p.put(x,y,VEIN[1]);if(Math.abs(x-VX)<5)p.put(x,y+1,VEIN[2])}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,a=TAU*t;
    for(let y=0;y<HOR;y++){const hz=Math.pow(clamp((y-50)/(HOR-50)),1.5);
      for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
        const A=tnoise(x/40+.8*Math.cos(a),y/13+.8*Math.sin(a),8,40,1),B=tnoise((x+156*t)/13,y/8+.4*Math.sin(a+1),12,40,2),C=tnoise(x/20-.7*Math.cos(a+2),y/9+.7*Math.sin(a+2),16,40,3);
        const n=.55*A+.25*B+.2*C,I=.1+.62*hz+(clamp((n-.3)*1.5)-.5)*.5*(.35+.65*hz);
        p.put(x,y,ramp(SKYF,clamp(I),x,y,2))}}
    // smoke column over the crater
    for(let y=0;y<PEAK;y++){const u=(PEAK-y)/PEAK,hw=10+u*30;for(let x=VX-hw;x<=VX+hw;x++){if(x<0||x>=W||mask[y*W+fl(x)]!==1)continue;
      const e=1-Math.abs(x-VX)/hw,n=tnoise((x+30*t)/5,(y+60*t)/6,12,20,8);const v=(n-.38)*e*2.2;if(v>0)p.tint(x,y,SMOKE,Math.min(1,v)*.9,.8)}}
    // lava rivers: glow pulses and cools as it flows toward the viewer
    for(let y=HOR;y<H;y++){const dp=(y-HOR)/(H-HOR);for(let x=0;x<W;x++){const v=RV[y*W+x];if(v<=0)continue;
      const b=.5+.5*Math.sin(TAU*(t-RP[y*W+x]*1.1)),cr=tnoise(x/4,y/3,40,80,6);
      if(v>=1){const I=clamp((.2+.45*b+.1*dp)*(cr>.72?.55:1));p.put(x,y,ramp(VEIN,I,x,y))}
      else p.tint(x,y,VEIN[0],v*.9*(.35+.65*b),.55)}}
    for(const q of SPECK){const v=Math.sin(TAU*(q.k*t+q.ph));if(v>.6)p.put(q.x,q.y,v>.9?VEIN[3]:VEIN[2])}
    // heat shimmer: whole rows slide sideways
    for(let y=104;y<HOR+40;y++){const amp=y<HOR?Math.pow((y-104)/(HOR-104),1.2)*2.6:2.6*(1-(y-HOR)/40),dx=Math.round(amp*Math.sin(TAU*(2*t-y*.055)));if(!dx)continue;
      const row=[];for(let x=0;x<W;x++){const i=(y*W+x)<<2;row.push(p.d[i],p.d[i+1],p.d[i+2])}
      for(let x=0;x<W;x++){const s=((x-dx)%W+W)%W*3,i=(y*W+x)<<2;p.d[i]=row[s];p.d[i+1]=row[s+1];p.d[i+2]=row[s+2]}}
    // glowing shimmer streaks above the horizon
    for(let k=0;k<9;k++){const y=112+k*5+(k%2),x0=(k*47+fl(14*Math.sin(TAU*(t+k*.13))))%W,ln=10+(k*7)%14,u=(y-104)/52;
      for(let i=0;i<ln;i++){const x=(x0+i)%W;if(mask[y*W+x]===1)p.dput(x,y,SKYF[7],.3+.3*u*Math.sin(Math.PI*i/ln))}}
    // lava running down the cone
    for(const[dir,sp,ph]of STREAMS){let x=VX+dir*2;
      for(let k=0;k<(HOR-PEAK-6);k++){const y=top[Math.round(x)]+1+k*.0,yy=PEAK+4+k;if(yy>=HOR)break;x=VX+dir*(2+k*.42*sp)+1.2*Math.sin(k*.35+ph*6);
        if(mask[yy*W+Math.round(x)]!==0)continue;const b=.5+.5*Math.sin(TAU*(t-k*.02+ph));
        p.put(x,yy,VEIN[b>.7?3:b>.35?2:1],1-k/(HOR-PEAK)*.4)}}
    // crater glow
    const hb=.5+.5*Math.sin(TAU*t);
    for(let dy=-12;dy<=2;dy++)for(let dx=-16;dx<=16;dx++){const d=Math.hypot(dx,dy*1.6);if(d>=15)continue;const x=VX+dx,y=PEAK+3+dy;if(mask[y*W+x]===1)p.tint(x,y,SKYF[8],Math.pow(1-d/15,1.4)*(.45+.25*hb),.6)}
    for(let x=VX-4;x<=VX+4;x++)p.put(x,top[x],hb>.5?VEIN[4]:VEIN[3]);
    emberDraw(p,EMB,t,8,EMBC);emberDraw(p,SPK,t,0,[EMBC[0],EMBC[0],EMBC[1],EMBC[2]]);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== FROST: blizzard in an ice cave ================================== */
(()=>{
  const self={cls:'MAGE',tree:3,id:'mage_frost',name:'FROST'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKYB=c.ramp(['#05020c','#0a0a2c','#0e1448','#162466','#223a88']);
  const ROCK=c.ramp(['#05020c','#080618','#0c0a30','#121448','#1a2060']);
  const FLR=c.ramp(['#0a0820','#0e0e34','#141848','#1e2a82']);
  const ICE=c.ramp(['#0c0a30','#14185a','#1e2a82','#2e48b0','#4f8dff','#8fc8ff','#bfe9ff']);
  const AUR=c.ramp(['#0e1a58','#1450a0','#2a7ad0','#4faaf0','#8fdcff','#d8f6ff']);
  const GLT=c('#f2fdff'),RIDGE=c('#0e1448'),STAR=['#3a2a78','#7a7ad0','#e0e6ff'].map(c);
  const mask=new Uint8Array(W*H); // 1 open sky, 2 floor, 3 ridge, 0 rock or crystal
  const yTop=new Int16Array(W),flY=new Int16Array(W);
  const SPIKES=[[6,7,34],[18,5,16],[30,6,26],[44,5,12],[56,6,20],[68,4,10],[82,5,17],[96,6,24],[110,5,11],[122,7,30],[136,5,17],[148,6,28]];
  const CRY=[[11,40,8,48,-.2,.02],[25,30,6,30,.18,.4],[38,24,4,17,.3,.65],[124,26,5,22,-.25,.2],[140,40,8,50,.1,.55],[152,24,5,24,.2,.85],[66,8,3,9,0,.3],[92,10,4,12,.1,.75]];
  const CPIX=[],TIPS=[];
  const STARS=[];{const r=rng(5);for(let i=0;i<26;i++)STARS.push({x:20+fl(r()*116),y:6+fl(r()*160),ph:r(),k:1+fl(r()*2)})}
  const SNOW=[];{const r=rng(77);[[64,1,0],[40,2,1],[18,3,2]].forEach(([n,sp,l])=>{for(let i=0;i<n;i++)SNOW.push({x:r()*W,y:r()*H,sp,l})})}
  const SL=.55;
  function build(){
    const p=new Px();
    for(let x=0;x<W;x++){const u=(x-78)/68;let y=Math.abs(u)>=1?999:122-124*Math.sqrt(1-u*u);y+=3*vn(x,7,5);let s=0;
      for(const[xi,w,l]of SPIKES)s=Math.max(s,l*(1-Math.abs(x-xi)/w));yTop[x]=Math.min(999,Math.round(y+s));
      flY[x]=Math.round(196-10*Math.pow(Math.abs(x-78)/78,2)+3*vn(x,13,3))}
    const ridge=x=>Math.round(176-9*vn(x,17,6)-6*vn(x+50,6,8)-(h2(x,2,3)>.96?4:0));
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y>=flY[x]){mask[y*W+x]=2;p.put(x,y,ramp(FLR,.12+.45*tnoise(x/9,y/5,20,50,3)+(y-flY[x]<3?.3:0),x,y))}
      else if(y<yTop[x]){mask[y*W+x]=0;p.put(x,y,ramp(ROCK,.1+.5*tnoise(x/7,y/9,24,32,5)+.18*Math.exp(-Math.abs(x-78)/70),x,y))}
      else if(y>=ridge(x)){mask[y*W+x]=3;p.put(x,y,RIDGE)}
      else{mask[y*W+x]=1;p.put(x,y,ramp(SKYB,Math.pow(y/180,1.4)*.9,x,y))}}
    // ice rim along the cave mouth
    const sky=(x,y)=>x>=0&&y>=0&&x<W&&y<H&&mask[y*W+x]===1;
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==0)continue;
      if(sky(x-1,y)||sky(x+1,y)||sky(x,y+1)||sky(x,y-1))p.put(x,y,ICE[3]);
      else if(sky(x-2,y)||sky(x+2,y)||sky(x,y+2)||sky(x,y-2))p.dput(x,y,ICE[2],.7)}
    for(let x=0;x<W;x++)if(mask[flY[x]*W+x]===2){p.put(x,flY[x],ICE[3]);p.dput(x,flY[x]+1,ICE[2],.6)}
    for(const s of STARS)if(mask[s.y*W+s.x]===1)p.put(s.x,s.y,STAR[0]);
    // crystals
    for(const[cx,h0,w,h,lean,tg]of CRY){const yb=flY[cx]+3,px=[];
      for(let k=0;k<h;k++){const cw=k<h*.72?w:Math.max(1,Math.round(w*(1-(k-h*.72)/(h*.28)))),ox=Math.round(lean*k*.5);
        for(let i=0;i<cw;i++){const x=cx-(cw>>1)+i+ox,y=yb-k,q=i/Math.max(1,cw-1);
          p.put(x,y,i===0?ICE[5]:q<.45?ICE[4]:q<.75?ICE[3]:ICE[2]);mask[y*W+x]=0;px.push([x,y])}
        if(k===h-1)TIPS.push([cx+ox,yb-k,tg,px])}
      for(let k=2;k<h*.7;k+=1){const x=cx+Math.round(lean*k*.5);if(w>=5)p.put(x,yb-k,ICE[2])}}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,a=TAU*t;
    // aurora ribbon
    for(let x=0;x<W;x++){const yc=56+14*Math.sin(TAU*(x/78+t))+6*Math.sin(TAU*(x/31-2*t)),ray=tnoise(x/3.5+.8*Math.cos(a),.8*Math.sin(a),48,16,4);
      for(let y=Math.max(0,fl(yc-34));y<yc+8&&y<H;y++){if(mask[y*W+x]!==1)continue;const dy=y-yc,
        b=(dy>0?Math.max(0,1-dy/8):Math.max(0,1-(-dy)/34))*(.25+.9*ray)*(dy>0?1:Math.pow(1+dy/34,1.3));
        if(b>.08)p.put(x,y,ramp(AUR,clamp(b*.9),x,y),Math.min(1,b*2.2))}}
    // stars
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));if(v>.82)p.put(s.x,s.y,STAR[2]);else if(v>.1)p.put(s.x,s.y,STAR[1])}
    // blizzard haze streaks
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){const n=tnoise((x+SL*y+156*t)/19.5,y/70,8,4,9),v=n-.58;if(v>0)p.tint(x,y,ICE[2],Math.min(1,v*2.4)*.6,.6)}
    // crystal glints, one per crystal per loop
    for(const[x,y,tg,px]of TIPS){const u=frac(t-tg)/.16;if(u>=1)continue;const s=Math.sin(Math.PI*u),r=Math.round(1+4*s);
      for(const[qx,qy]of px)p.tint(qx,qy,ICE[6],s*.55,.55);
      for(let k=-r;k<=r;k++){const al=1-Math.abs(k)/(r+1);p.put(x+k,y-2,GLT,al);p.put(x,y-2+k,GLT,al)}
      if(r>2){p.put(x-1,y-3,ICE[6],.8);p.put(x+1,y-3,ICE[6],.8);p.put(x-1,y-1,ICE[6],.8);p.put(x+1,y-1,ICE[6],.8)}}
    // snow at three speeds
    for(const s of SNOW){const yw=((s.y+s.sp*H*t)%H+H)%H,len=s.l===0?1:s.l===1?3:6,al=s.l===0?.45:s.l===1?.7:.9,col=s.l===0?ICE[4]:s.l===1?ICE[5]:ICE[6];
      for(let k=0;k<len;k++){const yy=yw-k,x=(((s.x-SL*yy)%W)+W)%W;p.put(x,yy,col,k===0?al:al*.5*(1-k/len));if(s.l===2&&k<3)p.put(x+1,yy,col,.4)}}
  }
  self.draw=draw;return TBG.add(self);
})();
