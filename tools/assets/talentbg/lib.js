/* Shared helpers for the talent spec background scenes. Loaded as a plain script by bake.mjs (node vm) and preview.html.
   Every scene file calls TBG.add(scene); nothing here touches the DOM. */
const W=156,H=236,SC=3;
const TAU=Math.PI*2,fl=Math.floor;
const clamp=(v,a=0,b=1)=>v<a?a:v>b?b:v;
const frac=v=>v-fl(v);
const hexc=h=>[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];
const mixc=(a,b,t)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t];
function hash(n){let h=Math.imul(n|0,0x9E3779B1)^0x85EBCA6B;h=Math.imul(h^(h>>>15),0x2C1B3C6D);h=Math.imul(h^(h>>>12),0x297A2D39);h^=h>>>15;return(h>>>0)/4294967296}
const h2=(x,y,s)=>hash(Math.imul(x|0,73856093)^Math.imul(y|0,19349663)^Math.imul((s|0)+1,83492791));
function rng(seed){let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296}}
const BAYER=[[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]];
const dith=(x,y,v)=>v*16>BAYER[y&3][x&3]+0.5;
function vn(i,step,s){const k=fl(i/step),f=(i-k*step)/step,a=hash(k+s*977),b=hash(k+1+s*977),u=f*f*(3-2*f);return a+(b-a)*u}
/* tileable 2D value noise: lattice period px x py cells, so a loop that shifts a whole period is seamless.
   The lattice of hashed corner values is built once per (px, py, seed) and looked up per call. */
const LATC=new Map();
function lat(px,py,s){const k=(px*4099+py)*131+s;let L=LATC.get(k);
  if(!L||L.px!==px||L.py!==py||L.s!==s){const v=new Float64Array(px*py);for(let iy=0;iy<py;iy++)for(let ix=0;ix<px;ix++)v[iy*px+ix]=h2(ix,iy,s);L={px,py,s,v};LATC.set(k,L)}
  return L}
function tnoise(x,y,px,py,s){
  const L=lat(px,py,s),v=L.v,x0=fl(x),y0=fl(y),fx=x-x0,fy=y-y0;
  const ix=(((x0|0)%px)+px)%px,iy=(((y0|0)%py)+py)%py,jx=ix+1===px?0:ix+1,jy=iy+1===py?0:iy+1;
  const a=v[iy*px+ix],b=v[iy*px+jx],c=v[jy*px+ix],d=v[jy*px+jx];
  const sx=fx*fx*(3-2*fx),sy=fy*fy*(3-2*fy);
  return a+(b-a)*sx+(c-a)*sy+(a-b-c+d)*sx*sy;
}
function ramp(pal,t,x,y,sharp){const k=clamp(t)*(pal.length-1),lo=fl(k);let f=k-lo;if(sharp)f=clamp((f-.5)*sharp+.5);return lo>=pal.length-1?pal[pal.length-1]:(dith(x,y,f)?pal[lo+1]:pal[lo])}
class Px{
  constructor(){this.d=new Uint8ClampedArray(W*H*4);for(let i=3;i<this.d.length;i+=4)this.d[i]=255}
  clone(){const p=new Px();p.d.set(this.d);return p}
  put(x,y,c,a){x=fl(x);y=fl(y);if(x<0||y<0||x>=W||y>=H)return;const i=(y*W+x)<<2,d=this.d;
    if(a===undefined||a>=1){d[i]=c[0];d[i+1]=c[1];d[i+2]=c[2]}else if(a>0){d[i]+=(c[0]-d[i])*a;d[i+1]+=(c[1]-d[i+1])*a;d[i+2]+=(c[2]-d[i+2])*a}}
  dput(x,y,c,a){x=fl(x);y=fl(y);if(dith(x,y,a))this.put(x,y,c)}
  tint(x,y,c,a,s){x=fl(x);y=fl(y);if(dith(x,y,a))this.put(x,y,c,s===undefined?.5:s)}
}
/* a scene registers every colour it draws with, and the baked frame is snapped to that palette (limited palette, crisp pixels) */
function palette(){const set=[];const c=h=>{if(!set.includes(h))set.push(h);return hexc(h)};c.list=set;c.ramp=a=>a.map(c);return c}
const INKS=['#05020c','#0a0418','#120a28','#1c1038','#2a1850','#3a2068'];
function quantizer(hexes){
  const pal=hexes.map(hexc),lut=new Int16Array(1<<18).fill(-1);
  return{n:pal.length,apply(d){
    for(let i=0;i<d.length;i+=4){
      const r=d[i],g=d[i+1],b=d[i+2],key=((r>>2)<<12)|((g>>2)<<6)|(b>>2);let k=lut[key];
      if(k<0){let best=1e12;const rr=(r&~3)+2,gg=(g&~3)+2,bb=(b&~3)+2;
        for(let j=0;j<pal.length;j++){const p=pal[j],dr=rr-p[0],dg=gg-p[1],db=bb-p[2],e=3*dr*dr+4*dg*dg+2*db*db;if(e<best){best=e;k=j}}
        lut[key]=k}
      const p=pal[k];d[i]=p[0];d[i+1]=p[1];d[i+2]=p[2]}}}
}
/* particles with a life: a particle is up for `lf` of the loop starting at phase `ph`, so any loop length is seamless */
function emberList(seed,n,y0,y1,Dmin,Dmax,lf0,lf1){const r=rng(seed),a=[];for(let i=0;i<n;i++)a.push({x:r()*W,y:y0+r()*(y1-y0),D:Dmin+r()*(Dmax-Dmin),lf:lf0+r()*(lf1-lf0),ph:r(),sw:r()*TAU,k:1+fl(r()*2),big:r()>.86});return a}
function emberDraw(p,list,t,wind,cols){
  for(const e of list){
    const age=frac(t-e.ph);if(age>=e.lf)continue;const u=age/e.lf;
    let x=e.x+wind*u+2.4*Math.sin(TAU*(e.k*u*.5+e.sw)),y=e.y-e.D*u;x=((x%W)+W)%W;
    const a=u<.12?u/.12:u>.62?(1-u)/.38:1,col=cols[Math.min(cols.length-1,fl(u*cols.length))];
    p.dput(x,y,col,a);if(e.big){p.dput(x+1,y,col,a*.6);p.dput(x,y-1,col,a*.6)}}
}

/* scene registry: cls is the class token (UnitClass second return), tree is the talent tree index left to right (1..3) */
const TBG={scenes:[],add(s){if(!s.cls||!s.tree||!s.id)throw new Error('scene needs cls, tree, id');this.scenes.push(s);return s},
  prepare(s){if(!s.base){s.init();s.q=quantizer(s.pal)}},
  render(s,f,N){TBG.prepare(s);const p=s.base.clone();s.draw(p,f,N);s.q.apply(p.d);return p.d}};
