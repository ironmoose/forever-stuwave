/* C: AURORA NIGHT. A night plain under a moving aurora (cyan into magenta), layered hills with a rim of moonlight, a lone
   standing stone, low fog drifting across the grass and fireflies. The calm, outdoorsy one. */
(()=>{
  const self={cls:'ANY',tree:3,id:'char_aurora',name:'AURORA NIGHT'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#03020a','#05030f','#080418','#0c0622','#120a2e']);
  const AUR=c.ramp(['#0a2a3a','#0e4a56','#14806e','#20c8a0','#5af0c8','#b8ffe8']);
  const AURP=c.ramp(['#2a0a3a','#5a1458','#a02a86','#e05ab0']);
  const STAR=c.ramp(['#3a2a78','#7a7ad0','#e0e6ff']);
  const H1=c('#0c0820'),H1R=c('#2a2a6a'),H2=c('#08051a'),H2R=c('#1e1a50'),H3=c('#05030f'),GR=c('#0a0718'),GR2=c('#120c26');
  const FOG=c.ramp(['#141030','#1e1a46','#2a2860']),STONE=c('#140e2c'),STONER=c('#3a3a80');
  const FLY=c.ramp(['#4a5a1a','#a8e04a','#efffa0']),MOON=c('#d8dcff'),MOON2=c('#8a90d0');
  const R1=[],R2=[],R3=[];
  for(let x=0;x<W;x++){R1.push(fl(112-10*vn(x,37,2)-6*vn(x,13,3)));R2.push(fl(132-12*vn(x+50,29,5)-4*vn(x,9,6)));R3.push(fl(156-6*vn(x+20,41,8)-3*vn(x,7,9)))}
  const STARS=[];{const r=rng(31);for(let i=0;i<70;i++)STARS.push({x:fl(r()*W),y:fl(r()*100),ph:r(),k:1+fl(r()*3),b:r()})}
  const FLIES=[];{const r=rng(44);for(let i=0;i<14;i++)FLIES.push({x:8+r()*144,y:150+r()*36,ax:4+r()*8,ay:2+r()*4,kx:1+fl(r()*2),ky:1+fl(r()*2),ph:r(),bp:r()})}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++)p.put(x,y,ramp(SKY,y/120,x,y));
    // a moon, small, upper right
    for(let dy=-5;dy<=5;dy++)for(let dx=-5;dx<=5;dx++){const d=dx*dx+dy*dy;if(d<=22)p.put(134+dx,22+dy,(dx+dy>3)?MOON2:MOON);else if(d<=40)p.dput(134+dx,22+dy,SKY[4],.6)}
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N;
    for(const s of STARS){const v=.55+.45*Math.sin(TAU*(s.k*t+s.ph));if(v>.3)p.dput(s.x,s.y,STAR[s.b>.88?2:s.b>.5?1:0],v)}
    // the aurora: a curtain hung from a wavy line, bright at its lower edge, fading up; hue drifts from teal to magenta across x
    for(let x=0;x<W;x++){
      const base=58+9*Math.sin(TAU*(x/90+t))+5*Math.sin(TAU*(x/41-2*t)+1.3)+3*Math.sin(TAU*(x/23+t)+.4);
      const str=.55+.45*Math.sin(TAU*(x/70-t)+.8);
      const pinkness=clamp((x-60)/90+.25*Math.sin(TAU*t));
      for(let y=fl(base-46);y<=base+2;y++){if(y<0)continue;const k=(base-y)/46;
        const ray=.65+.35*tnoise(x/2.5,(y/14)-t*2,64,8,4);
        let v=(k<0?1+k*3:Math.pow(1-k,1.6))*str*ray;if(v<.06)continue;
        const pal=dith(x,y,pinkness)?AURP:AUR;p.dput(x,y,pal[Math.min(pal.length-1,fl(v*pal.length))],Math.min(1,v*1.4))}
    }
    // hills, back to front, each with a moonlit rim
    for(let x=0;x<W;x++){
      for(let y=R1[x];y<H;y++)p.put(x,y,y===R1[x]?H1R:H1);
      for(let y=R2[x];y<H;y++)p.put(x,y,y===R2[x]?H2R:H2);
      for(let y=R3[x];y<H;y++)p.put(x,y,y<R3[x]+1?H2R:(dith(x,y,.18)?GR2:GR));
    }
    // a standing stone on the middle hill, left
    {const sx=26,sb=R2[26]+1;for(let y=sb-17;y<=sb;y++){const hw=y<sb-14?1:2;for(let dx=-hw;dx<=hw;dx++)p.put(sx+dx,y,dx===hw?STONER:STONE)}}
    // grass tufts on the near ground
    {const r=rng(52);for(let i=0;i<40;i++){const x=fl(r()*W),y=R3[x]+3+fl(r()*30);if(y>=H)continue;const sw=Math.sin(TAU*(t+r()))>.3?1:0;p.put(x,y,GR2);p.put(x+sw,y-1,GR2)}}
    // low fog: tileable noise drifting right, one whole period per loop
    for(let y=128;y<H;y++)for(let x=0;x<W;x++){const n=tnoise(x/16+t*10,y/5,10,40,7);const band=Math.exp(-Math.pow((y-164)/16,2));
      const v=(n-.45)*2.2*band;if(v>.05)p.tint(x,y,FOG[Math.min(2,fl(v*3))],Math.min(1,v),.55)}
    for(const fy of FLIES){const x=fy.x+fy.ax*Math.sin(TAU*(fy.kx*t+fy.ph)),y=fy.y+fy.ay*Math.sin(TAU*(fy.ky*t+fy.ph*2));
      const b=.5+.5*Math.sin(TAU*(2*t+fy.bp));if(b<.2)continue;p.put(x,y,FLY[b>.75?2:1]);if(b>.75){p.dput(x+1,y,FLY[0],.7);p.dput(x-1,y,FLY[0],.7)}}
  }
  self.draw=draw;return TBG.add(self);
})();
