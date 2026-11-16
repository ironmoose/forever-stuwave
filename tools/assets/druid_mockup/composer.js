// The Druid Gunsight piece, drawn from the baked sprites (DruidArt manifest MAN, atlas image ATLAS) the way
// GunsightDruid.lua draws it. One sprite px is N canvas px. State S (see STATES in the page):
//   form  "moon" | "cat" | "bear" | "tree" | "travel"      t  seconds      shiftAt  time of the last form change
//   moon: charges 0..4, left (s of 15), locked, unknown, spendAt, grantAt
//   cat : combo (0..5) or null (secret), energy (0..1), energyNum (number or null), sp ("ready" | "cool" | "none"), spCd (0..1), spendAt,
//         secret (combo and energy held by the engine only)
//   bear: rage (0..1), rageNum, bite ("ready" | "cool" | "none"), biteCd, stacks 0..5, lacLeft (s of 15), spendAt, lacAt, unknown, secret
//   tree: rejuv (s left of 12 or null), regrow (s left of 21 or null), swift ("ready" | "cool" | "none"), swiftCd, bloomAt, hotAt
const PAL = {
  out: "#120822", darkv: "#170c2a", midv: "#2a1846", line: "#3a2168", violet: "#a855f7", cyan: "#22e0ff", amber: "#ffb648",
  gold: "#ffd23f", warm: "#ff3d1f", red: "#ff3b4e", green: "#39ff14", pink: "#ff4dd8", white: "#f3fbff", muted: "#9d93c4",
};
const FORM_COLOR = { moon: PAL.cyan, cat: PAL.gold, bear: PAL.warm, tree: PAL.green, travel: PAL.muted };
const RJ_LEN = 12, RG_LEN = 21, LAC_LEN = 15, ECL_LEN = 15;

function mixHex(a, b, k) {
  const A = [1, 3, 5].map(i => parseInt(a.substr(i, 2), 16)), B = [1, 3, 5].map(i => parseInt(b.substr(i, 2), 16));
  return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * k).toString(16).padStart(2, "0")).join("");
}

class Druid {
  constructor(canvas, MAN, ATLAS, N, fontFamily) {
    this.cv = canvas; this.ctx = canvas.getContext("2d"); this.MAN = MAN; this.AT = ATLAS; this.N = N; this.G = MAN.GEOM;
    this.font = fontFamily; this.tints = {}; this.reduced = false; this.files = {};
    canvas.width = this.G.W * N; canvas.height = this.G.H * N;
    this.ctx.imageSmoothingEnabled = false;
  }
  file(name) { if (!this.files[name]) { const i = new Image(); i.src = this.MAN.FILEDATA[name]; this.files[name] = i; } return this.files[name]; }
  tint(name, color) {
    const key = name + color;
    if (this.tints[key]) return this.tints[key];
    const s = this.MAN.sprites[name], SC = this.MAN.SCALE;
    const c = document.createElement("canvas"); c.width = s[2] * SC; c.height = s[3] * SC;
    const x = c.getContext("2d"); x.imageSmoothingEnabled = false;
    x.drawImage(this.AT, s[0], s[1], s[2] * SC, s[3] * SC, 0, 0, s[2] * SC, s[3] * SC);
    x.globalCompositeOperation = "multiply"; x.fillStyle = color; x.fillRect(0, 0, c.width, c.height);
    x.globalCompositeOperation = "destination-in";
    x.drawImage(this.AT, s[0], s[1], s[2] * SC, s[3] * SC, 0, 0, s[2] * SC, s[3] * SC);
    return (this.tints[key] = c);
  }
  // sprite `name` with its origin at sprite px (x, y); color tints it (multiply), a alpha, flip mirrors it (the origin mirrors too)
  spr(name, x, y, color, a, flip) {
    const s = this.MAN.sprites[name], SC = this.MAN.SCALE, N = this.N, ctx = this.ctx;
    if (!s || a <= 0) return;
    const src = color ? this.tint(name, color) : null;
    ctx.globalAlpha = a === undefined ? 1 : a;
    const ox = flip ? s[2] - 1 - s[4] : s[4];
    const dx = (x - ox) * N, dy = (y - s[5]) * N, dw = s[2] * N, dh = s[3] * N;
    if (flip) { ctx.save(); ctx.translate(dx + dw, dy); ctx.scale(-1, 1); this.draw(src, s, SC, 0, 0, dw, dh); ctx.restore(); }
    else this.draw(src, s, SC, dx, dy, dw, dh);
    ctx.globalAlpha = 1;
  }
  draw(src, s, SC, dx, dy, dw, dh) {
    if (src) this.ctx.drawImage(src, 0, 0, s[2] * SC, s[3] * SC, dx, dy, dw, dh);
    else this.ctx.drawImage(this.AT, s[0], s[1], s[2] * SC, s[3] * SC, dx, dy, dw, dh);
  }
  // a baked file (a StatusBar's texture) with its box's top left at (x, y); frac crops it (horizontal from the left, vertical from the bottom)
  fileBar(name, x, y, wpx, hpx, frac, vertical, color, a) {
    const SC = this.MAN.SCALE, N = this.N, ctx = this.ctx, img = this.file(name);
    if (!(frac > 0)) return;
    frac = Math.min(1, frac);
    ctx.globalAlpha = a === undefined ? 1 : a;
    if (vertical) {
      const h = Math.round(hpx * frac);
      ctx.drawImage(img, 0, (hpx - h) * SC, wpx * SC, h * SC, x * N, (y + hpx - h) * N, wpx * N, h * N);
    } else {
      const w = Math.round(wpx * frac);
      ctx.drawImage(img, 0, 0, w * SC, hpx * SC, x * N, y * N, w * N, hpx * N);
    }
    ctx.globalAlpha = 1;
  }
  rect(x, y, w, h, color, a) { const N = this.N; this.ctx.globalAlpha = a === undefined ? 1 : a; this.ctx.fillStyle = color; this.ctx.fillRect(Math.round(x) * N, Math.round(y) * N, Math.round(w) * N, Math.round(h) * N); this.ctx.globalAlpha = 1; }
  text(str, x, y, color, px, align, a) {
    const N = this.N, ctx = this.ctx;
    ctx.globalAlpha = a === undefined ? 1 : a; ctx.fillStyle = color; ctx.font = `700 ${px * N}px ${this.font}`;
    ctx.textAlign = align || "left"; ctx.textBaseline = "middle"; ctx.fillText(str, x * N, y * N); ctx.globalAlpha = 1;
  }

  // ---- the cue: the word under the eyes and whether the eyes are hot ----
  cue(S) {
    const f = S.form;
    if (f === "travel") return { word: "TRAVEL", color: PAL.muted, hot: false };
    if (f === "moon") {
      if (S.moon.locked) return { word: "ECLIPSE L30", color: PAL.muted, hot: false };
      if (S.moon.unknown) return { word: "?", color: PAL.muted, hot: false };
      return S.moon.charges > 0 ? { word: "STARFIRE", color: PAL.gold, hot: true } : { word: "WRATH", color: PAL.cyan, hot: false };
    }
    if (f === "cat") {
      const c = S.cat;
      if (c.secret || c.combo === null) return { word: "CAT", color: PAL.muted, hot: false, engine: true };
      if (c.combo >= 5) return { word: "FINISH", color: PAL.amber, hot: true };
      if (c.sp === "ready" && c.energyNum !== null && c.energyNum < 55) return { word: "SHIFT", color: PAL.cyan, hot: true };
      return { word: "CAT", color: PAL.muted, hot: false };
    }
    if (f === "bear") {
      const b = S.bear;
      if (b.unknown) return { word: "?", color: PAL.muted, hot: false };
      if (b.stacks >= 5 && b.lacLeft <= 3 && b.lacLeft > 0) return { word: "LACERATE", color: PAL.amber, hot: true, blink: true };
      if (b.bite === "ready") return { word: "BITE", color: PAL.warm, hot: true };
      if (b.stacks < 5) return { word: "LACERATE", color: mixHex(PAL.warm, PAL.white, .25), hot: false };
      return { word: "BEAR", color: PAL.muted, hot: false };
    }
    const T = S.tree;
    if (T.rejuv === null) return { word: "REJUV", color: PAL.green, hot: true };
    if (T.regrow === null) return { word: "REGROWTH", color: PAL.pink, hot: false };
    if (T.swift === "ready") return { word: "SWIFTMEND", color: PAL.pink, hot: true };
    return { word: "HOTS UP", color: PAL.muted, hot: false };
  }

  render(S, t) {
    const G = this.G, ctx = this.ctx, N = this.N, red = this.reduced;
    ctx.clearRect(0, 0, this.cv.width, this.cv.height);
    const f = S.form, col = FORM_COLOR[f], cue = this.cue(S);
    const sinceShift = t - (S.shiftAt === undefined ? -9 : S.shiftAt);
    const shifting = !red && sinceShift >= 0 && sinceShift < 0.3;
    const breath = red ? 0.5 : 0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 3.2);
    // thicket
    this.spr("ivy", 1, 1, null, 0.9); this.spr("ivy", G.W - 2, 1, null, 0.9, true);
    this.spr("ivy_buds", 1, 1, col, 0.35 + 0.35 * breath); this.spr("ivy_buds", G.W - 2, 1, col, 0.35 + 0.35 * breath, true);
    // eyes
    const eyeForm = f === "travel" ? "moon" : f;
    let state = cue.hot ? "hot" : "open";
    if (f === "travel") state = "half";
    if (!red && f !== "travel") {
      const bp = (t + 1.3) % 4.6;
      if (bp > 4.3 && bp < 4.4) state = "half"; else if (bp >= 4.4 && bp < 4.5) state = "shut"; else if (bp >= 4.5 && bp < 4.6) state = "half";
    }
    if (shifting) state = sinceShift < 0.12 ? "shut" : "half";
    const glowA = cue.hot ? 0.28 + 0.3 * breath : (f === "travel" ? 0 : 0.1 + 0.08 * breath);
    for (const side of [0, 1]) {
      const ex = side ? G.EYE_R : G.EYE_L;
      if (state !== "shut" && glowA > 0) this.spr(`eye_${eyeForm}_glow`, ex, G.EYE_Y, col, glowA, !!side);
      this.spr(`eye_${eyeForm}_${state}`, ex, G.EYE_Y, f === "travel" ? mixHex(PAL.white, PAL.midv, .55) : null, 1, !!side);
    }
    if (shifting) {
      const k = 1 - sinceShift / 0.3;
      this.spr(`eye_${eyeForm}_glow`, G.EYE_L, G.EYE_Y, PAL.white, k, false); this.spr(`eye_${eyeForm}_glow`, G.EYE_R, G.EYE_Y, PAL.white, k, true);
      for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4 + 0.3, r = 4 + sinceShift * 70; this.rect(G.GLYPH_X + Math.cos(a) * r, G.GLYPH_Y + Math.sin(a) * r * 0.7, 1, 1, i % 2 ? col : PAL.white, k); }
    }
    this.spr(`glyph_${eyeForm}`, G.GLYPH_X, G.GLYPH_Y, col, f === "travel" ? 0.4 : (cue.hot ? 1 : 0.8));
    // the cue word
    const blinkOff = cue.blink && !red && (Math.floor(t * 4) % 2 === 1);
    if (cue.word && !blinkOff) this.text(cue.word, G.GLYPH_X, G.CUE_Y, cue.color, 8, "center", f === "travel" ? 0.7 : 1);

    if (f === "moon") this.moons(S, t, col);
    else if (f === "cat") this.claws(S, t, col);
    else if (f === "bear") this.paws(S, t, col);
    else if (f === "tree") this.lanes(S, t, col);
    else this.rect(G.MOON_X, G.DRAIN_Y + 3, 92, 1, PAL.line, 0.6);
  }

  moons(S, t, col) {
    const G = this.G, M = S.moon, red = this.reduced;
    const since = t - (M.spendAt === undefined ? -9 : M.spendAt), grant = t - (M.grantAt === undefined ? -9 : M.grantAt);
    for (let i = 0; i < G.MOON_N; i++) {
      const x = G.MOON_X + G.MOON_STEP * i, y = G.MOON_Y;
      if (M.locked) { this.spr("moon_dotted", x, y, null, 1); continue; }
      this.spr("moon_dark", x, y, null, M.unknown ? 0.5 : 1);
      const lit = !M.unknown && i < M.charges;
      if (lit) {
        const pop = !red && grant >= 0 && grant < 0.3 && i >= M.charges - 2 ? 1 - grant / 0.3 : 0;
        const hold = M.charges > 0 ? 0.35 + 0.2 * (red ? 0.5 : 0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 2.4)) : 0;
        this.spr("moon_glow", x, y, PAL.gold, hold + pop * 0.5);
        this.spr("moon_lit", x, y, mixHex(PAL.cyan, PAL.white, 0.25 + pop * 0.5), 1);
      } else if (!red && since >= 0 && since < 0.5 && i === M.charges) {
        const k = 1 - since / 0.5;
        this.spr("moon_lit", x, y, PAL.white, k); this.spr("moon_glow", x, y, PAL.gold, k);
        for (let j = 0; j < 6; j++) { const a = j * 1.05 + i, r = 3 + since * 26; this.rect(x + 9 + Math.cos(a) * r, y + 9 + Math.sin(a) * r, 1, 1, j % 2 ? PAL.gold : PAL.white, k); }
      }
    }
    // the drain: how long the banked charges last
    const x = G.DRAIN_X, y = G.DRAIN_Y;
    this.spr("track_drain", x, y, null, 1);
    if (!M.locked && !M.unknown && M.charges > 0) {
      const frac = Math.max(0, Math.min(1, M.left / ECL_LEN)), w = Math.round((G.DRAIN_W - 2) * frac), warn = M.left <= 3;
      const c = warn ? PAL.amber : PAL.cyan;
      this.rect(x + 1, y + 1, w, 5, mixHex(c, PAL.out, .35)); this.rect(x + 1, y + 1, w, 1, mixHex(c, PAL.white, .5));
      this.text("~" + Math.ceil(M.left) + "s", G.SECS_X, G.SECS_Y, warn ? PAL.amber : PAL.muted, 8, "left");
    } else if (!M.locked) this.text(M.unknown ? "?" : "0", G.SECS_X, G.SECS_Y, PAL.muted, 8, "left", 0.6);
  }

  claws(S, t, col) {
    const G = this.G, C = S.cat, red = this.reduced, SB = this.MAN.SLASH_ART;
    const since = t - (C.spendAt === undefined ? -9 : C.spendAt);
    const combo = C.combo === null ? (C.secretCount || 0) : C.combo;   // the engine shows a secret count; the mockup is told it
    const full = combo >= 5;
    for (let i = 0; i < G.SLASH_N; i++) {
      const x = G.SLASH_X + G.SLASH_STEP * i, y = G.SLASH_Y + G.SLASH_DY[i];
      this.spr("slash_dark", x, y, null, 1);
      if (i < combo) this.fileBar("druid_slash_lit", x, y, 16, 32, 1, false);
      if (full) this.fileBar("druid_slash_flare", x, y, 16, 32, 1, false, null, red ? 0.55 : 0.35 + 0.35 * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 0.9)));
    }
    if (!red && since >= 0 && since < 0.5) {
      const k = since / 0.5;
      for (let j = 0; j < 14; j++) { const px = G.SLASH_X + 4 + (G.SLASH_STEP * 4 + 10) * Math.min(1, k * 1.4) - j * 3; if (px > G.SLASH_X - 2) this.rect(px, G.SLASH_Y + 4 + j * 1.4, 1, 1, j % 2 ? PAL.amber : PAL.white, 1 - k); }
    }
    this.energy(C.energy, C.energyNum, 55, "druid_energy_fill", "track_energy", G.ENERGY_Y, 6, G.NUM_Y, t);
    this.chip("sp", C.sp, C.spCd, G.CHIP_X, G.CHIP_Y, PAL.cyan, t);
  }

  // the energy / rage bar: frame, fill cropped to frac, ticks, the shift zone, the number
  energy(frac, num, notch, fillFile, trackName, y, h, numY, t, rage) {
    const G = this.G, x = G.ENERGY_X;
    this.spr(trackName, x, y, null, 1);
    this.fileBar(fillFile, x + 1, y + 1, G.FILL_W, h, frac, false);
    const ix = x + 1;
    if (!rage) {
      this.rect(ix, y + 1, Math.round(G.FILL_W * notch / 100), 6, PAL.cyan, 0.13);
      this.rect(ix + Math.round(G.FILL_W * notch / 100), y + 1, 1, 6, PAL.cyan, 0.95);
    }
    for (let i = 1; i < 10; i++) if (!rage || true) this.rect(ix + Math.round(G.FILL_W * i / 10), y + h, 1, 1, PAL.line, 1);
    if (num !== null && num !== undefined) this.text(String(num), G.NUM_X, numY, PAL.white, 8, "left");
  }

  chip(kind, st, cd, x, y, glow, t) {
    const G = this.G;
    this.spr("chip_ring", x - 2, y - 2, st === "ready" ? glow : null, 1);
    if (st === "none") { this.spr("chip_" + kind, x, y, null, 0.35); return; }
    this.spr("chip_" + kind, x, y, null, 1);
    const fileName = { sp: "druid_chip_sp", pb: "druid_chip_pb", sm: "druid_chip_sm" }[kind];
    if (st === "ready") {
      this.fileBar(fileName, x, y, 16, 16, 1, true);
      const a = this.reduced ? 0.45 : 0.25 + 0.3 * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 1.6));
      this.spr("halo", x + 8, y + 8, glow, a);
    } else this.fileBar(fileName, x, y, 16, 16, cd, true);
  }

  paws(S, t, col) {
    const G = this.G, B = S.bear, red = this.reduced, x = G.RAGE_X, y = G.RAGE_Y;
    this.spr("track_rage", x, y, null, 1);
    this.fileBar("druid_rage_fill", x + 1, y + 1, G.FILL_W, 10, B.rage, false);
    const marks = [[15, "L"], [20, "B"], [35, "M"]];
    for (const [cost, ch] of marks) {
      const mx = x + 1 + Math.round(G.FILL_W * cost / 100);
      this.rect(mx, y + 1, 1, 10, PAL.white, 0.35);
      this.rect(mx, G.TICK_Y, 1, 3, PAL.muted, 1);
      const lit = B.rageNum !== null && B.rageNum !== undefined && B.rageNum >= cost;
      this.spr("letter_" + ch, mx - 1, G.LETTER_Y, lit ? (ch === "B" && B.bite === "ready" ? PAL.amber : PAL.white) : PAL.muted, lit ? 1 : 0.7);
    }
    if (B.rageNum !== null && B.rageNum !== undefined) this.text(String(B.rageNum), G.NUM_X, G.RAGE_NUM_Y, PAL.white, 8, "left");
    this.chip("pb", B.bite, B.biteCd, G.CHIP_X, G.RAGE_CHIP_Y, PAL.amber, t);
    // Lacerate stacks
    const since = t - (B.lacAt === undefined ? -9 : B.lacAt), warn = B.stacks >= 5 && B.lacLeft <= 3;
    for (let i = 0; i < 5; i++) {
      const px = G.PIP_X + G.PIP_STEP * i;
      this.spr("pip_dark", px, G.PIP_Y, null, B.unknown ? 0.5 : 1);
      if (!B.unknown && i < B.stacks) {
        const pulse = warn && !red && Math.floor(t * 4) % 2 === 1;
        this.spr("pip_lit", px, G.PIP_Y, pulse ? PAL.white : (warn ? PAL.amber : PAL.warm), 1);
        if (!red && since >= 0 && since < 0.3 && i === B.stacks - 1) this.spr("halo", px + 3, G.PIP_Y + 4, PAL.warm, (1 - since / 0.3) * 0.7);
      }
    }
    if (!B.unknown && B.stacks > 0) this.text("~" + Math.ceil(B.lacLeft) + "s", G.PIP_X + G.PIP_STEP * 5 + 4, G.PIP_Y + 4, warn ? PAL.amber : PAL.muted, 8, "left");
    // Primal Bite spend flash across the bar
    const bs = t - (B.spendAt === undefined ? -9 : B.spendAt);
    if (!red && bs >= 0 && bs < 0.4) this.rect(x + 1, y + 1, G.FILL_W, 10, PAL.white, (1 - bs / 0.4) * 0.6);
  }

  lanes(S, t, col) {
    const G = this.G, T = S.tree, red = this.reduced;
    const L = [[T.rejuv, RJ_LEN, PAL.green, "icon_rejuv", "rejuv"], [T.regrow, RG_LEN, PAL.pink, "icon_regrow", "regrow"]];
    for (let i = 0; i < 2; i++) {
      const [left, len, c, icon] = L[i], y = G.LANE_Y[i], up = left !== null;
      this.spr("track_lane", G.LANE_X, y, null, 1);
      const idle = !up && !red && Math.floor(t * 2) % 2 === 0;
      this.spr(icon, G.ICON_X, y - 1, up ? c : PAL.muted, up ? 1 : (idle ? 0.9 : 0.5));
      if (up) {
        const w = Math.round((G.LANE_W - 2) * Math.max(0, Math.min(1, left / len))), warn = left <= 3;
        const cc = warn ? PAL.amber : c;
        this.rect(G.LANE_X + 1, y + 1, w, 7, mixHex(cc, PAL.out, .4)); this.rect(G.LANE_X + 1, y + 1, w, 2, mixHex(cc, PAL.white, .45));
        for (let k = 1; k < 6; k++) this.rect(G.LANE_X + 1 + Math.round((G.LANE_W - 2) * k / 6), y + 1, 1, 7, PAL.out, 0.35);
        this.text("~" + Math.ceil(left) + "s", G.LANE_SECS_X, y + 4, warn ? PAL.amber : PAL.muted, 8, "left");
      } else this.text("--", G.LANE_SECS_X, y + 4, PAL.muted, 8, "left", 0.5);
    }
    const since = t - (T.bloomAt === undefined ? -9 : T.bloomAt);
    if (!red && since >= 0 && since < 0.5) this.rect(G.LANE_X + 1, G.LANE_Y[0] + 1, G.LANE_W - 2, 7, PAL.white, (1 - since / 0.5) * 0.7);
    this.chip("sm", T.swift, T.swiftCd, G.FLOWER_X + 2, G.FLOWER_Y + 8, PAL.pink, t);
  }
}
