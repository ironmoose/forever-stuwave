/* A: NEON HORIZON. A striped sun setting behind wire-rim mountains, a perspective grid floor rolling toward the viewer, stars,
   and a pad ring under the character's feet that breathes once per loop. */
(()=>{
  const self={cls:'ANY',tree:1,id:'char_horizon',name:'NEON HORIZON'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp(['#05020c','#08031a','#0e0628','#160a36','#22093e','#320c48','#4a1052','#66165a']);
  const SUN=c.ramp(['#ffd27a','#ffb050','#ff8a48','#f2604e','#d83c62','#b0286e']);
  const HALO=c('#5a1258'),HALO2=c('#3a0c44');
  const MTN=c('#0c0618'),MTN2=c('#140a26'),RIM=c('#7a2a9a'),RIM2=c('#3a1a6a');
  const GLINE=c.ramp(['#1e0a36','#3a0e52','#6a1a72','#a02a86','#d83c9a']);
  const HORL=c('#ff7ad0'),HORC=c('#20d8ff'),FLOOR=c('#07030e');
  const PAD=c.ramp(['#0e3a5a','#1a7aa0','#20d8ff','#a8f4ff']);
  const STAR=c.ramp(['#3a2a78','#7a7ad0','#e0e6ff']);
  const HOR=116,SX=80,SY=HOR,SR=40,CX=80,PY=174;
  const back=[],front=[];
  for(let x=0;x<W;x++){
    back.push(HOR-fl(10+14*vn(x,23,3)+6*vn(x+90,9,4)));
    const e=Math.abs(x-CX)/CX;front.push(HOR-fl(Math.max(0,(e-.25))*44*(.55+.45*vn(x,11,7))));
  }
  const STARS=[];{const r=rng(17);for(let i=0;i<46;i++)STARS.push({x:fl(r()*W),y:fl(r()*(HOR-34)),ph:r(),k:1+fl(r()*3),b:r()})}
  function build(){
    const p=new Px();
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      if(y<HOR){const d=Math.hypot((x-SX)/1.6,(y-SY)*1.1);p.put(x,y,ramp(SKY,Math.pow(y/HOR,1.6)*.8+.25*Math.exp(-d*d/1800),x,y))}
      else p.put(x,y,FLOOR);
    }
    // sun halo, then the disc (the stripes are cut live)
    for(let y=SY-SR-10;y<SY;y++)for(let x=SX-SR-12;x<=SX+SR+12;x++){const d=Math.hypot(x-SX,y-SY);
      if(d>SR&&d<SR+10)p.dput(x,y,d<SR+4?HALO:HALO2,1-(d-SR)/10)}
    // mountains: the back range dim with a faint rim, the front range darker with a bright wire rim
    for(let x=0;x<W;x++){for(let y=back[x];y<HOR;y++)p.put(x,y,y===back[x]?RIM2:MTN2)}
    self.sun=p.clone();
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N;
    for(const s of STARS){const v=.5+.5*Math.sin(TAU*(s.k*t+s.ph));const col=STAR[s.b>.85?2:s.b>.5?1:0];if(v>.25)p.dput(s.x,s.y,col,v);
      if(s.b>.93&&v>.8){p.put(s.x-1,s.y,STAR[0]);p.put(s.x+1,s.y,STAR[0]);p.put(s.x,s.y-1,STAR[0]);p.put(s.x,s.y+1,STAR[0])}}
    // the sun: stripes roll down through the lower half, one band pitch per loop
    for(let y=SY-SR;y<SY;y++){const k=(y-(SY-SR))/SR;const band=SY-y;const gap=k>.45?fl((k-.45)*9):0;
      const ph=((y+fl(t*8))%8+8)%8;const cut=gap>0&&ph<Math.min(gap,5);
      for(let x=SX-SR;x<=SX+SR;x++){if(Math.hypot(x-SX,y-SY)>SR)continue;if(y>=back[x])continue;if(cut)continue;
        p.put(x,y,ramp(SUN,k,x,y))}}
    // front mountains over the sun
    for(let x=0;x<W;x++){for(let y=front[x];y<HOR;y++)p.put(x,y,y===front[x]?RIM:MTN);
      if(front[x]<HOR&&x>0&&front[x-1]!==front[x]){const a=Math.min(front[x],front[x-1]),b=Math.max(front[x],front[x-1]);for(let y=a;y<b;y++)p.put(x,y,RIM)}}
    // the floor grid: horizontal lines roll toward the viewer one spacing per loop; verticals fan from the vanishing point
    const zOf=y=>48/(y-HOR+.6);
    for(let y=HOR+1;y<H;y++){
      const z0=zOf(y),z1=zOf(y+1),near=clamp((y-HOR)/(H-HOR));
      const roll=a=>fl(a/2.2-t);const isRow=roll(z0)!==roll(z1);
      for(let x=0;x<W;x++){
        const u0=(x-CX)*z0/9,u1=(x+1-CX)*z0/9;const isCol=fl(u0)!==fl(u1);
        if(isRow||isCol){const k=near*(isRow?1:.8);p.put(x,y,GLINE[Math.min(4,fl(k*5))])}
        else if(dith(x,y,(1-near)*.35))p.put(x,y,GLINE[0]);
      }
    }
    for(let x=0;x<W;x++){p.put(x,HOR,Math.abs(x-SX)<SR+8?HORL:GLINE[2]);if(dith(x,HOR+1,.5))p.put(x,HOR+1,GLINE[1])}
    // the pad under the feet: a flat ellipse that breathes, two dots chasing round it
    const pulse=.5+.5*Math.sin(TAU*t),RX=40,RY=7;
    for(let y=PY-RY-2;y<=PY+RY+2;y++)for(let x=CX-RX-3;x<=CX+RX+3;x++){
      const e=Math.hypot((x-CX)/RX,(y-PY)/RY);
      if(e<.96)p.put(x,y,FLOOR);
      else if(e<1.12)p.put(x,y,PAD[1+fl(pulse*1.99)]);
      else if(e<1.35)p.dput(x,y,PAD[0],(1.35-e)/.23*(.4+.6*pulse));
    }
    for(const off of[0,.5]){const a=TAU*(t+off),x=CX+Math.cos(a)*RX,y=PY+Math.sin(a)*RY;p.put(x,y,PAD[3]);p.put(x+1,y,PAD[2]);p.put(x-1,y,PAD[2])}
  }
  self.draw=draw;return TBG.add(self);
})();
