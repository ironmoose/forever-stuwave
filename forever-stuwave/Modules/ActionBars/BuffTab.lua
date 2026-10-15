-- Forever STUwave: Shaman buff tab
--
-- A second Shaman shoulder on the Console chassis, right of the totem tab (the design mockup):
-- 2 columns x 1 row (92.8 x 49 design px) seated at 316 design px, holding two self reminder tiles, IMBUE and SHIELD.
-- The chrome is ClassShoulder.lua's (its `also` shoulder of the Shaman); the tiles are plain SecureActionButtonTemplate
-- buttons on a separate protected host, built the way TotemBar.lua builds the totem tab's: attributes written from Lua
-- out of combat, no secure snippet, no state driver (they do not run on this client). The data model is
-- ShamanBuffs.lua (the weapon tooltip for the imbue, the player aura snapshot for the shield).
--
--   * TWO buttons, FSBuffTabButton1 (IMBUE) and FSBuffTabButton2 (SHIELD), built ONCE, in a fixed order that is the
--     saved keybind order (append only). CLICK FSBuffTabButtonN:LeftButton is declared in Bindings.xml and Quick
--     Keybind mode binds it. A click casts: IMBUE the imbue its chip shows (or the best known one when none is up),
--     SHIELD casts Lightning Shield: type "spell" with the localized spell name.
--   * A tile is the ICON of the spell it casts (the imbue shown, Lightning Shield; Water Shield while that one is up),
--     seated in the cut border like an action button's, with the time or count as a small overlay on a dark label plate,
--     an underline in the state colour and a border: quiet gold underline when up, pink under five minutes (the time
--     replaces the orb count), the icon dimmed and desaturated with a red word when missing (dimmed and desaturated
--     with a "?" when nothing can be read), a dashed underline and a "~" for the shield estimate in combat. The
--     icon is C_Spell.GetSpellTexture of the view's `spellId` (it follows the imbue pick); a spell the client gives
--     no texture for falls back to the mockup's chip (the imbue code, or LS) over the same text.
--     Everything that changes with the state (colours, text, icon, alpha) is a texture or font write, legal in combat.
--   * LOCKED: SHIELD until Lightning Shield is known (level 8) carries NO castable attribute, shows the dotted mold
--     and its unlock level, and dims by alpha; it is never hidden (Show and Hide on a secure button are refused in
--     combat). IMBUE never locks (Rockbiter is level 1); it is absent (hidden, out of combat) while no imbue is known.
--   * SetAttribute, Show, Hide, SetPoint and SetSize on a secure button (or its host) are refused in combat.
--     Everything that does any of them runs out of combat only; combat sets `pendingSync` and PLAYER_REGEN_ENABLED
--     replays it, so an imbue that changes in combat re-aims the click at regen.
--   * No `.bar`, `.isExtra`, `.buttonType`, `CalculateAction` or other field Blizzard's secure click code reads is ever
--     written on a button, and no attribute that makes it borrow its parent's (the "use parent" family): such a write
--     taints the click. Every button carries explicit `type` and `spell` attributes only.
--   * USABILITY: the same feedback as the main bars (ActionBars.lua UpdateUsable, colours Theme.COLOR_OOM and
--     Theme.COLOR_UNUSABLE), asked of the spell the tile casts (C_Spell.IsSpellUsable, else IsUsableSpell): out of mana
--     blends the tile's foreground (chip stroke, glow and code, the time or word, the underline) toward blue,
--     otherwise unusable toward grey, usable is the approved look. The cut border, the plate and the chip fill keep
--     their state colours, and the state colour is blended, not replaced, so the quiet gold, pink and red states
--     still read. A secret, missing or raised answer leaves the tint as it was; a locked or absent tile is plain and
--     never asked. Event driven (SPELL_UPDATE_USABLE, ACTIONBAR_UPDATE_USABLE, the combat edges, a sync, a changed
--     spell): font and texture writes only, a repaint only when the state changed.
--   * VISIBILITY: the tab follows the Console shoulder like the totem tab, Shaman only, and does NOT depend on a
--     target (it is a self buff reminder on the player side). With the Console off it sits beside the totem tab
--     (which then sits above the stance bar).
--
--   * COMBAT STATE: the reads above freeze in combat, so one AuraContainer on "player" inside the host draws the real
--     shield and weapon enchant over the tiles there (see "The engine drawn state in combat" below); out of combat
--     the plain reads draw and the container is invisible.
--
-- Loads after ShamanBuffs.lua, which loads after TotemBar.lua. Nothing here is verified in game.

local _, FS = ...

local BuffTab = {}
FS.BuffTab = BuffTab

local FH = FS.FrameHelpers
local SpellUsability = FH.SpellUsability
local UsabilityColor = FH.UsabilityColor
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

local BT = {
    CLASS = "SHAMAN",
    KEY = "shamanbuff",             -- ClassShoulder's name for this shoulder
    -- the totem tab's numbers (TotemBar.lua), with COLS = 2
    BTN = 38, GAP = 4.8, PAD = 6, PT = 6, PB = 5, COLS = 2,
    DX = 316,                       -- the shoulder's seat on the Console, design px from the chassis left
    BESIDE = 16,                    -- design px between the totem tab and this one with the Console off
    LOCKED_ALPHA = 0.4,
    CHIP_W = 22, CHIP_H = 15, CHIP_TOP = 5, CHIP_C = 3, GLOW_PAD = 3,
    CODE_PX = 10, TEXT_PX = 11, WORD_PX = 9,    -- WORD_PX: the missing word (IMBUE and SHIELD), in PHYSICAL pixels, on the band below
    MIN_PX = 6,                     -- FitPx never goes below this, however small the UI scale
    MISSING = { imbue = "IMBUE", shield = "SHIELD" },   -- the word of the missing look (ShamanBuffs says the same out of combat)
    TEXT_INSET = 3,                 -- design px kept clear on each side of the time or word (the cut border's chamfer)
    ADVANCE = 0.5615,               -- Mononoki Bold's advance per em (every glyph; the font is monospaced)
    CAP = 0.703, ASCENT = 0.879, DESCENT = 0.244,   -- Mononoki Bold's capital height, ascent and descent per em
    TEXT_Y = 27,                    -- the time line's centre, design px below the tile top
    -- the missing word's band (the design mockup, option D): rows 24 to 32 from the tile top
    -- (9 tall), x 3 to 35 (32 wide), the label plate colour at .96. The word is a fontstring of its own on it.
    BAND_TOP = 24, BAND_H = 9, BAND_W = 32, BAND_A = 0.96,
    TICK = 1,                       -- seconds between repaints (the clock text)
    CHIP_GLOW_A = 0.35,             -- the chip's glow alpha while a chip glows (the looks table says which do)
    ICON_RETRY = 2,                 -- seconds before a tile asks again for an icon the client has not answered
    ENGINE_TEMPLATE = "CustomAuraContainerTemplate", ENGINE_LEVEL = 12,    -- the combat state container (engine section)
    UNREADABLE_TICKS = 5,           -- out of combat ticks a slot may stay unreadable before it is logged
    ENGINE_REBUILDS = 3,            -- spellbook driven container rebuilds a session
    ENGINE_RETRY = 10,              -- seconds before the one uncounted retry of a failed build
    ENGINE_LIMIT = 3,               -- failed container builds in a row before the combat state is given up for the session
    TINT_MIX = 0.6,                 -- how far the foreground colours move toward the usability tint (out of mana, unusable)
    -- Append only, never reorder: the index is the saved keybind.
    BUTTONS = {
        { key = "imbue", title = "Weapon imbue", label = "Weapon imbue" },
        { key = "shield", title = "Lightning Shield", label = "Lightning Shield", unlock = 8 },
    },
    ATTRS = { "type", "spell" },
    EVENTS = { "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD" },
    -- state-only events: a repaint of the usability tint, legal in combat
    USABLE_EVENTS = { "SPELL_UPDATE_USABLE", "ACTIONBAR_UPDATE_USABLE", "PLAYER_REGEN_DISABLED" },
    host = nil,
    list = {},          -- the two buttons, by index
    byKey = {},         -- and by key
    built = false,
    owns = false,
    pendingSync = false,
    warned = {},
}
BuffTab.BT = BT

for i, def in ipairs(BT.BUTTONS) do
    _G["BINDING_NAME_CLICK FSBuffTabButton" .. i .. ":LeftButton"] = def.label
end

local IsSecret = FS.IsSecret

local function Scale()
    return (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
end

-- One chat line per distinct problem, once per session (LogDegradeOnce does not dedupe).
local function WarnOnce(key, text)
    if BT.warned[key] then return end
    BT.warned[key] = true
    FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text)
end

-- The same, silent: the failure goes to the degrade log on disk (FS.LogQuiet) and not to chat, for a problem the player cannot
-- act on. `err` is the error value; its text is built inside the pcall, so an error that will not turn into text (a secret)
-- cannot make the report itself throw.
local function QuietOnce(key, text, err)
    if BT.warned[key] then return end
    BT.warned[key] = true
    if FS.LogQuiet then
        pcall(function() FS.LogQuiet(key, err == nil and text or (text .. tostring(err))) end)
    end
end

-- Settings: read by the config window (Unit Frames page), explained there by the `tip` (a ? icon).
BT.SETTINGS = {
    combatstate = {
        key = "buffs.combatstate", default = true, label = "Buff tab combat state",
        tip = "In combat the game itself draws your Lightning Shield and weapon enchant on the Shaman buff tab. "
            .. "Off shows the last known state instead.",
    },
}
BuffTab.SETTINGS = BT.SETTINGS
if FS.Config and FS.Config.RegisterDefault then
    for _, def in pairs(BT.SETTINGS) do FS.Config.RegisterDefault(def.key, def.default) end
end

local function Setting(def)
    local config = FS.Config
    if config and config.Get then
        local value = config.Get(def.key)
        if type(value) == "boolean" then return value end
    end
    return def.default
end

-- The combat state container's bookkeeping (the builder is the engine section below; the painter needs the answer
-- earlier). `armed` is a READBACK: the container read back enabled and shown after the last out of combat arm.
local EngineState = { container = nil, armed = false, failures = 0, gaveUp = false, alpha = nil, templateOk = nil,
    parked = {}, seenIds = nil, rebuilds = 0, passTried = false, noImbue = false, retryAt = nil }
BuffTab.Engine = EngineState

-- true while `button` shows the engine drawn combat state: in combat, the setting on, the container armed (read back),
-- the tile has a slot and no slot of ANY tile is unproven or off its icon. Cheap enough for every paint.
-- true when no tile with slots is unproven or misplaced. ONE predicate for the container's alpha and for every tile, so
-- a tile is live only when the container is really visible (an unproven tile hides the container for all).
local function AllProven()
    for _, button in ipairs(BT.list) do
        local eng = button.fsEngine
        if eng and eng.bad then return false end
    end
    return true
end
EngineState.allProven = AllProven

local function EngineLive(button)
    local eng = button.fsEngine
    if not (eng and eng.declared > 0 and AllProven() and EngineState.armed and InCombatLockdown()) then return false end
    -- an item enchantment tile is live only once a slot was SEEN shown out of combat while the plain read said an imbue
    -- is on (ProveEngine): until then the engine is not known to draw this client's imbues at all, and the tile keeps
    -- its frozen estimate, which counts down from the last read, rather than showing a missing look over a live buff
    if eng.item and not eng.seen then return false end
    return Setting(BT.SETTINGS.combatstate)
end
function BuffTab.EngineLive(key)
    local button = BT.byKey[key]
    return button ~= nil and EngineLive(button)
end

local function IsShaman()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or IsSecret(token) then return false end
    return token == BT.CLASS
end

-------------------------------------------------------------------------------
-- Looks: the mockup's tile states
-------------------------------------------------------------------------------

local looks            -- mode -> colours, built once the theme exists
local GOLD = { 0xd9 / 255, 0xa5 / 255, 0x21 / 255 }        -- #d9a521 the chip gold
local FG = { 0xe9 / 255, 0xe2 / 255, 1 }                   -- #e9e2ff the soft foreground
local BG = { 13 / 255, 6 / 255, 32 / 255 }                 -- #0d0620
local GAP_FILL = { 0x1a / 255, 0x0f / 255, 0x2e / 255 }    -- #1a0f2e the dashes of the estimate underline
local WHITE = { 1, 1, 1 }
local LABEL_PLATE = { 0.024, 0.012, 0.071, 0.78 }              -- rgba(6,3,18,.78) the label plate of the aura tiles

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

local function BuildLooks()
    if looks then return looks end
    local T = FS.Theme
    local white, red, muted, pink = T.COLOR_TEXT_WHITE, T.COLOR_RED, T.COLOR_MUTED, T.COLOR_HEALTH
    local violet = T.COLOR_BORDER
    local hollow = Mix(muted, { 1, 1, 1 }, 0.25)
    local plain = { BG[1], BG[2], BG[3], 0.72 }
    -- ringA and glowA per state live here; the chip glow alpha is BT.CHIP_GLOW_A.
    looks = {
        on = { ring = violet, ringA = 0.35, glowA = 0, plate = plain, chip = GOLD, chipFill = Mix(BG, GOLD, 0.3),
            chipFillA = 1, chipGlow = true, code = white, text = FG, textA = 0.85, line = GOLD, lineA = 0.9, icon = 1 },
        exp = { ring = pink, ringA = 0.9, glowA = 0.5, plate = Mix(BG, pink, 0.1), plateA = 0.9, chip = pink,
            chipFill = Mix(BG, pink, 0.3), chipFillA = 1, chipGlow = true, code = white, text = pink, textA = 1,
            line = pink, lineA = 0.9, icon = 1 },
        warn = { ring = red, ringA = 0.85, glowA = 0.5, plate = Mix(BG, red, 0.1), plateA = 0.9, chip = red,
            chipFill = Mix(BG, red, 0.22), chipFillA = 1, chipGlow = true, code = red, text = red, textA = 1,
            line = red, lineA = 0.9, icon = 0.45, desat = true },
        hollow = { ring = muted, ringA = 0.6, glowA = 0, plate = plain, chip = hollow, chipFill = BG,
            chipFillA = 0.7, chipGlow = false, code = hollow, text = muted, textA = 1, line = muted, lineA = 0.55,
            icon = 0.6, desat = true },
    }
    looks.cyan = { ring = T.COLOR_POWER, ringA = 1, glowA = 0.6 }
    -- ENGINE MODE (PaintButton): exactly the MISSING look, except the red glow. The slot of a buff that is up covers
    -- the whole tile (an opaque plate, the lit icon and a neutral ring, see CoverSlot); the glow is an ADD blend that
    -- reaches outside the tile where nothing can cover it, so it stays off.
    looks.engine = setmetatable({ glowA = 0 }, { __index = looks.warn })
    return looks
end
BuffTab.Looks = BuildLooks

-------------------------------------------------------------------------------
-- Buttons
-------------------------------------------------------------------------------

local function ViewOf(button)
    local view = FS.ShamanBuffs and FS.ShamanBuffs.View()
    return view and view[button.fsKey]
end

local function Plural(n, one, many)
    return n == 1 and one or many
end

-- "8 min left" / "42 sec left" for a number of seconds.
local function LeftText(seconds)
    if seconds >= 60 then
        local n = math.floor(seconds / 60)
        return n .. " min left"
    end
    return math.max(0, math.floor(seconds)) .. " sec left"
end

-- The tooltip as lines { text, color, wrap }: the title in the tile colour, one plain line of state, one line for the
-- click (the mockup's section D). Pure data from the view; the harness reads it.
function BuffTab.TipLines(key)
    local L = BuildLooks()
    local T = FS.Theme
    local v = FS.ShamanBuffs and FS.ShamanBuffs.View()[key]
    if not (v and v.mode) then return nil end
    local gold, pink, red, muted = GOLD, T.COLOR_HEALTH, T.COLOR_RED, T.COLOR_MUTED
    local lines = {}
    local function add(text, color, wrap) lines[#lines + 1] = { text, color, wrap } end
    local click = v.spell and ("Click: cast " .. v.spell .. ".") or nil
    -- in combat with the engine drawing the tile, the frozen times below would be read as fact: say who shows the state
    if BuffTab.EngineLive(key) then
        if key == "imbue" then
            add(v.spell or "Weapon imbue", muted)
            add("The game shows the imbue time in combat.", { 1, 1, 1 }, true)
            add("In combat this shows any weapon enchant.", muted, true)
        else
            add(v.spell or "Lightning Shield", muted)
            add("The game shows your shield and its time in combat.", { 1, 1, 1 }, true)
        end
        if click then add(click, muted, true) end
        return lines
    end
    if key == "imbue" then
        local handName = v.hand == "off" and "Off hand" or "Main hand"
        if v.mode == "on" or v.mode == "exp" then
            add(v.spell or "Weapon imbue", v.mode == "exp" and pink or gold)
            add(handName .. " imbue, " .. LeftText(v.remaining or 0) .. ".", { 1, 1, 1 }, true)
        elseif v.mode == "warn" then
            add(v.spell or "Weapon imbue", red)
            add("No imbue on your " .. (v.lackHand == "off" and "off" or "main") .. " hand.", { 1, 1, 1 }, true)
        else
            add(v.spell or "Weapon imbue", muted)
            add("The imbue time cannot be read yet.", { 1, 1, 1 }, true)
        end
        if click then add(click, muted, true) end
        return lines
    end
    local title = v.spell or "Lightning Shield"
    if v.mode == "locked" then
        add(title, muted)
        add("Opens at level " .. v.unlock .. ".", muted, true)
        return lines
    end
    if v.other then
        add(title, muted)
        add("Water Shield is active.", { 1, 1, 1 }, true)
    elseif v.mode == "on" or v.mode == "exp" then
        if v.estimate then
            add(title, muted)
            local about = v.count and v.count >= 1
                and ("About " .. math.floor(v.count) .. " left.") or "It is up."
            add("Charges cannot be read in combat. " .. about, { 1, 1, 1 }, true)
        else
            add(title, v.mode == "exp" and pink or gold)
            local text
            if v.count and v.count >= 1 then
                text = math.floor(v.count) .. Plural(math.floor(v.count), " charge", " charges")
            end
            if v.remaining then
                text = (text and (text .. ", ") or "") .. LeftText(v.remaining)
            end
            add((text or "Active") .. ".", { 1, 1, 1 }, true)
        end
    elseif v.mode == "warn" then
        add(title, red)
        add("Not active.", { 1, 1, 1 }, true)
    else
        add(title, muted)
        add("Charges cannot be read yet.", { 1, 1, 1 }, true)
    end
    if click then add(click, muted, true) end
    return lines
end

local function ShowTooltip(self)
    local tip = GameTooltip
    if not tip then return end
    local lines = BuffTab.TipLines(self.fsKey)
    if not lines then return end
    FH.AnchorTooltip(self)
    for _, line in ipairs(lines) do
        local c = line[2]
        tip:AddLine(line[1], c[1], c[2], c[3], line[3])
    end
    tip:Show()
end

local function HideTooltip()
    GameTooltip:Hide()
end

-- The icon texture of a spell id (a rank 1 id: every rank wears one icon), or nil when the client will not say. A secret
-- or odd answer is nil too, so the tile keeps its chip.
local function SpellIcon(id)
    if type(id) ~= "number" then return nil end
    local modern = C_Spell and C_Spell.GetSpellTexture
    if type(modern) == "function" then
        local ok, tex = pcall(modern, id)
        if ok and not IsSecret(tex) and (type(tex) == "number" or type(tex) == "string") then return tex end
    end
    local legacy = _G.GetSpellTexture
    if type(legacy) == "function" then
        local ok, tex = pcall(legacy, id)
        if ok and not IsSecret(tex) and (type(tex) == "number" or type(tex) == "string") then return tex end
    end
    return nil
end

local function NewText(parent, px, color)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(fs, px, color)
    return fs
end

-- The highest frame level in a frame's tree (itself and its child frames, `depth` generations down), read out of combat.
-- No table or closure is made: the tick runs this every pass.
local TopLevel
local function TopOfKids(depth, top, ...)
    for i = 1, select("#", ...) do
        local below = TopLevel(select(i, ...), depth)
        if below > top then top = below end
    end
    return top
end
local function TopWithKids(frame, depth, top)
    return TopOfKids(depth - 1, top, frame:GetChildren())
end
function TopLevel(frame, depth)
    local ok, top = pcall(frame.GetFrameLevel, frame)
    if not ok or type(top) ~= "number" then return 0 end
    if depth > 0 and frame.GetChildren then
        local okc, deeper = pcall(TopWithKids, frame, depth, top)
        if okc and type(deeper) == "number" then top = deeper end
    end
    return top
end

-- The level the key label frames sit at: the floor (host + ENGINE_LEVEL + 3), or one over the highest frame found under
-- the container (the client gives a created child its parent's level + 1, so the slots sit at container + 1 and their
-- children above that). One walk per pass; the caller hands the result to every tile's SeatHotkeyHost.
local function HotkeyLevel()
    local level = (BT.host and BT.host:GetFrameLevel() or 0) + BT.ENGINE_LEVEL + 3
    local container = EngineState.container
    if container then level = math.max(level, TopLevel(container, 3) + 1) end
    return level
end

-- The tile's key label (and its plate) rides a frame of its own above the combat container, so the lit cover the slot
-- draws (the slot is a child of the container) never hides it. Out of combat only: StyleButton, SeatHost and the engine
-- passes call this, and it writes a level only when it changed.
local function SeatHotkeyHost(button, level)
    if InCombatLockdown() then return end
    if not button.fsHotkeyHost then
        local hh = CreateFrame("Frame", nil, button)
        hh:SetAllPoints(button)
        hh:EnableMouse(false)
        button.fsHotkeyHost = hh
    end
    local hh = button.fsHotkeyHost
    level = level or HotkeyLevel()
    if hh:GetFrameLevel() ~= level then hh:SetFrameLevel(level) end
    if button.HotKey and button.HotKey:GetParent() ~= hh then button.HotKey:SetParent(hh) end
    if button.fsHotkeyPlate and button.fsHotkeyPlate:GetParent() ~= hh then button.fsHotkeyPlate:SetParent(hh) end
end

local SeatBand

-- The size, in physical pixels, the missing word starts at: BT.WORD_PX, or smaller so it keeps a pixel clear across the
-- band and its capitals keep a pixel clear above and below (the tile shrinks with the UI scale and fonts do not); whole and
-- half pixels, never below BT.MIN_PX. This is the model; the client's own measure (WordFits) has the last word.
local function WordPx(word, bandW, bandH)
    local n = type(word) == "string" and #word or 0
    if n == 0 then return BT.WORD_PX end
    local across = math.floor((bandW - 1) / (n * BT.ADVANCE) * 2) / 2
    local tall = math.floor((bandH - 2) / BT.CAP * 2) / 2
    return math.max(math.min(across, tall, BT.WORD_PX), BT.MIN_PX)
end

-- The width, in UI units, the client gives the word's text as set now, or nil when it will not say (a secret or a missing
-- call). The advance the client uses is hinted to whole pixels, so it can be wider than the font file's advance.
local function MeasuredWidth(fs)
    local call = fs.GetUnboundedStringWidth or fs.GetStringWidth
    if not call then return nil end
    local ok, w = pcall(call, fs)
    if ok and type(w) == "number" and not IsSecret(w) and w == w and w >= 0 and w < math.huge then return w end
    return nil
end

-- Whether the word's fontstring wears the bundled font now. On a cold start the client may not have the file yet and the
-- word is measured in the fallback face (Theme retries the font a few times in the first seconds); an unreadable answer
-- counts as loaded, so nothing waits on it.
local function FontLoaded(fs)
    if not fs.GetFont then return true end
    local ok, face = pcall(fs.GetFont, fs)
    local want = FS.Theme.FONT_MONO
    if not ok or IsSecret(face) or type(face) ~= "string" or type(want) ~= "string" then return true end
    local function leaf(path) return (path:gsub("/", "\\"):match("([^\\]*)$") or path):lower() end
    return leaf(face) == leaf(want)
end

-- Sets the word at its start size and shrinks it in half pixels until the width the client measures fits the band less a
-- pixel. Runs when the tile is seated and again when the bundled font lands after a miss.
local function FitWord(button, fit)
    local fs, px, phys = button.fsWord, 1 / fit.es, fit.start
    FS.Theme.ApplyMono(fs, phys * px, FS.Theme.COLOR_RED)
    if not fit.word then return end
    fs:SetText(fit.word)
    while phys > BT.MIN_PX do
        local w = MeasuredWidth(fs)
        if not w or w * fit.es <= fit.bandW - 1 + 1e-6 then break end
        phys = math.max(BT.MIN_PX, phys - 0.5)
        FS.Theme.ApplyMono(fs, phys * px, FS.Theme.COLOR_RED)
    end
end

-- The fits waiting for the bundled font: the word's fontstring -> its button (weak, so a discarded tile is not kept).
local fitWaiting = setmetatable({}, { __mode = "k" })

-- Fits the word again with the real font. Only a current fit that is not done, only once the font reads back, and never in
-- combat (a font or size write is not allowed there): the fit then stays waiting for PLAYER_REGEN_ENABLED. ApplyMono puts the
-- word's colour back to full red, so the tile is painted again straight after (its saved state cleared, or Paint would
-- skip it), which restores the state's own colour and alpha. The fit is done only if the font still reads back after the
-- write; a miss leaves it open for the next landing.
local function RefitNow(button, fit)
    if button.fsFit ~= fit or fit.done or not FontLoaded(button.fsWord) then return false end
    if InCombatLockdown and InCombatLockdown() then return false end
    FitWord(button, fit)
    fit.done = FontLoaded(button.fsWord)    -- a font that did not take stays open for the next landing
    button.fsSig = nil              -- Paint writes only on a change: this one has to, the word is full red again
    BuffTab.Paint()
    return true
end

-- RefitNow under pcall: a retry callback or timer must never throw into Theme or the timer queue.
local function SafeRefit(button, fit)
    local ok, err = pcall(RefitNow, button, fit)
    if not ok then QuietOnce("bufftab_refit", "the buff tab word could not be fitted again: ", err) end
end

-- Hears Theme's font retry (at login, entering the world and on its timers) and refits the word whose font just landed.
-- A client or Theme without the hook gets timers just after each of Theme's own retries instead.
local fontHooked = false
local function HookFontRetry()
    if fontHooked then return true end
    local T = FS.Theme
    if not (T and type(T.OnFontLanded) == "function") then return false end
    fontHooked = true
    T.OnFontLanded(function(fontString)
        local button = fitWaiting[fontString]
        if button and button.fsFit then SafeRefit(button, button.fsFit) end
    end)
    return true
end

local function WaitForFont(button, fit)
    fitWaiting[button.fsWord] = button
    if HookFontRetry() or not (C_Timer and C_Timer.After) then return end
    for _, delay in ipairs({ 0.1, 2.1, 5.1 }) do
        C_Timer.After(delay, function() SafeRefit(button, fit) end)
    end
end

-- PLAYER_REGEN_ENABLED: a fit that waited out combat runs now.
local function RefitAfterCombat()
    for _, button in ipairs(BT.list) do
        local fit = button.fsFit
        if fit and not fit.done and fit.waiting then SafeRefit(button, fit) end
    end
end

-- Seats the band and the word once per scale (out of combat: StyleButton), in PHYSICAL pixels: `es` is the pixels in one
-- UI unit (FrameHelpers.PixelsPerUnit), not the effective scale. The band is an even number of pixels wide and centred in
-- the tile, its top and height are rounded. The word has NO size of its own, only its centre: the client truncates a
-- fontstring with a fixed width to "SH..." when the text is wider than the box, while one without a width simply grows,
-- so the word can overflow the band at the smallest size but is never cut. The centre is the middle of a box one pixel
-- below the band's top and an even number of pixels tall (a pixel edge), so the capitals' ink (cap top .703 em above the
-- baseline, the line .879 + .244 em tall, centred on that point) stays inside the band. The font is set in UI units for
-- WordPx physical pixels (WORD_PX is a size on the screen, not scaled by the layout scale) and then SHRUNK in half pixels
-- until the width the client measures fits the band less a pixel.
function SeatBand(button, size, s)
    local es = FH.PixelsPerUnit(button)
    local tilePx = math.floor(size * es + 0.5)
    local bandW = math.floor(BT.BAND_W * s * es / 2 + 0.5) * 2
    bandW = math.max(2, math.min(bandW, tilePx - 2))
    local left = math.floor((tilePx - bandW) / 2)
    local top = math.floor(BT.BAND_TOP * s * es + 0.5)
    local height = math.max(2, math.floor(BT.BAND_H * s * es + 0.5))
    local wordH = math.max(2, height - 1 - (height - 1) % 2)
    local px = 1 / es
    button.fsBand:ClearAllPoints()
    button.fsBand:SetPoint("TOPLEFT", button, "TOPLEFT", left * px, -top * px)
    button.fsBand:SetSize(bandW * px, height * px)
    local word = BT.MISSING[button.fsKey]
    local fs = button.fsWord
    fs:ClearAllPoints()
    fs:SetPoint("CENTER", button, "TOPLEFT", (left + bandW / 2) * px, -(top + 1 + wordH / 2) * px)
    local fit = { word = word, start = WordPx(word, bandW, height), bandW = bandW, es = es }
    button.fsFit = fit
    FitWord(button, fit)
    if word and not FontLoaded(fs) then
        fit.waiting = true
        WaitForFont(button, fit)
    end
    if fs.SetWordWrap then pcall(fs.SetWordWrap, fs, false) end
    if button.fsBand.SetSnapToPixelGrid then
        pcall(button.fsBand.SetSnapToPixelGrid, button.fsBand, true)
        if button.fsBand.SetTexelSnappingBias then pcall(button.fsBand.SetTexelSnappingBias, button.fsBand, 0) end
    end
end

-- Runs once per button, from Build and again on every re-seat. Everything that creates a region, hook or frame
-- is guarded so a throw partway is finished by the next Build.
local function StyleButton(button, size, scale)
    local T = FS.Theme
    button:SetSize(size, size)

    if not button.fsPlate then
        button.fsPlate = T.AddCut2Texture(button, T.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    T.SkinCutButton(button, { borderColor = T.COLOR_BORDER, glowAlpha = BuildLooks().on.glowA })

    if not button.fsHooked then
        button.fsHooked = true
        button:HookScript("OnEnter", function(self)
            self.fsHover = true
            BuffTab.Paint()
            ShowTooltip(self)
        end)
        button:HookScript("OnLeave", function(self)
            self.fsHover = nil
            BuffTab.Paint()
            HideTooltip()
        end)
    end

    -- the icon of the spell the tile casts, in the cut border like an action button's (button.icon is the field
    -- SeatCutIcon seats); the chip below is the fallback while the client gives no texture
    if not button.icon then
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        icon:Hide()
        button.icon = icon
    end
    FH.SeatCutIcon(button)

    local textHost = FH.SeatButtonText(button)
    FH.SeatButtonHotkey(button, textHost)
    SeatHotkeyHost(button)

    -- the face: chip, time and underline, hidden as one while the tile is locked
    if not button.fsFace then
        local face = CreateFrame("Frame", nil, textHost)
        face:SetAllPoints(button)
        face:EnableMouse(false)
        button.fsFace = face

        local c = BT.CHIP_C
        local ringPath, glowPath = MEDIA .. "slice_cut2_outline_c3.tga", MEDIA .. "slice_cut2_glow_c3.tga"
        if T.Cut2ButtonSet then
            local ok, ring, glow, used = pcall(T.Cut2ButtonSet, BT.CHIP_C)
            if ok and type(ring) == "string" and type(glow) == "string" then
                ringPath, glowPath, c = ring, glow, used or c
            end
        end
        local chip = {}
        chip.glow = face:CreateTexture(nil, "BACKGROUND", nil, 0)
        chip.glow:SetTexture(glowPath)
        T.ApplyNineSlice(chip.glow, (T.SLICE_CUT2_GLOW_PAD or 4) + c)
        chip.glow:SetBlendMode("ADD")
        chip.fill = face:CreateTexture(nil, "BACKGROUND", nil, 1)
        chip.fill:SetTexture(MEDIA .. "slice_cut2_fill_c" .. c .. ".tga")
        T.ApplyNineSlice(chip.fill, c)
        chip.ring = face:CreateTexture(nil, "ARTWORK", nil, 0)
        chip.ring:SetTexture(ringPath)
        T.ApplyNineSlice(chip.ring, c)
        chip.code = NewText(face, BT.CODE_PX, T.COLOR_TEXT_WHITE)
        chip.code:SetJustifyH("CENTER")
        button.fsChip = chip

        button.fsText = NewText(face, BT.TEXT_PX, T.COLOR_TEXT_WHITE)
        button.fsText:SetJustifyH("CENTER")
        -- the dark label plate behind the time or count while the icon shows (the aura tiles' LABEL_PLATE colour)
        button.fsTextPlate = face:CreateTexture(nil, "ARTWORK", nil, 7)
        button.fsTextPlate:SetColorTexture(LABEL_PLATE[1], LABEL_PLATE[2], LABEL_PLATE[3], LABEL_PLATE[4])
        button.fsTextPlate:SetPoint("TOPLEFT", button.fsText, "TOPLEFT", -2, 0)
        button.fsTextPlate:SetPoint("BOTTOMRIGHT", button.fsText, "BOTTOMRIGHT", 2, 0)
        button.fsTextPlate:Hide()
        -- the missing word's band and word (option D): built once, never re-anchored or resized afterwards except by a rescale
        -- out of combat (StyleButton); a paint only shows, hides, colours and sets text
        button.fsBand = face:CreateTexture(nil, "ARTWORK", nil, 6)
        button.fsBand:SetColorTexture(LABEL_PLATE[1], LABEL_PLATE[2], LABEL_PLATE[3], BT.BAND_A)
        button.fsBand:Hide()
        button.fsWord = NewText(face, BT.WORD_PX, T.COLOR_RED)
        button.fsWord:SetJustifyH("CENTER")        -- a word with no width is centred on its point
        button.fsWord:Hide()
        button.fsLine = face:CreateTexture(nil, "OVERLAY", nil, 2)
        button.fsLine:SetColorTexture(1, 1, 1, 1)
        button.fsDashes = {}
        for i = 1, 4 do
            local dash = face:CreateTexture(nil, "OVERLAY", nil, 3)
            dash:SetColorTexture(GAP_FILL[1], GAP_FILL[2], GAP_FILL[3], 1)
            dash:SetAlpha(0)
            button.fsDashes[i] = dash
        end
    end

    local s = scale
    local chip = button.fsChip
    local x = (BT.BTN - BT.CHIP_W) / 2 * s
    for _, tex in ipairs({ chip.fill, chip.ring }) do
        tex:ClearAllPoints()
        tex:SetPoint("TOPLEFT", button, "TOPLEFT", x, -BT.CHIP_TOP * s)
        tex:SetSize(BT.CHIP_W * s, BT.CHIP_H * s)
    end
    chip.glow:ClearAllPoints()
    chip.glow:SetPoint("TOPLEFT", button, "TOPLEFT", x - BT.GLOW_PAD * s, (-BT.CHIP_TOP + BT.GLOW_PAD) * s)
    chip.glow:SetSize((BT.CHIP_W + 2 * BT.GLOW_PAD) * s, (BT.CHIP_H + 2 * BT.GLOW_PAD) * s)
    chip.code:ClearAllPoints()
    chip.code:SetPoint("CENTER", chip.fill, "CENTER", 0, -0.5 * s)
    button.fsText:ClearAllPoints()
    button.fsText:SetPoint("CENTER", button, "TOP", 0, -BT.TEXT_Y * s)
    SeatBand(button, size, s)
    button.fsLine:ClearAllPoints()
    button.fsLine:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 5 * s, 3 * s)
    button.fsLine:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -5 * s, 3 * s)
    button.fsLine:SetHeight(2 * s)
    for i, dash in ipairs(button.fsDashes) do
        dash:ClearAllPoints()
        dash:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", (5 + 4 + (i - 1) * 6) * s, 3 * s)
        dash:SetSize(2 * s, 2 * s)
    end
    button.fsSig = nil          -- sizes and points were rewritten: paint again (fonts are never scaled)

    -- a locked tile: the dotted mold and its unlock level
    if not button.fsMold then
        local mold = button:CreateTexture(nil, "ARTWORK", nil, 1)
        mold:SetTexture(MEDIA .. "totem_mold.tga")
        local m = T.COLOR_MUTED or { 0.62, 0.58, 0.77, 1 }
        mold:SetVertexColor(m[1], m[2], m[3], 0.9)
        mold:SetAllPoints(button)
        mold:Hide()
        button.fsMold = mold
    end
    if not button.fsLockText then
        local text = textHost:CreateFontString(nil, "OVERLAY")
        T.ApplyMono(text, 11, T.COLOR_MUTED or T.COLOR_TEXT_WHITE)
        text:SetPoint("CENTER", button, "CENTER", 0, 0)
        text:SetText("L" .. (button.fsDef.unlock or 0))
        text:Hide()
        button.fsLockText = text
    end
end

local function BuildButton(host, def, index)
    local button = CreateFrame("Button", "FSBuffTabButton" .. index, host, "SecureActionButtonTemplate")
    button.fsKey = def.key
    button.fsDef = def
    button.fsCommand = "CLICK FSBuffTabButton" .. index .. ":LeftButton"
    button:RegisterForClicks("AnyUp", "AnyDown")
    FH.AttachQuickKeybind(button, button.fsCommand)
    return button
end

-------------------------------------------------------------------------------
-- Painting (texture and font writes only: legal in combat)
-------------------------------------------------------------------------------

local function SetColor(tex, c, a)
    tex:SetVertexColor(c[1], c[2], c[3], a or c[4] or 1)
end

-- A colour moved BT.TINT_MIX of the way toward the usability tint (nil tint: the colour itself), as r, g, b.
local function Shade(c, tint)
    if not tint then return c[1], c[2], c[3] end
    local k = BT.TINT_MIX
    return c[1] + (tint[1] - c[1]) * k, c[2] + (tint[2] - c[2]) * k, c[3] + (tint[3] - c[3]) * k
end

-- The font size for `text`: `px`, or smaller so the string stays inside the tile with TEXT_INSET design px clear on
-- each side. The tile shrinks with the UI scale and fonts do not, so the longest words (SHIELD) are fitted to the
-- current scale; whole and half pixels only (rounded down), never below BT.MIN_PX, and a rescale repaints, which refits.
local function FitPx(text, px)
    local n = type(text) == "string" and #text or 0
    if n == 0 then return px end
    local room = (BT.BTN - 2 * BT.TEXT_INSET) * Scale()
    local fit = math.floor(room / (n * BT.ADVANCE) * 2) / 2
    return math.max(math.min(fit, px), BT.MIN_PX)
end

-- Paints one tile from its view. Writes only when something changed.
local function PaintButton(button, v)
    if button.fsLocked or not button.fsFace or not (v and v.mode) then return end
    local L = BuildLooks()
    local hover = button.fsHover and true or false
    -- ENGINE MODE: in combat a tile with a proven slot shows the MISSING look as its base (looks.engine); the slot
    -- draws the lit icon, the time and the count on top while the buff is really up (see the engine section)
    local engineMode = EngineLive(button)
    -- the state last painted, compared field by field: no signature string or table is built per call
    local estimate, other = v.estimate and true or false, v.other and true or false
    if button.fsSig and button.fsMode == v.mode and button.fsCode == v.code and button.fsTxt == v.text
        and button.fsEst == estimate and button.fsHov == hover and button.fsOth == other
        and button.fsPaintedUse == button.fsUsable and button.fsIconId == v.spellId
        and button.fsEngNow == engineMode
        and (button.fsIconOk or not v.spellId or GetTime() < (button.fsIconRetry or 0)) then
        return
    end
    button.fsSig = true
    button.fsEngNow = engineMode
    button.fsMode, button.fsCode, button.fsTxt = v.mode, v.code, v.text
    button.fsEst, button.fsHov, button.fsOth = estimate, hover, other
    button.fsPaintedUse = button.fsUsable
    -- the icon: asked again on every paint while the client has not answered (the signature above lets that through)
    local iconTex = SpellIcon(v.spellId)
    button.fsIconId, button.fsIconOk = v.spellId, iconTex ~= nil
    button.fsIconRetry = GetTime() + BT.ICON_RETRY
    local tint = UsabilityColor(button.fsUsable)
    local look = engineMode and L.engine or (L[v.mode] or L.hollow)
    local missing = engineMode or v.mode == "warn"
    local word = missing and (engineMode and BT.MISSING[button.fsKey] or v.text) or nil
    if word == "" then word = nil end
    -- the missing word has its own band and fontstring (option D); the time line and its plate show only while up
    local text = (not word) and v.text or nil
    local skin = button.fsSkin
    if skin and skin.border and skin.border.ring then
        local r = hover and L.cyan.ring or look.ring
        skin.border.ring:SetVertexColor(r[1], r[2], r[3], hover and L.cyan.ringA or look.ringA)
    end
    if skin and skin.glow then
        local g = hover and L.cyan.ring or look.ring
        skin.glow:SetVertexColor(g[1], g[2], g[3], hover and L.cyan.glowA or look.glowA)
    end
    SetColor(button.fsPlate, look.plate, look.plateA or look.plate[4])
    local chip = button.fsChip
    SetColor(chip.fill, look.chipFill, look.chipFillA)
    local r, g, b = Shade(look.chip, tint)
    chip.ring:SetVertexColor(r, g, b, 1)
    chip.glow:SetVertexColor(r, g, b, look.chipGlow and BT.CHIP_GLOW_A or 0)
    r, g, b = Shade(look.code, tint)
    chip.code:SetTextColor(r, g, b, 1)
    chip.code:SetText(v.code or "")
    -- icon or chip: one of them. The chip keeps its colours either way, so the fallback is always painted.
    local icon = button.icon
    if iconTex then
        FH.SetSpellIcon(icon, iconTex)
        r, g, b = Shade(WHITE, tint)
        local k = look.icon or 1
        icon:SetVertexColor(r * k, g * k, b * k, 1)
        icon:SetDesaturated(look.desat and true or false)
        icon:Show()
        chip.fill:Hide(); chip.ring:Hide(); chip.glow:Hide(); chip.code:Hide()
        button.fsTextPlate:SetShown(text ~= nil and text ~= "")
    else
        icon:Hide()
        chip.fill:Show(); chip.ring:Show(); chip.glow:Show(); chip.code:Show()
        button.fsTextPlate:Hide()
    end
    local size = FitPx(text, BT.TEXT_PX)
    if button.fsTextPx ~= size then
        button.fsTextPx = size
        FS.Theme.ApplyMono(button.fsText, size, look.text)
    end
    r, g, b = Shade(look.text, tint)
    button.fsText:SetTextColor(r, g, b, look.textA)
    button.fsText:SetText(text or "")
    -- the band and the word: colour, text and visibility only (their points, size and font were seated out of combat)
    button.fsBand:SetShown(word ~= nil)
    button.fsWord:SetShown(word ~= nil)
    if word then
        button.fsWord:SetTextColor(r, g, b, look.textA)
        button.fsWord:SetText(word)
    end
    r, g, b = Shade(look.line, tint)
    button.fsLine:SetVertexColor(r, g, b, look.lineA)
    for _, dash in ipairs(button.fsDashes) do dash:SetAlpha((not engineMode and v.estimate) and 1 or 0) end
    -- the imbue slots' own lit icons follow the tile's icon (an item enchantment slot has no aura icon of its own).
    -- Out of combat only: a slot frame is restricted in combat, and the regen repaint (the engine mode flips) writes it.
    local eng = button.fsEngine
    if eng and not InCombatLockdown() then
        for _, part in ipairs(eng.parts) do
            if part.lit then pcall(part.lit.SetTexture, part.lit, iconTex) end
        end
    end
end

-------------------------------------------------------------------------------
-- The engine drawn state in combat (UNVERIFIED live)
-------------------------------------------------------------------------------
--
-- Addon aura and weapon reads are refused in combat, so the tiles above freeze there (an estimate with a "~"). The
-- engine still draws the player's own buff row in combat, so the same trick as CombatHud.lua's buff covers and DoT
-- timers (read its header, "THE OCCLUSION TRICK" and "DOT TIMERS") is used: ONE AuraContainer on unit "player" inside the
-- tab host, with
--   * SHIELD: one AddAuraSlot (HELPFUL, candidateFilters.includeSpellIDs = every Lightning Shield and Water Shield
--     rank id, ShamanBuffs.ShieldIds), whose frame sits exactly on the tile's icon rect, above the tile's own icon.
--     Its initializeFrame builds the lit icon (SetIcon: the aura's own icon, so a Water Shield shows as itself), the
--     engine's duration text (SetDurationText) bottom centre where the tile's time sits, and the orb count
--     (SetApplicationCount) top right, each on a dark label plate.
--   * IMBUE: AddItemEnchantment on the off hand and the main hand slots (the way Buffs.lua's AddNativeEnchants does),
--     both on the tile's icon rect, the main hand drawn last so it wins an overlap. An enchantment slot's own icon is
--     probably the weapon's, not the imbue's, so no SetIcon here: each frame carries OUR lit icon texture (the imbue
--     the tile shows, rewritten out of combat) and the engine's duration text. LIMIT: an item enchantment slot has no
--     spell filter, so a sharpening stone, a weightstone or an oil lights the tile in combat too, and the lit icon is
--     the pick, not the actual enchant. The in combat tooltip says so.
-- While the buff is up the engine draws the slot over the tile; when it falls off the slot draws nothing and the tile's
-- own MISSING look shows through (the dim icon and the red IMBUE / SHIELD word on its plate), and it is covered again
-- when the buff is recast. No Lua ever learns which: the base is the missing look always, the slot is the only thing
-- that says "up". Only what the slot's lit icon covers is red (its rect is the tile's icon rect and it draws above every
-- tile frame); the border ring and glow, the button plate and the underline are outside it and stay neutral.
--
-- In combat a tile with a slot is in ENGINE MODE (PaintButton, EngineLive): the missing look as the base (looks.engine:
-- a dim desaturated icon and the red word, a neutral ring, no count, no underline, no dashes), because the frozen reads
-- would lie. It
-- is only entered on PROOF: the container read back enabled and shown after the last out of combat arm (CombatHud's
-- live CORRECTION: a refused arm or a re-anchored slot shows a confident wrong "not active" for the whole fight), and
-- every slot frame of the tile was PROVEN on the tile's icon rect: its GetLeft/GetTop read BEFORE anything re-seats it
-- (so an override by the engine's layout is seen) and equal to the icon's, by a proof pass out of combat on every
-- tick (a layout pass after our seat is caught within a second). A slot frame that does not exist yet proves nothing
-- wrong and draws nothing; one that exists but cannot be read, or was built in combat (the engine's layout pass comes
-- after init, and combat cannot look), is UNPROVEN and its tile is not live until the next out of combat proof. A
-- tile with an unproven or misplaced slot also hides the container (alpha 0 for all), so no stray lit icon draws over a
-- tile that shows its frozen state. The setting `buffs.combatstate` (default on) turns it off: the tiles keep today's
-- frozen estimate and the container stays invisible. Out of combat the plain reads stay authoritative and the container
-- is invisible (alpha 0), so nothing is drawn twice. The tile's own count never shows in combat: if the engine draws
-- no orb count the tile shows none rather than a stale one.
--
-- Rules (CombatHud's live CORRECTION): the container is built, given its unit, enabled and shown OUT OF COMBAT only
-- (Sync, and again at PLAYER_REGEN_ENABLED when it reads back off); in combat the only write is SetAlpha (1 in combat,
-- 0 out). initializeFrame may run lazily (when the engine first needs a frame), so it seats its own texts and icon on its
-- own and nothing depends on a later pass; every slot region is written out of combat only afterwards (a slot frame is
-- restricted in combat). The slots' mouse is switched off at init and READ BACK out of combat after every seat; a slot
-- found with the mouse on propagates clicks and motion to the tile below (SetPropagateMouse*), else its mouse is
-- switched off again, and one line is logged. A failed build logs once and leaves the tiles as they were (the frozen
-- estimate); a failed slot costs just its tile; a failed imbue slot parks the whole container (no stray off hand slot)
-- and the rebuild goes without imbue slots. BT.ENGINE_LIMIT failed out of combat PASSES in a row (one attempt per pass,
-- a pass ends at regen) give the path up for the session. Every failed or replaced container is parked and tracked. The
-- KNOWN LIMIT: a slot's position cannot be read in combat, so an engine re-anchor DURING a fight is not seen; the proof
-- is the last out of combat pass and the next one corrects it. The shield id set is checked out of combat when the
-- spellbook changes; it rebuilds only when an id never seen before appears, at most BT.ENGINE_REBUILDS times a session
-- (then a line says to /reload). A failed build gets one uncounted retry BT.ENGINE_RETRY seconds later from the tick (a
-- login that failed once would otherwise lose whole fights). The state for the live test is written to
-- ForeverSTUwaveDB.buffTabEngine.line (SaveStatus), on disk after a /reload.
-- UNVERIFIED in game: the slot rendering over the tiles, the layering, the item enchantment slot frames, whether the
-- engine draws an orb count at all, and what an item enchantment slot reports.

local function Quiet(obj, method, ...)
    local okGet, fn = pcall(function() return obj[method] end)
    if okGet and type(fn) == "function" then return (pcall(fn, obj, ...)) end
    return true
end

local function EngineTemplate()
    if EngineState.templateOk ~= nil then return EngineState.templateOk end
    local info = C_XMLUtil and C_XMLUtil.GetTemplateInfo
    local ok = false
    if type(info) == "function" then
        local good, result = pcall(info, BT.ENGINE_TEMPLATE)
        ok = good and result ~= nil and result ~= false
    end
    EngineState.templateOk = ok
    return ok
end

-- true when the container reads back in the wanted state; a blocked call raises nothing, so only a readback proves it.
local function ContainerIs(container, live)
    local ok, isShown = pcall(container.IsShown, container)
    if ok and not IsSecret(isShown) and (isShown and true or false) ~= live then return false end
    local okFn, fn = pcall(function() return container.IsEnabled end)
    if okFn and type(fn) == "function" then
        local okE, enabled = pcall(fn, container)
        if okE and not IsSecret(enabled) and (enabled and true or false) ~= live then return false end
    end
    return true
end

-- A slot text seated for the current scale: the engine time where the tile's own time sits, the orb count top right,
-- each with its label plate following it. Runs inside initializeFrame and again from SeatEngine on a rescale.
local function SeatPart(tile, part, s)
    if part.dur then
        pcall(function()
            part.dur:ClearAllPoints()
            part.dur:SetPoint("CENTER", tile, "TOP", 0, -BT.TEXT_Y * s)
        end)
    end
    if part.count then
        pcall(function()
            part.count:ClearAllPoints()
            part.count:SetPoint("TOPRIGHT", tile, "TOPRIGHT", -4 * s, -4 * s)
        end)
    end
end

local function NewPlate(slot, text)
    local plate = slot:CreateTexture(nil, "ARTWORK", nil, 6)
    plate:SetColorTexture(LABEL_PLATE[1], LABEL_PLATE[2], LABEL_PLATE[3], LABEL_PLATE[4])
    plate:SetPoint("TOPLEFT", text, "TOPLEFT", -2, 0)
    plate:SetPoint("BOTTOMRIGHT", text, "BOTTOMRIGHT", 2, 0)
    return plate
end

-- The lit look of the WHOLE tile, drawn by the slot frame (a child of the slot, so the engine shows and hides it with
-- the slot: SetShown(aura ~= nil), Blizzard_CustomAuraButton ApplyVisibility). Under the tile's missing look (red ring,
-- plate, dim icon, red word) a slot with an aura draws: an opaque plate of the tile's shape, the lit icon on top of it
-- (the aura's own), and an opaque ring of the lit colour over the tile's own ring. Both sit on the TILE, not the slot, so
-- they reach the tile's edge. Built and seated out of combat (initializeFrame); nothing is anchored or read in combat.
-- A tile with no readable plate or ring texture simply gets no cover on that part.
local function CoverSlot(tile, part)
    local slot, skin = part.slot, tile.fsSkin
    local L = BuildLooks()
    local function Layer(source, layer, sublevel, color, margin)
        local path = source and source:GetTexture()
        if path == nil then return nil end
        local tex = slot:CreateTexture(nil, layer, nil, sublevel)
        tex:SetTexture(path)
        FS.Theme.ApplyNineSlice(tex, margin)
        tex:SetPoint("TOPLEFT", tile, "TOPLEFT", 0, 0)
        tex:SetPoint("BOTTOMRIGHT", tile, "BOTTOMRIGHT", 0, 0)
        tex:SetVertexColor(color[1], color[2], color[3], 1)
        return tex
    end
    -- the margins come from where the tile's own chrome takes them: the plate from AddCut2Texture (SLICE_CUT_MARGIN), the
    -- ring from the skin's chamfer
    part.coverPlate = Layer(tile.fsPlate, "BACKGROUND", -8, BG, FS.Theme.SLICE_CUT_MARGIN)
    part.coverRing = Layer(skin and skin.border and skin.border.ring, "OVERLAY", 7, Mix(BG, L.on.ring, L.on.ringA),
        skin and skin.chamfer)
end

-- The slot's frame, built by the engine (at AddAuraSlot, or later, when it first needs one): no mouse (the secure tile
-- below keeps clicks and the tooltip), seated on the tile's icon rect, the lit icon and the engine's texts. Each step on
-- its own, so a missing method stops nothing. It registers its parts on the tile, one entry per frame.
local function InitSlot(tile, ownIcon)
    local eng = tile.fsEngine                         -- captured at add time: the one this slot was declared on
    return function(slot)
        Quiet(slot, "SetMouseMotionEnabled", false)
        Quiet(slot, "SetMouseClickEnabled", false)
        Quiet(slot, "SetHideTooltipInCombat", true)
        if tile.fsEngine ~= eng then return end      -- a parked container's late frame is not this tile's
        local part = { slot = slot, ok = false }
        eng.parts[#eng.parts + 1] = part
        eng.bad = true                               -- UNPROVEN until a proof pass out of combat has read it
        tile.fsSig = nil
        pcall(function() slot:SetAllPoints(tile.icon) end)
        pcall(CoverSlot, tile, part)
        pcall(function()
            local lit = slot:CreateTexture(nil, "ARTWORK")
            lit:SetAllPoints(slot)
            lit:SetTexCoord(0.07, 0.93, 0.07, 0.93)
            if ownIcon then
                part.lit = lit
                local v = ViewOf(tile)
                local tex = SpellIcon(v and v.spellId)
                if tex then lit:SetTexture(tex) end
            else
                slot:SetIcon(lit)
            end
        end)
        pcall(function()
            local dur = slot:CreateFontString(nil, "OVERLAY")
            FS.Theme.ApplyMono(dur, BT.TEXT_PX, FS.Theme.COLOR_TEXT_WHITE)
            dur:SetJustifyH("CENTER")
            part.dur = dur
            part.durPlate = NewPlate(slot, dur)
            slot:SetDurationText(dur, {})
        end)
        if not ownIcon then
            pcall(function()
                local count = slot:CreateFontString(nil, "OVERLAY")
                FS.Theme.ApplyMono(count, BT.CODE_PX, FS.Theme.COLOR_TEXT_WHITE)
                count:SetJustifyH("RIGHT")
                part.count = count
                part.countPlate = NewPlate(slot, count)
                slot:SetApplicationCount(count)
            end)
        end
        SeatPart(tile, part, Scale())
    end
end

local function SortOptions()
    local method = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
    local direction = type(_G.AuraContainerSortDirection) == "table" and _G.AuraContainerSortDirection.Normal or nil
    return method, direction
end

local function NewEngineTile(tile)
    tile.fsEngine = { declared = 0, parts = {}, bad = false }
    return tile.fsEngine
end

local function AddShieldSlot(container, tile, ids)
    local eng = NewEngineTile(tile)
    local method, direction = SortOptions()
    local ok, err = pcall(container.AddAuraSlot, container, "shield", "HELPFUL", {
        initializeFrame = InitSlot(tile, false),
        candidateFilters = { includeSpellIDs = ids },
        sortMethod = method,
        sortDirection = direction,
    })
    if ok then
        eng.declared = 1
    else
        tile.fsEngine = nil
        WarnOnce("bufftab_engine_shield", "the shield tile carries no combat state (" .. tostring(err) .. ")")
    end
end

-- Both hands, or an error table { imbue = message }: a hand that got in before a later one failed would stay a stray
-- slot on the container, so the caller parks the whole container and rebuilds without imbue slots.
local function AddImbueSlots(container, tile, s)
    if type(container.AddItemEnchantment) ~= "function" or type(container.SetItemEnchantmentLayout) ~= "function"
        or type(_G.AuraContainerItemEnchantmentSlot) ~= "table" then
        WarnOnce("bufftab_engine_imbue", "the imbue tile carries no combat state (this client has no item enchantment slots)")
        return
    end
    local eng = NewEngineTile(tile)
    eng.item = true
    local ok, err = pcall(function()
        local layout = { elementSpacing = 0, lineSpacing = 0, groupSpacing = 0, groupLineSpacing = 0,
            elementWidth = BT.BTN * s, elementHeight = BT.BTN * s }
        if type(_G.CustomAuraContainerItemEnchantmentPlacement) == "table" then
            layout.placement = _G.CustomAuraContainerItemEnchantmentPlacement.AfterAuraGroups
        end
        container:SetItemEnchantmentLayout(layout)
        local slots = _G.AuraContainerItemEnchantmentSlot
        container:AddItemEnchantment(slots.OffHand, { initializeFrame = InitSlot(tile, true) })
        eng.declared = eng.declared + 1
        container:AddItemEnchantment(slots.MainHand, { initializeFrame = InitSlot(tile, true) })
        eng.declared = eng.declared + 1
    end)
    if not ok then
        tile.fsEngine = nil
        error({ imbue = tostring(err) }, 0)
    end
end

local function ParkContainer(container)
    Quiet(container, "SetEnabled", false)
    Quiet(container, "Hide")
    Quiet(container, "SetAlpha", 0)
    EngineState.parked[#EngineState.parked + 1] = container
end

local function ClearEngineTiles()
    for _, button in ipairs(BT.list) do
        button.fsEngine = nil
        button.fsSig = nil
    end
end

-- Builds the container with its slots, out of combat. Returns the container and the shield id set it covers. Any failure parks
-- the container (a frame cannot be destroyed) and clears the tiles' slots before raising.
local function BuildContainer(withImbue)
    local container = CreateFrame("AuraContainer", nil, BT.host, BT.ENGINE_TEMPLATE)
    local ids
    local ok, err = pcall(function()
        local s = Scale()
        container:SetSize(1, 1)
        container:SetPoint("CENTER", BT.host, "CENTER", 0, 0)
        container:SetFrameLevel(BT.host:GetFrameLevel() + BT.ENGINE_LEVEL)
        container:SetUnit("player")
        container:SetAlpha(0)
        local shield, imbue = BT.byKey.shield, BT.byKey.imbue
        ids = FS.ShamanBuffs.ShieldIds()
        if shield then AddShieldSlot(container, shield, ids) end
        if imbue and withImbue then AddImbueSlots(container, imbue, s) end
        container:SetEnabled(true)
        container:Show()
    end)
    if not ok then
        ParkContainer(container)
        ClearEngineTiles()
        error(err, 0)
    end
    return container, ids
end

local function Rect(region)
    local okL, left = pcall(region.GetLeft, region)
    local okT, top = pcall(region.GetTop, region)
    local okR, right = pcall(region.GetRight, region)
    local okB, bottom = pcall(region.GetBottom, region)
    if okL and okT and okR and okB and type(left) == "number" and type(top) == "number" and type(right) == "number"
        and type(bottom) == "number" and not IsSecret(left) and not IsSecret(top) and not IsSecret(right)
        and not IsSecret(bottom) then
        return left, top, right, bottom
    end
    return nil
end

-- true when `slot` stands on `icon` (all four edges), false when it stands elsewhere, nil when either cannot be read.
local function Placed(slot, icon)
    local sl, st, sr, sb = Rect(slot)
    local il, it, ir, ib = Rect(icon)
    if not (sl and il) then return nil end
    return math.abs(il - sl) <= 1.5 and math.abs(it - st) <= 1.5 and math.abs(ir - sr) <= 1.5
        and math.abs(ib - sb) <= 1.5
end

-- true when `slot` is hidden (the engine hides a slot with no aura). An unreadable answer is "not hidden".
local function Hidden(slot)
    local ok, shown = pcall(slot.IsShown, slot)
    return ok and not IsSecret(shown) and shown == false
end

local function GuardMouse(slot)
    local function On(method)
        local ok, fn = pcall(function() return slot[method] end)
        if not (ok and type(fn) == "function") then return false end
        local okCall, answer = pcall(fn, slot)
        return okCall and not IsSecret(answer) and answer == true
    end
    if not (On("IsMouseClickEnabled") or On("IsMouseMotionEnabled")) then return end
    WarnOnce("bufftab_engine_mouse", "a combat state slot has the mouse on; clicks and the tooltip are kept for the tile")
    if type(slot.SetPropagateMouseClicks) == "function" and type(slot.SetPropagateMouseMotion) == "function" then
        Quiet(slot, "SetPropagateMouseClicks", true)
        Quiet(slot, "SetPropagateMouseMotion", true)
    else
        Quiet(slot, "SetMouseClickEnabled", false)
        Quiet(slot, "SetMouseMotionEnabled", false)
    end
end

-- What a slot frame shows right now, for the tile's live test and the state line (out of combat only, plain values
-- only): shownCode 0 unknown, 1 hidden, 2 shown; w and h its size in whole px (0 unknown).
-- One plain boolean answer of `slot` to `method`, or nil and why not: "error", "secret", "type:<type>" or "missing".
local function PlainBoolean(slot, method)
    local call = slot[method]
    if type(call) ~= "function" then return nil, "missing" end
    local ok, v = pcall(call, slot)
    if not ok then return nil, "error" end
    if IsSecret(v) then return nil, "secret" end
    if type(v) ~= "boolean" then return nil, "type:" .. type(v) end
    return v
end

local function ReadPart(part)
    local slot = part.slot
    -- whether the slot draws: IsShown, else IsVisible when the client keeps IsShown from us; why it was unknown is kept for
    -- the state line (a slot that draws an aura may be secret by design)
    local shown, why = PlainBoolean(slot, "IsShown")
    if shown == nil then
        local visible, why2 = PlainBoolean(slot, "IsVisible")
        if visible ~= nil then shown = visible else why = why .. "/" .. why2 end
    end
    part.shownCode = shown == nil and 0 or (shown and 2 or 1)
    part.shownWhy = shown == nil and why or nil
    local okW, w = pcall(slot.GetWidth, slot)
    local okH, h = pcall(slot.GetHeight, slot)
    part.w = (okW and type(w) == "number" and not IsSecret(w)) and math.floor(w + 0.5) or 0
    part.h = (okH and type(h) == "number" and not IsSecret(h)) and math.floor(h + 0.5) or 0
    -- the lit icon's texture: 0 unknown (no call, an error or a secret), 1 none, 2 one. Read here, out of combat, so the
    -- state line (written in combat too) never touches the region.
    local lit = part.lit
    part.litCode = 0
    if lit then
        local okT, tex = pcall(lit.GetTexture, lit)
        if okT and not IsSecret(tex) then part.litCode = tex ~= nil and 2 or 1 end
    end
end

-- The PROOF pass, out of combat only (SeatEngine, and the tick every second): every slot frame of every tile read against
-- the tile's icon BEFORE anything is written. A slot found off the icon is put back (its tile is not live until the next
-- pass reads it right); one that cannot be read is unproven, except that a HIDDEN slot (no aura to draw) with no readable
-- rect keeps the proof it already has. An unreadable slot is logged after BT.UNREADABLE_TICKS passes. Allocation free
-- when nothing is wrong.
local function ProveEngine()
    for _, button in ipairs(BT.list) do
        local eng = button.fsEngine
        if eng then
            local bad = false
            for _, part in ipairs(eng.parts) do
                ReadPart(part)
                local placed = Placed(part.slot, button.icon)
                if placed == nil and part.ok and Hidden(part.slot) then
                    part.nils = 0                              -- keeps its last proof
                else
                    part.ok = placed == true
                    if placed == nil then
                        part.nils = (part.nils or 0) + 1
                        if part.nils >= BT.UNREADABLE_TICKS then
                            WarnOnce("bufftab_engine_unreadable", "a combat state slot cannot be located; that tile keeps the last known state")
                        end
                    else
                        part.nils = 0
                    end
                    if not part.ok then
                        bad = true
                        if placed == false then
                            WarnOnce("bufftab_engine_layout", "a combat state slot is not on its tile; that tile keeps the last known state")
                            pcall(part.slot.SetAllPoints, part.slot, button.icon)
                        end
                    end
                end
            end
            if eng.bad ~= bad then
                eng.bad = bad
                button.fsSig = nil
            end
            if eng.item and not eng.seen then
                local v = ViewOf(button)
                if v and (v.mode == "on" or v.mode == "exp") then
                    for _, part in ipairs(eng.parts) do
                        if part.shownCode == 2 then
                            eng.seen = true
                            button.fsSig = nil
                        end
                    end
                end
            end
        end
    end
    -- a slot or a child the engine made since the last pass may sit higher than the key label frames: lift them
    if EngineState.container then
        local level = HotkeyLevel()
        for _, button in ipairs(BT.list) do SeatHotkeyHost(button, level) end
    end
end

-- Re-seats every slot's texts for the current scale, reads the mouse back, then proves the positions. Out of combat
-- only (Sync after every build and rescale, and regen).
local function SeatEngine()
    local s = Scale()
    for _, button in ipairs(BT.list) do
        local eng = button.fsEngine
        if eng then
            for _, part in ipairs(eng.parts) do
                SeatPart(button, part, s)
                GuardMouse(part.slot)
            end
        end
    end
    ProveEngine()
end

-- true when an id of `ids` was never covered by a container before.
local function HasNewId(ids)
    local seen = EngineState.seenIds
    if not seen then return true end
    for id in pairs(ids) do
        if not seen[id] then return true end
    end
    return false
end

-- Out of combat: builds the container once, arms it again when it reads back off, rebuilds it when the shield ids
-- grew. `retry` is the tick's one uncounted second attempt after a failed build. Combat does none of it.
local function EnsureEngine(retry)
    if EngineState.gaveUp or not BT.host or InCombatLockdown() then return end
    if not Setting(BT.SETTINGS.combatstate) then return end
    local container = EngineState.container
    if container then
        local rebuild = false
        if HasNewId(FS.ShamanBuffs.ShieldIds()) then
            if EngineState.rebuilds < BT.ENGINE_REBUILDS then
                rebuild = true
            else
                WarnOnce("bufftab_engine_cap", "a new shield rank appeared; /reload to cover it")
            end
        end
        if not rebuild then
            if not ContainerIs(container, true) then
                Quiet(container, "SetUnit", "player")
                Quiet(container, "SetEnabled", true)
                Quiet(container, "Show")
                EngineState.alpha = nil
            end
            EngineState.armed = ContainerIs(container, true)
            return
        end
        -- the spellbook brought a shield id the slot filter lacks
        EngineState.rebuilds = EngineState.rebuilds + 1
        ParkContainer(container)
        EngineState.container, EngineState.armed, EngineState.alpha = nil, false, nil
        ClearEngineTiles()
    end
    if EngineState.passTried and not retry then return end
    if not EngineTemplate() then
        WarnOnce("bufftab_engine_template", "this client has no " .. BT.ENGINE_TEMPLATE .. "; the tiles show no combat state")
        EngineState.gaveUp = true
        return
    end
    local ok, result, ids = pcall(BuildContainer, not EngineState.noImbue)
    if not ok and type(result) == "table" and result.imbue then
        EngineState.noImbue = true
        WarnOnce("bufftab_engine_imbue", "the imbue tile carries no combat state (" .. result.imbue .. ")")
        ok, result, ids = pcall(BuildContainer, false)
    end
    if ok then
        EngineState.failures, EngineState.retryAt = 0, nil
        EngineState.container, EngineState.alpha = result, 0
        EngineState.seenIds = EngineState.seenIds or {}
        for id in pairs(ids) do EngineState.seenIds[id] = true end
        EngineState.armed = ContainerIs(result, true)
        for _, button in ipairs(BT.list) do button.fsSig = nil end
        BuffTab.Paint()             -- the imbue slots' lit icons take the tile's icon now
        return
    end
    WarnOnce("bufftab_engine_build", "the combat state could not be built (" .. tostring(result) .. ")")
    if retry then return end         -- the extra attempt costs nothing and is not repeated
    EngineState.passTried = true     -- one counted attempt per out of combat pass; regen starts the next
    EngineState.failures = EngineState.failures + 1
    EngineState.retryAt = GetTime() + BT.ENGINE_RETRY
    if EngineState.failures >= BT.ENGINE_LIMIT then EngineState.gaveUp = true end
end
BuffTab.EnsureEngine = EnsureEngine

-- The state of the combat state for the live test, in ForeverSTUwaveDB.buffTabEngine (written to disk on /reload or
-- logout): `line` is the one readable line, the rest are the same numbers. Rewritten in place only when something it
-- shows changed (a numeric signature is compared first), so a quiet tick allocates nothing.
-- A plain whole number or "secret" for a value that is not one: nothing in the state line is formatted from a raw value.
local function Plain(v)
    if IsSecret(v) then return "secret" end
    if type(v) ~= "number" or v ~= v or v == math.huge or v == -math.huge then return "?" end
    return tostring(math.floor(v + 0.5))
end

-- A plain number for the signature: a secret or non-number counts as 0 (no arithmetic or comparison on it).
local function Num(v)
    if type(v) ~= "number" or IsSecret(v) or v ~= v or v == math.huge or v == -math.huge then return 0 end
    return v
end

-- The state line's word for a coded value (0 unknown, 1 no, 2 yes): "secret" for a secret one.
local function CodeText(v, no, yes)
    if IsSecret(v) then return "secret" end
    if v == 2 then return yes end
    if v == 1 then return no end
    return "?"
end

local function WriteStatus()
    local on = Setting(BT.SETTINGS.combatstate) and true or false
    local sig = (on and 1048576 or 0) + (EngineState.armed and 1 or 0) + (EngineState.gaveUp and 2 or 0) + (EngineState.retryAt and 4 or 0)
        + (InCombatLockdown() and 8 or 0) + (EngineState.alpha or 2) * 16 + EngineState.rebuilds * 128
        + EngineState.failures * 1024
    for _, button in ipairs(BT.list) do
        local eng = button.fsEngine
        if eng then
            local ok, nils = 0, 0
            for _, part in ipairs(eng.parts) do
                if part.ok then ok = ok + 1 end
                if Num(part.nils) > nils then nils = Num(part.nils) end
            end
            sig = (sig * 31 + #eng.parts * 7 + ok * 3 + (eng.bad and 1 or 0) + nils * 13 + (eng.seen and 17 or 0)) % 2147483647
            for _, part in ipairs(eng.parts) do
                sig = (sig * 31 + Num(part.shownCode) * 5 + Num(part.w) * 3 + Num(part.h)
                    + Num(part.litCode) * 11 + (part.shownWhy and #part.shownWhy or 0) * 37 + (part.coverPlate and 19 or 0)
                    + (part.coverRing and 23 or 0)) % 2147483647
            end
        end
    end
    -- the spell icon values with no baked art (SpellArt.lua) ride along in the same table
    local art = FS.SpellArt
    local unmappedIcons = art and art.UnmappedLine and art.UnmappedLine() or nil
    sig = (sig * 31 + (art and art.UnmappedCount and art.UnmappedCount() or 0)) % 2147483647
    -- never create or replace the database: Config leaves a corrupt or newer-version one alone on purpose
    local db = ForeverSTUwaveDB
    if type(db) ~= "table" or (FS.Config and type(FS.Config.IsReadOnly) == "function" and FS.Config.IsReadOnly()) then return end
    local saved = db.buffTabEngine
    if type(saved) == "table" and saved.sig == sig and saved == EngineState.status then return end   -- a corrupt value is replaced
    saved = { sig = sig, setting = on, armed = EngineState.armed, alpha = EngineState.alpha, rebuilds = EngineState.rebuilds,
        failures = EngineState.failures, retryAt = EngineState.retryAt, gaveUp = EngineState.gaveUp,
        combat = InCombatLockdown() and true or false, tiles = {}, unmappedIcons = unmappedIcons }
    local text = { string.format("setting=%s armed=%s alpha=%s combat=%s rebuilds=%s failures=%s retryAt=%s gaveUp=%s",
        on and "on" or "off", tostring(saved.armed), tostring(saved.alpha), tostring(saved.combat), Plain(saved.rebuilds),
        Plain(saved.failures),
        tostring(saved.retryAt), tostring(saved.gaveUp)) }
    for _, button in ipairs(BT.list) do
        local eng = button.fsEngine
        if eng then
            local ok, nils = 0, 0
            for _, part in ipairs(eng.parts) do
                if part.ok then ok = ok + 1 end
                if Num(part.nils) > nils then nils = Num(part.nils) end
            end
            saved.tiles[button.fsKey] = { declared = Num(eng.declared), parts = #eng.parts, ok = ok, nils = nils,
                bad = eng.bad and true or false }
            local detail = {}
            for n, part in ipairs(eng.parts) do
                local cover = (part.coverPlate and "plate" or "") .. (part.coverPlate and part.coverRing and "+" or "")
                    .. (part.coverRing and "ring" or "")
                local lit = "n/a"
                if part.lit then lit = CodeText(part.litCode, "false", "true") end
                detail[#detail + 1] = string.format("slot%d shown=%s %sx%s lit=%s cover=%s", n,
                    CodeText(part.shownCode, "false", "true") .. (part.shownWhy and ("(" .. part.shownWhy .. ")") or ""),
                    Plain(part.w), Plain(part.h), lit,
                    cover ~= "" and cover or "none")
            end
            text[#text + 1] = string.format("%s declared=%s parts=%d ok=%d nils=%s bad=%s%s%s", button.fsKey, Plain(eng.declared),
                #eng.parts, ok, Plain(nils), tostring(eng.bad and true or false), eng.item and (" seen=" .. tostring(eng.seen == true)) or "",
                #detail > 0 and (" [" .. table.concat(detail, "; ") .. "]") or "")
        end
    end
    saved.line = table.concat(text, " | ")
    db.buffTabEngine = saved
    EngineState.status = saved
end

-- Paint and the tick call this; a database that refuses the write must never make them throw.
local function SaveStatus()
    local ok, err = pcall(WriteStatus)
    if not ok then QuietOnce("bufftab_status", "the buff tab state line could not be saved: ", err) end
end
BuffTab.SaveStatus = SaveStatus
BuffTab.SeatHotkeyHost = SeatHotkeyHost

-- The tick's share, out of combat only: the one uncounted retry of a failed build, and the proof pass.
local function EngineTick()
    if InCombatLockdown() then return end
    local at = EngineState.retryAt
    if at and not EngineState.container and GetTime() >= at then
        EngineState.retryAt = nil
        EnsureEngine(true)
        SeatEngine()
    elseif EngineState.container then
        ProveEngine()
    end
    SaveStatus()
end

-- The only thing combat writes: 1 while in combat and the state is on and every slot of every tile is proven (a tile
-- that shows its frozen state must not have a stray lit icon drawn over it), 0 otherwise.
local function SyncEngineAlpha()
    local container = EngineState.container
    if not container then return SaveStatus() end
    local alpha = (InCombatLockdown() and EngineState.armed and Setting(BT.SETTINGS.combatstate)) and 1 or 0
    if alpha == 1 and not AllProven() then alpha = 0 end
    if EngineState.alpha ~= alpha and Quiet(container, "SetAlpha", alpha) then EngineState.alpha = alpha end
    SaveStatus()
end

-- true when the tooltip of `button` is up: it is repainted with the tile.
local function TipIsOurs(button)
    local tip = GameTooltip
    if not (tip and button.fsHover) then return false end
    if type(tip.IsOwned) == "function" then return tip:IsOwned(button) and true or false end
    return type(tip.GetOwner) == "function" and tip:GetOwner() == button
end

function BuffTab.Paint()
    if not BT.built then return end
    SyncEngineAlpha()
    for _, button in ipairs(BT.list) do
        PaintButton(button, ViewOf(button))
        if TipIsOurs(button) then ShowTooltip(button) end
    end
end

-------------------------------------------------------------------------------
-- Applying a state to a button
-------------------------------------------------------------------------------

local function SetSpell(button, name)
    if name then
        button:SetAttribute("type", "spell")
        button:SetAttribute("spell", name)
    else
        for _, attr in ipairs(BT.ATTRS) do button:SetAttribute(attr, nil) end
    end
    button.fsAttrKey = name or ""
end

-- The spell a button casts right now, from the view.
local function WantedSpell(button)
    local v = ViewOf(button)
    return v and v.spell or nil
end

-- Reads one tile's usability from the spell it casts and repaints it when the state changed. An answer that cannot be
-- told (nil: secret, missing, raised) leaves the tint as it was; a locked tile is plain; an absent one is hidden.
local function UpdateUsable(button)
    if button.fsLocked then
        button.fsUsable, button.fsUsableSpell = nil, nil
        return
    end
    if button.fsAbsent then return end
    local spell = WantedSpell(button)
    button.fsUsableSpell = spell
    if not spell then
        -- nothing to ask about: the old tint no longer describes anything the tile casts
        if button.fsUsable ~= nil then
            button.fsUsable = nil
            PaintButton(button, ViewOf(button))
        end
        return
    end
    local state = SpellUsability(spell)
    if state and state ~= button.fsUsable then
        button.fsUsable = state
        PaintButton(button, ViewOf(button))
    end
end

local function UpdateAllUsable()
    for _, button in ipairs(BT.list) do UpdateUsable(button) end
end
BuffTab.UpdateUsable = UpdateAllUsable

-- A tile whose spell changed since it was last judged (a different imbue) is judged again without waiting for an event.
local function UpdateUsableIfSpellChanged()
    for _, button in ipairs(BT.list) do
        if not button.fsLocked and not button.fsAbsent and WantedSpell(button) ~= button.fsUsableSpell then
            UpdateUsable(button)
        end
    end
end

-- Re-aims the click at the view's spell: now out of combat, at regen from combat. Attribute writes only.
local function FollowSpell()
    for _, button in ipairs(BT.list) do
        if not button.fsLocked and not button.fsAbsent then
            local want = WantedSpell(button)
            if (want or "") ~= button.fsAttrKey then
                if InCombatLockdown() then
                    BT.pendingSync = true
                else
                    SetSpell(button, want)
                end
            end
        end
    end
end

-- Dims and strips a tile that has nothing to cast: no castable attribute, the mold and the unlock level. Out of
-- combat only (the caller).
local function Lock(button)
    if button.fsAttrKey ~= nil and button.fsAttrKey ~= "" then SetSpell(button, nil) end
    button.fsAttrKey = ""
    button.fsLocked, button.fsAbsent = true, false
    button:SetAlpha(BT.LOCKED_ALPHA)
    button.fsFace:Hide()
    button.icon:Hide()
    button.fsMold:Show()
    button.fsLockText:Show()
    button.fsPlate:SetAlpha(0)
    local skin = button.fsSkin
    if skin and skin.border and skin.border.ring then skin.border.ring:SetAlpha(0) end
    if skin and skin.glow then skin.glow:SetAlpha(0) end
end

local function Unlock(button)
    if not button.fsLocked then return end
    button.fsLocked = false
    button:SetAlpha(1)
    button.fsFace:Show()
    button.fsMold:Hide()
    button.fsLockText:Hide()
    button.fsPlate:SetAlpha(1)
    local skin = button.fsSkin
    if skin and skin.border and skin.border.ring then skin.border.ring:SetAlpha(1) end
    if skin and skin.glow then skin.glow:SetAlpha(1) end
    button.fsSig = nil
end

-- The imbue tile is absent while no imbue is known and none is on a weapon: hidden, nothing castable.
local function Absent(button)
    if button.fsAttrKey ~= nil and button.fsAttrKey ~= "" then SetSpell(button, nil) end
    button.fsAttrKey = ""
    button.fsAbsent = true
end

-------------------------------------------------------------------------------
-- The seat
-------------------------------------------------------------------------------

local function ConsoleApi()
    local console = FS.Console
    if type(console) == "table" and type(console.IsDrawn) == "function" then return console end
end

-- Where the host stands: the SetPoint arguments, or nil for no seat (the host then hides). While the class
-- shoulder is up it supplies the seat; without it the host sits on the Console chassis top edge at 316 design px,
-- or, with the Console not drawn, beside the totem tab (which sits above the stance bar there).
function BuffTab.HostPoint()
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.HostPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint, BT.KEY)
        if ok and point then return point, rel, relPoint, x, y end
    end
    local s = Scale()
    local console = ConsoleApi()
    if console and console.IsDrawn() and console.root then
        return "BOTTOMLEFT", console.root, "TOPLEFT", BT.DX * s, 0
    end
    local totems = _G.FSTotemBar
    if totems then return "BOTTOMLEFT", totems, "BOTTOMRIGHT", BT.BESIDE * s, 0 end
    local stance = _G.FSStanceBar
    if stance then return "BOTTOMLEFT", stance, "TOPLEFT", 0, 4 * s end
    return nil
end

-- Where button `col` (1..2) stands on the host.
function BuffTab.SlotPoint(col)
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.SlotPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.SlotPoint, BT.host, 1, col, BT.KEY)
        if ok and point then return point, rel, relPoint, x, y end
    end
    local s, pitch = Scale(), BT.BTN + BT.GAP
    return "BOTTOMLEFT", BT.host, "BOTTOMLEFT", (BT.PAD + (col - 1) * pitch) * s, BT.PB * s
end

local function SeatButtons()
    local s = Scale()
    BT.host:SetSize((2 * BT.PAD + BT.COLS * BT.BTN + (BT.COLS - 1) * BT.GAP) * s, (BT.PT + BT.BTN + BT.PB) * s)
    for _, button in ipairs(BT.list) do StyleButton(button, BT.BTN * s, s) end
end

local function ApplyButtons()
    local view = FS.ShamanBuffs.Update()
    for i, button in ipairs(BT.list) do
        button:ClearAllPoints()
        button:SetPoint(BuffTab.SlotPoint(i))
        local v = view[button.fsKey]
        if v.mode == "locked" then
            Lock(button)
            button:Show()
        elseif not v.mode then
            Absent(button)
            button:Hide()
        else
            button.fsAbsent = false
            Unlock(button)
            SetSpell(button, WantedSpell(button))
            button:Show()
        end
        FH.UpdateButtonHotkey(button)
    end
    UpdateAllUsable()
    BuffTab.Paint()
end

local function SeatHost()
    local host = BT.host
    local point, rel, relPoint, x, y = BuffTab.HostPoint()
    if not point then
        host:Hide()
        return
    end
    host:ClearAllPoints()
    host:SetPoint(point, rel, relPoint, x, y)
    if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
    local level = HotkeyLevel()
    for _, button in ipairs(BT.list) do SeatHotkeyHost(button, level) end
    host:Show()
end
BuffTab.SeatHost = SeatHost

-- Every protected step in one place; combat parks it for PLAYER_REGEN_ENABLED. Each step is its own pcall so one
-- failure cannot stop the next.
local function Sync()
    if not BT.built then return end
    if InCombatLockdown() then
        BT.pendingSync = true
        return
    end
    BT.pendingSync = false
    for _, step in ipairs({ SeatButtons, ApplyButtons, SeatHost, EnsureEngine, SeatEngine }) do
        local ok, err = pcall(step)
        if not ok then WarnOnce("bufftab_sync", "buff tab update failed (" .. tostring(err) .. ")") end
    end
end
BuffTab.Sync = Sync

-- true for the config window: the tab exists for this character (a Shaman with the tiles built).
function BuffTab.Applies()
    return BT.owns
end

-- true once this tab is built for a Shaman: ClassShoulder.lua then stands its block.
function BuffTab.OwnsShoulder()
    return BT.owns
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Build()
    BT.host = CreateFrame("Frame", "FSBuffTab", UIParent)
    BT.host:SetFrameStrata("LOW")
    BT.host:Hide()
    for i, def in ipairs(BT.BUTTONS) do
        local button = BT.list[i]
        if not button then
            button = BuildButton(BT.host, def, i)
            BT.list[i] = button
            BT.byKey[def.key] = button
        end
        button:Hide()
    end
    BT.built = true
end

-- Whether a tile's seat disagrees with its view: a Lightning Shield learned (locked -> live), an imbue learned or
-- gone (absent <-> live). Those need the protected steps of Sync, not just a repaint.
local function NeedsSync(view)
    for _, button in ipairs(BT.list) do
        local v = view[button.fsKey]
        if v then
            local locked, absent = v.mode == "locked", v.mode == nil
            if (locked and true or false) ~= (button.fsLocked and true or false) then return true end
            if (absent and true or false) ~= (button.fsAbsent and true or false) then return true end
        end
    end
    return false
end

-- Reads the data and brings the tiles after it: a changed seat goes through Sync (which parks in combat), a changed
-- spell is followed, the paint is texture and font writes only.
local function Refresh()
    local view = FS.ShamanBuffs.Update()
    if NeedsSync(view) then
        Sync()
    else
        FollowSpell()
    end
    UpdateUsableIfSpellChanged()
    BuffTab.Paint()
end

-- One repaint a second while the tab stands: the clock text moves, the slow sources are read when due. A plain
-- frame, not the protected host, so its script is never in question in combat.
local function Tick(self, dt)
    self.fsElapsed = (self.fsElapsed or 0) + dt
    if self.fsElapsed < BT.TICK then return end
    self.fsElapsed = 0
    if not (BT.host and BT.host:IsShown()) then return end
    local ok, err = pcall(Refresh)
    if not ok then WarnOnce("bufftab_tick", "buff tab repaint failed (" .. tostring(err) .. ")") end
    local okE, errE = pcall(EngineTick)
    if not okE then WarnOnce("bufftab_tick_engine", "buff tab combat state check failed (" .. tostring(errE) .. ")") end
end

local function OnEvent(_, event)
    if event == "SPELL_UPDATE_USABLE" or event == "ACTIONBAR_UPDATE_USABLE" then
        UpdateAllUsable()
    elseif event == "PLAYER_REGEN_DISABLED" then
        UpdateAllUsable()
        BuffTab.Paint()             -- the combat state: the engine slots are shown, the tiles drop to the dim base
    elseif event == "PLAYER_REGEN_ENABLED" then
        RefitAfterCombat()
        UpdateAllUsable()
        EngineState.passTried = false       -- a new out of combat pass may try the container again
        if BT.pendingSync then
            Sync()
        else
            FollowSpell()
            EnsureEngine()          -- arm (or build) the combat state container out of combat
            SeatEngine()
        end
        BuffTab.Paint()
    elseif event == "UPDATE_BINDINGS" then
        for _, button in ipairs(BT.list) do
            if button:IsShown() then FH.UpdateButtonHotkey(button) end
        end
    else
        Sync()
    end
end

local function Apply()
    if not IsShaman() then return end
    if not (FS.Theme and FH and FS.Layout and FS.ShamanBuffs) then return end

    local ok, err = pcall(Build)
    if not ok then
        print("|cff22e0ffForever STUwave|r: buff tab failed to build (" .. tostring(err) .. ")")
        return
    end

    -- Listeners start only now that the tiles exist (a failed or non-Shaman build leaves none running).
    FS.ShamanBuffs.Start()
    FS.ShamanBuffs.OnChange(Refresh)

    local events = CreateFrame("Frame")
    FS.FrameHelpers.RegisterEvents(events, BT.EVENTS)
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:RegisterEvent("UPDATE_BINDINGS")
    FS.FrameHelpers.RegisterEvents(events, BT.USABLE_EVENTS)
    events:SetScript("OnEvent", OnEvent)

    local ticker = CreateFrame("Frame")
    ticker:SetScript("OnUpdate", Tick)

    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(BT.SETTINGS.combatstate.key, function()
            if not InCombatLockdown() then
                pcall(EnsureEngine)
                pcall(SeatEngine)
            end
            for _, button in ipairs(BT.list) do button.fsSig = nil end
            BuffTab.Paint()
        end)
    end
    if FS.Layout.OnRescale then FS.Layout.OnRescale(Sync) end
    if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(Sync) end
    FH.OnQuickKeybindChanged(function()
        for _, button in ipairs(BT.list) do
            if button:IsShown() then FH.UpdateButtonHotkey(button) end
        end
    end)

    BT.owns = true
    if FS.ClassShoulder and FS.ClassShoulder.Refresh then
        local shouldered, why = pcall(FS.ClassShoulder.Refresh)
        if not shouldered then WarnOnce("bufftab_shoulder", "class shoulder failed (" .. tostring(why) .. ")") end
    end

    Sync()
end

-- Deferred to PLAYER_LOGIN with an InCombatLockdown fallback to PLAYER_REGEN_ENABLED, like TotemBar.lua's loader.
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
