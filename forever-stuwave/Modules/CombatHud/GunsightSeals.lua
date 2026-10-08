-- Forever STUwave: Gunsight Seal Chamber chrome (the Paladin's class slot, piece key "dot").
--
-- The Paladin's seat of the DoT area (mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html,
-- drawSealChamber, lines 2099 to 2255; the dispatch at 2361 is CLS==='pl' ? drawSealChamber : drawDots).
-- GunsightDots.lua gives the seat away for a profile whose FS.HudProfiles.ClassSlot is "seals": it builds the
-- piece frame (ForeverSTUwaveGunsightDots, exposed as FS.GunsightDots.frame) and registers it under "dot" but
-- draws nothing. This file hangs the chamber off that frame, so the console's dot key shows and hides it.
--
-- Lane 7 built the static chrome, lane 8 drives it live from the Hud state, lane 9 makes the Judgement lane live.
--   built   the chamfered frame (fill, edge, halo, the seal's soft radial wash), the "SEAL" header, the 0 to 30 s
--           ruler on the left edge (31 ticks, numbers at the fives), the lens ring (seal_lens.tga) and its three
--           arcs (seal_arcs.tga, at rest), the glyph (seal_glyph_<id>.tga) with a dim halo copy, the seal name,
--           the "SEAL ACTIVE" caption, the amber reseal band (RESEAL), the drain tube (track, rungs, outline),
--           the NO SEAL labels, and the Judgement lane's geometry (JUDGED header, 0 to 40 s ruler, guide, the
--           empty-lane label).
--   LIVE    (drawSealChamber's animated terms, all from own cast times: remaining = expiresAt - GetTime(), both
--           plain, a secret or non number reads as unknown and draws nothing for that part)
--           the drain fill (the seal colour, tail .35 to tip 1, height remaining / 30 s) with its tip bar and tip dot;
--           the countdown (whole seconds above 5, tenths from 5 down) and its muted S; the RESEAL band cue at 3 s
--           (amber tube, fill, tip and number, the wash pulsing with the clock, RESEAL breathing with the pulse); the
--           strike up flicker on a fresh cast (castAt) and the dying tube in the last 5 s (sealNeon: dropouts that get
--           likelier and deeper), both through one neon level that scales every neon driven part; EXPIRING in
--           amber in the last 5 s; the NO SEAL pulse (edge, halo, label) in combat; the Judgement ring (judgeAt).
--           A seal that runs out flips the chamber to NO SEAL by itself for immediacy: HudLogic's change detector sees the
--           seal as gone and pushes within one 0.2 s tick, and that late push repaints nothing.
--   JUDGEMENT LANE (lane 9, mockup 2180 to 2198; the debuff on the CURRENT TARGET, from state.judged, whatever the seal look):
--           a debuff lights the lane: the JUDGED header in the chamber's colour, the axis, ticks and numbers at their on alphas, a
--           bar from the foot up to the chip's lower edge (a faint wide stroke under a narrow core, the colour .35 to 1), the
--           chip centred on jY(remaining) on the 0 to 40 s axis with the Judgement spell icon in it and a white flash for
--           .35 s after it lands. No debuff (false), an unknown one (nil, DECIDED: the mockup has no unknown lane look, so the
--           empty look) or one that cannot be read gets the empty lane and its label. The colour is the chamber's (the mockup's
--           `col`: the current seal's, red with no seal, violet unknown), so a seal swap recolours the lane. A retarget reads
--           Hud.GetJudgement at once (an unreadable answer, or a secret target GUID, empties the lane until the next push) and a
--           dead target hides it (UnitIsDead, plus UNIT_HEALTH for the target, which also relights it on a resurrection). The event frame listens only while subscribed. The landing flash starts late, because the Hud tells the lane of a fresh Judgement
--           on its 0.2 s tick (the first paint can be up to .2 s into the .35 s flash). The mockup has no countdown and no
--           expiring cue in the lane.
--   REDUCED MOTION  ForeverSTUwaveDB.reducedMotion == true (ConsoleKeys.lua's convention) ports the mockup's reduce branch:
--           the neon is a steady .8 while expiring and 1 otherwise, with no strike, no dropouts and no shimmer; the pulse
--           is held at u = 1, so the RESEAL wash and the NO SEAL look are steady; the ticker runs only for what still moves
--           (the drain and countdown, and the Judgement ring, which the mockup does not gate). The flag is read at each
--           Hud push, so a change shows at the next push.
--   TICKER  ONE OnUpdate on the chamber, installed only while the piece is on AND something moves (a timed seal, a
--           strike or ring window, the NO SEAL pulse in combat) and cleared the moment nothing does. The per frame
--           path (Tick and what it calls) allocates nothing: no table, closure, concatenation or format; the number
--           strings come from tables built at load, and a steady frame writes only the fill height.
--   v1 DROPS, not built on purpose: the turning arcs (the arcs sit at their start angles), the comet and the
--           target-box flash, the NO SEAL scan sweep and scanlines, the judge chip's glyph (the chip wears the Judgement
--           spell icon instead), the lsLive shoulder, and both NO SEAL rings (mockup lines 2172 and 2173: the dashed r=50 at alpha
--           .35 and the solid r=36 at .2; each needs a baked ring texture, and a new TGA needs a client restart).
--           The Judgement ring (line 2202) is built: seal_ring.tga, the baked full circle with its glow(col, 1) halo.
--   NOT MAPPED, approximations to look at in game: the two rings above; the lane label's reading direction (the mockup
--           rotates it to read bottom to top, Lua cannot rotate, so the stacked letters read top to bottom); the
--           letter spacing of pSpaced and header; the baked chamfer 6 against the mockup's 8; the shadow-blur glows
--           (edge, glyph, band) as four nested plain strokes or one scaled copy; the 1.3 line weight (see LINE); the
--           Judgement ring grows by scaling its texture, so its stroke and halo thicken a little as it fades (the mockup
--           keeps their width); the tip dot is one soft glow_round disc, not a hard 3 px disc with a shadow glow; the ring
--           and the fill draw under the labels (the mockup paints the ring over text); the fill and the number pin at
--           30 s (the own cast ledger holds 30, but a reconcile can report a longer duration, and then remaining exceeds 30);
--           the steady drain height is quantised to a quarter screen pixel where the client reports the pixel size; the
--           countdown rounds tenths as floor(x * 10 + .5), which differs from toFixed only at inexact .x5 ties.
--           Lane 9: the chip's plate is the baked button plate (the mockup tints it .18 toward the seal, 2192), its cut is
--           the shared baked one (6, the mockup's 5) and its edge glow is Theme.SkinButton's ADD halo at the mockup's
--           coverage rather than the nested strokes; the icon is inset inside the cut (masks do not clip) where the
--           mockup's glyph is centred; a debuff longer than 40 s (a reconcile can report one) pins at the top of the axis.
--
-- STATE. Three looks, picked from FS.Hud's state.seal: a known seal (its key maps to a mockup id: sor righteousness,
-- sotc crusader, sofu fury, soc command, sol light, sow wisdom, soj justice) gets its colour and glyph; false (no
-- seal) is the mockup's NO SEAL look (red, the seal parts hidden); nil, a secret or an unmapped key is UNKNOWN: a
-- dim violet chamber with no seal parts and no NO SEAL cry, so a guess is never drawn. The Hud is subscribed to only
-- while the "dot" piece is on (GunsightSeals follows Gunsight.OnPieceChanged and reads IsPieceOn once at build,
-- because the piece hooks belong to GunsightDots), and a repaint is written only when the look changes. The NO SEAL
-- look also wears the Hud's in-combat flag: its IN COMBAT sub-label shows only in combat, and that flag change repaints.
-- The profile can arrive after the pieces build (HudLogic has no change hook): until a profile answers, a piece change
-- or a rescale asks again; the chamber only latches off once the class is decided.
--
-- Every image px number is in the constants block with its mockup name in a comment, and
-- gunsightseals-harness.py parses each back out of the HTML. Nothing is built at file load, for a class that is
-- not on the seals slot, or when the Gunsight is disabled.

local _, FS = ...

local Gunsight = FS.Gunsight
if not (Gunsight and Gunsight.G and Gunsight.OnReady and Gunsight.OnPieceChanged) then return end

FS.GunsightSeals = FS.GunsightSeals or {}
local Seals = FS.GunsightSeals

local G = Gunsight.G
local ui, Point = Gunsight.ui, Gunsight.Point
local TOP, BOT, DOT_AX, FR_T, FR_B = G.TOP, G.BOT, G.DOT_AX, G.FR_T, G.FR_B

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsightseals-harness.py re-reads them from drawSealChamber)
-------------------------------------------------------------------------------

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    -- the chamber frame: SC = { x: DOT_AX, y: FR_T, w: 164, h: FR_B - FR_T, c: 8 }
    SC = { x = DOT_AX, y = FR_T, w = 164, h = FR_B - FR_T, c = 8 },
    TX_DX = 33, TW = 12,                      -- SC_TX = DOT_AX + 33, SC_TW = 12 (the drain tube)
    GX = 1349, GY = 612, GR = 50,             -- SC_GX, SC_GY, SC_GR (the lens centre and radius)
    JL_X = 1431, JL_AX = 1457,                -- the Judgement lane: its guide and its ruler axis
    JL_MAX_S = 40,                            -- jY(s) = BOT - s / 40 * (BOT - TOP)
    HDR_Y = 488, JUDGED_DX = 14,              -- header('SEAL', DOT_AX, 488), header('JUDGED', JL_X - 14, 488)
    JUDGED_A = 0.6,                           -- header('JUDGED', ..., K.muted, .6) with no debuff
    HDR_A = 0.9,                              -- header('SEAL', ..., col, .9)
    PLATE_RGB = { 13 / 255, 6 / 255, 32 / 255 }, PLATE_FILL = 0.8,   -- rgba(13,6,32,.8)
    PLATE_A = 0.55, PLATE_A_NO = 0.7,         -- A(no ? .7 : .55)
    RADIAL_A = 0.2, RADIAL_R0 = 6, RADIAL_PAD = 30,   -- createRadialGradient(.., 6, .., SC_GR + 30) from rgba(col, .2)
    EDGE_A0 = 0.55, EDGE_A1 = 0.45,           -- A(.55 + .45 * neon)
    NO_EDGE_A0 = 0.35, NO_EDGE_A1 = 0.65,     -- A(.35 + .65 * u) with no seal
    GLOW_K0 = 0.6, GLOW_K1 = 0.25,            -- glow(col, .6 + .5 * neon * .5)
    MAJ = 5, MAJ_LEN = 10, MIN_LEN = 5,       -- tick(DOT_AX, y, s % 5 === 0 ? 10 : 5, -1, K.violet, .7)
    TICK_A = 0.7, MAX_S = 30,                 -- the ruler runs 0 to 30 s
    LABEL_DX = 6, LABEL_DY = 4, LABEL_SIZE = 12,      -- text(String(s), DOT_AX + 6, y + 4, 12, K.fg, ..)
    LABEL_A = 0.9, LABEL_A_NO = 0.45,         -- no ? .45 : .9
    BAND_S = 3, BAND_FILL = 0.16,             -- yb = secY(3); A(.16 + .2 * pl) fill across the frame
    BAND_PAD = 2, BAND_DASH = { 5, 4 },       -- hline(yb, SC.x + 2, SC.x + SC.w - 2, ..) dashed [5, 4]
    BAND_TOP_A = 0.75, BAND_BOT_A = 0.95, BAND_BOT_W = 1.3,   -- the dashed top .75, the solid foot .95 at LW * 1.3
    RESEAL_DY = 3.5, RESEAL_SIZE = 10, RESEAL_A = 0.6,        -- text('RESEAL', SC_GX, (yb + BOT) / 2 + 3.5, 10, K.amber, .6)
    TUBE_A = 0.18, TUBE_NO_A = 0.16,          -- the tube track: rgba(tcol, .18), rgba(K.steel, .16) with no seal
    RUNG_STEP = 5, RUNG_A = 0.7,              -- hline(secY(s), .., K.bg, .7) for s = 5 .. 25
    OUT_W = 0.8, OUT_A = 0.55, OUT_NO_A = 0.3,        -- strokeRect at LW * .8, A(no ? .3 : .55)
    LENS_K = 1.2, LENS_SIZE = 128,            -- seal_lens.tga / seal_arcs.tga: 1.2 texels per image px (generator)
    ARCS_A = 0.95,                            -- A(.95 * neon) on the arcs
    GLYPH_R = 0.56, GLYPH_SIZE = 64,          -- strokeGlyph(.., SC_GR * .56, ..); seal_glyph_*.tga is 64 image px square
    GLYPH_TINT = 0.3,                         -- mix(col, '#ffffff', .3)
    NAME_Y = 541, NAME_SIZE = 12, NAME_SIZE_LONG = 10.5, NAME_LONG = 9,   -- pSpaced(sl.n, SC_GX, 541, n.length > 9 ? 10.5 : 12, ..)
    NAME_TINT = 0.2, NAME_A = 0.95,           -- mix(col, '#ffffff', .2), .95 * neon
    CAP_Y = 716, CAP_SIZE = 10.5, CAP_A = 0.85,       -- pSpaced('SEAL ACTIVE', SC_GX, 716, 10.5, col, .85)
    NO_Y = 6, NO_SIZE = 19,                   -- text('NO SEAL', SC_GX, SC_GY + 6, 19, K.red, ..)
    NO_SUB_Y = 24, NO_SUB_SIZE = 10.5, NO_SUB_A = 0.55,       -- pSpaced('IN COMBAT', SC_GX, SC_GY + 24, 10.5, K.red, .55)
    NO_TIME_DX = 5, NO_TIME_Y = 700, NO_TIME_SIZE = 26, NO_TIME_A = 0.4,   -- text('--', SC_GX - 5, 700, 26, K.muted, .4)
    NO_HINT_SIZE = 10.5, NO_HINT_A = 0.6,     -- pSpaced('CAST A SEAL', SC_GX, 716, 10.5, K.muted, .6)
    NO_U = 0.5,                               -- u, the pulse (0 to 1): its resting mean, worn by every look that does not pulse
    -- the live layer (sealNeon and drawSealChamber's animated terms)
    STRIKE = { 0.2, 0.9, 0.1, 0.7, 0.3, 1, 0.6 }, STRIKE_S = 0.7,   -- [.2, .9, .1, .7, .3, 1, .6][min(6, floor(strike / .7 * 7))]
    EXPIRE_S = 5, FLICK_RATE = 13,            -- st.rem <= 5 dies out; n = floor(t * 13)
    FLICK_SEED = 91.7, FLICK_SEED2 = 12.9898, FLICK_MUL = 43758.5453,   -- fract(sin(n * 91.7) * 43758.5453), the depth with 12.9898
    DROP_P0 = 0.28, DROP_P1 = 0.4,            -- p = .28 + .4 * (1 - rem / 5): the odds of a dropout
    DROP_LO = 0.12, DROP_SPAN = 0.3,          -- a dropout is .12 + .3 * fract(..)
    STEADY_BASE = 0.78, STEADY_AMP = 0.22, STEADY_FREQ = 37,   -- else .78 + .22 * sin(t * 37)
    PULSE_S = 1.4,                            -- u = .5 - .5 * cos(PI * clock / 1.4)
    BAND_PL_FREQ = 9, BAND_PL = 0.2,          -- pl = .5 + .5 * sin(clock * 9); the wash is A(.16 + .2 * pl)
    RESEAL_IN0 = 0.55, RESEAL_IN1 = 0.45,     -- RESEAL in the band: .55 + .45 * u
    FILL_MIN = 0.05, FILL_A0 = 0.35,          -- the drain shows for st.rem > .05; its tail is .35
    TIP_A = 0.9, TIP_MIX = 0.55, TIP_H = 1.5, -- A(.9 * neon), mix(tcol, '#ffffff', .55), fillRect(.., tipY, SC_TW, 1.5)
    DOT_MIX = 0.5, DOT_R = 3,                 -- the tip dot: mix(tcol, '#ffffff', .5), arc radius 3
    COUNT_FROM = 5, COUNT_DX = 5, COUNT_Y = 700, COUNT_SIZE = 26,   -- whole seconds above 5; text(s, SC_GX - 5, 700, 26, tcol, neon)
    S_GAP = 3, S_SIZE = 12, S_A = 0.9,        -- text('S', SC_GX - 5 + p / 2 + 3, 700, 12, K.muted, .9 * neon, 'left')
    CAP_TEXT = "SEAL ACTIVE", CAP_EXPIRING = "EXPIRING",
    RING_S = 0.9, RING_A = 0.85, RING_GROW = 26,   -- f < .9, A(.85 * (1 - p)), radius SC_GR + p * 26
    RING_SIZE = 256, RING_K = 1.2,            -- seal_ring.tga: 256 texels, 1.2 texels per image px (generate_seal_ring.py), circle r = SC_GR
    REDUCED_EXPIRING = 0.8,                   -- sealNeon under reduce: st.mode === 'expiring' ? .8 : 1
    FILL_STEP = 0.25,                         -- not in the mockup: the steady drain height snaps to a quarter screen pixel
    GLOW_HALF = 0.5634765625,                 -- glow_round.tga: the radius (as a share of the half size) where its alpha is a half
    JL_AX_UP = 4, JL_AX_DN = 4, JL_AX_A = 0.35,       -- vline(JL_AX, TOP - 4, BOT + 4, K.violet, .35)
    JL_MAJ = 10, JL_MID = 5, JL_MAJ_LEN = 10, JL_MID_LEN = 7, JL_MIN_LEN = 4, JL_TICK_A = 0.3,
    JL_LABEL_A = 0.4,                         -- text(String(s), JL_AX + 6, y + 4, 12, K.fg, .4, 'left') at s % 10 === 0
    JL_GUIDE_DASH = { 2, 6 }, JL_GUIDE_A = 0.2,       -- setLineDash([2, 6]); vline(JL_X, TOP, BOT, K.violet, .2)
    JL_TEXT_DX = 4, JL_TEXT_SIZE = 10.5, JL_TEXT_SP = 1.4, JL_TEXT_A = 0.8,   -- the empty lane label, rotated in the mockup
    NOT_JUDGED = "NOT JUDGED", NO_DEBUFF = "NO DEBUFF",
    -- the Judgement lane live (lane 9; drawSealChamber 2180 to 2198): a debuff on the target lights the lane
    JUDGED_A_ON = 0.9,                        -- header('JUDGED', .., st.jrem > 0 ? col : K.muted, st.jrem > 0 ? .9 : .6)
    JL_AX_A_ON = 0.85, JL_TICK_A_ON = 0.7, JL_LABEL_A_ON = 0.9,   -- the ruler with a debuff up (off: .35, .3, .4)
    CHS = 24,                                 -- CHS: the chip is a 24 image px square, CHP = CHS / 2
    JL_BAR_A0 = 0.35,                         -- createLinearGradient(0, BOT, 0, min(BOT, y + CHP)): rgba(col, .35) to rgba(col, 1)
    JL_BAR_GLOW_W = 7, JL_BAR_GLOW_A = 0.22,  -- A(.22), lineWidth 7: the faint wide stroke
    JL_BAR_CORE_W = 2.6, JL_BAR_CORE_A = 1,   -- A(1), lineWidth 2.6: the core
    ICON_ASKS = 3,                            -- NOT in the mockup: the chip's icon is logged as missing only after this many unanswered asks ...
    ICON_WAIT = 5,                            -- ... the last one at least this many seconds after the first
    CHIP_PLATE_A = 0.92,                      -- chamfer(JL_X - CHP, y - CHP, CHS, CHS, 5); A(.92) plate
    CHIP_GLOW_K = 0.6,                        -- glow(col, .6) on the chip's edge
    POP_S = 0.35, POP_A = 0.8,                -- if (st.jage < .35) A((1 - jage / .35) * .8), K.white fill
    -- Mononoki Bold, read from the font file (the harness re-reads it): the line box of a font runs from the hhea ascender (900)
    -- to the descender (-250) of 1024 units, so its middle sits (900 - 250) / 2 / 1024 above the baseline; the monospace
    -- advance is 575 of 1024. The engine's centring on that box is UNVERIFIED in game.
    CAP = 325 / 1024,                         -- baseline to the middle of a text line, as a fraction of its size
    MONO_ADV = 575 / 1024,                    -- Mononoki's advance as a fraction of its size (the stacked letters)
    -- the mockup's baked style halo (HALO, line 526): four nested strokes of reach r and alpha a, drawn at k * a under the core
    HALO = { { 1.5, 0.26 }, { 3.2, 0.17 }, { 5, 0.10 }, { 7, 0.055 } },
    GLYPH_GLOW_K = 0.9, BAND_GLOW_K = 0.8,    -- strokeGlyph(.., neon, .9, ..), glow(K.amber, .8) on the foot of the band
    COLORS = {                                -- the mockup's :root tokens
        bg = Hex("#0d0620"), fg = Hex("#e9e2ff"), violet = Hex("#a855f7"), amber = Hex("#ffb648"),
        red = Hex("#ff3b4e"), steel = Hex("#8d93a6"), muted = Hex("#9d93c4"), white = Hex("#f3fbff"),
    },
    -- SEALS: n the name, c the colour, deb the Judgement debuff seconds (0 = none)
    SEALS = {
        righteousness = { n = "RIGHTEOUSNESS", c = Hex("#ffd23f"), deb = 0 },
        crusader = { n = "CRUSADER", c = Hex("#ff9a2e"), deb = 40 },
        fury = { n = "FURY", c = Hex("#ff3b4e"), deb = 0 },
        command = { n = "COMMAND", c = Hex("#b565ff"), deb = 0 },
        light = { n = "LIGHT", c = Hex("#f3fbff"), deb = 40 },
        wisdom = { n = "WISDOM", c = Hex("#4da3ff"), deb = 40 },
        justice = { n = "JUSTICE", c = Hex("#c9d3e6"), deb = 10 },
    },
}
Seals.C = C
local K, SEALS = C.COLORS, C.SEALS

-- How much of a colour the halo lays down just outside a stroke: the four nested strokes at alpha k * a over each other,
-- counted from stroke `from` (1 = at the stroke's own edge, all four) outward.
local function Coverage(k, from)
    local keep = 1
    for i = from or 1, #C.HALO do keep = keep * (1 - k * C.HALO[i][2]) end
    return 1 - keep
end

-- The glyph's glow(col, .9) is that halo around line art; one scaled ADD copy of the glyph stands in for it. It grows by the
-- halo's alpha weighted mean reach and wears the mean coverage over the 7 px reach.
do
    local sum, prev, wr, wa = 0, 0, 0, 0
    for j = 1, #C.HALO do
        sum = sum + (C.HALO[j][1] - prev) * Coverage(C.GLYPH_GLOW_K, j)
        prev = C.HALO[j][1]
        wr, wa = wr + C.HALO[j][1] * C.HALO[j][2], wa + C.HALO[j][2]
    end
    C.HALO_K = 1 + (wr / wa) / (C.GLYPH_SIZE / 2)
    C.HALO_A = sum / C.HALO[#C.HALO][1]
end

-- HudSpells seal key (the profile's `seals.order`, HudLogic state.seal.key) to the mockup's seal id.
local KEY_ID = {
    sor = "righteousness", sotc = "crusader", sofu = "fury", soc = "command",
    sol = "light", sow = "wisdom", soj = "justice",
}

local WHITE = { 1, 1, 1 }
-- Hairline weight in image px: the DoT scale's own (GunsightDots.lua), so the two classes that share this seat match, and the
-- GunsightFrame lines beside it are a pixel snapped 1 image px. The mockup's LW is 1.3 CSS px at its 1400 px preview, which is
-- 1.857 image px, and the baked lens, arcs and glyph strokes carry that weight (a texture cannot be thinned); at 1.857 these
-- lines would be the heaviest in the HUD. UNVERIFIED in game next to the baked strokes.
local LINE = G.LINE or 1.3
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local GLOW_ROUND = MEDIA .. "glow_round.tga"

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightseals_" .. key,
            "|cffff4488Forever STUwave|r: gunsight seals: " .. tostring(msg))
    end
end

local built, subscribed = false, false
local chamber                  -- the chamfered frame itself, a child of the dot piece frame
local P = {}                   -- the named parts (exposed as Seals.parts)
local seats = {}               -- closures re-run by every rescale
local mode, sealId             -- the look last painted: "seal" | "none" | "unknown", and the seal id for "seal"
local inCombat = false         -- the combat flag the NO SEAL look last painted (false for every other look)
local laneCol                  -- the colour the Judgement lane last painted a debuff in (the look's colour), nil for the empty lane

-- The live layer's state. The Hud's plain times (castAt, expiresAt, judgeAt), the last combat flag, and what the moving parts
-- last wore, so a frame writes only what changed. Paint resets the caches, so the first frame after a repaint writes everything.
local L = {
    neon = 1,                  -- the neon level the seal parts wear
    col = nil,                 -- the seal colour of the look painted
    expiresAt = nil, castAt = nil, judgeAt = nil,   -- plain GetTime values, nil when absent or unreadable
    combat = false,            -- the Hud's combat flag as of the last push (any look)
    band = false, expiring = false,                 -- the RESEAL band and EXPIRING cue worn
    fillShown = false, fillH = nil,                 -- the drain: shown, and its height in image px
    countText = nil, countLen = 0,                  -- the countdown text worn, and the text length the S stands for (Paint leaves it: the S stays where it was seated)
    ringOn = false, ringSize = 0,                   -- the Judgement ring: shown, and its size in image px
    countShown = false,                             -- the number and its S are up (any readable time; the tube also needs rem > .05)
    gradient = false,                               -- the client can draw the drain's gradient (decided at build)
    fillQ = nil,                                    -- the steady drain height snaps to this many image px (nil: exact)
    reduced = false,                                -- ForeverSTUwaveDB.reducedMotion as of the last Paint
    jExp = nil, jApplied = nil,                     -- the target's Judgement debuff: plain expiresAt and appliedAt, nil when none or unreadable
    jH = nil,                                       -- the lane bar's height in image px (BOT - jY(remaining)), snapped like the drain
    jBarOn = false, jChipOn = false, jPopOn = false,    -- the bar, the chip and the landing flash are up
    jIcon = nil,                                    -- the Judgement spell texture once the client has answered
    jDead = false,                                  -- the lane is hidden only because the target is dead: a health event may relight it
    iconAsks = 0, iconSince = nil,                  -- unanswered icon asks so far and the time of the first (the noicon log waits for both)
    jGrad = {},                                     -- per lane colour table: the bar's gradient colours, made once
    laneText = "",                                  -- the empty lane label the seal look gives (NOT JUDGED, NO DEBUFF or none)
    broken = false,            -- a frame threw: the ticker stays off until the next push
}
local ticking = false          -- the chamber's OnUpdate is installed
local Sync                     -- forward: Tick stops itself through it

local function Seat(fn)
    seats[#seats + 1] = fn
    fn()
end

local function SeatAll()
    for i = 1, #seats do
        local ok, err = pcall(seats[i])
        if not ok then LogOnce("seat", err) end
    end
end

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

local function SecY(s) return BOT - s / C.MAX_S * (BOT - TOP) end
local function JY(s) return BOT - s / C.JL_MAX_S * (BOT - TOP) end

-------------------------------------------------------------------------------
-- Drawing helpers (all seated by mockup image coordinates through Gunsight.Point)
-------------------------------------------------------------------------------

local function Tex(layer, sub)
    return chamber:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
end

local function Solid(t, c, a)
    t:SetColorTexture(c[1], c[2], c[3], a)
end

-- A horizontal line from x0 to x1 (image px) centred on y, `th` image px thick.
local function HLine(y, x0, x1, c, a, th, layer, sub)
    local t = Tex(layer, sub)
    Solid(t, c, a)
    Seat(function()
        Point(t, "LEFT", x0, y)
        t:SetSize(ui(x1 - x0), ui(th))
    end)
    return t
end

-- A vertical line at x from y0 down to y1.
local function VLine(x, y0, y1, c, a, th, layer, sub)
    local t = Tex(layer, sub)
    Solid(t, c, a)
    Seat(function()
        Point(t, "TOP", x, y0)
        t:SetSize(ui(th), ui(y1 - y0))
    end)
    return t
end

local function HDashes(y, x0, x1, dash, c, a, th, layer, sub)
    local list, x = {}, x0
    while x < x1 - 1e-6 do
        list[#list + 1] = HLine(y, x, math.min(x1, x + dash[1]), c, a, th, layer, sub)
        x = x + dash[1] + dash[2]
    end
    return list
end

local function VDashes(x, y0, y1, dash, c, a, th)
    local list, y = {}, y0
    while y < y1 - 1e-6 do
        list[#list + 1] = VLine(x, y, math.min(y1, y + dash[1]), c, a, th)
        y = y + dash[1] + dash[2]
    end
    return list
end

-- A centred square texture of `size` image px on (cx, cy).
local function Square(t, cx, cy, size)
    Seat(function()
        Point(t, "CENTER", cx, cy)
        t:SetSize(ui(size), ui(size))
    end)
end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    fs.cur = { c[1], c[2], c[3], a }
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-- Text on a mockup baseline: `anchor` is "LEFT" or "CENTER", the line is centred C.CAP * size above the baseline.
local function Text(text, size, anchor, x, baseline)
    local fs = chamber:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs.size = size                             -- image px; the seal name changes it, then calls fs.seat()
    fs.x = x                                   -- image px; the countdown's S moves it, then calls fs.seat()
    fs:SetJustifyH(anchor)
    fs.seat = function()
        FS.Theme.ApplyMono(fs, ui(fs.size), fs.cur)
        Point(fs, anchor, fs.x, baseline - C.CAP * fs.size)
    end
    Seat(fs.seat)
    -- After Seat, which runs once at once and so sets the font: SetText on a FontString with none throws "Font not set".
    fs:SetText(text)
    return fs
end

-- A header word: the DoT scale's own recipe (BOTTOMLEFT, 2.5 below the baseline), so the two classes line up.
local function Header(text, x)
    local fs = chamber:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs:SetJustifyH("LEFT")
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(11), fs.cur)
        Point(fs, "BOTTOMLEFT", x, C.HDR_Y + 2.5)
    end)
    fs:SetText(text)
    return fs
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function BuildFrame()
    local sc, Theme = C.SC, FS.Theme
    -- the chamber frame is the chamfered rect itself; the dot piece frame is its parent
    Seat(function()
        Point(chamber, "TOPLEFT", sc.x, sc.y)
        chamber:SetSize(ui(sc.w), ui(sc.h))
    end)
    -- Draw order, from drawSealChamber's sequence (the harness derives it from the mockup and checks every overlapping pair):
    -- plate, radial wash, edge halo, edge (BACKGROUND 0, 1, BORDER -1, 0); then ARTWORK 0 ruler, 1 band fill, 2 band top,
    -- 3 band glow, 4 band foot, 5 tube, 6 rungs, 7 tube outline; then OVERLAY -4 lens, -3 arcs, -2 glyph halo, -1 glyph, and
    -- every label at OVERLAY 0 above all of it. (The mockup paints the amber band wash over the ruler numbers, which sit
    -- below it there; here the numbers are above it.) The baked cut is 6, the mockup 8 image px.
    P.plate = Theme.AddCut2Texture(chamber, Theme.SLICE_CUT2_FILL_TEXTURE, WHITE, "BACKGROUND", 0)
    P.glow = Theme.AddSliceTexture(chamber, Theme.SLICE_GLOW_TEXTURE, WHITE, "BORDER", -1, -Theme.SLICE_GLOW_PAD)
    Theme.ApplyNineSlice(P.glow, Theme.SLICE_GLOW_MARGIN)
    P.glow:SetBlendMode("ADD")
    -- chamfer(..) fill with createRadialGradient(SC_GX, SC_GY, 6, SC_GX, SC_GY, SC_GR + 30): the soft round glow
    -- texture, cropped at the frame's right edge (the circle reaches 26 image px past it and the fill is clipped)
    local R = C.GR + C.RADIAL_PAD
    local right = sc.x + sc.w
    local u1 = (right - (C.GX - R)) / (2 * R)
    P.radial = Tex("BACKGROUND", 1)
    P.radial:SetTexture(GLOW_ROUND)
    P.radial:SetTexCoord(0, u1, 0, 1)
    Seat(function()
        Point(P.radial, "TOPLEFT", C.GX - R, C.GY - R)
        P.radial:SetSize(ui(right - (C.GX - R)), ui(2 * R))
    end)
    P.edge = Theme.AddCut2Texture(chamber, Theme.SLICE_CUT2_OUTLINE_TEXTURE, WHITE, "BORDER")
end

local function BuildRuler()
    P.ticks, P.labels = {}, {}
    for s = 0, C.MAX_S do
        local y = SecY(s)
        local maj = s % C.MAJ == 0
        local len = maj and C.MAJ_LEN or C.MIN_LEN
        P.ticks[s + 1] = HLine(y, DOT_AX - len, DOT_AX, K.violet, C.TICK_A, LINE, "ARTWORK", -4)
        if maj then
            P.labels[s] = Text(tostring(s), C.LABEL_SIZE, "LEFT", DOT_AX + C.LABEL_DX, y + C.LABEL_DY)
            TextColor(P.labels[s], K.fg, C.LABEL_A)
        end
    end
    P.header = Header("SEAL", DOT_AX)
end

local function BuildBand()
    local sc = C.SC
    local yb = SecY(C.BAND_S)
    local x0, x1 = sc.x + C.BAND_PAD, sc.x + sc.w - C.BAND_PAD
    P.band = Tex("ARTWORK", -3)
    Solid(P.band, K.amber, C.BAND_FILL)
    Seat(function()
        Point(P.band, "TOPLEFT", sc.x, yb)
        P.band:SetSize(ui(sc.w), ui(BOT - yb))
    end)
    P.bandTop = HDashes(yb, x0, x1, C.BAND_DASH, K.amber, C.BAND_TOP_A, LINE, "ARTWORK", -2)
    -- glow(K.amber, .8) on the foot: the four nested halo strokes, each wider than the core by twice its reach and at
    -- k * a of the foot's alpha, plain blend (source over), as the mockup stacks them
    P.bandGlow = {}
    for i = 1, #C.HALO do
        local reach, a = C.HALO[i][1], C.HALO[i][2]
        P.bandGlow[i] = HLine(BOT, x0, x1, K.amber, C.BAND_BOT_A * C.BAND_GLOW_K * a, LINE * C.BAND_BOT_W + 2 * reach,
            "ARTWORK", -1)
    end
    P.bandBottom = HLine(BOT, x0, x1, K.amber, C.BAND_BOT_A, LINE * C.BAND_BOT_W, "ARTWORK", 0)
    P.reseal = Text("RESEAL", C.RESEAL_SIZE, "CENTER", C.GX, (yb + BOT) / 2 + C.RESEAL_DY)
    TextColor(P.reseal, K.amber, C.RESEAL_A)
end

-- UI units per physical pixel at the root's effective scale, or nil when the client will not say (GunsightFrame's PixelUnit).
local function PixelUnit()
    local factor
    local pixelUtil, physical = _G.PixelUtil, _G.GetPhysicalScreenSize
    if type(pixelUtil) == "table" and type(pixelUtil.GetPixelToUIUnitFactor) == "function" then
        local ok, v = pcall(pixelUtil.GetPixelToUIUnitFactor)
        if ok then factor = v end
    elseif type(physical) == "function" then
        local ok, _, h = pcall(physical)
        if ok and type(h) == "number" and not (FS.IsSecret and FS.IsSecret(h)) and h > 0 then factor = 768 / h end
    end
    -- a plain, finite, positive number or nothing (a NaN or an infinity would poison every height written after it)
    if type(factor) ~= "number" or (FS.IsSecret and FS.IsSecret(factor)) or factor ~= factor or factor <= 0 or factor == math.huge then return nil end
    local scale = 1
    local root = Gunsight.root
    if root and root.GetEffectiveScale then
        local ok, v = pcall(root.GetEffectiveScale, root)
        if ok and type(v) == "number" and not (FS.IsSecret and FS.IsSecret(v)) and v > 0 and v < math.huge then scale = v end
    end
    return factor / scale
end

-- How many image px a quarter screen pixel is at the current scale (nil: the client will not say, the height stays exact).
local function SeatFillStep()
    L.fillQ = nil
    local px = PixelUnit()
    if not px then return end
    local one = ui(1)
    if type(one) == "number" and one > 0 and one < math.huge then L.fillQ = C.FILL_STEP * px / one end
end

local function BuildTube()
    local cx, hw = DOT_AX + C.TX_DX, C.TW / 2
    L.amberTip = Mix(K.amber, WHITE, C.TIP_MIX)
    L.amberDot = Mix(K.amber, WHITE, C.DOT_MIX)
    P.tube = Tex("ARTWORK", 1)
    Seat(function()
        Point(P.tube, "TOPLEFT", cx - hw, TOP)
        P.tube:SetSize(ui(C.TW), ui(BOT - TOP))
    end)
    -- The drain: a white colour texture the VERTICAL gradient multiplies (set once, here), grown from the foot by SetHeight
    -- alone. The tip bar and the tip dot hang off its top edge, so a frame writes the fill height and nothing else.
    P.fill = Tex("ARTWORK", 2)
    P.fill:SetColorTexture(1, 1, 1, 1)
    -- a client without Texture:SetGradient or CreateColor gets a flat tint (PaintFill), as GunsightDots' Gradient does; what the
    -- drain wears in the RESEAL band is built once here so the flip into the band allocates nothing
    L.gradient = type(P.fill.SetGradient) == "function" and type(CreateColor) == "function"
    if L.gradient then
        L.amberLo = CreateColor(K.amber[1], K.amber[2], K.amber[3], C.FILL_A0)
        L.amberHi = CreateColor(K.amber[1], K.amber[2], K.amber[3], 1)
    end
    Seat(SeatFillStep)
    Seat(function()
        Point(P.fill, "BOTTOMLEFT", cx - hw, BOT)
        P.fill:SetSize(ui(C.TW), ui(L.fillH or 0))
    end)
    P.tipBar = Tex("ARTWORK", 3)
    Solid(P.tipBar, WHITE, C.TIP_A)
    Seat(function()
        P.tipBar:ClearAllPoints()
        P.tipBar:SetPoint("TOPLEFT", P.fill, "TOPLEFT")
        P.tipBar:SetSize(ui(C.TW), ui(C.TIP_H))
    end)
    P.tipDot = Tex("ARTWORK", 4)
    P.tipDot:SetTexture(GLOW_ROUND)
    Seat(function()
        local size = ui(2 * C.DOT_R / C.GLOW_HALF)
        P.tipDot:ClearAllPoints()
        P.tipDot:SetPoint("CENTER", P.fill, "TOP")
        P.tipDot:SetSize(size, size)
    end)
    P.rungs = {}
    for s = C.RUNG_STEP, C.MAX_S - 1, C.RUNG_STEP do
        P.rungs[#P.rungs + 1] = HLine(SecY(s), cx - hw, cx + hw, K.bg, C.RUNG_A, LINE, "ARTWORK", 5)
    end
    -- strokeRect: four lines centred on the rect's edges
    local th = LINE * C.OUT_W
    P.outline = {
        HLine(TOP, cx - hw, cx + hw, WHITE, 1, th, "ARTWORK", 6),
        HLine(BOT, cx - hw, cx + hw, WHITE, 1, th, "ARTWORK", 6),
        VLine(cx - hw, TOP, BOT, WHITE, 1, th, "ARTWORK", 6),
        VLine(cx + hw, TOP, BOT, WHITE, 1, th, "ARTWORK", 6),
    }
end

local function BuildLens()
    local lens = C.LENS_SIZE / C.LENS_K
    P.lens = Tex("OVERLAY", -5)
    P.lens:SetTexture(MEDIA .. "seal_lens.tga")
    Square(P.lens, C.GX, C.GY, lens)
    P.arcs = Tex("OVERLAY", -4)
    P.arcs:SetTexture(MEDIA .. "seal_arcs.tga")
    Square(P.arcs, C.GX, C.GY, lens)
    P.glyphHalo = Tex("OVERLAY", -3)
    P.glyphHalo:SetBlendMode("ADD")
    Square(P.glyphHalo, C.GX, C.GY, C.GLYPH_SIZE * C.HALO_K)
    P.glyph = Tex("OVERLAY", -2)
    Square(P.glyph, C.GX, C.GY, C.GLYPH_SIZE)
    -- The Judgement ring (a fresh judgeAt): the baked full circle with its halo (seal_ring.tga, whose circle is the lens radius
    -- at rest), above the glyph; its size follows L.ringSize, so a rescale re-seats it at the size it wears and a frame writes
    -- SetSize only while it moves. Needs a full client restart the first time (a new TGA).
    P.judgeRing = Tex("OVERLAY", -1)
    P.judgeRing:SetTexture(MEDIA .. "seal_ring.tga")
    L.ringSize = C.RING_SIZE / C.RING_K
    Seat(function()
        Point(P.judgeRing, "CENTER", C.GX, C.GY)
        P.judgeRing:SetSize(ui(L.ringSize), ui(L.ringSize))
    end)
    P.name = Text("", C.NAME_SIZE, "CENTER", C.GX, C.NAME_Y)
    P.caption = Text("SEAL ACTIVE", C.CAP_SIZE, "CENTER", C.GX, C.CAP_Y)
end

-- The countdown number and its muted S (the S sits right of the number: BuildCount seats it for two digits, the live layer
-- moves it when the text length changes).
local function BuildCount()
    local x = C.GX - C.COUNT_DX
    P.count = Text("", C.COUNT_SIZE, "CENTER", x, C.COUNT_Y)
    P.countS = Text("S", C.S_SIZE, "LEFT", x + 2 * C.MONO_ADV * C.COUNT_SIZE / 2 + C.S_GAP, C.COUNT_Y)
end

local function BuildNoSeal()
    P.noSeal = Text("NO SEAL", C.NO_SIZE, "CENTER", C.GX, C.GY + C.NO_Y)
    P.noSub = Text("IN COMBAT", C.NO_SUB_SIZE, "CENTER", C.GX, C.GY + C.NO_SUB_Y)
    P.noTime = Text("--", C.NO_TIME_SIZE, "CENTER", C.GX - C.NO_TIME_DX, C.NO_TIME_Y)
    P.noHint = Text("CAST A SEAL", C.NO_HINT_SIZE, "CENTER", C.GX, C.CAP_Y)
    TextColor(P.noSub, K.red, C.NO_SUB_A)
    TextColor(P.noTime, K.muted, C.NO_TIME_A)
    TextColor(P.noHint, K.muted, C.NO_HINT_A)
end

local JL_LETTERS = #C.NOT_JUDGED       -- the longest empty lane label

-- The empty lane label runs bottom to top in the mockup; Lua cannot rotate text, so it is stacked upright letters
-- centred on the guide, top to bottom (the DoT scale's REFRESH label does the same).
local stack = ""
local function SeatStack()
    local n = #stack
    local pitch = C.MONO_ADV * C.JL_TEXT_SIZE + C.JL_TEXT_SP
    local x = C.JL_X + C.JL_TEXT_DX - C.CAP * C.JL_TEXT_SIZE
    local cy = (TOP + BOT) / 2
    for i = 1, JL_LETTERS do
        local fs = P.stack[i]
        fs:SetShown(i <= n)
        if i <= n then
            Point(fs, "CENTER", x, cy + (i - (n + 1) / 2) * pitch)
        end
    end
end

-- The Judgement chip (mockup 2192 to 2195): the DoT scale's own chip recipe (GunsightDots BuildChip), a 24 square frame whose
-- icon is the Judgement spell, inset inside the cut by FrameHelpers.SeatAuraTile, with Theme.SkinButton's ring and halo in the
-- seal colour and a cut shaped white pop for the landing flash. It stands in for the mockup's chip, which holds the seal's glyph
-- (a v1 drop: the plan puts the spell icon there). A frame on the chamber, so it stacks above every chamber texture (the bar).
-- Nothing here is needed by the bar: a missing helper or a throw (BuildJudgementLane's pcall) logs `nochip` once and the lane keeps its bar.
local function BuildJudgeChip()
    local Theme, FH = FS.Theme, FS.FrameHelpers
    local f = CreateFrame("Frame", nil, chamber)
    f:Hide()
    f:SetFrameLevel(chamber:GetFrameLevel() + 1)
    f:EnableMouse(false)
    f:SetSize(ui(C.CHS), ui(C.CHS))             -- sized first: the chamfer comes from the height
    f.icon = f:CreateTexture(nil, "ARTWORK")
    f.icon:SetAllPoints(f)
    Theme.SkinButton(f, { borderColor = K.violet })
    FH.SeatAuraTile(f)
    local c = (f.fsSkin and f.fsSkin.chamfer) or 6
    local path = c == 6 and Theme.SLICE_CUT2_FILL_TEXTURE or (MEDIA .. "slice_cut2_fill_c" .. c .. ".tga")
    local pop = Theme.AddSliceTexture(f, path, { K.white[1], K.white[2], K.white[3], 0 }, "OVERLAY", 2)
    Theme.ApplyNineSlice(pop, c)
    pop:Hide()
    Seat(function()
        f:SetSize(ui(C.CHS), ui(C.CHS))
        Point(f, "CENTER", C.JL_X, BOT - (L.jH or 0))
    end)
    P.jChip, P.jPop = f, pop
end

local function BuildJudgementLane()
    local jx, ax = C.JL_X, C.JL_AX
    P.judged = Header("JUDGED", jx - C.JUDGED_DX)
    TextColor(P.judged, K.muted, C.JUDGED_A)
    P.jAxis = VLine(ax, TOP - C.JL_AX_UP, BOT + C.JL_AX_DN, K.violet, C.JL_AX_A, LINE)
    P.jTicks, P.jLabels = {}, {}
    for s = 0, C.JL_MAX_S do
        local y = JY(s)
        local len = s % C.JL_MAJ == 0 and C.JL_MAJ_LEN or (s % C.JL_MID == 0 and C.JL_MID_LEN or C.JL_MIN_LEN)
        P.jTicks[s + 1] = HLine(y, ax - len, ax, K.violet, C.JL_TICK_A, LINE)
        if s % C.JL_MAJ == 0 then
            P.jLabels[s] = Text(tostring(s), C.LABEL_SIZE, "LEFT", ax + C.LABEL_DX, y + C.LABEL_DY)
            TextColor(P.jLabels[s], K.fg, C.JL_LABEL_A)
        end
    end
    P.jGuide = VDashes(jx, TOP, BOT, C.JL_GUIDE_DASH, K.violet, C.JL_GUIDE_A, LINE)
    -- the debuff bar (2189 to 2191): a faint wide stroke under a narrow core, grown from BOT by SetHeight alone, hidden at rest
    P.jBarGlow, P.jBarCore = Tex("ARTWORK", 3), Tex("ARTWORK", 4)
    P.jBarGlow:SetAlpha(C.JL_BAR_GLOW_A)
    P.jBarCore:SetAlpha(C.JL_BAR_CORE_A)
    for _, spec in ipairs({ { P.jBarGlow, C.JL_BAR_GLOW_W }, { P.jBarCore, C.JL_BAR_CORE_W } }) do
        local t, w = spec[1], spec[2]
        t:SetColorTexture(1, 1, 1, 1)
        t:Hide()
        Seat(function()
            Point(t, "BOTTOM", jx, BOT)
            t:SetWidth(ui(w))
            t:SetHeight(ui(math.max(0, (L.jH or 0) - C.CHS / 2)))
        end)
    end
    local ok, err = pcall(BuildJudgeChip)
    if not ok then LogOnce("nochip", err) end
    P.stack = {}
    for i = 1, JL_LETTERS do
        local fs = chamber:CreateFontString(nil, "OVERLAY")
        fs.cur = { K.muted[1], K.muted[2], K.muted[3], C.JL_TEXT_A }
        fs:SetJustifyH("CENTER")
        Seat(function() FS.Theme.ApplyMono(fs, ui(C.JL_TEXT_SIZE), fs.cur) end)
        fs:SetText("")
        P.stack[i] = fs
    end
    Seat(SeatStack)
end

local function SetStack(text)
    stack = text
    for i = 1, JL_LETTERS do P.stack[i]:SetText(text:sub(i, i)) end
    SeatStack()
end

-------------------------------------------------------------------------------
-- Look
-------------------------------------------------------------------------------

local function Tint(t, c, a)
    t:SetVertexColor(c[1], c[2], c[3], a)
end

-- The drain's colour: the vertical gradient .35 to 1 where the client can draw one (L.gradient, decided at build), else a flat
-- tint of the same colour at full alpha (neon scales it through the fill's own alpha either way).
local function PaintFill(on)
    if L.gradient then
        P.fill:SetGradient("VERTICAL", on and L.amberLo or L.sealLo, on and L.amberHi or L.sealHi)
    else
        local c = on and K.amber or L.col
        P.fill:SetColorTexture(c[1], c[2], c[3], 1)
    end
end

local function ShowAll(list, on)
    for i = 1, #list do list[i]:SetShown(on) end
end

-- The seal parts: shown for a known seal only. The none parts: shown for "none" only.
local function SealParts() return { P.radial, P.lens, P.arcs, P.glyphHalo, P.glyph, P.name, P.caption, P.reseal } end
local function DrainParts() return { P.fill, P.tipBar, P.tipDot, P.count, P.countS, P.judgeRing } end
local function NoneParts() return { P.noSeal, P.noTime, P.noHint } end

-- Paints a look at rest (neon 1, no pulse, nothing moving) and resets what the live layer has worn, so the first frame after
-- a repaint writes everything again. The seal's drain parts (fill, tip bar, tip dot, number, S) and the Judgement ring start
-- hidden: the live layer shows them when it reads a time.
local function Paint(newMode, id, combat, reduce)
    local no, known = newMode == "none", newMode == "seal"
    local sl = known and SEALS[id] or nil
    local col = known and sl.c or (no and K.red or K.violet)
    local pu = reduce and 1 or C.NO_U             -- reduced motion holds the pulse at u = 1
    local neon = 1

    L.neon, L.col = neon, col
    L.band, L.expiring = false, false
    L.fillShown, L.fillH, L.countShown, L.countText, L.ringOn = false, nil, false, nil, false

    -- frame
    local plateA = (no and C.PLATE_A_NO or C.PLATE_A) * C.PLATE_FILL
    P.plate:SetVertexColor(C.PLATE_RGB[1], C.PLATE_RGB[2], C.PLATE_RGB[3], plateA)
    local edgeA = known and (C.EDGE_A0 + C.EDGE_A1 * neon) or (no and (C.NO_EDGE_A0 + C.NO_EDGE_A1 * pu) or C.EDGE_A0)
    Tint(P.edge, col, edgeA)
    -- glow(col, k) lays the edge's own alpha down in four nested strokes: what shows is that alpha times their coverage
    local glowK = known and (C.GLOW_K0 + C.GLOW_K1 * neon) or (no and pu or 0)
    Tint(P.glow, col, edgeA * Coverage(glowK))
    P.glow:SetShown(glowK > 0)
    TextColor(P.header, col, C.HDR_A)

    -- ruler numbers
    local la = no and C.LABEL_A_NO or C.LABEL_A
    for _, fs in pairs(P.labels) do TextColor(fs, K.fg, la) end

    -- drain tube, and the amber band cue back at rest (the wash and RESEAL at their resting alphas)
    local tc = known and col or K.steel
    Solid(P.tube, tc, known and C.TUBE_A or C.TUBE_NO_A)
    local oa = known and C.OUT_A or C.OUT_NO_A
    for _, t in ipairs(P.outline) do Solid(t, tc, oa) end
    Solid(P.band, K.amber, C.BAND_FILL)
    TextColor(P.reseal, K.amber, C.RESEAL_A)

    -- the drain parts hide until the live layer reads a time; the colours they wear are made here, never per frame
    ShowAll(DrainParts(), false)
    if known then
        if L.gradient then
            L.sealLo = CreateColor(col[1], col[2], col[3], C.FILL_A0)
            L.sealHi = CreateColor(col[1], col[2], col[3], 1)
        end
        L.sealTip = Mix(col, WHITE, C.TIP_MIX)
        L.sealDot = Mix(col, WHITE, C.DOT_MIX)
        L.glyphTint = Mix(col, WHITE, C.GLYPH_TINT)
        PaintFill(false)
        P.fill:SetAlpha(neon)
        Solid(P.tipBar, L.sealTip, C.TIP_A)
        P.tipBar:SetAlpha(neon)
        Tint(P.tipDot, L.sealDot, 1)
        P.tipDot:SetAlpha(neon)
        TextColor(P.count, col, neon)
        TextColor(P.countS, K.muted, C.S_A * neon)
    end

    -- the seal parts and the none parts
    ShowAll(SealParts(), known)
    ShowAll(NoneParts(), no)
    -- IN COMBAT is a statement about the fight: it shows only while the player is in combat. The mockup draws the NO SEAL
    -- look with it always on (it has no out of combat state), so out of combat the look keeps NO SEAL, -- and CAST A SEAL
    -- and drops the sub-label rather than claim a fight that is not on.
    P.noSub:SetShown(no and combat == true)
    if known then
        Tint(P.radial, col, C.RADIAL_A * neon)
        Tint(P.lens, col, neon)
        Tint(P.arcs, col, C.ARCS_A * neon)
        local path = MEDIA .. "seal_glyph_" .. id .. ".tga"
        P.glyph:SetTexture(path)
        Tint(P.glyph, L.glyphTint, neon)
        P.glyphHalo:SetTexture(path)
        Tint(P.glyphHalo, col, C.HALO_A * neon)
        TextColor(P.name, Mix(col, WHITE, C.NAME_TINT), C.NAME_A * neon)
        local long = #sl.n > C.NAME_LONG
        P.name.size = long and C.NAME_SIZE_LONG or C.NAME_SIZE
        P.name:SetText(sl.n)
        P.name.seat()
        P.caption:SetText(C.CAP_TEXT)
        TextColor(P.caption, col, C.CAP_A)
    end
    if no then
        TextColor(P.noSeal, K.red, 0.5 + 0.5 * pu)
    end
    -- the empty lane label follows the seal look; a debuff on the target takes the lane, so the label waits for it to clear
    L.laneText = known and (sl.deb > 0 and C.NOT_JUDGED or C.NO_DEBUFF) or ""
    SetStack(laneCol and "" or L.laneText)
    mode, sealId, inCombat, L.reduced = newMode, id, combat, reduce
end

-------------------------------------------------------------------------------
-- Live layer (drawSealChamber's animated terms; every function from Fract to Tick is on the per frame path)
-------------------------------------------------------------------------------

local floor, ceil, sin, cos, pi, huge = math.floor, math.ceil, math.sin, math.cos, math.pi, math.huge
local RING_BASE = C.RING_SIZE / C.RING_K        -- the ring texture at rest, image px (its circle is the lens radius)

-- The countdown strings, made once: the per frame path cannot format or concatenate. Whole seconds 0 to 30, tenths 0.0 to 5.0.
local WHOLE, TENTHS = {}, {}
for i = 0, C.MAX_S do WHOLE[i] = tostring(i) end
for i = 0, C.COUNT_FROM * 10 do TENTHS[i] = string.format("%d.%d", floor(i / 10), i % 10) end

-- A time from the Hud as a plain finite number, or nil: a secret (the guard first), a string, NaN and infinity read as unknown.
local function Plain(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    if type(v) ~= "number" or v ~= v or v == huge or v == -huge then return nil end
    return v
end

local function Fract(x)
    return x - floor(x)
end

-- sealNeon (mockup 1995 to 2041): the strike up table for 0 <= strike < .7 s after a cast, the dying tube in the last 5 s
-- (dropouts that get likelier and deeper, else a fast shimmer), else 1. The dying tube wins over the strike. Reduced motion
-- (the mockup's `if(reduce)` line) is a steady .8 while expiring and 1 otherwise.
local function NeonAt(strike, expiring, rem, t, reduce)
    if reduce == true then
        if expiring then return C.REDUCED_EXPIRING end
        return 1
    end
    if expiring and rem > 0 then
        local n = floor(t * C.FLICK_RATE)
        local p = C.DROP_P0 + C.DROP_P1 * (1 - rem / C.EXPIRE_S)
        if Fract(sin(n * C.FLICK_SEED) * C.FLICK_MUL) < p then
            return C.DROP_LO + C.DROP_SPAN * Fract(sin(n * C.FLICK_SEED2) * C.FLICK_MUL)
        end
        return C.STEADY_BASE + C.STEADY_AMP * sin(t * C.STEADY_FREQ)
    end
    if strike >= 0 and strike < C.STRIKE_S then
        local i = floor(strike / C.STRIKE_S * 7)
        if i > 6 then i = 6 end
        return C.STRIKE[i + 1]
    end
    return 1
end

-- u = .5 - .5 * cos(PI * clock / 1.4)
local function Pulse(t)
    return 0.5 - 0.5 * cos(pi * t / C.PULSE_S)
end

-- Whole seconds above 5 (a ceiling, clamped at 30), tenths from 5 down.
local function CountText(rem)
    if rem > C.COUNT_FROM then
        local n = ceil(rem)
        if n > C.MAX_S then n = C.MAX_S end
        return WHOLE[n]
    end
    return TENTHS[floor(rem * 10 + 0.5)] or TENTHS[0]
end

-- A text region's alpha, in place: the colour lives on fs.cur (Theme.ApplyMono resets from it at a rescale).
local function TextAlpha(fs, a)
    local cur = fs.cur
    cur[4] = a
    fs:SetTextColor(cur[1], cur[2], cur[3], a)
end

local function PaintText(fs, c, a)
    local cur = fs.cur
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-- One neon level scales every neon driven part (mockup: edge .55 + .45 * neon, glow .6 + .25 * neon, radial, lens, arcs, glyph
-- and its halo, name, the caption while expiring, the drain with its tip, the number and its S). Nothing is written when the
-- level did not move.
local function ApplyNeon(e)
    if e == L.neon then return end
    L.neon = e
    local col = L.col
    local edgeA = C.EDGE_A0 + C.EDGE_A1 * e
    Tint(P.edge, col, edgeA)
    Tint(P.glow, col, edgeA * Coverage(C.GLOW_K0 + C.GLOW_K1 * e))
    Tint(P.radial, col, C.RADIAL_A * e)
    Tint(P.lens, col, e)
    Tint(P.arcs, col, C.ARCS_A * e)
    Tint(P.glyph, L.glyphTint, e)
    Tint(P.glyphHalo, col, C.HALO_A * e)
    TextAlpha(P.name, C.NAME_A * e)
    TextAlpha(P.caption, L.expiring and C.CAP_A * e or C.CAP_A)
    TextAlpha(P.count, e)
    TextAlpha(P.countS, C.S_A * e)
    P.fill:SetAlpha(e)
    P.tipBar:SetAlpha(e)
    P.tipDot:SetAlpha(e)
end

-- The RESEAL band cue (remaining at or under 3 s): the wash breathes with the clock every frame in the band; the tube, its
-- outline, the drain, the tip, the dot and the number go amber once on the way in and back once on the way out.
local function SetBand(on, now)
    if on and not L.reduced then
        local pl = 0.5 + 0.5 * sin(now * C.BAND_PL_FREQ)
        P.band:SetColorTexture(K.amber[1], K.amber[2], K.amber[3], C.BAND_FILL + C.BAND_PL * pl)
        TextAlpha(P.reseal, C.RESEAL_IN0 + C.RESEAL_IN1 * Pulse(now))
    end
    if on == L.band then return end
    L.band = on
    local c = on and K.amber or L.col
    Solid(P.tube, c, C.TUBE_A)
    for i = 1, 4 do Solid(P.outline[i], c, C.OUT_A) end
    PaintFill(on)
    Solid(P.tipBar, on and L.amberTip or L.sealTip, C.TIP_A)
    local dot = on and L.amberDot or L.sealDot
    P.tipDot:SetVertexColor(dot[1], dot[2], dot[3], 1)
    PaintText(P.count, c, P.count.cur[4])
    if not on then
        P.band:SetColorTexture(K.amber[1], K.amber[2], K.amber[3], C.BAND_FILL)
        TextAlpha(P.reseal, C.RESEAL_A)
    elseif L.reduced then
        -- no breathing: the wash already rests at its base (Paint and the way out write it), RESEAL holds .55 + .45 * 1,
        -- written once on the way in
        TextAlpha(P.reseal, C.RESEAL_IN0 + C.RESEAL_IN1)
    end
end

-- EXPIRING in amber for the last 5 s, else SEAL ACTIVE in the seal colour.
local function SetExpiring(on)
    if on == L.expiring then return end
    L.expiring = on
    if on then
        P.caption:SetText(C.CAP_EXPIRING)
        PaintText(P.caption, K.amber, C.CAP_A * L.neon)
    else
        P.caption:SetText(C.CAP_TEXT)
        PaintText(P.caption, L.col, C.CAP_A)
    end
end

-- The NO SEAL pulse (u): edge .35 + .65 * u, the halo at that alpha times its coverage, the label .5 + .5 * u.
local function ApplyNoSeal(u)
    local a = C.NO_EDGE_A0 + C.NO_EDGE_A1 * u
    Tint(P.edge, K.red, a)
    Tint(P.glow, K.red, a * Coverage(u))
    TextAlpha(P.noSeal, 0.5 + 0.5 * u)
end

-- The drain: height remaining / 30 s of the tube (pinned at the full tube: a reconcile can report a duration above 30), shown
-- for more than .05 s; the number and its S show for any readable time (the mockup gates only the tube on rem > .05). The tip
-- bar and the dot ride the fill's top edge by their anchors, so a frame writes the fill height and nothing else, and that
-- height snaps to L.fillQ (a quarter screen pixel) so a steady drain writes only when a pixel quarter changes. No time hides all.
local function ApplyFill(rem)
    if rem and rem > C.FILL_MIN then
        local h = rem * (BOT - TOP) / C.MAX_S
        local q = L.fillQ
        if q then h = floor(h / q + 0.5) * q end
        if h > BOT - TOP then h = BOT - TOP end
        if not L.fillShown then
            L.fillShown = true
            P.fill:Show()
            P.tipBar:Show()
            P.tipDot:Show()
        end
        if h ~= L.fillH then
            L.fillH = h
            P.fill:SetHeight(ui(h))
        end
    elseif L.fillShown then
        L.fillShown = false
        P.fill:Hide()
        P.tipBar:Hide()
        P.tipDot:Hide()
    end
    if rem then
        if not L.countShown then
            L.countShown = true
            P.count:Show()
            P.countS:Show()
        end
    elseif L.countShown then
        L.countShown = false
        P.count:Hide()
        P.countS:Hide()
    end
end

-- The countdown: the text is written only when it changes, the S moves only when the text gets longer or shorter.
local function ApplyCount(rem)
    local text = CountText(rem)
    if text == L.countText then return end
    L.countText = text
    P.count:SetText(text)
    local len = #text
    if len ~= L.countLen then
        L.countLen = len
        P.countS.x = C.GX - C.COUNT_DX + len * C.MONO_ADV * C.COUNT_SIZE / 2 + C.S_GAP
        P.countS.seat()
    end
end

-- The Judgement ring: for .9 s after a Judgement it grows from the arcs' size by 26 of the lens radius's 50 on an ease out
-- cubic and fades with it (A(.85 * (1 - p))).
local function ApplyRing(now)
    local ja = L.judgeAt
    local f = -1
    if ja then f = now - ja end
    if f >= 0 and f < C.RING_S then
        local q = 1 - f / C.RING_S
        local p = 1 - q * q * q
        local size = RING_BASE * (C.GR + p * C.RING_GROW) / C.GR
        local col = L.col
        P.judgeRing:SetVertexColor(col[1], col[2], col[3], C.RING_A * (1 - p))
        L.ringSize = size
        P.judgeRing:SetSize(ui(size), ui(size))
        if not L.ringOn then
            L.ringOn = true
            P.judgeRing:Show()
        end
    elseif L.ringOn then
        L.ringOn = false
        P.judgeRing:Hide()
    end
end

-- The Judgement lane (lane 9). It follows the TARGET's debuff in state.judged, so every seal look (a seal, NO SEAL, unknown) can
-- carry it, and it wears the chamber's colour as the mockup does (2111, 2188 to 2194: `col`, the current seal's, red with no seal,
-- violet for the unknown look). A repaint (LaneLook) happens only when the lane goes between empty and a colour, or the colour
-- changes. The mockup uses the seal's id inside the chip only for the glyph, which v1 replaces with the spell icon.

-- One texture answer as a plain usable value: a positive finite number (a file id; a NaN fails the > 0) or a non empty string, else nil.
local function ReadTexture(fn, id)
    local ok, tex = pcall(fn, id)
    if not ok then return nil end
    if FS.IsSecret and FS.IsSecret(tex) then return nil end
    if type(tex) == "number" and tex > 0 and tex < huge then return tex end
    if type(tex) == "string" and tex ~= "" then return tex end
    return nil
end

-- The Judgement spell's icon: the id comes from the Hud's own spell table (HudSpells jd, 20271 verified in game), the texture from
-- C_Spell.GetSpellTexture, else the legacy GetSpellTexture. nil when the client will not say (the chip then draws without an icon).
local function JudgeIconId()
    local spells = FS.HudSpells
    local def = type(spells) == "table" and spells.jd
    local ids = type(def) == "table" and def.ids
    local id = type(ids) == "table" and ids[1]
    if type(id) ~= "number" then return nil end
    local tex
    local modern = C_Spell and C_Spell.GetSpellTexture
    if type(modern) == "function" then tex = ReadTexture(modern, id) end
    if tex == nil and type(GetSpellTexture) == "function" then tex = ReadTexture(GetSpellTexture, id) end
    return tex
end

-- Is `key` (a ledger seal key) one a Judgement debuff can be cast under? Righteousness, Fury and Command carry none in the mockup
-- (deb 0), an unmapped key or a non string one is nothing, a secret is never indexed.
local function KeyHasDebuff(key)
    if FS.IsSecret and FS.IsSecret(key) then return false end
    local id = KEY_ID[key]
    return id ~= nil and SEALS[id].deb > 0
end

-- The target's Judgement debuff from a Hud state: true with the plain expiresAt and appliedAt, or nil when there is none or it
-- cannot be read (false and nil both draw the empty lane: the mockup has no unknown look for the lane, DECIDED). An unreadable
-- expiresAt comes back as nil and the lane reads as empty, like any other time we cannot use.
local function JudgedOf(state)
    if FS.IsSecret and FS.IsSecret(state) then return nil end
    if type(state) ~= "table" then return nil end
    local jd = state.judged
    if FS.IsSecret and FS.IsSecret(jd) then return nil end
    if type(jd) ~= "table" then return nil end
    if not KeyHasDebuff(jd.key) then return nil end
    return true, Plain(jd.expiresAt), Plain(jd.appliedAt)
end

-- The current target's debuff straight from the Hud (FS.Hud.GetJudgement resolves the target itself): true with an absolute
-- expiresAt, or nil for none, unknown, a missing or throwing Hud and anything unreadable. No appliedAt, so no flash. A remaining of
-- zero or less lands on an expiresAt that is not in the future, which the next frame turns into the empty lane.
local function ReadJudgement(now)
    local Hud = FS.Hud
    local fn = type(Hud) == "table" and Hud.GetJudgement
    local ok, j = pcall(fn)
    if not ok then return nil end
    if FS.IsSecret and FS.IsSecret(j) then return nil end
    if type(j) ~= "table" then return nil end
    if not KeyHasDebuff(j.key) then return nil end
    local rem = Plain(j.remaining)
    if not rem then return nil end
    return true, now + rem
end

-- Is the target plainly dead? A secret, a missing API, a throw or an odd answer reads as alive (the lane is hidden only on a
-- plain yes; the legacy API answers 1).
local function TargetDead()
    local ok, v = pcall(UnitIsDead, "target")
    if not ok then return false end
    if FS.IsSecret and FS.IsSecret(v) then return false end
    return v == true or v == 1
end

-- Asks the client for the chip's icon and seats it, or hides the icon. Apply calls it only while L.jIcon is nil: the icon is the same
-- for every seal, so once the client has answered it is kept, and until then every push that carries a debuff asks again (a push
-- is rare, the per frame path never asks).
local function SeatJudgeIcon()
    local chip = P.jChip
    if not chip then return end
    local tex = JudgeIconId()
    L.jIcon = tex
    if tex then
        chip.icon:SetTexture(tex)
        chip.icon:Show()
    else
        chip.icon:Hide()
        -- spell data can simply be late, so the first nil is not a fault: log only when it stays unanswered across several asks
        local now = GetTime()
        L.iconAsks = L.iconAsks + 1
        L.iconSince = L.iconSince or now
        if L.iconAsks >= C.ICON_ASKS and now - L.iconSince >= C.ICON_WAIT then
            LogOnce("noicon", "the Judgement spell texture is still unavailable, the lane chip has no icon (asked again at each push)")
        end
    end
end

-- The lane's look in colour `col` (nil: the empty lane): the JUDGED header, the axis, ticks and numbers at their on or off alphas,
-- the bar and chip in the colour or hidden, the empty label. The moving parts start over (the next frame places them). The look
-- latches (laneCol) only after every write succeeded, so a throw is retried by the next push instead of leaving half a lane.
local function LaneLook(col)
    if col == laneCol then return end
    local on = col ~= nil
    TextColor(P.judged, on and col or K.muted, on and C.JUDGED_A_ON or C.JUDGED_A)
    Solid(P.jAxis, K.violet, on and C.JL_AX_A_ON or C.JL_AX_A)
    local ta = on and C.JL_TICK_A_ON or C.JL_TICK_A
    for i = 1, #P.jTicks do Solid(P.jTicks[i], K.violet, ta) end
    local la = on and C.JL_LABEL_A_ON or C.JL_LABEL_A
    for _, fs in pairs(P.jLabels) do TextColor(fs, K.fg, la) end
    SetStack(on and "" or L.laneText)
    L.jH, L.jBarOn, L.jChipOn, L.jPopOn = nil, false, false, false
    P.jBarGlow:Hide()
    P.jBarCore:Hide()
    local chip = P.jChip
    if chip then
        chip:Hide()
        P.jPop:Hide()
    end
    if not on then
        laneCol = nil
        return
    end
    if L.gradient then
        local g = L.jGrad[col]
        if not g then
            g = { CreateColor(col[1], col[2], col[3], C.JL_BAR_A0), CreateColor(col[1], col[2], col[3], 1) }
            L.jGrad[col] = g
        end
        P.jBarGlow:SetGradient("VERTICAL", g[1], g[2])
        P.jBarCore:SetGradient("VERTICAL", g[1], g[2])
    else
        P.jBarGlow:SetColorTexture(col[1], col[2], col[3], 1)
        P.jBarCore:SetColorTexture(col[1], col[2], col[3], 1)
    end
    if chip then
        chip.fsSkin.border.ring:SetVertexColor(col[1], col[2], col[3], 1)
        chip.fsSkin.glow:SetVertexColor(col[1], col[2], col[3], Coverage(C.CHIP_GLOW_K))
        chip.fsAuraPlate:SetAlpha(C.CHIP_PLATE_A)
    end
    laneCol = col
end

-- The bar and the chip for `rem` seconds left: the chip centred on jY(rem), the bar from the foot up to the chip's lower edge
-- (mockup: y = jY(jrem), the stroke runs BOT to min(BOT, y + CHP), so inside the last CHP the chip covers it and the bar goes). The
-- axis is 0 to 40 s and a longer debuff (a reconcile can report one; the mockup has none) pins at the top. The height snaps to a quarter screen pixel like the drain's, so a steady
-- tick writes only when a quarter changes; the bar and the chip are written together, nothing else moves.
local function ApplyLaneBar(rem)
    local h = rem * (BOT - TOP) / C.JL_MAX_S
    local q = L.fillQ
    if q then h = floor(h / q + 0.5) * q end
    if h > BOT - TOP then h = BOT - TOP end
    if h == L.jH then return end
    L.jH = h
    local len = h - C.CHS / 2
    if len > 0 then
        local u = ui(len)
        P.jBarGlow:SetHeight(u)
        P.jBarCore:SetHeight(u)
        if not L.jBarOn then
            L.jBarOn = true
            P.jBarGlow:Show()
            P.jBarCore:Show()
        end
    elseif L.jBarOn then
        L.jBarOn = false
        P.jBarGlow:Hide()
        P.jBarCore:Hide()
    end
    local chip = P.jChip
    if chip then
        Point(chip, "CENTER", C.JL_X, BOT - h)
        if not L.jChipOn then
            L.jChipOn = true
            chip:Show()
        end
    end
end

-- The debuff ran out before the Hud said so: the lane empties at once (the Hud's late push for it, judged false, repaints nothing).
local function ExpireJudged()
    L.jExp, L.jApplied = nil, nil
    LaneLook(nil)
end

-- The lane's frame: the bar and chip follow expiresAt - GetTime(); a debuff that landed within POP_S shows the white flash on the chip,
-- fading with its age (1 - age / .35, times .8). Neither is gated by reduced motion, as in the mockup.
local function LiveJudged(now)
    local ea = L.jExp
    if not ea then return end
    local rem = ea - now
    if rem <= 0 then
        ExpireJudged()
        return
    end
    ApplyLaneBar(rem)
    local pop, pa = P.jPop, L.jApplied
    if not pop then return end
    local age = -1
    if pa then age = now - pa end
    if age >= 0 and age < C.POP_S then
        pop:SetVertexColor(K.white[1], K.white[2], K.white[3], (1 - age / C.POP_S) * C.POP_A)
        if not L.jPopOn then
            L.jPopOn = true
            pop:Show()
        end
    elseif L.jPopOn then
        L.jPopOn = false
        pop:Hide()
    end
end

local function LiveNone(now)
    if L.combat and not L.reduced then ApplyNoSeal(Pulse(now)) end
end

-- The seal ran out: the chamber flips to NO SEAL itself, wearing the combat flag the last push carried. The Hud's own push for
-- the expiry (the change detector sees the seal as gone) lands within one 0.2 s tick; the self flip gives immediacy and that
-- late push repaints nothing.
local function Expire()
    Paint("none", nil, L.combat, L.reduced)
    LaneLook(L.jExp and L.col or nil)           -- a debuff on the target follows the chamber's colour to red at once
end

local function LiveSeal(now)
    local ea = L.expiresAt
    local rem = nil
    if ea then
        rem = ea - now
        if rem <= 0 then
            Expire()
            LiveNone(now)
            return
        end
    end
    local ca = L.castAt
    local strike = -1
    if ca then strike = now - ca end
    local expiring = rem ~= nil and rem <= C.EXPIRE_S
    SetBand(rem ~= nil and rem <= C.BAND_S, now)
    SetExpiring(expiring)
    ApplyNeon(NeonAt(strike, expiring, rem or 0, now, L.reduced))
    ApplyFill(rem)
    if L.countShown then ApplyCount(rem) end
    ApplyRing(now)
end

local function Live(now)
    if mode == "seal" then
        LiveSeal(now)
    elseif mode == "none" then
        LiveNone(now)
    end
    LiveJudged(now)
end

-- Does anything move? A debuff on the target (its bar drains), a timed seal, a strike or ring window still open, the NO SEAL pulse in
-- combat. Reduced motion drops the strike and the pulse; the drains, the countdown, the ring and the landing flash (which the mockup
-- does not gate) still move.
local function Animating(now)
    if L.broken then return false end
    if L.jExp then return true end
    if mode == "seal" then
        if L.expiresAt then return true end
        local ca = L.castAt
        if not L.reduced and ca and now - ca >= 0 and now - ca < C.STRIKE_S then return true end
        local ja = L.judgeAt
        if ja and now - ja >= 0 and now - ja < C.RING_S then return true end
        return false
    end
    return mode == "none" and L.combat and not L.reduced
end

-- The chamber's one OnUpdate. A throw stops the ticker (logged once) until the next push.
local function Tick()
    local now = GetTime()
    local ok, err = pcall(Live, now)
    if not ok then
        LogOnce("tick", err)
        L.broken = true
    end
    if not Animating(now) then Sync() end
end

-- Install the OnUpdate when something moves and the piece is on, clear it the moment nothing does.
function Sync()
    local want = false
    if subscribed and chamber and Animating(GetTime()) then want = true end
    if want == ticking then return end
    ticking = want
    if want then
        chamber:SetScript("OnUpdate", Tick)
    else
        chamber:SetScript("OnUpdate", nil)
    end
end

Seals.Neon, Seals.Pulse, Seals.CountText = NeonAt, Pulse, CountText

-- ForeverSTUwaveDB.reducedMotion == true, the flag ConsoleKeys.lua reads (only an exact true counts). Read at each Hud push.
local function ReducedMotion()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

-- A plain string key from our own ledger, mapped to a seal id; anything else is nil.
local function SealIdOf(seal)
    if type(seal) ~= "table" then return nil end
    local key = seal.key
    if FS.IsSecret and FS.IsSecret(key) then return nil end
    if type(key) ~= "string" then return nil end
    return KEY_ID[key]
end

-- The Hud's plain combat boolean; a secret, a non boolean or a missing flag is not combat (the guard comes first, a secret is
-- never compared).
local function CombatOf(state)
    local flag = state.inCombat
    if FS.IsSecret and FS.IsSecret(flag) then return false end
    return flag == true
end

-- mode, seal id, in combat. Only the NO SEAL look reads the combat flag, so no other look repaints when combat changes.
local function Resolve(state)
    if FS.IsSecret and FS.IsSecret(state) then return "unknown" end
    if type(state) ~= "table" then return "unknown" end
    local seal = state.seal
    if FS.IsSecret and FS.IsSecret(seal) then return "unknown" end
    if seal == false then return "none", nil, CombatOf(state) end
    local id = SealIdOf(seal)
    if id then return "seal", id end
    return "unknown"
end

-- One push: read the plain times and the reduced motion flag, repaint if the look changed, then let the live layer write what moves. A timed seal that
-- is already out reads as NO SEAL at once. The look latches (mode, sealId, inCombat) only after Paint succeeded, so a
-- throwing repaint is retried by the next push.
local function Apply(state)
    local newMode, id = Resolve(state)
    local reduce = ReducedMotion()
    local seal = newMode == "seal" and state.seal or nil
    L.broken = false
    L.combat = newMode ~= "unknown" and CombatOf(state) or false
    L.expiresAt = seal and Plain(seal.expiresAt) or nil
    L.castAt = seal and Plain(seal.castAt) or nil
    L.judgeAt = seal and Plain(state.judgeAt) or nil
    if L.expiresAt and L.expiresAt - GetTime() <= 0 then
        newMode, id = "none", nil
    end
    local jid, jexp, japp = JudgedOf(state)
    local dead = jid and TargetDead() or false                    -- a corpse carries no lane
    if dead then jexp, japp = nil, nil end
    L.jDead = dead
    L.jExp, L.jApplied = jexp, japp
    local combat = newMode == "none" and L.combat or false
    if newMode ~= mode or id ~= sealId or combat ~= inCombat or reduce ~= L.reduced then
        Paint(newMode, id, combat, reduce)
    end
    LaneLook(L.jExp and L.col or nil)
    if laneCol and not L.jIcon then SeatJudgeIcon() end
    Live(GetTime())
    Sync()
end

local function OnState(state)
    if not subscribed then return end          -- a stale push after the piece went off
    local ok, err = pcall(Apply, state)
    if not ok then LogOnce("state", err) end
end

-- The lane between Hud pushes. HudLogic pushes on its 0.2 s tick, so after a retarget the lane would show the old target's bar for
-- up to 0.2 s: PLAYER_TARGET_CHANGED reads the Hud's own judgement for the target at once (ReadTarget below) and repaints, an
-- unreadable answer emptying the lane rather than keeping the old bar; the push that follows carries the full entry and takes over.
-- A target that dies keeps its ledger entry, so UNIT_HEALTH for the target hides the lane too (L.jDead remembers that death alone hid
-- it), and a UNIT_HEALTH that finds the target alive again relights it the same way a retarget does. Nothing is read with no debuff on
-- the lane, and a live target's health event changes nothing.
-- The current target's debuff straight from the Hud, but only when the target GUID is plain or nil. A secret GUID is where the Hud's
-- own target handler may not have run yet, so the direct read could be the old target's: nil (the lane stays empty) and the push that
-- follows decides. A GUID that cannot be read at all cannot be vouched for either. Returns the absolute expiresAt or nil.
local function ReadTarget(now)
    local ok, guid = pcall(UnitGUID, "target")
    if not ok or (FS.IsSecret and FS.IsSecret(guid)) then return nil end
    local _, e = ReadJudgement(now)
    return e
end

local function TargetMoved(event)
    local now = GetTime()
    local changed, dead = false, nil
    if event == "PLAYER_TARGET_CHANGED" then
        L.jExp, L.jApplied = ReadTarget(now), nil
        changed = true
    elseif L.jDead then
        -- hidden only because the target was dead: a resurrection relights it from the Hud's own read
        if TargetDead() then return end
        dead = false
        L.jExp, L.jApplied = ReadTarget(now), nil
        changed = true
    end
    if L.jExp then
        if dead == nil then dead = TargetDead() end
        if dead then L.jExp, L.jApplied = nil, nil; changed = true end
    end
    L.jDead = dead or false
    if not changed then return end
    L.broken = false
    LaneLook(L.jExp and L.col or nil)
    if laneCol and not L.jIcon then SeatJudgeIcon() end
    Live(now)
    Sync()
end

local function OnTargetEvent(_, event)
    local ok, err = pcall(TargetMoved, event)
    if not ok then LogOnce("target", err) end
end

-- One frame on the chamber for the target change and the target's health (the DoT scale's own death watch registers the same way).
-- It is built bare and listens only while the piece is subscribed: Subscribe registers, Unsubscribe unregisters.
local function BuildEvents()
    local f = CreateFrame("Frame", nil, chamber)
    f:SetScript("OnEvent", OnTargetEvent)
    P.events = f
end

-- Only reached with the chamber built (Subscribe and Unsubscribe run from the piece hooks after the build).
local function ListenTarget(on)
    local f = P.events
    if on then
        f:RegisterEvent("PLAYER_TARGET_CHANGED")
        pcall(f.RegisterUnitEvent, f, "UNIT_HEALTH", "target")      -- a client without the unit filter just gets no health event
    else
        f:UnregisterEvent("PLAYER_TARGET_CHANGED")
        f:UnregisterEvent("UNIT_HEALTH")
    end
end

-------------------------------------------------------------------------------
-- Piece follow and build
-------------------------------------------------------------------------------

local function Subscribe()
    if subscribed then return end
    local Hud = FS.Hud
    if not (Hud and Hud.Subscribe) then
        LogOnce("nohud", "FS.Hud is missing, the Seal Chamber has no data")
        return
    end
    subscribed = true
    Hud.Subscribe(OnState)                     -- pushes the current state at once
    local ok, err = pcall(ListenTarget, true)  -- the lane works from pushes alone if the events cannot be had
    if not ok then LogOnce("listen", err) end
end

local function Unsubscribe()
    if subscribed and FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnState) end
    subscribed = false
    ListenTarget(false)
    Sync()
end

-- Does the class profile give the DoT seat to the chamber (the one shared rule, as ConsoleKeys and the DoT scale ask)?
-- true: it does. false: DECIDED, it does not (another class slot, a profile with neither, a missing or throwing helper).
-- nil: no profile yet, HudLogic has no change hook and may resolve it after the pieces build, so the question stays open.
local function OwnsSeat()
    local Hud, Profiles = FS.Hud, FS.HudProfiles
    if type(Hud) ~= "table" or type(Hud.GetProfile) ~= "function" then return false end
    if type(Profiles) ~= "table" or type(Profiles.ClassSlot) ~= "function" then return false end
    local ok, profile = pcall(Hud.GetProfile)
    if not ok then return false end
    if profile == nil then return nil end
    local ok2, slot = pcall(Profiles.ClassSlot, profile)
    return ok2 and slot == "seals"
end

local settled = false          -- the answer is final (built, or decided never to build): nothing asks again
local Build

-- The chamber follows the dot piece, and while no profile has arrived the same two signals ask again: a piece change and a
-- rescale. Both are registered once and never removed (a Layout callback cannot be); a class that decided at the first ask
-- never gets here, so Warlock and Priest add no callback.
local retryHooked = false
local function HookRetries()
    if retryHooked then return end
    retryHooked = true
    if FS.Layout and FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            if chamber then SeatAll() else Build() end
        end)
    end
    Gunsight.OnPieceChanged(function(key, on)
        if key ~= "dot" then return end
        if not chamber then Build() return end
        if on then Subscribe() else Unsubscribe() end
    end)
end

local function BuildChamber()
    local Theme = FS.Theme
    if not (Theme and Theme.ApplyMono and Theme.AddSliceTexture and Theme.AddCut2Texture and Theme.ApplyNineSlice
            and Theme.SLICE_GLOW_TEXTURE and Theme.SLICE_CUT2_FILL_TEXTURE and Theme.SLICE_CUT2_OUTLINE_TEXTURE) then
        LogOnce("notheme", "Theme is missing, the Seal Chamber is not built")
        return
    end
    chamber = CreateFrame("Frame", "ForeverSTUwaveGunsightSeals", FS.GunsightDots.frame)
    local ok, err = pcall(function()
        BuildFrame()
        BuildRuler()
        BuildBand()
        BuildTube()
        BuildLens()
        BuildCount()
        BuildNoSeal()
        BuildJudgementLane()
        BuildEvents()
        Paint("unknown", nil, false)
    end)
    if not ok then
        LogOnce("build", err)
        chamber:Hide()
        chamber = nil
        return
    end
    Seals.frame, Seals.parts = chamber, P
    HookRetries()
    if Gunsight.IsPieceOn("dot") then Subscribe() end
end

-- Latches only once the gates have an answer: a profile that has not arrived yet leaves the question open (a late Paladin
-- profile builds on the next ask), where the old build latched first and lost the chamber for the session.
function Build()
    if built or settled then return end
    if not Gunsight.IsEnabled() then settled = true return end
    local owns = OwnsSeat()
    if owns == nil then HookRetries() return end
    settled = true
    if not owns then return end
    local Dots = FS.GunsightDots
    if not (Dots and Dots.frame) then
        LogOnce("nodots", "FS.GunsightDots.frame is missing, the Seal Chamber has no piece frame to hang off")
        return
    end
    -- the piece frame exists once the DoT file's build ran, but the piece registers only after that build succeeded: a
    -- throw in it leaves a frame no console key or SetPiece can show, so the chamber would hang off a dead frame
    if Dots.registered ~= true then
        LogOnce("nopiece", "the DoT piece never registered (its build failed), the Seal Chamber is not built")
        return
    end
    built = true
    BuildChamber()
end

function Seals.Mode() return mode, sealId end

Gunsight.OnReady(Build)
