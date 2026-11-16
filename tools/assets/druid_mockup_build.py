#!/usr/bin/env python3
"""Build the Druid Gunsight design pages (untracked local mockups) from the SAME sprites the module ships.

    python3 tools/assets/druid_mockup_build.py [OUT_DIR]      (default: mockups/ at the repo root)

writes gunsight-class-module-druid-2026-11-16.html (the final design, every state, real size and 4x) and
gunsight-class-module-druid-concepts-2026-11-16.html (three divergent concepts, one picked). The pages embed the atlas, the single file
textures and the manifest, and run tools/assets/druid_mockup/composer.js, which draws the piece the way GunsightDruid.lua does.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def load_generator():
    spec = importlib.util.spec_from_file_location("druid_gen", HERE / "generate_druid_gunsight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def png(w: int, h: int, rgba: bytearray) -> bytes:
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def rgba_from_bgra(px: bytearray) -> bytearray:
    out = bytearray(len(px))
    for i in range(0, len(px), 4):
        out[i], out[i + 1], out[i + 2], out[i + 3] = px[i + 2], px[i + 1], px[i], px[i + 3]
    return out


def data_uri(b: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(b).decode()


def build_data(g) -> dict:
    sprites = g.build()
    atlas = rgba_from_bgra(g.raster_atlas(g.ATLAS_SIZE, sprites))
    man = {"SCALE": g.SCALE, "GEOM": g.GEOM, "SLASH_ART": [g.SL_OX, g.SL_OY], "sprites": {}, "FILEDATA": {}}
    for s in sprites:
        man["sprites"][s.name] = [s.tx, s.ty, s.w, s.h, -s.x0, -s.y0]
    for name, (size, fn) in g.FILES.items():
        man["FILEDATA"][name] = data_uri(png(size[0], size[1], rgba_from_bgra(g.raster_file(size, fn()))))
    return {"atlas": data_uri(png(g.ATLAS_SIZE[0], g.ATLAS_SIZE[1], atlas)), "man": man}


CSS = """
@font-face{font-family:'Mononoki';src:url(../forever-stuwave/Media/Fonts/MononokiNerdFontMono-Bold.ttf) format('truetype');font-weight:100 900;font-style:normal;font-display:block}
:root{color-scheme:dark;--bg:#0d0620;--fg:#e9e2ff;--muted:#9d93c4;--white:#f3fbff;--violet:#a855f7;--cyan:#22e0ff;--amber:#ffb648;--gold:#ffd23f;--green:#39ff14;--pink:#ff4dd8;--warm:#ff3d1f;--edge:rgba(168,85,247,.35)}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg)}
body{max-width:1500px;padding:28px 30px 48px;color:var(--fg);font-family:'Mononoki',ui-monospace,monospace;font-weight:700;line-height:1.45}
h1{margin:0;font-size:30px;letter-spacing:.08em;color:var(--white);text-shadow:0 0 18px var(--green)}
.ref{display:inline-block;margin:10px 0 0;padding:2px 10px;font-size:13px;letter-spacing:.12em;color:var(--amber);border:1px solid rgba(255,182,72,.5);background:rgba(255,182,72,.06)}
.sub{margin:10px 0 22px;color:var(--muted);font-size:15px;max-width:1300px}
.sub b,.cap b,.panel b{color:var(--white)}
h2{margin:36px 0 10px;font-size:22px;letter-spacing:.1em;color:var(--white);text-shadow:0 0 12px var(--violet)}
h2 i{font-style:normal;color:var(--gold)}
h3{margin:18px 0 6px;font-size:16px;color:var(--cyan);letter-spacing:.08em}
canvas{display:block;image-rendering:pixelated;image-rendering:crisp-edges}
.frame{display:inline-block;border:1px solid var(--edge);background:#150a26}
.row{display:flex;flex-wrap:wrap;gap:22px;align-items:flex-start}
.tile .tc{margin-top:4px;font-size:12px;color:var(--muted);line-height:1.35}
.tile .tc b{color:var(--cyan);display:block;letter-spacing:.06em}
.cap{font-size:13px;color:var(--muted);max-width:520px}
.panel{border:1px solid var(--edge);background:rgba(26,16,37,.7);padding:12px 16px 14px;font-size:13px;line-height:1.5;max-width:1300px;margin-top:8px}
.panel li{margin-bottom:5px}
.verdict{border-color:rgba(57,255,20,.5);background:rgba(57,255,20,.05)}
.rej{border-color:rgba(255,61,31,.4)}
.real{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}
"""

PAGE_JS_COMMON = """
const ATLAS = new Image();
const FONT = "Mononoki, ui-monospace, monospace";
function ready(fn) { const imgs = [ATLAS]; ATLAS.src = ATLAS_URI; ATLAS.onload = () => document.fonts.load("700 12px Mononoki").then(() => setTimeout(fn, 60), () => setTimeout(fn, 60)); }
function pad(t0, period) { return Math.floor(t0 / period) * period; }
// the states of the design: each is a function of time (a looping event re-fires every `period` s)
const STATES = {
  moon: {
    idle:   (t) => ({ form: "moon", moon: { charges: 0, left: 0 } }),
    cue:    (t) => ({ form: "moon", moon: { charges: 2, left: 11.4 - (t % 6), grantAt: undefined } }),
    spend:  (t) => ({ form: "moon", moon: { charges: 2 + (Math.floor(t / 2.6) % 2 ? 0 : 0), left: 8, grantAt: pad(t, 2.6), spendAt: pad(t, 2.6) + 1.0 } }),
    held:   (t) => ({ form: "moon", moon: { charges: 0, left: 0, unknown: true } }),
    locked: (t) => ({ form: "moon", moon: { charges: 0, left: 0, locked: true } }),
  },
  cat: {
    idle:   (t) => ({ form: "cat", cat: { combo: 2, energy: 0.62, energyNum: 62, sp: "cool", spCd: (t % 8) / 8 } }),
    cue:    (t) => ({ form: "cat", cat: { combo: 5, energy: 0.34, energyNum: 34, sp: "ready", spCd: 1 } }),
    spend:  (t) => ({ form: "cat", cat: { combo: Math.floor(t % 3.2) < 1 ? 5 : 0, energy: 0.8, energyNum: 80, sp: "cool", spCd: 0.4, spendAt: pad(t, 3.2) + 1.0, spent: 5 } }),
    held:   (t) => ({ form: "cat", cat: { combo: null, secretCount: 3, secret: true, energy: 0.7, energyNum: null, sp: "ready", spCd: 1 } }),
    heldfull: (t) => ({ form: "cat", cat: { combo: null, secretCount: 5, secret: true, energy: 0.35, energyNum: null, sp: "cool", spCd: 0.5 } }),
  },
  bear: {
    idle:   (t) => ({ form: "bear", bear: { rage: 0.18, rageNum: 18, bite: "cool", biteCd: (t % 6) / 6, stacks: 3, lacLeft: 10 - (t % 6) } }),
    cue:    (t) => ({ form: "bear", bear: { rage: 0.52, rageNum: 52, bite: "ready", biteCd: 1, stacks: 5, lacLeft: 11 } }),
    urgent: (t) => ({ form: "bear", bear: { rage: 0.4, rageNum: 40, bite: "cool", biteCd: 0.5, stacks: 5, lacLeft: 2.4 } }),
    spend:  (t) => ({ form: "bear", bear: { rage: 0.14, rageNum: 14, bite: "cool", biteCd: ((t % 3) / 3), stacks: 4, lacLeft: 12, spendAt: pad(t, 3.0) + 0.6, lacAt: pad(t, 3.0) + 1.6 } }),
    held:   (t) => ({ form: "bear", bear: { rage: 0.6, rageNum: null, bite: "ready", biteCd: 1, stacks: 4, lacLeft: 9, unknown: false } }),
  },
  tree: {
    idle:   (t) => ({ form: "tree", tree: { rejuv: null, regrow: null, swift: "none", swiftCd: 0 } }),
    one:    (t) => ({ form: "tree", tree: { rejuv: Math.max(0.1, 9 - (t % 9)), regrow: null, swift: "cool", swiftCd: (t % 15) / 15 } }),
    cue:    (t) => ({ form: "tree", tree: { rejuv: 7.5, regrow: 15, swift: "ready", swiftCd: 1 } }),
    bloom:  (t) => ({ form: "tree", tree: { rejuv: Math.max(0.2, 3 - (t % 3.2)), regrow: 12, swift: "cool", swiftCd: 0.6, bloomAt: pad(t, 3.2) + 2.8 } }),
  },
  travel: { idle: (t) => ({ form: "travel" }) },
};
function mount(host, form, key, N, opts) {
  const cv = document.createElement("canvas");
  host.appendChild(cv);
  const d = new Druid(cv, MAN, ATLAS, N, FONT);
  d.reduced = !!(opts && opts.reduced);
  const fn = STATES[form][key];
  const t0 = performance.now();
  const loop = () => { const t = (performance.now() - t0) / 1000 + (opts && opts.t0 || 0); const S = fn(t); S.shiftAt = (opts && opts.shift) ? pad(t, 4) : undefined; d.render(S, t); requestAnimationFrame(loop); };
  loop();
  return d;
}
"""


def final_page(data: dict, composer: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=1500">
<title>Druid Wildshape Eyes</title><style>{CSS}</style></head><body>
<h1>GUNSIGHT CLASS MODULE, DRUID: WILDSHAPE EYES</h1>
<div class="ref">Design, 2026-11-16, final of three concepts (see the concepts page)</div>
<p class="sub">A pair of eyes watches from the thicket and <b>changes with the form</b>: owl eyes for the caster and Moonkin, slit eyes for the Cat, angry eyes
for the Bear, soft leaf eyes when a Restoration Druid targets a friend. Under them is <b>one gauge per form</b>: the Eclipse moons, five claw gashes with the energy
bar, the rage bar with its ability ticks, two heal over time lanes. The eyes go <b>hot</b> and the word under them says what to do now. Every sprite on this page is the baked art
the addon ships; the canvas is the module's own layout at 150 x 86 sprite px (the client draws a sprite px as 1.25 image px).</p>

<h2><i>REAL SIZE //</i> 150 x 86 sprite px, one tile per form, ready state</h2>
<div class="real" id="real"></div>

<h2><i>1 //</i> CAT, energy and the five gashes</h2>
<div class="row" id="cat"></div>
<div class="panel"><ul>
<li><b>The gashes are the combo points.</b> Five parallel claw marks on one raking arc: dark engraved scratches that light amber to white hot, one per point. At five points they all
flare together and the eyes go hot with the word FINISH. In combat the count is secret on this client, so the gashes are lit by the ENGINE (a status bar per gash, each full only when the count reaches its slot) and the
flare is a bar that is full only at five: no word, but the glow still tells you. Out of combat, or if the count reads plain, the word and the spend streak play too.</li>
<li><b>Energy</b> is the bar below with a notch at 55 and the zone under it tinted: that is the Shifting Power window (it converts mana to 40 Energy, usable below full Energy, 8 s cooldown). The chip at the right is the cooldown: it fills from the bottom while it recharges and glows cyan when ready.
SHIFT shows only when a plain energy read says it is under the notch.</li>
<li><b>Spending</b> (Rip or Ferocious Bite cast): the lit gashes flash white and a rake streak crosses them, then they go dark.</li>
</ul></div>

<h2><i>2 //</i> MOONKIN and caster, the Eclipse moons</h2>
<div class="row" id="moon"></div>
<div class="panel"><ul>
<li><b>Four sockets, lit left to right.</b> A Wrath banks two charges, a Starfire spends one, they run out 15 s after the last grant (the thin bar under them is that clock). All of it is a ledger from your own casts, so the seconds
carry a ~. With at least one moon lit the eyes go hot and the word flips from WRATH to STARFIRE. A spent moon flashes and scatters. Below level 30 the sockets are dotted and say ECLIPSE L30; after a reload in combat they are dim with a ? until a cast tells the truth.</li>
<li>A miss banks nothing but cannot be seen from the cast, so the ledger can over count after a resist. The eyes are honest about it: ~ on the time, and the ledger corrects at the next Starfire cast or at 15 s.</li>
</ul></div>

<h2><i>3 //</i> BEAR, rage, Primal Bite, Lacerate</h2>
<div class="row" id="bear"></div>
<div class="panel"><ul>
<li><b>The rage bar</b> is drawn by the engine (the rage number is secret in combat). Ticks under it mark what things cost: L Lacerate 15, B Primal Bite 20, M the Maul pool 35. The chip is Primal Bite's 6 s cooldown, filling from the bottom, glowing when ready.</li>
<li><b>Lacerate</b> is five pips (a ledger from your own casts, 15 s, ~). The cue order is the Method priority: LACERATE flashing amber when five stacks have 3 s or less, BITE when Primal Bite is ready, LACERATE while it is under five, otherwise BEAR.</li>
</ul></div>

<h2><i>4 //</i> RESTORATION, a friend in the sights</h2>
<div class="row" id="tree"></div>
<div class="panel"><ul>
<li>A friendly target in caster form swaps the Eclipse moons for two lanes: <b>Rejuvenation</b> (green, 12 s) and <b>Regrowth</b> (pink, 21 s), a ledger of your own casts on that target (~), and the Swiftmend flower, glowing when its 15 s cooldown is ready and one of your HoTs is on them.
A lane that ran its full time flashes (Bloom pays out at natural expiry). The word says which HoT to put on next.</li>
</ul></div>

<h2><i>5 //</i> TRAVEL, and the shift itself</h2>
<div class="row" id="misc"></div>
<div class="panel"><ul><li>Travel, Aquatic and Flight forms have no gauge: the owl eyes are half shut. Changing form closes the eyes in a flash with a ring of sparks, then they open as the new form (the second tile loops it, 4 s).</li>
<li><b>Reduced motion</b> (third tile): no blink, no breathing, no flash, no sparks; every state change still shows.</li></ul></div>

<script>
const ATLAS_URI = {json.dumps(data['atlas'])};
const MAN = {json.dumps(data['man'])};
{composer}
{PAGE_JS_COMMON}
function tile(host, title, text, form, key, N, opts) {{
  const d = document.createElement("div"); d.className = "tile";
  const f = document.createElement("div"); f.className = "frame"; d.appendChild(f);
  const c = document.createElement("div"); c.className = "tc"; c.innerHTML = "<b>" + title + "</b>" + text; d.appendChild(c);
  c.style.width = (150 * N) + "px";
  host.appendChild(d); mount(f, form, key, N, opts);
}}
ready(() => {{
  const real = document.getElementById("real");
  for (const [f, k] of [["cat", "cue"], ["moon", "cue"], ["bear", "cue"], ["tree", "cue"], ["travel", "idle"]]) tile(real, f.toUpperCase(), "", f, k, 1);
  const big = document.getElementById("real");
  const S = (id, items) => items.forEach(i => tile(document.getElementById(id), i[0], i[1], i[2], i[3], 3, i[4]));
  S("cat", [["IDLE", "2 points, energy 62, Shifting Power recharging", "cat", "idle"], ["READY", "five points: the gashes flare, FINISH", "cat", "cue"],
    ["SPENDING", "a finisher: streak and flash (loops)", "cat", "spend"], ["SECRET HELD", "combat: only the engine knows the count; no word", "cat", "held"],
    ["SECRET, FIVE", "the engine's flare at five points", "cat", "heldfull"]]);
  S("moon", [["IDLE", "no charges: WRATH", "moon", "idle"], ["READY", "two moons banked: STARFIRE, eyes hot", "moon", "cue"], ["SPENDING", "Wrath banks, Starfire spends (loops)", "moon", "spend"],
    ["UNKNOWN", "reload in combat: dim sockets and ?", "moon", "held"], ["LOCKED", "below level 30", "moon", "locked"]]);
  S("bear", [["IDLE", "rage 18, Primal Bite recharging, 3 stacks", "bear", "idle"], ["READY", "Primal Bite ready: BITE", "bear", "cue"], ["LACERATE DUE", "five stacks, 2.4 s: flashing amber", "bear", "urgent"],
    ["SPENDING", "a bite, then a Lacerate stack (loops)", "bear", "spend"], ["SECRET HELD", "rage drawn by the engine, no number", "bear", "held"]]);
  S("tree", [["NO HOTS", "REJUV", "tree", "idle"], ["ONE UP", "REGROWTH next", "tree", "one"], ["READY", "both up, Swiftmend ready", "tree", "cue"], ["BLOOM", "a HoT runs out: the lane flashes (loops)", "tree", "bloom"]]);
  S("misc", [["TRAVEL", "owl eyes half shut, no gauge", "travel", "idle"], ["THE SHIFT", "form change: eyes shut, flash, sparks (cat, loops)", "cat", "cue", {{shift: true}}],
    ["REDUCED MOTION", "cat, ready: still", "cat", "cue", {{reduced: true}}], ["4X", "cat ready at 4x", "cat", "cue"]]);
}});
</script></body></html>
"""


CONCEPT_JS = r"""
// Concepts A and B are drawn flat on a 150 x 86 canvas (plain canvas shapes, no baked art: they are sketches).
const CP = { bg: "#150a26", dim: "#3a2a5c", violet: "#a855f7", cyan: "#22e0ff", amber: "#ffb648", gold: "#ffd23f", green: "#39ff14", pink: "#ff4dd8", red: "#ff3d1f", white: "#f3fbff", muted: "#9d93c4" };
const FORMCOL = { moon: CP.cyan, cat: CP.gold, bear: CP.red, tree: CP.green };
function sketch(host, title, text, draw) {
  const d = document.createElement("div"); d.className = "tile";
  const f = document.createElement("div"); f.className = "frame"; d.appendChild(f);
  const cv = document.createElement("canvas"); cv.width = 150; cv.height = 86; cv.style.width = "450px"; cv.style.height = "258px"; f.appendChild(cv);
  const c = document.createElement("div"); c.className = "tc"; c.style.width = "450px"; c.innerHTML = "<b>" + title + "</b>" + text; d.appendChild(c);
  host.appendChild(d);
  const g = cv.getContext("2d"); g.imageSmoothingEnabled = false;
  const t0 = performance.now();
  const loop = () => { const t = (performance.now() - t0) / 1000; g.fillStyle = CP.bg; g.fillRect(0, 0, 150, 86); draw(g, t); requestAnimationFrame(loop); };
  loop();
}
function txt(g, s, x, y, col, size) { g.fillStyle = col; g.font = "700 " + (size || 8) + "px Mononoki, monospace"; g.textAlign = "center"; g.fillText(s, x, y); }
// A: the orrery, a round dial. ring pips = charges / points, arc = timer or energy, centre glyph = form
function orrery(form, st) {
  return (g, t) => {
    const cx = 40, cy = 43, col = FORMCOL[form];
    g.strokeStyle = CP.dim; g.lineWidth = 3; g.beginPath(); g.arc(cx, cy, 30, 0, 6.2832); g.stroke();
    g.strokeStyle = st.unknown ? CP.muted : col; g.lineWidth = 3; g.beginPath(); g.arc(cx, cy, 30, -1.5708, -1.5708 + 6.2832 * st.fill); g.stroke();
    const n = form === "moon" ? 4 : 5;
    for (let i = 0; i < n; i++) { const a = -1.5708 + i * 6.2832 / n; g.fillStyle = i < st.pips ? (st.hot ? CP.white : col) : CP.dim; g.beginPath(); g.arc(cx + Math.cos(a) * 21, cy + Math.sin(a) * 21, 3, 0, 6.2832); g.fill(); }
    g.fillStyle = col; g.globalAlpha = st.hot ? 0.6 + 0.4 * Math.sin(t * 6) : 0.5;
    if (form === "moon") { g.beginPath(); g.arc(cx, cy, 8, 0, 6.2832); g.fill(); g.fillStyle = CP.bg; g.beginPath(); g.arc(cx + 4, cy - 2, 7, 0, 6.2832); g.fill(); }
    else if (form === "cat") { for (let i = 0; i < 3; i++) g.fillRect(cx - 6 + i * 5, cy - 7 + i, 2, 14); }
    else { g.beginPath(); g.arc(cx, cy, 8, 0, 6.2832); g.fill(); }
    g.globalAlpha = 1;
    txt(g, st.word, 110, 44, st.hot ? CP.white : CP.muted, 9);
    if (st.spend) { g.fillStyle = CP.amber; for (let i = 0; i < 12; i++) g.fillRect(cx + Math.cos(i) * (6 + (t % 1) * 28), cy + Math.sin(i) * (6 + (t % 1) * 28), 1, 1); }
  };
}
// B: the heartwood branch, a horizontal vine. blossoms = charges / points, the thin line under = timer or energy
function branch(form, st) {
  return (g, t) => {
    const col = FORMCOL[form], y = 36;
    g.strokeStyle = "#5a3d2a"; g.lineWidth = 3; g.beginPath(); g.moveTo(6, y + 2); for (let x = 6; x <= 144; x += 6) g.lineTo(x, y + 2 + Math.sin(x / 9) * 3); g.stroke();
    const n = form === "moon" ? 4 : 5;
    for (let i = 0; i < n; i++) {
      const x = 22 + i * (106 / (n - 1)), lit = i < st.pips;
      g.fillStyle = lit ? (st.hot ? CP.white : col) : CP.dim; g.beginPath(); g.arc(x, y - 2 + Math.sin(x / 9) * 3, lit ? 5 : 3, 0, 6.2832); g.fill();
      if (st.spend && lit) { g.fillStyle = CP.amber; g.fillRect(x + ((t % 1) * 8), y - 10 - (t % 1) * 10, 1, 1); }
    }
    g.fillStyle = CP.dim; g.fillRect(14, 64, 122, 3);
    g.fillStyle = st.unknown ? CP.muted : col; g.fillRect(14, 64, Math.round(122 * st.fill), 3);
    txt(g, st.word, 75, 80, st.hot ? CP.white : CP.muted, 8);
    txt(g, form.toUpperCase(), 75, 12, col, 7);
  };
}
const CASES = {
  cat:  { idle: { pips: 2, fill: 0.62, word: "CAT", hot: false }, ready: { pips: 5, fill: 0.34, word: "FINISH", hot: true }, spend: { pips: 3, fill: 0.7, word: "CAT", hot: false, spend: true }, unknown: { pips: 0, fill: 0.5, word: "CAT", hot: false, unknown: true } },
  moon: { ready: { pips: 2, fill: 0.7, word: "STARFIRE", hot: true } },
  bear: { ready: { pips: 5, fill: 0.5, word: "BITE", hot: true } },
};
function conceptRow(id, make) {
  const h = document.getElementById(id);
  for (const k of ["idle", "ready", "spend", "unknown"]) sketch(h, "CAT " + k.toUpperCase(), "", make("cat", CASES.cat[k]));
  sketch(h, "MOON READY", "", make("moon", CASES.moon.ready));
  sketch(h, "BEAR READY", "", make("bear", CASES.bear.ready));
}
"""


def concepts_page(data: dict, composer: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=1500">
<title>Druid Gunsight Concepts</title><style>{CSS}</style></head><body>
<h1>GUNSIGHT CLASS MODULE, DRUID: THREE CONCEPTS</h1>
<div class="ref">Design, 2026-11-16, concepts before the final</div>
<p class="sub">The Druid has four forms, so the module has to be one idea that makes sense in all of them. The 150 x 86 sprite px box is the same for every concept, drawn here at 3x.
A and B are quick sketches (flat shapes, no baked art); C is drawn from the baked art the addon ships. Every concept is judged on the same four questions: can you read it at real size,
what does it tell you to do, does it look different from the other class modules (Shaman poles, Warrior rings, Hunter radar, Paladin seal, Mage sigils, Priest shield), and can it be fed by plain data in combat.</p>

<h2><i>A //</i> MOON ORRERY, a round dial</h2>
<div class="row" id="a"></div>
<div class="panel rej"><ul>
<li><b>What it is:</b> a ring dial. Pips round the rim are charges or points, the arc is a timer or the energy, the middle changes with the form (moon, claw, paw), a word to the right.</li>
<li><b>Readability:</b> good, a ring reads at any size. <b>Tells you to do:</b> only through a word; the dial itself does not point at an action.</li>
<li><b>Against the set:</b> too close to the Hunter radar and the Warrior rune ring, which are already round gauges. The form change is a glyph swap in the middle, which is small at 150 x 86.</li>
<li><b>Data:</b> fine, the same ledger and plain reads as the others. <b>Verdict: rejected</b>, it repeats a shape the set already has.</li></ul></div>

<h2><i>B //</i> HEARTWOOD BRANCH, a vine with blossoms</h2>
<div class="row" id="b"></div>
<div class="panel rej"><ul>
<li><b>What it is:</b> a horizontal branch. A blossom per charge or point lights up along it, a thin line underneath is the timer or energy.</li>
<li><b>Readability:</b> blossoms read, but the vine is decorative and the form is told only by the colour and a tiny label. <b>Tells you to do:</b> a word, no more.</li>
<li><b>Against the set:</b> distinct in shape, but the energy and the rage need their own separate bar, so it ends up as the usual bar plus dots, which is the shape the other modules already show.</li>
<li><b>Data:</b> fine. <b>Verdict: rejected</b>, weak form identity at a glance and half of it is a plain bar.</li></ul></div>

<h2><i>C //</i> WILDSHAPE EYES, picked</h2>
<div class="row" id="c"></div>
<div class="panel verdict"><ul>
<li><b>What it is:</b> a pair of eyes in the thicket that become the form: owl (caster and Moonkin), slit (Cat), angry (Bear), leaf (Restoration). A glyph between them, a cue word under them, one gauge below: Eclipse moons, five claw gashes with the energy bar, the rage bar and Lacerate pips, two HoT lanes. When there is something to do the eyes go hot.</li>
<li><b>Readability:</b> the eyes are the biggest thing on the tile and the form is told by their shape and colour before any text is read. The cue word is under them. At real size every part is whole sprite pixels.</li>
<li><b>Tells you to do:</b> yes: the hot eyes are the "now", the word is the "what" (WRATH, STARFIRE, FINISH, SHIFT, LACERATE, BITE, REJUV, REGROWTH, SWIFTMEND).</li>
<li><b>Against the set:</b> no other module has a face, and a form change is a transformation (eyes shut, flash, sparks) that no other module has. It is the class fantasy.</li>
<li><b>Data:</b> the combo gashes and the energy and rage bars are drawn by the engine from secret values (status bars), the words come only from plain reads and ledgers of your own casts. In combat with everything secret the face and gauge still draw, only the word stays calm. <b>Verdict: chosen.</b></li></ul></div>
<p class="sub">The final design at real size and 4x with every state is on the page <b>gunsight-class-module-druid-2026-11-16.html</b>.</p>

<script>
const ATLAS_URI = {json.dumps(data['atlas'])};
const MAN = {json.dumps(data['man'])};
{composer}
{PAGE_JS_COMMON}
{CONCEPT_JS}
function tile(host, title, text, form, key, N, opts) {{
  const d = document.createElement("div"); d.className = "tile";
  const f = document.createElement("div"); f.className = "frame"; d.appendChild(f);
  const c = document.createElement("div"); c.className = "tc"; c.innerHTML = "<b>" + title + "</b>" + text; d.appendChild(c);
  c.style.width = (150 * N) + "px";
  host.appendChild(d); mount(f, form, key, N, opts);
}}
ready(() => {{
  conceptRow("a", orrery); conceptRow("b", branch);
  const h = document.getElementById("c");
  tile(h, "CAT IDLE", "", "cat", "idle", 3); tile(h, "CAT READY", "", "cat", "cue", 3); tile(h, "CAT SPENDING", "", "cat", "spend", 3);
  tile(h, "CAT SECRET HELD", "", "cat", "held", 3); tile(h, "MOON READY", "", "moon", "cue", 3); tile(h, "BEAR READY", "", "bear", "cue", 3);
}});
</script></body></html>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "mockups"
    out.mkdir(parents=True, exist_ok=True)
    g = load_generator()
    data = build_data(g)
    composer = (HERE / "druid_mockup" / "composer.js").read_text(encoding="utf-8")
    (out / "gunsight-class-module-druid-2026-11-16.html").write_text(final_page(data, composer), encoding="utf-8")
    (out / "gunsight-class-module-druid-concepts-2026-11-16.html").write_text(concepts_page(data, composer), encoding="utf-8")
    print("wrote the final page and the concepts page in", out)


if __name__ == "__main__":
    main()
