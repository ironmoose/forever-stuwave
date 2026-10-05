-- Forever STUwave: Minimap
-- Rounded mask, feature-detected Blizzard-chrome hide, custom neon border/
-- glow, mouse-wheel zoom, a restyled zone-text label, a cyan north tick, a
-- control bezel below the map (reparented tracking/calendar/mail keys on the
-- left -- zoom is mouse-wheel only, and Blizzard's zoom buttons are hidden
-- outright rather than reparented, see HideBlizzardChrome -- the coord/clock
-- LCD re-anchored on the right), a single tiled horizontal scanline overlay, a
-- soft top-left highlight, a magenta glow behind the native player blip, and a
-- tray drawer below the bezel that COLLECTS the addon minimap buttons (LibDBIcon
-- and stray *MinimapButton* frames) so they stop cluttering the map edge, popped
-- out by a small tab hanging off the bezel's bottom edge. The
-- vignette/glare CRT elements and the pulsing waypoint marker are a
-- deliberate second chunk, still deferred (no existing waypoint-arrow
-- handling was found anywhere in this addon to build on). Every Blizzard-
-- chrome lookup below is nil-guarded so a missing name degrades to a no-op
-- instead of erroring.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local AddOuterGlow = FS.Theme.AddOuterGlow
local AddGradientBorder = FS.Theme.AddGradientBorder
local AddRoundedFill = FS.Theme.AddRoundedFill
local ApplyFontGeneric = FS.Theme.ApplyFontGeneric
local ApplyMono = FS.Theme.ApplyMono
local SkinButton = FS.Theme.SkinButton
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_TEXT_WHITE = FS.Theme.COLOR_TEXT_WHITE
local FONT_ORBITRON = FS.Theme.FONT_ORBITRON
local GLOW_EDGE_TEXTURE = FS.Theme.GLOW_EDGE_TEXTURE

-- Same border/glow color token the UnitFrames panel uses; hard-square mask so
-- this pass uses radius 0 (no rounded-corner arcs) rather than PANEL_RADIUS.
local BORDER_THICK = 1 -- mockup minimap borderWidth:1
local GLOW_SIZE -- derived in RefreshMetrics below (Metrics.glowSize)
local GLOW_ALPHA = 0.20 -- was 0.42 (too bright, read as a second border); cut to 0.20 for a soft ambient halo (2026-09-26 minimap fix). Retune here if still too visible/faint.
local SQUARE_RADIUS = 0
-- Map face glow + border chamfer under Theme.CHROME_CORNERS "cut": the baked
-- mask_minimap.tga clips the map with a TOP-LEFT / BOTTOM-RIGHT chamfer of 6/250, so the
-- border and glow cut the same two corners at 6 (TOP-RIGHT / BOTTOM-LEFT stay square).
local MAP_CHAMFER = 6

-- Mockup #ffb648, converted to 0-1; Theme has no amber token (checked), so it
-- is local to this readout only. Its only use in this file is the coords/
-- clock LCD readout's clock half (see ApplyReadout).
local COLOR_AMBER = { 1, 0.714, 0.282, 1 }

-- Mockup mail-key accent (#ff2e97) is the exact value already tokenized as
-- Theme.COLOR_HEALTH, so it is reused here rather than re-declared.
local COLOR_PINK = COLOR_HEALTH

-- Mockup border color: color-mix(in srgb, var(--cyan) 60%, var(--violet)).
-- cyan (Theme.COLOR_POWER) = {0.133, 0.878, 1}; violet (Theme.COLOR_BORDER)
-- = {0.659, 0.333, 0.969}. Per-channel color-mix at 60% cyan / 40% violet:
--   r: 0.133*0.6 + 0.659*0.4 = 0.0798 + 0.2636 = 0.3434 ~= 0.343
--   g: 0.878*0.6 + 0.333*0.4 = 0.5268 + 0.1332 = 0.6600 = 0.660
--   b: 1.000*0.6 + 0.969*0.4 = 0.6000 + 0.3876 = 0.9876 ~= 0.988
local COLOR_BORDER_BLEND = { 0.343, 0.660, 0.988, 1 }

-- Control bezel: near-black chassis frame below the Minimap holding the
-- reparented Blizzard minimap-button keys (left) and the coord/clock LCD
-- (right). Reuses the readout chip's near-black fill for the same "console
-- housing" look; its own border/radius are local since the mockup gives the
-- chassis a slightly rounded strip against the hard-square map above it.
-- EVERY size below is DERIVED from the map edge, exactly as the mockup does
-- it. mockups/full-ui-layout.html's minimap renderer computes m = min(w,h) and
-- then sizes each part as a fraction of m:
--
--     btn   = max(9,  m*0.12)      bezel key edge
--     bf    = max(5,  btn*0.5)     key glyph
--     rad   = max(2,  btn*0.24)    key corner radius (mockup border-radius:24%)
--     off   = max(1,  m*0.018)     chassis padding; gaps are off*1.6
--     blip  = max(3,  m*0.04)      player blip
--     zoneF = max(6,  m*0.092)     zone text
--     coordF= max(5,  m*0.058)     LCD readout text
--     northF= max(5,  m*0.062)     N tick
--     rowH  = max(30, round(m*0.17))   bezel row height  (mmRowGP)
--     glowP = max(4,  m*0.076)     outer glow size (gb_px=round(6+glow/100*22)=19px at glow:60, 19/250=0.076)
--
-- The previous constants were hardcoded at roughly half these values (key 20
-- vs 30, zone 9 vs 23, north 7 vs 15.5, readout 10 vs 14.5 at m=250), which is
-- why the console read as small text on a big map instead of the mockup's
-- chunky CRT chassis. Deriving them also means a planner re-export at a
-- different map size stays proportional instead of needing every number
-- re-tuned by hand.
--
-- `m` itself is now read from FS.Layout.minimap's SCALED size (L.scaledW/
-- scaledH, populated by FS.Layout.Apply) rather than the raw design w/h --
-- see ApplyLayout's own comment below on the right-edge-cutoff bug this
-- fixes. DeriveMetrics runs once at file load (raw design values, before
-- Apply has run) and again from RefreshMetrics inside ApplyLayout once
-- Minimap's real scaled size is known.
local Metrics = {}

local function DeriveMetrics()
    local L = FS.Layout and FS.Layout.minimap
    local w = (L and (L.scaledW or L.w)) or 250
    local h = (L and (L.scaledH or L.h)) or 250
    local m = math.min(w, h)
    local btn = math.max(9, m * 0.12)
    local off = math.max(1, m * 0.018)

    Metrics.map = m
    Metrics.keySize = btn
    Metrics.keyFont = math.max(5, btn * 0.5)
    Metrics.keyRadius = math.max(2, btn * 0.24) -- mockup border-radius:24% (was 0.22)
    Metrics.pad = off * 1.6
    Metrics.keyGap = off * 1.6
    Metrics.blip = math.max(3, m * 0.04)
    Metrics.zoneFont = math.max(6, m * 0.092)
    Metrics.coordFont = math.max(5, m * 0.058)
    Metrics.northFont = math.max(5, m * 0.062)
    Metrics.northInset = off
    Metrics.rowHeight = math.max(30, math.floor(m * 0.17 + 0.5))
    -- was m*0.076 (glow band read as a second border); halved to m*0.038 (2026-09-26 minimap fix). Retune here if still too wide/narrow.
    Metrics.glowSize = math.max(4, m * 0.038)
    return Metrics
end

local BEZEL_HEIGHT
local BEZEL_RADIUS = 4
local BEZEL_BORDER_THICK = 1
local BEZEL_PADDING
local KEY_GAP
local KEY_SIZE

local NORTH_FONT_SIZE
local NORTH_INSET_Y

-- Readout box chrome: near-black fill (#04020c) and a faint cyan border, both
-- matching mockups/full-ui-layout.html's .mmreadout rather than the panel's
-- COLOR_BG/COLOR_BORDER tokens, which read too bright for this small a chip.
-- Also reused as the bezel keys' own dark fill (item 9) and the tray
-- drawer's fill (item 10): a single near-black "console housing" color
-- rather than three separate near-duplicate tokens.
local READOUT_FILL = { 0.016, 0.008, 0.047, 0.85 }
local READOUT_BORDER = { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.35 }
local READOUT_RADIUS = 4
local READOUT_BORDER_THICK = 1
local READOUT_HEIGHT
local READOUT_INSET_X = 8
local READOUT_FONT_SIZE
-- The box takes whatever the bezel has left of the THREE key slots (tracking, calendar, mail;
-- see RefreshMetrics). The mail slot is only visible while mail is waiting, but its seat is
-- always reserved: sizing the box for two keys put it 26 px under the pink slot at m = 250
-- (Parker: "when i get mail it goes behind the cords"). The text is then sized to the box, not
-- the other way round: READOUT_FIT.chars mono glyphs ("99.9, 99.9" + a space + "19:56") at
-- READOUT_FIT.advance em each (Mononoki Nerd Font Mono, measured 0.5615 em) inside
-- READOUT_FIT.inset per side. The coord formatter (FormatCoord) clamps each number to
-- COORD_MAX 99.9, so the reading is never wider than "99.9, 99.9": an unclamped "100.0, 100.0"
-- is 17 glyphs with the clock, which overlapped the clock by about 7 px at m = 250.
local READOUT_WIDTH
local READOUT_FIT = { chars = 16, advance = 0.5615, inset = 4 }
-- Frame levels above the bezel: the readout box sits at +1, the keys above it at +3, so a key
-- (the pink mail slot and its envelope in particular) is never painted under the box.
local READOUT_LEVEL_OFFSET = 1
local KEY_LEVEL_OFFSET = 3

local ZONE_FONT_SIZE

-- Existing shipped asset (see Chat.lua's identical local declaration for its
-- own scanline overlay): a 4x4 tiling texture, one dark row over transparent.
-- SCANLINE_ALPHA keeps the scrim subtle over the small, blip-busy map face.
local SCANLINE_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\scanline.tga"
local SCANLINE_ALPHA = 0.65 -- mockup scan:26 -> opacity 26/40

-- NEW: mask with a small baked-in corner radius (item 3), replacing the flat
-- hard-square WHITE8X8 mask.
local MASK_MINIMAP_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\mask_minimap.tga"

-- NEW: soft top-left highlight (item 6) reuses the existing glow_round.tga
-- (128x128 radial falloff, see generate_glow_round.py) rather than a new
-- texture. Not exported as a Theme.* constant (checked -- no such export
-- exists), so this is a local path constant, same idiom as SCANLINE_TEXTURE
-- above and as ChatCore.lua/XPBar.lua/DataBar.lua/UnitFrames.lua's own
-- identical local declarations of the same path.
local GLOW_ROUND_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"
local HIGHLIGHT_COLOR = { 0.84, 0.94, 1, 1 } -- mockup rgba(215,240,255,...), pale cyan-white
local HIGHLIGHT_ALPHA = 0.11
local HIGHLIGHT_SIZE_FRACTION = 0.55 -- 45-60% of the map per the mockup's radial-gradient

-- NEW: player blip glow (item 7) -- a magenta halo behind Blizzard's native,
-- always-centered player arrow.
local BLIP_GLOW_SIZE_MULT = 3.5 -- mockup: Metrics.blip * 3 to * 4
local BLIP_GLOW_ALPHA = 0.5

-- NEW: bezel key underline glow bar (item 9, .mmbtn::after).
local KEY_UNDERLINE_HEIGHT = 2 -- ~2px scaled per the mockup
local KEY_UNDERLINE_INSET_FRACTION = 0.20 -- 20%-80% inset -> ~60% width, centered
local KEY_UNDERLINE_BOTTOM_FRACTION = 0.13 -- 13% up from the key's bottom edge

-- Mail key's notification dot (mockup .mmbtn .nd): a round pink dot straddling the key's
-- top-right corner (top:-2px; right:-2px), size max(3, btn*0.34), with a soft pink glow.
-- The glow reach is 3 px, not the mockup's ~5: the mockup's key has overflow:hidden, which
-- clips its box-shadow at the key edge, but WoW does not clip a texture to its parent, so the
-- halo draws at full reach. At 5 it extended about 7 px past the key edge (KEY_DOT_OFFSET + reach)
-- and touched the readout box border; at 3 it stops about 5 px out.
local KEY_DOT_SIZE_FRACTION = 0.34
local KEY_DOT_OFFSET = 2
local KEY_DOT_GLOW_REACH = 3
local KEY_DOT_GLOW_ALPHA = 0.6
-- Our own handle on the dot textures (never a field on Blizzard's MailFrame).
local mailDot = {}

local function RefreshMetrics()
    DeriveMetrics()

    -- Plain reassignment, not `local` redeclaration: every function below
    -- that reads these closed over the SAME upvalue slots at file-load time,
    -- and Lua closures share upvalues by reference, not by value -- a
    -- redeclare here would create new locals those functions never see.
    BEZEL_HEIGHT = Metrics.rowHeight
    BEZEL_PADDING = Metrics.pad
    KEY_GAP = Metrics.keyGap
    KEY_SIZE = Metrics.keySize

    NORTH_FONT_SIZE = Metrics.northFont
    NORTH_INSET_Y = Metrics.northInset

    -- The box starts one key gap right of the third key and ends READOUT_INSET_X short of the
    -- bezel's right edge (floored, so the gap to the key can only grow).
    local keysRight = BEZEL_PADDING + 3 * KEY_SIZE + 2 * KEY_GAP
    READOUT_HEIGHT = math.floor(Metrics.coordFont * 1.6 + 0.5)
    READOUT_WIDTH = math.floor(Metrics.map - READOUT_INSET_X - (keysRight + KEY_GAP))
    READOUT_FONT_SIZE = math.max(5, math.min(Metrics.coordFont,
        (READOUT_WIDTH - 2 * READOUT_FIT.inset) / (READOUT_FIT.chars * READOUT_FIT.advance)))

    ZONE_FONT_SIZE = Metrics.zoneFont

    GLOW_SIZE = Metrics.glowSize
end

-- Initial pass at file load, before FS.Layout.Apply has run (raw 250x252
-- design values, via DeriveMetrics' own w/h fallback). ApplyLayout below
-- calls this again once Minimap's real SCALED size is known.
RefreshMetrics()

-------------------------------------------------------------------------------
-- Layout (reposition + resize)
-------------------------------------------------------------------------------

-- MinimapCluster is the modern-engine container that owns the minimap's
-- on-screen position (already referenced as a feature-detected candidate in
-- HideBlizzardChrome below); repositioning the bare Minimap while the cluster
-- still anchors it can fight, so the cluster is the preferred target and
-- Minimap is only a fallback when it does not exist. Unverified in-game like
-- the rest of this file's Blizzard-chrome lookups.
-- MinimapCluster is TALLER THAN ITS MAP. It reserves a header strip above the
-- map for the zone text and the expansion/addon-compartment buttons, and
-- hiding those children does not give the space back -- the reservation is the
-- cluster's own geometry. Parker, 2026-09-22: "the minmap has some invisible
-- stuff above it", which is exactly this.
--
-- So seating the CLUSTER at FS.Layout.minimap puts the cluster's box where the
-- layout asks and leaves the visible map sitting lower inside it by the header
-- height, which is what "the minimap is not at the top of the screen" was.
--
-- Rather than hardcode a header height (it differs per client build, and the
-- names involved have already been guessed wrong twice in this file), the
-- offset is MEASURED: seat the cluster, then read how far the map's own edges
-- sit inside the cluster's and shift the cluster by that much so the MAP lands
-- where the layout meant. Self-correcting, and it needs no name to be right.
-- WHY the cluster is anchored by the edge the map hangs from, not by its middle.
-- MinimapContainer hangs from ONE cluster edge, centred: its TOP at (10, -30), or its
-- BOTTOM at (10, 30) with Edit Mode's Header Underneath setting (Blizzard_Minimap/
-- Mainline/Minimap.lua, SetHeaderUnderneath), and the Minimap sits CENTER in it. So the
-- map's offset from THAT edge and from the cluster's centre column does not depend on
-- the cluster's size. MinimapCluster is a ResizeLayoutFrame (Minimap.xml:3): every
-- Layout pass (the synchronous one in EditModeMinimapSystemMixin:
-- UpdateSystemSettingHeaderUnderneath, or the deferred OnUpdate one a MarkDirty arms)
-- resets its size to its children's extents and overrides the SetSize FS.Layout.Apply
-- wrote. The old compensation anchored the cluster's CENTER at the layout point, which
-- is right only while the cluster stays exactly the height Apply set; a Layout pass
-- after it moved the map by (H' - H) / 2 (about 30 units too high). That is what the
-- mock in minimap-harness.py reproduces, and ONLY when a Layout pass lands after our
-- re-seat. Whether Blizzard's real first-login sequence does that (Parker's new Mage,
-- 2026-10-05: chat right, minimap not) is UNVERIFIED; the seat log (minimapSeatLog,
-- mt vs tt and ml vs tl) is the instrument that settles it.
--
-- The inset itself is MEASURED and re-measured, because it is not constant: Edit
-- Mode's Size setting (SetEditModeScale on the container) and header setting change
-- it, and both are applied by EditModeManagerFrame:UpdateLayoutInfo, which the server
-- triggers AFTER login on a character's first login (on a /reload the layout is
-- already applied before addons load). Hooks below re-run the compensation after each
-- of them, and re-seat when Edit Mode puts the cluster back at its own anchor. Every
-- hooked name is verified against the retail 12.1.0 source only; each hook is
-- feature-detected, a missing one is skipped, and the seat log's "hooks" entry says
-- which ones installed.
local CompensateClusterInset, ScheduleCompensate, InstallSeatWatch

do
    local FRAC = {
        TOPLEFT = { 0, 1 }, TOP = { 0.5, 1 }, TOPRIGHT = { 1, 1 },
        LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 }, RIGHT = { 1, 0.5 },
        BOTTOMLEFT = { 0, 0 }, BOTTOM = { 0.5, 0 }, BOTTOMRIGHT = { 1, 0 },
    }

    local compensatePending = false   -- a compensation timer is armed
    local compensateHeld = false      -- a compensation was refused in combat (protected cluster)
    local reseatPending = false       -- a re-seat is armed, or refused in combat
    local installed = false

    -- A plain number or nil: a secret is never read, a non-number never used.
    local function Num(v)
        if type(v) ~= "number" then return nil end
        if FS.IsSecret and FS.IsSecret(v) then return nil end
        return v
    end

    local function Round(v, step)
        if not v then return nil end
        return math.floor(v / step + 0.5) * step
    end

    -- GetTop/GetLeft/GetCenter answer in the frame's OWN scale space (the Minimap
    -- sits in a container scaled by Edit Mode's Size setting, the cluster does not),
    -- so every reading is converted to UIParent units before two of them are compared.
    local function EffScale(frame)
        if not (frame and frame.GetEffectiveScale) then return 1 end
        local ok, s = pcall(frame.GetEffectiveScale, frame)
        s = ok and Num(s)
        if s and s > 0 then return s end
        return 1
    end

    local function ToUI(v, frame)
        v = Num(v)
        if not v then return nil end
        return v * EffScale(frame) / EffScale(UIParent)
    end

    -- Where the visible MAP should sit for FS.Layout.minimap: its top and left as
    -- offsets from the layout's relPoint on UIParent (UIParent units), plus the layout
    -- entry and scale.
    local function WantedMapEdges()
        local L = FS.Layout and FS.Layout.minimap
        if not (L and L.w and L.h and L.x and L.y) then return end
        local scale = (FS.Layout.Scale and FS.Layout.Scale()) or 1
        local f = FRAC[L.point] or FRAC.CENTER
        return L, scale,
            L.y * scale + (1 - f[2]) * L.h * scale,   -- map top, above the relPoint
            L.x * scale - f[1] * L.w * scale          -- map left, right of the relPoint
    end

    -- Same rule as Layout.lua's IsHeldInCombat: a protected frame refuses SetPoint
    -- in combat. MinimapCluster normally is not protected, so this is a guard only.
    local function HeldInCombat(frame)
        if not (InCombatLockdown and InCombatLockdown()) then return false end
        if not frame.IsProtected then return false end
        local ok, protected = pcall(frame.IsProtected, frame)
        return not ok or protected and true or false
    end

    -- The cluster edge the map hangs from: "BOTTOM" when MinimapContainer is anchored
    -- by its BOTTOM to the cluster (Header Underneath), else "TOP".
    local function HangEdge(cluster)
        local container = cluster.MinimapContainer
        if container and container.GetPoint then
            local ok, point, rel = pcall(container.GetPoint, container, 1)
            if ok and rel == cluster and point == "BOTTOM" then return "BOTTOM" end
        end
        return "TOP"
    end

    ---------------------------------------------------------------------------
    -- Seat log (ForeverSTUwaveDB.minimapSeatLog, shown by /fsbug as minimapSeat)
    ---------------------------------------------------------------------------
    -- Whether the minimap lands where the layout asks depends on the order of
    -- Blizzard's Edit Mode steps on a character's first login, which the UI source
    -- does not settle. 20 entries, the first 10 pinned (the login sequence), the
    -- previous session kept as minimapSeatLogPrev, and the FIRST session ever logged
    -- (no log existed: a new install of this build) kept as minimapSeatLogFirst so two
    -- reloads cannot erase a first login. Plain numbers and strings only, all under
    -- pcall: logging can never break a seat.
    local SEAT_LOG_MAX = 20
    local SEAT_LOG_PIN = 10
    local rotated = false

    -- Starts this session's log. Done on the FIRST entry, not at install, so the
    -- rescale pass of PLAYER_LOGIN (which runs before the seat is installed) lands in
    -- this session's log and not in the previous one's.
    local function SessionLog(db)
        if not rotated then
            rotated = true
            if db.minimapSeatLogFirst == nil and db.minimapSeatLog == nil then
                local fresh = {}
                db.minimapSeatLogFirst = fresh   -- the live table: it stays as it ends this session
                db.minimapSeatLog = fresh
            else
                db.minimapSeatLogPrev = db.minimapSeatLog
                db.minimapSeatLog = {}
            end
        end
        local log = db.minimapSeatLog
        if type(log) ~= "table" then
            log = {}
            db.minimapSeatLog = log
        end
        return log
    end

    local function LogSeat(ev, hooks)
        pcall(function()
            local db = ForeverSTUwaveDB
            if type(db) ~= "table" then return end
            local log = SessionLog(db)

            local entry = { ev = ev, hk = hooks }
            if type(GetTime) == "function" then entry.t = Round(Num(GetTime()), 0.01) end

            local cluster = MinimapCluster
            if cluster and cluster.GetPoint then
                local ok, point, _, _, x, y = pcall(cluster.GetPoint, cluster, 1)
                if ok then
                    if type(point) == "string" and not (FS.IsSecret and FS.IsSecret(point)) then
                        entry.pt = point
                    end
                    entry.x, entry.y = Round(Num(x), 0.1), Round(Num(y), 0.1)
                end
            end
            if cluster and cluster.IsClampedToScreen then
                local ok, clamped = pcall(cluster.IsClampedToScreen, cluster)
                if ok and type(clamped) == "boolean" then entry.clamp = clamped end
            end
            if Minimap and Minimap.GetTop and Minimap.GetLeft then
                local okT, top = pcall(Minimap.GetTop, Minimap)
                local okL, left = pcall(Minimap.GetLeft, Minimap)
                if okT then entry.mt = Round(ToUI(top, Minimap), 0.1) end
                if okL then entry.ml = Round(ToUI(left, Minimap), 0.1) end
            end
            local L, scale, topOff, leftOff = WantedMapEdges()
            if L then
                entry.sc = Round(scale, 0.001)
                local rf = FRAC[L.relPoint] or FRAC.CENTER
                local okH, h = pcall(UIParent.GetHeight, UIParent)
                local okW, w = pcall(UIParent.GetWidth, UIParent)
                h, w = okH and Num(h), okW and Num(w)
                if h then entry.tt = Round(rf[2] * h + topOff, 0.1) end
                if w then entry.tl = Round(rf[1] * w + leftOff, 0.1) end
                if h then entry.ui = Round(h, 0.1) end
            end

            -- The same state repeated counts up instead of taking a slot.
            local last = log[#log]
            if last and last.ev == ev and last.hk == entry.hk and last.pt == entry.pt
                and last.x == entry.x and last.y == entry.y and last.mt == entry.mt
                and last.ml == entry.ml and last.tt == entry.tt and last.tl == entry.tl
                and last.clamp == entry.clamp then
                last.n = (last.n or 1) + 1
                return
            end
            log[#log + 1] = entry
            while #log > SEAT_LOG_MAX do table.remove(log, SEAT_LOG_PIN + 1) end
        end)
    end

    ---------------------------------------------------------------------------
    -- Compensation
    ---------------------------------------------------------------------------
    -- The last measured inset (see CompensateClusterInset): where the map hangs from
    -- and its offsets, in UIParent units. Session-only; nil until the first measurement.
    local inset

    -- The anchor that puts the map's top and left on the layout seat, from the last
    -- measured inset: edge, relPoint, x, y (cluster-space offsets), or nil with none.
    -- The offsets are the wanted map edges, which follow the CURRENT scale, plus the
    -- inset; SetPoint offsets are in the cluster's own scale space.
    local function CompensatedAnchor()
        local cluster = MinimapCluster
        if not (inset and cluster) then return end
        local L, _, topOff, leftOff = WantedMapEdges()
        if not L then return end
        local k = EffScale(cluster) / EffScale(UIParent)
        local x = leftOff - inset.dl
        local y = (inset.edge == "TOP" and topOff or (topOff - inset.mh)) + inset.d
        return inset.edge, L.relPoint or "CENTER", x / k, y / k
    end

    function CompensateClusterInset()
        compensatePending = false
        local cluster = MinimapCluster
        if not (cluster and Minimap and cluster ~= Minimap) then return end
        if not (cluster.GetTop and cluster.GetBottom and cluster.GetCenter
            and Minimap.GetTop and Minimap.GetBottom and Minimap.GetLeft) then return end
        if HeldInCombat(cluster) then
            compensateHeld = true   -- PLAYER_REGEN_ENABLED finishes it
            return
        end
        if cluster.SetClampedToScreen then
            cluster:SetClampedToScreen(false)
        end

        local edge = HangEdge(cluster)
        local clusterEdge = ToUI(edge == "TOP" and cluster:GetTop() or cluster:GetBottom(), cluster)
        local mapTop, mapBottom = ToUI(Minimap:GetTop(), Minimap), ToUI(Minimap:GetBottom(), Minimap)
        local clusterMid = ToUI((cluster:GetCenter()), cluster)
        local mapLeft = ToUI(Minimap:GetLeft(), Minimap)
        if not (clusterEdge and mapTop and mapBottom and clusterMid and mapLeft) then return end

        -- All in UIParent units: the map's offset from the edge it hangs from, from
        -- the cluster's centre column, and its own height (it scales with Edit Mode's
        -- Size). Kept as the last known inset so FS.Layout.Apply can write the
        -- compensated anchor itself (the SeatAdjust registration below).
        inset = { edge = edge, d = clusterEdge - (edge == "TOP" and mapTop or mapBottom),
                  dl = mapLeft - clusterMid, mh = mapTop - mapBottom }
        local _, relPoint, x, y = CompensatedAnchor()
        if not relPoint then return end

        -- Already there (the inset did not change): no write, so a repeat pass
        -- is a no-op and nothing fights the layout watcher.
        if cluster.GetPoint then
            local ok, point, rel, rp, cx, cy = pcall(cluster.GetPoint, cluster, 1)
            if ok and point == edge and rel == UIParent and rp == relPoint
                and Num(cx) and Num(cy) and math.abs(cx - x) < 0.01 and math.abs(cy - y) < 0.01 then
                return
            end
        end

        -- MinimapCluster is an Edit Mode system frame: its ClearAllPoints/SetPoint
        -- are overrides that write an Edit Mode flag under our taint (see
        -- FS.Layout.Apply). Use the stored originals when present.
        local clear = cluster.ClearAllPointsBase or cluster.ClearAllPoints
        local set = cluster.SetPointBase or cluster.SetPoint
        clear(cluster)
        set(cluster, edge, UIParent, relPoint, x, y)
        LogSeat("compensate")
    end

    -- A frame's rect is not final in the same frame it was anchored, so the inset
    -- can only be read on the next one. One timer however many callers ask.
    function ScheduleCompensate()
        if compensatePending then return end
        if C_Timer and C_Timer.After then
            compensatePending = true
            C_Timer.After(0, CompensateClusterInset)
        else
            CompensateClusterInset()
        end
    end

    -- Puts the cluster back at the layout seat (raw). The compensation goes on top of
    -- it one frame later, like after a rescale: reading the rects in the frame they
    -- were anchored would measure a map that has not moved yet.
    local function Reseat(why)
        reseatPending = false
        local cluster = MinimapCluster
        if not (cluster and Minimap and cluster ~= Minimap) then return end
        if not (FS.Layout and FS.Layout.Apply) then return end
        if HeldInCombat(cluster) then
            reseatPending = true   -- PLAYER_REGEN_ENABLED finishes it
            return
        end
        local ok, err = pcall(function()
            FS.Layout.Apply(cluster, "minimap")
            local mm = FS.Layout.minimap
            if mm and mm.scaledW and mm.scaledH and Minimap.SetSize then
                Minimap:SetSize(mm.scaledW, mm.scaledH)
            end
            LogSeat(why)
        end)
        if not ok and FS.Layout.ForwardError then FS.Layout.ForwardError(err) end
        ScheduleCompensate()
    end

    -- One re-seat a frame from now, however many Blizzard calls ask for it.
    local function DeferReseat(why)
        LogSeat(why)
        if reseatPending then return end
        if not (C_Timer and type(C_Timer.After) == "function") then return end
        reseatPending = true
        C_Timer.After(0, function()
            if reseatPending then Reseat("reseat") end
        end)
    end

    -- FS.Layout.Apply (the PLAYER_LOGIN and rescale watcher, and the Edit Mode re-seat
    -- hook in Layout.lua) writes the cluster's anchor itself; with a measured inset it
    -- writes the compensated one, so the map is never shown at the raw seat for a frame
    -- until our compensation (a frame later) fixes it. The very first seat has no
    -- inset yet and is the raw seat, which the compensation then corrects.
    if FS.Layout then
        FS.Layout.SeatAdjust = FS.Layout.SeatAdjust or {}
        FS.Layout.SeatAdjust.minimap = CompensatedAnchor
    end

    -- FS.Layout's watcher re-Applies every seated frame on PLAYER_LOGIN, UI scale
    -- and resolution changes, which overwrites the corrected anchor with the raw
    -- one. Callbacks run after that pass (also after the Edit Mode re-seat), so
    -- this puts the correction back.
    if FS.Layout and FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            LogSeat("rescale:" .. tostring(FS.Layout.rescaleWhy or "?"))
            ScheduleCompensate()
        end)
    end

    ---------------------------------------------------------------------------
    -- Watching Blizzard move the cluster after us
    ---------------------------------------------------------------------------
    -- Layout.lua re-seats every Edit Mode frame from a post-hook on
    -- EditModeManagerFrame:UpdateLayoutInfo (after every system applied) and runs
    -- the rescale callbacks above. What it does not cover: a Layout pass the cluster
    -- takes later, the container scale (SetEditModeScale) and header
    -- (SetHeaderUnderneath) steps that change the inset, and ApplySystemAnchor
    -- reached without UpdateLayoutInfo (Reset to default position). None of these
    -- seats from inside Blizzard's call (that would land before its settings loop
    -- and put OUR seat into the layout's stored anchor, see ChatWindowState.lua):
    -- every one defers a frame.
    local HOOKS = {
        { key = "S", frame = function() return MinimapCluster end, name = "SetEditModeScale",
          run = function() LogSeat("SetEditModeScale"); ScheduleCompensate() end },
        { key = "H", frame = function() return MinimapCluster end, name = "SetHeaderUnderneath",
          run = function() LogSeat("SetHeaderUnderneath"); ScheduleCompensate() end },
        { key = "A", frame = function() return MinimapCluster end, name = "ApplySystemAnchor",
          run = function() DeferReseat("ApplySystemAnchor") end },
        { key = "U", frame = function() return EditModeManagerFrame end, name = "UpdateLayoutInfo",
          run = function() DeferReseat("UpdateLayoutInfo") end },
    }
    local hooked = {}   -- by key, so a late-defined method is retried on its own

    -- Hooks every method that exists and is not hooked yet; returns the keys of the
    -- ones installed so far, and whether all of them are.
    local function InstallHooks()
        if type(hooksecurefunc) ~= "function" then return "", false end
        local keys, all = {}, true
        for _, h in ipairs(HOOKS) do
            if not hooked[h.key] then
                local frame = h.frame()
                if frame and type(frame[h.name]) == "function" then
                    hooksecurefunc(frame, h.name, function()
                        local ok, err = pcall(h.run)
                        if not ok and FS.Layout and FS.Layout.ForwardError then FS.Layout.ForwardError(err) end
                    end)
                    hooked[h.key] = true
                end
            end
            if hooked[h.key] then keys[#keys + 1] = h.key else all = false end
        end
        return table.concat(keys), all
    end

    function InstallSeatWatch()
        if installed then return end
        installed = true
        local keys, all = InstallHooks()
        LogSeat("seat")
        LogSeat("hooks", keys)   -- which of S H A U (see HOOKS) exist on this client

        local watcher = CreateFrame("Frame")
        watcher:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
        watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
        watcher:RegisterEvent("PLAYER_REGEN_ENABLED")
        if not all then watcher:RegisterEvent("ADDON_LOADED") end
        watcher:SetScript("OnEvent", function(self, event, arg1, arg2)
            if event == "PLAYER_REGEN_ENABLED" then
                if reseatPending then Reseat("regen") end
                if compensateHeld then
                    compensateHeld = false
                    ScheduleCompensate()
                end
            elseif event == "ADDON_LOADED" then
                if arg1 == "Blizzard_EditMode" then
                    local late = InstallHooks()
                    LogSeat("hooks", late)
                    self:UnregisterEvent("ADDON_LOADED")
                end
            elseif event == "PLAYER_ENTERING_WORLD" then
                -- Zone changes fire this too; only a login or reload needs the re-seat.
                if arg1 or arg2 then DeferReseat(event) end
            else
                DeferReseat(event)
            end
        end)
    end
end

-- ROOT CAUSE of the right-edge cutoff: FS.Layout.Apply(target, "minimap")
-- sizes `target` (MinimapCluster) to L.w*scale, L.h*scale and ALSO writes
-- those scaled values onto FS.Layout.minimap as `scaledW`/`scaledH` (see
-- Layout.lua). The bare Minimap widget was then sized to the RAW, UNSCALED
-- mm.w/mm.h (250x252 design px) instead -- at a typical measured scale
-- (~0.833, see Layout.lua's own comment), that left Minimap ~42px WIDER/
-- TALLER than its own MinimapCluster container in each dimension, a ~21px
-- overhang per side. Combined with the map's design position sitting close
-- to the right edge of the design canvas (x=1136, half-width 1280, only
-- ~19 design px / ~16 scaled px of margin), that overhang is exactly what
-- pushed the visible map's right edge off-screen. Fixed by sizing Minimap
-- to mm.scaledW/mm.scaledH (already populated by FS.Layout.Apply above)
-- instead of the raw mm.w/mm.h.
local function ApplyLayout()
    if not Minimap or Minimap.fsPlaced then return end
    if not (FS.Layout and FS.Layout.Apply) then return end

    local target = MinimapCluster or Minimap
    if FS.Layout.Apply(target, "minimap") then
        -- Whether MinimapCluster:SetSize cascades to the child Minimap is
        -- UNVERIFIED on this client, so Minimap is sized explicitly here to
        -- guarantee the chrome (mask/border/glow, all applied to the bare
        -- Minimap widget) matches the reserved footprint either way.
        local mm = FS.Layout.minimap
        if mm and mm.scaledW and mm.scaledH and Minimap.SetSize then
            Minimap:SetSize(mm.scaledW, mm.scaledH)
        end

        if target ~= Minimap then
            ScheduleCompensate()
            InstallSeatWatch()
        end

        -- Minimap's real (scale-correct) size is now known -- re-derive every
        -- size-dependent metric (bezel/key/font/glow/readout sizes) from it,
        -- since DeriveMetrics' file-load-time call above only had the raw,
        -- oversized design values to work with.
        RefreshMetrics()

        Minimap.fsPlaced = true
    end
end

-------------------------------------------------------------------------------
-- Shape
-------------------------------------------------------------------------------

-- Small (cornerRadius:4 at the mockup's base 250px width -> fraction 0.016)
-- rounded-corner mask, replacing the prior hard-square WHITE8X8 mask (which
-- was "verified working in-game" as a hard square, but per Parker's spec the
-- mockup wants a small rounding on the map face itself). SetMaskTexture
-- stretches the mask to whatever Minimap's current size is, so this
-- FRACTIONAL radius stays correct automatically at any UI scale -- no
-- per-scale recompute needed. See generate_mask_minimap.py.
local function ApplySquareMask()
    if Minimap and Minimap.SetMaskTexture then
        Minimap:SetMaskTexture(MASK_MINIMAP_TEXTURE)
    end
end

-- Edge-button libs (LibDBIcon, minimap button addons) query this to lay out
-- around the minimap shape; only define it if nothing else already has.
if type(GetMinimapShape) ~= "function" then
    function GetMinimapShape()
        return "SQUARE"
    end
end

-------------------------------------------------------------------------------
-- Blizzard chrome hide (feature-detected; names unverified -- see report)
-------------------------------------------------------------------------------

-- Hides a global by name only if it currently exists; the frame-name list
-- below is unverified on interface 16001, and each lookup is nil-guarded so
-- a missing name is a silent no-op.
-- Every step pcall'd INDIVIDUALLY. Previously one unguarded Hide() on a
-- protected frame aborted the whole sweep, which is why the sun and the
-- expansion button survived while everything after them in the list did too.
--
-- Alpha and mouse are cleared as well as Hide: some of these are re-Shown by
-- Blizzard's own layout code, and a zero-alpha, mouse-disabled frame is
-- invisible and unclickable even in the instant before the OnShow hook fires.
local function HideIfExists(frame)
    if not frame then return end
    pcall(function() frame:Hide() end)
    pcall(function() frame:SetAlpha(0) end)
    pcall(function() frame:EnableMouse(false) end)
    pcall(function()
        if frame.HookScript and not frame.fsHideHooked then
            frame:HookScript("OnShow", function(self)
                -- A button later reparented into the control bezel (see
                -- StyleBezelKey) marks itself fsBezelOwned; skip the re-hide
                -- there so the bezel's own Show()/SetAlpha(1)/EnableMouse(true)
                -- sticks instead of being undone the next time this same
                -- button (now a bezel key) fires OnShow.
                if self.fsBezelOwned then return end
                self:Hide()
                self:SetAlpha(0)
            end)
            frame.fsHideHooked = true
        end
    end)
end

-- Parker, 2026-09-2X: "weird circles" on the minimap, and separately "looks
-- bad and is cut off on the right side" (the cutoff half is Layout.lua's
-- problem -- see the minimap/minimaptray x-shift comment there -- this is
-- only the circles half). HideBlizzardChrome above only hides a fixed list
-- of GUESSED global/parentKey names, several already marked unconfirmed in
-- its own comments right there. A wrong guess is a silent no-op: nothing
-- errors, the art just stays visible, which is exactly how a mockup with
-- almost no circular elements at all (only a tiny player-blip dot and a tiny
-- mail-notification dot, both ~50% border-radius in the mockup's own CSS,
-- everything else a barely-rounded square) can still show rings in-game --
-- whatever native minimap ring/border/compass art this client actually uses
-- was simply never on the guessed list.
--
-- Rather than guess more names, this sweeps GENERICALLY by what a region
-- CLAIMS to be rather than what it is called: every Texture region sitting
-- directly on Minimap, and on MinimapCluster if it exists, whose ATLAS name
-- contains one of a handful of chrome-signaling substrings gets hidden,
-- regardless of whether it is exposed under any global/parentKey name at
-- all. This is ADDITIVE to the named-lookup hides above, never a
-- replacement for them -- some chrome may carry no atlas at all (a bare
-- fileID texture), and this sweep cannot safely tell that apart from real
-- content, so it deliberately leaves atlas-less regions alone rather than
-- guess by size or position, which would be a much bigger and riskier
-- change than this fix calls for. Known limitation, not a bug: any stray
-- chrome that turns out to be a bare fileID texture will survive this pass.
--
-- Safe by construction: it only strips a region whose atlas name EXPLICITLY
-- signals decorative minimap chrome, so it can never touch the live map's
-- own rendered imagery (not exposed as a matching-atlas Texture region), and
-- it is called from the end of HideBlizzardChrome below -- before any of
-- this file's own chrome-adding functions (ApplyChrome/ApplyHighlight/
-- ApplyPlayerBlipGlow/ApplyScanline, see the Apply() call order near the
-- bottom of this file) have created anything, so there is nothing of ours
-- yet to accidentally self-hide, and no exclude-list is needed for that.
--
-- Every step pcall'd INDIVIDUALLY, exactly like HideIfExists above, so one
-- region that throws on a method call can't abort the rest of the sweep.
-- Shared by StripStrayMinimapArt below for both the direct-region sweep and
-- the one-level-deep child-frame sweep: hides any Texture region in the
-- given list whose atlas name contains one of the chrome-signaling
-- substrings. Every step pcall'd individually, exactly like the rest of
-- this file's Blizzard-chrome handling, so one region that throws on a
-- method call can't abort the rest of the sweep.
local function StripChromeRegions(regions)
    for _, region in ipairs(regions) do
        local isTexture = false
        pcall(function() isTexture = (region:GetObjectType() == "Texture") end)

        if isTexture then
            local atlas
            pcall(function() atlas = region:GetAtlas() end)

            if atlas then
                atlas = string.lower(atlas)
                -- "tracking" is a known, accepted tradeoff: kept because the task's own
                -- diagnosis specifically named a leftover tracking-button ring as a likely
                -- cause of the "weird circles" report, and no repo evidence currently
                -- confirms or denies whether a real minimap pin's atlas name could ever
                -- collide with that substring on this client. If a real tracking pin ever
                -- goes missing in-game, check here first.
                local isChrome = false
                for _, needle in ipairs({ "minimap", "compass", "ring", "border", "tracking" }) do
                    if string.find(atlas, needle, 1, true) then
                        isChrome = true
                        break
                    end
                end

                if isChrome then
                    pcall(function() region:SetAlpha(0) end)
                    pcall(function() region:SetTexture(nil) end)
                end
            end
        end
    end
end

local function StripStrayMinimapArt()
    if not (Minimap and Minimap.GetRegions) then return end

    local okMinimapRegions, minimapRegions = pcall(function() return { Minimap:GetRegions() } end)
    local regions = okMinimapRegions and minimapRegions or {}

    if MinimapCluster and MinimapCluster.GetRegions then
        local okClusterRegions, clusterRegions = pcall(function() return { MinimapCluster:GetRegions() } end)
        if okClusterRegions then
            for _, region in ipairs(clusterRegions) do
                regions[#regions + 1] = region
            end
        end
    end

    StripChromeRegions(regions)

    -- ADDITIVE, self-healing: Blizzard's corner/border decoration on this
    -- client lives on a NESTED child FRAME of MinimapCluster (this file's
    -- own HideBlizzardChrome already reaches for MinimapCluster.BorderTop
    -- as exactly such a separate frame), not as a direct Texture region of
    -- Minimap/MinimapCluster themselves. GetRegions() only ever returns
    -- DIRECT Texture/FontString children -- it never descends into child
    -- frames -- so the sweep above alone can never see it. This walks one
    -- level of MinimapCluster's own child FRAMES and sweeps each one's own
    -- GetRegions() through the SAME StripChromeRegions/needle list. One
    -- level of descent only (no deep recursion): every known case of this
    -- stray art sits directly on a first-level child. This can never hide a
    -- reparented minimap-button key (see StyleBezelKey) outright -- only a
    -- Texture REGION belonging to a child is ever touched, never the child
    -- frame itself, so a Button-type child (and its Show/Hide state) is
    -- left alone regardless.
    if MinimapCluster and MinimapCluster.GetChildren then
        local okChildren, children = pcall(function() return { MinimapCluster:GetChildren() } end)
        if okChildren then
            for _, child in ipairs(children) do
                local objType
                pcall(function() objType = child and child.GetObjectType and child:GetObjectType() end)

                -- Skip Button/CheckButton children outright: these are candidate
                -- minimap-button keys StyleBezelKey may reparent into the control
                -- bezel later in Apply() (ApplyControlBezel runs AFTER this
                -- sweep) -- MinimapCluster.Tracking is the concrete case. Their
                -- own icon Texture region could otherwise collide with the
                -- "tracking" needle above (a real, named tracking-button icon,
                -- not a hypothetical stray pin) and get blanked via SetTexture(nil)
                -- before the button ever reaches the bezel, defeating the whole
                -- point of making that key visible and usable.
                if child and child.GetRegions and objType ~= "Button" and objType ~= "CheckButton" then
                    local okChildRegions, childRegions = pcall(function() return { child:GetRegions() } end)
                    if okChildRegions then
                        StripChromeRegions(childRegions)
                    end
                end
            end
        end
    end
end

local function HideBlizzardChrome()
    -- Modern-engine candidates (unconfirmed).
    if MinimapCluster and MinimapCluster.BorderTop then
        HideIfExists(MinimapCluster.BorderTop)
    end
    HideIfExists(MinimapBackdrop)
    HideIfExists(MinimapBorder)
    HideIfExists(MinimapCompassTexture)
    -- Keep ZoneTextButton interactive while the map-owned zone label displays its text.
    HideIfExists(MinimapZoneText)

    -- Legacy-client candidates (unconfirmed).
    HideIfExists(MinimapBorderTop)

    -- This client is mouse-wheel zoom only (see OnMouseWheel/ApplyZoom below)
    -- and the mockup's control bezel has no zoom +/- buttons, so Blizzard's
    -- native zoom buttons are hidden outright rather than reparented into the
    -- bezel (contrast tracking/calendar/mail below, which ARE reparented and
    -- marked fsBezelOwned so HideIfExists' own OnShow re-hide hook skips
    -- them). Since these two are never marked fsBezelOwned, they must be
    -- hidden here, before ApplyControlBezel runs.
    HideIfExists(Minimap.ZoomIn)
    HideIfExists(Minimap.ZoomOut)

    -- Blizzard's own coords + clock, which our bezel LCD already renders (see
    -- ApplyReadout: cyan coords left, amber clock right). Leaving these up
    -- shows each value twice.
    --
    -- Both paths are MEASURED, not guessed. PlayerCoords is a parentKey frame
    -- on MinimapCluster.MinimapContainer per Blizzard_Minimap/Mainline/
    -- Minimap.xml on the `forever` branch (MinimapContainer at line 186,
    -- PlayerCoords at 425); MinimapContainer is confirmed present in the
    -- 2026-09-19 recon dump. TimeManagerClockButton is confirmed in the 16001
    -- globals dump.
    --
    -- Hiding the frame rather than clearing the CVar (minimapShowPlayerCoords)
    -- keeps this contained to our addon: a CVar write would silently change a
    -- saved account setting that outlives the addon being disabled. Hiding also
    -- stops MinimapPlayerCoordsMixin:OnUpdate, since hidden frames do not tick.
    local container = MinimapCluster and MinimapCluster.MinimapContainer
    if container and container.PlayerCoords then
        HideIfExists(container.PlayerCoords)
    end
    HideIfExists(TimeManagerClockButton)

    -- The "sun" above the map is GameTimeFrame (the calendar button); it and
    -- the expansion/addon-compartment buttons sit ABOVE MinimapCluster and push
    -- the whole cluster down. All four names confirmed in the 16001 globals
    -- dump. Our bezel already provides tracking/calendar/mail; zoom buttons
    -- are hidden outright above, not provided via the bezel. None of these
    -- three need to stay.
    for _, name in ipairs({
        "GameTimeFrame",
        "ExpansionLandingPageMinimapButton",
        "AddonCompartmentFrame",
    }) do
            HideIfExists(_G[name])
    end

    -- The sun above the map is MinimapCluster.DielFrame -- the day/night cycle
    -- indicator. It is a parentKey, NOT a global, which is why hiding
    -- GameTimeFrame by name did nothing. Identified by enumerating
    -- MinimapCluster's children: every one is anonymous, and the 41x42 entry
    -- matches .DielFrame in the 2026-09-19 recon dump.
    --
    -- Keep .Tracking, .InstanceDifficulty, and .ZoneTextButton available;
    -- only the native zone FontString is hidden above.
    if MinimapCluster then
        HideIfExists(MinimapCluster.DielFrame)
    end

    -- Generic atlas-substring sweep, additive to every named lookup above.
    -- See StripStrayMinimapArt's own comment for the full "weird circles"
    -- rationale. Must run from here (not later in Apply()) so it fires
    -- before ApplyChrome/ApplyHighlight/ApplyPlayerBlipGlow/ApplyScanline
    -- have created any of our own textures.
    StripStrayMinimapArt()
end

-------------------------------------------------------------------------------
-- Custom neon border + glow
-------------------------------------------------------------------------------

-- Under "cut" the mask is chamfered TOP-LEFT and BOTTOM-RIGHT (6/250), so the border
-- and glow take MAP_CHAMFER and follow it; under "round" (the old A/B path) the mask
-- corners are tiny and the chrome stays the well-tested radius-0 square.
local function MapChromeRadius()
    return (FS.Theme.CHROME_CORNERS == "cut") and MAP_CHAMFER or SQUARE_RADIUS
end

local function ApplyChrome()
    if not Minimap or Minimap.fsChrome then return end
    if not (AddOuterGlow and AddGradientBorder) then return end

    -- Mockup wants a CYAN outer glow (COLOR_POWER), not the border's
    -- violet-blend -- previously this used COLOR_BORDER (pure violet) for
    -- both. GLOW_SIZE is now a fraction of the map (Metrics.glowSize), so it
    -- scales with the real, scale-corrected map size instead of a hardcoded 8px.
    AddOuterGlow(Minimap, COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], GLOW_SIZE, GLOW_ALPHA, MapChromeRadius())
    -- Border: cyan/violet color-mix blend (COLOR_BORDER_BLEND), replacing the
    -- previous plain COLOR_BORDER (pure violet).
    AddGradientBorder(Minimap, COLOR_BORDER_BLEND, BORDER_THICK, MapChromeRadius())
    Minimap.fsChrome = true
end

-------------------------------------------------------------------------------
-- Soft top-left highlight
-------------------------------------------------------------------------------

-- Mockup: radial-gradient(ellipse at 30% 15%, rgba(215,240,255,.11), transparent 45%)
-- -- a soft pale glow biased toward the map's top-left quadrant. Reuses the
-- existing glow_round.tga (128x128, full alpha at center, radial falloff to 0
-- at the unit circle -- see generate_glow_round.py) rather than a new
-- texture; sized to a fraction of the map and anchored off-center via offset
-- points rather than SetAllPoints. ARTWORK layer, same tier as the scanline
-- overlay below, under the OVERLAY zone text/north tick.
local function ApplyHighlight()
    if not Minimap or Minimap.fsHighlight then return end
    if not Minimap.CreateTexture then return end

    local m = (Minimap.GetWidth and Minimap:GetWidth()) or Metrics.map
    local size = m * HIGHLIGHT_SIZE_FRACTION

    local glow = Minimap:CreateTexture(nil, "ARTWORK")
    glow:SetTexture(GLOW_ROUND_TEXTURE)
    glow:SetBlendMode("ADD")
    glow:SetVertexColor(HIGHLIGHT_COLOR[1], HIGHLIGHT_COLOR[2], HIGHLIGHT_COLOR[3], HIGHLIGHT_ALPHA)
    glow:SetSize(size, size)
    -- Biased toward the top-left quadrant (mockup's 30% 15% ellipse center),
    -- not dead-center: offset the glow's own center up-left of Minimap's
    -- own center.
    glow:SetPoint("CENTER", Minimap, "CENTER", -m * 0.20, m * 0.35)

    Minimap.fsHighlight = glow
end

-------------------------------------------------------------------------------
-- Player blip glow
-------------------------------------------------------------------------------

-- The player is always exactly at Minimap's center (this is a player-
-- centered minimap), so this is a static centered texture, never
-- repositioned or tracked. Blizzard's own native player arrow already
-- renders at center and rotates with facing -- deliberately NOT replaced
-- (risk of breaking facing/rotation and touching Blizzard's internal texture
-- management); this only ADDS a magenta glow HALO behind it.
--
-- UNVERIFIED in-game which draw layer/sublevel the native arrow actually
-- renders on -- kept on a low ARTWORK sublevel so it reads as a glow under/
-- around the arrow rather than covering it, per this file's established
-- honesty convention for unvalidated Blizzard-internals guesses.
local function ApplyPlayerBlipGlow()
    if not Minimap or Minimap.fsBlipGlow then return end
    if not Minimap.CreateTexture then return end

    local size = Metrics.blip * BLIP_GLOW_SIZE_MULT

    local glow = Minimap:CreateTexture(nil, "ARTWORK", nil, -1)
    glow:SetTexture(GLOW_ROUND_TEXTURE)
    glow:SetBlendMode("ADD")
    glow:SetVertexColor(COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], BLIP_GLOW_ALPHA)
    glow:SetSize(size, size)
    glow:SetPoint("CENTER", Minimap, "CENTER")

    Minimap.fsBlipGlow = glow
end

-------------------------------------------------------------------------------
-- Scanline overlay
-------------------------------------------------------------------------------

-- ARTWORK draw layer sits above the map's own base render but below the
-- OVERLAY zone text/north tick added elsewhere in this file, so the scrim
-- reads over the map face without dimming either label. Purely decorative
-- (a Texture never intercepts mouse input), so blips/readout/keys stay
-- interactive underneath it.
--
-- Single tiled layer: the dark horizontal scanline (SCANLINE_TEXTURE, a 4x4
-- texture whose alpha varies only by row -- row 0 dark, rows 1-3 transparent,
-- uniform across every column) tiled via SetHorizTile/SetVertTile, the same
-- idiom Theme.lua's own panel-scanline pass uses, rather than a manual
-- SetTexCoord repeat-count computation. A prior second layer (a vertical RGB
-- subpixel-stripe texture, approximating the mockup's .mmscan gradient) was
-- removed: combined with this horizontal layer it read as a grid/banding
-- rather than the mockup's subtle horizontal-only lines.
local function ApplyScanline()
    if not Minimap or Minimap.fsScanline then return end
    if not Minimap.CreateTexture then return end

    local function TileTexture(path, alpha)
        local tex = Minimap:CreateTexture(nil, "ARTWORK")
        tex:SetTexture(path, "REPEAT", "REPEAT")
        tex:SetAllPoints(Minimap)
        tex:SetHorizTile(true)
        tex:SetVertTile(true)
        tex:SetAlpha(alpha)
        return tex
    end

    Minimap.fsScanline = TileTexture(SCANLINE_TEXTURE, SCANLINE_ALPHA)
end

-------------------------------------------------------------------------------
-- Mouse-wheel zoom
-------------------------------------------------------------------------------

local function ClampZoom(value, minValue, maxValue)
    if value < minValue then return minValue end
    if value > maxValue then return maxValue end
    return value
end

local function OnMouseWheel(self, delta)
    if not (self.GetZoom and self.SetZoom) then return end

    local maxZoom = 0
    if self.GetZoomLevels then
        maxZoom = math.max(0, (self:GetZoomLevels() or 1) - 1)
    end

    local zoom = ClampZoom(self:GetZoom() + delta, 0, maxZoom)
    self:SetZoom(zoom)
end

local function ApplyZoom()
    if not Minimap or Minimap.fsZoomEnabled then return end
    if not Minimap.EnableMouseWheel then return end

    Minimap:EnableMouseWheel(true)
    Minimap:SetScript("OnMouseWheel", OnMouseWheel)
    Minimap.fsZoomEnabled = true
end

-------------------------------------------------------------------------------
-- Zone text
-------------------------------------------------------------------------------

-- Blizzard's MinimapZoneText is parented to the cluster's narrow header button.
-- Moving that FontString onto the map does not make it reliably visible, so
-- display the same zone name in a map-owned label below our north tick.
local function ApplyZoneText()
    if not Minimap or Minimap.fsZoneLabel or not ApplyFontGeneric then return end

    local zone = Minimap:CreateFontString(nil, "OVERLAY")
    zone:SetPoint("TOP", Minimap, "TOP", 0, -(NORTH_INSET_Y + NORTH_FONT_SIZE + 2))
    zone:SetWidth(math.max(1, Minimap:GetWidth() - 18))
    zone:SetJustifyH("CENTER")
    ApplyFontGeneric(zone, FONT_ORBITRON, math.min(ZONE_FONT_SIZE, 13), COLOR_TEXT_WHITE, "")
    zone:SetShadowColor(0, 0, 0, 1)
    zone:SetShadowOffset(1, -1)

    local function UpdateZone()
        if type(GetMinimapZoneText) ~= "function" then return end
        local ok, name = pcall(GetMinimapZoneText)
        if ok then pcall(zone.SetText, zone, name) end
    end

    local events = CreateFrame("Frame")
    events:RegisterEvent("ZONE_CHANGED")
    events:RegisterEvent("ZONE_CHANGED_INDOORS")
    events:RegisterEvent("ZONE_CHANGED_NEW_AREA")
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    events:SetScript("OnEvent", UpdateZone)
    Minimap.fsZoneLabel = zone
    Minimap.fsZoneEvents = events
    UpdateZone()
end

-------------------------------------------------------------------------------
-- North tick
-------------------------------------------------------------------------------

-- New fontstring child of Minimap (no Blizzard equivalent to restyle);
-- top-center, small cyan glow to match the zone text's halo treatment.
local function ApplyNorthTick()
    if not Minimap or Minimap.fsNorthTick then return end
    if not ApplyFontGeneric then return end

    local north = Minimap:CreateFontString(nil, "OVERLAY")
    north:SetPoint("TOP", Minimap, "TOP", 0, -NORTH_INSET_Y)
    ApplyFontGeneric(north, FONT_ORBITRON, NORTH_FONT_SIZE, COLOR_POWER, "")
    north:SetShadowColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
    north:SetShadowOffset(0, 0)
    north:SetText("N")

    Minimap.fsNorthTick = north
end

-------------------------------------------------------------------------------
-- Control bezel (reparented minimap-button keys)
-------------------------------------------------------------------------------

-- Strips leftover stock Blizzard button background/border art from a
-- reparented bezel key -- the same "blank named plate-art regions, keep the
-- icon" idiom MicroBars.lua's StripButtonArt uses for micro buttons (not
-- exported from that file, so this is a bounded, minimap-scoped copy rather
-- than a shared dependency). Deliberately does NOT touch NormalTexture: that
-- region carries the key's own icon glyph (e.g. the tracking icon, the
-- calendar sun, the mail envelope), not backdrop plate, so blanking it
-- unconditionally would erase the button's only visible icon. Feature-
-- detected/nil-guarded throughout: whether Tracking/GameTimeFrame/the mail
-- frame still carry named Border/Background regions on this client is
-- UNVERIFIED -- a miss here just leaves old art visible under our new fill,
-- not an error. Only ever called on these three bezel-reparented keys (see
-- StyleBezelKey's callers below); zoom buttons never reach this function,
-- since they are hidden outright rather than reparented into the bezel (see
-- HideBlizzardChrome).
local function StripKeyArt(button)
    if not button then return end
    for _, key in ipairs({ "Border", "Background" }) do
        local region = button[key]
        if region and region.SetAlpha then region:SetAlpha(0) end
    end
end

-- Chamfer shared by a button's fill and its SkinButton ring (a bezel key at KEY_SIZE, or
-- the tray's tab and tiles at their own edge), or nil when the cut chrome is off (or Theme
-- lacks the helpers) and the old rounded fill applies.
local function KeyChamfer(size)
    local Theme = FS.Theme
    if Theme.CHROME_CORNERS ~= "cut" then return nil end
    if not (Theme.Cut2ButtonSet and Theme.CutSizeIcon and Theme.AddSliceTexture and Theme.ApplyNineSlice) then
        return nil
    end
    local _, _, c = Theme.Cut2ButtonSet(Theme.CutSizeIcon(size or KEY_SIZE) or 6)
    return c
end

-- Plain white two-corner fill piece at chamfer c (c = 6 is the original file name).
local function CutFillTexture(c)
    if c == 6 then return FS.Theme.SLICE_CUT2_FILL_TEXTURE end
    return "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_fill_c" .. c .. ".tga"
end

-- Underline glow bar (.mmbtn::after / .tbtn::after): a short (~60% width, centered,
-- 20%-80% inset), thin (~2px scaled) bar near the button's bottom edge (13% up from the
-- bottom edge), colored the button's own accent, with a soft glow. Reuses
-- GLOW_EDGE_TEXTURE, the same ADD-blend strip-glow texture AddOuterGlow/AddHoverGlow
-- already use elsewhere in this addon; its baked fade direction is tuned for an OUTWARD
-- edge glow rather than a centered bar, so the exact fade look here is approximate/untuned
-- -- a minor visual nuance, not re-derived for this narrower use. `w`/`h` are the button's
-- own edges (bezel keys pass KEY_SIZE twice; the tray's tab and tiles pass theirs).
local function AddKeyUnderline(button, w, h, accentColor)
    if not GLOW_EDGE_TEXTURE then return nil end
    local underline = button:CreateTexture(nil, "OVERLAY", nil, 3)
    underline:SetTexture(GLOW_EDGE_TEXTURE)
    underline:SetBlendMode("ADD")
    underline:SetVertexColor(accentColor[1], accentColor[2], accentColor[3], 0.9)
    underline:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT",
        w * KEY_UNDERLINE_INSET_FRACTION, h * KEY_UNDERLINE_BOTTOM_FRACTION)
    underline:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT",
        -w * KEY_UNDERLINE_INSET_FRACTION, h * KEY_UNDERLINE_BOTTOM_FRACTION)
    underline:SetHeight(KEY_UNDERLINE_HEIGHT)
    return underline
end

-- Reparents a non-secure Blizzard button into the bezel's left key row as a
-- flat rounded-square neon key. Sized uniformly to the bezel's usable height
-- regardless of the source button's own size; anchored after `anchorTo` when
-- given, else flush to the bezel's left padding, so a skipped earlier key
-- leaves no gap in the row.
local function StyleBezelKey(bezel, button, accentColor, anchorTo)
    if not button then return nil end

    -- Mark this button as bezel-owned before anything below runs: if
    -- HideBlizzardChrome's HideIfExists already hid this button and
    -- installed its permanent OnShow re-hide hook (see that function),
    -- this flag makes that hook skip re-hiding it once Show() below fires
    -- OnShow again.
    button.fsBezelOwned = true

    button:SetParent(bezel)
    -- Above the readout box (a later sibling, which would otherwise paint over a key).
    if button.SetFrameLevel and bezel.GetFrameLevel then
        button:SetFrameLevel(bezel:GetFrameLevel() + KEY_LEVEL_OFFSET)
    end
    button:SetSize(KEY_SIZE, KEY_SIZE)
    button:ClearAllPoints()
    if anchorTo then
        button:SetPoint("LEFT", anchorTo, "RIGHT", KEY_GAP, 0)
    else
        button:SetPoint("LEFT", bezel, "LEFT", BEZEL_PADDING, 0)
    end

    -- HideBlizzardChrome may have already hidden this button (alpha 0,
    -- mouse disabled) before it was reparented here; explicitly restore
    -- it now that it belongs to the bezel instead of relying on a bare
    -- Show(), since the button was left alpha-0/mouse-disabled by
    -- HideIfExists above and SetParent alone does not undo that.
    button:Show()
    button:SetAlpha(1)
    if button.EnableMouse then button:EnableMouse(true) end

    StripKeyArt(button)

    -- Dark fill behind the key, UNDER the border/glow SkinButton adds below
    -- (mockup: linear-gradient(180deg,#0e0822,#050311); AddRoundedFill only
    -- takes a flat color, so READOUT_FILL -- the bezel's own existing
    -- near-black "console housing" color -- approximates it rather than
    -- introducing a near-duplicate new token).
    -- Keys are buttons: under "cut" the fill is the two-corner cut2 fill (TOP-LEFT and
    -- BOTTOM-RIGHT) at the SAME chamfer SkinButton's ring takes (CutSizeIcon of the key
    -- edge), nine-sliced with margin c and tinted READOUT_FILL, so it never pokes past the
    -- ring. "round" keeps the old rounded fill.
    local keyChamfer = KeyChamfer()
    if keyChamfer then
        local texture = FS.Theme.AddSliceTexture(
            button, CutFillTexture(keyChamfer), READOUT_FILL, "BACKGROUND", 0)
        FS.Theme.ApplyNineSlice(texture, keyChamfer)
    elseif AddRoundedFill then
        AddRoundedFill(button, READOUT_FILL, Metrics.keyRadius)
    end

    if SkinButton then
        -- .mmbtn border-radius is 24% of the key in the mockup (rad =
        -- btn*0.24 in the renderer, bumped from 0.22 -- see DeriveMetrics),
        -- not the shared button default, so the keys read as rounded squares
        -- rather than near-circles at this size.
        SkinButton(button, {
            borderColor = accentColor,
            radius = Metrics.keyRadius,
            chamfer = keyChamfer,
        })
    end

    AddKeyUnderline(button, KEY_SIZE, KEY_SIZE, accentColor)

    return button
end

-- The mockup's pink notification dot is a SEPARATE round texture (glow_round.tga, the same
-- radial falloff the player-blip glow uses) at the key's top-right corner, plus a wider halo
-- behind it for the glow. Both are textures OWNED by MailFrame, so they show and hide with the
-- FRAME, with no hook or event of ours. That is not the same as showing with the envelope: in
-- Blizzard 12.1 the envelope is shown only when the arrival animation finishes (see
-- StyleMailKey), so for about 0.4 to 0.5 s after mail arrives the dot shows alone. They are drawn
-- on OVERLAY (the dot a sublevel above its halo) so they sit over the envelope; the handles live
-- in the module-local mailDot, not on the Blizzard frame.
local function AddMailDot(frame)
    if mailDot.core or not frame.CreateTexture then return end
    local size = math.max(3, KEY_SIZE * KEY_DOT_SIZE_FRACTION)

    local core = frame:CreateTexture(nil, "OVERLAY", nil, 7)
    core:SetTexture(GLOW_ROUND_TEXTURE)
    core:SetBlendMode("ADD")
    core:SetVertexColor(COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], 1)
    core:SetSize(size, size)
    core:SetPoint("TOPRIGHT", frame, "TOPRIGHT", KEY_DOT_OFFSET, KEY_DOT_OFFSET)

    local halo = frame:CreateTexture(nil, "OVERLAY", nil, 6)
    halo:SetTexture(GLOW_ROUND_TEXTURE)
    halo:SetBlendMode("ADD")
    halo:SetVertexColor(COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], KEY_DOT_GLOW_ALPHA)
    halo:SetSize(size + 2 * KEY_DOT_GLOW_REACH, size + 2 * KEY_DOT_GLOW_REACH)
    halo:SetPoint("CENTER", core, "CENTER", 0, 0)

    mailDot.core, mailDot.halo = core, halo
end

-- Mail is a two-part detect: MinimapCluster.IndicatorFrame.MailFrame is the actual clickable
-- button, reparented/skinned like any other key, and MiniMapMailIcon is Blizzard's own unread-mail
-- texture (a child of MailFrame, hidden="true" in its XML). The ICON does not show and hide with
-- the mail state by itself; verified against Blizzard_Minimap/Mainline/Minimap.lua (12.1):
--   * MiniMapMailFrameMixin:OnEvent Shows or Hides the FRAME and starts the NewMailAnim
--     (0.5 s) or MailReminderAnim (0.4 s) flipbook;
--   * MinimapMailAnimMixin:OnPlay hides the icon and :OnFinished shows it (HasNewMail());
--   * MiniMapMailFrameMixin:OnHide runs ResetMailIcon, which hides it again.
-- So the envelope appears only once the arrival animation ends, and the notification dot
-- (AddMailDot) shows alone for that 0.4 to 0.5 s. No unread-tracking logic is built here. The
-- icon is seated CENTERED in the key at the same glyph size as the other keys' icons
-- (Metrics.keyFont tall, 4:3 like the 20 x 15 MailFrame) and tinted the key's accent. Blizzard's
-- own NewMailFlipbook / MailReminderFlipbook are anchored to this texture, so the arrival
-- animation plays around the middle of the key. Nothing in MiniMapMailFrameMixin moves the icon
-- again: OnEvent only Show/Hides the frame, plays the animation and calls GetParent():Layout()
-- (a no-op on the bezel, see ApplyControlBezel).
local function StyleMailKey(bezel, anchorTo)
    local icon = MiniMapMailIcon
    local frame = MinimapCluster and MinimapCluster.IndicatorFrame and MinimapCluster.IndicatorFrame.MailFrame
    if not (icon and frame) then return nil end

    StyleBezelKey(bezel, frame, COLOR_PINK, anchorTo)

    local glyph = Metrics.keyFont
    icon:SetParent(frame)
    icon:ClearAllPoints()
    icon:SetPoint("CENTER", frame, "CENTER", 0, 0)
    icon:SetSize(glyph * 4 / 3, glyph)
    icon:SetVertexColor(COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], 1)

    AddMailDot(frame)

    return frame
end

-- Builds the chassis frame below Minimap and populates its left key row.
-- Every button lookup is feature-detected by its real (measured) name; a
-- missing one is skipped and simply leaves no gap, per key, in the row.
-- fsBezel is the sole idempotency guard (no per-key flags needed) since
-- Apply() only ever runs this once.
local function ApplyControlBezel()
    if not Minimap or Minimap.fsBezel then return end
    if not (AddRoundedFill and AddGradientBorder) then return end

    local bezel = CreateFrame("Frame", nil, Minimap)
    bezel:SetHeight(BEZEL_HEIGHT)
    bezel:SetPoint("TOPLEFT", Minimap, "BOTTOMLEFT", 0, 0)
    bezel:SetPoint("TOPRIGHT", Minimap, "BOTTOMRIGHT", 0, 0)

    -- StyleBezelKey reparents Blizzard minimap buttons onto this frame, and two
    -- of them call Layout() on whatever their parent is when their state
    -- changes. Verified against Blizzard_Minimap/Mainline/Minimap.lua on the
    -- `forever` client branch:
    --   MiniMapMailFrameMixin:OnEvent          -> self:GetParent():Layout()  (466)
    --   MiniMapCraftingOrderFrameMixin:OnEvent -> self:GetParent():Layout()  (538)
    -- Their real parent is MinimapCluster, a LayoutFrame; ours is a plain
    -- Frame, so the call hit nil and threw inside BLIZZARD's file the first
    -- time mail arrived -- which reads as a Blizzard bug and is ours.
    --
    -- A no-op is the correct body, not a stub: the bezel positions its keys
    -- explicitly in StyleBezelKey, so there is no layout pass to run. This only
    -- has to not throw.
    bezel.Layout = function() end

    AddRoundedFill(bezel, READOUT_FILL, BEZEL_RADIUS)
    AddGradientBorder(bezel, COLOR_BORDER, BEZEL_BORDER_THICK, BEZEL_RADIUS)

    Minimap.fsBezel = bezel

    local resolved, skipped = {}, {}
    local last

    local function TryKey(id, button, accentColor)
        local styled = StyleBezelKey(bezel, button, accentColor, last)
        if styled then
            last = styled
            resolved[#resolved + 1] = id
        else
            skipped[#skipped + 1] = id
        end
    end

    TryKey("tracking", MinimapCluster and MinimapCluster.Tracking, COLOR_POWER)
    TryKey("calendar", GameTimeFrame, COLOR_BORDER)

    local mailKey = StyleMailKey(bezel, last)
    if mailKey then
        last = mailKey
        resolved[#resolved + 1] = "mail"
    else
        skipped[#skipped + 1] = "mail"
    end

    -- Kept on Minimap for an in-game /dump-driven sanity check of which keys
    -- resolved; not read by any other code path in this file.
    Minimap.fsBezelResolved = resolved
    Minimap.fsBezelSkipped = skipped
end

-------------------------------------------------------------------------------
-- Coord / clock readout
-------------------------------------------------------------------------------

-- The highest number a coordinate may show. A position of 1.0 would format as "100.0", one glyph
-- wider than the 16 the readout box is sized for (READOUT_FIT), so each axis is clamped to this.
local COORD_MAX = 99.9

-- A 0-1 map fraction as the readout's percentage text, clamped to COORD_MAX. The clamp comes
-- before the format, so 99.95 also reads 99.9 rather than rounding up to "100.0".
local function FormatCoord(fraction)
    local pct = fraction * 100
    if pct > COORD_MAX then pct = COORD_MAX end
    return string.format("%.1f", pct)
end

-- FS.IsSecret read at call time, never a captured local. The map-position docs mark no return
-- as secret (only its arguments), but nothing else in this file guards it, and a secret number
-- would throw on the arithmetic above, so a secret position blanks the text like no position.
local function IsSecret(v)
    return FS.IsSecret and FS.IsSecret(v)
end

-- C_Map.GetPlayerMapPosition returns nil in instances/dungeons (no map);
-- callers must blank the text rather than error on that case.
local function GetCoordsText()
    if not (C_Map and C_Map.GetBestMapForUnit and C_Map.GetPlayerMapPosition) then return nil end

    local mapID = C_Map.GetBestMapForUnit("player")
    if not mapID then return nil end

    local pos = C_Map.GetPlayerMapPosition(mapID, "player")
    if IsSecret(pos) or not pos then return nil end

    local x, y = pos:GetXY()
    if IsSecret(x) or IsSecret(y) then return nil end
    if not (x and y) then return nil end

    return FormatCoord(x) .. ", " .. FormatCoord(y)
end

local function GetClockText()
    if type(GetGameTime) ~= "function" then return nil end

    local hour, minute = GetGameTime()
    if not (hour and minute) then return nil end

    return string.format("%02d:%02d", hour, minute)
end

local function UpdateReadout()
    if not (Minimap and Minimap.fsReadoutCoords and Minimap.fsReadoutClock) then return end

    Minimap.fsReadoutCoords:SetText(GetCoordsText() or "")
    Minimap.fsReadoutClock:SetText(GetClockText() or "")
end

-- Throttled driver: prefers C_Timer.NewTicker (matches the addon's existing
-- feature-detect pattern), falls back to a 1s OnUpdate accumulator so this
-- never polls every frame either way.
local function StartReadoutUpdater()
    UpdateReadout()

    if C_Timer and C_Timer.NewTicker then
        Minimap.fsReadoutTicker = C_Timer.NewTicker(1.0, UpdateReadout)
        return
    end

    local accumulator = 0
    local driver = CreateFrame("Frame")
    driver:SetScript("OnUpdate", function(_, elapsed)
        accumulator = accumulator + elapsed
        if accumulator >= 1.0 then
            accumulator = 0
            UpdateReadout()
        end
    end)
    Minimap.fsReadoutDriver = driver
end

-- Dark cyan-bordered LCD chip in the control bezel's right side, holding two
-- mono readouts (cyan coords left, amber clock right). Requires the bezel to
-- already exist (Minimap.fsBezel, built by ApplyControlBezel) since this is
-- where it now lives, off the map face.
local function ApplyReadout()
    if not Minimap or Minimap.fsReadout then return end
    if not Minimap.fsBezel then return end
    if not (AddRoundedFill and AddGradientBorder and ApplyMono) then return end

    local box = CreateFrame("Frame", nil, Minimap.fsBezel)
    box:SetFrameLevel(Minimap.fsBezel:GetFrameLevel() + READOUT_LEVEL_OFFSET)
    box:SetSize(READOUT_WIDTH, READOUT_HEIGHT)
    box:SetPoint("RIGHT", Minimap.fsBezel, "RIGHT", -READOUT_INSET_X, 0)

    AddRoundedFill(box, READOUT_FILL, READOUT_RADIUS)
    AddGradientBorder(box, READOUT_BORDER, READOUT_BORDER_THICK, READOUT_RADIUS)

    local coords = box:CreateFontString(nil, "OVERLAY")
    coords:SetPoint("LEFT", box, "LEFT", READOUT_FIT.inset, 0)
    ApplyMono(coords, READOUT_FONT_SIZE, COLOR_POWER)

    local clock = box:CreateFontString(nil, "OVERLAY")
    clock:SetPoint("RIGHT", box, "RIGHT", -READOUT_FIT.inset, 0)
    ApplyMono(clock, READOUT_FONT_SIZE, COLOR_AMBER)

    Minimap.fsReadoutBox = box
    Minimap.fsReadoutCoords = coords
    Minimap.fsReadoutClock = clock
    Minimap.fsReadout = true

    StartReadoutUpdater()
end

-------------------------------------------------------------------------------
-- Addon-button tray drawer (collects LibDBIcon + stray minimap buttons)
-------------------------------------------------------------------------------

-- Parker: "any addons that are loaded and would normally put icons around the minimap need
-- to be moved to the tray ... so it doesn't clutter our awesome ui. Also I never saw a
-- button to pop out the tray."
--
-- THE DRAWER hangs below the bezel (mockups .traydrawer): dark fill, cyan/violet border, a
-- small Orbitron "ADDONS" label, square tiles in a per-tile accent with the key underline.
-- Fill and border go through AddRoundedFill/AddGradientBorder at chamfer 4 like the bezel,
-- so under CHROME_CORNERS "cut" it is TOP-LEFT and BOTTOM-RIGHT cut only. Tiles wrap into
-- rows and the drawer height follows the row count. It is a child of Minimap anchored to
-- the bezel (no FS.Layout seat: the old `minimaptray` Layout entry is unused).
--
-- THE POP-OUT is a TAB hanging off the bezel's bottom edge, not a 4th bezel key. Measured
-- from the metrics above at m = 250: three keys end at pad + 3 * KEY + 2 * gap = 111.6 and
-- the readout box starts one gap later, at m - 8 - READOUT_WIDTH = 119 (at m = 208, 93 and
-- 99), so the bezel row is already full and a 4th key would sit on top of the coords/clock
-- LCD (as the third, mail, key did before the box was sized to start after it). The tab
-- (count badge left, chevron right) sits in the drawer's header row, which is the same
-- height, so open it reads as a handle on the drawer and closed as a tab under the bezel.
-- Open/closed lives in ForeverSTUwaveDB.minimapTrayOpen (default closed).
--
-- COLLECTION, read from LibDBIcon-1.0 minor 56 (the copy bundled with ForeverDungeonScout)
-- and CallbackHandler-1.0, not guessed:
--   * lib.objects / lib:GetButtonList() / lib:GetMinimapButton(name) list every button;
--   * lib.RegisterCallback(owner, "LibDBIcon_IconCreated", fn) (CallbackHandler passes
--     fn(event, button, name)) hears buttons created later; createButton fires it last;
--   * the lib positions a button ONLY through its file-local updatePosition, which does
--     button:SetPoint("CENTER", Minimap, "CENTER", x, y). It is called from lib:Show,
--     lib:Refresh, lib:SetButtonRadius, lib:SetButtonToPosition, the drag OnUpdate, the
--     PLAYER_LOGIN frame and createButton itself. It is local, so it cannot be replaced;
--     the button's own SetPoint is what we own. A collected button gets per-instance
--     overrides of SetPoint/ClearAllPoints/SetParent/SetSize/SetWidth/SetHeight/SetScale that
--     ignore the caller while the button is ours; the tray calls the stored originals. Those
--     lock overrides run no OnUpdate and no timers (the tray's own re-sweeps use
--     C_Timer.After), and click/tooltip scripts are untouched.
--   * drag-to-move is switched off with button:RegisterForDrag() (no buttons), so the lib's
--     onDragStart never fires; lib:ShowOnEnter(name, true) (hover fade, alpha 0) is
--     post-hooked back to alpha 1 because a hidden-until-hover button inside a drawer is
--     just invisible.
-- Strays: a sweep of Minimap and MinimapCluster children for Buttons named *MinimapButton*,
-- *MinimapIcon* or LibDBIcon10_*, minus everything the bezel or HideBlizzardChrome owns.
-- Re-swept on ADDON_LOADED, PLAYER_ENTERING_WORLD and two delayed passes, since addons make
-- their button late. Combat: nothing here is secure, but reparent and anchor changes still
-- wait for PLAYER_REGEN_ENABLED, per the rest of this file.

local TRAY_FILL = { 0.027, 0.012, 0.062, 0.96 } -- between the mock's #090515 and #040209 (flat; AddRoundedFill has no gradient)
local TRAY_LABEL_COLOR = { 0.604, 0.561, 0.741, 1 } -- mock --muted, #9a8fbd
local COLOR_MINT = { 0.227, 1, 0.627, 1 } -- mock tray key #3affa0
local TRAY_ACCENTS = { COLOR_POWER, COLOR_PINK, COLOR_BORDER, COLOR_AMBER, COLOR_MINT }
local TRAY_LOGIN_SWEEPS = { 1.5, 5 } -- seconds after Apply for the late-button re-sweeps
local TRAY_HIGHLIGHT_TEXTURE = "Interface\\Buttons\\WHITE8X8"
-- Names the bezel / HideBlizzardChrome already handle, lower case prefixes. A stray button
-- whose name starts with one is Blizzard's, not an addon's.
local TRAY_BLIZZARD_PREFIXES = {
    "gametime", "expansionlandingpage", "addoncompartment", "minimaptracking", "minimapzoom",
    "minimapmail", "minimapworldmap", "minimapbattlefield", "minimaplfg", "minimapinstance",
    "minimapcrafting", "queuestatus", "foreverstuwave",
}
-- Per-instance methods a collected button must not obey from anyone but the tray.
local TRAY_LOCKED_METHODS = {
    "SetPoint", "ClearAllPoints", "SetParent", "SetSize", "SetWidth", "SetHeight", "SetScale",
}

local Tray = {
    entries = {},      -- { button, accent, orig = { SetPoint = fn, ... } } in collection order
    byButton = {},
    pending = {},      -- buttons seen in combat, adopted on PLAYER_REGEN_ENABLED
    layoutPending = false,
    relayout = false,  -- re-entry guard (a Show/Hide hook can fire while we lay out)
    count = 0,         -- tiles currently laid out (shown buttons only)
    open = false,
    libHooked = false,
    togglePending = false, -- a drawer show/hide waiting for PLAYER_REGEN_ENABLED
    failureLogged = false,
    owner = {},        -- CallbackHandler owner key
}

local function LogTrayFailure(where, err)
    if Tray.failureLogged then return end
    Tray.failureLogged = true
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("minimap_tray",
            "|cffff4488Forever STUwave|r: minimap button tray degraded (" .. tostring(where) .. "): " .. tostring(err))
    end
end

local function TrayMetrics()
    local m = Metrics.map
    local tabH = math.max(12, math.floor(KEY_SIZE * 0.5 + 0.5))
    return {
        tile = math.max(12, math.floor(KEY_SIZE * 0.8 + 0.5)),
        gap = math.max(3, math.floor(m * 0.02 + 0.5)),
        padX = math.max(6, math.floor(m * 0.036 + 0.5)),
        padY = math.max(4, math.floor(m * 0.024 + 0.5)),
        tabW = math.max(24, math.floor(KEY_SIZE * 1.2 + 0.5)),
        tabH = tabH,
        header = tabH + 3,
        labelFont = math.max(6, math.floor(m * 0.032 + 0.5)),
        tabFont = math.max(7, math.floor(tabH * 0.6 + 0.5)),
    }
end

local function TrayWantsOpen()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.minimapTrayOpen == true
end

local function SaveTrayOpen(open)
    if type(ForeverSTUwaveDB) ~= "table" then ForeverSTUwaveDB = {} end
    ForeverSTUwaveDB.minimapTrayOpen = open and true or false
end

-- Calls the original (pre-override) method on a collected button.
local function Raw(entry, method, ...)
    local fn = entry.orig[method]
    if fn then return fn(entry.button, ...) end
end

-- No closure per call: this runs for every entry on every layout and every Show/Hide.
local function ButtonIsShown(button)
    local ok, shown = pcall(button.IsShown, button)
    return (not ok) or shown ~= false
end

-- True when a collected button is a protected frame (the drawer's own Show/Hide is then
-- left for after combat; nothing here ever touches a protected frame directly).
local function AnyProtectedButton()
    for _, entry in ipairs(Tray.entries) do
        local ok, protected = pcall(entry.button.IsProtected, entry.button)
        if ok and protected then return true end
    end
    return false
end

-- Drawer show/hide, deferred to PLAYER_REGEN_ENABLED when protected buttons ride in it.
local function SetDrawerShown(drawer, want)
    if (drawer:IsShown() and true or false) == want then
        Tray.togglePending = false
        return
    end
    if InCombatLockdown() and AnyProtectedButton() then
        Tray.togglePending = true
        return
    end
    Tray.togglePending = false
    if want then drawer:Show() else drawer:Hide() end
end

local function UpdateToggle()
    local toggle = Minimap and Minimap.fsTrayToggle
    local drawer = Minimap and Minimap.fsTray
    if not (toggle and drawer) then return end
    if toggle.count then toggle.count:SetText(tostring(Tray.count)) end
    if toggle.glyph then toggle.glyph:SetText(Tray.open and "^" or "v") end
    if Tray.count == 0 then
        toggle:Hide()
        SetDrawerShown(drawer, false)
    else
        toggle:Show()
        SetDrawerShown(drawer, Tray.open)
    end
end

local function LayoutTiles()
    local drawer = Minimap and Minimap.fsTray
    if not drawer then return end
    local m = TrayMetrics()
    local width = (Minimap.GetWidth and Minimap:GetWidth()) or Metrics.map
    local cols = math.max(1, math.floor((width - 2 * m.padX + m.gap) / (m.tile + m.gap)))

    local n = 0
    for _, entry in ipairs(Tray.entries) do
        if ButtonIsShown(entry.button) then
            local col, row = n % cols, math.floor(n / cols)
            Raw(entry, "SetScale", 1)
            Raw(entry, "SetSize", m.tile, m.tile)
            Raw(entry, "ClearAllPoints")
            Raw(entry, "SetPoint", "TOPLEFT", drawer, "TOPLEFT",
                m.padX + col * (m.tile + m.gap), -(m.header + row * (m.tile + m.gap)))
            n = n + 1
        end
    end
    Tray.count = n

    local rows = math.ceil(n / cols)
    local height = m.header + m.padY
    if rows > 0 then height = m.header + rows * m.tile + (rows - 1) * m.gap + m.padY end
    drawer:SetHeight(height)
    UpdateToggle()
end

local function RelayoutTray()
    if not (Minimap and Minimap.fsTray) or Tray.relayout then return end
    if InCombatLockdown() then
        Tray.layoutPending = true -- PLAYER_REGEN_ENABLED (held by Tray.events) finishes it
        return
    end
    Tray.relayout = true
    local ok, err = pcall(LayoutTiles)
    Tray.relayout = false
    if not ok then LogTrayFailure("layout", err) end
end

local function SetTrayOpen(open)
    Tray.open = open and true or false
    SaveTrayOpen(Tray.open)
    UpdateToggle()
end

-- The lib's round "minimap button" border and background disc, or anything a stray button
-- draws from those same two Blizzard textures, would show inside the square tile.
local function IsMinimapButtonArt(tex)
    if tex == 136430 or tex == 136467 then return true end -- TrackingBorder, UI-Minimap-Background
    if type(tex) ~= "string" then return false end
    local lower = string.lower(tex)
    return string.find(lower, "minimap-trackingborder", 1, true) ~= nil
        or string.find(lower, "ui-minimap-background", 1, true) ~= nil
end

local function HideArt(region)
    if not region then return end
    pcall(function() region:Hide() end)
    pcall(function() region:SetAlpha(0) end)
end

local function StripMinimapButtonArt(button)
    HideArt(button.border)
    HideArt(button.background)
    local ok, regions = pcall(function() return { button:GetRegions() } end)
    if not ok then return end
    for _, region in ipairs(regions) do
        local isTexture, tex = false, nil
        pcall(function() isTexture = (region:GetObjectType() == "Texture") end)
        if isTexture then
            pcall(function() tex = region:GetTexture() end)
            if IsMinimapButtonArt(tex) then HideArt(region) end
        end
    end
end

local function SeatTileIcon(button, m)
    local icon = button.icon or button.Icon
    if not icon then return end
    local isTexture = false
    pcall(function() isTexture = (icon:GetObjectType() == "Texture") end)
    if not isTexture then return end
    local size = math.max(8, math.floor(m.tile * 0.64 + 0.5))
    pcall(function()
        icon:ClearAllPoints()
        icon:SetPoint("CENTER", button, "CENTER", 0, 0)
        icon:SetSize(size, size)
    end)
end

local function NeutralizeHoverFade(button)
    button.showOnMouseover = false
    pcall(function() if button.fadeOut and button.fadeOut.Stop then button.fadeOut:Stop() end end)
    pcall(function() button:SetAlpha(1) end)
end

-- The square ADD wash that replaces the lib's round highlight.
local function ApplyTileHighlight(button, accent)
    pcall(function()
        button:SetHighlightTexture(TRAY_HIGHLIGHT_TEXTURE, "ADD")
        local hl = button.GetHighlightTexture and button:GetHighlightTexture()
        if hl then
            hl:SetVertexColor(accent[1], accent[2], accent[3], 0.25)
            hl:ClearAllPoints()
            hl:SetAllPoints(button)
        end
    end)
end

-- The tile: dark cut fill, accent ring and the key underline, behind the button's own icon.
local function BuildTileChrome(button, accent, m)
    local chamfer = KeyChamfer(m.tile)
    if chamfer then
        local texture = FS.Theme.AddSliceTexture(
            button, CutFillTexture(chamfer), READOUT_FILL, "BACKGROUND", 0)
        FS.Theme.ApplyNineSlice(texture, chamfer)
    elseif AddRoundedFill then
        AddRoundedFill(button, READOUT_FILL, Metrics.keyRadius)
    end
    if SkinButton then
        SkinButton(button, { borderColor = accent, radius = Metrics.keyRadius, chamfer = chamfer })
    end
    AddKeyUnderline(button, m.tile, m.tile, accent)
    ApplyTileHighlight(button, accent)
end

local function AdoptButton(button)
    local drawer = Minimap.fsTray
    local m = TrayMetrics()
    local entry = {
        button = button,
        accent = TRAY_ACCENTS[(#Tray.entries % #TRAY_ACCENTS) + 1],
        orig = {},
    }

    -- Locks first, so nothing the steps below trigger (or any addon, ever again) can
    -- re-anchor the button around the map. Originals are kept for the tray's own use.
    for _, method in ipairs(TRAY_LOCKED_METHODS) do
        local original = button[method]
        if type(original) == "function" then
            entry.orig[method] = original
            button[method] = function(self, ...)
                if self.fsTrayOwned then return end
                return original(self, ...)
            end
        end
    end
    button.fsTrayOwned = true
    Tray.byButton[button] = entry
    Tray.entries[#Tray.entries + 1] = entry

    -- One failing step must not strand the rest, but it must not vanish either.
    local function Step(label, fn)
        local ok, err = pcall(fn)
        if not ok then LogTrayFailure("adopt " .. label, err) end
    end

    Step("parent", function() Raw(entry, "SetParent", drawer) end)
    -- Tiles sit in the drawer's own strata and just above it. LibDBIcon builds its button
    -- with SetFixedFrameStrata/Level(true) (LibDBIcon-1.0 createButton), so the fixed flags
    -- are lifted for the explicit set, then restored so a later reparent or raise cannot
    -- shuffle the tile under the drawer's fill. Feature-detected: stray buttons have none.
    Step("strata", function()
        if button.SetFixedFrameStrata then pcall(button.SetFixedFrameStrata, button, false) end
        if button.SetFixedFrameLevel then pcall(button.SetFixedFrameLevel, button, false) end
        local strata = drawer.GetFrameStrata and drawer:GetFrameStrata()
        if strata then button:SetFrameStrata(strata) end
        button:SetFrameLevel((drawer:GetFrameLevel() or 1) + 2)
        if button.SetFixedFrameStrata then pcall(button.SetFixedFrameStrata, button, true) end
        if button.SetFixedFrameLevel then pcall(button.SetFixedFrameLevel, button, true) end
    end)
    Step("movable", function() button:SetMovable(false) end)
    Step("drag", function() button:RegisterForDrag() end)
    Step("art", function() StripMinimapButtonArt(button) end)
    Step("icon", function() SeatTileIcon(button, m) end)
    Step("hover", function() NeutralizeHoverFade(button) end)
    Step("chrome", function() BuildTileChrome(button, entry.accent, m) end)
    -- A button its addon shows or hides (db.hide, lib:Hide/Show) joins or leaves the grid,
    -- but only when its shown state actually changed (Show on a shown button is a no-op).
    entry.shown = ButtonIsShown(button)
    local function OnVisibilityCall()
        local now = ButtonIsShown(button)
        if now == entry.shown then return end
        entry.shown = now
        RelayoutTray()
    end
    Step("visibility", function()
        hooksecurefunc(button, "Show", OnVisibilityCall)
        hooksecurefunc(button, "Hide", OnVisibilityCall)
    end)
end

local function CollectButton(button)
    if not button or Tray.byButton[button] then return end
    if not (Minimap and Minimap.fsTray) then return end
    if InCombatLockdown() then
        Tray.pending[button] = true -- adopted on PLAYER_REGEN_ENABLED
        return
    end
    local ok, err = pcall(AdoptButton, button)
    if not ok then LogTrayFailure("collect", err) end
    RelayoutTray()
end

local function LooksLikeMinimapButton(name)
    local lower = string.lower(name)
    if string.sub(lower, 1, 12) == "libdbicon10_" then return true end
    return string.find(lower, "minimapbutton", 1, true) ~= nil
        or string.find(lower, "minimapicon", 1, true) ~= nil
end

local function IsBlizzardOrOurs(button, name)
    if button.fsBezelOwned or button.fsHideHooked or button.fsTrayOwned then return true end
    local lower = string.lower(name)
    for _, prefix in ipairs(TRAY_BLIZZARD_PREFIXES) do
        if string.sub(lower, 1, #prefix) == prefix then return true end
    end
    return false
end

local function SweepStrays()
    for _, parent in ipairs({ Minimap, MinimapCluster }) do
        if parent and parent.GetChildren then
            local ok, kids = pcall(function() return { parent:GetChildren() } end)
            if ok then
                for _, child in ipairs(kids) do
                    local objType, name
                    pcall(function() objType = child:GetObjectType() end)
                    pcall(function() name = child:GetName() end)
                    if (objType == "Button" or objType == "CheckButton")
                        and type(name) == "string" and LooksLikeMinimapButton(name)
                        and not IsBlizzardOrOurs(child, name) then
                        CollectButton(child)
                    end
                end
            end
        end
    end
end

-- Lib calls that re-apply the round art, icon geometry or highlight on an existing button
-- (LibDBIcon-1.0 minor 56: createButton and every Set/ResetButton* call). Each is
-- post-hooked, feature-detected, so a tray-owned button is restyled right after.
local TRAY_ART_HOOKS = {
    "ResetButtonBorder", "SetButtonBorder", "ResetButtonBackground", "SetButtonBackground",
    "ResetButtonIcon", "SetButtonIcon", "ResetButtonHighlightTexture", "SetButtonHighlightTexture",
}

local function ReapplyTileArt(button)
    local entry = Tray.byButton[button]
    if not entry then return end
    local m = TrayMetrics()
    local ok, err = pcall(function()
        StripMinimapButtonArt(button)
        SeatTileIcon(button, m)
        ApplyTileHighlight(button, entry.accent)
    end)
    if not ok then LogTrayFailure("art reapply", err) end
end

local function GetDBIcon()
    if type(LibStub) ~= "table" and type(LibStub) ~= "function" then return nil end
    local ok, lib = pcall(LibStub, "LibDBIcon-1.0", true)
    if ok and type(lib) == "table" then return lib end
    return nil
end

local function SweepLib()
    local lib = GetDBIcon()
    if not lib then return end

    if not Tray.libHooked then
        Tray.libHooked = true
        local okCb, errCb = pcall(function()
            lib.RegisterCallback(Tray.owner, "LibDBIcon_IconCreated", function(_, button)
                CollectButton(button)
            end)
        end)
        if not okCb then LogTrayFailure("IconCreated callback", errCb) end
        pcall(function()
            hooksecurefunc(lib, "ShowOnEnter", function(_, name, value)
                local button = value and lib.GetMinimapButton and lib:GetMinimapButton(name)
                if button and Tray.byButton[button] then NeutralizeHoverFade(button) end
            end)
        end)
        for _, method in ipairs(TRAY_ART_HOOKS) do
            if type(lib[method]) == "function" then
                local okHook, errHook = pcall(hooksecurefunc, lib, method, function(_, name)
                    local button = lib.GetMinimapButton and lib:GetMinimapButton(name)
                    if button then ReapplyTileArt(button) end
                end)
                if not okHook then LogTrayFailure("hook " .. method, errHook) end
            end
        end
    end

    local okList, names = pcall(function() return lib:GetButtonList() end)
    if not (okList and type(names) == "table") then return end
    for _, name in ipairs(names) do
        local okBtn, button = pcall(function() return lib:GetMinimapButton(name) end)
        if okBtn and button then CollectButton(button) end
    end
end

local function SweepAll()
    if not (Minimap and Minimap.fsTray) then return end
    local ok, err = pcall(function()
        SweepLib()
        SweepStrays()
    end)
    if not ok then LogTrayFailure("sweep", err) end
end

local function FlushPending()
    local pending = Tray.pending
    Tray.pending = {}
    for button in pairs(pending) do CollectButton(button) end
    if Tray.layoutPending then
        Tray.layoutPending = false
        RelayoutTray()
    end
    if Tray.togglePending then UpdateToggle() end
end

local function ReanchorTray()
    if not (Minimap and Minimap.fsTray) then return end
    local anchorAbove = Minimap.fsBezel or Minimap
    Minimap.fsTray:ClearAllPoints()
    Minimap.fsTray:SetPoint("TOPLEFT", anchorAbove, "BOTTOMLEFT", 0, 0)
    Minimap.fsTray:SetPoint("TOPRIGHT", anchorAbove, "BOTTOMRIGHT", 0, 0)
    local toggle = Minimap.fsTrayToggle
    if toggle then
        toggle:ClearAllPoints()
        toggle:SetPoint("TOPRIGHT", anchorAbove, "BOTTOMRIGHT", -BEZEL_PADDING, 0)
    end
end

local function BuildTrayToggle(m, anchorAbove)
    local toggle = CreateFrame("Button", "ForeverSTUwaveMinimapTrayToggle", anchorAbove)
    toggle:SetSize(m.tabW, m.tabH)
    toggle:Hide() -- stays hidden until UpdateToggle shows it; a throw below leaves no tab
    toggle:SetPoint("TOPRIGHT", anchorAbove, "BOTTOMRIGHT", -BEZEL_PADDING, 0)
    toggle:SetFrameLevel((anchorAbove:GetFrameLevel() or 1) + 6)

    local chamfer = KeyChamfer(m.tabH)
    if chamfer then
        local texture = FS.Theme.AddSliceTexture(
            toggle, CutFillTexture(chamfer), READOUT_FILL, "BACKGROUND", 0)
        FS.Theme.ApplyNineSlice(texture, chamfer)
    elseif AddRoundedFill then
        AddRoundedFill(toggle, READOUT_FILL, Metrics.keyRadius)
    end
    if SkinButton then
        SkinButton(toggle, { borderColor = COLOR_POWER, radius = Metrics.keyRadius, chamfer = chamfer })
    end
    AddKeyUnderline(toggle, m.tabW, m.tabH, COLOR_POWER)

    -- Count badge (left, amber like the clock) and chevron (right, cyan). Plain ASCII "v" /
    -- "^": no glyph that the bundled mono font might lack.
    local count = toggle:CreateFontString(nil, "OVERLAY")
    count:SetPoint("LEFT", toggle, "LEFT", 5, 0)
    ApplyMono(count, m.tabFont, COLOR_AMBER)
    count:SetText("0")
    local glyph = toggle:CreateFontString(nil, "OVERLAY")
    glyph:SetPoint("RIGHT", toggle, "RIGHT", -5, 1)
    ApplyMono(glyph, m.tabFont, COLOR_POWER)
    glyph:SetText("v")
    toggle.count = count
    toggle.glyph = glyph

    toggle:SetScript("OnClick", function() SetTrayOpen(not Tray.open) end)
    toggle:SetScript("OnEnter", function(self)
        if not GameTooltip then return end
        pcall(function()
            GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
            GameTooltip:SetText(string.format("Addon buttons (%d)", Tray.count))
            GameTooltip:Show()
        end)
    end)
    toggle:SetScript("OnLeave", function()
        if GameTooltip then pcall(function() GameTooltip:Hide() end) end
    end)
    return toggle
end

local function BuildTray()
    if not Minimap or Minimap.fsTray then return end
    if not (AddRoundedFill and AddGradientBorder and ApplyMono and ApplyFontGeneric) then return end

    local m = TrayMetrics()
    local anchorAbove = Minimap.fsBezel or Minimap

    local drawer = CreateFrame("Frame", nil, Minimap)
    drawer:SetHeight(m.header + m.padY)
    drawer:SetPoint("TOPLEFT", anchorAbove, "BOTTOMLEFT", 0, 0)
    drawer:SetPoint("TOPRIGHT", anchorAbove, "BOTTOMRIGHT", 0, 0)
    AddRoundedFill(drawer, TRAY_FILL, BEZEL_RADIUS)
    -- COLOR_BORDER_BLEND, the same cyan/violet color-mix as the map's own border, per the
    -- mockup's .traydrawer. Under "cut" the chamfer is TOP-LEFT and BOTTOM-RIGHT only.
    AddGradientBorder(drawer, COLOR_BORDER_BLEND, BEZEL_BORDER_THICK, BEZEL_RADIUS)

    local label = drawer:CreateFontString(nil, "OVERLAY")
    label:SetPoint("LEFT", drawer, "TOPLEFT", m.padX, -(m.header / 2))
    ApplyFontGeneric(label, FONT_ORBITRON, m.labelFont, TRAY_LABEL_COLOR, "")
    label:SetShadowColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.5)
    label:SetShadowOffset(0, 0)
    label:SetText("ADDONS")
    drawer.label = label
    drawer:Hide()

    -- Minimap.fsTray / fsTrayToggle are published only once everything below exists, so a
    -- throw anywhere in here leaves nothing half-wired (BuildTrayToggle hides its frame at
    -- creation, so a failed build leaves no visible tab either).
    local toggle = BuildTrayToggle(m, anchorAbove)

    -- Late buttons: addons create theirs well after login.
    local events = CreateFrame("Frame")
    events:RegisterEvent("ADDON_LOADED")
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    -- PLAYER_REGEN_ENABLED is held for the whole session: a button seen in combat, or a
    -- Show/Hide in combat, is finished when lockdown lifts.
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:SetScript("OnEvent", function(_, event)
        if event == "PLAYER_REGEN_ENABLED" then
            FlushPending()
        elseif event == "PLAYER_ENTERING_WORLD" then
            SweepAll()
            if C_Timer and C_Timer.After then
                for _, delay in ipairs(TRAY_LOGIN_SWEEPS) do C_Timer.After(delay, SweepAll) end
            end
        else
            SweepAll()
        end
    end)
    Tray.events = events

    Minimap.fsTray = drawer
    Minimap.fsTrayToggle = toggle
    Tray.open = TrayWantsOpen()

    SweepAll()
    if C_Timer and C_Timer.After then
        for _, delay in ipairs(TRAY_LOGIN_SWEEPS) do C_Timer.After(delay, SweepAll) end
    end
    RelayoutTray()
end

local function ApplyMinimapTray()
    local ok, err = pcall(BuildTray)
    if not ok then LogTrayFailure("build", err) end
end

-- Layout.lua's watcher re-Applies every seated frame on PLAYER_LOGIN/UI_SCALE_CHANGED/
-- DISPLAY_SIZE_CHANGED, which can move the map and bezel. Callbacks run after that pass
-- (same OnRescale mechanism ScheduleCompensate above uses for the cluster).
if FS.Layout and FS.Layout.OnRescale then
    FS.Layout.OnRescale(ReanchorTray)
    FS.Layout.OnRescale(RelayoutTray)
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Minimap is a non-secure frame, so none of the steps above are combat-illegal;
-- deferred anyway for consistency with the rest of the addon's Init pattern.
local function Apply()
    ApplyLayout()
    ApplySquareMask()
    HideBlizzardChrome()
    ApplyChrome()
    ApplyHighlight()
    ApplyPlayerBlipGlow()
    ApplyZoom()
    ApplyZoneText()
    ApplyNorthTick()
    ApplyControlBezel()
    ApplyReadout()
    ApplyMinimapTray()
    ApplyScanline()
end

-- PLAYER_LOGIN, not file scope. Two reasons, both bitten already elsewhere in
-- this addon: UIParent is not fully sized during load (so FS.Layout seats the
-- cluster at ~64%), and several of the frames HideBlizzardChrome targets --
-- GameTimeFrame, the expansion button, the addon compartment -- are not
-- reliably present or stay re-shown when hidden that early. The sun and clock
-- above the map survived a file-scope hide for exactly that reason.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    if InCombatLockdown() then
        self:RegisterEvent("PLAYER_REGEN_ENABLED")
        self:SetScript("OnEvent", function(inner)
            inner:UnregisterEvent("PLAYER_REGEN_ENABLED")
            Apply()
        end)
        return
    end
    Apply()
end)
