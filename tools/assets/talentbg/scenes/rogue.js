/* ROGUE: Assassination (poison alley under a green moon), Combat (harbor deck at night), Subtlety (moonlit rooftops). */
/* ================================== ASSASSINATION: poison alley ================================== */
(()=>{
  const self={cls:'ROGUE',tree:1,id:'rogue_assassination',name:'ASSASSINATION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const TOX=c.ramp(['#05020c','#07100c','#0a1a12','#0e2418','#123020','#17402a','#2a8a3a','#4fc040','#7dff4a']);
  const MOONC=['#4fc040','#9fe88a','#d4ffc0'].map(c),MORT=c('#040a07'),FOGC=c('#17402a');
  const mask=new Uint8Array(W*H); // 1 = open sky, 2 = wall or ground (tintable), 0 = silhouette
  const VPX=78,VPY=96,FX0=58,FX1=98,FY0=66,FY1=114,TS=1.5,BS=.9,MX=104,MY=26,MR=6,PUX=74,PUY=192,VX=52,VY=119,SKX=61,SKY0=70,DGY=188;
  const SKULL=['....#########....','..#############..','.###############.','.###############.','####ooo###ooo####','####ooo###ooo####','####ooo###ooo####','.###ooo###ooo###.','..######n######..','...#####n#####...','....#########....','....#.#.#.#.#....','....#.#.#.#.#....'];
  const STARS=[];{const r=rng(41);for(let i=0;i<12;i++){const x=20+fl(r()*116),y=2+fl(r()*40);if(Math.hypot(x-MX,y-MY)>MR+8)STARS.push({x,y,ph:r(),k:1+fl(r()*2)})}}
  const BUBS=[[90,197,.1],[64,201,.5],[100,191,.8]];
  const sil=(p,x,y,col)=>{p.put(x,y,col);if(x>=0&&x<W&&y>=0&&y<H)mask[fl(y)*W+fl(x)]=0};
  const puddle=(x,y)=>Math.pow((x-PUX)/44,2)+Math.pow((y-PUY)/12,2)+.3*(tnoise(x/6,y/3,64,64,4)-.5);
  const kindOf=(x,y)=>{const dx=Math.abs(x-VPX);
    if(x>=FX0&&x<=FX1)return y<FY0?1:y<=FY1?3:4;
    return y<VPY-TS*dx?1:y<=VPY+BS*dx?2:4};
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const k=kindOf(x,y),dx=Math.abs(x-VPX),dy=y-VPY;
      if(k===1){const dm=Math.hypot(x-MX,(y-MY)*1.1);p.put(x,y,ramp(TOX,.03+.2*clamp(1-dm/55)+.04*clamp(y/70),x,y));mask[y*W+x]=1}
      else if(k===3){const cr=fl((y-FY0)/3),xo=(cr&1)*3,bx=fl((x-FX0+xo)/6),vx=(x-FX0+xo)%6,mt=(y-FY0)%3===2||vx===5;
        const g=.15+(h2(bx,cr,3)-.5)*.1+.03*tnoise(x/5,y/5,64,64,2);p.put(x,y,mt?MORT:ramp(TOX,g,x,y));mask[y*W+x]=2;
        if(y===FY0||x===FX0||x===FX1)p.put(x,y,TOX[4]);else if(y===FY0+1&&dith(x,y,.4))p.put(x,y,TOX[3])}
      else if(k===2){
        let col;if(dx>=26){const cs=dy/dx*14,crs=fl(cs),cf=cs-crs,rowM=cf<.9*14/dx;let colM=false,bx=0;
          if(dx>=34){const zc=500/dx+(crs&1)*.5;bx=fl(zc);colM=zc-bx<.9*500/(dx*dx)}
          const g=.17+(h2(bx,crs,5)-.5)*.12+.12*clamp(1-dx/80)+.03*tnoise(x/6,y/6,64,64,8);col=(rowM||colM)?MORT:ramp(TOX,g,x,y)}
        else col=ramp(TOX,.2,x,y);
        p.put(x,y,col);mask[y*W+x]=2;
        const yt=VPY-TS*dx,yb2=VPY+BS*dx;if(y<=yt+1&&y>=yt)p.put(x,y,TOX[y<yt+.5?5:4]);if(y>=yb2-1)p.put(x,y,TOX[y>=yb2-.5?4:3])}
      else{const dyf=Math.max(1,dy),rf=Math.sqrt(dyf)*3.2,rr=fl(rf),cf=rf-rr,u=(x-VPX)/dyf*12+(rr&1)*.5,cu=u-fl(u);
        const mt=cf<1.6/Math.sqrt(dyf)||cu<12/dyf,g=.15+(h2(fl(u),rr,7)-.5)*.1+.05*tnoise(x/7,y/4,64,64,3)-.07*clamp((y-150)/86),pd=puddle(x,y);
        if(pd<1)p.put(x,y,ramp(TOX,pd>.86?.66:.4+.1*tnoise(x/9,y/3,64,64,6),x,y));else p.put(x,y,mt?MORT:ramp(TOX,g,x,y));mask[y*W+x]=2}}
    // far wall details: a vent, a chimney on its roof
    for(let y=58;y<=66;y++)for(let x=82;x<=86;x++)sil(p,x,y,x===86?TOX[4]:TOX[1]);for(let x=81;x<=87;x++)sil(p,x,57,TOX[4]);
    for(let y=60;y<=66;y++)sil(p,64,y,TOX[2]);
    // the small pale moon
    for(let dy=-MR;dy<=MR;dy++)for(let dx=-MR;dx<=MR;dx++){const d=Math.hypot(dx,dy);if(d>MR)continue;const s=(dx*.6+dy*.8)/MR;
      let col=s<-.4?MOONC[2]:s<.4?MOONC[1]:MOONC[0];if(Math.hypot(dx-2,dy-1)<=1.5&&col!==MOONC[2])col=MOONC[0];
      p.put(MX+dx,MY+dy,col);mask[(MY+dy)*W+MX+dx]=1}
    // crates and a barrel near the camera
    for(let y=160;y<=206;y++)for(let x=0;x<=36;x++){const e=y===160||x===36;sil(p,x,y,e?TOX[3]:((y-160)%12===0||x%18===0||Math.abs((x*1.2)-(y-160)%46)<1?TOX[1]:TOX[0]))}
    for(let y=130;y<160;y++)for(let x=6;x<=30;x++){const e=y===130||x===30;sil(p,x,y,e?TOX[4]:((y-130)%10===0?TOX[1]:TOX[0]))}
    for(let y=186;y<=206;y++)for(let x=102;x<=120;x++){const e=y===186||x===120;sil(p,x,y,e?TOX[3]:((y-186)%7===0?TOX[1]:TOX[0]))}
    for(let y=150;y<=206;y++){const hw=Math.round(12+2.4*Math.sin(Math.PI*(y-150)/56));for(let x=136-hw;x<=136+hw;x++){const hoop=y===162||y===180||y===198;
      sil(p,x,y,hoop?TOX[2]:(x>=136+hw-1?TOX[4]:TOX[0]))}}
    for(let x=122;x<=150;x++)sil(p,x,149,TOX[4]);
    // vial bracket, wire and the vial (mouth down)
    for(let x=44;x<=VX+2;x++){sil(p,x,111,TOX[4]);sil(p,x,112,TOX[1])}
    for(let y=113;y<VY;y++)sil(p,VX,y,TOX[4]);
    for(let x=VX-1;x<=VX+1;x++)p.put(x,VY,TOX[5]);
    for(let y=VY+1;y<=VY+7;y++)for(let x=VX-3;x<=VX+3;x++){const e=x===VX-3||x===VX+3;p.put(x,y,e?(x>VX?TOX[7]:TOX[5]):(y>=VY+5?TOX[6]:TOX[3]))}
    for(let x=VX-2;x<=VX+2;x++)p.put(x,VY+8,x===VX-2||x===VX+2?TOX[5]:TOX[6]);
    for(let y=VY+9;y<=VY+11;y++){p.put(VX-1,y,TOX[5]);p.put(VX+1,y,TOX[7]);p.put(VX,y,y===VY+11?TOX[8]:TOX[6])}
    // sign bracket on the right wall
    for(let x=118;x<=132;x++){sil(p,x,88,TOX[4]);sil(p,x,89,TOX[1])}
    for(let y=90;y<=92;y++){sil(p,119,y,TOX[3]);sil(p,129,y,TOX[3])}
    // the skull painted on the far wall, doubled
    for(let r=0;r<26;r++)for(let q=0;q<34;q++){const ch=SKULL[r>>1][q>>1];if(ch==='.')continue;
      const X=SKX+q,Y=SKY0+r;if(ch==='o'||ch==='n'){p.put(X,Y,TOX[0]);continue}
      if(h2(X,Y,17)>.95)continue;p.put(X,Y,q<12?TOX[5]:(q>26&&r<14?TOX[7]:TOX[6]))}
    for(const[q,len]of[[10,9],[18,14],[26,6]]){for(let k=0;k<len;k++){p.put(SKX+q,SKY0+26+k,TOX[5]);p.put(SKX+q+1,SKY0+26+k,TOX[5])}p.put(SKX+q,SKY0+26+len,TOX[6]);p.put(SKX+q+1,SKY0+26+len,TOX[6])}
    self.base=p;
  }
  function drip(p,x,top,ground,rx,ph,t){
    const a=frac(t-ph);
    if(a<.16){const u=a/.16;p.put(x,top,TOX[8],.4+.6*u);if(u>.55)p.put(x,top+1,TOX[7],.8)}
    else if(a<.34){const u=(a-.16)/.18,y=top+1+(ground-top-1)*u*u;p.put(x,y,TOX[8]);p.put(x,y-1,TOX[7]);p.dput(x,y-2,TOX[6],.6)}
    else if(a<.74){const u=(a-.34)/.4,r=1.2+rx*u,ry=Math.max(.9,r*.34);
      for(let k=0;k<26;k++){const th=k*TAU/26;p.dput(x+Math.cos(th)*r,ground+Math.sin(th)*ry,TOX[u<.5?8:7],Math.pow(1-u,.8))}
      if(u>.15&&u<.75){const r2=r*.55,ry2=Math.max(.7,ry*.55);for(let k=0;k<16;k++){const th=k*TAU/16;p.dput(x+Math.cos(th)*r2,ground+Math.sin(th)*ry2,TOX[6],(1-u)*.8)}}
      if(u<.3){for(const s of[-1,1]){const v=u/.3;p.put(x+s*(1.5+3.5*v),ground-1-6*Math.sin(Math.PI*v),TOX[8],1-v*.6);p.dput(x+s*(1+2.4*v),ground-1-4*Math.sin(Math.PI*v),TOX[7],1-v)}}}
  }
  function draw(p,f,N){
    const t=f/N,hb=1+.06*Math.sin(TAU*t),eg=.5+.5*Math.sin(TAU*t);
    for(let y=MY-40;y<MY+50;y++)for(let x=MX-44;x<=MX+44;x++){if(x<0||x>=W||y<0||y>=H)continue;const m=mask[y*W+x];if(!m)continue;
      const d=Math.hypot(x-MX,(y-MY)*1.1);if(d<44)p.tint(x,y,TOX[5],Math.pow(1-d/44,1.8)*.3*hb*(m===1?1:.6),.5)}
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.6?TOX[7]:v>-.2?TOX[6]:TOX[4])}
    for(let y=4;y<64;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const d=tnoise((x+78*t)/12,y/2.6,6,64,7),m=tnoise(x/36,y/18,8,64,4),v=d*.7+m*.5-.74;if(v>0)p.tint(x,y,TOX[4],v*2.4,.5)}
    // the skull breathes: eyes and a sickly halo on the wall
    for(const ex of[11,23]){for(let a=0;a<2;a++)for(let b=0;b<2;b++)p.put(SKX+ex+a,SKY0+11+b,TOX[8],.35+.55*eg);p.dput(SKX+ex-1,SKY0+11,TOX[6],.5*eg);p.dput(SKX+ex+2,SKY0+12,TOX[6],.5*eg);p.dput(SKX+ex,SKY0+13,TOX[7],.5*eg)}
    for(let y=SKY0-10;y<SKY0+50;y++)for(let x=SKX-16;x<SKX+50;x++){const d=Math.hypot(x-(SKX+17),(y-(SKY0+16))*1.1);if(d<34&&mask[y*W+x]===2)p.tint(x,y,TOX[6],Math.pow(1-d/34,1.9)*.3*(.65+.35*eg),.5)}
    // vial glow, drip and ripple
    const vg=.7+.3*Math.sin(TAU*t);
    for(let y=VY-10;y<VY+24;y++)for(let x=VX-14;x<=VX+14;x++){const d=Math.hypot(x-VX,y-(VY+6));if(d<14&&mask[y*W+x]!==0)p.tint(x,y,TOX[7],Math.pow(1-d/14,1.6)*.4*vg,.5)}
    p.put(VX+3,VY+3,TOX[8],.5+.4*vg);p.put(VX-1,VY+6,TOX[8],.4+.4*(1-vg));p.dput(VX,VY+7,TOX[8],.6*vg);
    drip(p,VX,VY+13,DGY,12,0,t);drip(p,VX,VY+13,DGY,12,.5,t);
    // the poison pool glows
    for(let y=PUY-22;y<PUY+22;y++)for(let x=PUX-62;x<=PUX+62;x++){if(x<0||x>=W||y<0||y>=H||mask[y*W+x]===0)continue;
      const pd=puddle(x,y);if(pd>=1&&pd<2.6)p.tint(x,y,TOX[6],(1-(pd-1)/1.6)*.22*(.7+.3*vg),.5)}
    for(const[bx,by,ph]of BUBS){const a=frac(t-ph);if(a<.3){const u=a/.3;p.dput(bx,by-u*2,TOX[7],.5+.4*u);if(u>.7)p.dput(bx+1,by-3,TOX[8],.9)}}
    // laundry line across the alley, with rags swaying
    const A=[24,52],B=[132,46],ln=(u)=>[A[0]+(B[0]-A[0])*u,A[1]+(B[1]-A[1])*u+9*Math.sin(Math.PI*u)];
    for(let i=0;i<=108;i++){const q=ln(i/108);p.put(q[0],q[1],TOX[4])}
    [[.26,7,10,0],[.47,9,8,.3],[.7,6,11,.6]].forEach(([u,w,h,ph],k)=>{const q=ln(u),x0=Math.round(q[0])-fl(w/2);
      for(let j=0;j<h;j++){const sx=Math.round(1.4*Math.sin(TAU*(t+ph))*(j/h));for(let i=0;i<w;i++){const edge=(i===w-1)||j===0;
        if(j>h-3&&((i+k)&1))continue;p.put(x0+i+sx,Math.round(q[1])+1+j,edge?TOX[5]:(k===1?TOX[2]:TOX[0]))}}});
    // hanging sign, swaying a little
    const sw=Math.round(1.2*Math.sin(TAU*t));
    for(let j=0;j<9;j++){const s=Math.round(sw*j/8);for(let i=0;i<13;i++){const e=i===0||i===12||j===0||j===8;p.put(117+i+s,93+j,e?TOX[4]:TOX[1])}}
    p.put(123+sw,96,TOX[7]);p.put(122+sw,97,TOX[6]);p.put(124+sw,97,TOX[6]);p.put(123+sw,98,TOX[6]);p.put(123+sw,95,TOX[5]);
    // faint fog, low
    for(let y=104;y<H;y++)for(let x=0;x<W;x++){if(!mask[y*W+x])continue;
      const d=tnoise((x+78*t)/13,y/6,6,64,5),m=tnoise(x/38,y/17,4,64,9),v=d*.6+m*.5-.76+(y>170?.04*(y-170)/60:0);
      if(v>0)p.tint(x,y,FOGC,Math.min(.3,v*1.8),.5)}
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== COMBAT: harbor deck at night ================================== */
(()=>{
  const self={cls:'ROGUE',tree:2,id:'rogue_combat',name:'COMBAT'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#070a1c','#0a1030','#101848','#1a2260','#2e2a78','#5a2a80','#8a2a7e']);
  const SEA=c.ramp(['#05020c','#080a1e','#0c1232','#141c4a']);
  const DECK=c.ramp(['#06081a','#0a0e26','#10163a','#161e4a','#1e2860','#2a3478']);
  const INK=c('#05020c'),MORT=c('#040616');
  const STL=['#24287a','#3d4a8a','#5a6aa8','#8fa0d8','#c8d4ff'].map(c);
  const PINK=c('#ff2e97'),PINKD=c('#a02a7a'),PINKM=c('#d02a88');
  const GOLD=['#7a4a1a','#c88a3a','#ffd27a','#fff2c8'].map(c);
  const STAR=['#2a2a70','#6a7ad0','#e0e6ff'].map(c);
  const HOR=122,GX=100,RAILY=148,DECKY=158,PX=114,PY=9,PL=62;
  const mask=new Uint8Array(W*H); // 0 = silhouette (never tinted)
  const sil=(p,x,y,col)=>{p.put(x,y,col);if(x>=0&&x<W&&y>=0&&y<H)mask[fl(y)*W+fl(x)]=0};
  function line(p,x0,y0,x1,y1,col,s){const n=Math.max(Math.abs(x1-x0),Math.abs(y1-y0))|0;for(let i=0;i<=n;i++){const u=n?i/n:0;(s?sil:(q,x,y,cl)=>q.put(x,y,cl))(p,Math.round(x0+(x1-x0)*u),Math.round(y0+(y1-y0)*u),col)}}
  const ROWS=[DECKY];{let y=DECKY,st=4;while(y<H){y+=Math.round(st);st+=.5;ROWS.push(y)}}
  const rowOf=new Int16Array(H);for(let k=0;k<ROWS.length-1;k++)for(let y=ROWS[k];y<ROWS[k+1]&&y<H;y++)rowOf[y]=k;
  const STARS=[];{const r=rng(12);for(let i=0;i<30;i++)STARS.push({x:2+fl(r()*152),y:2+fl(r()*84),ph:r(),k:1+fl(r()*2)})}
  const LIGHTS=[[38,.1],[50,.4],[60,.7],[122,.2],[136,.55],[148,.85]];
  const gx=x=>Math.exp(-Math.pow((x-GX)/55,2));
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<HOR){p.put(x,y,ramp(SKY,Math.pow(y/HOR,1.7)*(.42+.5*gx(x)),x,y));mask[y*W+x]=1}
      else if(y<DECKY){p.put(x,y,ramp(SEA,.7-.55*(y-HOR)/(DECKY-HOR)+.2*(tnoise(x/9,y/1.5,64,64,2)-.5),x,y));mask[y*W+x]=1}
      else{const k=rowOf[y],ry=y-ROWS[k],len=34+6*(k%3),off=fl(hash(k*7+3)*len),bx=fl((x+off)/len),vx=(x+off)%len,bt=h2(bx,k,5);
        let g=.3+.2*tnoise(x/16,y/1.3,40,64,3)+(bt-.5)*.2-.28*(y-DECKY)/(H-DECKY);
        if(ry===1)g+=.12;
        p.put(x,y,(ry===0||vx===0)?MORT:ramp(DECK,g,x,y));mask[y*W+x]=1}}
    // distant ships and harbor lights on the horizon
    for(const[x0,w]of[[92,22],[130,14],[30,12]]){for(let x=x0;x<x0+w;x++){const hh=2+(x>x0+3&&x<x0+w-3?1:0);for(let k=0;k<hh;k++)sil(p,x,HOR-k,INK)}
      for(const mx of[x0+fl(w*.3),x0+fl(w*.68)]){for(let k=0;k<(w>14?16:9);k++)sil(p,mx,HOR-3-k,INK);for(let k=0;k<6;k++)for(let q=0;q<=Math.min(k,4);q++)if(w>14)sil(p,mx+1+q,HOR-4-6-k+(q>2?1:0),INK)}}
    // ship rail with a rope slung between posts
    for(let y=RAILY;y<DECKY;y++)for(let x=0;x<W;x++){const top=y===RAILY;sil(p,x,y,top?STL[1]:(y===RAILY+1?STL[0]:(y%4===0?DECK[1]:INK)))}
    for(let x=10;x<W;x+=28){for(let y=RAILY-9;y<RAILY;y++){sil(p,x,y,INK);sil(p,x+1,y,INK);if(y===RAILY-9)sil(p,x,y-1,STL[1])}}
    for(let x=10;x+28<W;x+=28)for(let i=0;i<=26;i++){const u=i/26;sil(p,x+1+i,RAILY-7+Math.round(4*(1-Math.pow(2*u-1,2))),GOLD[0])}
    // mast with hoops, yardarm and furled sail
    for(let y=0;y<=182;y++){const wd=y>170?(y-170)/3:0;for(let x=14-Math.round(wd);x<=19+Math.round(wd);x++)sil(p,x,y,x>=19+Math.round(wd)-0&&y%3?STL[0]:INK)}
    for(const hy of[44,82,124]){for(let x=13;x<=20;x++)sil(p,x,hy,GOLD[0])}
    for(let x=0;x<=52;x++){const dr=Math.round(x*.02);sil(p,x,28+dr,STL[1]);sil(p,x,29+dr,INK)}
    for(let x=4;x<=46;x++){const hh=3+Math.round(1.6*Math.sin(x*.55));for(let k=0;k<hh;k++)sil(p,x,30+k,k===0?STL[0]:DECK[1])}
    // crane boom top right and rigging
    line(p,156,3,112,9,INK,1);line(p,156,4,112,10,INK,1);line(p,156,2,112,8,STL[1],1);line(p,156,32,122,10,INK,1);
    for(let y=6;y<=14;y++)for(let x=PX-2;x<=PX+2;x++)if(Math.abs(x-PX)+Math.abs(y-PY)<=3)sil(p,x,y,STL[1]);
    line(p,17,9,70,148,INK,1);line(p,17,9,126,148,INK,1);line(p,17,46,48,148,INK,1);
    self.base=p;
  }
  function xsect(a,b,ua,ub){const d=ua[0]*ub[1]-ua[1]*ub[0];if(Math.abs(d)<1e-6)return a;const s=((b[0]-a[0])*ub[1]-(b[1]-a[1])*ub[0])/d;return[a[0]+ua[0]*s,a[1]+ua[1]*s]}
  function blade(p,hx,hy,ux,uy,L,sg){
    const nx=-uy,ny=ux;
    for(let s=-12;s<3;s+=.5){const x=hx+ux*s,y=hy+uy*s;p.put(x,y,s%3<1.5?STL[1]:DECK[3]);p.put(x+nx*.7,y+ny*.7,STL[0])}
    p.put(hx-ux*13,hy-uy*13,GOLD[2]);p.put(hx-ux*13+1,hy-uy*13,GOLD[1]);p.put(hx-ux*13,hy-uy*13+1,GOLD[1]);
    for(let o=-5;o<=5;o+=.5){const x=hx+nx*o+ux*2,y=hy+ny*o+uy*2;p.put(x,y,Math.abs(o)>3.5?GOLD[2]:GOLD[1]);p.put(x-ux,y-uy,GOLD[0])}
    const n=L*2;for(let i=0;i<=n;i++){const u=i/n,s=3+(L-3)*u,off=sg*2.6*Math.sin(Math.PI*u),w=1.9*(1-u)+.8;
      const cx=hx+ux*s+nx*off,cy=hy+uy*s+ny*off;
      for(let o=-w;o<=w;o+=.8){const col=u>.93?STL[3]:o>w*.4?STL[3]:o<-w*.4?PINKD:(Math.abs(o)<.5&&u>.06&&u<.85?STL[2]:STL[1]);p.put(cx+nx*o,cy+ny*o,col)}}
  }
  function draw(p,f,N){
    const t=f/N,step=fl(t*6);
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.8?STAR[2]:v>.1?STAR[1]:STAR[0])}
    // sea: harbor lights and pink glints under the glow
    for(const[lx,ph]of LIGHTS){const tw=Math.sin(TAU*(t+ph))>-.6;if(tw)p.put(lx,HOR-1,GOLD[2]);else p.put(lx,HOR-1,GOLD[0]);
      for(let y=HOR+1;y<HOR+14;y++){if(hash(y*19+lx+step*5)>.5-.02*(y-HOR))continue;p.put(lx+fl(hash(y+lx+step)*3)-1,y,GOLD[1],.5-.03*(y-HOR))}}
    for(let y=HOR+1;y<RAILY;y++){const dp=(y-HOR)/(RAILY-HOR);
      for(let k=0;k<2;k++){if(hash(y*23+k*91+step*9)>.6)continue;const x0=GX+fl((hash(y*7+k+step)-.5)*46),ln=2+fl(hash(y*3+k+step*2)*(3+dp*6));for(let i=0;i<ln;i++)p.put(x0+i,y,PINKM,.5)}}
    // sky haze brightens and fades with the swell
    const hz=.5+.5*Math.sin(TAU*t);
    for(let y=84;y<HOR;y++)for(let x=GX-60;x<=GX+60;x++){if(x<0||x>=W||mask[y*W+x]!==1)continue;const d=Math.hypot((x-GX)*.8,(y-HOR)*1.3);if(d<50)p.tint(x,y,PINKD,Math.pow(1-d/50,1.7)*(.2+.1*hz),.5)}
    // wet planks catch the pink light
    for(let y=DECKY;y<H;y++){const dp=(y-DECKY)/(H-DECKY);
      for(let x=GX-62;x<=GX+62;x++){if(x<0||x>=W)continue;const a=Math.exp(-Math.pow((x-GX)/30,2))*(1-dp*.55)*.26;p.tint(x,y,PINKD,a,.55)}
      for(let k=0;k<3;k++){if(hash(y*17+k*101+step*7)>.5)continue;const x0=GX+fl((hash(y*31+k*7+step)-.5)*70*(.6+dp)),ln=2+fl(hash(y+k*5+step*3)*(4+dp*8));
        for(let i=0;i<ln;i++)p.put(x0+i,y,PINK,.42-.18*dp)}}
    // lantern light
    const th=.2*Math.sin(TAU*t),lx=PX+PL*Math.sin(th),ly=PY+PL*Math.cos(th),fk=.85+.15*hash(f*31+5);
    for(let y=ly-32;y<=ly+34;y++)for(let x=lx-32;x<=lx+32;x++){if(x<0||x>=W||y<0||y>=H)continue;const xi=fl(x),yi=fl(y);if(mask[yi*W+xi]===0)continue;
      const d=Math.hypot(x-lx,(y-ly-4)*1.1);if(d<32)p.tint(x,y,GOLD[1],Math.pow(1-d/32,1.7)*.5*fk,.5)}
    // loose rope off the yardarm, out of phase
    for(let i=0;i<=38;i++){const u=i/38;p.put(44+5*u*Math.sin(TAU*(t-u*.3+.4)),31+i,GOLD[1]);if(i%3===0)p.put(45+5*u*Math.sin(TAU*(t-u*.3+.4)),31+i,GOLD[0])}
    // swinging lantern on its rope
    line(p,PX,PY,Math.round(lx),Math.round(ly),GOLD[1],0);
    const lxi=Math.round(lx),lyi=Math.round(ly);
    for(let x=lxi-2;x<=lxi+2;x++){p.put(x,lyi+1,INK);p.put(x,lyi+9,INK)}p.put(lxi,lyi,STL[1]);
    for(let y=lyi+2;y<=lyi+8;y++){p.put(lxi-2,y,INK);p.put(lxi+2,y,INK);p.put(lxi-1,y,GOLD[1]);p.put(lxi+1,y,GOLD[1]);p.put(lxi,y,y===lyi+5?GOLD[3]:GOLD[2])}
    if(fk>.97)p.put(lxi,lyi+3,GOLD[3]);
    // the clash: two blades, closing on a beat twice a loop
    const bp=frac(2*t),op=Math.pow(Math.sin(Math.PI*bp),.8),dl=.17*op;
    const dir=(dx,dy,a)=>{const ca=Math.cos(a),sa=Math.sin(a);return[dx*ca-dy*sa,dx*sa+dy*ca]};
    const uA=dir(.511,-.859,dl),uB=dir(-.511,-.859,-dl),hA=[60,166],hB=[104,166];
    blade(p,hA[0],hA[1],uA[0],uA[1],84,1);blade(p,hB[0],hB[1],uB[0],uB[1],84,-1);
    const C=xsect(hA,hB,uA,uB);
    if(bp<.5){const fl0=Math.exp(-bp*14);
      if(fl0>.1)for(let y=C[1]-16;y<=C[1]+16;y++)for(let x=C[0]-16;x<=C[0]+16;x++){const d=Math.hypot(x-C[0],y-C[1]);if(d<16)p.tint(x,y,PINK,Math.pow(1-d/16,1.5)*.4*fl0,.55)}
      if(bp<.05){for(let k=-4;k<=4;k++){p.put(C[0]+k,C[1],GOLD[2],.8-Math.abs(k)/6);p.put(C[0],C[1]+k,GOLD[2],.8-Math.abs(k)/6)}p.put(C[0],C[1],GOLD[3])}
      const age=bp/.4;
      for(let i=0;i<16;i++){const a0=-Math.PI*(.12+.76*hash(i*7+1))+(i%5===0?Math.PI*.9:0),v=24+30*hash(i*13+2),sp=age;
        for(let tr=0;tr<3;tr++){const q=Math.max(0,sp-tr*.07);if(q>=1)continue;const x=C[0]+Math.cos(a0)*v*q,y=C[1]+Math.sin(a0)*v*q+34*q*q;
          const col=q<.25?GOLD[3]:q<.5?GOLD[2]:q<.78?PINK:STL[3];p.put(x,y,col,tr===0?1:.55-.15*tr)}}}
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== SUBTLETY: moonlit rooftops ================================== */
(()=>{
  const self={cls:'ROGUE',tree:3,id:'rogue_subtlety',name:'SUBTLETY'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const V=c.ramp(['#05020c','#0a0418','#120a28','#1c1038','#2a1850','#3a2068','#4c2a8a','#6a3ab8','#a855f7']);
  const X=['#1a1a4a','#2e1a5c','#4a1a5a','#5a30a0','#7a4ad0','#8a5ad8'].map(c);
  const LAV=c('#d7b8ff'),PALE=c('#c99aff'),WHITE=c('#e6d0ff'),CY=c('#22e0ff'),CY2=c('#a8f4ff');
  const MX=106,MY=44,MR=14,HX=100,HW=28,HY=178,FB=207;
  const mask=new Uint8Array(W*H); // 1 = sky, 2 = distant roofs, 0 = near (never tinted)
  const CH=[]; // smoke origins
  const rt=x=>208-fl(x*.05);
  const STARS=[];{const r=rng(71);for(let i=0;i<34;i++){const x=2+fl(r()*152),y=2+fl(r()*112);if(Math.hypot(x-MX,y-MY)>MR+4)STARS.push({x,y,ph:r(),k:1+fl(r()*2)})}}
  const sil=(p,x,y,col)=>{p.put(x,y,col);if(x>=0&&x<W&&y>=0&&y<H)mask[fl(y)*W+fl(x)]=0};
  function layer(p,base,seed,wMin,wMax,hMin,hMax,hi,lo,rim,win){
    const r=rng(seed),top=new Int16Array(W).fill(H);let x=-6;
    while(x<W){const w=wMin+fl(r()*(wMax-wMin)),h=hMin+fl(r()*(hMax-hMin)),gab=r()<.55,gh=gab?fl(w*.42):0,cx=x+w/2;
      for(let xx=Math.max(0,x);xx<Math.min(W,x+w);xx++){const yt=base-h-(gab?Math.max(0,gh-fl(Math.abs(xx-cx)*gh/(w/2))):0);if(yt<top[xx])top[xx]=yt}
      x+=w-2}
    for(let xx=0;xx<W;xx++){if(top[xx]>=H)continue;for(let y=top[xx];y<H;y++){const k=clamp((y-top[xx])/55);
      p.put(xx,y,ramp([V[lo],V[hi]],1-k,xx,y));mask[y*W+xx]=2}
      p.put(xx,top[xx],rim);if(xx>0&&top[xx-1]>top[xx])p.put(xx,top[xx]+1,rim)}
    for(let i=0;i<win;i++){const wx=4+fl(r()*148),wy=top[wx]+6+fl(r()*18);if(wy<H-30&&wx>0&&wx<W-3){
      const lit=i%4===0;for(const[a,b]of[[0,0],[1,0],[0,1],[1,1]])p.put(wx+a,wy+b,lit?V[7]:V[hi+1]);if(lit){p.dput(wx-1,wy,V[5],.6);p.dput(wx+2,wy+1,V[5],.6)}}}
    return top;
  }
  function chim(p,top,x,w,h,rim){const yb=top[x]+3;for(let y=yb-h;y<=yb;y++)for(let xx=x;xx<x+w;xx++)p.put(xx,y,xx===x+w-1?V[5]:V[2]);
    for(let xx=x-1;xx<=x+w;xx++)p.put(xx,yb-h,rim);CH.push([x+w/2,yb-h-1])}
  function build(){
    const p=new Px();CH.length=0;
    for(let y=0;y<150;y++)for(let x=0;x<W;x++){const dm=Math.hypot(x-MX,(y-MY)*1.1);p.put(x,y,ramp(V,clamp(Math.pow(y/150,1.4)*.6+.3*clamp(1-dm/70)),x,y));mask[y*W+x]=1}
    for(let dy=-MR;dy<=MR;dy++)for(let dx=-MR;dx<=MR;dx++){const d=Math.hypot(dx,dy);if(d>MR)continue;const s=(dx*.6+dy*.8)/MR;
      let col=s<-.6?PALE:s<.1?X[5]:s<.6?V[7]:X[3];
      for(const[cx,cy,cr]of[[3,3,3],[-5,5,2],[4,-6,2],[-2,-2,1]])if(Math.hypot(dx-cx,dy-cy)<=cr&&col!==PALE)col=X[3];
      p.put(MX+dx,MY+dy,col)}
    const far=layer(p,146,5,16,30,0,22,2,1,X[3],12);chim(p,far,84,4,14,X[4]);
    for(let y=100;y<132;y++)sil(p,20,y,V[2]);for(let x=14;x<=26;x++)if(x!==20)sil(p,x,108,V[2]);for(let k=0;k<4;k++){sil(p,12-k,107+k%2,V[2]);sil(p,13,106+k,V[2])}
    sil(p,20,99,X[4]);
    const mid=layer(p,184,9,18,34,0,22,1,0,X[4],8);chim(p,mid,14,6,16,X[4]);
    // hero house: gable, lit window to blink, chimney
    for(let y=HY-16;y<208;y++)for(let x=HX;x<HX+HW;x++){const rf=HY-16+Math.abs(x-(HX+HW/2-.5))*1.05;if(y<rf)continue;
      sil(p,x,y,ramp([V[0],V[2]],1-clamp((y-HY)/30),x,y))}
    for(let x=HX;x<HX+HW;x++){const yy=Math.round(HY-16+Math.abs(x-(HX+HW/2-.5))*1.05);sil(p,x,yy,V[8]);sil(p,x,yy+1,X[3]);if(x>HX+HW/2)sil(p,x,yy+2,X[1])}
    for(let y=HY-26;y<HY-3;y++)for(let x=HX+19;x<=HX+23;x++)sil(p,x,y,x===HX+23?X[3]:V[2]);for(let x=HX+18;x<=HX+24;x++)sil(p,x,HY-27,V[8]);CH.push([HX+21,HY-28]);
    for(const[wx,wy]of[[HX+6,HY+4],[HX+17,HY+4]]){for(let y=wy;y<wy+7;y++)for(let x=wx;x<wx+5;x++)sil(p,x,y,V[0]);for(let x=wx-1;x<=wx+5;x++)sil(p,x,wy-1,X[3]);for(let y=wy;y<wy+7;y++)sil(p,wx+2,y,V[1])}
    // near roof: shingles and a lit ridge
    for(let x=0;x<W;x++){const r0=rt(x);
      for(let y=r0;y<H;y++){const row=fl((y-r0)/5),ry=(y-r0)%5,xo=(row&1)*4,sx=(x+xo)%8;
        let col=V[2];if(ry===4||sx===7)col=V[0];else if(ry===0)col=V[3];else if(sx===0&&ry<4&&h2(x,y,2)>.5)col=V[3];
        sil(p,x,y,col)}
      sil(p,x,r0,V[8]);if(dith(x,r0+1,.5))sil(p,x,r0+1,X[4])}
    // banner pole on the near roof
    for(let y=136;y<rt(148);y++){sil(p,148,y,V[2]);sil(p,149,y,y%5===0?X[3]:V[1])}
    for(let x=147;x<=150;x++)sil(p,x,135,V[8]);
    self.base=p;
  }
  function smoke(p,cx,cy,t,wind,seed,hmax,w0){
    for(let y=cy-hmax;y<cy;y++){const h=cy-y,u=h/hmax,center=cx+wind*Math.pow(u,1.3)*16+3.6*Math.sin(TAU*(t-h/34)),wd=w0+h*.13;
      for(let x=Math.floor(center-wd);x<=center+wd;x++){if(x<0||x>=W||!mask[y*W+x])continue;
        const n=tnoise((x-center)/2.8+8,h/5-6*t,32,6,seed),env=clamp(1-Math.abs(x-center)/wd)*Math.pow(1-u,.7),v=(n-.3)*2.2*env;
        if(v>0)p.tint(x,y,V[7],Math.min(.8,v),.55)}}
  }
  const fig=new Uint8Array(W*H);
  function poly(pts,fn){let y0=1e9,y1=-1e9;for(const q of pts){y0=Math.min(y0,q[1]);y1=Math.max(y1,q[1])}
    for(let y=Math.ceil(y0);y<=y1;y++){const xs=[];for(let i=0;i<pts.length;i++){const a=pts[i],b=pts[(i+1)%pts.length];if((a[1]<=y&&b[1]>y)||(b[1]<=y&&a[1]>y))xs.push(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))}
      xs.sort((u,v)=>u-v);for(let k=0;k+1<xs.length;k+=2)for(let x=Math.round(xs[k]);x<=Math.round(xs[k+1]);x++)fn(x,y)}}
  const BODY=[[46,131],[52,134],[60,137],[64,142],[65,148],[63,152],[61,155],[66,158],[72,165],[77,172],[78,182],[73,191],[76,200],[79,204],[40,204],[30,198],[28,186],[32,172],[38,160],[43,152],[46,146],[47,138]].map(([x,y])=>[x,y+3]);
  function draw(p,f,N){
    const t=f/N;
    for(const s of STARS){if(mask[s.y*W+s.x]!==1)continue;const v=Math.sin(TAU*(s.k*t+s.ph));p.put(s.x,s.y,v>.8?WHITE:v>.1?V[6]:V[4])}
    for(let y=8;y<120;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==1)continue;
      const d=tnoise((x+78*t)/13,y/3.4,6,64,5),m=tnoise(x/38,y/18,8,64,12),v=d*.7+m*.5-.7;if(v>0)p.tint(x,y,X[1],Math.min(.85,v*3.2),.7)}
    for(let y=120;y<200;y++)for(let x=0;x<W;x++){if(mask[y*W+x]!==2)continue;
      const v=tnoise((x+52*t)/11,y/5,6,64,8)*.7+tnoise(x/40,y/16,4,64,3)*.5-.8;if(v>0)p.tint(x,y,X[0],v*2,.5)}
    smoke(p,CH[0][0],CH[0][1],t,1,3,56,2);smoke(p,CH[1][0],CH[1][1],t,1,11,64,2.4);smoke(p,CH[2][0],CH[2][1],t,1,9,70,2.6);
    // the lit window blinks once
    const wx=HX+6,wy=HY+4,on=f===11?.5:(f===12||f===13)?1:f===14?.5:0;
    if(on>0){for(let y=wy-8;y<wy+16;y++)for(let x=wx-8;x<wx+14;x++){const d=Math.hypot(x-wx-2,y-wy-3);if(d<10&&mask[y*W+x]!==undefined)p.tint(x,y,V[6],Math.pow(1-d/10,1.5)*.45*on,.5)}
      for(let y=wy;y<wy+7;y++)for(let x=wx;x<wx+5;x++)p.dput(x,y,x===wx+2?V[7]:WHITE,on)}
    // banner streaming off the pole in the wind
    for(let i=0;i<24;i++){const u=i/23,cy=140+2.6*Math.sin(TAU*(t-i*.045))*u,hh=Math.round(9-5*u)+(i>19&&((i+Math.round(cy))&1)?-1:0);
      for(let j=0;j<hh;j++){const y=Math.round(cy)+j;p.put(147-i,y,j===0?X[4]:j===hh-1?V[3]:(i%7<2?X[2]:V[4]))}}
    // the crouched figure: cape tail with a fluttering hem, hood, body
    fig.fill(0);const mark=(x,y)=>{if(x>=0&&x<W&&y>=0&&y<H)fig[y*W+x]=1};
    for(let x=0;x<=46;x++){const yt=165+(46-x)*.42+2*Math.sin(TAU*(t-x/30)),yb=198+4*Math.sin(TAU*(t-x/45))+((x>>2)&1?2:0);for(let y=Math.round(yt);y<=Math.round(yb);y++)mark(x,y)}
    poly(BODY,mark);
    for(let y=130;y<=FB;y++)for(let x=0;x<=80;x++){if(!fig[y*W+x])continue;
      const up=!fig[(y-1)*W+x],rg=!fig[y*W+x+1],lf=x===0||!fig[y*W+x-1];
      let col=((x*2+y)%11===0&&y>158)?V[1]:V[0];
      if(up)col=y<165?V[8]:X[4];else if(rg)col=(x+y)%2?X[3]:X[4];else if(!fig[(y+1)*W+x]&&y<FB-4)col=X[1];
      p.put(x,y,col)}
    p.put(63,150,X[5]);p.put(62,150,V[7]);
    // dagger and its single cyan glint
    for(let k=0;k<=18;k++){const x=76+k,y=182+Math.round(k*.3);p.put(x,y,k<3?X[3]:k>15?LAV:V[8]);if(k>3)p.put(x,y+1,X[4],.6)}
    p.put(75,180,V[7]);p.put(75,181,V[7]);p.put(75,183,V[7]);
    const g=(t-.62)/.14;
    if(g>=0&&g<=1){const s=Math.sin(Math.PI*g),L=Math.round(5*s);p.put(94,187,CY2);for(let k=1;k<=L;k++){const a=1-k/(L+1);p.put(94-k,187,CY,a);p.put(94+k,187,CY,a);p.put(94,187-k,CY,a);p.put(94,187+k,CY,a)}
      if(s>.5){p.put(93,186,CY2,.7);p.put(95,188,CY2,.7)}}
  }
  self.draw=draw;return TBG.add(self);
})();
