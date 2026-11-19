/* B: HOLO BAY. A dark tech bay: panel wall with blinking LEDs, two light columns at the edges, a holo pedestal with rings
   rolling outward and motes rising, a scan line that sweeps the bay once per loop, data rain down the outer gutters. */
(()=>{
  const self={cls:'ANY',tree:2,id:'char_bay',name:'HOLO BAY'};const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const WALL=c.ramp(['#06030f','#0a0518','#0e0820','#140a2a']);
  const SEAM=c('#1e1240'),SEAM2=c('#2a1a58'),BOLT=c('#3a2470');
  const LED=c.ramp(['#1a3a4a','#20d8ff','#c8f8ff']),LEDP=c.ramp(['#4a1a3a','#ff4aa0']);
  const BEAM=c.ramp(['#0a1a30','#0e3050','#145a80','#20a0d0','#7ae8ff']);
  const FLOORC=c.ramp(['#05020c','#0a0518','#120a28','#1c1038']),FLINE=c('#2a1a58');
  const HOLO=c.ramp(['#0a2a40','#105070','#1a8ab0','#20d8ff','#b8f6ff']);
  const SCAN=c('#7ae8ff'),SCAN2=c('#1a6a90'),RAIN=c.ramp(['#12203a','#1a4a6a','#2a8ab0']);
  const FL=150,CX=80,PY=174;
  const LEDS=[];{const r=rng(5);for(let i=0;i<22;i++){const px=fl(r()*7),py=fl(r()*6);LEDS.push({x:12+px*20+(r()<.5?3:15),y:8+py*24+3,ph:r(),k:1+fl(r()*2),pink:r()>.8})}}
  const MOTES=emberList(9,26,150,178,30,90,.4,.8).map(m=>({...m,x:CX-26+((m.x/W)*52)}));
  const RAINC=[];{const r=rng(12);for(const x of[2,5,8,151,154,157])RAINC.push({x,ph:r(),len:4+fl(r()*6),gap:10+fl(r()*10)})}
  function build(){
    const p=new Px();
    for(let y=0;y<FL;y++)for(let x=0;x<W;x++){
      const v=.25+.5*(1-Math.abs(x-CX)/CX)*(1-y/FL*.4)+.15*(tnoise(x/12,y/12,40,40,3)-.5);
      p.put(x,y,ramp(WALL,clamp(v),x,y));
      const sx=(x-12)%20,sy=(y-8)%24;
      if(x>=12&&x<W-12&&(sx===0||sy===0))p.put(x,y,sx===0&&sy===0?BOLT:(sy===0?SEAM2:SEAM));
    }
    // the floor: plates in perspective, darker toward the viewer
    for(let y=FL;y<H;y++)for(let x=0;x<W;x++){
      const k=(y-FL)/(H-FL),z=30/(y-FL+1.5);const u=(x-CX)*z/6;
      p.put(x,y,ramp(FLOORC,.65-.5*k,x,y));
      if(fl((x-CX)*z/6)!==fl((x+1-CX)*z/6)||fl(z*1.1)!==fl(30/(y-FL+2.5)*1.1))p.dput(x,y,FLINE,.8-k*.3);
    }
    for(let x=0;x<W;x++)p.put(x,FL,SEAM2);
    self.base=p;
  }
  function draw(p,f,N){
    const t=f/N;
    for(const l of LEDS){const on=frac(l.k*t+l.ph)<.55;const pal=l.pink?LEDP:LED;p.put(l.x,l.y,on?pal[pal.length-1]:pal[0]);if(on&&!l.pink)p.put(l.x+1,l.y,LED[1])}
    // light columns at the two edges, breathing out of phase
    for(const[x0,ph]of[[14,0],[W-15,.5]]){const b=.55+.45*Math.sin(TAU*(t+ph));
      for(let y=0;y<FL;y++)for(let dx=-6;dx<=6;dx++){const a=Math.abs(dx);const v=(a===0?1:a===1?.75:Math.max(0,.5-a*.08))*b*(.75+.25*Math.sin(TAU*(y/48-t)));
        if(v>.05)p.dput(x0+dx,y,BEAM[Math.min(4,fl(v*5))],Math.min(1,v*1.6))}
      for(let dx=-8;dx<=8;dx++)for(let k=0;k<6;k++)p.dput(x0+dx,FL+k,BEAM[1],(1-Math.abs(dx)/9)*(1-k/6)*b)}
    // data rain in the outer gutters
    for(const r of RAINC){const per=r.len+r.gap;const off=fl(t*per*2);
      for(let y=0;y<FL;y++){const k=((y-off-fl(r.ph*per))%per+per)%per;if(k<r.len)p.put(r.x,y,RAIN[k===r.len-1?2:k>r.len/2?1:0])}}
    // the pedestal: a dark disc with a cyan rim and rings rolling outward from it
    const RX=34,RY=6;
    for(let y=PY-RY-1;y<=PY+RY+3;y++)for(let x=CX-RX-2;x<=CX+RX+2;x++){const e=Math.hypot((x-CX)/RX,(y-PY)/RY);
      if(e<.9)p.put(x,y,FLOORC[1]);else if(e<1.08)p.put(x,y,HOLO[3]);}
    for(let x=CX-RX;x<=CX+RX;x++){const e=Math.abs(x-CX)/RX;if(e<1)for(let k=1;k<=3;k++)p.put(x,PY+Math.round(RY*Math.sqrt(1-e*e))+k,k===1?HOLO[1]:FLOORC[2])}
    for(const ph of[0,1/3,2/3]){const u=frac(t+ph),R=1.1+u*.9,a=(1-u);
      for(let i=0;i<180;i++){const ang=TAU*i/180,x=CX+Math.cos(ang)*RX*R,y=PY+Math.sin(ang)*RY*R;if(y<FL)continue;p.dput(x,y,HOLO[a>.6?2:1],a*.9)}}
    // a faint cone of light up from the pedestal
    for(let y=60;y<PY;y++){const k=(PY-y)/(PY-60);const hw=RX*(1-k*.35);for(let x=fl(CX-hw);x<=CX+hw;x++)p.dput(x,y,HOLO[0],(1-k)*.35*(1-Math.abs(x-CX)/hw))}
    emberDraw(p,MOTES,t,0,[HOLO[4],HOLO[3],HOLO[2],HOLO[1]]);
    // the scan line: down the bay once per loop, a short trail above it
    const sy=fl(t*(H+16))-8;
    for(let x=0;x<W;x++){if(sy>=0&&sy<H)p.put(x,sy,SCAN);for(let k=1;k<=6;k++)if(sy-k>=0&&sy-k<H)p.dput(x,sy-k,SCAN2,(1-k/7)*.55)}
  }
  self.draw=draw;return TBG.add(self);
})();
