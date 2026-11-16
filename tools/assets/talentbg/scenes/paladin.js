/* PALADIN: Holy (nave of light), Protection (consecrated shrine floor at night), Retribution (dawn over cathedral spires). */
/* ================================== HOLY: nave of light ================================== */
(()=>{
  const self={cls:'PALADIN',tree:1,id:'paladin_holy',name:'HOLY'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const INK=INKS.map(c);
  const GOLD=c.ramp(['#2a1850','#4a2a5a','#6a4a58','#8a6a38','#b08a2c','#d4a62e','#ffd23f','#fff1c4']);
  const VIO=c('#3a2068'),MORT=c('#07030e');
  const FLR=224-56,WX=[26,78,130],HW=11,SPR=52,TOPY=30,BOT=118,SL=.3,SY0=60;
  const mask=new Uint8Array(W*H); // 1 wall, 2 floor, 0 solid (windows, pillars)
  const hwAt=y=>y>=SPR?HW:HW*Math.pow(Math.max(0,1-(SPR-y)/(SPR-TOPY+1)),.6);
  const shaftC=(i,y)=>WX[i]+SL*(y-SY0), shaftW=y=>34+(y-SY0)*.16;
  const MOTES=[];{const r=rng(12);for(let i=0;i<2;i++)for(let k=0;k<30;k++)MOTES.push({i,u:r(),y:SY0+20+r()*150,D:30+r()*60,lf:.5+r()*.4,ph:r(),sw:r()*TAU,k:1+fl(r()*2),big:r()>.8})}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<FLR){let col=ramp([INK[0],INK[1],INK[2],INK[3]],clamp(.18+.5*y/FLR+.2*(tnoise(x/7,y/5,40,60,3)-.5)),x,y);
        const row=fl(y/12),jx=(x+(row&1?9:0))%18;if(y%12===0||jx===0)col=INK[0];
        p.put(x,y,col);mask[y*W+x]=1}
      else{const d=(y-FLR)/(H-FLR);let col=ramp([INK[0],INK[1],INK[2],INK[3]],clamp(.25+.55*d+.35*(tnoise(x/6,y/4,40,60,5)-.5)),x,y);
        p.put(x,y,col);mask[y*W+x]=2}}
    // flagstone joints, receding toward a vanishing point
    for(const ry of [FLR,FLR+7,FLR+16,FLR+28,FLR+42,FLR+58])for(let x=0;x<W;x++)p.put(x,ry,INK[0]);
    for(let k=-9;k<=9;k++)for(let y=FLR+1;y<H;y++){const x=78+(k*26)*(y-100)/(FLR-100);p.put(x,y,INK[0])}
    // worn chips on the stone
    {const r=rng(31);for(let i=0;i<40;i++){const x=fl(r()*W),y=FLR+2+fl(r()*(H-FLR-2));p.put(x,y,INK[4]);p.put(x+1,y,INK[3])}}
    // pillars between the windows
    for(const px of [0,52,104,152]){const w=px===0||px===152?5:8;
      for(let y=0;y<FLR;y++)for(let i=0;i<w;i++){const x=px+i-(px>0&&px<152?0:0);if(x>=W)continue;
        let col=i===0?INK[3]:i===w-1?INK[0]:INK[1];if(y>FLR-10&&i>0&&i<w-1)col=INK[2];if(y===FLR-10||y===FLR-11)col=INK[3];
        p.put(x,y,col);mask[y*W+x]=0}}
    // tall pointed windows
    for(const wx of WX)for(let y=TOPY-2;y<=BOT+2;y++){const hw=hwAt(y)+ (y<=BOT?2:0);if(y===BOT+2){for(let x=wx-HW-2;x<=wx+HW+2;x++){p.put(x,y,INK[4]);mask[y*W+x]=0}continue}
      for(let dx=-Math.ceil(hw);dx<=Math.ceil(hw);dx++){const x=wx+dx,ad=Math.abs(dx);let col;
        if(ad>hwAt(y)+.5)col=ad>hw+.4?null:INK[4];
        else{const gy=(y-TOPY)/(BOT-TOPY);col=ramp([GOLD[0],GOLD[1],GOLD[2],GOLD[3]],.18+.55*(1-gy)+.15*(1-ad/HW),x,y);
          if(dx===0||(y-TOPY)%20===19||(ad===5&&y>SPR-4&&(y-TOPY)%20===9&&false))col=INK[1];
          if(y<SPR&&ad<hwAt(y)-3&&Math.abs(ad-hwAt(y)*.55)<.5)col=INK[1]}
        if(col){p.put(x,y,col);mask[y*W+x]=0}}}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,pulse=.5+.5*Math.sin(TAU*t);
    // windows breathe a touch
    for(const wx of WX)for(let y=TOPY;y<=BOT;y++){const hw=hwAt(y);for(let dx=-Math.ceil(hw);dx<=Math.ceil(hw);dx++){const x=wx+dx;if(mask[y*W+x]!==0)continue;
      if(Math.abs(dx)<=hw-1)p.tint(x,y,GOLD[5],.12+.12*pulse*(1-(y-TOPY)/(BOT-TOPY)),.5)}}
    // shafts: clean parallelograms, fading along their length, soft dithered edges, intensity breathing only
    for(let i=0;i<2;i++){const br=.82+.18*Math.sin(TAU*t+i*2.1);
      for(let y=SY0;y<FLR+16;y++){const cx=shaftC(i,y),w=shaftW(y),fade=Math.pow(clamp(1-(y-SY0)/(FLR+16-SY0)),.8);
        for(let x=fl(cx-w/2);x<=Math.ceil(cx+w/2);x++){const u=Math.abs(x-cx)/(w/2);if(u>=1)continue;
          const m=mask[y*W+x];if(m===0&&y<=BOT+2&&Math.abs(x-WX[i])<=14)continue;
          const a=.78*fade*br*clamp((1-u)*3.2)*(m===0?.5:1);
          p.dput(x,y,GOLD[3],Math.min(1,a*1.5));if(a>.5)p.dput(x,y,GOLD[4],(a-.5)*2.2)}}
      // soft lit pool where the shaft lands
      const pcx=shaftC(i,FLR+34),pcy=FLR+36,prx=26;
      for(let y=pcy-9;y<=pcy+9;y++)for(let x=pcx-prx-1;x<=pcx+prx+1;x++){if(x<0||x>=W||y<FLR||y>=H)continue;
        const d=Math.hypot((x-pcx)/prx,(y-pcy)/(prx*.27));if(d>=1)continue;
        const a=.7*br*Math.pow(1-d,1.2);p.dput(x,y,GOLD[3],Math.min(1,a*1.4));if(a>.45)p.dput(x,y,GOLD[4],(a-.45)*2)}}
    // dust motes rising in the shafts
    for(const e of MOTES){const age=frac(t-e.ph);if(age>=e.lf)continue;const u=age/e.lf,y=e.y-e.D*u;if(y<SY0+6||y>H-2)continue;
      const x=shaftC(e.i,y)+(e.u-.5)*(shaftW(y)-5)+2*Math.sin(TAU*(e.k*u*.5+e.sw));
      const a=u<.15?u/.15:u>.6?(1-u)/.4:1;p.dput(x,y,e.big?GOLD[7]:GOLD[6],a);if(e.big&&Math.sin(TAU*(2*t+e.ph*5))>.3){p.put(x-1,y,GOLD[6],.8*a);p.put(x+1,y,GOLD[6],.8*a);p.put(x,y-1,GOLD[6],.8*a);p.put(x,y+1,GOLD[6],.8*a)}}
    // halo pulse over the worn stone
    const cx=78,cy=204,rx=46+5*Math.sin(TAU*t);
    for(let y=cy-30;y<=cy+30;y++)for(let x=cx-rx-4;x<=cx+rx+4;x++){if(x<0||x>=W||y<FLR||y>=H)continue;
      const d=Math.hypot((x-cx)/rx,(y-cy)/(rx*.26));
      let a=0;if(d<1)a=.14*(1-d)*(.7+.5*pulse);if(Math.abs(d-1)<.07)a=.4*(.6+.4*pulse);
      const e=frac(t),re=.2+.8*e;if(Math.abs(d-re)<.045)a=Math.max(a,.32*(1-e));
      if(a>0)p.tint(x,y,GOLD[5],a,.5)}
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== PROTECTION: consecrated shrine floor at night ================================== */
(()=>{
  const self={cls:'PALADIN',tree:2,id:'paladin_protection',name:'PROTECTION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const INK=INKS.map(c);
  const GOLD=c.ramp(['#2a1850','#5a3a50','#8a5a30','#b07a2c','#d89a38','#ffb648','#ffd98a','#fff1c4']);
  const WALL=c.ramp(['#07030e','#0c0a24','#141a40','#1c2858','#2a3a78','#5a6aa8']);
  const DEEP=c('#07030e');
  const FLR=140,CX=78,AY=206,LANT=[[16,84,0],[140,84,.4],[44,52,.7],[112,52,.2]];
  const mask=new Uint8Array(W*H); // 0 = solid object (altar, posts), 1 = wall, 2 = floor
  const EMB=emberList(41,34,150,214,40,100,.4,.7);
  const sil=(p,x,y,col)=>{if(x<0||x>=W||y<0||y>=H)return;p.put(x,y,col);mask[fl(y)*W+fl(x)]=0};
  const rel=new Uint8Array(W*H); // relief pixels that glint
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<FLR){let col=ramp([WALL[0],WALL[1],WALL[2],WALL[3]],clamp(.1+.5*(y/FLR)+.25*(tnoise(x/7,y/5,40,60,3)-.5)),x,y);
        const row=fl(y/13),jx=(x+(row&1?10:0))%20;if(y%13===0||jx===0)col=WALL[0];else if(y%13===1&&h2(x,y,3)>.6)col=WALL[3];
        p.put(x,y,col);mask[y*W+x]=1}
      else{const d=(y-FLR)/(H-FLR);p.put(x,y,ramp([WALL[1],WALL[2],WALL[1],WALL[0]],clamp(.15+.4*d+.3*(tnoise(x/6,y/4,40,60,5)-.5)),x,y));mask[y*W+x]=2}}
    for(const ry of [FLR,FLR+6,FLR+14,FLR+25,FLR+39,FLR+56,FLR+77])for(let x=0;x<W;x++)p.put(x,ry,WALL[0]);
    for(let k=-9;k<=9;k++)for(let y=FLR+1;y<H;y++)p.put(78+(k*24)*(y-60)/(FLR-60),y,WALL[0]);
    // blue moon chips on the floor
    {const r=rng(60);for(let i=0;i<40;i++){const x=fl(r()*W),y=FLR+2+fl(r()*(H-FLR-3));p.put(x,y,WALL[4])}}
    // tall dark arch behind the altar
    for(let y=22;y<FLR;y++){const hw=y>=62?36:36*Math.sqrt(Math.max(0,1-Math.pow((62-y)/40,2)));
      for(let dx=-Math.ceil(hw);dx<=Math.ceil(hw);dx++){const x=CX+dx,e=Math.abs(dx)>=hw-1.2;
        p.put(x,y,e?WALL[4]:ramp([WALL[0],WALL[1]],.3+.5*(y/FLR)+.2*(Math.abs(dx)/36),x,y));if(e&&dx<0)p.put(x,y,WALL[5])}}
    // altar: steps, body, slab
    for(const[y0,y1,hw]of[[198,206,44],[190,198,38]])for(let y=y0;y<y1;y++)for(let dx=-hw;dx<=hw;dx++){
      const lit=y===y0,col=lit?WALL[5]:dx<-hw+2?WALL[4]:dx>hw-2?WALL[0]:ramp([WALL[1],WALL[2],WALL[3]],.2+.3*(y-y0)/8+.1*h2(dx,y,2),CX+dx,y);sil(p,CX+dx,y,col)}
    for(let y=112;y<190;y++)for(let dx=-33;dx<=33;dx++){const x=CX+dx;
      let col=ramp([WALL[1],WALL[2],WALL[3]],.25+.3*(1-(dx+33)/66)+.1*(tnoise(x/4,y/4,40,60,7)-.5),x,y);
      if(dx<=-32)col=WALL[5];else if(dx<=-30)col=WALL[4];else if(dx>=32)col=WALL[0];sil(p,x,y,col)}
    for(let dx=-37;dx<=37;dx++){sil(p,CX+dx,108,WALL[5]);sil(p,CX+dx,109,WALL[4]);sil(p,CX+dx,110,WALL[3]);sil(p,CX+dx,111,WALL[0])}
    // hammer and shield relief, 44 wide, lit from the upper left
    const RY=150,shw=y=>y<=4?22:22*(1-Math.pow((y-4)/23,1.6));
    for(let y=-27;y<=27;y++){const hw=Math.round(shw(y));if(hw<=0&&y>=26)continue;
      for(let dx=-hw;dx<=hw;dx++){const x=CX+dx,yy=RY+y;const edgeD=Math.min(hw-Math.abs(dx),y+27);
        let col=edgeD<=1?(dx<0||y===-27?GOLD[5]:GOLD[3]):edgeD<=3?(dx<0?GOLD[3]:GOLD[2]):dx<0?WALL[3]:WALL[2];
        p.put(x,yy,col);if(edgeD<=3)rel[yy*W+x]=1}}
    for(let y=-24;y<=22;y++)for(let dx=-1;dx<=1;dx++){const x=CX+dx,yy=RY+y;p.put(x,yy,dx<0?GOLD[5]:dx>0?GOLD[2]:GOLD[4]);rel[yy*W+x]=1}
    for(let y=-24;y<=-12;y++)for(let dx=-14;dx<=14;dx++){const x=CX+dx,yy=RY+y;
      const e=y===-24?GOLD[7]:y===-12?GOLD[2]:dx===-14?GOLD[6]:dx===14?GOLD[2]:y<-18?GOLD[5]:GOLD[4];p.put(x,yy,e);rel[yy*W+x]=1}
    // iron posts and chains
    for(const[lx,ly]of LANT){
      if(ly>60){for(let y=ly+5;y<=AY-4;y++){sil(p,lx,y,DEEP);sil(p,lx+1,y,y%5===0?WALL[3]:WALL[1])}for(let dx=-4;dx<=5;dx++)sil(p,lx+dx,AY-3,dx<0?WALL[3]:DEEP),sil(p,lx+dx,AY-2,DEEP)}
      else for(let y=0;y<ly-4;y++)sil(p,lx,y,y%2?WALL[3]:WALL[1]);
      for(let dy=-4;dy<=4;dy++)for(let dx=-3;dx<=3;dx++)sil(p,lx+dx,ly+dy,Math.abs(dx)===3||Math.abs(dy)===4?DEEP:WALL[1]);
      sil(p,lx,ly-5,DEEP);sil(p,lx-1,ly-5,WALL[3]);sil(p,lx+1,ly-5,WALL[3])}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,pulse=.5+.5*Math.sin(TAU*t);
    // moonlight drifting over the stone
    const w=.5-.5*Math.cos(TAU*t);
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){if(mask[y*W+x]===0)continue;
      const n=tnoise(x/16,y/22,40,12,17)*(1-w)+tnoise(x/16,y/22,40,12,18)*w-.6;if(n>0)p.tint(x,y,WALL[5],n*.8,.4)}
    // lantern pools
    for(const[lx,ly,ph]of LANT){const fk=1+.08*Math.sin(TAU*(3*t+ph))+.05*Math.sin(TAU*(5*t+ph*2)),R=42*fk;
      for(let y=ly-R;y<=ly+R;y++)for(let x=lx-R;x<=lx+R;x++){if(x<0||x>=W||y<0||y>=H)continue;
        const d=Math.hypot(x-lx,(y-ly)*1.1)/R;if(d>=1)continue;const a=Math.pow(1-d,1.6)*(mask[y*W+x]===0?.45:.62);p.tint(x,y,GOLD[3],a,.5)}
      const core=Math.sin(TAU*(3*t+ph))>.2;
      for(let dy=-3;dy<=3;dy++)for(let dx=-2;dx<=2;dx++)p.put(lx+dx,ly+dy,Math.abs(dx)+Math.abs(dy)<=2?(core?GOLD[7]:GOLD[6]):GOLD[5])}
    // ward rings as ellipses on the floor, rippling out from the altar
    for(let i=0;i<3;i++){const u=frac(t+i/3),rx=24+u*104,ry=rx*.27,a=Math.pow(1-u,1.0)*.95;
      for(let y=fl(AY-ry-3);y<=AY+ry+3;y++)for(let x=fl(CX-rx-4);x<=CX+rx+4;x++){if(x<0||x>=W||y<FLR||y>=H)continue;
        if(mask[y*W+x]===0&&y<=AY)continue;
        const d=Math.hypot((x-CX)/rx,(y-AY)/ry),dd=(d-1)*Math.min(rx,ry*3.2);
        if(Math.abs(dd)<1.1)p.tint(x,y,u<.5?GOLD[6]:GOLD[5],a,.6);else if(Math.abs(dd)<3&&dd<0)p.tint(x,y,GOLD[3],a*.35,.45)}}
    // relief glints with the ring beat, and a slow shine across the hammer
    for(let y=122;y<=178;y++)for(let x=CX-23;x<=CX+23;x++)if(rel[y*W+x])p.tint(x,y,GOLD[6],.12+.3*pulse,.55);
    const gl=(t-.1)/.4;if(gl>=0&&gl<=1){const gx=CX-14+Math.round(28*gl);for(let k=-2;k<=2;k++)p.put(gx,126+k,GOLD[7],.85*(1-Math.abs(k)/3));p.put(gx-1,126,GOLD[7],.6);p.put(gx+1,126,GOLD[7],.6)}
    emberDraw(p,EMB,t,3,[GOLD[7],GOLD[6],GOLD[4],GOLD[2]]);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== RETRIBUTION: dawn over cathedral spires ================================== */
(()=>{
  const self={cls:'PALADIN',tree:3,id:'paladin_retribution',name:'RETRIBUTION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const INK=INKS.map(c);
  const SKY=c.ramp(['#05020c','#0a0420','#1c1038','#32185c','#5a2268','#a02c52','#c04450','#e0703c','#ffb648']);
  const GOLD=c.ramp(['#a02c52','#c8523e','#e0873a','#ffb648','#ffd98a','#fff1c4']);
  const DEEP=c('#07030e'),WIN=c('#ffb648');
  const HOR=170,SX=78,SYY=168,WALLY=186;
  const gx=x=>Math.exp(-Math.pow((x-SX)/62,2));
  const mask=new Uint8Array(W*H); // 1 sky, 0 silhouette
  const sil=(p,x,y,col)=>{if(x<0||x>=W||y<0||y>=H)return;p.put(x,y,col);mask[fl(y)*W+fl(x)]=0};
  const SPIRES=[[10,6,150],[30,8,122],[53,7,140],[104,7,134],[126,9,112],[146,7,144]];
  const FEA=emberList(77,40,80,232,60,120,.45,.8);
  function spire(p,cx,hw,ap){
    for(let y=ap;y<=WALLY;y++){const k=y-ap;let w;
      if(k<hw*2.6)w=hw*(k/(hw*2.6)); else w=hw;
      w=Math.round(w);for(let dx=-w;dx<=w;dx++){let col=dx===w&&w>0&&k>3?INK[2]:INK[0];sil(p,cx+dx,y,col)}}
    sil(p,cx,ap-1,INK[0]);sil(p,cx,ap-2,INK[0]);
    // small pointed side pinnacles
    for(const s of[-1,1]){const px=cx+s*(hw+2);for(let k=0;k<9;k++)sil(p,px,ap+hw*2.6+10-k,INK[0]);sil(p,px,ap+hw*2.6,INK[0]);sil(p,px,ap+hw*2.6-1,INK[0])}
    // lit slit windows
    const wy=ap+hw*3.2+4;for(let y=wy;y<HOR-6;y+=11)if(h2(cx,y,5)>.35){p.put(cx,y,WIN);p.put(cx,y+1,GOLD[2]);}
  }
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<HOR){p.put(x,y,ramp(SKY,Math.pow(y/HOR,1.5)*(.42+.58*gx(x))*.98,x,y));mask[y*W+x]=1}
      else{p.put(x,y,ramp([INK[1],INK[0],DEEP],clamp((y-HOR)/(H-HOR)+.2*(tnoise(x/8,y/5,40,40,4)-.5)),x,y))}}
    for(const[cx,hw,ap]of SPIRES)spire(p,cx,hw,ap);
    // central spire and the sword of light mount
    spire(p,SX,9,100);
    // flat dark city wall in the foreground with a straight dawn rim on top
    for(let y=WALLY;y<H;y++)for(let x=0;x<W;x++)sil(p,x,y,y===WALLY?(gx(x)>.5?GOLD[2]:gx(x)>.2?GOLD[1]:GOLD[0]):y===WALLY+1?INK[1]:DEEP);
    // dawn rim light on spire edges facing the sun
    for(let y=0;y<WALLY;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==0)continue;
      const g=gx(x);if(g<.2)continue;const side=x<SX?1:-1;
      if(y>0&&mask[(y-1)*W+x]===1)p.put(x,y,g>.6?GOLD[3]:GOLD[2]);
      else if(x+side>=0&&x+side<W&&mask[y*W+x+side]===1)p.put(x,y,g>.55?GOLD[2]:GOLD[1])}
    // sword: guard, grip, pommel
    for(let dx=-11;dx<=11;dx++){const y=86+(Math.abs(dx)>8?-1:0)+(Math.abs(dx)>10?-1:0);p.put(SX+dx,y,GOLD[3]);p.put(SX+dx,y+1,GOLD[1])}
    for(let y=87;y<=95;y++){p.put(SX,y,y%2?GOLD[2]:GOLD[1]);p.put(SX-1,y,GOLD[1]);p.put(SX+1,y,GOLD[1])}
    for(let dy=-1;dy<=1;dy++)for(let dx=-2;dx<=2;dx++)p.put(SX+dx,97+dy,Math.abs(dx)+Math.abs(dy)<=2?GOLD[3]:GOLD[1]);
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,pulse=.5+.5*Math.sin(TAU*t);
    // horizon dawn glow
    for(let y=60;y<HOR;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const d=Math.hypot((x-SX)*.8,(y-SYY));if(d<90){const a=Math.pow(1-d/90,2)*.4*(.9+.1*pulse);p.tint(x,y,GOLD[2],a,.5)}}
    // sweeping white gold rays
    for(let y=0;y<HOR;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const dx=x-SX,dy=SYY-y,r=Math.hypot(dx,dy);if(r<6)continue;
      const th=Math.atan2(dx,dy),s=Math.sin(9*th-TAU*t),v=Math.max(0,(s-.9)/.1);
      const a=v*.9/(1+r/90)*(y<30?y/30:1);
      if(a>.3){if(((x+y)&1)===0)p.put(x,y,GOLD[2])}else if(a>.12&&((x+y)&1)===0&&(y&1)===0)p.put(x,y,GOLD[1])}
    // the sword of light
    for(let y=10;y<=85;y++){const k=(85-y)/75,hw=k>.93?0:k>.35?1:2;
      for(let dx=-hw;dx<=hw;dx++)p.put(SX+dx,y,Math.abs(dx)===hw&&hw>0?GOLD[4]:GOLD[5]);
      // bright halo hugging the blade
      for(let dx=-9;dx<=9;dx++){if(Math.abs(dx)<=hw)continue;const a=Math.exp(-Math.pow(Math.abs(dx)/4.2,2))*(.55+.2*pulse)*(.5+.5*k*0+.5);
        p.tint(SX+dx,y,Math.abs(dx)<4?GOLD[5]:GOLD[4],a*.6,.5)}}
    for(let k=-7;k<=7;k++){const a=1-Math.abs(k)/8;p.put(SX+k,9,GOLD[5],a*(.5+.5*pulse));p.put(SX,9+k,GOLD[5],a*(.5+.5*pulse))}
    const gl=(t-.3)/.4;if(gl>=0&&gl<=1){const gy=Math.round(84-72*gl);for(let k=-2;k<=2;k++)p.put(SX,gy+k,GOLD[5],.9*(1-Math.abs(k)/3))}
    // mist at the roofs
    for(let y=HOR-6;y<HOR+26;y++)for(let x=0;x<W;x++){if(mask[y*W+x]===0)continue;
      const n=tnoise((x+78*t)/13,y/6,6,40,8)-.52;if(n>0)p.tint(x,y,GOLD[1],n*.8*(y<HOR?1:.5),.45)}
    // feather sparks drifting upward
    for(const e of FEA){const age=frac(t-e.ph);if(age>=e.lf)continue;const u=age/e.lf;
      let x=e.x+6*u+2.4*Math.sin(TAU*(e.k*u*.5+e.sw)),y=e.y-e.D*u;x=((x%W)+W)%W;
      const a=u<.12?u/.12:u>.6?(1-u)/.4:1,col=u<.4?GOLD[5]:u<.75?GOLD[4]:GOLD[2];
      p.dput(x,y,col,a);p.dput(x,y+1,col,a*.7);if(e.big){p.dput(x+(Math.sin(TAU*u*2)>0?1:-1),y+2,GOLD[3],a*.5);p.dput(x,y+3,GOLD[2],a*.35)}}
  }
  self.draw=draw;return TBG.add(self);
})();
