-- Forever STUwave: Minimap
-- Rounded mask, feature-detected Blizzard-chrome hide, mouse-wheel zoom, a restyled zone-text label, a cyan north tick,
-- a single tiled horizontal scanline overlay, a soft top-left highlight and a magenta glow behind the native player
-- blip, and ONE BODY under all of it (design mockup 2026-11-12, section A "ONE BODY"): the map, a key row under it and,
-- when the addon tray is open, a second row of collected addon buttons are a single chamfered shape with one cyan edge
-- and one dark plate, cut at its TOP-LEFT and BOTTOM-RIGHT only (Theme.CHROME_CORNERS "cut"). The map has no bottom
-- cut of its own: the body's BOTTOM-RIGHT is the last row's, wherever that row is.
--
--   * the key row: bare glyphs over a coloured LED underline, no boxes. Tracking (cyan), calendar (violet), the STU key
--     (pink; it replaces the stock gear and opens the config window) and the tray toggle (amber; the number of
--     collected addon buttons and a chevron), then a faint divider and the coords, right aligned. Mail keeps a seat
--     after the toggle and is there only while mail waits; every key is placed by the keys that are showing, so the row
--     never has a hole in it. Hovering a key draws a thin chamfered outline in its own colour and brightens its LED.
--   * the tray: a second row of the same body under a dashed amber rule, collecting the addon minimap buttons
--     (LibDBIcon and stray *MinimapButton* frames) so they stop cluttering the map edge, each with the same LED
--     underline. Open or closed is the toggle's; it is hidden with no buttons.
--
-- The bezel (Minimap.fsBezel) is the key row. Everything that hangs under the body (QuestTimer.lua's drawer) seats on its
-- bottom edge. The vignette/glare CRT elements and the pulsing waypoint marker are a deliberate second chunk, still
-- deferred (no existing waypoint-arrow handling was found anywhere in this addon to build on). Every Blizzard-chrome
-- lookup below is nil-guarded so a missing name degrades to a no-op instead of erroring.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local AddOuterGlow = FS.Theme.AddOuterGlow
local ApplyFontGeneric = FS.Theme.ApplyFontGeneric
local ApplyMono = FS.Theme.ApplyMono
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_TEXT_WHITE = FS.Theme.COLOR_TEXT_WHITE
local FONT_ORBITRON = FS.Theme.FONT_ORBITRON

local GLOW_SIZE -- derived in RefreshMetrics below (Metrics.glowSize)
local GLOW_ALPHA = 0.20 -- was 0.42 (too bright, read as a second border); cut to 0.20 for a soft ambient halo (2026-09-26 minimap fix). Retune here if still too visible/faint.

-- The body's chamfer, in screen pixels: Theme.CHROME_CORNERS "cut" is the TOP-LEFT and BOTTOM-RIGHT of the whole body at the
-- baked piece c = 6 (border_cut_c6_t1, fill_cut_c6); mask_minimap_tl.tga cuts the map's own top-left to match (6/250).
-- Under "round" (the old A/B flag) the body is square.
local BODY_CHAMFER = 6

local COLOR_AMBER = FS.Theme.COLOR_AMBER or { 1, 0.714, 0.282, 1 } -- mockup #ffb648: the tray's accent (toggle, rule, first tiles)

-- Mockup pink (#ff2e97) is the exact value already tokenized as Theme.COLOR_HEALTH, so it is reused here rather than
-- re-declared: the STU key's LED and hover outline, the mail key and its notification dot.
local COLOR_PINK = COLOR_HEALTH

-- THE BODY. One edge in the cyan of the coords (mockup --cyan, 2 px wide at 2x so 1 px) round the whole shape, and one
-- plate under the rows (mockup --plate #0b0618 at .94) that starts where the map ends: the map is the Minimap frame's own
-- render, the body frame sits above it, so a plate over the map would hide it.
local BODY_EDGE = COLOR_POWER
local BODY_PLATE = { 0.043, 0.024, 0.094, 0.94 }
-- The faint rule where the map meets the key row (mockup: cyan at 35%, 1 px at 2x so under 1 px; drawn as 1 px).
local BODY_RULE = { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.35 }

-- Every size of the rows is a SCREEN PIXEL count, taken from the mockup, which is drawn at 2x (1 design px = 2 screen
-- px): each number below is its mockup px / 2, at the reference map REF_MAP px wide (the mockup's 496 px map / 2). A map of
-- another physical size scales them by (map px / REF_MAP) and rounds each to a whole pixel, so the rows stay in the
-- mockup's proportion at any resolution and every edge lands on the pixel grid (Geo below). Where a number is not the
-- mockup's it says why:
--
--   row       28  the key row's height (mockup 56 / 2)
--   margin     8  the gap from the body's left and right edges to the first key and to the coords (mockup 16 and 18 / 2; both
--                 8, so the row is symmetric)
--   keyW      18  a key's width, which is its LED's (mockup 34 / 2 = 17, and 36 / 2 = 18 for the tray toggle: 18 puts the
--                 16 px glyph and the 32 px STU canvas on whole pixels, which an odd width cannot)
--   keyGap     8  the gap between keys, and between the last key and the divider (mockup 16 / 2)
--   keyH      22  a key's height: the glyph, the gap and the LED, and the height of the STU icon
--   glyph     16  a glyph's box (mockup 30 / 2 = 15; 16 keeps the same parity as keyW, so it centres on whole pixels)
--   glyphGap   3  glyph to LED (mockup 8 / 2 less the glyph's own padding)
--   led        2  the LED underline's thickness (mockup 3 / 2 = 1.5, which is not a pixel count)
--   stu       32  the STU icon's texture canvas; its art box is 22 px of it (mockup 44 / 2) and its ink 20 px wide
--   stuGap     2  the STU icon's ink to the LED (mockup: its lettering ends 3.5 above the LED at 2x, 1.75 px). The icon is a
--                 taller block than the glyphs, so it hangs from this gap instead of sitting centred on the key
--   topM       3  the vertical margin round the keys, (row - keyH) / 2: the row is as high as the STU icon plus 3 above and
--                 below it, so the margins above and below the keys are equal
--   coords    12  the coords' font size (mockup 24 / 2)
--   count     10  the toggle count's font size (mockup 20 / 2)
--   dividerH  18  the divider's height (mockup 36 / 2), centred in the row
--   chevron  8x4  the toggle's chevron (mockup 12 x 6 / 2 plus its stroke)
--   outline    3  how far a hovered key's outline stands off it sideways (mockup: a 24 px wide box round a 17 px LED / 2)
--   halo       1  how far the bright LED's wash reaches past the LED (mockup 3 at 2x, 1.5 px; 1 keeps the wash inside the hover
--                 outline, which stands outlineY = 1 px below the key)
--   dash       2  the tray's dashed rule's dash and gap (mockup 4 / 2)
--   ruleInset  6  how far that rule stops short of each edge (mockup 12 / 2)
local REF_MAP = 248
local SPEC = {
    row = 28, margin = 8, keyW = 18, keyGap = 8, keyH = 22, glyph = 16, glyphGap = 3, led = 2, stu = 32, stuGap = 2,
    coords = 12, count = 10, dividerH = 18, chevW = 8, chevH = 4, outline = 3, halo = 1,
    dash = 2, ruleInset = 6,
}
-- The Metrics below size the map's own furniture (zone text, north tick, blip, glow); the rows above do not use them.
local Metrics = {}

local function DeriveMetrics()
    local L = FS.Layout and FS.Layout.minimap
    local w = (L and (L.scaledW or L.w)) or 250
    local h = (L and (L.scaledH or L.h)) or 250
    local m = math.min(w, h)
    local off = math.max(1, m * 0.018)

    Metrics.map = m
    Metrics.blip = math.max(3, m * 0.04)
    Metrics.zoneFont = math.max(6, m * 0.092)
    Metrics.northFont = math.max(5, m * 0.062)
    Metrics.northInset = off
    -- was m*0.076 (glow band read as a second border); halved to m*0.038 (2026-09-26 minimap fix). Retune here if still too wide/narrow.
    Metrics.glowSize = math.max(4, m * 0.038)
    return Metrics
end

local NORTH_FONT_SIZE
local NORTH_INSET_Y

local ZONE_FONT_SIZE

-- Mononoki Nerd Font Mono's advance in ems (measured 0.5615): the coords are the widest reading "99.9, 99.9" (the coord formatter,
-- FormatCoord, clamps each number to COORD_MAX), 10 glyphs, and the "--.-, --.-" dashes are as wide.
local COORDS_CHARS = 10
local COORDS_ADVANCE = 0.5615

-- Frame levels above the bezel: the body (plate, border) at +1, the row's divider and coords and the tray at +2, the keys
-- above them at +3 (so a key, and the pink mail one in particular, is never painted under anything else).
local BODY_LEVEL_OFFSET = 1
local DECK_LEVEL_OFFSET = 2
local KEY_LEVEL_OFFSET = 3

-- Existing shipped asset (see Chat.lua's identical local declaration for its
-- own scanline overlay): a 4x4 tiling texture, one dark row over transparent.
-- SCANLINE_ALPHA keeps the scrim subtle over the small, blip-busy map face.
local SCANLINE_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\scanline.tga"
local SCANLINE_ALPHA = 0.65 -- mockup scan:26 -> opacity 26/40

-- The map face's mask: only the TOP-LEFT is cut, the body's bottom-right belongs to its last row (generate_mask_minimap_tl.py).
local MASK_MINIMAP_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\mask_minimap_tl.tga"

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

-- Mail key's notification dot (mockup .mmbtn .nd): a round pink dot straddling the key's top-right corner, with a soft
-- pink glow. The dot is a sixth of the 2x map's 30 px key scaled to this key (6 px), 2 px past the corner; the glow reach is
-- 3 px, not the mockup's ~5: the mockup's key has overflow:hidden, which clips its box-shadow at the key edge, but WoW does not
-- clip a texture to its parent, so the halo draws at full reach (at 5 it touched the neighbouring chrome).
local KEY_DOT_SIZE = 6
local KEY_DOT_OFFSET = 2
local KEY_DOT_GLOW_REACH = 3
local KEY_DOT_GLOW_ALPHA = 0.6
-- Our own handle on the dot textures (never a field on Blizzard's MailFrame).
local mailDot = {}

-- The key row's glyphs (generate_minimap_keys.py, generate_icon_stu.py): white shapes tinted in Lua, and the STU icon in colour.
local TEXTURES = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local SEARCH_TEXTURE = TEXTURES .. "icon_key_search.tga"
local CALENDAR_TEXTURE = TEXTURES .. "icon_key_calendar.tga"
local CHEVRON_TEXTURE = TEXTURES .. "icon_key_chevron.tga"
local STU_TEXTURE = TEXTURES .. "icon_stu.tga"
-- The STU texture's canvas is 32 texels with the 22 texel art centred; the key lays the canvas at SPEC.stu pixels. The bottom
-- edge of its last solid texel row is 25 / 32 down the canvas (generate_icon_stu.py, pinned by test_tga_generators.py): the key
-- hangs the canvas from that line, SPEC.stuGap above the LED.
local STU_INK_BOTTOM = 25 / 32
local STU_KEY_NAME = "ForeverSTUwaveMinimapSTUKey"

-- A key at rest and bright: the LED's alpha at rest (mockup .75) and bright (1), and the wash behind a bright LED (mockup .18).
local LED_REST_ALPHA = 0.75
local LED_WASH_ALPHA = 0.18
-- The faint divider between the keys and the coords (mockup: cyan at 30%).
local DIVIDER_ALPHA = 0.3
-- The tray's dashed rule (mockup: amber at 35%).
local RULE_ALPHA = 0.35

local function RefreshMetrics()
    DeriveMetrics()

    -- Plain reassignment, not `local` redeclaration: every function below
    -- that reads these closed over the SAME upvalue slots at file-load time,
    -- and Lua closures share upvalues by reference, not by value -- a
    -- redeclare here would create new locals those functions never see.
    NORTH_FONT_SIZE = Metrics.northFont
    NORTH_INSET_Y = Metrics.northInset

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
-- cluster's own geometry. Player, 2026-09-22: "the minmap has some invisible
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
-- re-seat. Whether Blizzard's real first-login sequence does that (the player's new Mage,
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

-- The map face's mask: a hard square with ONLY the top-left cut (6/250), the body's own top-left chamfer; the
-- bottom-right belongs to the body's last row. SetMaskTexture stretches the mask to whatever Minimap's current size is, so this
-- FRACTIONAL cut stays correct automatically at any UI scale -- no per-scale recompute needed. See
-- generate_mask_minimap_tl.py.
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
                -- A button later reparented into the key row (see
                -- AdoptBlizzardKey) marks itself fsBezelOwned; skip the re-hide
                -- there so the row's own Show()/SetAlpha(1)/EnableMouse(true)
                -- sticks instead of being undone the next time this same
                -- button (now a key) fires OnShow.
                if self.fsBezelOwned then return end
                self:Hide()
                self:SetAlpha(0)
            end)
            frame.fsHideHooked = true
        end
    end)
end

-- Player, 2026-09-2X: "weird circles" on the minimap, and separately "looks
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
-- this file's own chrome-adding functions (ApplyHighlight/
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
    -- reparented minimap-button key (see AdoptBlizzardKey) outright -- only a
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
                -- minimap-button keys AdoptBlizzardKey may reparent into the key
                -- row later in Apply() (ApplyControlBezel runs AFTER this
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

    -- Blizzard's own coords, which our bezel LCD already renders (see ApplyReadout),
    -- and its clock, which the player does not want on the minimap at all (the data
    -- bar has the time). Leaving the coords up shows them twice.
    --
    -- Both paths are MEASURED, not guessed. PlayerCoords is a parentKey frame
    -- on MinimapCluster.MinimapContainer per Blizzard_Minimap/Mainline/
    -- Minimap.xml on the `forever` branch (MinimapContainer at line 186,
    -- PlayerCoords at 425); MinimapContainer is confirmed present in the
    -- 2026-09-19 inspect dump. TimeManagerClockButton is confirmed in the 16001
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
    -- matches .DielFrame in the 2026-09-19 inspect dump.
    --
    -- Keep .Tracking, .InstanceDifficulty, and .ZoneTextButton available;
    -- only the native zone FontString is hidden above.
    if MinimapCluster then
        HideIfExists(MinimapCluster.DielFrame)
    end

    -- Generic atlas-substring sweep, additive to every named lookup above.
    -- See StripStrayMinimapArt's own comment for the full "weird circles"
    -- rationale. Must run from here (not later in Apply()) so it fires
    -- before ApplyHighlight/ApplyPlayerBlipGlow/ApplyScanline
    -- have created any of our own textures.
    StripStrayMinimapArt()
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
-- Pixel geometry of the body's rows
-------------------------------------------------------------------------------

-- Pixel crisp, as MicroBars' icon pieces are: snapped to the pixel grid with no texel bias, where the client has the calls.
local function Crisp(texture)
    if texture.SetSnapToPixelGrid then pcall(texture.SetSnapToPixelGrid, texture, true) end
    if texture.SetTexelSnappingBias then pcall(texture.SetTexelSnappingBias, texture, 0) end
    return texture
end

-- A flat colour texture, pixel crisp.
local function Flat(frame, layer, sublevel, color, alpha)
    local texture = frame:CreateTexture(nil, layer, nil, sublevel)
    texture:SetColorTexture(color[1], color[2], color[3], alpha or color[4] or 1)
    return Crisp(texture)
end

-- UI units per physical pixel at `frame`; one unit per pixel when the client will not say (every edge then sits on a whole
-- UI unit instead of a whole pixel). FS.FrameHelpers loads before this file but is read at call time, like everywhere else.
local function PixelUnit(frame)
    local helpers = FS.FrameHelpers
    local px = helpers and helpers.PixelUnit and helpers.PixelUnit(frame)
    if type(px) ~= "number" or px ~= px or px <= 0 then return 1 end
    return px
end

-- `n` raised by one when its parity differs from `ref`'s: a glyph centres on whole pixels only on a key of the same parity.
local function Like(n, ref)
    if (n - ref) % 2 ~= 0 then return n + 1 end
    return n
end

-- The rows' geometry for the pixel scale the map has now, as whole pixel counts (SPEC above, the mockup's px / 2 scaled by the
-- map's physical width over REF_MAP and rounded); g.px turns a count into UI units. Nothing here is cached: a UI scale or
-- resolution change moves the pixel, and every Seat* function below runs again on it.
local function Geo(frame)
    local px = PixelUnit(frame or Minimap)
    local width = (Minimap and Minimap.GetWidth and Minimap:GetWidth()) or Metrics.map
    local k = width / px / REF_MAP
    local function S(n) return math.max(1, math.floor(n * k + 0.5)) end

    local g = { px = px, k = k, width = math.floor(width / px + 0.5) }
    g.row = S(SPEC.row)
    g.keyW = S(SPEC.keyW)
    g.keyH = math.min(Like(S(SPEC.keyH), g.row), g.row)
    g.topM = (g.row - g.keyH) / 2
    g.margin = S(SPEC.margin)
    g.keyGap = S(SPEC.keyGap)
    g.pitch = g.keyW + g.keyGap
    g.led = S(SPEC.led)
    g.glyph = Like(S(SPEC.glyph), g.keyW)
    g.glyphGap = S(SPEC.glyphGap)
    g.glyphY = math.max(0, g.keyH - g.led - g.glyphGap - g.glyph)
    g.stu = Like(S(SPEC.stu), g.keyW)
    g.stuX = (g.keyW - g.stu) / 2
    g.stuGap = S(SPEC.stuGap)
    g.stuY = math.floor(g.keyH - g.led - g.stuGap - STU_INK_BOTTOM * g.stu + 0.5)
    g.coords = S(SPEC.coords)
    g.count = S(SPEC.count)
    g.dividerH = math.min(Like(S(SPEC.dividerH), g.row), g.row)
    g.chevW = S(SPEC.chevW)
    g.chevH = S(SPEC.chevH)
    g.outlineX = S(SPEC.outline)
    g.outlineY = math.max(1, math.min(math.floor(g.topM), S(1)))
    g.halo = S(SPEC.halo)
    g.dash = S(SPEC.dash)
    g.ruleInset = S(SPEC.ruleInset)
    g.edge = 1 -- the body's edge and the rules: one pixel
    return g
end

-------------------------------------------------------------------------------
-- The body: one edge, one plate, from the map's top to the last row's bottom
-------------------------------------------------------------------------------

-- Where the pieces live: our own handles, never fields on a Blizzard frame.
local Body = {}

-- The chamfer in pixels, or 0 when the cut chrome is off (the body is then square).
local function BodyCut()
    if FS.Theme.CHROME_CORNERS ~= "cut" then return 0 end
    return BODY_CHAMFER
end

-- Texcoords (L, R, T, B) of a baked cut piece of chamfer c: every piece is a 16 x 16 canvas with the piece at the top-left
-- (Theme.CUT_SIZES), so the bottom-right corner reads the same piece flipped both ways.
local function CutCoords(corner, c)
    local k = c / 16
    if corner == "TOPLEFT" then return 0, k, 0, k end
    return k, 0, k, 0
end

-- The body frame and everything on it that does not move with a row: the outer glow, the plate, the edge, the map's rule.
-- The frame spans the map's top to the last row's bottom (SeatBody picks the row), a child of the bezel so the diagnostics'
-- minimap bounds file it as custom furniture, at +1 over the bezel so the divider and the keys sit over the plate. The edge is
-- a flat 1 px line round the rectangle plus one baked diagonal piece at each cut corner, at full alpha all round (the shared
-- AddGradientBorder fades its top edge to a third, which reads as an edge on the map's top only; the mockup's is one even cyan).
local function BuildBody(bezel)
    local Theme = FS.Theme
    local body = CreateFrame("Frame", nil, bezel)
    body:SetFrameLevel(bezel:GetFrameLevel() + BODY_LEVEL_OFFSET)
    body:SetPoint("TOPLEFT", Minimap, "TOPLEFT", 0, 0)
    body:SetPoint("BOTTOMRIGHT", bezel, "BOTTOMRIGHT", 0, 0)

    if AddOuterGlow then
        AddOuterGlow(body, COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], GLOW_SIZE, GLOW_ALPHA,
            BodyCut() > 0 and BODY_CHAMFER or 0)
    end

    local p = {}
    -- The plate: all of it under the map's bottom edge, as three flat rectangles and one baked triangle at the bottom-right cut,
    -- which tile without overlap so the translucent plate keeps one alpha.
    p.plate = Flat(body, "BACKGROUND", -8, BODY_PLATE)
    p.plateFoot = Flat(body, "BACKGROUND", -8, BODY_PLATE)
    p.plateCorner = body:CreateTexture(nil, "BACKGROUND", nil, -8)
    p.plateCorner:SetTexture(Theme.FILL_CUT_TEXTURES[BODY_CHAMFER])
    p.plateCorner:SetVertexColor(BODY_PLATE[1], BODY_PLATE[2], BODY_PLATE[3], BODY_PLATE[4])
    p.plateCorner:SetTexCoord(CutCoords("BOTTOMRIGHT", BODY_CHAMFER))

    -- The edge.
    p.top = Flat(body, "BORDER", 0, BODY_EDGE)
    p.bottom = Flat(body, "BORDER", 0, BODY_EDGE)
    p.left = Flat(body, "BORDER", 0, BODY_EDGE)
    p.right = Flat(body, "BORDER", 0, BODY_EDGE)
    local file = Theme.BORDER_CUT_TEXTURES[BODY_CHAMFER][1]
    for _, corner in ipairs({ "TOPLEFT", "BOTTOMRIGHT" }) do
        local piece = body:CreateTexture(nil, "BORDER")
        piece:SetTexture(file)
        piece:SetVertexColor(BODY_EDGE[1], BODY_EDGE[2], BODY_EDGE[3], 1)
        piece:SetTexCoord(CutCoords(corner, BODY_CHAMFER))
        p[corner == "TOPLEFT" and "cutTL" or "cutBR"] = piece
    end

    -- The rule where the map meets the first row.
    p.rule = Flat(body, "BORDER", 1, BODY_RULE)

    Body.frame, Body.pieces = body, p
    Minimap.fsBody = body
    return body
end

-- Sizes and seats the body's pieces for the pixel scale now: the chamfer and the edge are whole pixels (the baked pieces draw one
-- texel a pixel, so a piece sized in pixels is never resampled).
local function SeatBodyPieces(g)
    local body, p = Body.frame, Body.pieces
    if not (body and p) then return end
    local px = g.px
    local c = BodyCut()
    local cu, t = c * px, g.edge * px

    p.plate:ClearAllPoints()
    p.plate:SetPoint("TOPLEFT", Minimap, "BOTTOMLEFT", 0, 0)
    p.plate:SetPoint("BOTTOMRIGHT", body, "BOTTOMRIGHT", 0, cu)
    p.plateFoot:ClearAllPoints()
    p.plateFoot:SetPoint("BOTTOMLEFT", body, "BOTTOMLEFT", 0, 0)
    p.plateFoot:SetPoint("BOTTOMRIGHT", body, "BOTTOMRIGHT", -cu, 0)
    p.plateFoot:SetHeight(math.max(cu, 0.001))
    p.plateCorner:ClearAllPoints()
    p.plateCorner:SetPoint("BOTTOMRIGHT", body, "BOTTOMRIGHT", 0, 0)
    p.plateCorner:SetSize(math.max(cu, 0.001), math.max(cu, 0.001))
    for _, piece in ipairs({ p.plateFoot, p.plateCorner, p.cutTL, p.cutBR }) do
        if c > 0 then piece:Show() else piece:Hide() end
    end

    p.top:ClearAllPoints()
    p.top:SetPoint("TOPLEFT", body, "TOPLEFT", cu, 0)
    p.top:SetPoint("TOPRIGHT", body, "TOPRIGHT", 0, 0)
    p.top:SetHeight(t)
    p.bottom:ClearAllPoints()
    p.bottom:SetPoint("BOTTOMLEFT", body, "BOTTOMLEFT", 0, 0)
    p.bottom:SetPoint("BOTTOMRIGHT", body, "BOTTOMRIGHT", -cu, 0)
    p.bottom:SetHeight(t)
    p.left:ClearAllPoints()
    p.left:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -cu)
    p.left:SetPoint("BOTTOMLEFT", body, "BOTTOMLEFT", 0, 0)
    p.left:SetWidth(t)
    p.right:ClearAllPoints()
    p.right:SetPoint("TOPRIGHT", body, "TOPRIGHT", 0, -t)
    p.right:SetPoint("BOTTOMRIGHT", body, "BOTTOMRIGHT", 0, cu)
    p.right:SetWidth(t)
    for _, corner in ipairs({ "cutTL", "cutBR" }) do
        local piece = p[corner]
        local point = corner == "cutTL" and "TOPLEFT" or "BOTTOMRIGHT"
        piece:ClearAllPoints()
        piece:SetPoint(point, body, point, 0, 0)
        piece:SetSize(math.max(cu, 0.001), math.max(cu, 0.001))
    end

    p.rule:ClearAllPoints()
    p.rule:SetPoint("TOPLEFT", Minimap, "BOTTOMLEFT", 0, 0)
    p.rule:SetPoint("TOPRIGHT", Minimap, "BOTTOMRIGHT", 0, 0)
    p.rule:SetHeight(t)
end

-- The body ends at the last row: the tray's drawer while it is open, else the key row. A drawer that is not shown leaves the
-- body at the bezel's bottom edge, so a closed tray costs the body nothing.
local function SeatBody()
    local body, bezel = Minimap and Minimap.fsBody, Minimap and Minimap.fsBezel
    if not (body and bezel) then return end
    local last = bezel
    local drawer = Minimap.fsTray
    if drawer and drawer.IsShown and drawer:IsShown() then last = drawer end
    body:ClearAllPoints()
    body:SetPoint("TOPLEFT", Minimap, "TOPLEFT", 0, 0)
    body:SetPoint("BOTTOMRIGHT", last, "BOTTOMRIGHT", 0, 0)
end

-------------------------------------------------------------------------------
-- Keys: a bare glyph, an LED underline, a hover outline
-------------------------------------------------------------------------------

-- Everything on a key frame that this file adds, by frame, so no field is written to a Blizzard button for it: the LED
-- underline, the wash behind a bright LED, the hover outline, the glyph, and the two flags that paint them (over: the mouse is
-- on it; lit: it is held bright, the open tray's toggle).
local Keys = {}

-- The key row's keys in seat order (st.order), tracking, calendar, STU, tray toggle, mail: tables from Keys.
local Row = { keys = {} }

local function AddRowKey(st)
    local keys = Row.keys
    local at = #keys + 1
    for i, other in ipairs(keys) do
        if other.order > st.order then at = i break end
    end
    table.insert(keys, at, st)
end

-- LED, wash and outline on `frame`, in the accent colour. Seated by SeatKeyChrome.
local function AddKeyChrome(frame, accent, kind)
    local st = { frame = frame, accent = accent, kind = kind }
    st.wash = Flat(frame, "OVERLAY", 1, accent, LED_WASH_ALPHA)
    st.wash:Hide()
    st.led = Flat(frame, "OVERLAY", 2, accent, 1)
    st.led:SetAlpha(LED_REST_ALPHA)
    st.outline = frame:CreateTexture(nil, "OVERLAY", nil, 3)
    st.outline:SetVertexColor(accent[1], accent[2], accent[3], 1)
    st.outline:Hide()
    Keys[frame] = st
    return st
end

-- The glyph texture of a key, white shapes tinted by `tint`.
local function AddGlyph(frame, texture, tint)
    local glyph = Crisp(frame:CreateTexture(nil, "ARTWORK", nil, 1))
    glyph:SetTexture(texture)
    if tint then glyph:SetVertexColor(tint[1], tint[2], tint[3], 1) end
    return glyph
end

-- Rest, hover or held bright, from the two flags: the LED at .75 or 1, the wash behind it only when bright, the outline only
-- under the mouse. Texture writes only. A key hidden with the mouse on it gets no OnLeave, so OnHide clears over.
local function PaintKey(frame)
    local st = Keys[frame]
    if not st then return end
    local bright = (st.over or st.lit) and true or false
    st.led:SetAlpha(bright and 1 or LED_REST_ALPHA)
    if bright then st.wash:Show() else st.wash:Hide() end
    if st.over and not st.noOutline then st.outline:Show() else st.outline:Hide() end
end

-- LED along the bottom of the key at its full width, the wash round it, the hover outline round the key (chamfered at the baked
-- ring the buttons use, one pixel wide, `outlineX` out at the sides and `outlineY` above and below).
local function SeatKeyChrome(st, g)
    local frame, px = st.frame, g.px
    st.led:ClearAllPoints()
    st.led:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 0, 0)
    st.led:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)
    st.led:SetHeight(g.led * px)
    st.wash:ClearAllPoints()
    st.wash:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", -g.halo * px, -g.halo * px)
    st.wash:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", g.halo * px, -g.halo * px)
    st.wash:SetHeight((g.led + 2 * g.halo) * px)

    local Theme = FS.Theme
    if Theme.Cut2ButtonSet and Theme.ApplyNineSlice then
        local ring, _, c = Theme.Cut2ButtonSet(g.outlineX)
        st.outline:SetTexture(ring)
        st.noOutline = not Theme.ApplyNineSlice(st.outline, c)
    else
        st.noOutline = true
    end
    st.outline:ClearAllPoints()
    st.outline:SetPoint("TOPLEFT", frame, "TOPLEFT", -g.outlineX * px, g.outlineY * px)
    st.outline:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", g.outlineX * px, -g.outlineY * px)
end

-- Hover on a key we do not own the scripts of (Blizzard's tracking, calendar and mail keys, an addon's tile): a post-hook, so its
-- own tooltip stays. `extra` is the frame that actually takes the mouse when the key is a container (the tracking frame's own button).
local function WireHover(frame, extra)
    local function over(on)
        local st = Keys[frame]
        if st then
            st.over = on
            PaintKey(frame)
        end
    end
    for _, target in ipairs({ frame, extra or false }) do
        if target and target.HookScript then
            pcall(target.HookScript, target, "OnEnter", function() over(true) end)
            pcall(target.HookScript, target, "OnLeave", function() over(false) end)
            pcall(target.HookScript, target, "OnHide", function() over(false) end)
        end
    end
end

-- Seats one key's glyph in its frame for the pixel scale now: a 16 px box on the glyph row of the key, centred across it; the STU
-- icon's 32 px canvas centred across it and hung so its ink ends SPEC.stuGap above the LED (the art is a taller block than a
-- glyph and rises past the key's top, into the row's margin).
local function SeatKeyGlyph(st, g)
    local glyph, frame, px = st.glyph, st.frame, g.px
    if not glyph then return end
    glyph:ClearAllPoints()
    if st.kind == "stu" then
        glyph:SetSize(g.stu * px, g.stu * px)
        glyph:SetPoint("TOPLEFT", frame, "TOPLEFT", g.stuX * px, -g.stuY * px)
    else
        glyph:SetSize(g.glyph * px, g.glyph * px)
        glyph:SetPoint("TOPLEFT", frame, "TOPLEFT", (g.keyW - g.glyph) / 2 * px, -g.glyphY * px)
    end
end

-- Mail's dot (see AddMailDot): a 6 px dot at the key's top-right corner and its soft halo.
local function SeatMailDot(frame, g)
    local px = g.px
    if not (mailDot.core and mailDot.halo) then return end
    local size = math.max(3, math.floor(KEY_DOT_SIZE * g.k + 0.5)) * px
    local reach = KEY_DOT_GLOW_REACH * px
    mailDot.core:ClearAllPoints()
    mailDot.core:SetSize(size, size)
    mailDot.core:SetPoint("TOPRIGHT", frame, "TOPRIGHT", KEY_DOT_OFFSET * px, KEY_DOT_OFFSET * px)
    mailDot.halo:ClearAllPoints()
    mailDot.halo:SetSize(size + 2 * reach, size + 2 * reach)
    mailDot.halo:SetPoint("CENTER", mailDot.core, "CENTER", 0, 0)
end

-- The tray toggle's count and chevron: the chevron against the key's right (one pixel in), the count's right edge a 3 px gap
-- left of it, both centred on the glyph row. One digit fills the key (about 5.6 + 3 + 8 of its 18 px at the mockup's 10 px
-- font); two digits grow leftward into the key gap, which is wider than what they overshoot by.
local function SeatToggleContent(st, g)
    local toggle, px = st.frame, g.px
    local mid = -(g.glyphY + g.glyph / 2) * px
    if toggle.chevron then
        toggle.chevron:ClearAllPoints()
        toggle.chevron:SetSize(g.chevW * px, g.chevH * px)
        toggle.chevron:SetPoint("RIGHT", toggle, "TOPRIGHT", -px, mid)
    end
    if toggle.count and toggle.chevron then
        if toggle.fsCountPx ~= g.count then
            toggle.fsCountPx = g.count
            ApplyMono(toggle.count, g.count * px, COLOR_AMBER)
        end
        toggle.count:ClearAllPoints()
        toggle.count:SetPoint("RIGHT", toggle.chevron, "LEFT", -g.glyphGap * px, 0)
    end
end

-- Seats one key: its size and place (slot `slot` of the row, 0 when it is not in the row), its chrome and its glyph.
local function SeatKey(st, bezel, g, slot)
    local frame, px = st.frame, g.px
    frame:SetSize(g.keyW * px, g.keyH * px)
    if slot then
        frame:ClearAllPoints()
        frame:SetPoint("TOPLEFT", bezel, "TOPLEFT", (g.margin + (slot - 1) * g.pitch) * px, -g.topM * px)
    end
    -- The hit box reaches a half gap each side and the row's margin above and below, so no pixel between two keys is dead.
    if frame.SetHitRectInsets then
        pcall(frame.SetHitRectInsets, frame, -g.keyGap / 2 * px, -g.keyGap / 2 * px, -g.topM * px, -g.topM * px)
    end
    SeatKeyChrome(st, g)
    SeatKeyGlyph(st, g)
    if st.kind == "mail" then
        local icon = st.icon
        if icon then
            local w = g.glyph
            icon:ClearAllPoints()
            icon:SetSize(w * px, math.floor(w * 3 / 4 + 0.5) * px)
            icon:SetPoint("CENTER", frame, "TOPLEFT", g.keyW / 2 * px, -(g.glyphY + g.glyph / 2) * px)
        end
        SeatMailDot(frame, g)
    elseif st.kind == "toggle" then
        SeatToggleContent(st, g)
    end
end

local function KeyShown(st)
    local ok, shown = pcall(st.frame.IsShown, st.frame)
    return ok and shown ~= false
end

-- The divider and the coords: a divider one key gap after the last key showing, a 1 px line, centred in the row; the coords right
-- aligned at the margin, as large as the room between the divider and the right margin takes up to SPEC.coords.
local function SeatDividerAndCoords(bezel, g, shownCount)
    local px = g.px
    local dividerX = g.margin + shownCount * g.pitch
    local divider = Row.divider
    if divider then
        divider:ClearAllPoints()
        divider:SetPoint("TOPLEFT", bezel, "TOPLEFT", dividerX * px, -(g.row - g.dividerH) / 2 * px)
        divider:SetSize(g.edge * px, g.dividerH * px)
    end
    local coords = Minimap.fsReadoutCoords
    if coords then
        local room = g.width - g.margin - (dividerX + g.edge + g.keyGap)
        local font = math.max(5, math.min(g.coords, math.floor(room / (COORDS_CHARS * COORDS_ADVANCE))))
        if coords.fsFontPx ~= font then
            coords.fsFontPx = font
            ApplyMono(coords, font * px, COLOR_POWER)
        end
        coords:ClearAllPoints()
        coords:SetPoint("RIGHT", bezel, "RIGHT", -g.margin * px, 0)
    end
end

local seating = false -- SeatRow is running (a Show/Hide hook it provokes must not run it again)

-- Seats the whole key row for the pixel scale now: the bezel's height, every key in the next free slot (a key that is not
-- showing takes none, so the row has no hole), the divider, the coords, and the body's pieces. Run at build, whenever a key
-- joins or leaves the row, and on every rescale.
local function SeatRow()
    local bezel = Minimap and Minimap.fsBezel
    if not bezel or seating then return end
    seating = true
    local g = Geo(bezel)
    bezel:SetHeight(g.row * g.px)
    local slot = 0
    for _, st in ipairs(Row.keys) do
        local shown = KeyShown(st)
        if shown then slot = slot + 1 end
        local ok, err = pcall(SeatKey, st, bezel, g, shown and slot or nil)
        if not ok and FS.LogDegradeOnce then
            FS.LogDegradeOnce("minimap_key_" .. tostring(st.kind),
                "|cffff4488Forever STUwave|r: minimap key degraded (" .. tostring(st.kind) .. "): " .. tostring(err))
        end
    end
    pcall(SeatDividerAndCoords, bezel, g, slot)
    pcall(SeatBodyPieces, g)
    SeatBody()
    seating = false
end

if FS.Layout and FS.Layout.OnRescale then
    FS.Layout.OnRescale(SeatRow)
end

-------------------------------------------------------------------------------
-- The keys: Blizzard's three (tracking, calendar, mail) and ours (STU, the tray's toggle)
-------------------------------------------------------------------------------

-- Blanks every texture and string a Blizzard key draws by itself (icon, plate art, date number, highlight): the key is a bare
-- glyph of ours over an LED, so what the stock button paints would show through it. Alpha only, and run once at build, before
-- our own regions exist on the frame (it would blank those too).
local function QuietRegions(frame)
    if type(frame) ~= "table" or not frame.GetRegions then return end
    local ok, regions = pcall(function() return { frame:GetRegions() } end)
    if not ok then return end
    for _, region in ipairs(regions) do
        pcall(region.SetAlpha, region, 0)
    end
end

-- The named plate regions of a stock key, alpha 0 (MicroBars' StripButtonArt idiom). The mail key keeps its envelope, which is
-- its own texture, so it takes this and not QuietRegions.
local function StripKeyArt(button)
    if not button then return end
    for _, key in ipairs({ "Border", "Background" }) do
        local region = button[key]
        if region and region.SetAlpha then region:SetAlpha(0) end
    end
end

-- Blizzard's button becomes a key of the row: ours to seat, size and skin, on the bezel, over the body. It is marked
-- fsBezelOwned before anything else runs: HideBlizzardChrome's OnShow re-hide hook (HideIfExists) skips a frame carrying it, so
-- the Show below sticks. `restore` brings back a key HideBlizzardChrome hid (tracking, calendar); the mail key keeps whatever
-- shown state Blizzard gave it, because it is there only while mail waits.
local function AdoptBlizzardKey(bezel, frame, restore)
    frame.fsBezelOwned = true
    frame:SetParent(bezel)
    if frame.SetFrameLevel and bezel.GetFrameLevel then
        frame:SetFrameLevel(bezel:GetFrameLevel() + KEY_LEVEL_OFFSET)
    end
    frame:ClearAllPoints()
    if restore then frame:Show() end
    frame:SetAlpha(1)
    if frame.EnableMouse then frame:EnableMouse(true) end
end

-- A key that shows or hides (mail, the tray toggle) takes a slot or gives it back, so the row seats again.
local function WireVisibility(frame)
    if not frame.HookScript then return end
    pcall(frame.HookScript, frame, "OnShow", function() SeatRow() end)
    pcall(frame.HookScript, frame, "OnHide", function() SeatRow() end)
end

-- A key's own mouse state: over, and the tooltip when it has one. Scripts set on keys that are ours.
local function SetOver(frame, on)
    local st = Keys[frame]
    if not st then return end
    st.over = on and true or false
    PaintKey(frame)
end

local function ShowTip(owner, anchor, text)
    if not GameTooltip then return end
    pcall(function()
        GameTooltip:SetOwner(owner, anchor)
        GameTooltip:SetText(text)
        GameTooltip:Show()
    end)
end

local function HideTip()
    if GameTooltip then pcall(function() GameTooltip:Hide() end) end
end

local function LogKeyFailure(id, err)
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("minimap_key_" .. id,
            "|cffff4488Forever STUwave|r: minimap key degraded (" .. id .. "): " .. tostring(err))
    end
end

-- Tracking (cyan): the stock tracking frame, its button the one that takes the mouse and opens the menu. Our magnifier glyph
-- replaces its icon; the button is pinned to the key so the whole key is its hit area.
local function BuildTrackingKey(bezel)
    local frame = MinimapCluster and MinimapCluster.Tracking
    if not frame then return nil end
    AdoptBlizzardKey(bezel, frame, true)
    local button = type(frame.Button) == "table" and frame.Button or nil
    QuietRegions(frame)
    QuietRegions(button)
    if button and button.SetAllPoints then
        pcall(function()
            button:ClearAllPoints()
            button:SetAllPoints(frame)
        end)
    end
    local st = AddKeyChrome(frame, COLOR_POWER, "tracking")
    st.order = 1
    st.glyph = AddGlyph(frame, SEARCH_TEXTURE, COLOR_POWER)
    WireHover(frame, button)
    WireVisibility(frame)
    AddRowKey(st)
    return frame
end

-- Calendar (violet): the stock calendar button, its sun and date number blanked, our calendar glyph in their place.
local function BuildCalendarKey(bezel)
    local frame = GameTimeFrame
    if not frame then return nil end
    AdoptBlizzardKey(bezel, frame, true)
    QuietRegions(frame)
    local st = AddKeyChrome(frame, COLOR_BORDER, "calendar")
    st.order = 2
    st.glyph = AddGlyph(frame, CALENDAR_TEXTURE, COLOR_BORDER)
    WireHover(frame)
    WireVisibility(frame)
    AddRowKey(st)
    return frame
end

-- The STU key (pink): ours, it replaces the stock gold gear and does its job, opening the config window (the one /fsconfig
-- toggles), so the player does not need the slash command. The icon is the STUwave mark (generate_icon_stu.py) in colour,
-- on a canvas larger than the key (SeatKeyGlyph). Nothing here is secure: the build, the looks and the click are all legal in
-- combat. The click reads FS.ConfigWindow at click time (ConfigWindow.lua loads after this file) and does nothing while it is
-- absent.
local function BuildSTUKey(bezel)
    local key = CreateFrame("Button", STU_KEY_NAME, bezel)
    local ok, err = pcall(function()
        key:SetFrameLevel(bezel:GetFrameLevel() + KEY_LEVEL_OFFSET)
        local st = AddKeyChrome(key, COLOR_PINK, "stu")
        st.order = 3
        st.glyph = AddGlyph(key, STU_TEXTURE)
        key:RegisterForClicks("LeftButtonUp")
        key:SetScript("OnEnter", function(self)
            SetOver(self, true)
            ShowTip(self, "ANCHOR_BOTTOM", "Settings")
        end)
        key:SetScript("OnLeave", function(self)
            SetOver(self, false)
            HideTip()
        end)
        -- A key hidden with the mouse on it gets no OnLeave.
        key:SetScript("OnHide", function(self) SetOver(self, false) end)
        key:SetScript("OnClick", function()
            local window = FS.ConfigWindow
            if window and window.Toggle then window.Toggle() end
        end)
        AddRowKey(st)
    end)
    if not ok then
        key:Hide()
        LogKeyFailure("stu", err)
        return nil
    end
    Minimap.fsSTUKey = key
    return key
end

-- Mail (pink). The notification dot is a SEPARATE round texture (glow_round.tga, the same radial falloff the player-blip glow
-- uses) at the key's top-right corner, plus a wider halo behind it for the glow. Both are textures OWNED by MailFrame, so they
-- show and hide with the FRAME, with no hook or event of ours. That is not the same as showing with the envelope: in Blizzard
-- 12.1 the envelope is shown only when the arrival animation finishes (see BuildMailKey), so for about 0.4 to 0.5 s after mail
-- arrives the dot shows alone. They are drawn on OVERLAY (the dot a sublevel above its halo) so they sit over the envelope; the
-- handles live in the module-local mailDot, not on the Blizzard frame. Sized and seated by SeatMailDot.
local function AddMailDot(frame)
    if mailDot.core or not frame.CreateTexture then return end

    local core = frame:CreateTexture(nil, "OVERLAY", nil, 7)
    core:SetTexture(GLOW_ROUND_TEXTURE)
    core:SetBlendMode("ADD")
    core:SetVertexColor(COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], 1)

    local halo = frame:CreateTexture(nil, "OVERLAY", nil, 6)
    halo:SetTexture(GLOW_ROUND_TEXTURE)
    halo:SetBlendMode("ADD")
    halo:SetVertexColor(COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], KEY_DOT_GLOW_ALPHA)

    mailDot.core, mailDot.halo = core, halo
end

-- Mail is a two-part detect: MinimapCluster.IndicatorFrame.MailFrame is the actual clickable button, reparented and skinned
-- like any other key, and MiniMapMailIcon is Blizzard's own unread-mail texture (a child of MailFrame, hidden="true" in its
-- XML). The ICON does not show and hide with the mail state by itself; verified against Blizzard_Minimap/Mainline/Minimap.lua
-- (12.1):
--   * MiniMapMailFrameMixin:OnEvent Shows or Hides the FRAME and starts the NewMailAnim (0.5 s) or MailReminderAnim (0.4 s)
--     flipbook;
--   * MinimapMailAnimMixin:OnPlay hides the icon and :OnFinished shows it (HasNewMail());
--   * MiniMapMailFrameMixin:OnHide runs ResetMailIcon, which hides it again.
-- So the envelope appears only once the arrival animation ends, and the notification dot (AddMailDot) shows alone for that
-- 0.4 to 0.5 s. No unread-tracking logic is built here. The icon is seated CENTRED on the glyph row at the same width as the
-- other keys' glyphs (4:3 like the 20 x 15 MailFrame) and tinted pink. Blizzard's own NewMailFlipbook / MailReminderFlipbook are
-- anchored to this texture, so the arrival animation plays around the middle of the key. Nothing in MiniMapMailFrameMixin
-- moves the icon again: OnEvent only Show/Hides the frame, plays the animation and calls GetParent():Layout() (a no-op on the
-- bezel, see ApplyControlBezel). The frame is shown by Blizzard only while mail waits, which is when the key takes its slot.
local function BuildMailKey(bezel)
    local icon = MiniMapMailIcon
    local frame = MinimapCluster and MinimapCluster.IndicatorFrame and MinimapCluster.IndicatorFrame.MailFrame
    if not (icon and frame) then return nil end

    AdoptBlizzardKey(bezel, frame, false)
    StripKeyArt(frame)
    icon:SetParent(frame)
    icon:SetVertexColor(COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], 1)

    local st = AddKeyChrome(frame, COLOR_PINK, "mail")
    st.order = 5
    st.icon = icon
    AddMailDot(frame)
    WireHover(frame)
    WireVisibility(frame)
    AddRowKey(st)
    return frame
end

-------------------------------------------------------------------------------
-- Coords readout
-------------------------------------------------------------------------------

-- The highest number a coordinate may show. A position of 1.0 would format as "100.0", a glyph wider per
-- axis than the "99.9, 99.9" the readout is budgeted for (see COORDS_CHARS), so each axis is clamped to this.
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

local function UpdateReadout()
    if not (Minimap and Minimap.fsReadoutCoords) then return end

    -- No position inside an instance (a battleground, a dungeon): dashes keep the readout looking on, not broken
    -- (player, Warsong Gulch 2026-11-05: an empty half box "looks weird").
    local coords = GetCoordsText()
    Minimap.fsReadoutCoords:SetText(coords or "--.-, --.-")
    Minimap.fsReadoutCoords:SetAlpha(coords and 1 or 0.45)
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

-- The coords: a divider and the readout, right aligned in the key row, on the body (SeatDividerAndCoords seats them for the
-- keys showing). Requires the bezel and body to already exist (ApplyControlBezel). Text only: no box of its own, the body is the
-- plate. The readout's size is fitted when it is seated, so it is created at the nominal one.
local function ApplyReadout()
    if not Minimap or Minimap.fsReadout then return end
    local body, bezel = Body.frame, Minimap.fsBezel
    if not (body and bezel) then return end
    if not ApplyMono then return end

    Row.divider = Flat(body, "BORDER", 2, COLOR_POWER, DIVIDER_ALPHA)
    local coords = body:CreateFontString(nil, "OVERLAY")
    ApplyMono(coords, SPEC.coords, COLOR_POWER)
    coords:SetJustifyH("RIGHT")

    Minimap.fsReadoutCoords = coords
    Minimap.fsReadout = true

    SeatRow()
    StartReadoutUpdater()
end

-- Builds the body and the key row below Minimap: the bezel frame (the row: Minimap.fsBezel, what the quest timer and the
-- queue eye seat on), the body round the map and the rows, and the keys (tracking, calendar, STU, mail; the tray's toggle joins
-- from ApplyMinimapTray). Every Blizzard button lookup is feature-detected by its real (measured) name, a missing one or a
-- throw is skipped and costs no slot, per key. fsBezel is the sole idempotency guard since Apply() only ever runs this once.
local function ApplyControlBezel()
    if not Minimap or Minimap.fsBezel then return end
    if not (FS.Theme.FILL_CUT_TEXTURES and FS.Theme.BORDER_CUT_TEXTURES) then return end

    local bezel = CreateFrame("Frame", nil, Minimap)
    bezel:SetPoint("TOPLEFT", Minimap, "BOTTOMLEFT", 0, 0)
    bezel:SetPoint("TOPRIGHT", Minimap, "BOTTOMRIGHT", 0, 0)
    local g = Geo(bezel)
    bezel:SetHeight(g.row * g.px)

    -- Adopting Blizzard minimap buttons reparents them onto this frame, and two of them call Layout() on whatever their parent
    -- is when their state changes. Verified against Blizzard_Minimap/Mainline/Minimap.lua on the `forever` client branch:
    --   MiniMapMailFrameMixin:OnEvent          -> self:GetParent():Layout()  (466)
    --   MiniMapCraftingOrderFrameMixin:OnEvent -> self:GetParent():Layout()  (538)
    -- Their real parent is MinimapCluster, a LayoutFrame; ours is a plain Frame, so the call hit nil and threw inside
    -- BLIZZARD's file the first time mail arrived, which reads as a Blizzard bug and is ours.
    --
    -- A no-op is the correct body, not a stub: SeatRow positions every key explicitly, so there is no layout pass to run. This
    -- only has to not throw.
    bezel.Layout = function() end

    Minimap.fsBezel = bezel

    local ok, err = pcall(BuildBody, bezel)
    if not ok then LogKeyFailure("body", err) end

    local resolved, skipped = {}, {}
    local function TryKey(id, build)
        local okKey, built = pcall(build, bezel)
        if okKey and built then
            resolved[#resolved + 1] = id
            return
        end
        skipped[#skipped + 1] = id
        if not okKey then LogKeyFailure(id, built) end
    end

    TryKey("tracking", BuildTrackingKey)
    TryKey("calendar", BuildCalendarKey)
    TryKey("stu", BuildSTUKey)
    TryKey("mail", BuildMailKey)

    -- Kept on Minimap for an in-game /dump-driven sanity check of which keys resolved; not read by any other code path in this
    -- file.
    Minimap.fsBezelResolved = resolved
    Minimap.fsBezelSkipped = skipped

    SeatRow()
end

-------------------------------------------------------------------------------
-- Addon-button tray (collects LibDBIcon + stray minimap buttons)
-------------------------------------------------------------------------------

-- Player: "any addons that are loaded and would normally put icons around the minimap need
-- to be moved to the tray ... so it doesn't clutter our awesome ui. Also I never saw a button
-- to pop out the tray."
--
-- THE DRAWER is the body's SECOND ROW (mockup A, open): a frame under the key row with no
-- box of its own (the body's plate and edge run on round it, SeatBody), a dashed amber rule
-- along its top, and the collected buttons as keys, each with the LED underline. They seat on
-- the key row's own columns (SPEC.margin and the key pitch) and wrap into further rows of the
-- key row's height when there are more of them than columns; the drawer's height follows the
-- row count. It is a child of Minimap anchored to the bezel (no FS.Layout seat: the old
-- `minimaptray` Layout entry is unused).
--
-- THE POP-OUT is the key row's fourth key (BuildTrayToggle), not a tab: the number of
-- collected buttons and a chevron, an amber LED that stays bright while the drawer is open. It
-- is placed by SeatRow like every key, and hidden with the drawer at zero buttons.
-- Open/closed lives in ForeverSTUwaveDB.minimapTrayOpen (default closed).
----
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
    entries = {},      -- { button, accent, key, orig = { SetPoint = fn, ... } } in collection order
    byButton = {},
    pending = {},      -- buttons seen in combat, adopted on PLAYER_REGEN_ENABLED
    layoutPending = false,
    relayout = false,  -- re-entry guard (a Show/Hide hook can fire while we lay out)
    count = 0,         -- tiles currently laid out (shown buttons only)
    open = false,
    libHooked = false,
    togglePending = false, -- a drawer show/hide waiting for PLAYER_REGEN_ENABLED
    failureLogged = false,
    dashes = {},       -- the rule's dash textures, made as the width asks for them
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

-- Drawer show/hide, deferred to PLAYER_REGEN_ENABLED when protected buttons ride in it. The body ends at the drawer while it is
-- shown, so it follows the drawer the moment it changes.
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
    SeatBody()
end

local function UpdateToggle()
    local toggle = Minimap and Minimap.fsTrayToggle
    local drawer = Minimap and Minimap.fsTray
    if not (toggle and drawer) then return end
    if toggle.count then toggle.count:SetText(tostring(Tray.count)) end
    if toggle.chevron then
        -- The baked chevron points down (closed); open is the same piece flipped over.
        if Tray.open then toggle.chevron:SetTexCoord(0, 1, 1, 0) else toggle.chevron:SetTexCoord(0, 1, 0, 1) end
    end
    local st = Keys[toggle]
    if st then
        st.lit = Tray.open and true or false
        PaintKey(toggle)
    end
    if Tray.count == 0 then
        toggle:Hide()
        SetDrawerShown(drawer, false)
    else
        toggle:Show()
        SetDrawerShown(drawer, Tray.open)
    end
end

-- The dashed amber rule along the drawer's top edge (mockup: 4 px dashes and gaps at 2x, so 2 px, inset 6 px from each side), a
-- run of flat dashes made as the width asks for them and hidden past the last one.
local function SeatDrawerRule(g)
    local drawer = Minimap and Minimap.fsTray
    if not drawer then return end
    local px = g.px
    local count = math.max(0, math.floor((g.width - 2 * g.ruleInset + g.dash) / (2 * g.dash)))
    for i = 1, count do
        local dash = Tray.dashes[i]
        if not dash then
            dash = Flat(drawer, "BORDER", 1, COLOR_AMBER, RULE_ALPHA)
            Tray.dashes[i] = dash
        end
        dash:ClearAllPoints()
        dash:SetPoint("TOPLEFT", drawer, "TOPLEFT", (g.ruleInset + (i - 1) * 2 * g.dash) * px, 0)
        dash:SetSize(g.dash * px, g.edge * px)
        dash:Show()
    end
    for i = count + 1, #Tray.dashes do Tray.dashes[i]:Hide() end
end

-- A tile's icon: the key's glyph box (16 px, centred across the key, on the glyph row), where the lib's own icon would sit
-- off-centre in a round button.
local function SeatTileIcon(button, g)
    local icon = button.icon or button.Icon
    if not icon then return end
    local isTexture = false
    pcall(function() isTexture = (icon:GetObjectType() == "Texture") end)
    if not isTexture then return end
    local px = g.px
    pcall(function()
        icon:ClearAllPoints()
        icon:SetPoint("TOPLEFT", button, "TOPLEFT", (g.keyW - g.glyph) / 2 * px, -g.glyphY * px)
        icon:SetSize(g.glyph * px, g.glyph * px)
    end)
end

-- The tile's LED, wash and hover outline and its icon, for the pixel scale now.
local function SeatTileChrome(entry, g)
    if entry.key then SeatKeyChrome(entry.key, g) end
    SeatTileIcon(entry.button, g)
end

-- The tiles: key-sized, on the key row's columns (margin, then one key pitch a column), a row of the key row's height each.
-- Columns are whatever whole keys the width takes (9 at the 248 px map).
local function LayoutTiles()
    local drawer = Minimap and Minimap.fsTray
    if not drawer then return end
    local g = Geo(drawer)
    local px = g.px
    local cols = math.max(1, math.floor((g.width - 2 * g.margin + g.keyGap) / g.pitch))

    local n = 0
    for _, entry in ipairs(Tray.entries) do
        if ButtonIsShown(entry.button) then
            local col, row = n % cols, math.floor(n / cols)
            Raw(entry, "SetScale", 1)
            Raw(entry, "SetSize", g.keyW * px, g.keyH * px)
            Raw(entry, "ClearAllPoints")
            Raw(entry, "SetPoint", "TOPLEFT", drawer, "TOPLEFT",
                (g.margin + col * g.pitch) * px, -(row * g.row + g.topM) * px)
            local ok, err = pcall(SeatTileChrome, entry, g)
            if not ok then LogTrayFailure("tile chrome", err) end
            n = n + 1
        end
    end
    Tray.count = n

    drawer:SetHeight(math.max(1, math.ceil(n / cols)) * g.row * px)
    SeatDrawerRule(g)
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

local function NeutralizeHoverFade(button)
    button.showOnMouseover = false
    pcall(function() if button.fadeOut and button.fadeOut.Stop then button.fadeOut:Stop() end end)
    pcall(function() button:SetAlpha(1) end)
end

-- The lib's round highlight replaced by a flat one drawn at no alpha: the hover look is the key's own outline and bright LED
-- (WireHover), and the lib's round art must not show inside the key.
local function ApplyTileHighlight(button)
    pcall(function()
        button:SetHighlightTexture(TRAY_HIGHLIGHT_TEXTURE, "ADD")
        local hl = button.GetHighlightTexture and button:GetHighlightTexture()
        if hl then hl:SetAlpha(0) end
    end)
end

local function AdoptButton(button)
    local drawer = Minimap.fsTray
    local g = Geo(drawer)
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
    Step("icon", function() SeatTileIcon(button, g) end)
    Step("hover", function() NeutralizeHoverFade(button) end)
    -- The tile is a key of the second row: the same LED underline and hover outline in its accent, over whatever the lib drew.
    Step("chrome", function()
        entry.key = AddKeyChrome(button, entry.accent, "tile")
        WireHover(button)
        ApplyTileHighlight(button)
        SeatTileChrome(entry, g)
    end)
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
    local g = Geo(Minimap.fsTray)
    local ok, err = pcall(function()
        StripMinimapButtonArt(button)
        SeatTileIcon(button, g)
        ApplyTileHighlight(button)
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
    local drawer, bezel = Minimap and Minimap.fsTray, Minimap and Minimap.fsBezel
    if not (drawer and bezel) then return end
    drawer:ClearAllPoints()
    drawer:SetPoint("TOPLEFT", bezel, "BOTTOMLEFT", 0, 0)
    drawer:SetPoint("TOPRIGHT", bezel, "BOTTOMRIGHT", 0, 0)
end

-- The toggle, the key row's fourth: the count of collected buttons (amber mono) and a chevron, an amber LED. A Button of ours,
-- hidden until UpdateToggle shows it (a throw below leaves no key in the row), placed by SeatRow like the others. Its
-- chevron is the baked one pointing down; UpdateToggle flips it while the drawer is open.
local function BuildTrayToggle(bezel)
    local toggle = CreateFrame("Button", "ForeverSTUwaveMinimapTrayToggle", bezel)
    toggle:Hide()
    toggle:SetFrameLevel(bezel:GetFrameLevel() + KEY_LEVEL_OFFSET)

    local st = AddKeyChrome(toggle, COLOR_AMBER, "toggle")
    st.order = 4

    local count = toggle:CreateFontString(nil, "OVERLAY")
    ApplyMono(count, SPEC.count, COLOR_AMBER)
    count:SetText("0")
    local chevron = Crisp(toggle:CreateTexture(nil, "ARTWORK", nil, 1))
    chevron:SetTexture(CHEVRON_TEXTURE)
    chevron:SetVertexColor(COLOR_AMBER[1], COLOR_AMBER[2], COLOR_AMBER[3], 1)
    toggle.count = count
    toggle.chevron = chevron

    toggle:SetScript("OnClick", function() SetTrayOpen(not Tray.open) end)
    toggle:SetScript("OnEnter", function(self)
        SetOver(self, true)
        ShowTip(self, "ANCHOR_BOTTOMLEFT", string.format("Addon buttons (%d)", Tray.count))
    end)
    toggle:SetScript("OnLeave", function(self)
        SetOver(self, false)
        HideTip()
    end)
    toggle:SetScript("OnHide", function(self) SetOver(self, false) end)
    WireVisibility(toggle)

    AddRowKey(st)
    return toggle
end

local function BuildTray()
    if not Minimap or Minimap.fsTray then return end
    if not (ApplyMono and Minimap.fsBezel) then return end

    local bezel = Minimap.fsBezel
    local g = Geo(bezel)

    local drawer = CreateFrame("Frame", nil, Minimap)
    drawer:SetFrameLevel(bezel:GetFrameLevel() + DECK_LEVEL_OFFSET)
    drawer:SetHeight(g.row * g.px)
    drawer:SetPoint("TOPLEFT", bezel, "BOTTOMLEFT", 0, 0)
    drawer:SetPoint("TOPRIGHT", bezel, "BOTTOMRIGHT", 0, 0)
    drawer:Hide()

    -- Minimap.fsTray / fsTrayToggle are published only once everything below exists, so a
    -- throw anywhere in here leaves nothing half-wired (BuildTrayToggle hides its frame at
    -- creation, so a failed build leaves no visible key either).
    local toggle = BuildTrayToggle(bezel)

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
    SeatRow()
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
