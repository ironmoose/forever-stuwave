/* DRUID: Balance (eclipse over standing stones), Feral (dark jungle), Restoration (dawn grove). */
/* ================================== BALANCE: sun and moon trade places over a stone circle ================================== */
(()=>{
  const self={cls:'DRUID',tree:1,id:'druid_balance',name:'BALANCE'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0420','#12083a','#1a0c4a','#241060','#32187a']);
  const GOLD=c.ramp(['#6a4410','#a8701c','#d89a2a','#ffd23f','#fff0a0']);
  const BLUE=c.ramp(['#1e3a6a','#3a66a8','#6a9ad8','#9ad0ff','#e0f4ff']);
  const STAR=['#3a2a78','#7a7ad0','#e0e6ff'].map(c);
  const CR=c('#5a82bc'),FAR=c('#120a28'),FAR2=c('#0e0620'),STONE=c('#07030e'),GRS=c('#0a0418');
  const POOL=c.ramp(['#0a0420','#12083a','#1a0c4a']);
  const CX=78,CY=70,RX=60,RY=44,R0=21,SR=9,MR=8,HOR=168;
  const sx0=a=>CX+RX*Math.cos(a),sy0=a=>CY-RY*Math.sin(a)*1+14;
  const STARS=[];{const r=rng(31);for(let i=0;i<54;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*160),ph:r(),k:1+fl(r()*2)})}
  const MC=['#fff0a0','#ffd23f','#9ad0ff','#3a66a8'].map(c);
  const MOTE=emberList(7,30,150,225,60,120,.5,.9);
  const mask=new Uint8Array(W*H); // 1 sky, 0 silhouette
  const edges=[]; // stone edge pixels for rim light
  const RIDGE=[],RIDGE2=[];for(let x=0;x<W;x++){RIDGE.push(fl(HOR-6-14*Math.exp(-Math.pow((x-30)/40,2))-9*Math.exp(-Math.pow((x-130)/34,2))+3*vn(x,11,2)));RIDGE2.push(fl(HOR+2-3*vn(x,17,5)-2*vn(x,5,6)))}
  const STONES=[[14,44,7],[34,32,6],[57,38,7],[100,40,7],[122,30,6],[144,46,7],[78,52,9]]; // x, height, half width
  function stone(p,x,h,w,top){
    const y1=top;for(let y=y1-h;y<=y1;y++){const f=(y-(y1-h))/h,ww=Math.round(w*(.72+.28*f)),jag=y<y1-h+3?(h2(x,y,3)>.5?1:0):0;
      for(let dx=-ww+jag;dx<=ww;dx++){p.put(x+dx,y,STONE);mask[y*W+x+dx]=0;
        if(dx===-ww+jag)edges.push([x+dx,y,-1,0,x,y1-h/2]);else if(dx===ww)edges.push([x+dx,y,1,0,x,y1-h/2]);else if(y===y1-h+(dx<0?0:0)+jag&&dx>-ww+jag)edges.push([x+dx,y,0,-1,x,y1-h/2])}}}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){mask[y*W+x]=1;
      const n=tnoise(x/38,y/30,64,64,3)*.6+tnoise(x/14,y/11,64,64,4)*.4;
      const hz=Math.pow(clamp(y/HOR),2.2);
      p.put(x,y,ramp(SKY,clamp(.08+.38*n+.45*hz),x,y))}
    for(let x=0;x<W;x++){for(let y=RIDGE[x];y<H;y++){p.put(x,y,FAR);mask[y*W+x]=0}}
    for(let x=0;x<W;x++){const r=RIDGE2[x]+10;for(let y=r;y<H;y++){p.put(x,y,FAR2);mask[y*W+x]=0}}
    // stones standing on the near ridge, a trilithon in the middle
    const top=y=>y;
    for(const[x,h,w]of STONES.slice(0,6)){const ww=Math.min(w,5);stone(p,x,h,ww,RIDGE2[x]+9)}
    stone(p,70,34,4,RIDGE2[70]+9);stone(p,86,34,4,RIDGE2[86]+9);
    for(let x=64;x<=92;x++)for(let y=RIDGE2[70]+9-34-4;y<=RIDGE2[70]+9-34;y++){p.put(x,y,STONE);mask[y*W+x]=0;if(y===RIDGE2[70]+9-34-4)edges.push([x,y,0,-1,78,RIDGE2[70]+9-34])}
    for(let x=0;x<W;x++){const g=RIDGE2[x]+10+fl(2*vn(x,6,8));for(let y=g;y<H;y++){p.put(x,y,GRS);mask[y*W+x]=0}}
    for(let x=0;x<W;x+=1)if(h2(x,4,9)>.62){const g=RIDGE2[x]+9;p.put(x,g-1,GRS);mask[(g-1)*W+x]=0;if(h2(x,5,9)>.6){p.put(x,g-2,GRS);mask[(g-2)*W+x]=0}}
    self.base=p;
  }
  function glow(p,px,py,col,R,A){
    for(let y=fl(py-R);y<=py+R;y++)for(let x=fl(px-R);x<=px+R;x++){if(x<0||x>=W||y<0||y>=H||mask[y*W+x]!==1)continue;
      const d=Math.hypot(x-px,(y-py)*1.1);if(d>=R)continue;p.tint(x,y,col,Math.pow(1-d/R,1.6)*A,.5)}}
  function draw(p,f,N){
    const t=f/N,a=TAU*t;
    const sx=sx0(a),sy=sy0(a),mx=sx0(a+Math.PI),my=sy0(a+Math.PI);
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.85?STAR[2]:v>.05?STAR[1]:STAR[0])}
    // warm side and cool side of the sky
    glow(p,sx,sy,GOLD[0],105,.5);glow(p,mx,my,BLUE[0],95,.5);
    // trails along the arc
    for(let k=1;k<=16;k++){const q=a-k*.07,u=1-k/17;
      p.dput(sx0(q),sy0(q),GOLD[3],u*.8);p.dput(sx0(q+Math.PI),sy0(q+Math.PI),BLUE[3],u*.8)}
    // corona around the eclipse
    for(let k=0;k<16;k++){const q=TAU*(k/16+t*.125),L=k%2?5:11,s=Math.cos(q-a);
      for(let r=R0+3;r<R0+3+L;r++){p.dput(CX+r*Math.cos(q),CY-r*Math.sin(q),s>0?GOLD[3]:BLUE[3],.6*(1-(r-R0-3)/L))}}
    for(let dy=-R0-3;dy<=R0+3;dy++)for(let dx=-R0-3;dx<=R0+3;dx++){const d=Math.hypot(dx,dy);if(d>R0+2.2)continue;
      if(d<=R0-1.5){p.put(CX+dx,CY+dy,INKS_C[0]);continue}
      const s=Math.cos(Math.atan2(-dy,dx)-a),u=clamp(Math.abs(s)*1.1),th=d>R0-.2?1:.6;
      if(d>R0-1.5&&d<=R0+1.5||dith(CX+dx,CY+dy,th*u))p.put(CX+dx,CY+dy,s>0?ramp(GOLD,.35+.65*u,CX+dx,CY+dy):ramp(BLUE,.35+.65*u,CX+dx,CY+dy))}
    // sun
    for(let dy=-SR-5;dy<=SR+5;dy++)for(let dx=-SR-5;dx<=SR+5;dx++){const d=Math.hypot(dx,dy);
      if(d<=SR)p.put(sx+dx,sy+dy,ramp(GOLD,.4+.6*(1-d/SR),sx+dx,sy+dy));
      else if(d<=SR+5){const q=Math.atan2(dy,dx)+TAU*t*.5;if(Math.cos(q*6)>.5)p.dput(sx+dx,sy+dy,GOLD[3],.7*(1-(d-SR)/5))}}
    // moon with a shadowed limb
    for(let dy=-MR;dy<=MR;dy++)for(let dx=-MR;dx<=MR;dx++){const d=Math.hypot(dx,dy);if(d>MR)continue;
      const sh=Math.hypot(dx-3*Math.cos(a+Math.PI),dy+3*Math.sin(a+Math.PI));
      p.put(mx+dx,my+dy,ramp(BLUE,sh>MR*.92?.12:.45+.5*(1-d/MR),mx+dx,my+dy))}
    for(const[ox,oy]of[[-3,-2],[2,3],[3,-4],[-4,3]])p.put(mx+ox,my+oy,CR);
    // rim light on the stones from whichever body faces them
    for(const[x,y,nx,ny,cx,cy]of edges){
      const sd=Math.hypot(sx-cx,sy-cy),md=Math.hypot(mx-cx,my-cy);
      const ls=Math.max(0,(nx*(sx-cx)+ny*(sy-cy))/sd),lm=Math.max(0,(nx*(mx-cx)+ny*(my-cy))/md);
      const gs=ls*(1.3-sd/160),gm=lm*(1.3-md/160);
      if(gs>=gm&&gs>.25)p.put(x,y,ramp(GOLD,clamp(.3+gs*.7),x,y));else if(gm>.25)p.put(x,y,ramp(BLUE,clamp(.3+gm*.7),x,y))}
    // a still pool at the foot of the trilithon, mirroring both lights
    const PX=78,PY=206,PRX=40,PRY=11;
    for(let y=PY-PRY;y<=PY+PRY;y++)for(let x=PX-PRX;x<=PX+PRX;x++){const u=((x-PX)/PRX)**2+((y-PY)/PRY)**2;if(u>1)continue;
      p.put(x,y,ramp(POOL,u>.8?.1:.3+.4*(1-u),x,y));
      const rip=Math.sin(y*1.9-TAU*t*2+x*.2);
      const dg=Math.abs((x-PX)-(sx-CX)*.5),dm=Math.abs((x-PX)-(mx-CX)*.5);
      if(rip>.55){if(dg<14)p.dput(x,y,GOLD[2],(1-dg/14)*.7);if(dm<14)p.dput(x,y,BLUE[2],(1-dm/14)*.7)}}
    // ground mist drifting through the stones
    for(let y=165;y<200;y++)for(let x=0;x<W;x++){const d=tnoise((x+96*t)/16,y/5,6,64,12)-.55;if(d>0)p.tint(x,y,BLUE[0],d*2.4*(1-Math.abs(y-182)/20),.5)}
    // foreground grass blades swaying
    for(let i=0;i<60;i++){const x=1+i*2.6,y=fl(222+3*h2(i,2,3)),sw=Math.round(1.5*Math.sin(TAU*(t+i*.07))),hh=4+fl(h2(i,1,4)*8);
      for(let k=0;k<=hh;k++){p.put(x+Math.round(sw*k*k/(hh*hh)),y-k+10-fl(h2(i,3,5)*6),INKS_C[0])}}
    emberDraw(p,MOTE,t,8,MC);
  }
  const INKS_C=INKS.map(h=>hexc(h));
  self.draw=draw;return TBG.add(self);
})();

/* ================================== FERAL: dark jungle ================================== */
(()=>{
  const self={cls:'DRUID',tree:2,id:'druid_feral',name:'FERAL'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const JG=c.ramp(['#05020c','#050f0a','#0a1a12','#0e2418','#143222','#1c4430']);
  const MOSS=c.ramp(['#0e2418','#1a4a30','#2a7a4c','#2fbf7a','#7ae0a8']);
  const AMB=c.ramp(['#3a2008','#7a4a14','#c8801e','#ffb648','#ffd890']);
  const MOON=c.ramp(['#4a5a48','#8a9a80','#c0d0b0','#e8f0d8']),INK=c("#030a06"),LEAF=c("#030a06");
  const MOONX=112,MOONY=44,MR=12;
  const mask=new Uint8Array(W*H);
  const sil=(p,x,y,col)=>{p.put(x,y,col);if(x>=0&&x<W&&y>=0&&y<H)mask[fl(y)*W+fl(x)]=0};
  function blob(p,cx,cy,rx,ry,rot,col,rim){const ca=Math.cos(rot),sa=Math.sin(rot);
    const ux=MOONX-cx,uy=MOONY-cy,ul=Math.hypot(ux,uy)||1,nx=ux/ul,ny=uy/ul;
    const inn=(x,y)=>{const dx=x-cx,dy=y-cy,u=dx*ca+dy*sa,v=-dx*sa+dy*ca;return (u*u)/(rx*rx)+(v*v)/(ry*ry)<=1};
    for(let y=fl(cy-rx-1);y<=cy+rx+1;y++)for(let x=fl(cx-rx-1);x<=cx+rx+1;x++){
      if(inn(x,y)){const edge=rim&&!inn(x+Math.round(nx*1.5),y+Math.round(ny*1.5));sil(p,x,y,edge&&h2(x,y,4)>.3?MOSS[2]:col)}}}
  const SWAY=[];{const r=rng(17);for(let i=0;i<9;i++)SWAY.push({x:8+i*17+fl(r()*8),len:12+fl(r()*22),ph:r()})}
  const FERNS=[];{const r=rng(23);for(let i=0;i<22;i++)FERNS.push({x:r()*W,y:212+r()*24,h:10+fl(r()*16),ph:r(),d:r()>.5?1:-1})}
  const FF=emberList(9,26,60,215,18,42,.5,.9),FC=['#7ae0a8','#2fbf7a','#ffb648','#7a4a14'].map(c);
  const STR=[[34,84,52,150,0],[46,80,64,146,0],[58,78,76,142,0]];
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){mask[y*W+x]=1;
      const n=tnoise(x/30,y/24,64,64,5);p.put(x,y,ramp(JG,clamp(.2+.3*n+.15*(y/H)+.5*Math.exp(-Math.hypot(x-MOONX,(y-MOONY)*1.1)/34)),x,y))}
    // moon and its halo ring of rim light
    for(let dy=-MR;dy<=MR;dy++)for(let dx=-MR;dx<=MR;dx++){const d=Math.hypot(dx,dy);if(d>MR)continue;
      const sh=Math.hypot(dx+4,dy-3);let v=.25+.6*(1-sh/(MR*1.5));
      p.put(MOONX+dx,MOONY+dy,ramp(MOON,clamp(v*1.1,.2,.9),MOONX+dx,MOONY+dy))}
    // canopy mass
    const r=rng(61);
    for(let i=0;i<70;i++){const x=r()*W,y=r()*(18+60*Math.pow(r(),2))-2;
      if(Math.hypot(x-MOONX,y-MOONY)<MR+6&&r()<.8)continue;blob(p,x,y,8+r()*9,2.5+r()*3,(r()-.5)*1.8,LEAF,true)}
    for(let x=0;x<W;x++)for(let y=0;y<8;y++)if(Math.hypot(x-MOONX,y-MOONY)>MR+8)sil(p,x,y,LEAF);
    // trunks with moon rim on the right
    for(const[tx,w]of[[14,10],[142,12]]){for(let y=0;y<H;y++){const ww=w+Math.round(1.5*Math.sin(y/17));
      for(let x=tx-ww;x<=tx+ww;x++){sil(p,x,y,x>=tx+ww-1&&tx<MOONX?MOSS[1]:INK)}}}
    // vines
    {const rr=rng(77);for(let i=0;i<7;i++){const x0=30+fl(rr()*100);let x=x0;const L=30+fl(rr()*50);
      for(let k=0;k<L;k++){if(rr()<.2)x+=rr()<.5?-1:1;sil(p,x,8+k,INK)}}}
    // a low bush that holds the eyes
    blob(p,40,184,24,14,0,INK);blob(p,26,190,16,11,0,INK);blob(p,56,190,14,10,0,INK);
    for(let x=0;x<W;x++){const h=fl(214+5*vn(x,9,3));for(let y=h;y<H;y++)sil(p,x,y,INK)}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N;
    // moon glow, only on open pixels
    for(let y=MOONY-34;y<=MOONY+40;y++)for(let x=MOONX-38;x<=MOONX+38;x++){if(x<0||x>=W||y<0||y>=H||mask[y*W+x]!==1)continue;
      const d=Math.hypot(x-MOONX,y-MOONY);if(d<MR||d>38)continue;p.tint(x,y,MOSS[4],Math.pow(1-d/38,2)*.3*(1+.08*Math.sin(TAU*t)),.5)}
    // light shafts
    for(let y=20;y<200;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const u=x-(MOONX-(y-44)*.55);const w=Math.abs(((u+300)%34)-17);if(w<5){const a=(1-w/5)*.12*(1-y/220);p.tint(x,y,MOSS[2],a,.4)}}
    // mist drifting
    for(let y=130;y<226;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const d=tnoise((x+96*t)/16,y/6,6,64,9)-.58;if(d>0)p.tint(x,y,MOSS[1],d*2.4,.5)}
    // swaying leaf clusters hanging from the canopy
    for(const s of SWAY){for(let k=0;k<s.len;k++){const u=k/s.len,sx=Math.round(2.2*u*Math.sin(TAU*(t-u*.5+s.ph)));
      p.put(s.x+sx,10+k,LEAF);if(k%4===3){const d=k%8===3?-1:1;for(let m=1;m<=3;m++)p.put(s.x+sx+d*m,10+k+(m>1?1:0),LEAF)}}
      p.put(s.x+Math.round(2.2*Math.sin(TAU*(t-.5+s.ph))),10+s.len,MOSS[1])}
    // ferns
    for(const g of FERNS){const sw=Math.sin(TAU*(t+g.ph));for(let k=0;k<g.h;k++){const u=k/g.h,x=g.x+g.d*u*u*5+Math.round(2*u*sw);
      p.put(x,236-12-k+(g.y-212)*.2+8,INK);if(k>4&&k%3===0){p.put(x-1,236-12-k+(g.y-212)*.2+9,INK);p.put(x+1,236-12-k+(g.y-212)*.2+9,INK)}}}
    for(let i=0;i<10;i++){const x=6+i*15.5,sw=Math.round(1.6*Math.sin(TAU*(t+i*.13)));p.put(x+sw,213,MOSS[0]);p.put(x+sw+1,214,MOSS[0])}
    // claw marks: three slashes sweep in, glow amber, cool to moss, are gone by the wrap
    {const k=(t-.12)/.3;if(k>0)for(let i=0;i<3;i++){const[x0,y0,x1,y1]=STR[i],reveal=clamp(k*1.25-i*.12);const fade=t<.42?1:clamp(1-(t-.42)/.4);
      const n=70;for(let m=0;m<=n*reveal;m++){const u=m/n,w=Math.sin(Math.PI*u)*1.4+.3;
        const x=x0+(x1-x0)*u+3*Math.sin(u*2.5),y=y0+(y1-y0)*u;
        const hot=t<.3?1:clamp(1-(t-.3)/.3);
        for(let q=-1;q<=1;q++){if(Math.abs(q)>w)continue;const a=fade*(q===0?1:.55);
          p.dput(x+q,y,q===0?(hot>.5?AMB[4]:AMB[3]):(hot>.3?AMB[2]:MOSS[2]),a)}}}}
    // eyes
    {const bl=t>.56&&t<.62,ex=[34,46],ey=180;const pulse=.75+.25*Math.sin(TAU*t);
      for(const x of ex){for(let dy=-5;dy<=5;dy++)for(let dx=-6;dx<=6;dx++){const d=Math.hypot(dx,dy);if(d<6)p.tint(x+dx,ey+dy,AMB[1],(1-d/6)*.35*pulse,.4)}}
      for(const x of ex){if(bl){p.put(x-2,ey,AMB[1]);p.put(x-1,ey,AMB[1]);p.put(x,ey,AMB[1]);p.put(x+1,ey,AMB[1])}
        else{p.put(x-2,ey-1,AMB[2]);p.put(x-1,ey-1,AMB[3]);p.put(x,ey-1,AMB[3]);p.put(x+1,ey-1,AMB[2]);
          p.put(x-2,ey,AMB[3]);p.put(x-1,ey,AMB[4]);p.put(x,ey,AMB[4]);p.put(x+1,ey,AMB[3]);
          p.put(x-1,ey+1,AMB[2]);p.put(x,ey+1,AMB[2]);p.put(x-1,ey,INK);p.put(x,ey-1,INK)}}}
    emberDraw(p,FF,t,6,FC);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== RESTORATION: dawn grove ================================== */
(()=>{
  const self={cls:'DRUID',tree:3,id:'druid_restoration',name:'RESTORATION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const DAWN=c.ramp(['#12083a','#1c1038','#2a1850','#40205e','#5e2a6e','#8a3a78','#b84a80','#d86a90']);
  const MINT=c.ramp(['#0a2a28','#0e4a3a','#1a7a5a','#2ad090','#43ffb4','#b8ffe0']);
  const PINK=c.ramp(['#3a1244','#6a2060','#a8347a','#ff8ac8','#ffd0e8']);
  const TRUNK=c('#07030e'),BARK=c('#120a28'),FARC=c('#2a1850'),FARD=c('#1c1038');
  const WEB=c('#a898e8'),WEBD=c('#5a4aa8'),DEW=c('#e0fff0');
  const mask=new Uint8Array(W*H);
  const sil=(p,x,y,col)=>{x=fl(x);y=fl(y);if(x<0||x>=W||y<0||y>=H)return;p.put(x,y,col);mask[y*W+x]=0};
  const SUNX=84,SUNY=170,HOR=186;
  const WX=80,WY=92,SPOKES=10,RINGS=[7,14,22,30,39];
  const BL={x0:6,y0:80,cx:28,cy:18,x1:68,y1:28},BR={x0:150,y0:74,cx:132,cy:10,x1:96,y1:22};
  const SPORE=[];{const r=rng(11);for(let i=0;i<34;i++)SPORE.push({x:r()*W,y:90+r()*146,D:80+r()*110,lf:.55+r()*.35,ph:r(),A:4+r()*8,k:1+fl(r()*2),petal:i%3!==2,s:r()})}
  const VIN=[{x:44,y:40,len:34,ph:.1},{x:118,y:30,len:44,ph:.5},{x:30,y:46,len:22,ph:.8},{x:132,y:36,len:28,ph:.3}];
  const LEAVES=[];{const r=rng(41);const pts=[];
    for(const B of[BL,BR])for(let i=0;i<=1;i+=.07){const u=i,x=(1-u)*(1-u)*B.x0+2*(1-u)*u*B.cx+u*u*B.x1,y=(1-u)*(1-u)*B.y0+2*(1-u)*u*B.cy+u*u*B.y1;pts.push([x,y])}
    for(const[x,y]of pts)for(let k=0;k<2;k++)LEAVES.push({x:x+(r()-.5)*14,y:y+(r()-.3)*14,rx:4+r()*5,ry:2+r()*3,rot:(r()-.5)*1.8})}
  function bez(p,B,r0,r1,col){const n=60;for(let i=0;i<=n;i++){const u=i/n,x=(1-u)*(1-u)*B.x0+2*(1-u)*u*B.cx+u*u*B.x1,y=(1-u)*(1-u)*B.y0+2*(1-u)*u*B.cy+u*u*B.y1,r=r0+(r1-r0)*u;
    for(let dy=-r;dy<=r;dy++)for(let dx=-r;dx<=r;dx++)if(dx*dx+dy*dy<=r*r)sil(p,x+dx,y+dy,col)}}
  function leaf(p,l,rim){const ca=Math.cos(l.rot),sa=Math.sin(l.rot);
    for(let y=fl(l.y-l.rx-1);y<=l.y+l.rx+1;y++)for(let x=fl(l.x-l.rx-1);x<=l.x+l.rx+1;x++){const dx=x-l.x,dy=y-l.y,u=dx*ca+dy*sa,v=-dx*sa+dy*ca;
      if(u*u/(l.rx*l.rx)+v*v/(l.ry*l.ry)<=1){const toward=((u+1.6*ca*0)-1)*0;const e=(u*u/(l.rx*l.rx)+(v+1.6)*(v+1.6)/(l.ry*l.ry))>1&&v<0;sil(p,x,y,e&&h2(x,y,2)>.35?rim:TRUNK)}}}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){mask[y*W+x]=1;
      const d=Math.hypot((x-SUNX)/1.15,(y-SUNY)*1.05),v=Math.exp(-d/78);
      p.put(x,y,ramp(DAWN,clamp(.07+.2*(1-y/H)*.4+.92*v+.05*tnoise(x/26,y/18,64,64,2)),x,y))}
    // sun low behind the trees
    for(let dy=-13;dy<=13;dy++)for(let dx=-13;dx<=13;dx++){const d=Math.hypot(dx,dy);if(d>12.5||SUNY+dy>=HOR)continue;p.put(SUNX+dx,SUNY+dy,ramp(PINK,.62+.38*(1-d/12.5),SUNX+dx,SUNY+dy))}
    // distant tree line (two layers)
    for(let x=0;x<W;x++){let h=0;for(const[cx,w,hh]of[[10,14,40],[30,10,24],[52,12,30],[110,12,28],[130,10,36],[148,12,26]]){const v=hh*(1-Math.abs(x-cx)/w);if(v>h)h=v}
      const y=HOR-4-Math.max(h*.6,6+4*vn(x,9,3));for(let yy=fl(y);yy<H;yy++)sil(p,x,yy,FARC)}
    for(let x=0;x<W;x++){const y=HOR+3-5*vn(x,13,4)-2*vn(x,5,5);for(let yy=fl(y);yy<H;yy++)sil(p,x,yy,FARD)}
    // near ground
    for(let x=0;x<W;x++){const g=fl(206+4*vn(x,19,6)+2*vn(x,6,7));for(let y=g;y<H;y++)sil(p,x,y,TRUNK);p.put(x,g,BARK)}
    // branches and leaf crowns
    bez(p,BL,5,2,TRUNK);bez(p,BR,5,2,TRUNK);
    // framing trunks with flared roots
    for(let y=0;y<H;y++){const fr=Math.max(0,(y-176)*.45),w1=Math.round(1+2*Math.sin(y/14)+fr*.8),w2=Math.round(1+2*Math.sin(y/12+2)+fr*.8);
      for(let x=0;x<=w1+10;x++)if(x<=w1+9+(y>150?0:0)&&x<=w1+8)sil(p,x,y,x>=w1+7?BARK:TRUNK);
      for(let x=W-1-w2-8;x<W;x++)sil(p,x,y,x<=W-w2-9?BARK:TRUNK)}
    for(const l of LEAVES)leaf(p,l,MINT[1]);
    // roots and tufts
    for(const[x0,d]of[[22,1],[130,-1],[34,1],[118,-1]]){for(let k=0;k<22;k++){const x=x0+d*k,y=204+k*.15-(k<4?k:4)*.0+ (k>14?(k-14)*.0:0);sil(p,x,y+2,TRUNK);sil(p,x,y+3,TRUNK)}}
    self.base=p;
  }
  function ln(p,x0,y0,x1,y1,col){const n=Math.max(1,Math.ceil(Math.hypot(x1-x0,y1-y0)));for(let i=0;i<=n;i++){const u=i/n;p.put(x0+(x1-x0)*u,y0+(y1-y0)*u,col)}}
  function draw(p,f,N){
    const t=f/N;
    // sun halo breathing
    for(let y=100;y<HOR;y++)for(let x=20;x<W-20;x++){if(mask[y*W+x]!==1)continue;const d=Math.hypot(x-SUNX,(y-SUNY)*1.2);if(d>50)continue;p.tint(x,y,PINK[3],Math.pow(1-d/50,2)*.3*(1+.1*Math.sin(TAU*t)),.45)}
    // light shafts fanning up from the sun
    for(let y=0;y<HOR;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const ang=Math.atan2(x-SUNX,SUNY-y),k=ang*9+.3*Math.sin(TAU*t),w=Math.abs(k-Math.round(k));
      if(w<.2){const a=(1-w/.2)*.16*(1-(SUNY-y)/230)*(.8+.2*Math.sin(TAU*(t+ang)));if(a>0)p.tint(x,y,MINT[5],a,.35)}}
    // the web: frame threads to the branches and trunks, spokes, rings
    const wob=r=>.8*Math.sin(TAU*t+r*.1);
    ln(p,68,28,WX+wob(40)-6,WY-39,WEBD);ln(p,96,22,WX+wob(40)+8,WY-38,WEBD);
    ln(p,24,104,WX-39+wob(39),WY+6,WEBD);ln(p,132,104,WX+39+wob(39),WY+6,WEBD);
    for(let s=0;s<SPOKES;s++){const q=TAU*s/SPOKES+.15;ln(p,WX,WY,WX+40*Math.cos(q)+wob(40),WY+40*Math.sin(q),WEBD)}
    for(const R of RINGS)for(let s=0;s<SPOKES;s++){const q0=TAU*s/SPOKES+.15,q1=TAU*(s+1)/SPOKES+.15,sag=-1.6*(R/39)+1.1*Math.sin(TAU*t+R*.2);
      const x0=WX+R*Math.cos(q0)+wob(R),y0=WY+R*Math.sin(q0),x1=WX+R*Math.cos(q1)+wob(R),y1=WY+R*Math.sin(q1),mx=(x0+x1)/2+sag*Math.cos((q0+q1)/2)*-1,my=(y0+y1)/2+sag*Math.sin((q0+q1)/2)*-1;
      ln(p,x0,y0,mx,my,WEB);ln(p,mx,my,x1,y1,WEB)}
    for(let ri=0;ri<RINGS.length;ri++){const R=RINGS[ri];for(let s=0;s<SPOKES;s++){const q=TAU*s/SPOKES+.15;
      const dx=WX+R*Math.cos(q)+wob(R),dy=WY+R*Math.sin(q),lit=Math.cos(q-TAU*t)*.5+.5;
      if(lit>.8){p.put(dx,dy,DEW);p.put(dx+1,dy,MINT[4]);p.put(dx,dy+1,MINT[4]);p.dput(dx-1,dy,MINT[3],.7);p.dput(dx,dy-1,MINT[3],.7)}
      else if(lit>.4){p.put(dx,dy,MINT[4]);p.put(dx,dy+1,MINT[2])}else if((ri+s)%2===0)p.put(dx,dy,MINT[3])}}
    // vines swaying from the branches
    for(const v of VIN){let px=v.x;for(let k=0;k<v.len;k++){const u=k/v.len,x=v.x+Math.round(3*u*Math.sin(TAU*(t-u*.4+v.ph)));
      p.put(x,v.y+k,MINT[1]);if(k%4===2){const d=(k>>2)%2?1:-1;p.put(x+d,v.y+k,MINT[2]);p.put(x+2*d,v.y+k+1,MINT[3])}px=x}
      p.put(px,v.y+v.len,MINT[4])}
    // rim light on the crowns facing the sun, stirring leaves
    for(const l of LEAVES){const sw=Math.sin(TAU*(t+l.x*.01));if(sw>.6)p.put(l.x+l.rx*.5,l.y-l.ry,MINT[3])}
    // ferns, flowers and grass on the ground
    for(let i=0;i<46;i++){const x=3+i*3.3,y=fl(206+4*vn(x,19,6)+2*vn(x,6,7)),sw=Math.round(1.5*Math.sin(TAU*(t+i*.11))),hh=4+fl(h2(i,1,3)*7);
      for(let k=1;k<=hh;k++){p.put(x+Math.round(sw*k/hh),y-k,TRUNK);if(k>2&&k%2===0&&i%2===0){p.put(x+Math.round(sw*k/hh)-1,y-k,TRUNK);p.put(x+Math.round(sw*k/hh)+1,y-k,TRUNK)}}
      if(i%4===1){const fx=x+sw,fy=y-hh-1;p.put(fx,fy,PINK[3]);p.put(fx+1,fy,PINK[2]);p.put(fx,fy-1,PINK[4])}
      if(i%7===3){p.put(x+sw,y-hh-1,MINT[4])}}
    // spores and petals in slow spirals through the light
    for(const e of SPORE){const age=frac(t-e.ph);if(age>=e.lf)continue;const u=age/e.lf;
      const ph=TAU*(e.k*u+e.s),x=e.x+e.A*Math.sin(ph),y=e.y-e.D*u+2*Math.cos(ph);
      const a=u<.15?u/.15:u>.6?(1-u)/.4:1,xx=((x%W)+W)%W;
      if(e.petal){p.dput(xx,y,u<.5?PINK[4]:PINK[3],a);p.dput(xx+1,y,PINK[2],a*.8);p.dput(xx,y+1,PINK[2],a*.6)}
      else{p.dput(xx,y,MINT[5],a);p.dput(xx+1,y,MINT[3],a*.5);p.dput(xx,y-1,MINT[3],a*.4)}}
  }
  self.draw=draw;return TBG.add(self);
})();
