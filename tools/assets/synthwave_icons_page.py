"""HTML for the synthwave icon style mockup (synthwave_icons.py hands it the rendered images).

The page is standalone: every image is inlined as base64 PNG once, in a JSON blob, and a
small script builds the tables and the in-context strips from it.
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1600">
<title>Synthwave Icon Styles</title>
<style>
@font-face{font-family:'Mononoki';src:url(../forever-stuwave/Media/Fonts/MononokiNerdFontMono-Bold.ttf) format('truetype');font-weight:100 900;font-style:normal;font-display:block}
:root{
  color-scheme:dark;
  --bg:#0d0620; --fg:#e9e2ff; --muted:#9d93c4; --white:#f3fbff; --text:#e2e8f0;
  --violet:#a855f7; --cyan:#22e0ff; --pink:#ff2e97; --red:#ff3b4e; --amber:#ffb648; --green:#39ff14;
  --track:#0a0416; --line:#3a2168; --plate:#140a24;
  --edge:rgba(168,85,247,.35);
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg)}
body{width:100%;max-width:1600px;padding:28px 30px 44px;color:var(--fg);font-family:'Mononoki',ui-monospace,monospace;font-weight:700;line-height:1.45;overflow-x:hidden}
h1{margin:0;font-size:30px;letter-spacing:.08em;color:var(--white);text-shadow:0 0 18px var(--violet);font-weight:700}
.ref{display:inline-block;margin:10px 0 0;padding:2px 10px;font-size:13px;letter-spacing:.12em;color:var(--amber);border:1px solid rgba(255,182,72,.5);background:rgba(255,182,72,.06)}
.sub{margin:10px 0 8px;color:var(--muted);font-size:15px;max-width:1500px}
.sub b{color:var(--white);font-weight:700}
h2{margin:36px 0 8px;font-size:22px;letter-spacing:.1em;color:var(--white);text-shadow:0 0 12px var(--violet);font-weight:700}
h2 i{font-style:normal;color:var(--pink)}
.cap{font-size:13px;line-height:1.5;color:var(--muted);margin:0 0 12px;max-width:1500px}
.cap b{color:var(--white);font-weight:700}
.legal{margin:14px 0 0;font-size:12px;color:var(--muted);max-width:1500px;border-left:2px solid var(--line);padding-left:10px}
table.styles{border-collapse:collapse;margin:14px 0 0;font-size:13px;width:100%;max-width:1540px}
table.styles td{border:1px solid var(--edge);padding:7px 12px;vertical-align:top;background:rgba(26,16,37,.55)}
table.styles td.l{width:44px;font-size:22px;text-align:center;color:var(--cyan);text-shadow:0 0 10px var(--cyan)}
table.styles td.n{width:190px;color:var(--white);letter-spacing:.06em}
table.styles td.c{color:var(--text)}
table.styles td.k{width:420px;color:var(--amber)}
table.grid{border-collapse:collapse;margin:8px 0 0}
table.grid th{font-size:12px;letter-spacing:.1em;color:var(--cyan);font-weight:700;padding:4px 8px;text-align:center;border-bottom:1px solid var(--edge)}
table.grid td{padding:6px 8px;border-bottom:1px solid rgba(58,33,104,.5);vertical-align:middle}
table.grid td.nm{font-size:12px;color:var(--white);width:150px;white-space:nowrap}
table.grid td.nm small{display:block;color:var(--muted);font-size:10px;font-weight:700}
.cellimgs{display:flex;gap:8px;align-items:center;justify-content:center}
.cellimgs img{display:block;background:var(--bg);outline:1px solid rgba(58,33,104,.8)}
.sizelab{font-size:9px;color:var(--muted);text-align:center;margin-top:2px;letter-spacing:.06em}
.rowlab{font-size:14px;letter-spacing:.1em;color:var(--white);margin:20px 0 6px;text-shadow:0 0 10px var(--violet)}
.rowlab i{font-style:normal;color:var(--pink)}
.rowlab small{font-size:12px;color:var(--muted);letter-spacing:0;text-shadow:none;margin-left:10px}
.strips{display:flex;flex-wrap:wrap;gap:22px 34px;align-items:flex-start}
.strip .tilesrow{display:flex;gap:4.8px}
.strip.z2 .tilesrow{gap:9.6px}
.panel{display:inline-block;border:1px solid var(--edge);background:#120a22;padding:6px}
.deck{display:inline-flex;padding:8px 10px 8px 4px;background:#120a22;border:1px solid var(--edge)}
.deck svg{display:block}
.note{font-size:12px;color:var(--muted);margin:8px 0 0;max-width:1500px}
.note b{color:var(--white);font-weight:700}
</style>
</head>
<body>
<h1>SYNTHWAVE ICON STYLES</h1>
<div class="ref">DESIGN REFERENCE / STYLE MOCKUP, 2026-10-14</div>
<p class="sub">the player's idea: <b>do not hand draw the tab and micro menu icons, restyle Blizzard's own</b>. Four ways to do it, shown on the six Shaman buff tab icons and the whole micro menu. Pick a style (or a style per surface) and the next phase bakes it. Everything below is at the real in game size unless a label says zoom; judge <b>32 px</b> for buff tiles and <b>16 px</b> for the micro menu.</p>
<table class="styles">
<tr><td class="l">A</td><td class="n">WIREFRAME</td><td class="c">Edge detected thin neon lines (violet weak, pink mid, cyan or element accent strong, white hot core) on a near black violet ground, soft glow.</td><td class="k">Baked .tga per icon and size, plus the regeneration script (tools/assets/synthwave_icons.py).</td></tr>
<tr><td class="l">B</td><td class="n">GRADIENT MAP</td><td class="c">Luminance mapped onto the STUwave ramp (deep violet, pink, accent), shapes kept, faint scanline.</td><td class="k">Baked .tga per icon and size, same script.</td></tr>
<tr><td class="l">C</td><td class="n">HYBRID</td><td class="c">B dimmed underneath with A's neon edges on top. The shape from B, the neon from A.</td><td class="k">Baked .tga per icon and size, same script.</td></tr>
<tr><td class="l">D</td><td class="n">RUNTIME TINT</td><td class="c">No baked art. The real icon, desaturated, vertex colour tinted, with an ADD glow overlay (simulated here with only what the client can do live: desaturate, vertex colour, one ADD texture; approximate, the client minifies bilinear).</td><td class="k">Free for any spell or item, now and later. No art, no script, nothing to bake or keep in sync.</td></tr>
</table>
<p class="legal">The derived art is made from Blizzard's icons: fine for personal use. If the addon is released publicly, style D avoids shipping copies of Blizzard art.</p>

<h2>01 <i>//</i> SHAMAN BUFF TAB ICONS</h2>
<p class="cap">Each cell: <b>64 px</b> and the real in game <b>32 px</b> side by side. Element accents per icon (earth green, fire pink and amber, frost ice, air lavender, lightning and water cyan); one house shape.</p>
<div id="shamanGrid"></div>

<div class="rowlab">IN CONTEXT <i>//</i> BUFF TAB TILES<small>38 px cut corner tile, violet ring, 32 px icon. Left is real size, right is 2x.</small></div>
<div class="strips" id="tabStrips"></div>

<h2>02 <i>//</i> MICRO MENU</h2>
<p class="cap">Source is the classic micro button art, cropped out of its frame (32x64 BLP, the glyph is only about 22x29 px, so it is soft when upscaled). Cells show <b>64</b>, <b>32</b> and the real <b>16 px</b>. First column is today's hand drawn glyph for comparison. The sources are the classic micro art, the modern micro menu atlas (Professions, Guild, Housing) and the PvP faction emblem. Character (a runtime portrait) and Legacy have no static art and are not shown.</p>
<div id="microGrid"></div>

<div class="rowlab">IN CONTEXT <i></i>MICRO MENU BAR<small>34x26 slanted keys, 16 px glyph, idle look from MicroBars.lua (edge alpha .35, soft LED at .6, glyph multiplied by the live #cfc4ef tint) with the accent cycling cyan, violet, pink. Real size, then 3x.</small></div>
<div id="deckStrips"></div>
<p class="note">Reading it at 16 px: <b>B</b> keeps the silhouettes best, <b>A</b> is the most neon but loses small detail, <b>C</b> sits between, and <b>D</b> is the cheapest but dim on dark sources. The slanted key plate is drawn from cell_slant geometry (lean 34% of the width). The classic art carries its own square dark backdrop, which shows inside the slanted key; a bake would mask it to the glyph.</p>

<script>
var DATA = __DATA__;
var STYLE_NAMES = {O:'ORIGINAL',A:'A WIREFRAME',B:'B GRADIENT',C:'C HYBRID',D:'D RUNTIME'};
var ORDER = ['O','A','B','C','D'];
function src(b64){return 'data:image/png;base64,'+b64;}
function el(tag,attrs,html){var e=document.createElement(tag);for(var k in attrs)e.setAttribute(k,attrs[k]);if(html!=null)e.innerHTML=html;return e;}
function imgTag(row,key,size,extra){return '<img width="'+size+'" height="'+size+'" src="'+src(row.img[key])+'" '+(extra||'')+'>';}

function grid(rows,sizes,host,withCurrent){
  var t='<table class="grid"><tr><th></th>'+(withCurrent?'<th>CURRENT</th>':'');
  ORDER.forEach(function(k){t+='<th>'+STYLE_NAMES[k]+'</th>';});
  t+='</tr>';
  rows.forEach(function(r){
    t+='<tr><td class="nm">'+r.label+''+'<small>'+r.family.replace('house_','house ')+'</small></td>';
    if(withCurrent){
      var c=DATA.current[r.key];
      t+='<td><div class="cellimgs">'+(c?'<div><img width="32" height="32" src="'+src(c)+'" style="image-rendering:pixelated"><div class="sizelab">16 x2</div></div><div><img width="16" height="16" src="'+src(c)+'"><div class="sizelab">16</div></div>':'<span class="sizelab">none</span>')+'</div></td>';
    }
    ORDER.forEach(function(k){
      t+='<td><div class="cellimgs">';
      sizes.forEach(function(s){t+='<div>'+imgTag(r,k+s,s)+'<div class="sizelab">'+s+'</div></div>';});
      t+='</div></td>';
    });
    t+='</tr>';
  });
  host.innerHTML=t+'</table>';
}
grid(DATA.shaman,[64,32],document.getElementById('shamanGrid'),false);
grid(DATA.micro,[64,32,16],document.getElementById('microGrid'),true);

// ---- buff tab tiles -------------------------------------------------------
var NS='http://www.w3.org/2000/svg';
function tileSvg(row,k,z){
  var s=z>=2?64:32, c=3;
  var poly=[[c,0],[38-c,0],[38,c],[38,38-c],[38-c,38],[c,38],[0,38-c],[0,c]].map(function(p){return p.join(',');}).join(' ');
  var id='cl'+Math.random().toString(36).slice(2,8);
  var cl=function(inset){return [[c,0],[38-c,0],[38,c],[38,38-c],[38-c,38],[c,38],[0,38-c],[0,c]].map(function(p){return p.join(',');}).join(' ');};
  return '<svg xmlns="'+NS+'" width="'+38*z+'" height="'+38*z+'" viewBox="0 0 38 38"><defs><clipPath id="'+id+'"><polygon points="'+poly+'"/></clipPath></defs>'+
    '<polygon points="'+poly+'" fill="rgba(13,6,32,.72)"/>'+
    '<image href="'+src(row.img[k+s])+'" x="3" y="3" width="32" height="32" clip-path="url(#'+id+')"/>'+
    '<polygon points="'+poly+'" fill="none" stroke="#a855f7" stroke-opacity=".75" stroke-width="1"/></svg>';
}
(function(){
  var host=document.getElementById('tabStrips');
  [1,2].forEach(function(z){
    var col=el('div',{},'');
    col.appendChild(el('div',{'class':'sizelab',style:'text-align:left;margin:0 0 4px;font-size:11px'},z==1?'REAL SIZE':'2x ZOOM'));
    ORDER.forEach(function(k){
      var w=el('div',{style:'margin:0 0 10px'},'');
      w.appendChild(el('div',{'class':'sizelab',style:'text-align:left;color:#22e0ff;font-size:11px;margin:0 0 3px'},STYLE_NAMES[k]));
      var p=el('div',{'class':'panel'},'');
      var s=el('div',{'class':'strip z'+z},'');
      var rr=el('div',{'class':'tilesrow'},'');
      DATA.shaman.forEach(function(r){rr.innerHTML+=tileSvg(r,k,z);});
      s.appendChild(rr);p.appendChild(s);w.appendChild(p);col.appendChild(w);
    });
    host.appendChild(col);
  });
})();

// ---- micro menu bar ---------------------------------------------------------
var ACC=['#22e0ff','#7C3AED','#ff2e97'];
var TINTF='<filter id="gt" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="0.812 0 0 0 0  0 0.769 0 0 0  0 0 0.937 0 0  0 0 0 1 0"/></filter>'+
  '<filter id="led" x="-40%" y="-200%" width="180%" height="500%"><feGaussianBlur stdDeviation="0.9"/></filter>';
// idle key, as MicroBars.lua ComputeVisual draws it: edge alpha .35, glyph multiplied by GLYPH_NORMAL #cfc4ef,
// LED a 20x5 soft glow (deck_led.tga, core about 15x2.5) at alpha .6
function keySvg(img,i,z,tint){
  var W=34,H=26,L=Math.round(W*0.34);
  var pts=[[L,0],[W,0],[W-L,H],[0,H]].map(function(p){return p.join(',');}).join(' ');
  var a=ACC[i%3];
  return '<svg xmlns="'+NS+'" width="'+(W*z)+'" height="'+(H*z)+'" viewBox="0 0 '+W+' '+H+'" style="margin-right:'+((3-L)*z)+'px"><defs>'+TINTF+'</defs>'+
    '<polygon points="'+pts+'" fill="#140a24" fill-opacity=".95"/>'+
    '<polygon points="'+pts+'" fill="none" stroke="'+a+'" stroke-opacity=".35" stroke-width="1"/>'+
    '<image href="'+img+'" x="'+((W-16)/2)+'" y="'+((H-16)/2)+'" width="16" height="16"'+(tint?' filter="url(#gt)"':'')+'/>'+
    '<rect x="'+(W/2-4-7.5)+'" y="'+(H-3.75)+'" width="15" height="2.5" rx="1.25" fill="'+a+'" fill-opacity=".6" filter="url(#led)"/></svg>';
}
(function(){
  var host=document.getElementById('deckStrips');
  var kinds=['CURRENT'].concat(ORDER);
  [1,3].forEach(function(z){
    host.appendChild(el('div',{'class':'sizelab',style:'text-align:left;margin:10px 0 4px;font-size:11px'},z==1?'REAL SIZE':'3x ZOOM'));
    kinds.forEach(function(k){
      var w=el('div',{style:'margin:0 0 8px'},'');
      w.appendChild(el('div',{'class':'sizelab',style:'text-align:left;color:#22e0ff;font-size:11px;margin:0 0 3px'},k=='CURRENT'?'CURRENT HAND DRAWN':STYLE_NAMES[k]));
      var d=el('div',{'class':'deck'},'');
      var html='';
      DATA.micro.forEach(function(r,i){
        var img;
        if(k=='CURRENT'){var c=DATA.current[r.key]; if(!c)return; img=src(c);}
        else img=src(r.img[k+(z>=3?64:16)]);
        html+=keySvg(img,i,z,k!='CURRENT');
      });
      d.innerHTML=html;w.appendChild(d);host.appendChild(w);
    });
  });
})();
</script>
</body>
</html>
"""


def build_page(data_json: str) -> str:
    return TEMPLATE.replace("__DATA__", data_json)
