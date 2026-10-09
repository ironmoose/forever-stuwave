-- Forever STUwave: combat HUD DISPLAY layer over FS.Hud.
--
-- HudSpells -> HudProfiles -> HudLogic decide WHAT to show (FS.Hud.GetState: row, next,
-- buffsMissing, procs, shards, channel, inCombat). This file draws it, around the Stack A cast
-- bars, exactly as mockups/combat-hud-stack-a-2026-10-02.html lays it out (that mockup is the
-- locked design; its units are UIParent units here, the same as CastBars.lua, so nothing is
-- converted). It subscribes to FS.Hud, which pushes only when its change detector fires, so
-- there is no polling and no per-tile OnUpdate. The one OnUpdate is the root frame's, installed
-- only while a cooldown number is counting down, and the work in it runs at most 10 times a
-- second.
--
-- TWO VIEWS. When FS.Gunsight.IsEnabled() is true (the default) this file draws the GUNSIGHT view:
-- only the NEXT tile, the soul shards and the buff reminder, each seated on its FS.Gunsight anchor
-- (anchors.next, anchors.shards, anchors.buff) and registered as a Gunsight piece (`next`, `shard`,
-- `buff`) from inside FS.Gunsight.OnReady, so /fsgun piece can switch it off. Their sizes are the
-- Gunsight mockup's DESIGN px (NEXT 56, buff 24; the shard seat is one 9.5 x 17 glyph and the count) times FS.Layout.Scale(),
-- not the UI-unit table G below, and a rescale re-derives them. Nothing in that view reads a cast
-- bar frame or calls FS.CastBars (the idle row and the rest alpha included), and the Stack A spell
-- row, its cooldown ticker, the per-tile DoT slots (the "target" aura container) and the out of
-- combat dimming are never built. With the Gunsight off (`/fsgun off`, then /reload) everything
-- below runs as the Stack A layout it was written for. The view is decided once, when the UI is
-- first built (CombatHud.IsGunsight()).
--
-- LAYOUT OF THE STACK A VIEW (UIParent units, every frame anchored to the cast bar frames so it follows CastBars
-- when it re-seats the stack; with no cast bars the fixed seat (gap centre (0, -317), 18 gap) is
-- built here and logged):
--   spell row    36 high tiles, 6 apart, centred, its bottom TAB_H (15) + 10 above the target bar
--   next tile    56 x 56, 10 left of the bar column, centred on the 18 gap between the bars
--   shard row    12 high, under the player bar AND its hanging tab (+6), right aligned to the bar
--   buff row     24 tiles, 6 apart, centred, 8 below the shard row (or under the tab with none)
--
-- DOT TIMERS, THE ONLY ROUTE IN COMBAT. Addon aura reads throw while tainted in combat, so a
-- DoT's seconds come from an AuraContainer SLOT (AddAuraSlot): the engine finds the aura and
-- draws its duration text, no aura data ever enters Lua. One container on unit "target", one
-- slot per DoT tile (filter HARMFUL|PLAYER, candidateFilters.includeSpellIDs = the spell's rank
-- ids, banes sharing a group share one slot). The slot frame sits exactly on its tile. Built
-- OUT OF COMBAT only (a tile that appears in a fight gets its slot when the fight ends). A
-- container that cannot be built, a missing template or a throwing AddAuraSlot leaves the tile
-- WITHOUT a timer and logs once; AURA_BUILD_FAIL_LIMIT consecutive container failures give the
-- path up for the session (same shape as the nameplate rows in Nameplates.lua). On a
-- retarget the container needs UpdateAllAuras (SetUnit is a no-op for an unchanged token).
--
-- THE OCCLUSION TRICK, the buff reminders in combat. FS.Hud cannot tell a buff is missing in
-- combat (aura reads are blocked), so it reports nothing. The engine CAN draw the buff, so:
-- for every tracked self buff (aura kind, known spell) a WARNING tile (24 x 24, pulsing pink
-- border) is seated, and an AuraContainer slot for that buff on unit "player" (filter HELPFUL,
-- includeSpellIDs = the buff's rank ids) is stacked ON TOP of it, same rect, higher frame
-- level, opaque icon. While the buff is up its aura icon covers the warning; when it falls
-- off, the slot draws nothing and the warning shows through. No Lua ever learns which. That
-- container is VISIBLE only in combat (out of combat the Hud's own reads are exact and its
-- buffsMissing drives the tiles, and a live slot would draw a stray icon over a hidden tile).
-- Form and pet checks (Shadowform, the pet) are plain in combat, so they come from
-- buffsMissing as usual, with no slot. In the Gunsight view that visibility is ALPHA ONLY: the container is
-- enabled, given its unit and shown OUT OF COMBAT (ArmCover, which also writes alpha 0, after its
-- slots exist, again on PLAYER_REGEN_ENABLED if something left it off) and then never switched in combat, because
-- SetEnabled/Show/Hide on a protected frame in combat is refused and a container that could not be
-- enabled would leave every warning a permanent false alarm. Combat only writes SetAlpha (1 in
-- combat with a tile to cover, 0 otherwise, SetCover), which is always allowed.
-- If the container cannot be armed (or built) combat shows only what the Hud reports. The container is
-- a child of the buff piece frame, so the piece's fade and hide reach the covers through the parent
-- (the cover never reads the piece state itself, so a present buff's warning cannot flash while the
-- piece fades). Stack A keeps the
-- plain SetEnabled/Show/Hide of SetLive.
--
-- PROCS glow a ring around the row tile and the next tile: the profile's glow colour, STATIC (the
-- mockup's .ring.gold and .hud-next.gold carry no animation, only a box-shadow, drawn here by
-- Theme.AddOuterGlow). A row tile's own `proc` plus state.procs (active procs mapped through the
-- profile's overlaySpell) feed it. The next ring is cyan, gold on a proc.
--
-- OUT OF COMBAT. With no next cast and no combat the HUD is in the mockup's "ooc" style (hudRender's
-- `ooc` branch): every tile gets the plain "ready" look (no dim, no ring even on a proc or the next
-- spell, no seconds text), the DoT slots' engine timers are hidden (they hang off the aura
-- container, so the row's alpha would not reach them), the row sits at .55 opacity, the next tile
-- is hidden, and the cast bars are dimmed to the same .55 (FS.CastBars.SetRestAlpha). Buffs and
-- shards still show. A next cast (in or out of combat) is the "opener" style: row at full
-- opacity, the next tile up, the bars at full alpha, and the tiles' states and slots back.
--
-- IDLE ROW. With CombatHud.idleCastBars (default true) the cast bars show their idle row
-- (FS.CastBars.SetIdleVisible) and the player bar's tab names the next spell, or the class
-- filler (the wand) when there is none (SetIdleHint). The mockup keeps the idle row up in
-- combat too (the bar between casts), so IDLE_IN_COMBAT is true; CastBars hides it while a cast
-- runs. No CastBars API: skipped, logged once.
--
-- SECRETS. FS.Hud reports plain values, but every field is still checked IsSecret FIRST (a
-- secret compared even to nil is illegal) before it is compared, formatted or used as a key; a
-- secret field is treated as unknown. Nothing here reads an aura or does arithmetic on a value
-- it has not checked.
--
-- HudText.lua is a different job (zone text, error frame, raid warnings, combat text fonts)
-- and the two coexist: nothing here touches those frames.
--
-- Slash: /fshud [on|off|idle on|idle off]. Settings live in ForeverSTUwaveDB.combatHud
-- (account-wide; enabled is per class token). Default on for PRIEST, WARLOCK and PALADIN.
--
-- UNVERIFIED in game: the AuraContainer slot rendering over our tiles, the occlusion layering,
-- the glow, the placement against the mockup, and whether includeSpellIDs covers every rank id
-- (see RANK_IDS). Headless check: python3 addons/combathud-harness.py.

local _, FS = ...

local Theme = FS.Theme

local CombatHud = { idleCastBars = true }
FS.CombatHud = CombatHud

-------------------------------------------------------------------------------
-- Geometry (mockup units == UIParent units)
-------------------------------------------------------------------------------

local G = {
    TILE = 36, TILE_GAP = 6, ROW_H = 36, ROW_GAP = 10,      -- .hud-ic, .hud-spells, HUD_ROW, HUD_ROW_GAP
    NEXT = 56, NEXT_GAP = 10,                               -- HUD_NEXT, the hud's padding-left less the tile
    SHARD_W = 10, SHARD_H = 12, SHARD_GAP = 3, SHARD_TOP = 6, SHARD_ROW_H = 12,
    BUFF = 24, BUFF_GAP = 6, BUFF_TOP = 8, BUFF_ROW_H = 24,
    -- CastBars.lua's own numbers (file locals there; the harness compares them with its source)
    TAB_H = 15, FRAME_H = 22, GAP = 18, FALLBACK_X = 0, FALLBACK_Y = -317, FALLBACK_W = 268,
}
CombatHud.geometry = G

-- Tunables folded into ONE table: this file sits close to Lua's 200 file-scope local limit (a
-- luac 5.4 "too many local variables" failure at 200; parse-gate.py fails a file at 190), so a
-- constant used in one or two places lives here instead of taking a slot of its own.
local TUNE = {
    RING_OUT = 2, RING_THICK = 2, ROW_GLOW = 8,    -- .ring: inset -2, 2px border, glow 8
    NEXT_BORDER = 2, NEXT_GLOW = 10,               -- .hud-next: 2px border, glow 10
    RING_GLOW_ALPHA = 0.5,                         -- the Stack A rings' glow strength
    NEXT_GLOW_ALPHA = 1,                           -- Gunsight drawNext: glow(gc, 1), the full strength
    DIM_ALPHA = 0.45, OOC_ALPHA = 0.55,            -- .tile.dim opacity, .hud-spells.ooc opacity
    MAX_SHARDS = 20,                               -- 20 diamonds fill the 268 column
    CD_THROTTLE = 0.1,                             -- the countdown text runs at most 10 Hz
    CONTAINER_LEVEL = 20,                          -- aura containers sit above every tile of ours
    RING_LEVEL = 2,
    AURA_BUILD_FAIL_LIMIT = 3,
    IDLE_IN_COMBAT = true,
    SHARD_CANVAS_W = 16, SHARD_CANVAS_H = 32,      -- design px of the line, fill and facet files (generate_hud_shard.py LINE_TEX)
    SHARD_GLOW_CANVAS = 40,                        -- design px of the square glow file (GLOW_TEX)
    HOME_GLYPH_W = 9.5, HOME_GLYPH_H = 17,         -- v7 homeShards: the one glyph's box, image px
    HOME_GLYPH_DX = 16.25, HOME_NUM_PX = 14,       -- its centre left of the count's right edge, and the count's size, image px
    HOME_DIGIT = 0.6,                              -- the mono face's advance per size: the glyph steps left this far per extra digit
    HOME_OFF_LINE = 0.4, HOME_OFF_FILL = 0.06, HOME_OFF_FACET = 0.2,   -- shard(..., filled=false): the unlit glyph's alphas
}
local GRID = 1.28                                    -- design px per canvas image px (the Gunsight mockup's U = 1 / 1.28)
local BUFF_PULSE_FROM, BUFF_PULSE_S, BUFF_GLOW = 0.35, 1.4, 8   -- @keyframes hudpulse: border alpha from, seconds, box-shadow

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local DIAMOND_TEXTURE = MEDIA .. "hud_diamond.tga"
local TILE_TEXTURE = MEDIA .. "hud_tile_cut2.tga"
local AURA_CONTAINER_TEMPLATE = "CustomAuraContainerTemplate"

-- The mockup's palette. Theme has the violet, pink, cyan, bg and white tokens; gold, surface,
-- text, muted and the proc red are the mockup's own and are not Theme tokens yet (a Theme token
-- of the same name wins when it appears).
local COLOR_GOLD = Theme.COLOR_GOLD or { 1, 210 / 255, 63 / 255, 1 }            -- --gold #ffd23f
local COLOR_WARM = Theme.COLOR_WARM or { 1, 61 / 255, 31 / 255, 1 }             -- --warm #ff3d1f, the "red" proc
local COLOR_TEXT = Theme.COLOR_TEXT or { 226 / 255, 232 / 255, 240 / 255, 1 }   -- --text #e2e8f0
local COLOR_MUTED = Theme.COLOR_MUTED or { 154 / 255, 143 / 255, 189 / 255, 1 } -- --muted #9a8fbd
-- The mockup's tile is a 135 degree gradient from --surface #2d1b4e to --bg #1a1025. A diagonal
-- gradient has no texture API, so it is baked into media/hud_tile_cut2.tga (generate_hud_tile.py),
-- with the TOP-LEFT and BOTTOM-RIGHT corners chamfered at 1/6 of the tile (6 px on the 36 spell
-- tile, 4 on the 24 buff tile, 9.3 on the 56 next tile); this flat midpoint is the fallback when
-- that texture cannot be set.
local TILE_FILL = { 0.139, 0.084, 0.225, 1 }
local BORDER = Theme.COLOR_BORDER or { 0.659, 0.333, 0.969, 1 }
local PINK = Theme.COLOR_HEALTH or { 1, 0.180, 0.592, 1 }
local CYAN = Theme.COLOR_POWER or { 0.133, 0.878, 1, 1 }

-------------------------------------------------------------------------------
-- Rank ids for includeSpellIDs. UNVERIFIED classic data from memory: the dictionary lists only
-- the two ends of a verified rank range, and an aura reports the rank id that was cast. The
-- id the spell NAME resolves to today (the player's current rank) is added at run time, so a
-- highest rank cast is always covered even if a list below is wrong. Keys are HudSpells keys.
-------------------------------------------------------------------------------

local RANK_IDS = {
    sw_pain = { 589, 594, 970, 992, 2767, 10892, 10893, 10894, 25367, 25368 },
    dplague = { 2944, 19276, 19277, 19278, 19279, 19280, 25467 },
    corruption = { 172, 6222, 6223, 7648, 11671, 11672, 25311, 27216 },
    bane_agony = { 980, 1014, 6217, 11711, 11712, 11713, 27218 },
    bane_doom = { 603, 30910 },
    immolate = { 348, 707, 1094, 2941, 11665, 11667, 11668, 25309, 27215 },
    siphon = { 18265, 18879, 18880, 18881, 30911 },
    fort = { 1243, 1244, 1245, 2791, 10937, 10938, 25389, 21562, 21564, 25392 },
    inner_fire = { 588, 602, 1006, 7128, 10951, 10952, 25431 },
    demon_armor = { 687, 696, 706, 1086, 11733, 11734, 11735, 27260 },
}

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "combathud_" .. key, "|cffff4488Forever STUwave|r: combat HUD: " .. tostring(msg))
    end
end

-- A secret is checked FIRST: even `secret == nil` is an illegal comparison.
local function IsSecret(v)
    local fn = FS.IsSecret
    if type(fn) ~= "function" then return false end
    local ok, r = pcall(fn, v)
    return not ok or r == true
end

local function PlainNumber(v)
    if IsSecret(v) then return nil end
    if type(v) == "number" then return v end
    return nil
end

local function PlainString(v)
    if IsSecret(v) then return nil end
    if type(v) == "string" and v ~= "" then return v end
    return nil
end

local function PlainBool(v)
    if IsSecret(v) then return nil end
    if type(v) == "boolean" then return v end
    return nil
end

local function PlainIcon(v)
    if IsSecret(v) then return nil end
    if type(v) == "number" or type(v) == "string" then return v end
    return nil
end

-- Fails closed: a throwing check reads as "in combat".
local function InCombatSafe()
    local ok, r = pcall(InCombatLockdown)
    if not ok or IsSecret(r) then return true end
    return r and true or false
end

-- Fails the other way: true only when the client reads as in combat right now. A throwing or secret
-- check is NOT in combat (the Gunsight cover must never go live on a guess).
local function InCombatNow()
    local ok, r = pcall(InCombatLockdown)
    if not ok or IsSecret(r) then return false end
    return r and true or false
end

-- obj:method(...) when the method exists, any error swallowed. True unless the method existed
-- and threw (a missing method is not a failure), so one refusing setter never stops the next.
local function Quiet(obj, method, ...)
    local okGet, fn = pcall(function() return obj[method] end)
    if okGet and type(fn) == "function" then return (pcall(fn, obj, ...)) end
    return true
end

-------------------------------------------------------------------------------
-- Spells: names, icons, known, rank ids
-------------------------------------------------------------------------------

local function Def(key)
    local spells = FS.HudSpells
    return spells and spells[key] or nil
end

local function SpellName(key)
    local def = Def(key)
    return def and def.names and def.names[1] or nil
end

-- name, id, icon of a spell by name or id; plain values only.
local function SpellInfo(x)
    local fn = C_Spell and C_Spell.GetSpellInfo
    if fn then
        local ok, info = pcall(fn, x)
        if ok and not IsSecret(info) and type(info) == "table" then
            return PlainString(info.name), PlainNumber(info.spellID), PlainIcon(info.iconID)
        end
        return nil
    end
    if GetSpellInfo then
        local ok, name, _, icon, _, _, _, id = pcall(GetSpellInfo, x)
        if ok then return PlainString(name), PlainNumber(id), PlainIcon(icon) end
    end
    return nil
end

local iconCache = {}
local function IconFor(key)
    local hit = iconCache[key]
    if hit then return hit end
    local def = Def(key)
    for _, name in ipairs(def and def.names or {}) do
        local _, _, icon = SpellInfo(name)
        if icon then iconCache[key] = icon; return icon end
    end
    return nil
end

-- A short label: the initials of a multi word name ("Shadow Word: Pain" = SWP), else its first
-- three letters ("Corruption" = COR). The mockup's tile ids are of this kind.
local SKIP_WORD = { of = true, the = true }
local function Abbrev(key)
    if key == "pet" then return "PET" end
    local name = SpellName(key)
    if not name then return string.upper(string.sub(key, 1, 3)) end
    local words = {}
    for w in string.gmatch(name, "%a+") do
        if not SKIP_WORD[string.lower(w)] then words[#words + 1] = w end
    end
    if #words == 0 then return string.upper(string.sub(key, 1, 3)) end
    if #words == 1 then return string.upper(string.sub(words[1], 1, 3)) end
    local out = ""
    for i = 1, math.min(#words, 3) do out = out .. string.upper(string.sub(words[i], 1, 1)) end
    return out
end

-- true / false / nil (cannot tell) for "does the player know this spell id", the same three
-- sources HudLogic.lua asks.
local function IsKnownId(id)
    local fns = {}
    if IsPlayerSpell then fns[#fns + 1] = IsPlayerSpell end
    if IsSpellKnown then fns[#fns + 1] = IsSpellKnown end
    if C_SpellBook and C_SpellBook.IsSpellKnown then fns[#fns + 1] = C_SpellBook.IsSpellKnown end
    local sawFalse, unreadable = false, false
    for _, fn in ipairs(fns) do
        local ok, r = pcall(fn, id)
        if ok and not IsSecret(r) then
            if r then return true end
            sawFalse = true
        else
            unreadable = true
        end
    end
    if unreadable then return nil end
    if sawFalse then return false end
    return nil
end

local knownCache = {}
local function SpellKnown(key)
    local hit = knownCache[key]
    if hit ~= nil then return hit end
    local def = Def(key)
    if not def then return nil end
    local ids = {}
    for _, name in ipairs(def.names or {}) do
        local _, id = SpellInfo(name)
        if id then ids[#ids + 1] = id end
    end
    for _, id in ipairs(def.ids or {}) do ids[#ids + 1] = id end
    local result = nil
    for _, id in ipairs(ids) do
        local k = IsKnownId(id)
        if k == true then result = true; break end
        if k == false then result = false end
    end
    if result ~= nil then knownCache[key] = result end
    return result
end

-- The set { [spellId] = true } an aura slot may show for `key`: the dictionary ids, the id the
-- name resolves to now, and RANK_IDS. Returns the set and its size.
local function IdSet(key)
    local set, n = {}, 0
    local function add(id)
        if type(id) == "number" and not IsSecret(id) and not set[id] then
            set[id] = true
            n = n + 1
        end
    end
    local def = Def(key)
    if def then
        for _, id in ipairs(def.ids or {}) do add(id) end
        for _, name in ipairs(def.names or {}) do
            local _, id = SpellInfo(name)
            add(id)
        end
    end
    for _, id in ipairs(RANK_IDS[key] or {}) do add(id) end
    return set, n
end

-------------------------------------------------------------------------------
-- Frame building blocks
-------------------------------------------------------------------------------

local ui = { tiles = {}, buffTiles = {}, diamonds = {} }
CombatHud.ui = ui
local containers = {}
CombatHud.containers = containers

-- Tooltips for the tiles that show a HudSpells spell (a skill that shows up has a tooltip). Hover only:
-- the centre HUD must pass clicks through, and the mouse state is set once, when the tile is built, never in
-- combat. Under the Gunsight a tip is suppressed while it is switched off (the root only fades in combat).
-- Fields of CombatHud, not file-scope locals (this file is near the parse-gate ceiling).
function CombatHud.AttachTip(frame)
    local helpers = FS.FrameHelpers
    if type(helpers) ~= "table" then return end
    local gate = nil
    if ui.gunsight then
        gate = function()
            local gs = FS.Gunsight
            return type(gs) == "table" and type(gs.IsActive) == "function" and gs.IsActive() == true
        end
    end
    helpers.AttachSpellTooltip(frame, { gate = gate })
end

-- Paint side: caches the spell id and name of HudSpells `key` on the frame (SetTipSpell), so the tip works
-- in combat, and redraws an open tip when the spell changed. Allocation-free: a table read and two cached
-- lookups. A key with no spell name clears the tip.
function CombatHud.SetTip(frame, key)
    local helpers = FS.FrameHelpers
    if type(helpers) ~= "table" then return end
    local name = SpellName(key)
    helpers.SetTipSpell(frame, helpers.SpellIDForName(name), name)
end
CombatHud.stats = { cdTicks = 0 }

-------------------------------------------------------------------------------
-- The Gunsight view: which view, and the design px to UI unit multiplier
-------------------------------------------------------------------------------

-- True while the Gunsight HUD is the view to draw. Read once per build (ui.gunsight): /fsgun on|off
-- needs a reload, so the answer cannot change under a built UI.
local function GunsightOn()
    local gs = FS.Gunsight
    if type(gs) ~= "table" or type(gs.IsEnabled) ~= "function" then return false end
    local ok, on = pcall(gs.IsEnabled)
    return ok and on == true
end

-- Design px to UI units: FS.Layout.Scale(). 1 when it cannot be read, so a missing Layout leaves the
-- design sizes as they are.
local function LayoutScale()
    local fn = FS.Layout and FS.Layout.Scale
    if type(fn) ~= "function" then return 1 end
    local ok, s = pcall(fn)
    if ok and not IsSecret(s) and type(s) == "number" and s > 0 then return s end
    return 1
end

-- The multiplier in force: 1 in the Stack A view (its numbers are UI units already), the layout
-- scale in the Gunsight view.
local function K() return ui.k or 1 end

-- A type size or stroke count for design px `v` at multiplier `k`: whole numbers, never under 1,
-- and `v` itself at k == 1 so the Stack A numbers do not move.
local function Sz(v, k)
    if k == 1 and v == math.floor(v) then return v end
    return math.max(1, math.floor(v * k + 0.5))
end

-- A size the Gunsight mockup draws in raw CANVAS px (its type sizes: the keybind 12, NEXT 9, the buff
-- abbreviation 8; the canvas is scaled to 2000 wide, design = image * 1.28) in the unit Sz takes. The Stack A
-- view keeps its own numbers, which are UI units already.
local function CanvasPx(v)
    if ui.gunsight then return v * GRID end
    return v
end

-- The chamfer, in units, of the ring and border drawn around a tile `size` units square: the baked
-- tile cut is 1/6 of the tile, so the nearest baked outline size to size / 6. Exact on the 36 spell
-- tile (6) and the 24 buff tile (4); the 56 next tile's baked cut is 9.3 and the outline set stops
-- at 6, so its ring is the closest set (its 2 unit stroke covers most of the difference).
local function TileCut(size)
    local ok, c = pcall(Theme.SnapCut, math.floor(size / 6 + 0.5))
    if ok and type(c) == "number" and c > 0 then return c end
    return 4
end

-- The tile's cut outline of `t` units: t stacked 1 texel TOP-LEFT and BOTTOM-RIGHT cut strokes of
-- chamfer `c`, each one unit inside the last (the same chamfer, so the stroke widens evenly), tinted
-- by vertex colour. The list is returned so a caller can retint it (SetVertexColor, never
-- SetColorTexture: the shape lives in the texture's alpha).
local function CutOutline(frame, color, c, t, layer)
    local edges = {}
    local ok, path = pcall(Theme.Cut2ButtonSet, c)
    if not ok or type(path) ~= "string" then return edges end
    for i = 1, t do
        local pieceOk, tex = pcall(Theme.AddSliceTexture, frame, path, color, layer or "OVERLAY", i, i - 1)
        if pieceOk and tex then
            pcall(Theme.ApplyNineSlice, tex, c)
            edges[#edges + 1] = tex
        end
    end
    return edges
end

-- Re-cuts the strokes CutOutline built to chamfer `c`, in place (the texture and the nine-slice
-- margin; the colour and the stacking stay). The Gunsight view calls it when a rescale changes the
-- snapped chamfer of a tile.
local function RecutOutline(edges, c)
    local ok, path = pcall(Theme.Cut2ButtonSet, c)
    if not ok or type(path) ~= "string" then return end
    for _, tex in ipairs(edges) do
        pcall(tex.SetTexture, tex, path)
        pcall(Theme.ApplyNineSlice, tex, c)
    end
end

-- A tile's icon inset: at least `base` on every side, and ceil(c / 2) so the square icon's corner
-- sits on the chamfer line instead of poking past it (FrameHelpers.SeatCutIcon's rule).
local function SeatIcon(icon, host, base, c)
    local inset = math.max(base, math.ceil(c / 2))
    icon:ClearAllPoints()
    icon:SetPoint("TOPLEFT", host, "TOPLEFT", inset, -inset)
    icon:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", -inset, inset)
end

-- Where a spell tile's bottom right label sits: that corner is the tile's cut, so the label box
-- corner stays past the chamfer line u + v = cut + 1 (the stroke), u across from the right edge and
-- v up from the bottom. On the 36 tile (cut 6) that is 4 and 3, so the last digit's ink (about a
-- unit inside the box corner) clears the diagonal. Returns u, v.
local function SecsInset()
    local x = math.ceil((TileCut(G.TILE) + 1) / 2)
    return x, x - 1
end

-- A looping alpha pulse on `frame`.
local function NewPulse(frame, fromAlpha, toAlpha, duration)
    local ag = frame:CreateAnimationGroup()
    ag:SetLooping("BOUNCE")
    local a = ag:CreateAnimation("Alpha")
    a:SetFromAlpha(fromAlpha)
    a:SetToAlpha(toAlpha)
    a:SetDuration(duration)
    a:SetSmoothing("IN_OUT")
    return ag
end

local function SetPulse(group, on)
    if not group then return end
    if on then
        if not group:IsPlaying() then group:Play() end
    elseif group:IsPlaying() then
        group:Stop()
    end
end

-- `flags` ("OUTLINE") only applies on the mono path: the mockup's .secs has a 4 way black outline.
local function ApplyFont(fs, size, color, mono, flags)
    local ok = pcall(function()
        if mono then
            Theme.ApplyFontGeneric(fs, Theme.FONT_MONO, size, color, flags or "")
        else
            Theme.ApplyMono(fs, size, color)
        end
    end)
    if not ok then pcall(fs.SetFont, fs, "Fonts\\FRIZQT__.TTF", size, flags or "") end
end

-- The tile fill: the baked gradient, or the flat colour when the texture cannot be set. A missing
-- file does not throw in WoW (SetTexture succeeds and the texture stays empty, so the tile would
-- draw nothing), hence the GetTexture read-back. Returns true when the baked texture is in use.
local function PaintTileFill(tex)
    local ok = pcall(tex.SetTexture, tex, TILE_TEXTURE)
    if ok then
        local readable, got = pcall(tex.GetTexture, tex)
        -- an unreadable read-back (a throw or a secret) keeps the texture: SetTexture raised no error
        if not readable or IsSecret(got) or got ~= nil then return true end
    end
    tex:SetColorTexture(TILE_FILL[1], TILE_FILL[2], TILE_FILL[3], 1)
    return false
end

-- CSS grayscale(1): the luminance of a colour as a grey triple.
local function GreyOf(c)
    local l = 0.2126 * c[1] + 0.7152 * c[2] + 0.0722 * c[3]
    return { l, l, l, c[4] or 1 }
end

local function Tint(edges, c)
    for _, edge in ipairs(edges) do edge:SetVertexColor(c[1], c[2], c[3], c[4] or 1) end
end

local function KindColor(kind)
    if kind == "gold" then return COLOR_GOLD end
    if kind == "red" then return COLOR_WARM end
    return CYAN
end

-- A proc glow name from the profile ("gold", "red") to a ring kind; nil stays nil.
local function GlowKind(name)
    if name == nil then return nil end
    if name == "red" then return "red" end
    return "gold"
end

-- The ring: a cut outline border of `thick` units `outset` outside `target` (0 = inside its edge)
-- plus a box-shadow glow of `glowSize`, tinted by kind ("cyan" next, "gold" or "red" proc), both
-- cut at TOP-LEFT and BOTTOM-RIGHT with chamfer `cut`. Glows are built per kind the first time
-- that kind is needed (Theme.AddOuterGlow bakes the colour). Every kind is static, like the
-- mockup's .ring and .ring.gold; the colour is a STEP between kinds (the Gunsight mockup eases cyan to
-- gold over 0.3 s, which would need an OnUpdate for one tile: not worth a permanent one).
local function NewRing(parent, target, outset, thick, glowSize, cut, glowAlpha)
    local ring = CreateFrame("Frame", nil, parent)
    ring:SetPoint("TOPLEFT", target, "TOPLEFT", -outset, outset)
    ring:SetPoint("BOTTOMRIGHT", target, "BOTTOMRIGHT", outset, -outset)
    ring:SetFrameLevel(target:GetFrameLevel() + TUNE.RING_LEVEL)
    ring.edges = CutOutline(ring, CYAN, cut, thick, "OVERLAY")
    ring.glows = {}
    ring.glowSize = glowSize
    ring.glowAlpha = glowAlpha or TUNE.RING_GLOW_ALPHA
    ring.cut = cut
    ring:Hide()
    return ring
end

local function SetRing(ring, kind)
    if ring.kind == kind then return end
    ring.kind = kind
    if not kind then
        ring:Hide()
        return
    end
    local c = KindColor(kind)
    Tint(ring.edges, c)
    for _, host in pairs(ring.glows) do host:Hide() end
    local host = ring.glows[kind]
    if not host then
        host = CreateFrame("Frame", nil, ring)
        host:SetAllPoints(ring)
        pcall(Theme.AddOuterGlow, host, c[1], c[2], c[3], ring.glowSize, ring.glowAlpha, ring.cut)
        ring.glows[kind] = host
    end
    host:Show()
    ring:Show()
end

-------------------------------------------------------------------------------
-- Cast bar anchors
-------------------------------------------------------------------------------

local fallbackBars

-- The two Stack A cast bar frames, or a fixed seat built here (logged once).
local function ResolveBars()
    local t = FS.targetCastBar and FS.targetCastBar.frame
    local p = FS.playerCastBar and FS.playerCastBar.frame
    if t and p then return t, p end
    LogOnce("no_castbars", "the cast bar frames are missing; the HUD uses the fixed seat at (0, -317) with an 18 gap.")
    if not fallbackBars then
        local half = G.GAP / 2 + G.FRAME_H / 2
        local function seat(cy)
            local f = CreateFrame("Frame", nil, UIParent)
            f:SetSize(G.FALLBACK_W, G.FRAME_H)
            f:SetPoint("CENTER", UIParent, "CENTER", G.FALLBACK_X, cy)
            return f
        end
        fallbackBars = { seat(G.FALLBACK_Y + half), seat(G.FALLBACK_Y - half) }
    end
    return fallbackBars[1], fallbackBars[2]
end

-------------------------------------------------------------------------------
-- AuraContainer slots
-------------------------------------------------------------------------------

local aura = { failures = 0, gaveUp = false, templateOk = nil }
local parked = {}
local passTried = {}

local function ResetPass() passTried = {} end

local function TemplateAvailable()
    if aura.templateOk ~= nil then return aura.templateOk end
    local info = C_XMLUtil and C_XMLUtil.GetTemplateInfo
    local ok = false
    if type(info) == "function" then
        local good, result = pcall(info, AURA_CONTAINER_TEMPLATE)
        ok = good and result ~= nil and result ~= false
    end
    aura.templateOk = ok
    return ok
end

local function BuildContainer(unit)
    -- The Gunsight view hangs the player container (the buff covers) under the buff PIECE frame, so the
    -- piece's 0.25 s fade and its hide carry the covers with it instead of the covers popping off first.
    local home = (ui.gunsight and unit == "player" and ui.buffPiece) or ui.root
    local container = CreateFrame("AuraContainer", nil, home, AURA_CONTAINER_TEMPLATE)
    local ok, err = pcall(function()
        container:SetSize(1, 1)
        container:SetPoint("CENTER", ui.root, "CENTER", 0, 0)
        container:SetFrameLevel(ui.root:GetFrameLevel() + TUNE.CONTAINER_LEVEL)
        container:SetUnit(unit)
        container:SetEnabled(false)
        container:Hide()
        if ui.gunsight and unit == "player" then container:SetAlpha(0) end
    end)
    if not ok then
        -- a frame cannot be destroyed: park it quietly
        Quiet(container, "SetEnabled", false)
        Quiet(container, "Hide")
        parked[#parked + 1] = container
        error(err, 0)
    end
    container.fsLive = false
    if ui.gunsight and unit == "player" then container.fsAlpha = 0 end
    return container
end

-- The container for `unit`, built on demand: out of combat only, at most once per pass, and
-- never again once AURA_BUILD_FAIL_LIMIT consecutive builds have failed.
local function EnsureContainer(unit)
    local c = containers[unit]
    if c then return c end
    -- defensive: every caller already checks combat, a throwing check reads as in combat here too
    if aura.gaveUp or passTried[unit] or InCombatSafe() then return nil end
    if not TemplateAvailable() then
        LogOnce("aura_container", "this client has no " .. AURA_CONTAINER_TEMPLATE .. "; the tiles carry no timers and no combat buff reminders.")
        aura.gaveUp = true
        return nil
    end
    passTried[unit] = true
    local ok, result = pcall(BuildContainer, unit)
    if ok then
        aura.failures = 0
        containers[unit] = result
        return result
    end
    aura.failures = aura.failures + 1
    LogOnce("aura_container", "the aura container could not be built (" .. tostring(result) .. "); tiles carry no timers.")
    if aura.failures >= TUNE.AURA_BUILD_FAIL_LIMIT then
        aura.gaveUp = true
        LogOnce("aura_container_giveup", "the aura container failed " .. TUNE.AURA_BUILD_FAIL_LIMIT .. " times; giving it up for this session.")
    end
    return nil
end

-- True when the container reads back in the wanted state. A blocked call (a protected frame in
-- combat) raises nothing, so a call that did not throw proves nothing: the readback is the proof.
-- Only what the container can answer is checked (IsEnabled may not exist on the client).
local function ContainerIs(container, live)
    local ok, shown = pcall(container.IsShown, container)
    if ok and not IsSecret(shown) and (shown and true or false) ~= live then return false end
    local okFn, fn = pcall(function() return container.IsEnabled end)
    if okFn and type(fn) == "function" then
        local okE, enabled = pcall(fn, container)
        if okE and not IsSecret(enabled) and (enabled and true or false) ~= live then return false end
    end
    return true
end

local function IsProtectedFrame(frame)
    local ok, fn = pcall(function() return frame.IsProtected end)
    if not ok or type(fn) ~= "function" then return false end
    local okP, value = pcall(fn, frame)
    return okP and value == true
end

-- Turns a container on or off (Stack A: the player buff container and the target DoT container).
-- Alpha is ALWAYS written (it is allowed in combat, even on a protected frame), so a Hide the engine
-- refuses still leaves nothing drawn and an enable it refuses leaves the container invisible rather
-- than half on. `fsLive` records only a state the container was read back in, so a refusal is asked
-- again by the next render; `fsPending` marks a container that could not be moved (refused, or
-- protected in combat, where no SetEnabled/Show/Hide is attempted at all) so PLAYER_REGEN_ENABLED
-- re-renders. The wanted state is never replayed from here: the re-render asks for the CURRENT one.
local function SetLive(container, live)
    if not container then return end
    local alpha = live and 1 or 0
    if container.fsAlpha ~= alpha and Quiet(container, "SetAlpha", alpha) then container.fsAlpha = alpha end
    if container.fsLive == live then
        container.fsPending = nil
        return
    end
    if InCombatSafe() and IsProtectedFrame(container) then
        container.fsPending = true
        return
    end
    local enabled = Quiet(container, "SetEnabled", live)
    local shown = Quiet(container, live and "Show" or "Hide")
    if enabled and shown and ContainerIs(container, live) then
        container.fsLive = live
        container.fsPending = nil
    else
        container.fsPending = true
    end
end

-- Gunsight: a cover is visible (alpha 1) or not (alpha 0), nothing else. SetAlpha is allowed in combat.
local function SetCover(container, live)
    if not container then return end
    local alpha = live and 1 or 0
    if container.fsAlpha ~= alpha and Quiet(container, "SetAlpha", alpha) then container.fsAlpha = alpha end
end

-- The Gunsight player container (the buff covers): enabled, given its unit and shown OUT OF COMBAT,
-- read back (the engine refuses a protected frame without raising), and left that way. `fsArmed` is the
-- state it was read back in; a container that reads back off is armed again on the next call. Arming also
-- writes alpha 0 (not through the SetCover cache, which a refused or reset frame can leave stale): a
-- freshly armed live slot must draw nothing until combat asks for it.
local function ArmCover(container)
    if not container or InCombatSafe() then return end
    local rearm = not container.fsArmed
    if not ContainerIs(container, true) then
        rearm = true
        Quiet(container, "SetUnit", "player")
        Quiet(container, "SetEnabled", true)
        Quiet(container, "Show")
    end
    container.fsArmed = ContainerIs(container, true)
    if rearm and Quiet(container, "SetAlpha", 0) then container.fsAlpha = 0 end
end

-- The player container's visibility in either view.
local function SetPlayerLive(live)
    local container = containers.player
    if ui.gunsight then SetCover(container, live) else SetLive(container, live) end
end

local function SortOptions()
    local method = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
    local direction = type(_G.AuraContainerSortDirection) == "table" and _G.AuraContainerSortDirection.Normal or nil
    return method, direction
end

-- initializeFrame for a DoT slot: the engine's duration text bottom right of the tile, nothing
-- else (the tile already shows the spell). Runs before the frame turns restricted, each step on
-- its own, mouse off first.
local function InitDotSlot(tile)
    return function(button)
        Quiet(button, "SetMouseMotionEnabled", false)
        Quiet(button, "SetMouseClickEnabled", false)
        Quiet(button, "SetHideTooltipInCombat", true)
        pcall(function() button:SetAllPoints(tile.holder) end)
        pcall(function()
            local text = button:CreateFontString(nil, "OVERLAY")
            ApplyFont(text, 11, Theme.COLOR_TEXT_WHITE, true, "OUTLINE")
            local x, y = SecsInset()
            text:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -x, y)
            text:SetJustifyH("RIGHT")
            button:SetDurationText(text, {})
        end)
    end
end

-- initializeFrame for a buff cover: the aura's own icon, opaque, with a cut border, exactly on
-- the warning tile. The cover carries its own cut tile fill under the icon (same TOP-LEFT and
-- BOTTOM-RIGHT chamfer as the warning tile) so the icon inset around the cut does not let the
-- warning tile's pink border show through a present buff, and its square icon never pokes past
-- the cut. The pieces are kept on `tile.cover` (with the chamfer they were cut at) so a rescale can
-- re-seat the icon and re-cut the border (RescaleCover); the fill is the baked tile, whose cut is a
-- fixed 1/6 of whatever size it is stretched to.
local function InitBuffSlot(tile)
    return function(button)
        Quiet(button, "SetMouseMotionEnabled", false)
        Quiet(button, "SetMouseClickEnabled", false)
        Quiet(button, "SetHideTooltipInCombat", true)
        pcall(function() button:SetAllPoints(tile.holder) end)
        local cut = TileCut(G.BUFF * K())
        local cover = { button = button, cut = cut }
        tile.cover = cover
        pcall(function()
            local bg = button:CreateTexture(nil, "BACKGROUND")
            bg:SetAllPoints(button)
            PaintTileFill(bg)
            cover.bg = bg
        end)
        pcall(function()
            local icon = button:CreateTexture(nil, "ARTWORK")
            SeatIcon(icon, button, 0, cut)
            icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
            button:SetIcon(icon)
            cover.icon = icon
        end)
        pcall(function() cover.border = CutOutline(button, BORDER, cut, 1, "OVERLAY") end)
    end
end

local function AddSlot(container, slotKey, filter, ids, initFn)
    local method, direction = SortOptions()
    return pcall(container.AddAuraSlot, container, slotKey, filter, {
        initializeFrame = initFn,
        candidateFilters = { includeSpellIDs = ids },
        sortMethod = method,
        sortDirection = direction,
    })
end

-- The profile this HUD runs on and its DoT group of a key.
local function Profile()
    local Hud = FS.Hud
    if type(Hud) ~= "table" or type(Hud.GetProfile) ~= "function" then return nil end
    local ok, p = pcall(Hud.GetProfile)
    if ok and type(p) == "table" then return p end
    return nil
end

local function IsDot(profile, key)
    return profile and profile.dots and profile.dots[key] ~= nil
end

-- The ids a DoT slot covers: the spell's own plus every member of its exclusivity group (the
-- banes), since the tile stands for the whole group.
local function DotIds(profile, key)
    local set, n = IdSet(key)
    local spec = profile.dots[key]
    if spec and spec.group then
        for other, o in pairs(profile.dots) do
            if other ~= key and o.group == spec.group then
                local more = IdSet(other)
                for id in pairs(more) do
                    if not set[id] then set[id] = true; n = n + 1 end
                end
            end
        end
    end
    return set, n
end

-------------------------------------------------------------------------------
-- Tiles
-------------------------------------------------------------------------------

-- The tile's own seconds (a cooldown, or the Hud's DoT estimate) sit bottom right, the mockup's
-- .secs corner. A DoT tile with a LIVE aura slot has the engine's timer in that corner, so its own
-- seconds (a cooldown while the DoT is down) move bottom left: the mockup never shows both.
local function SeatSecs(tile, left)
    if tile.secsLeft == left then return end
    tile.secsLeft = left
    local fs = tile.secs
    fs:ClearAllPoints()
    if left then
        fs:SetPoint("BOTTOMLEFT", tile.holder, "BOTTOMLEFT", 2, 1)
        fs:SetJustifyH("LEFT")
    else
        local x, y = SecsInset()
        fs:SetPoint("BOTTOMRIGHT", tile.holder, "BOTTOMRIGHT", -x, y)
        fs:SetJustifyH("RIGHT")
    end
end

local function NewTile(key)
    local holder = CreateFrame("Frame", nil, ui.row)
    holder:SetSize(G.TILE, G.TILE)
    CombatHud.AttachTip(holder)
    -- the part the dim state fades (the mockup's .tile); the ring and the seconds stay lit
    local face = CreateFrame("Frame", nil, holder)
    face:SetAllPoints(holder)
    local bg = face:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints(face)
    local baked = PaintTileFill(bg)
    local cut = TileCut(G.TILE)
    local icon = face:CreateTexture(nil, "ARTWORK")
    SeatIcon(icon, face, 1, cut)
    icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    local border = CutOutline(face, BORDER, cut, 1, "OVERLAY")
    local abbr = face:CreateFontString(nil, "OVERLAY")
    ApplyFont(abbr, 11, COLOR_TEXT)
    abbr:SetPoint("CENTER", face, "CENTER", 0, 0)
    local ring = NewRing(holder, holder, TUNE.RING_OUT, TUNE.RING_THICK, TUNE.ROW_GLOW, cut)
    local secsHost = CreateFrame("Frame", nil, holder)
    secsHost:SetAllPoints(holder)
    secsHost:SetFrameLevel(holder:GetFrameLevel() + TUNE.RING_LEVEL + 2)
    local secs = secsHost:CreateFontString(nil, "OVERLAY")
    ApplyFont(secs, 11, Theme.COLOR_TEXT_WHITE, true, "OUTLINE")
    secs:SetJustifyH("RIGHT")
    secs:SetText("")
    local tile = { key = key, holder = holder, face = face, bg = bg, bgBaked = baked, icon = icon, border = border,
                   abbr = abbr, ring = ring, secs = secs, secsHost = secsHost, cdText = "" }
    SeatSecs(tile, false)
    return tile
end

local function EnsureTile(profile, key)
    local tile = ui.tiles[key]
    if not tile then
        tile = NewTile(key)
        tile.isDot = IsDot(profile, key) and true or false
        ui.tiles[key] = tile
    end
    return tile
end

local function SetIconOf(tile, icon, key)
    local id = icon
    if tile.iconId ~= id then
        tile.iconId = id
        if id ~= nil then tile.icon:SetTexture(id) end
    end
    local has = id ~= nil
    if tile.hasIcon ~= has then
        tile.hasIcon = has
        tile.icon:SetShown(has)
    end
    local text = has and "" or Abbrev(key)
    if tile.abbrText ~= text then
        tile.abbrText = text
        tile.abbr:SetText(text)
    end
end

-- The mockup's .tile.dim is filter: grayscale(1) plus opacity .45 over the WHOLE tile: the icon and
-- fill are desaturated, and the colour-only border and label are re-tinted to their luminance.
local GREY_BORDER, GREY_TEXT = GreyOf(BORDER), GreyOf(COLOR_TEXT)
local function SetDim(tile, dim)
    if tile.dim == dim then return end
    tile.dim = dim
    tile.face:SetAlpha(dim and TUNE.DIM_ALPHA or 1)
    tile.icon:SetDesaturated(dim and true or false)
    if tile.bgBaked then
        tile.bg:SetDesaturated(dim and true or false)
    else
        local c = dim and GreyOf(TILE_FILL) or TILE_FILL
        tile.bg:SetColorTexture(c[1], c[2], c[3], 1)
    end
    Tint(tile.border, dim and GREY_BORDER or BORDER)
    local t = dim and GREY_TEXT or COLOR_TEXT
    tile.abbr:SetTextColor(t[1], t[2], t[3], t[4] or 1)
end

-- Seconds as text, cached per value: the countdown runs at 10 Hz and builds no string after the
-- first time a number is shown.
local secText, minText = {}, {}
local function FormatSeconds(s)
    if s >= 60 then
        local m = math.ceil(s / 60)
        local t = minText[m]
        if not t then t = tostring(m) .. "m"; minText[m] = t end
        return t
    end
    local n = math.ceil(s)
    local t = secText[n]
    if not t then t = tostring(n); secText[n] = t end
    return t
end

local function SetSecs(tile, text)
    if tile.cdText == text then return end
    tile.cdText = text
    tile.secs:SetText(text)
end

-- A DoT slot frame hangs off the AuraContainer, not off its tile, so hiding the tile leaves the
-- engine's timer drawn on an empty spot: it follows the tile by hand. (UNVERIFIED in game: that
-- the engine leaves a hidden slot frame hidden.) Out of combat the HUD's "ooc" look hides every
-- slot too, for the same reason: the row's alpha does not reach them.
local lastOoc = false          -- the last rendered state was ooc (Render sets it, HideAll clears it)
local function ShowSlot(tile, shown)
    if not tile.slot or tile.slotShown == shown then return end
    tile.slotShown = shown
    Quiet(tile.slot, shown and "Show" or "Hide")
end

-- A DoT slot for `tile`, out of combat only. The tile stays usable (without a timer) when any
-- step is refused.
local function AttachDotSlot(profile, tile)
    -- the Gunsight view has no spell tiles, so there is no DoT timer to hang an aura slot on
    if ui.gunsight or tile.slot or tile.slotTried or InCombatSafe() then return end
    local ids, n = DotIds(profile, tile.key)
    if n == 0 then
        tile.slotTried = true
        LogOnce("no_ids", "no spell ids to key an aura slot on for " .. tostring(tile.key) .. "; its tile carries no timer.")
        return
    end
    local container = EnsureContainer("target")
    if not container then return end
    tile.slotTried = true
    local ok, frame = AddSlot(container, "dot_" .. tile.key, "HARMFUL|PLAYER", ids, InitDotSlot(tile))
    if ok then
        tile.slot = frame
        SeatSecs(tile, true)
        -- BuildPending attaches to every DoT tile, in the row or not, and no render follows it: a
        -- slot for a hidden tile, or one made while the last state was ooc, would draw its timer
        if lastOoc or not tile.holder:IsShown() then ShowSlot(tile, false) end
        if CombatHud.IsEnabled() then SetLive(container, true) end
    else
        LogOnce("aura_slot", "AddAuraSlot failed for " .. tostring(tile.key) .. " (" .. tostring(frame) .. "); its tile carries no timer.")
    end
end

-------------------------------------------------------------------------------
-- The spell row
-------------------------------------------------------------------------------

-- The tiles whose seconds count down. One table for the session, compacted in place: the 10 Hz
-- tick allocates nothing.
local cdActive, cdCount = {}, 0
local ticking = false
local acc = 0

local function ClearCd()
    for i = cdCount, 1, -1 do cdActive[i] = nil end
    cdCount = 0
end

local function OnRootUpdate(_, elapsed)
    acc = acc + (PlainNumber(elapsed) or 0)
    if acc < TUNE.CD_THROTTLE then return end
    acc = 0
    CombatHud.stats.cdTicks = CombatHud.stats.cdTicks + 1
    local now = GetTime()
    local kept = 0
    for i = 1, cdCount do
        local tile = cdActive[i]
        local left = tile.cdEnd and (tile.cdEnd - now) or 0
        if left > 0 then
            SetSecs(tile, FormatSeconds(left))
            kept = kept + 1
            cdActive[kept] = tile
        else
            tile.cdEnd = nil
            SetSecs(tile, "")
        end
    end
    for i = cdCount, kept + 1, -1 do cdActive[i] = nil end
    cdCount = kept
    if cdCount == 0 and ticking then
        ticking = false
        ui.root:SetScript("OnUpdate", nil)
    end
end

local function SyncTicker()
    -- the cooldown ticker belongs to the Stack A spell row; the Gunsight view never installs it
    if ui.gunsight then return end
    if cdCount > 0 then
        if not ticking then
            ticking = true
            acc = 0
            ui.root:SetScript("OnUpdate", OnRootUpdate)
        end
    elseif ticking then
        ticking = false
        ui.root:SetScript("OnUpdate", nil)
    end
end

local function LayoutRow(keys)
    local sig = table.concat(keys, ",")
    if ui.rowSig == sig then return end
    ui.rowSig = sig
    local n = #keys
    local width = n * G.TILE + math.max(0, n - 1) * G.TILE_GAP
    ui.row:SetSize(math.max(width, 1), G.ROW_H)
    local shown = {}
    for i, key in ipairs(keys) do
        local tile = ui.tiles[key]
        shown[key] = true
        tile.holder:ClearAllPoints()
        tile.holder:SetPoint("LEFT", ui.row, "LEFT", (i - 1) * (G.TILE + G.TILE_GAP), 0)
        tile.holder:Show()
        ShowSlot(tile, true)
    end
    for key, tile in pairs(ui.tiles) do
        if not shown[key] then
            tile.holder:Hide()
            ShowSlot(tile, false)
        end
    end
end

-- Which spell keys glow, by ring kind: a row entry's own `proc`, and every active proc of
-- state.procs through the profile's overlaySpell.
local function ProcMap(state, profile)
    local procFor = {}
    for _, e in ipairs(state.row) do
        if type(e) == "table" then
            local key, glow = PlainString(e.key), PlainString(e.proc)
            if key and glow then procFor[key] = GlowKind(glow) end
        end
    end
    for _, p in ipairs(state.procs or {}) do
        if type(p) == "table" and PlainBool(p.active) == true then
            local name = PlainString(p.key)
            local spec = name and profile.procs and profile.procs[name]
            local spell = spec and spec.overlaySpell
            if spell and not procFor[spell] then
                procFor[spell] = GlowKind(PlainString(p.glow) or spec.glow)
            end
        end
    end
    return procFor
end

local function RenderRow(state, profile, ooc, procFor)
    local keys, entries = {}, {}
    for _, e in ipairs(state.row) do
        if type(e) == "table" then
            local key = PlainString(e.key)
            if key then
                EnsureTile(profile, key)
                keys[#keys + 1] = key
                entries[#entries + 1] = e
            end
        end
    end
    LayoutRow(keys)
    ui.row:SetShown(#keys > 0)
    ui.row:SetAlpha(ooc and TUNE.OOC_ALPHA or 1)

    local now = GetTime()
    ClearCd()
    local anySlot = false
    for i, key in ipairs(keys) do
        local e, tile = entries[i], ui.tiles[key]
        local missing, onCd = PlainBool(e.missing), PlainBool(e.onCd)
        local cd = PlainNumber(e.cdRemaining)
        local isNext = PlainBool(e.isNext) == true
        SetIconOf(tile, PlainIcon(e.icon) or IconFor(key), key)
        CombatHud.SetTip(tile.holder, key)
        -- mockup order: a DoT that is up wins, then a cooldown, then a missing DoT. The ooc look
        -- (no combat, no next cast) is every tile plain "ready": no dim, no ring (even on a proc or
        -- the next spell), no seconds, no slot timer.
        local up = tile.isDot and missing == false
        SetDim(tile, (not ooc) and (not up) and (onCd == true or (tile.isDot and missing == true)))
        local kind = nil           -- not `ooc and nil or kind`: that reads as kind when ooc is true
        if not ooc then kind = procFor[key] or (isNext and "cyan" or nil) end
        SetRing(tile.ring, kind)
        -- the slot first: whether it exists decides who owns the tile's corner
        if tile.isDot then AttachDotSlot(profile, tile) end
        if tile.slot then anySlot = true end
        ShowSlot(tile, not ooc)
        local remaining = PlainNumber(e.remaining)
        if ooc then
            tile.cdEnd = nil
            SetSecs(tile, "")
        elseif onCd == true and cd and cd > 0 and not up then
            tile.cdEnd = now + cd
            cdCount = cdCount + 1
            cdActive[cdCount] = tile
            SetSecs(tile, FormatSeconds(cd))
        elseif up and not tile.slot and remaining and remaining > 0 then
            -- no engine timer for this DoT (template missing, container given up, or a tile that
            -- appeared in combat): the Hud's own estimate, which it re-pushes each second
            tile.cdEnd = nil
            SetSecs(tile, FormatSeconds(remaining))
        else
            tile.cdEnd = nil
            SetSecs(tile, "")
        end
        SeatSecs(tile, tile.slot ~= nil)
    end
    -- HideAll turns the target container off with the HUD, so a state that comes back turns it on
    if anySlot and containers.target then SetLive(containers.target, true) end
    SyncTicker()
end

-------------------------------------------------------------------------------
-- The next tile
-------------------------------------------------------------------------------

-- The next tile's look at multiplier `k` (1 in the Stack A view, the layout scale in the Gunsight
-- view): the icon inset, type, the keybind and caption seats, and the ring. The ring is rebuilt only
-- when its chamfer, stroke count or glow size changed, so a rescale to the same look builds nothing.
local function StyleNext(n, k)
    local holder = n.holder
    local cut = TileCut(G.NEXT * k)
    local thick = Sz(TUNE.NEXT_BORDER, k)
    local glow = Sz(TUNE.NEXT_GLOW, k)
    SeatIcon(n.icon, holder, thick, cut)
    ApplyFont(n.abbr, Sz(ui.gunsight and (16 + 2 * GRID) or 16, k), COLOR_TEXT)     -- mockup: 16 * U + 2 image px
    ApplyFont(n.key, Sz(CanvasPx(12), k), CYAN, true)
    n.key:ClearAllPoints()
    n.key:SetPoint("TOPRIGHT", holder, "TOPRIGHT", -4 * k, -2 * k)
    ApplyFont(n.lbl, Sz(CanvasPx(9), k), COLOR_MUTED)
    n.lbl:ClearAllPoints()
    n.lbl:SetPoint("TOP", holder, "BOTTOM", 0, -3 * k)
    local sig = cut .. ":" .. thick .. ":" .. glow
    if n.ringSig ~= sig then
        n.ringSig = sig
        local old = n.ring
        local kind = old and old.kind
        if old then SetRing(old, nil) end       -- hides it and clears its kind, so a revisit re-seats it
        -- one ring per look (Theme.AddOuterGlow bakes the size and the chamfer and a frame cannot be
        -- destroyed): a scale already visited shows the ring it built then
        local ring = n.rings[sig]
        if not ring then
            ring = NewRing(holder, holder, 0, thick, glow, cut, ui.gunsight and TUNE.NEXT_GLOW_ALPHA or TUNE.RING_GLOW_ALPHA)
            n.rings[sig] = ring
        end
        n.ring = ring
        if kind then SetRing(ring, kind) end
    end
end

local function NewNextTile()
    local k = K()
    local gun = ui.gunsight
    local holder = CreateFrame("Frame", nil, gun and ui.nextPiece or ui.root)
    if gun then
        holder:SetAllPoints(ui.nextPiece)       -- the anchor's own rect: 56 design px
    else
        holder:SetSize(G.NEXT, G.NEXT)
        holder:SetPoint("RIGHT", ui.gap, "LEFT", -G.NEXT_GAP, 0)
    end
    local bg = holder:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints(holder)
    PaintTileFill(bg)
    local icon = holder:CreateTexture(nil, "ARTWORK")
    icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    -- above the ring (the ring sits RING_LEVEL over the tile)
    local text = CreateFrame("Frame", nil, holder)
    text:SetAllPoints(holder)
    text:SetFrameLevel(holder:GetFrameLevel() + TUNE.RING_LEVEL + 1)
    local abbr = text:CreateFontString(nil, "OVERLAY")
    abbr:SetPoint("CENTER", holder, "CENTER", 0, 0)
    local key = text:CreateFontString(nil, "OVERLAY")
    local lbl = text:CreateFontString(nil, "OVERLAY")
    CombatHud.AttachTip(holder)
    holder:Hide()
    key:Hide()
    local n = { holder = holder, bg = bg, icon = icon, abbr = abbr, key = key, lbl = lbl, rings = {} }
    StyleNext(n, k)
    -- After StyleNext, which gives lbl its font: SetText on a FontString with none throws "Font not set".
    lbl:SetText("NEXT")
    return n
end

-- The key bound to a spell, for the next tile's top right label. The spell's action bar slots come
-- from C_ActionBar.FindSpellActionButtons (it takes the BASE spell id and covers the player's
-- bars only; AllowedWhenTainted, so it answers in combat), each slot is mapped to the binding
-- command of its bar exactly as ActionBars.lua names them, and GetBindingKey / GetBindingText do
-- the rest (the abbreviate flag, as ActionBars.lua's UpdateHotkey passes it). Every call is
-- guarded and every result IsSecret-checked; nothing resolved reads as "no key" and the label is
-- hidden. Slots 1 to 12 are the main bar, and ACTIONBUTTONn follows the CURRENT page, so they
-- count only while the page is 1 (or unreadable); slots 13 to 24, 73 to 144 and 157 up (other
-- pages, bonus bars and forms, vehicle) have no direct binding and are skipped. A vehicle, override, temp shapeshift or
-- bonus bar replaces the main bar's slots, so those slots lose ACTIONBUTTONn too (MainBarPage). Results are cached per spell and the
-- cache is dropped when the bindings, the bars or the spells change.
local SLOT_BINDINGS = {
    { first = 1, prefix = "ACTIONBUTTON", main = true },
    { first = 25, prefix = "MULTIACTIONBAR3BUTTON" },
    { first = 37, prefix = "MULTIACTIONBAR4BUTTON" },
    { first = 49, prefix = "MULTIACTIONBAR2BUTTON" },
    { first = 61, prefix = "MULTIACTIONBAR1BUTTON" },
    { first = 145, prefix = "MULTIACTIONBAR5BUTTON" },
}
-- Bar 6 (MULTIACTIONBAR5) is on MULTIBAR_5_ACTIONBAR_PAGE, slots 145-156, NOT 73-84 (action
-- page 7, a bonus bar). 145 above is page 13's first slot; this re-derives it from the client's
-- own constant exactly as ActionBars.lua does ((page - 1) * 12 + 1), in a block so the two
-- helper values take no file-scope local slot.
do
    local page = _G.MULTIBAR_5_ACTIONBAR_PAGE
    if type(page) == "number" then SLOT_BINDINGS[6].first = (page - 1) * 12 + 1 end
end
CombatHud.slotBindings = SLOT_BINDINGS
local keybindCache = {}

-- The first plain return of fn(...), or nil (missing, throwing or secret).
local function PlainCall(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, r = pcall(fn, ...)
    if not ok or IsSecret(r) then return nil end
    return r
end

-- The page the main bar shows, the same switch as ActionBars.lua's CurrentPage (a file local there,
-- so mirrored here with the same order and the same fallback indexes): vehicle, then override,
-- then temp shapeshift, then bonus, then the paged bar. Each check is plain-or-nothing, so a
-- missing, throwing or secret one reads as "not active"; an unreadable page is nil.
local SPECIAL_PAGES = {
    { has = "HasVehicleActionBar", index = "GetVehicleBarIndex", default = 12 },
    { has = "HasOverrideActionBar", index = "GetOverrideBarIndex", default = 14 },
    { has = "HasTempShapeshiftActionBar", index = "GetTempShapeshiftBarIndex", default = 13 },
    { has = "HasBonusActionBar", index = "GetBonusBarIndex", default = 7 },
}

local function MainBarPage()
    for _, p in ipairs(SPECIAL_PAGES) do
        if PlainCall(_G[p.has]) then return PlainNumber(PlainCall(_G[p.index])) or p.default end
    end
    return PlainNumber(PlainCall(_G.GetActionBarPage))
end

local function CommandForSlot(slot)
    for _, b in ipairs(SLOT_BINDINGS) do
        if slot >= b.first and slot < b.first + 12 then
            if b.main then
                -- ACTIONBUTTONn fires the CURRENT page's nth slot, so slots 1 to 12 are that button
                -- only on page 1 (or when the page cannot be read)
                local page = MainBarPage()
                if page ~= nil and page ~= 1 then return nil end
            end
            return b.prefix .. (slot - b.first + 1)
        end
    end
    return nil
end

-- The spell's ids to ask the bars about: the id its name resolves to now (the current rank) first,
-- then the dictionary's.
local function KeybindIds(key)
    local ids, seen = {}, {}
    local function add(id)
        if type(id) == "number" and not IsSecret(id) and not seen[id] then
            seen[id] = true
            ids[#ids + 1] = id
        end
    end
    local def = Def(key)
    if def then
        for _, name in ipairs(def.names or {}) do
            local _, id = SpellInfo(name)
            add(id)
        end
        for _, id in ipairs(def.ids or {}) do add(id) end
    end
    return ids
end

local function ResolveKeybind(key)
    local find = type(C_ActionBar) == "table" and C_ActionBar.FindSpellActionButtons or nil
    if type(find) ~= "function" then return nil end
    for _, id in ipairs(KeybindIds(key)) do
        local slots = PlainCall(find, id)
        if type(slots) == "table" then
            for _, slot in ipairs(slots) do
                if type(slot) == "number" and not IsSecret(slot) then
                    local command = CommandForSlot(slot)
                    local bound = command and PlainCall(_G.GetBindingKey, command)
                    if type(bound) == "string" and bound ~= "" then
                        local text = PlainCall(_G.GetBindingText, bound, 1)
                        if type(text) == "string" and text ~= "" then return text end
                    end
                end
            end
        end
    end
    return nil
end

local function KeybindFor(key)
    local hit = keybindCache[key]
    if hit == nil then
        hit = ResolveKeybind(key) or false
        keybindCache[key] = hit
    end
    return hit or nil
end

local function RenderNext(state, procFor)
    local n = ui.nextTile
    local nx = state.next
    local key = type(nx) == "table" and PlainString(nx.key) or nil
    if not key then
        n.holder:Hide()
        n.shownKey = nil
        return
    end
    local icon = PlainIcon(nx.icon) or IconFor(key)
    if n.iconId ~= icon then
        n.iconId = icon
        if icon ~= nil then n.icon:SetTexture(icon) end
        n.icon:SetShown(icon ~= nil)
    end
    if n.shownKey ~= key or n.hadIcon ~= (icon ~= nil) then
        n.shownKey, n.hadIcon = key, icon ~= nil
        n.abbr:SetText(icon ~= nil and "" or Abbrev(key))
    end
    CombatHud.SetTip(n.holder, key)
    local bind = KeybindFor(key)
    if n.bindText ~= bind then
        n.bindText = bind
        n.key:SetText(bind or "")
        n.key:SetShown(bind ~= nil)
    end
    -- gold when the next spell is the proc, cyan otherwise
    local kind = GlowKind(PlainString(nx.glow)) or procFor[key] or "cyan"
    SetRing(n.ring, kind)
    n.holder:Show()
end

-------------------------------------------------------------------------------
-- Soul shards
-------------------------------------------------------------------------------

-- Gunsight view (v7 homeShards): the seat under your cast bar is ONE line art crystal and the count. The glyph is the
-- mockup's SH_GLYPH as four textures baked by media/generate_hud_shard.py and tinted here, nothing coloured in the files:
--   glow   a soft violet halo of the outline (the strength glow(K.violet, .5) is baked into its alpha)
--   line   the outline stroke, violet
--   fill   the lit top facet, violet at the mockup's faint alpha (SHARD_FILL_ALPHA)
--   facet  the three interior facet lines, violet mixed SHARD_FACET_MIX toward white
-- The files are canvases larger than the cell they were baked for, so a glyph box scales them by its ratio to
-- that cell. A rescale only re-sizes and re-seats them, it builds nothing.
local SHARD_TEXTURES = {
    glow = MEDIA .. "hud_shard_glow.tga", line = MEDIA .. "hud_shard_line.tga",
    fill = MEDIA .. "hud_shard_fill.tga", facet = MEDIA .. "hud_shard_facet.tga",
}
local SHARD_FILL_ALPHA = 0.3                      -- drawShards: A(.3) before the lit fill
local SHARD_FACET_MIX = 0.45                      -- drawShards: mix(K.violet, '#ffffff', .45) for the facet lines

local function Lighten(c, f)
    return { c[1] + (1 - c[1]) * f, c[2] + (1 - c[2]) * f, c[3] + (1 - c[3]) * f }
end

-- Builds the glyph and the count once. The glow goes on the seat's BACKGROUND layer, the rest on
-- ARTWORK sublevels 0 to 2 (line, fill, facet), all tinted from the Gunsight violet.
local function BuildShardGlyph()
    local facet = Lighten(BORDER, SHARD_FACET_MIX)
    local glyph = {}
    glyph.glow = ui.shards:CreateTexture(nil, "BACKGROUND")
    glyph.glow:SetTexture(SHARD_TEXTURES.glow)
    glyph.glow:SetVertexColor(BORDER[1], BORDER[2], BORDER[3], 1)
    glyph.line = ui.shards:CreateTexture(nil, "ARTWORK", nil, 0)
    glyph.line:SetTexture(SHARD_TEXTURES.line)
    glyph.line:SetVertexColor(BORDER[1], BORDER[2], BORDER[3], 1)
    glyph.fill = ui.shards:CreateTexture(nil, "ARTWORK", nil, 1)
    glyph.fill:SetTexture(SHARD_TEXTURES.fill)
    glyph.fill:SetVertexColor(BORDER[1], BORDER[2], BORDER[3], SHARD_FILL_ALPHA)
    glyph.facet = ui.shards:CreateTexture(nil, "ARTWORK", nil, 2)
    glyph.facet:SetTexture(SHARD_TEXTURES.facet)
    glyph.facet:SetVertexColor(facet[1], facet[2], facet[3], 1)
    ui.shardGlyph = glyph
    ui.shardNum = ui.shards:CreateFontString(nil, "OVERLAY")
    ui.shardNum:SetJustifyH("RIGHT")
end

-- Lit (a shard is held): the halo and the full strokes. Unlit (0 shards): no halo, the mockup's dim strokes.
local function SetShardGlyphLit(glyph, lit)
    local facet = Lighten(BORDER, SHARD_FACET_MIX)
    glyph.glow:SetShown(lit)
    glyph.line:SetVertexColor(BORDER[1], BORDER[2], BORDER[3], lit and 1 or TUNE.HOME_OFF_LINE)
    glyph.fill:SetVertexColor(BORDER[1], BORDER[2], BORDER[3], lit and SHARD_FILL_ALPHA or TUNE.HOME_OFF_FILL)
    glyph.facet:SetVertexColor(facet[1], facet[2], facet[3], lit and 1 or TUNE.HOME_OFF_FACET)
    glyph.line:Show()
    glyph.fill:Show()
    glyph.facet:Show()
end

-- Gunsight view: the count is flush with the right edge of the shard anchor (the tape's edge) and the glyph
-- centre sits HOME_GLYPH_DX image px left of it, one more advance per extra digit. Sizes and seats are
-- re-applied here so a rescale can re-run them over what is already built.
local function SeatShardsGunsight(k)
    local glyph, num = ui.shardGlyph, ui.shardNum
    if not (glyph and num) then return end
    local gs = FS.Gunsight.G
    local imagePx = GRID * k
    local cellW, cellH = TUNE.HOME_GLYPH_W * GRID / gs.SH_W, TUNE.HOME_GLYPH_H * GRID / gs.SH_H
    local x = -(TUNE.HOME_GLYPH_DX + ((ui.shardDigits or 1) - 1) * TUNE.HOME_DIGIT * TUNE.HOME_NUM_PX) * imagePx
    for name, tex in pairs(glyph) do
        local w, h = TUNE.SHARD_CANVAS_W, TUNE.SHARD_CANVAS_H
        if name == "glow" then w, h = TUNE.SHARD_GLOW_CANVAS, TUNE.SHARD_GLOW_CANVAS end
        tex:SetSize(w * cellW * k, h * cellH * k)
        tex:ClearAllPoints()
        tex:SetPoint("CENTER", ui.shards, "RIGHT", x, 0)
    end
    ApplyFont(num, Sz(CanvasPx(TUNE.HOME_NUM_PX), k), (ui.shardCount or 0) >= 1 and Theme.COLOR_TEXT_WHITE or COLOR_MUTED, true, "OUTLINE")
    num:ClearAllPoints()
    num:SetPoint("RIGHT", ui.shards, "RIGHT", 0, 0)
end

-- True while the Class Module draws the count in an area; the seat under your cast bar then stays empty.
-- No seam, a failing or secret answer reads as "not in an area".
local function ClassModuleShowsShards()
    local areas = FS.GunsightAreas
    if type(areas) ~= "table" or type(areas.AreaOf) ~= "function" then return false end
    local ok, area = pcall(areas.AreaOf, "class")
    return ok and not IsSecret(area) and type(area) == "string"
end

-- The glyph and the count; at 0 shards the glyph is dim and the count muted (v7 state D). Nothing for an
-- unknown or secret count, or while the Class Module draws it in an area.
local function RenderShardsGunsight(state, profile)
    local n = PlainNumber(state.shards)
    local has = profile.resource and profile.resource.shards
    if not (has and n and n >= 0) or ClassModuleShowsShards() then
        ui.shards:Hide()
        ui.shardCount = nil
        return false
    end
    n = math.floor(n)
    if ui.shardCount ~= n then
        ui.shardCount = n
        if not ui.shardGlyph then BuildShardGlyph() end
        SetShardGlyphLit(ui.shardGlyph, n >= 1)
        ui.shardDigits = #tostring(n)
        SeatShardsGunsight(K())
        local c = n >= 1 and Theme.COLOR_TEXT_WHITE or COLOR_MUTED
        ui.shardNum:SetTextColor(c[1], c[2], c[3], c[4] or 1)
        ui.shardNum:SetText(tostring(n))
    end
    ui.shards:Show()
    return true
end

local function RenderShards(state, profile)
    if ui.gunsight then return RenderShardsGunsight(state, profile) end
    local n = PlainNumber(state.shards)
    local has = profile.resource and profile.resource.shards
    if not (has and n and n >= 1) then
        ui.shards:Hide()
        ui.shardCount = 0
        return false
    end
    n = math.min(math.floor(n), TUNE.MAX_SHARDS)
    if ui.shardCount ~= n then
        ui.shardCount = n
        ui.shards:SetSize(n * G.SHARD_W + (n - 1) * G.SHARD_GAP, G.SHARD_ROW_H)
        for i = 1, n do
            local d = ui.diamonds[i]
            if not d then
                d = ui.shards:CreateTexture(nil, "ARTWORK")
                d:SetTexture(DIAMOND_TEXTURE)
                d:SetVertexColor(BORDER[1], BORDER[2], BORDER[3], 1)
                d:SetSize(G.SHARD_W, G.SHARD_H)
                d:SetPoint("RIGHT", ui.shards, "RIGHT", -(i - 1) * (G.SHARD_W + G.SHARD_GAP), 0)
                ui.diamonds[i] = d
            end
            d:Show()
        end
        for i = n + 1, #ui.diamonds do ui.diamonds[i]:Hide() end
    end
    ui.shards:Show()
    return true
end

-------------------------------------------------------------------------------
-- Buff reminders
-------------------------------------------------------------------------------

-- The pulsing glow of a buff tile: the box-shadow that fades with the border (@keyframes hudpulse),
-- on its own frame so the icon stays steady. One host (and its pulse) per size and chamfer, built the
-- first time that look is needed, since Theme.AddOuterGlow bakes both.
local function BuffGlow(t, size, cut)
    local key = size .. ":" .. cut
    local hit = t.glows[key]
    if not hit then
        local host = CreateFrame("Frame", nil, t.holder)
        host:SetAllPoints(t.holder)
        pcall(Theme.AddOuterGlow, host, PINK[1], PINK[2], PINK[3], size, 0.5, cut)
        hit = { host = host, pulse = NewPulse(host, 0, 1, BUFF_PULSE_S) }
        t.glows[key] = hit
    end
    return hit
end

local function NewBuffTile(key)
    local k = K()
    local holder = CreateFrame("Frame", nil, ui.buffs)
    holder:SetSize(G.BUFF * k, G.BUFF * k)
    CombatHud.AttachTip(holder)
    local bg = holder:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints(holder)
    PaintTileFill(bg)
    local cut = TileCut(G.BUFF * k)
    local icon = holder:CreateTexture(nil, "ARTWORK")
    SeatIcon(icon, holder, 1, cut)
    icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    local abbr = holder:CreateFontString(nil, "OVERLAY")
    ApplyFont(abbr, Sz(CanvasPx(8), k), COLOR_TEXT)
    abbr:SetPoint("CENTER", holder, "CENTER", 0, 0)
    -- the pulsing part (.hud-buff, hudpulse: the border from alpha .35 to full pink AND a box-shadow
    -- from nothing to 0 0 8px pink, 1.4 s alternate): the border and the glow each get their own
    -- frame so the icon stays steady
    local borderHost = CreateFrame("Frame", nil, holder)
    borderHost:SetAllPoints(holder)
    borderHost:SetFrameLevel(holder:GetFrameLevel() + 1)
    local border = CutOutline(borderHost, PINK, cut, 1, "OVERLAY")
    local pulse = NewPulse(borderHost, BUFF_PULSE_FROM, 1, BUFF_PULSE_S)
    local t = { key = key, holder = holder, bg = bg, icon = icon, abbr = abbr, border = border, pulse = pulse,
                cut = cut, glows = {} }
    local size = Sz(BUFF_GLOW, k)
    local glow = BuffGlow(t, size, cut)
    t.glowHost, t.glowPulse, t.glowSize, t.glowCut = glow.host, glow.pulse, size, cut
    holder:Hide()
    return t
end

-- The aura slot's cover (built once by the engine, kept on `tile.cover`) follows a rescale: its icon is
-- re-seated and its border re-cut to the new chamfer. The cover's frames are the engine's restricted
-- slot button's children, so in combat nothing is touched and `ui.coverPending` finishes it when combat
-- ends (FlushDeferred).
local function RescaleCover(t, cut)
    local c = t.cover
    if not c or c.cut == cut then return end
    if InCombatSafe() then
        ui.coverPending = true
        return
    end
    c.cut = cut
    if c.icon then pcall(SeatIcon, c.icon, c.button, 0, cut) end
    if c.border then pcall(RecutOutline, c.border, cut) end
end

-- A rescale (Gunsight view): the tile's size, icon seat, type, border chamfer, glow and cover follow the
-- new multiplier. The glow host for a size and chamfer is built once and shown again on a revisit.
local function RescaleBuffTile(t, k)
    local cut = TileCut(G.BUFF * k)
    t.holder:SetSize(G.BUFF * k, G.BUFF * k)
    SeatIcon(t.icon, t.holder, 1, cut)
    ApplyFont(t.abbr, Sz(CanvasPx(8), k), COLOR_TEXT)
    if t.cut ~= cut then
        t.cut = cut
        RecutOutline(t.border, cut)
    end
    local size = Sz(BUFF_GLOW, k)
    if t.glowSize ~= size or t.glowCut ~= cut then
        SetPulse(t.glowPulse, false)
        t.glowHost:Hide()
        local glow = BuffGlow(t, size, cut)
        glow.host:Show()
        t.glowHost, t.glowPulse, t.glowSize, t.glowCut = glow.host, glow.pulse, size, cut
    end
    RescaleCover(t, cut)
end

local function EnsureBuffTile(key)
    local t = ui.buffTiles[key]
    if not t then
        t = NewBuffTile(key)
        ui.buffTiles[key] = t
    end
    return t
end

-- Out of combat: the occlusion slots of every tracked aura buff the player knows, so the
-- warnings can be put behind them in a fight. (A buff the player cannot cast has no tile.)
local function EnsureBuffSlots(profile)
    if InCombatSafe() then return end
    for _, sb in ipairs(profile.selfBuffs or {}) do
        local key = sb.spell
        if type(key) == "string" and sb.kind == nil and SpellKnown(key) == true then
            local tile = EnsureBuffTile(key)
            if not tile.slot and not tile.slotTried then
                local ids, n = IdSet(key)
                if n == 0 then
                    tile.slotTried = true
                    LogOnce("no_ids", "no spell ids to key an aura slot on for " .. key .. "; no combat reminder for it.")
                else
                    local container = EnsureContainer("player")
                    if container then
                        tile.slotTried = true
                        local ok, frame = AddSlot(container, "buff_" .. key, "HELPFUL", ids, InitBuffSlot(tile))
                        if ok then
                            tile.slot = frame
                            -- a slot added to a container that is already armed needs it to rescan
                            if container.fsArmed then Quiet(container, "UpdateAllAuras") end
                        else
                            LogOnce("aura_slot", "AddAuraSlot failed for " .. key .. " (" .. tostring(frame) .. "); no combat reminder for it.")
                        end
                    end
                end
            end
        end
    end
    -- Gunsight: arm the container once its slots exist (out of combat; REGEN_ENABLED re-runs this)
    if ui.gunsight then ArmCover(containers.player) end
end

-- The tiles to show: out of combat (and whenever no occlusion is available) exactly what the Hud
-- reports missing; in combat every tracked aura buff that has a slot (its warning sits behind
-- the slot) plus the plain checks (form, pet) the Hud still reports.
local function BuffEntries(state, profile, inCombat)
    local missing, order = {}, {}
    for _, b in ipairs(state.buffsMissing or {}) do
        if type(b) == "table" then
            local key = PlainString(b.key)
            if key and not missing[key] then
                missing[key] = { icon = PlainIcon(b.icon) }
                order[#order + 1] = key
            end
        end
    end
    local out, seen = {}, {}
    local function add(key, icon)
        if seen[key] then return end
        seen[key] = true
        local tile = EnsureBuffTile(key)
        out[#out + 1] = { key = key, icon = icon or IconFor(key), tile = tile }
    end
    -- Gunsight: only an armed container can cover anything; without one the warnings would be false alarms
    local cover = containers.player
    local occlusion = inCombat and cover ~= nil and (not ui.gunsight or cover.fsArmed == true)
    if occlusion then
        for _, sb in ipairs(profile.selfBuffs or {}) do
            local key = sb.spell
            if type(key) == "string" then
                if sb.kind == nil then
                    local t = ui.buffTiles[key]
                    if t and t.slot and SpellKnown(key) == true then add(key, nil) end
                elseif missing[key] then
                    add(key, missing[key].icon)
                end
            end
        end
    end
    for _, key in ipairs(order) do add(key, missing[key].icon) end
    return out
end

local function LayoutBuffs(entries, shardsShown)
    local mode = shardsShown and "shards" or "player"
    local sig = mode
    for _, e in ipairs(entries) do sig = sig .. "," .. e.key end
    if ui.buffSig == sig then return end
    local k = K()
    -- the Gunsight row hangs from the buff anchor (set once at build) whatever the shards do; the
    -- Stack A row is re-anchored under the shard row or under the player tab
    if not ui.gunsight and ui.buffMode ~= mode then
        ui.buffMode = mode
        -- centred on the bar column (the shard row is right aligned, so it cannot be the anchor)
        local drop = G.TAB_H + G.BUFF_TOP
        if shardsShown then drop = G.TAB_H + G.SHARD_TOP + G.SHARD_ROW_H + G.BUFF_TOP end
        ui.buffs:ClearAllPoints()
        ui.buffs:SetPoint("TOP", ui.playerBar, "BOTTOM", 0, -drop)
    end
    ui.buffSig = sig
    local n = #entries
    ui.buffs:SetSize(math.max((n * G.BUFF + math.max(0, n - 1) * G.BUFF_GAP) * k, 1), G.BUFF_ROW_H * k)
    local shown = {}
    for i, e in ipairs(entries) do
        shown[e.key] = true
        local holder = e.tile.holder
        holder:ClearAllPoints()
        holder:SetPoint("LEFT", ui.buffs, "LEFT", (i - 1) * (G.BUFF + G.BUFF_GAP) * k, 0)
    end
    for key, tile in pairs(ui.buffTiles) do
        if not shown[key] then
            tile.holder:Hide()
            SetPulse(tile.pulse, false)
            SetPulse(tile.glowPulse, false)
        end
    end
end

local function RenderBuffs(state, profile, inCombat, shardsShown)
    EnsureBuffSlots(profile)
    local entries = BuffEntries(state, profile, inCombat)
    -- the player container draws only in combat, where the warnings are behind it. Gunsight: alpha only
    -- (SetCover); the buff piece frame, its parent (BuildContainer), carries the fade and the hide
    local live = inCombat and #entries > 0
    -- Gunsight: lastState can lag the client by a Hud tick (the piece's onShow replays it), so the cover
    -- is also gated on the client really being in combat now. Stack A is left as it was.
    if ui.gunsight and live and not InCombatNow() then live = false end
    SetPlayerLive(live and true or false)
    LayoutBuffs(entries, shardsShown)
    for _, e in ipairs(entries) do
        local tile = e.tile
        if e.icon ~= nil then
            if tile.iconId ~= e.icon then
                tile.iconId = e.icon
                tile.icon:SetTexture(e.icon)
            end
            tile.icon:Show()
            tile.abbr:SetText("")
        else
            tile.icon:Hide()
            tile.abbr:SetText(Abbrev(e.key))
        end
        CombatHud.SetTip(tile.holder, e.key)
        tile.holder:Show()
        SetPulse(tile.pulse, true)
        SetPulse(tile.glowPulse, true)
    end
    ui.buffs:SetShown(#entries > 0)
end

-------------------------------------------------------------------------------
-- Idle cast bar row
-------------------------------------------------------------------------------

local idle = { on = false, hint = nil }

local function IdleApi()
    local cb = FS.CastBars
    if type(cb) == "table" and type(cb.SetIdleVisible) == "function" and type(cb.SetIdleHint) == "function" then
        return cb
    end
    return nil
end

local function IdleOn()
    if idle.on or not CombatHud.idleCastBars then return end
    local cb = IdleApi()
    if not cb then
        LogOnce("no_idle_api", "FS.CastBars has no idle row API; the cast bars stay hidden between casts.")
        return
    end
    idle.on, idle.hint = true, nil
    pcall(cb.SetIdleVisible, true)
    pcall(cb.SetIdleHint, "target", nil)
end

local function IdleOff()
    if not idle.on then return end
    idle.on, idle.hint = false, nil
    local cb = IdleApi()
    if cb then pcall(cb.SetIdleVisible, false) end
end

-- The cast bars' resting alpha: the mockup's .hud-stack.ooc .bar-host { opacity: .55 }. FS.CastBars
-- owns the bars' alpha, so the HUD asks through SetRestAlpha (it applies to the resting row only,
-- never to a running cast). Only changes are sent.
local rest = { alpha = 1 }

local function SetBarsRest(alpha)
    -- the rest alpha is the Stack A cast bars' out of combat dimming; the Gunsight view has no
    -- business with them
    if ui.gunsight or rest.alpha == alpha then return end
    local cb = FS.CastBars
    local fn = type(cb) == "table" and cb.SetRestAlpha or nil
    if type(fn) ~= "function" then
        LogOnce("no_rest_alpha_api", "FS.CastBars has no SetRestAlpha; the cast bars are not dimmed out of combat.")
        return
    end
    if pcall(fn, alpha) then
        rest.alpha = alpha
    else
        LogOnce("rest_alpha", "FS.CastBars.SetRestAlpha failed; the cast bars are not dimmed out of combat.")
    end
end

-- The wand (or the class filler spell) the HUD falls back to when it has no next cast.
local function FillerName(profile)
    local want = profile.fillerOrder == "spell" and "spell" or "wand"
    local fallback
    for _, rule in ipairs(profile.rotation or {}) do
        if rule.filler == want then return SpellName(rule.cast) end
        if rule.filler and not fallback then fallback = rule.cast end
    end
    return fallback and SpellName(fallback) or nil
end

local function UpdateIdle(state, profile, inCombat)
    -- the idle row and its tab hint are the Stack A cast bars' (FS.CastBars); not asked in the Gunsight view
    if ui.gunsight then return end
    local wanted = CombatHud.idleCastBars and (TUNE.IDLE_IN_COMBAT or not inCombat)
    if not wanted then
        IdleOff()
        return
    end
    IdleOn()
    if not idle.on then return end
    local nx = state.next
    local key = type(nx) == "table" and PlainString(nx.key) or nil
    local hint = (key and SpellName(key)) or FillerName(profile)
    if hint ~= idle.hint then
        idle.hint = hint
        local cb = IdleApi()
        if cb then pcall(cb.SetIdleHint, "player", hint) end
    end
end

-------------------------------------------------------------------------------
-- Render
-------------------------------------------------------------------------------

local enabled = false
local lastState

local function HideAll()
    lastOoc = false
    if ui.row then ui.row:Hide() end            -- no row in the Gunsight view
    ui.rowSig = nil
    ui.nextTile.holder:Hide()
    ui.shards:Hide()
    ui.shardCount = nil
    ui.buffs:Hide()
    ui.buffSig = nil
    for _, tile in pairs(ui.tiles) do
        tile.holder:Hide()
        tile.cdEnd = nil
        SetRing(tile.ring, nil)
        ShowSlot(tile, false)
    end
    for _, tile in pairs(ui.buffTiles) do
        tile.holder:Hide()
        SetPulse(tile.pulse, false)
        SetPulse(tile.glowPulse, false)
    end
    SetRing(ui.nextTile.ring, nil)
    ui.nextTile.shownKey = nil
    ClearCd()
    SyncTicker()
    SetPlayerLive(false)
    SetLive(containers.target, false)
    SetBarsRest(1)
end

local function Render(state)
    if not enabled then return end
    ResetPass()
    local profile = Profile()
    if type(state) ~= "table" or PlainBool(state.active) ~= true or not profile then
        HideAll()
        return
    end
    -- unknown reads as in combat, the way HudLogic fails closed
    local inCombat = PlainBool(state.inCombat) ~= false
    -- the mockup's two resting looks: "ooc" (no combat, no next cast: dimmed, no next tile) and the
    -- "opener" (a next cast, in or out of combat: full opacity, the next tile up)
    local nx = state.next
    local hasNext = type(nx) == "table" and PlainString(nx.key) ~= nil
    local ooc = (not inCombat) and not hasNext
    lastOoc = ooc
    local procFor = ProcMap(state, profile)
    -- the spell row (tiles, DoT slots, cooldown ticker) and the cast bar dimming are Stack A only
    if not ui.gunsight then RenderRow(state, profile, ooc, procFor) end
    RenderNext(state, procFor)
    local shardsShown = RenderShards(state, profile)
    RenderBuffs(state, profile, inCombat, shardsShown)
    UpdateIdle(state, profile, inCombat)
    SetBarsRest(ooc and TUNE.OOC_ALPHA or 1)
end

local function OnState(state)
    lastState = state
    local ok, err = pcall(Render, state)
    if not ok then LogOnce("render", err) end
end

-------------------------------------------------------------------------------
-- Build and enable
-------------------------------------------------------------------------------

local buildFailed = false

-- The Stack A frames: everything hangs off the cast bar frames (or the fixed seat).
local function BuildStackAUI()
    local bars = { ResolveBars() }
    local targetBar, playerBar = bars[1], bars[2]
    local root = CreateFrame("Frame", "ForeverSTUwaveCombatHud", UIParent)
    root:SetSize(1, 1)
    root:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    ui.root, ui.targetBar, ui.playerBar = root, targetBar, playerBar

    -- spell row: bottom TAB_H (the target tab) + HUD_ROW_GAP above the target bar, centred
    ui.row = CreateFrame("Frame", nil, root)
    ui.row:SetSize(1, G.ROW_H)
    ui.row:SetPoint("BOTTOM", targetBar, "TOP", 0, G.TAB_H + G.ROW_GAP)

    -- the gap: a frame spanning exactly the space between the two bars
    ui.gap = CreateFrame("Frame", nil, root)
    ui.gap:SetPoint("TOPLEFT", targetBar, "BOTTOMLEFT", 0, 0)
    ui.gap:SetPoint("BOTTOMRIGHT", playerBar, "TOPRIGHT", 0, 0)

    ui.nextTile = NewNextTile()

    -- shards: right aligned under the player bar and its hanging tab, plus 6
    ui.shards = CreateFrame("Frame", nil, root)
    ui.shards:SetSize(1, G.SHARD_ROW_H)
    ui.shards:SetPoint("TOPRIGHT", playerBar, "BOTTOMRIGHT", 0, -(G.TAB_H + G.SHARD_TOP))
    ui.shards:Hide()

    -- buffs: centred, re-anchored by LayoutBuffs under the shards or under the tab
    ui.buffs = CreateFrame("Frame", nil, root)
    ui.buffs:SetSize(1, G.BUFF_ROW_H)
    ui.buffs:Hide()
end

-- The Gunsight frames: three piece frames, each exactly on its Gunsight anchor (the registry shows,
-- hides and fades THOSE), and inside each one the frame this file shows and hides itself. No cast bar
-- frame, no gap frame and no spell row exist in this view.
local function BuildGunsightUI()
    local gs = FS.Gunsight
    local anchors = gs.anchors
    local home = gs.root or UIParent
    ui.k = LayoutScale()
    local root = CreateFrame("Frame", "ForeverSTUwaveCombatHud", home)
    root:SetSize(1, 1)
    root:SetPoint("CENTER", home, "CENTER", 0, 0)
    ui.root = root

    local function piece(anchor)
        local f = CreateFrame("Frame", nil, root)
        f:SetAllPoints(anchor)
        return f
    end
    ui.nextPiece = piece(anchors.next)
    ui.shardPiece = piece(anchors.shards)
    ui.buffPiece = piece(anchors.buff)

    ui.nextTile = NewNextTile()

    -- shards: the row IS the anchor (right aligned, sized for four); shard glyph cells seat off its right edge
    ui.shards = CreateFrame("Frame", nil, ui.shardPiece)
    ui.shards:SetAllPoints(ui.shardPiece)
    ui.shards:Hide()

    -- buffs: a row of tiles hanging from the anchor's top centre (one missing buff is the anchor itself)
    ui.buffs = CreateFrame("Frame", nil, ui.buffPiece)
    ui.buffs:SetSize(1, G.BUFF_ROW_H * ui.k)
    ui.buffs:SetPoint("TOP", anchors.buff, "TOP", 0, 0)
    ui.buffs:Hide()
end

local function Rerender()
    if enabled and lastState then OnState(lastState) end
end

-- Hands the three piece frames to the Gunsight registry. Called through FS.Gunsight.OnReady (after
-- login and the first seat). The aura covers are children of the buff piece frame, so the piece's fade and
-- hide carry them with no re-render. Only the buff piece has a hook, onShow (never onHide): a hidden frame
-- may stop its pulse AnimationGroups and SetPulse only plays a group that is not playing, so showing the
-- piece redraws, which restarts them.
local function RegisterPieces()
    if ui.piecesRegistered or not ui.gunsight then return end
    ui.piecesRegistered = true
    local gs = FS.Gunsight
    for _, p in ipairs({ { "next", ui.nextPiece }, { "shard", ui.shardPiece }, { "buff", ui.buffPiece, Rerender } }) do
        local ok, result = pcall(gs.RegisterPiece, p[1], { frame = p[2], onShow = p[3] })
        if not ok or not result then
            LogOnce("piece_" .. p[1], "FS.Gunsight.RegisterPiece refused the " .. p[1] .. " piece (" .. tostring(result) .. ").")
        end
    end
    -- the shard seat follows the Class Module: it hides while an area shows the count, and returns when it leaves
    local areas = FS.GunsightAreas
    if type(areas) == "table" and type(areas.OnAreaChanged) == "function" then
        local ok, err = pcall(areas.OnAreaChanged, Rerender)
        if not ok then LogOnce("area_listener", "FS.GunsightAreas.OnAreaChanged failed (" .. tostring(err) .. ").") end
    end
end

-- A rescale (FS.Layout.OnRescale): every Gunsight size is design px times the layout scale, so each
-- piece is re-derived in place. The scale is compared first; the same scale builds nothing.
local function ApplyGunsightScale()
    if not (ui.gunsight and ui.built) then return end
    local k = LayoutScale()
    if ui.k == k then return end
    ui.k = k
    StyleNext(ui.nextTile, k)
    SeatShardsGunsight(k)
    for _, tile in pairs(ui.buffTiles) do RescaleBuffTile(tile, k) end
    ui.buffSig = nil
    Rerender()
end

local function BuildUI()
    if ui.built then return true end
    if buildFailed then return false end
    local ok, err = pcall(function()
        ui.gunsight = GunsightOn()
        if ui.gunsight then BuildGunsightUI() else BuildStackAUI() end
        ui.built = true
    end)
    if not ok then
        buildFailed = true
        LogOnce("build", err)
        return false
    end
    if ui.gunsight then
        local registered, why = pcall(FS.Gunsight.OnReady, RegisterPieces)
        if not registered then LogOnce("piece_ready", "FS.Gunsight.OnReady failed (" .. tostring(why) .. ").") end
    end
    return true
end

-- Layout.lua loads before this file; with no Layout there is nothing to rescale against.
if FS.Layout and type(FS.Layout.OnRescale) == "function" then
    FS.Layout.OnRescale(function()
        local ok, err = pcall(ApplyGunsightScale)
        if not ok then LogOnce("rescale", err) end
    end)
end

local function StopTicker()
    ClearCd()
    ticking = false
    if ui.root then ui.root:SetScript("OnUpdate", nil) end
end

function CombatHud.IsEnabled() return enabled end

-- True once the UI was built as the Gunsight view (false for Stack A, and before the first build).
function CombatHud.IsGunsight() return ui.gunsight == true end

function CombatHud.Enable()
    if enabled then return true end
    local Hud = FS.Hud
    if type(Hud) ~= "table" or type(Hud.Subscribe) ~= "function" or type(Hud.Unsubscribe) ~= "function" then
        LogOnce("no_hud", "FS.Hud is missing; there is nothing to display.")
        return false
    end
    if not Profile() then return false end
    if not BuildUI() then return false end
    enabled = true
    ui.root:Show()
    for _, tile in pairs(ui.tiles) do
        if tile.slot then SetLive(containers.target, true) break end
    end
    Hud.Subscribe(OnState)
    return true
end

function CombatHud.Disable()
    if not enabled then return end
    enabled = false
    local Hud = FS.Hud
    if type(Hud) == "table" and type(Hud.Unsubscribe) == "function" then pcall(Hud.Unsubscribe, OnState) end
    StopTicker()
    if ui.root then ui.root:Hide() end
    SetLive(containers.target, false)
    SetPlayerLive(false)
    IdleOff()
    SetBarsRest(1)
end

function CombatHud.SetIdleCastBars(on)
    CombatHud.idleCastBars = on and true or false
    if enabled and lastState then
        local profile = Profile()
        if profile then UpdateIdle(lastState, profile, PlainBool(lastState.inCombat) ~= false) end
    elseif not CombatHud.idleCastBars then
        IdleOff()
    end
end

-------------------------------------------------------------------------------
-- Settings, events and the slash command
-------------------------------------------------------------------------------

local DEFAULT_ON = { PRIEST = true, WARLOCK = true, PALADIN = true }

local function Saved()
    local db = type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.combatHud or nil
    return type(db) == "table" and db or nil
end

local function Store()
    if type(ForeverSTUwaveDB) ~= "table" then ForeverSTUwaveDB = {} end
    if type(ForeverSTUwaveDB.combatHud) ~= "table" then ForeverSTUwaveDB.combatHud = {} end
    return ForeverSTUwaveDB.combatHud
end

local function ClassToken()
    local ok, _, token = pcall(UnitClass, "player")
    if ok then return PlainString(token) end
    return nil
end

local started, idleLoaded = false, false

local function TryStart()
    if started then return end
    local Hud = FS.Hud
    if type(Hud) ~= "table" or type(Hud.GetProfile) ~= "function" then
        LogOnce("no_hud", "FS.Hud is missing; there is nothing to display.")
        return
    end
    if not Profile() then return end
    started = true
    local token = ClassToken()
    local saved = Saved()
    local want = saved and type(saved.enabled) == "table" and token and saved.enabled[token]
    if want == nil then want = token ~= nil and DEFAULT_ON[token] == true end
    if want then CombatHud.Enable() end
end

local function LoadIdleSetting()
    if idleLoaded then return end
    idleLoaded = true
    local saved = Saved()
    if saved and saved.idleCastBars ~= nil then CombatHud.idleCastBars = saved.idleCastBars and true or false end
end

local function SetEnabled(on)
    local token = ClassToken()
    if token then
        local store = Store()
        if type(store.enabled) ~= "table" then store.enabled = {} end
        store.enabled[token] = on and true or false
    end
    if on then return CombatHud.Enable() end
    CombatHud.Disable()
    return true
end

local PREFIX = "|cff22e0ffForever STUwave|r: "

local function PrintStatus()
    print(PREFIX .. "combat HUD is " .. (enabled and "ON" or "OFF")
        .. ", idle cast bars " .. (CombatHud.idleCastBars and "ON" or "OFF") .. ".  /fshud on | off | idle on | idle off")
end

SLASH_FSHUD1 = "/fshud"
SlashCmdList["FSHUD"] = function(msg)
    msg = string.lower((tostring(msg or "")))
    local first, second = string.match(msg, "^%s*(%S*)%s*(%S*)")
    if first == "" then
        PrintStatus()
    elseif first == "on" then
        if not Profile() then
            print(PREFIX .. "no HUD profile for this class.")
        else
            SetEnabled(true)
            PrintStatus()
        end
    elseif first == "off" then
        SetEnabled(false)
        PrintStatus()
    elseif first == "idle" and (second == "on" or second == "off") then
        local on = second == "on"
        Store().idleCastBars = on
        CombatHud.SetIdleCastBars(on)
        PrintStatus()
    else
        print(PREFIX .. "/fshud on | off | idle on | idle off")
    end
end

local events = CreateFrame("Frame")
for _, e in ipairs({ "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED",
                     "PLAYER_TARGET_CHANGED",
                     "SPELLS_CHANGED", "PLAYER_LEVEL_UP", "LEARNED_SPELL_IN_TAB",
                     "UPDATE_BINDINGS", "ACTIONBAR_SLOT_CHANGED", "ACTIONBAR_PAGE_CHANGED" }) do
    -- Individually guarded: an event absent on this client (16001 has no
    -- LEARNED_SPELL_IN_TAB) should skip, not abort the whole file.
    pcall(events.RegisterEvent, events, e)
end

local function BuildPending()
    if not enabled or InCombatSafe() then return end
    local profile = Profile()
    if not profile then return end
    ResetPass()
    for _, tile in pairs(ui.tiles) do
        if tile.isDot and not tile.slot then AttachDotSlot(profile, tile) end
    end
    EnsureBuffSlots(profile)
end

local handlers = {}
function handlers.PLAYER_LOGIN()
    LoadIdleSetting()
    TryStart()
end
function handlers.PLAYER_ENTERING_WORLD()
    LoadIdleSetting()
    keybindCache = {}       -- the bars may have been empty at the last look
    TryStart()
end
-- What combat put off: a Stack A container the engine would not move (SetLive left it pending) and the
-- aura covers' re-cut after a rescale (RescaleCover). The one redraw REPLAYS lastState, which at
-- PLAYER_REGEN_ENABLED is usually still the in-combat state until the next Hud push (about 0.2 s), so it
-- does not ask for the state wanted now; that push corrects it. This affects Stack A only (the Gunsight
-- cover is never pending and is zeroed by the handler itself) and the behaviour is unchanged.
local function FlushDeferred()
    local redraw = false
    for _, container in pairs(containers) do
        if container.fsPending then redraw = true end
    end
    if ui.coverPending then
        ui.coverPending = nil
        local cut = TileCut(G.BUFF * K())
        for _, tile in pairs(ui.buffTiles) do RescaleCover(tile, cut) end
    end
    if redraw then Rerender() end
end
function handlers.PLAYER_REGEN_ENABLED()
    -- the covers go dark on the event itself, not on the next Hud push; alpha is always allowed
    if ui.gunsight then SetCover(containers.player, false) end
    BuildPending()
    FlushDeferred()
end
-- Combat lockdown just began. HudLogic's inCombat can turn true (UnitAffectingCombat) a beat before
-- InCombatLockdown does, and that push leaves the Gunsight cover at alpha 0 (it is live only with BOTH);
-- nothing else re-renders when lockdown starts, so replay lastState now. The cover writes alpha only, which
-- combat allows. Stack A is left alone (its container is protected and its state is the Hud's, as before).
function handlers.PLAYER_REGEN_DISABLED()
    if ui.gunsight then Rerender() end
end
function handlers.PLAYER_TARGET_CHANGED()
    -- SetUnit is a no-op for an unchanged token ("target" stays "target"): a retarget needs the
    -- rescan, as Blizzard's TargetFrame does
    if enabled and containers.target then Quiet(containers.target, "UpdateAllAuras") end
end
local function Relearn()
    knownCache = {}
    keybindCache = {}
    if enabled and lastState then OnState(lastState) end
end
handlers.SPELLS_CHANGED = Relearn
handlers.PLAYER_LEVEL_UP = Relearn
handlers.LEARNED_SPELL_IN_TAB = Relearn
-- the next tile's key label: a rebind, or a spell moved on the bars (or the main bar's page). These
-- events fire in bursts (dragging a spell, a page flip) and change nothing but that label, so only
-- the next tile is redrawn, not the whole HUD.
local function RefreshKeybinds()
    keybindCache = {}
    if not (enabled and lastState) then return end
    local profile = Profile()
    if type(lastState) ~= "table" or PlainBool(lastState.active) ~= true or not profile then return end
    RenderNext(lastState, ProcMap(lastState, profile))
end
handlers.UPDATE_BINDINGS = RefreshKeybinds
handlers.ACTIONBAR_SLOT_CHANGED = RefreshKeybinds
handlers.ACTIONBAR_PAGE_CHANGED = RefreshKeybinds

events:SetScript("OnEvent", function(_, event, ...)
    local fn = handlers[event]
    if not fn then return end
    local ok, err = pcall(fn, ...)
    if not ok then LogOnce("event_" .. tostring(event), err) end
end)
