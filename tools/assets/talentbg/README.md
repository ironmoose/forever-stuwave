# Talent spec backgrounds

Each talent tree gets a looping pixel-art scene behind it. Scenes are plain JavaScript (`scenes/<class>.js`) on the shared
helpers in `lib.js`; `bake.mjs` renders them into one flipbook sheet per spec in `forever-stuwave/Media/Textures/` and writes
the manifest `forever-stuwave/Modules/Skins/TalentBgArt.lua`. `Modules/Skins/TalentBackdrops.lua` plays them.

```
node tools/assets/talentbg/bake.mjs preview MAGE out.png 2 0,6,12,18   # contact sheet: rows = scenes, columns = frames
node tools/assets/talentbg/bake.mjs stats MAGE                         # colours and loop seam per scene
node tools/assets/talentbg/bake.mjs sheets                             # write every sheet and the manifest
node tools/assets/talentbg/bake.mjs check                              # exit 1 unless the committed files are current
```

## A scene

```js
(()=>{
  const self={cls:'MAGE',tree:1,id:'mage_arcane',name:'ARCANE'};   // cls = UnitClass token, tree = 1..3 left to right
  const c=palette();self.pal=c.list;self.init=()=>build();c.ramp(INKS);
  const SKY=c.ramp([...]), GLOW=c('#22e0ff');                     // every colour drawn is registered through c()
  function build(){const p=new Px(); /* static art */ self.base=p}
  function draw(p,f,N){const t=f/N; /* animated layers over a clone of base */}
  self.draw=draw;return TBG.add(self);
})();
```

`TBG.render(scene,f,N)` clones `base`, calls `draw`, then snaps every pixel to the scene's palette (so blends via `put(...,a)`
and `tint` land on registered colours). `scenes/warrior.js` is the reference for quality and technique.

## Family rules

- Canvas 156 x 236 low-res pixels, shown at an integer scale (about 3x) with NEAREST filtering. No antialiasing.
- A 3 s loop of 24 frames at 8 fps. Everything animated is a function of `t=f/N` that is periodic in `t` with period 1:
  `Math.sin(TAU*k*t)` with integer k, tileable noise `tnoise` scrolled by whole periods, particles from `emberList` (life
  phases wrap). The wrap step (frame 23 to 0) must look like any other step; `stats` prints it next to the median step.
- Bayer 4 x 4 dither (`dith`, `dput`, `tint`, `ramp`) for every gradient.
- Every scene registers the shared six step ink ramp `INKS` (#05020c to #3a2068) and adds one accent ramp of 8 to 12 colours
  plus a few spot colours, so all 27 trees read as siblings. Aim for 20 to 40 colours total.
- Talent icons (45 px square, cut corners, 4 columns x 7 rows) sit over the whole picture. The scene is a backdrop: the bulk
  of it stays dark (below the middle of its ramp), with small sparse brights (sparks, stars, glints, rims). One clear focal
  silhouette or motif, readable at a glance behind the icon grid.
- Motion is calm and continuous: drifting, swaying, pulsing, falling. One or two "events" per loop at most (a strike, a
  glint). No full-screen flashes brighter than the Warrior Fury lightning.
- Each class has one warm, one cold and one odd scene so the three trees side by side never look alike.
- Deterministic: only `hash`, `h2`, `rng(seed)`, `vn`, `tnoise`; never `Math.random`.
- Rendering all 24 frames of a scene should take under about 2 s in node.
