/* WARLOCK: Affliction (sick swamp fog), Demonology (fel summoning circle in a crypt), Destruction (chaos rift in the sky). */
/* ================================== AFFLICTION: swamp fog, soul wisps, skull lantern ================================== */
(()=>{
  const self={cls:'WARLOCK',tree:1,id:'warlock_affliction',name:'AFFLICTION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SW=c.ramp(['#05020c','#0a1a12','#0c2218','#0f2e1c','#143e22','#1c5a2a','#2e8034']);
  const GR=['#4ab038','#7dff4a','#c8ff9a'].map(c),PU=['#2a1050','#4a1c80','#7a2ec0','#a855f7','#d4a0ff'].map(c);
  const INK=c('#05020c'),BRIM=c('#143e22'),BONE=['#4a5a48','#7a8a70','#a8b89a'].map(c),ROPE=c('#143e22'),MOON=c('#5a6a52');
  const HOR=178,MOONX=36,MOONY=40;
  const mask=new Uint8Array(W*H).fill(1); // 0 = silhouette (never tinted)
  const sil=(p,x,y,col)=>{p.put(x,y,col);x=fl(x);y=fl(y);if(x>=0&&x<W&&y>=0&&y<H)mask[y*W+x]=0};
  const line=(p,x0,y0,x1,y1,col,a)=>{const n=Math.max(Math.abs(x1-x0),Math.abs(y1-y0),1);for(let i=0;i<=n;i++)p.put(x0+(x1-x0)*i/n,y0+(y1-y0)*i/n,col,a)};
  const mt=(p,x,y,col,a,s)=>{x=fl(x);y=fl(y);if(x<0||y<0||x>=W||y>=H||mask[y*W+x]===0)return;p.tint(x,y,col,a,s)};
  function disc(p,cx,cy,r){for(let dy=-r;dy<=r;dy++)for(let dx=-r;dx<=r;dx++)if(dx*dx+dy*dy<=r*r+r*.6)sil(p,cx+dx,cy+dy,INK)}
  function limb(p,pts,w0,w1){const segs=pts.length-1;for(let i=0;i<segs;i++){const[ax,ay]=pts[i],[bx,by]=pts[i+1],n=Math.ceil(Math.hypot(bx-ax,by-ay));
    for(let s=0;s<=n;s++){const u=(i+s/n)/segs,w=Math.round(w0+(w1-w0)*u);disc(p,Math.round(ax+(bx-ax)*s/n),Math.round(ay+(by-ay)*s/n),Math.max(0,w>>1))}}}
  const RUNES=[["..#..",".###.","#.#.#",".###.","..#.."],["#...#",".#.#.","..#..",".#.#.","#...#"],[".###.","#...#","#.#.#","#...#",".###."]];
  const MARKS=[{x:16,y:92,g:0,ph:0},{x:54,y:128,g:1,ph:.34},{x:24,y:152,g:2,ph:.67}];
  const WISPS=[];{const r=rng(7);for(let i=0;i<11;i++)WISPS.push({x0:8+r()*100,ph:r(),lf:.62+r()*.3,amp:3+r()*5,sw:r(),pu:i%4===3})}
  const PIV=[84,92],ROPEL=26;
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<HOR)p.put(x,y,ramp(SW,Math.pow(y/HOR,1.7)*.3+.03*(tnoise(x/9,y/6,40,40,3)-.5),x,y));
      else{const v=(y-HOR)/(H-HOR),band=Math.exp(-Math.pow((y-HOR-5)/6,2));
        p.put(x,y,ramp(SW,.2+.22*band-.12*v+.05*(tnoise(x/12,y/3,40,80,4)-.5),x,y))}}
    // small pale moon
    for(let dy=-5;dy<=5;dy++)for(let dx=-5;dx<=5;dx++){const d=dx*dx+dy*dy;if(d>27)continue;p.put(MOONX+dx,MOONY+dy,d>20||dx<-2&&dy<-1?SW[6]:MOON)}
    p.put(MOONX+1,MOONY-1,SW[6]);p.put(MOONX-1,MOONY+2,SW[6]);
    // far treeline of dead sticks on the horizon
    {const r=rng(31);for(let i=0;i<17;i++){const x=4+i*9+fl(r()*5),h=8+fl(r()*16);
      for(let k=0;k<h;k++)p.put(x,HOR-1-k,SW[2]);
      for(const s of[-1,1]){const by=HOR-h*.55,len=3+fl(r()*5);for(let k=1;k<=len;k++)p.put(x+s*k,by-k*.7,SW[2])}}}
    // great dead tree on the right: gnarled trunk, branches, roots
    limb(p,[[118,224],[113,198],[120,170],[111,142],[117,114],[109,88],[114,62],[108,38]],15,3);
    limb(p,[[115,108],[100,100],[91,97],[84,92]],6,2);
    limb(p,[[117,120],[132,110],[146,98],[152,84]],5,2);
    limb(p,[[110,88],[98,74],[92,58],[88,46]],5,1);
    limb(p,[[111,84],[126,74],[139,60],[148,56]],5,1);
    limb(p,[[111,146],[96,156],[86,150],[80,156]],5,1);
    limb(p,[[119,172],[134,181],[146,174],[152,180]],5,1);
    limb(p,[[114,62],[124,48],[134,42],[142,34]],4,1);
    limb(p,[[109,40],[100,30],[96,20]],3,1);
    limb(p,[[91,97],[88,106],[90,112]],3,1);
    limb(p,[[132,110],[136,98],[134,90]],3,1);limb(p,[[98,74],[104,66],[103,58]],2,1);limb(p,[[139,60],[142,50]],2,1);
    limb(p,[[113,214],[98,222],[88,226],[80,224]],6,1);limb(p,[[116,218],[132,224],[144,228],[152,226]],6,1);
    limb(p,[[114,222],[106,230],[100,234]],4,1);limb(p,[[118,222],[124,231],[128,235]],4,1);
    // broken stump on the left
    limb(p,[[30,216],[27,196],[31,178],[28,164]],10,6);
    for(const[x,y]of[[24,162],[26,160],[29,159],[31,162],[33,160],[34,164]])disc(p,x,y,1);
    limb(p,[[28,186],[20,180],[14,181]],4,1);limb(p,[[29,196],[38,190],[42,192]],3,1);
    limb(p,[[30,214],[20,222],[12,224]],5,1);limb(p,[[30,214],[40,222],[48,224]],5,1);
    // reeds
    {const r=rng(52);for(let i=0;i<22;i++){const x=fl(r()*W),y=208+fl(r()*26),h=8+fl(r()*16),l=r()<.5?-1:1;
      if((x>76&&x<158&&y<230)||(x>8&&x<54&&y<228))continue;
      for(let k=0;k<h;k++)sil(p,x+l*(k>>3),y-k,INK);if(i%3===0){for(let k=0;k<3;k++)sil(p,x+l*(h>>3),y-h-k,INK)}}}
    // rim light on the moon side
    for(let y=14;y<236;y++)for(let x=2;x<W;x++)if(mask[y*W+x]===0&&mask[y*W+x-1]!==0&&(x+y)%2===0&&(x>70||x<50))p.put(x,y,BRIM);
    self.base=p;
  }
  function wispPos(w,u){return[w.x0+w.amp*Math.sin(TAU*(1.5*u+w.sw)),214-168*u]}
  function skull(p,sx,sy,f){
    const S=['.XXXXX.','XXXXXXX','XEXXXEX','XEXXXEX','.XXNXX.','.X.X.X.'];
    for(let j=0;j<6;j++)for(let i=0;i<7;i++){const ch=S[j][i];if(ch==='.')continue;
      const col=ch==='E'?(hash(f*7+i+j)>.4?GR[2]:GR[1]):ch==='N'?INK:(i>4&&j<4?BONE[0]:i<2&&j<3?BONE[2]:BONE[1]);
      for(let dy=0;dy<2;dy++)for(let dx=0;dx<2;dx++)p.put(sx-7+i*2+dx,sy-6+j*2+dy,col)}
  }
  function draw(p,f,N){
    const t=f/N;
    for(let y=MOONY-20;y<MOONY+20;y++)for(let x=MOONX-22;x<=MOONX+22;x++){const d=Math.hypot(x-MOONX,y-MOONY);if(d>20||d<5)continue;mt(p,x,y,SW[3],Math.pow(1-d/20,1.8)*.4,.5)}
    // fog: near-black banks, one dim sickly band low down
    const layers=[{P:52,sx:13,sy:4.6,seed:3,thr:.62,gain:2.2,col:SW[3]},{P:78,sx:13,sy:3.8,seed:9,thr:.64,gain:2.4,col:SW[4]}];
    for(const L of layers)for(let y=70;y<HOR+8;y++){const q=clamp((y-70)/100),wy=q*q*(3-2*q),gl=Math.exp(-Math.pow((y-150)/22,2));
      for(let x=0;x<W;x++){if(mask[y*W+x]===0)continue;
        const d=tnoise((x+L.P*t)/L.sx,y/L.sy,L.P/L.sx,64,L.seed),m=tnoise(x/40,y/22,8,64,L.seed+7),v=d*.7+m*.5-L.thr;
        if(v>0)p.tint(x,y,gl>.35?SW[5]:L.col,Math.min(v*L.gain*(.15+.5*wy+.6*gl),.4),.6)}}
    // dark water: lantern reflection wobbling, thin moon glints
    const step=fl(t*6),ang=.2*Math.sin(TAU*t),sx=PIV[0]+ROPEL*Math.sin(ang),sy=PIV[1]+ROPEL*Math.cos(ang);
    for(let y=HOR+2;y<H-2;y++){const v=(y-HOR)/(H-HOR),w=Math.round(2.4*Math.sin(TAU*(2*t+y*.21)));if(y%2)continue;
      const a=Math.max(0,.5-v*.5),ln=3+Math.round(8*v);for(let i=-ln;i<=ln;i++)if(hash(i*13+y*7+step)>.3)p.dput(sx+i+w,y,i*i<ln*ln*.3?GR[1]:GR[0],a)}
    for(let y=HOR+3;y<HOR+40;y+=3){if(hash(y*5+step*3)<.5)continue;const ln=2+fl(hash(y+step)*5),x0=MOONX-3+fl(hash(y*3+step)*8)-ln/2;
      for(let i=0;i<ln;i++)p.put(x0+i,y,SW[5],.5)}
    // curse runes: slow fade in and out, 5x5
    MARKS.forEach(m=>{const a=Math.max(0,Math.sin(TAU*(t+m.ph)));if(a<.08)return;
      for(let j=0;j<5;j++)for(let k=0;k<5;k++)if(RUNES[m.g][j][k]==='#')p.dput(m.x+k,m.y+j,a>.7?PU[4]:PU[3],Math.min(1,a*1.3));
      for(let q=0;q<18;q++){const th=q*TAU/18;p.dput(m.x+2+Math.cos(th)*6,m.y+2+Math.sin(th)*6,PU[1],a*.7)}});
    // soul wisps
    for(const w of WISPS){const age=frac(t-w.ph);if(age>=w.lf)continue;const u=age/w.lf,a=u<.12?u/.12:u>.55?(1-u)/.45:1;
      const cols=w.pu?[PU[4],PU[3],PU[2]]:[GR[2],GR[1],GR[0]];
      for(let k=7;k>=1;k--){const[x,y]=wispPos(w,Math.max(0,u-k*.013));p.dput(x,y,cols[k<3?1:2],a*(1-k/8))}
      const[hx,hy]=wispPos(w,u);p.put(hx,hy,cols[0],a);p.put(hx+1,hy,cols[0],a*.8);p.dput(hx,hy-1,cols[1],a*.9);
      for(const[dx,dy]of[[-1,0],[2,0],[0,1],[1,1],[0,-2]])p.dput(hx+dx,hy+dy,cols[2],a*.5)}
    // skull lantern swaying from the dead branch
    const fk=.34+.16*hash(f*11+3);
    for(let y=Math.round(sy-30);y<=sy+30;y++)for(let x=Math.round(sx-30);x<=sx+30;x++){const d=Math.hypot(x-sx,y-sy);if(d>=30||d<7)continue;
      mt(p,x,y,d<14?GR[1]:GR[0],Math.pow(1-d/30,1.5)*fk*1.9,.5)}
    line(p,PIV[0],PIV[1]+1,sx,sy-7,ROPE);
    skull(p,Math.round(sx),Math.round(sy),f);
    for(let k=1;k<=3;k++)p.dput(sx+((f>>2)%2?1:-1),sy+8+k*2+((f*2)%5),GR[1],.7-k*.2);
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== DEMONOLOGY: fel summoning circle in a crypt ================================== */
(()=>{
  const self={cls:'WARLOCK',tree:2,id:'warlock_demonology',name:'DEMONOLOGY'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const ST=c.ramp(['#05020c','#0a0418','#120a28','#12083a','#1c1048','#2a1a60']);
  const FEL=c.ramp(['#0a2a2a','#0e4a40','#13785e','#1fb088','#43ffb4','#b8ffe8']);
  const PK=['#4a0a38','#b01a68','#ff2e97','#ffa0d0'].map(c),CH=['#1c1038','#3a2068','#5a3a98'].map(c);
  const HOR=76,CX=78,CY=152,RX=74,RK=.6;
  const ROWS=[];for(let j=0;j<10;j++)ROWS.push(Math.round(HOR+6*Math.pow(1.5,j)));
  const EMB=emberList(41,26,120,196,40,90,.5,.9),EMC=[FEL[5],FEL[4],FEL[3],FEL[1]];
  const CHAINS=[{x:16,len:96},{x:33,len:60},{x:122,len:62},{x:140,len:98}];
  const EYES=[{x:12,y:60,ph:.1,k:1},{x:66,y:56,ph:.5,k:2},{x:118,y:62,ph:.8,k:1},{x:90,y:50,ph:.3,k:1},{x:40,y:46,ph:.65,k:2},{x:138,y:52,ph:.9,k:1}];
  const line=(p,x0,y0,x1,y1,col,a)=>{const n=Math.max(Math.abs(x1-x0),Math.abs(y1-y0),1);for(let i=0;i<=n;i++)p.put(x0+(x1-x0)*i/n,y0+(y1-y0)*i/n,col,a)};
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<HOR){
        let g=.1+.09*tnoise(x/12,y/6,40,40,3);const row=fl(y/8),xo=(row%2)*10,brick=((x+xo)%20===0)||(y%8===0);if(brick)g-=.07;
        let pil=false;for(const px of[0,52,104,156])if(Math.abs(x-px)<=5)pil=true;
        if(pil){g=.34+(x%4===0?.05:0)-(Math.abs((x+2)%52)>=4?0:0);}
        let niche=false;for(const ac of[26,78,130]){const dx=x-ac;if(Math.abs(dx)<=20&&(y>=40?true:dx*dx/400+(y-40)*(y-40)/576<=1))niche=true}
        if(niche&&!pil)g=.02+.05*tnoise(x/10,y/8,40,40,4);
        p.put(x,y,ramp(ST,g,x,y))}
      else{
        const v=y-HOR,Z=v+26,X=(x-78)*26/Z,Xp=(x-1-78)*26/Z;let j=0;while(j<ROWS.length-1&&ROWS[j+1]<=y)j++;
        const col=fl(X/16),cp=fl(Xp/16),gap=y===ROWS[j]||col!==cp;
        let g=(.34+.22*h2(col,j,5))*(.5+.5*clamp(v/150));if(y===ROWS[j]+1)g+=.05;
        if(h2(x,y,9)>.994)g*=.4;
        p.put(x,y,gap?ST[0]:ramp(ST,g,x,y))}}
    // wall base shadow
    for(let y=HOR;y<HOR+5;y++)for(let x=0;x<W;x++)p.dput(x,y,ST[0],(1-(y-HOR)/5)*.8);
    self.base=p;
  }
  const P=(a,R)=>[CX+R*Math.cos(a),CY+R*RK*Math.sin(a)];
  function ring(p,R,col,a,dash,t){const n=Math.floor(R*5);for(let i=0;i<n;i++){if(dash&&((i+Math.round(12*t*dash))%12)>=6)continue;const th=i*TAU/n,s=Math.sin(th),k=.55+.45*(s+1)/2;
    const[x,y]=P(th,R);p.put(x,y,col,a*k)}}
  function draw(p,f,N){
    const t=f/N,pu=1+.2*Math.sin(TAU*t);
    for(let y=CY-54;y<CY+54;y++)for(let x=CX-86;x<CX+86;x++){const d=Math.hypot((x-CX)/(RX+12),(y-CY)/(RX*RK+8));if(d>=1)continue;
      p.tint(x,y,FEL[1],Math.pow(1-d,1.4)*.42*pu,.55)}
    for(const dr of[0,.9]){ring(p,73-dr,FEL[3],.95,0,t);ring(p,62-dr,FEL[2],.9,0,t)}ring(p,38,FEL[2],.9,-1,t);ring(p,30,FEL[1],.9,1,t);ring(p,37,FEL[1],.7,0,t);
    for(let k=0;k<24;k++){const th=k*TAU/24,[x0,y0]=P(th,62),[x1,y1]=P(th,73);if(k%2===0)line(p,x0,y0,x1,y1,FEL[2],.6)}
    // pentagram turning one fifth per loop
    const pts=[];for(let k=0;k<5;k++)pts.push(P(-Math.PI/2+TAU*(k/5+t/5),37));
    for(let k=0;k<5;k++){const a=pts[k],b=pts[(k+2)%5];line(p,a[0],a[1],b[0],b[1],FEL[4],.95)}
    for(const[x,y]of pts){p.put(x,y,FEL[5]);p.put(x+1,y,FEL[3]);p.put(x-1,y,FEL[3])}
    // glyph band, two slots a loop
    for(let k=0;k<12;k++){const th=(k+2*t)*TAU/12,[x,y]=P(th,67.5),a=.6+.4*(Math.sin(th)+1)/2;
      if(k%2===0){p.put(x,y,FEL[4],a);p.put(x-1,y,FEL[3],a);p.put(x+1,y,FEL[3],a);p.put(x,y-1,FEL[3],a);p.put(x,y+1,FEL[3],a)}
      else{for(const[dx,dy]of[[-1,-1],[1,-1],[0,0],[-1,1],[1,1]])p.put(x+dx,y+dy,FEL[4],a)}}
    p.put(CX,CY,FEL[5]);p.put(CX-1,CY,FEL[4]);p.put(CX+1,CY,FEL[4]);p.put(CX,CY-1,FEL[4]);p.put(CX,CY+1,FEL[4]);
    emberDraw(p,EMB,t,3,EMC);
    // chains, a two frame rattle in two short bursts
    const win=(f>=4&&f<10)||(f>=15&&f<19),odd=f&1;
    CHAINS.forEach((ch,ci)=>{for(let i=0;i*4<ch.len;i++){const y=i*4,sh=win?(odd?1:-1)*(i>6?1:0):0,x=ch.x+sh+(win&&ci%2?-sh*2*(i>10?1:0):0);
      if(i%2===0){for(const[dx,dy]of[[-1,1],[1,1],[-1,2],[1,2]])p.put(x+dx,y+dy,CH[1]);p.put(x,y,CH[2]);p.put(x,y+3,CH[1])}
      else for(let k=0;k<4;k++)p.put(x,y+k,k===0?CH[2]:CH[1])}
      const ex=ch.x,ey=ch.len;for(let i=-3;i<=3;i++){p.put(ex+i,ey+1,CH[1]);p.put(ex+i,ey+4,CH[0])}p.put(ex-3,ey+2,CH[1]);p.put(ex+3,ey+2,CH[1]);p.put(ex-3,ey+3,CH[1]);p.put(ex+3,ey+3,CH[1])});
    // imp eyes in the dark niches
    for(const e of EYES){const q=frac(t*e.k+e.ph);if(q<.07)continue;const dx=(q>.5&&q<.6)?1:0,a=.75+.25*Math.sin(TAU*(t+e.ph));
      for(const ex of[e.x+dx,e.x+4+dx]){p.put(ex,e.y,PK[2],a);p.put(ex+1,e.y,PK[3],a);p.dput(ex,e.y-1,PK[0],.7);p.dput(ex+1,e.y+1,PK[0],.7)}}
  }
  self.draw=draw;return TBG.add(self);
})();

/* ================================== DESTRUCTION: chaos rift tearing the sky ================================== */
(()=>{
  const self={cls:'WARLOCK',tree:3,id:'warlock_destruction',name:'DESTRUCTION'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#0a0418','#1a0418','#2a0626','#44083a','#6a0e50']);
  const MG=['#6a0e50','#b01a68','#ff2e97','#ff7ac0','#ffd0ec'].map(c),GN=['#0e4a1a','#2a8a2e','#7dff4a','#c8ff9a'].map(c);
  const VOID=c.ramp(['#07030e','#1a0418','#2a0626','#44083a','#6a0e50']);
  const ROCK=c('#07030e'),ROCK2=c('#1a0418');
  const LX=80,LY=88,LH=66,LW=21;           // lens centre, half height, half width at rest
  const cxAt=y=>LX+(y-LY)*.1+3*Math.sin(y/17);
  const open=t=>.8+.5*Math.pow(Math.max(0,Math.sin(TAU*(t-.08))),2);
  const hwAt=(y,o)=>{const u=(y-LY)/LH;if(u<=-1||u>=1)return 0;return LW*o*Math.pow(1-u*u,.85)*(.82+.36*h2(y,0,5))};
  const SP=[[8,56],[26,26],[46,38],[64,20],[98,28],[118,62],[138,36],[150,50]];
  const RIDGE=[];for(let x=0;x<W;x++){let m=0;for(const[sx,h]of SP){const v=h*(1-Math.abs(x-sx)/13);if(v>m)m=v}
    RIDGE.push(Math.round(200-Math.max(m,4+5*vn(x,11,2)))+(h2(x,3,1)>.8?1:0)-(m>10&&h2(x,9,2)>.9?2:0))}
  const FIRES=[{x:26,g:false},{x:64,g:true},{x:98,g:false},{x:138,g:true},{x:46,g:true},{x:118,g:false}].map((f,i)=>({...f,y:RIDGE[f.x]+1,id:i}));
  const STREAKS=[];{const r=rng(13);FIRES.forEach((fr,i)=>{for(let k=0;k<5;k++){const y0=48+r()*80,x0=cxAt(y0)+(r()-.5)*LW*1.4;
      STREAKS.push({x0,y0,x1:fr.x+(r()-.5)*5,y1:fr.y-1,lf:.5+r()*.25,ph:(i*5+k)/30+r()*.03,g:fr.g,big:r()>.6})}});
    for(let k=0;k<12;k++){const y0=40+r()*90,x0=cxAt(y0)+(r()-.5)*LW*1.6,x1=x0+(r()-.5)*70,gx=clamp(x1,2,W-3);STREAKS.push({x0,y0,x1:gx,y1:RIDGE[Math.round(gx)]-1,lf:.45+r()*.3,ph:r(),g:r()<.4,big:false})}}
  const SHARDS=[];{const r=rng(77);for(let i=0;i<9;i++){const y=LY-LH*.8+i*(LH*1.6/8)+(r()-.5)*6,side=i%2?1:-1;SHARDS.push({y:Math.round(y),side,gap:5+r()*14,w:2+fl(r()*3),h:3+fl(r()*5),ph:r()})}}
  const mask=new Uint8Array(W*H).fill(1);
  const line=(p,x0,y0,x1,y1,col,a)=>{const n=Math.max(Math.abs(x1-x0),Math.abs(y1-y0),1);for(let i=0;i<=n;i++)p.put(x0+(x1-x0)*i/n,y0+(y1-y0)*i/n,col,a)};
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y>=RIDGE[x]){p.put(x,y,(y===RIDGE[x]||h2(x,y,4)>.985)?ROCK2:ROCK);mask[y*W+x]=0;continue}
      p.put(x,y,ramp(SKY,Math.pow(y/RIDGE[x],1.6)*.5+.04*(tnoise(x/9,y/6,40,40,3)-.5),x,y))}
    // cracks in the ridge
    {const r=rng(5);for(let i=0;i<14;i++){const x=4+fl(r()*148);let y=RIDGE[x]+3;for(let k=0;k<6+fl(r()*8);k++){p.put(x+(k>>1)*(i%2?1:-1),y+k,ROCK2)}}}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N,o=open(t),a=TAU*t;
    // fire-lit cloud banks
    for(const L of[{P:52,sx:13,sy:5,seed:3,thr:.6,y0:6,y1:170},{P:78,sx:13,sy:4,seed:9,thr:.64,y0:30,y1:190}])for(let y=L.y0;y<L.y1;y++)for(let x=0;x<W;x++){if(mask[y*W+x]===0)continue;
      const d=tnoise((x+L.P*t)/L.sx,y/L.sy,L.P/L.sx,64,L.seed),m=tnoise(x/40,y/22,8,64,L.seed+7),v=d*.7+m*.5-L.thr;
      if(v>0){const near=Math.exp(-Math.abs(x-cxAt(y))/40);p.tint(x,y,MG[0],Math.min(v*3*(.2+.8*near),.55),.5)}}
    // glow around the hole
    for(let y=LY-LH-10;y<LY+LH+10;y++){const cx=cxAt(y),e=Math.max(0,1-Math.pow((y-LY)/(LH+12),2)),span=22+16*o*e;
      for(let x=Math.round(cx-span);x<=cx+span;x++){if(x<0||x>=W||y<0||mask[y*W+x]===0)continue;
        const d=Math.abs(x-cx)/span;p.tint(x,y,d<.4?MG[1]:MG[0],Math.pow(1-d,2)*.4*(.25+.75*e),.5)}}
    // cracks running out of the rim
    for(let i=0;i<7;i++){const y=LY-LH*.7+i*LH*1.4/6,side=i%2?1:-1,cx=cxAt(y),hw=hwAt(y,o);let x=cx+side*hw,yy=y;const len=Math.round((9+hash(i*5)*12)*(.8+.3*o));
      for(let k=0;k<len;k++){x+=side*(k%3===2?0:1);if(k%4===3)yy+=hash(i*11+k)>.5?1:-1;p.put(x,yy,k<len*.5?MG[3]:MG[2],1-k/len*.6)}}
    // the torn hole: bright core, swirling dark chaos, magenta and green
    for(let y=LY-LH;y<=LY+LH;y++){const hw=hwAt(y,o);if(hw<1)continue;const cx=cxAt(y),x0=Math.round(cx-hw),x1=Math.round(cx+hw);
      for(let x=x0;x<=x1;x++){const d=Math.abs(x-cx)/hw;
        if(d>.88){p.put(x,y,x<cx?GN[2]:MG[2]);continue}
        const n=tnoise(x/4+1.6*Math.cos(a),y/4+1.6*Math.sin(a),64,64,11),n2=tnoise(x/3-1.4*Math.sin(a),y/5+1.4*Math.cos(a),64,64,12);
        const core=Math.pow(clamp(1-d*2.4),1.4),v=clamp(.1+.55*n+core*.9);
        if(n2>.66&&d>.3)p.put(x,y,ramp(GN,clamp((n2-.66)*3),x,y));
        else p.put(x,y,ramp([...VOID,MG[1],MG[2],MG[3],MG[4]],v,x,y))}
      p.dput(x0-1,y,GN[1],.8);p.dput(x1+1,y,MG[1],.8)}
    // sky shards peeling off the rim
    for(const s of SHARDS){const y=s.y,hw=hwAt(y,o),cx=cxAt(y),drift=s.gap*(.8+.3*o)+1.5*Math.sin(TAU*(t+s.ph)),bx=Math.round(cx+s.side*(hw+drift)),by=y+Math.round(1.2*Math.sin(TAU*(t+s.ph)));
      for(let j=0;j<s.h;j++){const w=Math.max(1,Math.round(s.w*(1-j/s.h)));for(let i=0;i<w;i++){const x=bx+s.side*i;p.put(x,by+j,ROCK);if(i===0)p.put(x-s.side,by+j,MG[2],.85)}}}
    // fire raining out of the hole onto the spires
    for(const s of STREAKS){const age=frac(t-s.ph);if(age>=s.lf)continue;const u=age/s.lf,a2=u<.1?u/.1:1,e=u*u;
      const cols=s.g?[GN[3],GN[2],GN[1],GN[0]]:[MG[4],MG[3],MG[2],MG[0]];
      for(let q=0;q<13;q++){const uu=e-q*.011;if(uu<0)break;const x=s.x0+(s.x1-s.x0)*uu,y=s.y0+(s.y1-s.y0)*uu;
        if(q<3)p.put(x,y,cols[q],a2);else p.dput(x,y,cols[Math.min(3,q>>2)],a2*(1-q/14));if(s.big&&q<6)p.dput(x+1,y,cols[1],a2*.7)}
      if(u>.9){const sp=(u-.9)/.1;for(const[dx,dy]of[[-2,-1],[2,-1],[-1,-3],[1,-3],[0,-4]])p.dput(s.x1+dx*(1+sp),s.y1+dy*(1+sp),cols[1],1-sp)}}
    // flames catching where the streaks land
    for(const fr of FIRES){let heat=0;for(const s of STREAKS)if(Math.abs(s.x1-fr.x)<8){const u=frac(t-s.ph)/s.lf;if(u>=0&&u<1.0&&frac(t-s.ph)<s.lf+.18)heat=Math.max(heat,1-Math.abs(frac(t-s.ph)-s.lf)/.18*.5)}
      const hs=hash(f*13+fr.id*7),h=14+Math.round(3*Math.sin(TAU*(2*t+fr.id*.3))+(hs>.7?2:0)+3*heat),cols=fr.g?GN:MG,mw=10;
      for(let r=0;r<h;r++){const u=r/h,wid=Math.max(1,Math.round(mw*Math.pow(1-u,.75)));
        for(let i=0;i<wid;i++){const lean=Math.round(Math.sin(TAU*(t+r*.06+fr.id*.2))*u*2),x=fr.x-((wid-1)>>1)+i+lean,edge=(i===0||i===wid-1)&&wid>2;if(u>.35&&edge&&hash(x*5+r*3+f*7+fr.id)>.6)continue;
          p.put(x,fr.y-r,u<.25?(edge?cols[2]:cols[3]):u<.6?(edge?cols[1]:cols[2]):(edge?cols[0]:cols[1]))}}}
    // rock rim catching the light
    for(let x=0;x<W;x++){const near=Math.exp(-Math.abs(x-LX)/46),hs=hash(fl(x/3)*7+f*5);if(hs<.3+.5*near)p.put(x,RIDGE[x],(x*7+f)%5<2?GN[1]:MG[1],.8)}
  }
  self.draw=draw;return TBG.add(self);
})();
