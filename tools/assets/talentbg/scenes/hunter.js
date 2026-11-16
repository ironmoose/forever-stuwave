/* HUNTER: Beast Mastery (moonlit clearing), Marksmanship (cliff overlook at dusk), Survival (snare thicket at night). */
/* helpers shared by the three scenes below live inside each IIFE to keep every scene self-contained */

/* ================================== BEAST MASTERY: moonlit clearing ================================== */
(()=>{
  const self={cls:'HUNTER',tree:1,id:'hunter_beastmastery',name:'BEAST MASTERY'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#080418','#0c0630','#12083a','#1a0e4a','#241660','#2e1e70','#3a2a88']);
  const GRD=c.ramp(['#10343a','#0c2530','#081a24','#060e18','#05050e','#04020a']);
  const INK=c('#05020c'),FAR=c('#1c1038'),FAR2=c('#241660'),PINE=c('#07030e'),PRIM=c('#17603c'),PRIM2=c('#1f8a4f');
  const MOON=['#32327a','#4a4a9a','#7070c0','#a0a8e0'].map(c),CRAT=c('#2e2e78');
  const GL=['#0b2f25','#10432f','#17603c','#1f8a4f','#2fbf7a','#8affc8'].map(c);
  const AMB=['#7a4a14','#c98a2a','#ffb648','#ffe0a0'].map(c);
  const GRASS=c('#10432f'),GRASS2=c('#17603c'),BUSH=c('#04020a'),CLOUD=c('#2e1e70'),STAR=['#3a2a78','#7a7ad0','#e0e6ff'].map(c);
  const MX=100,MY=52,MR=17,P=98;
  const RIDGE=[],FARL=[];
  for(let x=0;x<W;x++){RIDGE.push(158+fl(5*vn(x,28,1)+2*vn(x+40,7,2)));FARL.push(134+fl(5*vn(x,19,3)))}
  const mask=new Uint8Array(W*H); // 1 = open sky
  const STARS=[];{const r=rng(8);for(let i=0;i<34;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*100),ph:r(),k:1+fl(r()*2)})}
  const FIRE=[];{const r=rng(71);for(let i=0;i<20;i++)FIRE.push({x:6+r()*144,y:i<5?96+r()*60:150+r()*76,ph1:r(),ph2:r(),k1:1+fl(r()*2),k2:1+fl(r()*2),ph:r(),kb:1+fl(r()*2),col:i%4===0?1:0,ax:2+r()*3,ay:2+r()*3})}
  const TUFTS=[];{const r=rng(14);for(let i=0;i<80;i++)TUFTS.push({x:2+fl(r()*152),y:172+fl(r()*62),ph:r(),h:4+fl(r()*5)})}
  const EYE={x:34,y:196};
  function pine(p,cx,base,h,w,col,m){
    for(let k=0;k<h;k++){const u=k/h,u2=(u*5)%1,hw=Math.round(w*u*(.55+.45*u2))+(k>h-3?0:0),y=base-h+k;
      for(let x=cx-hw;x<=cx+hw;x++){p.put(x,y,col);if(m&&x>=0&&x<W&&y>=0&&y<H)mask[y*W+x]=0}}
    for(let k=0;k<5;k++){p.put(cx,base+k,col);p.put(cx+1,base+k,col)}
  }
  function bush(p,cx,cy,rx,ry,seed){
    for(let y=cy-ry-2;y<=cy+ry;y++)for(let x=cx-rx-2;x<=cx+rx+2;x++){
      const d=Math.hypot((x-cx)/rx,(y-cy)/ry),n=h2(x,y,seed)*.35+tnoise(x/3,y/3,64,64,seed)*.3;
      if(d+n*.5<1.0)p.put(x,y,BUSH)}
  }
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){const r=RIDGE[x];
      if(y<r){const dm=Math.hypot(x-MX,(y-MY)*1.1),halo=Math.pow(clamp(1-dm/56),1.8)*.4;
        p.put(x,y,ramp(SKY,clamp(Math.pow(y/150,1.5)*.62+halo),x,y));mask[y*W+x]=1}
      else p.put(x,y,ramp(GRD,clamp(Math.pow((y-r)/(H-r),.7)*1.1+.1*(tnoise(x/9,y/5,100,100,6)-.5)),x,y))}
    // moon disc
    for(let dy=-MR;dy<=MR;dy++)for(let dx=-MR;dx<=MR;dx++){const d=Math.hypot(dx,dy);if(d>MR)continue;
      let v=.55-(dx+dy)/(2*MR)*.42+.1*(1-d/MR);
      const cr=tnoise(dx/4+9,dy/4+9,64,64,12);if(cr>.7)v-=.28;else if(cr>.62)v-=.1;
      p.put(MX+dx,MY+dy,ramp(MOON,clamp(v),MX+dx,MY+dy));mask[(MY+dy)*W+MX+dx]=0}
    // distant pine line, a lighter tone than the pack so the wolves read darker
    for(let x=0;x<W;x++)for(let y=FARL[x];y<RIDGE[x];y++){p.put(x,y,FAR);mask[y*W+x]=0}
    {const r=rng(5);for(let x=2;x<W;x+=4+fl(r()*5)){const h=8+fl(r()*10);pine(p,x,FARL[x]+2,h,Math.round(h*.28),FAR,true)}}
    {const r=rng(6);for(let x=6;x<W;x+=9+fl(r()*8)){const h=6+fl(r()*6);pine(p,x,FARL[x]+2,h,Math.round(h*.3),FAR2,true)}}
    // ridge rim from moonlight
    for(let x=0;x<W;x++){p.put(x,RIDGE[x],ramp(GRD,.0,x,RIDGE[x]))}
    // big framing pines at the sides
    pine(p,10,166,118,24,PINE,true);pine(p,25,172,70,14,PINE,true);pine(p,146,170,88,18,PINE,true);pine(p,132,176,46,10,PINE,true);
    for(let y=60;y<166;y++){const x=11;if(y%6===0)p.put(x-14+((y*7)%5),y,PRIM)}
    // eyes brush and foreground bushes
    bush(p,EYE.x,EYE.y,17,11,3);bush(p,8,222,20,14,4);bush(p,148,218,18,16,5);bush(p,92,236,40,9,6);
    // moonlit rim along the bush tops
    for(let x=0;x<W;x++)for(let y=170;y<H-1;y++){const a=p.d[(y*W+x)*4],b=p.d[((y+1)*W+x)*4];
      if(a<=6&&b<=6&&p.d[(y*W+x)*4+1]<=4&&y>0){const up=p.d[((y-1)*W+x)*4+1];if(up>4&&h2(x,y,9)>.6){p.put(x,y-1,GL[0]);}}}
    self.base=p;
  }
  const WS=1.7;
  function blk(p,x,y,dx,dy,col){const x0=fl(dx*WS),x1=fl((dx+1)*WS)-1,y0=fl(dy*WS),y1=fl((dy+1)*WS)-1;for(let j=y0;j<=y1;j++)for(let i=x0;i<=x1;i++)p.put(x+i,y+j,col)}
  function wolf(p,x,y,ph){
    const bob=Math.round(1.6*Math.abs(Math.sin(TAU*(ph*2+.15))));y-=bob;
    const body=[[-6,-6],[-5,-7],[-4,-7],[-3,-7],[-2,-7],[-1,-7],[0,-7],[1,-7],[2,-7],[3,-7],[-6,-5],[-5,-5],[-4,-5],[-3,-5],[-2,-5],[-1,-5],[0,-5],[1,-5],[2,-5],[3,-5],[4,-5],[-5,-4],[-4,-4],[-3,-4],[-2,-4],[-1,-4],[0,-4],[1,-4],[2,-4],[3,-4],[4,-4],[-3,-8],[-2,-8],[-1,-8],[0,-8],[1,-8],[2,-8],[3,-8],[4,-8],[4,-7],[4,-6],[5,-7],[5,-6],[5,-9],[6,-9],[5,-8],[6,-8],[6,-7],[7,-8],[7,-7],[8,-7],[9,-7],[9,-6],[8,-6],[6,-10],[8,-9],[-7,-7],[-8,-8],[-9,-8],[-10,-7],[-11,-7],[-6,-4]];
    for(const[dx,dy]of body)blk(p,x,y,dx,dy,INK);
    for(let dx=-3;dx<=3;dx++)for(let i=fl(dx*WS);i<fl((dx+1)*WS);i++)p.put(x+i,y+fl(-8*WS)-1,PRIM);
    p.put(x+fl(6*WS),y+fl(-11*WS),PRIM);p.put(x+fl(8*WS),y+fl(-10*WS),PRIM);p.put(x+fl(7*WS)+1,y+fl(-9*WS)+1,AMB[2]);
    const leg=(hx,phi)=>{const s=Math.sin(TAU*phi),co=Math.cos(TAU*phi),fx=hx+5*s,fy=-1-(co>.3?2*co:0);
      for(let k=0;k<=5;k++){const u=k/5,lx=(hx+(fx-hx)*u)*WS,ly=(-4+(fy+4)*u)*WS;p.put(x+lx,y+ly,INK);p.put(x+lx+1,y+ly,INK)}
      p.put(x+fx*WS+2,y+(fy+(co>.3?-1:0))*WS,INK)};
    leg(3,ph);leg(2,ph+.12);leg(-5,ph+.5);leg(-4,ph+.62);
  }
  function draw(p,f,N){
    const t=f/N,sh=P*t;
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.8?STAR[2]:v>.1?STAR[1]:STAR[0])}
    // slow cloud wisps, two periods scrolling right
    for(let y=14;y<128;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const d=tnoise((x-48*t)/16,y/4,3,64,3),m=tnoise(x/46,y/24,8,64,5),v=d*.7+m*.55-.68;if(v>0)p.tint(x,y,CLOUD,v*3,.7)}
    // hawk circling across the moon face
    {const a=TAU*t+.4,hx=MX-3+36*Math.cos(a),hy=MY-1+7*Math.sin(a),fw=Math.sin(TAU*5*t),up=fw>.2?2:fw<-.4?-1:0,x=Math.round(hx),y=Math.round(hy);
      p.put(x,y,INK);p.put(x,y+1,INK);p.put(x,y+2,INK);p.put(x-1,y+3,INK);p.put(x+1,y+3,INK);p.put(x,y-1,INK);
      for(let k=1;k<=8;k++){const dy=up===2?-Math.round(k*.6):up===-1?Math.round(k*.3):-Math.round(k*.1)+(k>5?1:0);p.put(x-k,y+dy,INK);p.put(x+k,y+dy,INK);if(k<7&&k>1){p.put(x-k,y+dy+1,INK);p.put(x+k,y+dy+1,INK)}if(k<5){p.put(x-k,y+dy+2,INK);p.put(x+k,y+dy+2,INK)}}p.put(x-1,y+4,INK);p.put(x,y+4,INK);p.put(x+1,y+4,INK);}
    // wolves loping right along the ridge: two per 98 px lattice, shifted one lattice per loop
    for(const[o,pho,sc]of [[6,0,1],[56,.37,1]])for(let k=-1;k<3;k++){
      const x=Math.round(o+k*P+sh);if(x<-14||x>W+14)continue;const gy=RIDGE[Math.min(W-1,Math.max(0,x))]+2;wolf(p,x,gy,4*t+pho)}
    // brush sway and grass
    for(const g of TUFTS){const sx=Math.round(1.4*Math.sin(TAU*(t+g.ph)));
      for(let k=1;k<=g.h;k++){const u=k/g.h;p.put(g.x+Math.round(sx*u*u*1.6),g.y-k,k>g.h-2?GRASS2:GRASS)}}
    // eyes in the brush: blink once per loop, a faint glow
    {const cl=t>.52&&t<.6,eg=Math.pow(.5+.5*Math.sin(TAU*t),2);
      if(!cl){p.put(EYE.x-3,EYE.y,AMB[2]);p.put(EYE.x+3,EYE.y,AMB[2]);p.put(EYE.x-3,EYE.y+1,AMB[0],.7);p.put(EYE.x+3,EYE.y+1,AMB[0],.7);
        p.dput(EYE.x-4,EYE.y,AMB[0],.5+.2*eg);p.dput(EYE.x+4,EYE.y,AMB[0],.5+.2*eg);p.put(EYE.x-3,EYE.y-1,AMB[3],t>.3&&t<.4?.9:0)}
      else{p.put(EYE.x-4,EYE.y,AMB[0]);p.put(EYE.x-3,EYE.y,AMB[0]);p.put(EYE.x+3,EYE.y,AMB[0]);p.put(EYE.x+4,EYE.y,AMB[0])}}
    // fireflies
    for(const fl2 of FIRE){const x=fl2.x+fl2.ax*Math.sin(TAU*(fl2.k1*t+fl2.ph1)),y=fl2.y+fl2.ay*Math.sin(TAU*(fl2.k2*t+fl2.ph2));
      const b=Math.pow(Math.max(0,Math.sin(TAU*(fl2.kb*t+fl2.ph))),3),col=fl2.col?AMB:GL;
      if(b<.08)continue;const ci=fl2.col?2:4;
      p.put(x,y,col[b>.55?(fl2.col?3:5):ci],b>.35?1:.6);
      if(b>.4){p.dput(x+1,y,col[ci],b*.7);p.dput(x-1,y,col[ci],b*.7);p.dput(x,y+1,col[ci],b*.7);p.dput(x,y-1,col[ci],b*.7)}
      if(b>.8){p.dput(x+2,y,col[ci-1],.5);p.dput(x-2,y,col[ci-1],.5)}}
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== MARKSMANSHIP: cliff overlook at dusk ================================== */
(()=>{
  const self={cls:'HUNTER',tree:2,id:'hunter_marksmanship',name:'MARKSMANSHIP'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0420','#12083a','#2a1850','#40205a','#66305a','#8a4048','#b0583c']);
  const V1=c('#3a2068'),V2=c('#2a1850'),V3=c('#1c1038'),V4=c('#120a28'),FLOOR=c.ramp(['#2a1850','#1c1038','#120a28','#0a0418']);
  const CY=['#0e5a70','#22e0ff'].map(c),AM=['#7a4a14','#c98a2a','#ffb648','#ffe8b0'].map(c),SUNC=['#a8442a','#c8643a','#e08a3a'].map(c);
  const CLIFF=c('#07030e'),CLIFFR=c('#4a2058'),GR=c('#2a1850'),GR2=c('#4a2058'),GR3=c('#b0583c'),RIV=c('#0e5a70');
  const CLD=c('#8a4048'),CLD2=c('#40205a'),STAR=['#3a2a78','#7a7ad0','#e0e6ff'].map(c);
  const HOR=124,SX=40,SY=124,SR=9,TX=118,TY=150;
  const RA=[],RB=[],RC=[],CL=[];
  for(let x=0;x<W;x++){RA.push(HOR+2-fl(4*vn(x,21,1)+2*vn(x,6,2)));RB.push(138-fl(6*vn(x+40,26,3)+2*vn(x,7,4)));RC.push(156-fl(5*vn(x+90,31,5)+2*vn(x,9,6)));
    CL.push(200-fl(5*vn(x,17,7)+2*vn(x,5,8)+(x>108?Math.min(20,(x-108)*.8)*(1-Math.max(0,(x-146))/12):0)+(x<18?(18-x)*.4:0)))}
  const mask=new Uint8Array(W*H); // 1 = open sky
  const STARS=[];{const r=rng(18);for(let i=0;i<24;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*60),ph:r(),k:1+fl(r()*2)})}
  const BL=[];for(let x=1;x<W;x+=2)BL.push({x,h:6+fl(h2(x,3,5)*8),ph:h2(x,4,5)});
  const MOTE=emberList(9,16,150,206,20,50,.6,.9);
  const sm=u=>{u=clamp(u);return u*u*(3-2*u)};
  // river: a faint winding line through the valley
  const RIVER=[];for(let y=130;y<=184;y++){const u=(y-130)/54;RIVER.push([Math.round(104-48*u+10*Math.sin(u*7)+4*Math.sin(u*17)),y])}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<RA[x]){const gx=Math.exp(-Math.pow((x-SX)/80,2));p.put(x,y,ramp(SKY,clamp(Math.pow(y/HOR,1.6)*(.5+.5*gx)),x,y));mask[y*W+x]=1}
      else if(y<RB[x])p.put(x,y,ramp([V1,V2],clamp((y-RA[x])/10),x,y));
      else if(y<RC[x])p.put(x,y,ramp([V2,V3],clamp((y-RB[x])/16),x,y));
      else p.put(x,y,ramp(FLOOR,clamp((y-RC[x])/50),x,y))}
    // low sun half behind the far ridge
    for(let dy=-SR;dy<=0;dy++)for(let dx=-SR;dx<=SR;dx++){if(dx*dx+dy*dy>SR*SR)continue;const x=SX+dx,y=SY+dy;if(y>=RA[x]-1)continue;
      p.put(x,y,SUNC[dy<-5?2:dy<-2?1:0]);mask[y*W+x]=0}
    // haze bands in the valley
    for(let y=126;y<200;y++)for(let x=0;x<W;x++){if(y>=CL[x])continue;const k=(h2(x,y,3)>.5?1:0);
      const hz=Math.exp(-Math.pow((y-150)/26,2))*.3*(.5+.5*tnoise(x/30,y/6,64,64,4));if(dith(x,y,hz))p.put(x,y,V1)}
    // river
    for(const[x,y]of RIVER){if(y<RC[x])continue;if(h2(x,y,6)>.35)p.put(x,y,RIV)}
    // valley relief: stepped mesas and tree speckle, each ridge a shade darker toward the viewer
    for(const[mx,mw,mh,col]of [[22,9,10,V2],[56,7,8,V2],[96,11,12,V2],[140,8,9,V2],[8,8,8,V3],[74,10,9,V3],[128,12,11,V3]]){const by=col===V2?RB[mx]+3:RC[mx]+3;
      for(let y=0;y<mh;y++){const hw=Math.round(mw*(.55+.45*Math.min(1,y/(mh*.5)))*(y<mh*.25?.6:1)),yy=by-y;for(let x=mx-hw;x<=mx+hw;x++)p.put(x,yy,col);if(y>mh*.2)p.put(mx-hw,yy,V1)}}
    for(let x=0;x<W;x++)for(let y=RC[x];y<RC[x]+14;y++){if(h2(x,y,13)>.86)p.put(x,y,V4)}
    // the crag with the glint on it: a lone spire with a lit shoulder
    for(let y=0;y<14;y++){const hw=y<3?1:y<8?2:3+((y-8)>>1);for(let x=-hw;x<=hw;x++)p.put(TX+x,TY-4+y,V4);if(y>2)p.put(TX-hw,TY-4+y,V1)}
    p.put(TX,TY-5,V4);p.put(TX+1,TY-6+0,V4)
    // cliff
    for(let x=0;x<W;x++)for(let y=CL[x];y<H;y++){p.put(x,y,CLIFF);if(y===CL[x]&&h2(x,y,2)>.45)p.put(x,y,CLIFFR);else if(y===CL[x]+1&&h2(x,y,5)>.8)p.put(x,y,GR2)}
    for(let y=206;y<H;y+=6)for(let x=0;x<W;x++){if(h2(x>>3,y,11)>.35&&(x+y)%3!==0)p.put(x,y+(h2(x,y,3)>.7?1:0),GR)}
    for(let y=CL[40];y<H;y++)if(y%5===0)for(let x=30;x<110;x++)if(h2(x,y,8)>.7)p.put(x,y+1,GR)
    // a lone pine framing the left edge
    for(let k=0;k<132;k++){const u=k/132,u2=(u*6)%1,hw=Math.round(17*u*(.5+.5*u2)),y=64+k;for(let x=6-hw;x<=6+hw;x++){p.put(x,y,CLIFF);if(x>=0&&x<W)mask[y*W+x]=0}}
    for(let y=190;y<H;y++){p.put(5,y,CLIFF);p.put(6,y,CLIFF);p.put(7,y,CLIFF)}
    self.base=p;
  }
  function ring(p,cx,cy,r,col,a){const n=Math.max(24,Math.round(r*7));for(let i=0;i<n;i++){const th=i*TAU/n;p.put(cx+Math.cos(th)*r,cy+Math.sin(th)*r,col,a)}}
  function line(p,x0,y0,x1,y1,col,a,gap){const n=Math.max(Math.abs(x1-x0),Math.abs(y1-y0));for(let i=0;i<=n;i++){if(gap&&i%gap===gap-1)continue;p.put(x0+(x1-x0)*i/n,y0+(y1-y0)*i/n,col,a)}}
  function draw(p,f,N){
    const t=f/N;
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.8?STAR[2]:v>.1?STAR[1]:STAR[0])}
    // dusk cloud bars drifting, warm underside near the horizon
    for(let y=22;y<118;y++){const fy=y/118;for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const d=tnoise((x+78*t)/13,y/3.2,6,64,3),m=tnoise(x/44,y/22,8,64,9),v=d*.7+m*.5-.7;if(v>0)p.tint(x,y,fy>.6?CLD:CLD2,v*3,.6)}}
    // sun glow on the haze
    for(let y=SY-30;y<SY+30;y++)for(let x=SX-60;x<SX+60;x++){if(x<0||x>=W||y<0)continue;const d=Math.hypot(x-SX,(y-SY)*1.5);if(d>=55)continue;
      const a=Math.pow(1-d/55,1.9)*.42*(1+.05*Math.sin(TAU*t));if(mask[y*W+x]===1)p.tint(x,y,SUNC[2],a,.5)}
    // bent grass along the ledge, a gust running left to right
    for(const g of BL){const base=CL[g.x]+1,gust=2.4+2.2*Math.sin(TAU*(t-g.x/90)),lean=gust*(g.h/8);
      for(let k=1;k<=g.h;k++){const u=k/g.h;p.put(g.x+Math.round(lean*u*u),base-k,k>g.h-2?(g.ph>.7?GR3:GR2):GR)}}
    for(const m of MOTE){const age=frac(t-m.ph);if(age>=m.lf)continue;const u=age/m.lf,x=((m.x+130*u+2*Math.sin(TAU*(m.k*u+m.sw)))%W+W)%W,y=m.y-m.D*u*.6,a=u<.15?u/.15:u>.6?(1-u)/.4:1;p.dput(x,y,AM[0],a*.8)}
    // scope ring: drifts over the valley, settles on the glint, fires once, drifts on
    const dx=78+34*Math.sin(TAU*t+.6),dy=156+14*Math.sin(TAU*2*t+1),w=sm((t-.3)/.2)*(1-sm((t-.78)/.14));
    const rc=t>=.7&&t<.78?(1-(t-.7)/.08):0;
    const cx=dx+(TX-dx)*w,cy=dy+(TY-dy)*w-3.5*rc,r=17-6*w+1.5*rc;
    const col=w>.9&&t<.72?AM[2]:CY[1],a=.5+.3*w;
    ring(p,cx,cy,r,col,a);ring(p,cx,cy,r-3,CY[0],.5);
    for(const[ax,ay]of [[1,0],[-1,0],[0,1],[0,-1]]){line(p,cx+ax*(r-3),cy+ay*(r-3),cx+ax*(r+4),cy+ay*(r+4),col,a);line(p,cx+ax*4,cy+ay*4,cx+ax*(r-4),cy+ay*(r-4),col,a*.55,2)}
    p.put(cx,cy,col,.9);
    // the glint builds, then the shot
    const g=sm((t-.38)/.3)*(t<.7?1:0);
    if(g>.05){const L=Math.round(1+4*g);for(let k=-L;k<=L;k++){const aa=1-Math.abs(k)/(L+1);p.put(TX+k,TY-1,AM[3],aa*g);p.put(TX,TY-1+k,AM[3],aa*g*.9)}p.put(TX,TY-1,AM[3])}
    const ag=(t-.7)*24;
    if(ag>=0&&ag<3){
      if(ag<1.5){line(p,6,214,TX,TY-1,AM[2],.8,ag<.9?0:3);line(p,6,213,TX,TY-2,AM[1],.4,2)}
      const k=ag<1?1:ag<2?.6:.3;
      for(let i=0;i<10;i++){const th=i*TAU/10+.3,rr=2+ag*2.4;p.dput(TX+Math.cos(th)*rr,TY-1+Math.sin(th)*rr*.7,AM[ag<1?3:2],k)}
      p.put(TX,TY-1,AM[3])}
    // muzzle flash at the ledge on the shot frame
    if(ag>=0&&ag<1){for(let i=0;i<6;i++)p.put(6+i,213-(i>>1),AM[3],1-i/7)}
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== SURVIVAL: snare thicket at night ================================== */
(()=>{
  const self={cls:'HUNTER',tree:3,id:'hunter_survival',name:'SURVIVAL'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const BGR=c.ramp(['#05020c','#07050f','#06120f','#091d18','#0d2b22','#14402f']);
  const TR=c.ramp(['#03080a','#06120f','#091d18','#0d2b22']);
  const FARC=c('#0d2b22'),MIDC=c('#06120f'),NEARC=c('#03080a'),MOSS=c('#1f6347'),MOSS2=c('#14402f');
  const GL=['#0d2b22','#14402f','#1f6347','#2f9468','#43ffb4','#b8ffe4'].map(c);
  const OR=['#7a3a14','#ff8a2a','#ffd27a','#fff0d0'].map(c);
  const ROPE=c('#5a4630'),ROPE2=c('#2e2418'),GLINT=c('#e8d49a'),STEEL=['#1c2a30','#3a525a','#7aa0a0'].map(c);
  const MISTC=c('#14402f'),FLOOR=c.ramp(['#0d2b22','#091d18','#06120f','#03080a']);
  const GROUND=176,TX=78,TY=210;
  const mask=new Uint8Array(W*H); // 0 = near silhouette (no mist), 1 = open
  const occ=new Uint8Array(W*H);
  const FAR=[],MID=[];
  {const r=rng(42);for(let x=6;x<W;x+=19+fl(r()*13))FAR.push({x,w:2+fl(r()*2),lean:(r()-.5)*.08,base:GROUND-2+fl(r()*4)});
   for(const x of [44,92,118])MID.push({x:x+fl(r()*6),w:7+fl(r()*3),lean:(r()-.5)*.08,base:GROUND+12+fl(r()*8)})}
  const NEAR=[{x:6,w:15,dir:1,lean:.06},{x:151,w:17,dir:-1,lean:-.07}];
  const WS=[[28,226],[128,229]];
  const RUNES=[{x:TX,y:TY+1,rx:38,k:.75,main:1},{x:26,y:192,rx:13,k:0},{x:128,y:186,rx:12,k:.25},{x:136,y:222,rx:10,k:.5}];
  const MOTE=emberList(31,26,172,232,24,60,.45,.85);
  const FERNS=[];{const r=rng(55);for(let i=0;i<16;i++){const x=i<8?2+i*3+fl(r()*6):i<12?130+(i-8)*7+fl(r()*5):44+fl(r()*60);FERNS.push({x,y:232+fl(r()*4),n:3+fl(r()*2),L:12+fl(r()*8),ph:r()})}}
  const CORDS=[{ax:34,ay:60,bx:TX-11,by:TY-11,w0:.2},{ax:126,ay:66,bx:TX+11,by:TY-11,w0:.55}];
  function trunkX(tr,y){return tr.x+tr.lean*(tr.base-y)*.5}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<GROUND){const d=Math.hypot(x-124,(y-14)*1.3),glow=Math.pow(clamp(1-d/80),2)*.22;
        p.put(x,y,ramp(BGR,clamp(.04+.24*(y/GROUND)+glow+.08*(tnoise(x/12,y/8,64,64,3)-.5)),x,y));mask[y*W+x]=1}
      else{p.put(x,y,ramp(FLOOR,clamp((y-GROUND)/(H-GROUND)*.95+.26*(tnoise(x/7,y/4,100,100,6)-.5)+.04),x,y));mask[y*W+x]=1}}
    // far trunks: thin and dim, they fade into the mist
    for(const tr of FAR)for(let y=30;y<tr.base;y++){const cx=trunkX(tr,y);for(let i=0;i<tr.w;i++)p.put(cx-tr.w/2+i,y,FARC)}
    // mid trunks
    for(const tr of MID){for(let y=0;y<tr.base;y++){const cx=trunkX(tr,y),w=tr.w+(y>tr.base-12?Math.round((y-(tr.base-12))*.4):0);
      for(let i=0;i<w;i++)p.put(Math.round(cx-w/2+i),y,MIDC);if(h2(tr.x,y,5)>.8)p.put(Math.round(cx-w/2),y,TR[3])}
      const r=rng(tr.x*7);for(let k=0;k<2;k++){const by=40+fl(r()*80),dir=k?1:-1;let bx=trunkX(tr,by);for(let i=0;i<10;i++){bx+=dir;p.put(bx,by-(i>>1),MIDC)}}}
    // dark canopy mass: leaf clusters, a gap near the moon glow at the upper right
    const cl=[];{const r=rng(77);
      for(let x=-4;x<W+6;x+=8+fl(r()*5)){const gap=x>108&&x<140;cl.push({x,y:(gap?-8:8)+r()*12,r:gap?5+r()*3:9+r()*6})}
      for(let x=0;x<W;x+=11+fl(r()*7)){if(x>110&&x<138)continue;cl.push({x,y:26+r()*14,r:5+r()*4})}
      for(let x=10;x<W;x+=26+fl(r()*10))cl.push({x,y:42+r()*8,r:3+r()*3})}
    for(const q of cl)for(let y=fl(q.y-q.r-2);y<=q.y+q.r+2;y++)for(let x=fl(q.x-q.r-2);x<=q.x+q.r+2;x++){if(x<0||x>=W||y<0||y>=H)continue;
      const dx=x-q.x,dy=y-q.y,d=Math.hypot(dx,dy*1.1)/q.r+.28*(h2(x,y,3)-.5);if(d>=1)continue;
      occ[y*W+x]=1;let col=TR[1];if(dx-dy>q.r*.3&&d>.3)col=TR[2];if(dx-dy>q.r*.8&&d>.55&&h2(x,y,6)>.35)col=TR[3];if(dx-dy<-q.r*.55&&d>.7)col=NEARC;if(d>.9)col=NEARC;p.put(x,y,col);mask[y*W+x]=0}
    // near trunks: wide and black, a moss rim on the inner edge, roots reaching onto the floor
    for(const tr of NEAR){const edge=[];
      for(let y=0;y<H;y++){const fy=Math.max(0,y-(H-44)),fw=Math.round(Math.pow(fy/44,2)*9),w=tr.w+fw+(h2(1,y,tr.x)>.85?1:0),cx=tr.x+tr.lean*(H-y)*.2,x0=Math.round(cx-w/2),x1=x0+w-1;
        for(let x=x0;x<=x1;x++){p.put(x,y,NEARC);if(x>=0&&x<W)mask[y*W+x]=0}
        const ix=tr.dir>0?x1:x0;edge.push([ix,y])}
      for(const[x,y]of edge){const dens=.55+.4*Math.sin(y/9+tr.x);if(h2(x,y,9)<dens*.7)p.put(x,y,MOSS2);if(h2(x,y,10)>.45)p.put(x-tr.dir,y,MOSS2);if(h2(x,y,11)>.8)p.put(x-2*tr.dir,y,MOSS2);if(h2(x,y,12)>.93){for(let k=0;k<3;k++)p.put(x-tr.dir*k,y,GL[2])}}
      for(let y=0;y<H;y+=1){const cx=tr.x+tr.lean*(H-y)*.2;for(const o of [-.25,.1,.32]){if(h2(fl(o*100),y>>2,tr.x)>.55)p.put(Math.round(cx+tr.w*o),y,TR[1])}}
      for(const rt of [[196,.8],[214,1.1]]){const[y0,sl]=rt;for(let i=0;i<34;i++){const x=Math.round(tr.x+tr.dir*(tr.w/2+i)),y=Math.round(y0+i*sl*.5+i*i/90),th=Math.max(1,3-fl(i/8));
        for(let k=0;k<th;k++){p.put(x,y+k,NEARC);if(x>=0&&x<W&&y+k<H)mask[(y+k)*W+x]=0}if(h2(i,y0,tr.x)>.4)p.put(x,y-1,MOSS2)}}}
    // jaw trap: dark plate, two open steel jaws with teeth, a chain to a spike
    for(let dy=-4;dy<=4;dy++)for(let dx=-15;dx<=15;dx++){if(Math.hypot(dx/15,dy/4.6)<=1)p.put(TX+dx,TY+dy+1,dy<0?STEEL[1]:STEEL[0])}
    for(let dx=-3;dx<=3;dx++){p.put(TX+dx,TY,STEEL[2]);p.put(TX+dx,TY+1,STEEL[1])}
    for(const sg of [-1,1])for(let i=0;i<=9;i++){const th=Math.PI+i*(Math.PI/2)/9,y=TY-1+11.5*Math.sin(th);
      const jx=sg<0?TX-5+8*Math.cos(th):TX+5-8*Math.cos(th);p.put(jx,y,STEEL[2]);p.put(jx+(sg<0?-1:1),y,STEEL[1]);p.put(jx+(sg<0?-2:2),y,STEEL[0]);if(i%2===0){p.put(jx+(sg<0?1:-1),y+.5,STEEL[2]);p.put(jx+(sg<0?2:-2),y+1,STEEL[2])}}
    for(let i=0;i<14;i++)if(i%2===0)p.put(TX+15+i,TY+4+(i>>2),STEEL[1]);
    for(let k=0;k<8;k++)p.put(TX+29,TY+6+k,NEARC),p.put(TX+30,TY+6+k,k===0?ROPE:NEARC);
    // wire stakes
    for(const[sx,sy]of WS)for(let k=0;k<9;k++){p.put(sx,sy-k+4,NEARC);p.put(sx+1,sy-k+4,k===8?ROPE:NEARC)}
    self.base=p;
  }
  function line(p,x0,y0,x1,y1,col,a){const n=Math.max(Math.abs(x1-x0),Math.abs(y1-y0));for(let i=0;i<=n;i++)p.put(x0+(x1-x0)*i/n,y0+(y1-y0)*i/n,col,a)}
  function pulse(u,wd){u=frac(u);return u<wd?Math.sin(Math.PI*u/wd):0}
  function rune(p,q,t){
    const b=pulse(t-q.k,q.main?.3:.26),a=.3+.7*b,ry=q.rx*(q.main?.34:.36),n=Math.round(q.rx*2.6);
    for(let i=0;i<n;i++){const th=i*TAU/n,x=q.x+Math.cos(th)*q.rx,y=q.y+Math.sin(th)*ry;p.put(x,y,b>.5?GL[4]:GL[3],.45+.5*a*(i%2?.6:1))}
    for(let i=0;i<n;i++){if(i%2)continue;const th=i*TAU/n,x=q.x+Math.cos(th)*(q.rx-4),y=q.y+Math.sin(th)*(ry-1.4);p.put(x,y,b>.4?GL[3]:GL[2],.4+.5*a)}
    for(let i=0;i<(q.main?12:8);i++){const m=q.main?12:8,th=i*TAU/m+.2,x=q.x+Math.cos(th)*(q.rx-2),y=q.y+Math.sin(th)*(ry-.6);p.put(x,y,b>.3?GL[5]:GL[3],.4+.5*b)}
    if(!q.main){const d=Math.round(2+b*1.5);for(let k=-d;k<=d;k++){p.put(q.x+k,q.y-(d-Math.abs(k))*.5,GL[b>.4?4:2],.4+.5*a);p.put(q.x+k,q.y+(d-Math.abs(k))*.5,GL[b>.4?4:2],.4+.5*a)}}
    if(b>.2){const R=q.rx+2,RY=ry+3;for(let y=-Math.round(RY);y<=Math.round(RY);y++)for(let x=-R;x<=R;x++){const dd=Math.hypot(x/R,y/RY);if(dd<1)p.tint(q.x+x,q.y+y,GL[3],(1-dd)*b*(q.main?.6:.45),.5)}
      for(let i=0;i<(q.main?8:5);i++){const u=frac(b*.5+t*2+i*.2),hh=u*(q.main?18:12);p.dput(q.x-q.rx*.6+i*q.rx*1.2/(q.main?8:5),q.y-hh,GL[4],(1-u)*b*.9)}}
  }
  function fern(p,f,t){
    for(let k=0;k<f.n;k++){const a0=(k-(f.n-1)/2)*.5+.06*Math.sin(TAU*(t+f.ph)),L=f.L*(1-.12*Math.abs(k-(f.n-1)/2));
      for(let s=0;s<=L;s++){const u=s/L,ang=a0*(1+u*.6),x=f.x+Math.sin(ang)*s+Math.sign(a0||1)*u*u*4*Math.abs(a0),y=f.y-Math.cos(ang)*s*.9+u*u*L*.3;
        p.put(x,y,u>.7?GL[1]:GL[0]);if(s>2&&s%2===0&&u<.9){const lf=(1-u)*3.2+.6;p.put(x-lf,y+1,GL[0]);p.put(x+lf,y+1,GL[0]);if(u>.5)p.put(x+lf*Math.sign(a0||1),y,GL[1])}}}
  }
  function draw(p,f,N){
    const t=f/N;
    // low mist, two layers crawling in opposite senses
    for(let y=140;y<H;y++){const dp=clamp((y-140)/60);
      for(let x=0;x<W;x++){if(mask[y*W+x]===0)continue;
        const d=tnoise((x+52*t)/13,y/7,4,64,20),m=tnoise(x/38,y/18,8,64,22),v=d*.7+m*.55-.66+.1*dp;if(v>0)p.tint(x,y,MISTC,v*2,.55);
        const d2=tnoise((x-27*t)/9,y/5,3,64,30),v2=d2*.6+m*.5-.7+.1*dp;if(y>176&&v2>0)p.tint(x,y,MISTC,v2*1.6,.45)}}
    // runes: three satellites pulse in turn and hand the light to the trap ring
    for(const q of RUNES)rune(p,q,t);
    // two taut snare lines tied to the jaws, dark rope; light catches each only as a glint runs along it
    for(const cd of CORDS){const n=cd.bx-cd.ax,sg=cd.bx>cd.ax?1:-1,nn=Math.abs(n);
      for(let i=0;i<=nn;i++){const u=i/nn,x=cd.ax+sg*i,y=cd.ay+(cd.by-cd.ay)*u+2*Math.sin(Math.PI*u);p.put(x,y,ROPE);p.put(x,y+1,ROPE2,.8)}
      const g=(t-cd.w0)/.16;if(g>=0&&g<=1){const gx=Math.round(cd.ax+sg*g*nn),gu=g,gy=Math.round(cd.ay+(cd.by-cd.ay)*gu+2*Math.sin(Math.PI*gu));
        for(let k=-2;k<=2;k++)p.put(gx+k,gy,GLINT,1-Math.abs(k)/3);p.put(gx,gy-1,GLINT,.7)}}
    // glint across the steel
    {const g=(t-.72)/.12;if(g>=0&&g<=1){const gx=Math.round(TX-12+24*g);p.put(gx,TY-1,STEEL[2]);p.put(gx,TY-2,GLINT,.9);p.put(gx-1,TY-1,GLINT,.6);p.put(gx+1,TY-1,GLINT,.6)}}
    // tripwire in dark rope, with a burst of orange sparks where it snaps
    const age=frac(t-.04),au=age*24,jit=au<6?1.4*Math.sin(TAU*age*9)*(1-au/6):0;
    {const x0=WS[0][0]+1,x1=WS[1][0];let py=null;for(let x=x0;x<=x1;x++){const u=(x-x0)/(x1-x0),y=Math.round(WS[0][1]-5+(WS[1][1]-WS[0][1])*u+2*Math.sin(Math.PI*u)+jit*Math.sin(Math.PI*u));
      if(py!==null)for(let k=Math.min(py,y);k<=Math.max(py,y);k++)p.put(x,k,ROPE);else p.put(x,y,ROPE);py=y}}
    {const sx=Math.round((WS[0][0]+WS[1][0])/2),sy=Math.round((WS[0][1]+WS[1][1])/2-3);
      if(au<3){const k=1-au/3.4;
        for(let i=-5;i<=5;i++){const a=1-Math.abs(i)/6;p.put(sx+i,sy,OR[3],a);p.put(sx,sy+i,OR[3],a*.9)}
        for(let y=-8;y<=8;y++)for(let x=-12;x<=12;x++){const d=Math.hypot(x,y*1.5);if(d<12)p.tint(sx+x,sy+y,OR[0],(1-d/12)*k*.7,.55)}
        for(let i=0;i<9;i++){const th=-Math.PI*(.05+.9*h2(i,1,4)),v=3.5+4.5*h2(i,2,4),x=sx+Math.cos(th)*v*au*(1.0+au*.15),y=sy+Math.sin(th)*v*au+au*au*1.6;
          const col=OR[au<1?3:au<2?2:1];p.put(x,y,col);p.put(x,y+1,OR[1],.7);p.put(x+(Math.cos(th)>0?-1:1),y,OR[1],.5)}}}
    for(const fr of FERNS)fern(p,fr,t);
    emberDraw(p,MOTE,t,3,[GL[4],GL[3],GL[2],GL[1]]);
  }
  self.draw=draw;return TBG.add(self);
})();
