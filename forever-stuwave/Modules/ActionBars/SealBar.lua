-- Forever STUwave: Paladin Seal and Aura bar
--
-- The Paladin shoulder of the approved Gunsight mockup (mockups/gunsight-hud-v2-2026-10-02,
-- `LS_*`, `SEALS`, `AURAS`, `lsBtn`): ONE tall block holding the seal bar on top and the aura bar
-- against the Console chassis, 7 buttons each, 38 design px and 4.8 apart. It exists so Parker can
-- bind a seal or an aura with Blizzard's built-in Quick Keybind mode. The shoulder CHROME (the open
-- outline the mockup draws around the block) and the lit-seal drain underline are later work.
--
-- Same mechanism as StanceBar.lua and ActionBars.lua: plain SecureActionButtonTemplate buttons with
-- attributes set DIRECTLY from Lua (type="spell"), no secure snippet.
--
--   * 14 buttons, FSSealButton1..7 and FSAuraButton1..7, built ONCE (a named secure frame cannot be
--     destroyed). Hidden slots carry no spell attribute.
--   * SEALS are spellbook spells: FSSealButtonN is ALWAYS seal N of the mockup order (sor, sotc,
--     sofu, soc, sol, sow, soj), `spell` = the seal NAME (it resolves C-side at click time, so a
--     rank change needs no write), so the CLICK binding of a button stays on its seal. Learned
--     seals are SEATED packed left in order by moving their own named frames; an unlearned seal's
--     button stays hidden and inert (no spell attribute). Known = the name resolves to an id and a
--     spellbook API says the player knows it, asked the way PartyFrames.lua does (every result
--     pcall'd and secret-guarded; an unreadable answer counts as not known and is asked again at
--     the next event).
--   * AURAS are SHAPESHIFT FORMS on this client: one button per form i of GetNumShapeshiftForms(),
--     `spell` = the 4th return of GetShapeshiftFormInfo(i) (there is no "shapeshift" secure type),
--     ordered by the mockup's aura order when the form's spell name is in it (other forms follow in
--     form order). Each button keeps its OWN form index i: its Quick Keybind command is Blizzard's
--     "SHAPESHIFTBUTTON"..i (the binding runs StanceBar:Select(i) natively), so a key follows the
--     FORM, not the slot (a newly learned aura can insert a form index and move a key to the
--     neighbouring aura; Blizzard's own stance bar behaves the same, so this is left as it is), and
--     the hotkey text reads that binding. The active form lights an ADD
--     wash plus a brighter ring and glow (GetShapeshiftFormInfo's flag, cross-checked against
--     GetShapeshiftForm() when that flag is nil or secret, refreshed on
--     UPDATE_SHAPESHIFT_FORM and UPDATE_SHAPESHIFT_FORMS).
--   * COOLDOWN: every button carries a swipe (FrameHelpers.SeatButtonCooldown) fed from the spell's
--     cooldown: C_Spell.GetSpellCooldownDuration -> SetCooldownFromDurationObject when the client has
--     it, else the legacy start/duration read, secret-guarded (a form button reads
--     GetShapeshiftFormCooldown(form) there). Refreshed on SPELL_UPDATE_COOLDOWN and
--     UPDATE_SHAPESHIFT_COOLDOWN.
--   * SetAttribute, Show, Hide, SetPoint and SetSize on a secure button (or its host) are refused in
--     combat. Everything that does any of them runs out of combat only; combat sets `pendingSync`
--     and PLAYER_REGEN_ENABLED replays it. The active look and the swipe are texture and Cooldown
--     writes, so they follow in combat.
--   * Quick Keybind: FrameHelpers.AttachQuickKeybind. Seals use "CLICK FSSealButtonN:LeftButton",
--     declared in Bindings.xml (seals ONLY: an aura needs no Bindings.xml line or BINDING_NAME). A
--     bound seal key clicks THIS button (a CLICK binding), so the cast is ours.
--   * SEAT: SealBar.HostPoint() says where the host stands and SealBar.SlotPoint(row, col) where a
--     button stands on it; those two functions are the ONLY places that know. While the class
--     shoulder (ClassShoulder.lua) stands it answers for both (the same numbers), and these are the
--     fallback seat. The fallback: the host stands on the Console chassis top edge, LS_X (755)
--     design px from the screen left where the chassis starts at 719 (the pet dock's DOCK_X
--     derivation), so BOTTOMLEFT of the host sits on FSConsole's TOPLEFT at 36 design px. With the
--     Console present but not drawn (/fsconsole off, /fsbars blizz) the bar stays up on the stance
--     bar's seat (just above FSStanceBar, which a Paladin never fills), with no log: a normal case.
--     With no Console API at all it takes the same seat and says so once.
--   * StanceBar.lua hands a Paladin's forms over to this bar through FS.SealBar.OwnsForms(), read
--     by its Build on every rebuild.

local _, FS = ...

local SealBar = {}
FS.SealBar = SealBar

local SB = {
    CLASS = "PALADIN",
    -- mockup LS_* in design px (x scaled by FS.Layout.Scale())
    BTN = 38, GAP = 4.8, PAD = 6, PT = 6, PB = 5, PER_ROW = 7,
    -- LS_X less the chassis left: the mockup's shoulder is 36 design px in from the chassis
    DX = 36,
    BORDER_ALPHA = 0.35,
    -- the active aura's look: the stance bar's checked wash, a ring lifted this far toward white
    -- and a glow at GLOW_ACTIVE
    ACTIVE_ALPHA = 0.4, RING_LIFT = 0.5, GLOW_ACTIVE = 0.7,
    -- forms read per sync (a Paladin has seven auras; the cap only bounds a bad answer)
    MAX_FORMS = 16,
    -- the seal bar, row 0 (top): spell name and the seal's own colour (mockup SEALS).
    -- Append only, never reorder: the index is the saved keybind.
    SEALS = {
        { "Seal of Righteousness", "ffd23f" }, { "Seal of the Crusader", "ff9a2e" },
        { "Seal of Fury", "ff3b4e" }, { "Seal of Command", "b565ff" },
        { "Seal of Light", "f3fbff" }, { "Seal of Wisdom", "4da3ff" },
        { "Seal of Justice", "c9d3e6" },
    },
    -- the aura bar, row 1 (against the chassis): cyan like the stance buttons (mockup AURAS).
    -- Only the ORDER is used: the buttons are the shapeshift forms, sorted by this list.
    AURAS = {
        { "Devotion Aura" }, { "Retribution Aura" }, { "Concentration Aura" },
        { "Shadow Resistance Aura" }, { "Frost Resistance Aura" }, { "Fire Resistance Aura" },
        { "Sanctity Aura" },
    },
    ROWS = { { key = "seal", prefix = "FSSealButton" }, { key = "aura", prefix = "FSAuraButton" } },
    ROW_INDEX = { seal = 1, aura = 2 },
    EVENTS = {
        "SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD",
        "UPDATE_SHAPESHIFT_FORMS",
    },
    -- state-only events: texture and Cooldown writes, legal in combat
    LIVE_EVENTS = { "UPDATE_SHAPESHIFT_FORM", "SPELL_UPDATE_COOLDOWN", "UPDATE_SHAPESHIFT_COOLDOWN" },
    host = nil,
    buttons = { seal = {}, aura = {} },
    built = false,
    owns = false,
    pendingSync = false,
    warned = {},
}

-- Binding labels for the SEAL commands Bindings.xml names; the client reads these globals for the
-- key binding screen, and for every class, so a non-Paladin sees the (inert) entries too. Button N
-- is always seal N of SB.SEALS, so the label is that seal's name. An aura key is Blizzard's own
-- SHAPESHIFTBUTTONi, which already has its label.
BINDING_HEADER_FOREVERSTUWAVE = "Forever STUwave"
for i, def in ipairs(SB.SEALS) do
    _G["BINDING_NAME_CLICK FSSealButton" .. i .. ":LeftButton"] = def[1]
end

local IsSecret = FS.IsSecret

local function Hex(hex)
    return {
        tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255,
        tonumber(hex:sub(5, 6), 16) / 255,
    }
end

local function Scale()
    return (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
end

-- One chat line per distinct problem, once per session (LogDegradeOnce does not dedupe).
local function WarnOnce(key, text)
    if SB.warned[key] then return end
    SB.warned[key] = true
    FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text)
end

-------------------------------------------------------------------------------
-- Class and spells
-------------------------------------------------------------------------------

local function IsPaladin()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or IsSecret(token) then return false end
    return token == SB.CLASS
end

-- A value only when it is plain (not secret) and of the wanted type, else nil.
local function PlainValue(v, kind)
    if IsSecret(v) or v == nil or type(v) ~= kind then return nil end
    return v
end

-- spellID, iconID of a spell by name, plain values only; nil when the name does not resolve.
local function ResolveSpell(name)
    local modern = C_Spell and C_Spell.GetSpellInfo
    if modern then
        local ok, info = pcall(modern, name)
        if ok and not IsSecret(info) and info ~= nil and type(info) == "table" then
            return PlainValue(info.spellID, "number"), PlainValue(info.iconID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, _, _, icon, _, _, _, id = pcall(GetSpellInfo, name)
        if ok then return PlainValue(id, "number"), PlainValue(icon, "number") end
    end
    return nil
end

-- true when the player knows this spell id, asking every spellbook API the client has
-- (PartyFrames.lua's IsKnownSpellId, reduced to the question this bar asks: known or not). An API
-- that raises or answers secret counts as "no" and is asked again at the next event. With none of
-- them present the id already resolved by name, which in this spellbook API means known.
local function IsKnownSpellId(id)
    local fns = { IsPlayerSpell, IsSpellKnown, C_SpellBook and C_SpellBook.IsSpellKnown }
    local asked = false
    for i = 1, 3 do
        local fn = fns[i]
        if fn then
            asked = true
            local ok, answer = pcall(fn, id)
            if ok and not IsSecret(answer) and answer then return true end
        end
    end
    return not asked
end

-- The known seals, keyed by their BUTTON index (seal N of SB.SEALS is always FSSealButtonN, so a key
-- bound to it stays on its seal): out[N] = { spell = name, id, icon, color, slot }, with `slot` the
-- packed position (1 for the first known seal, in mockup order). Unknown seals leave a hole.
local function KnownSeals()
    local out, slot = {}, 0
    for index, def in ipairs(SB.SEALS) do
        local id, icon = ResolveSpell(def[1])
        if id and IsKnownSpellId(id) then
            slot = slot + 1
            out[index] = { spell = def[1], id = id, icon = icon, color = Hex(def[2]), slot = slot }
        end
    end
    return out
end

-- The English name of a spell id, a plain string or nil.
local function SpellName(id)
    local modern = C_Spell and C_Spell.GetSpellInfo
    if modern then
        local ok, info = pcall(modern, id)
        if ok and not IsSecret(info) and info ~= nil and type(info) == "table" then
            return PlainValue(info.name, "string")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, name = pcall(GetSpellInfo, id)
        if ok then return PlainValue(name, "string") end
    end
    return nil
end

local function PlainIcon(v)
    if IsSecret(v) or v == nil then return nil end
    if type(v) == "number" or type(v) == "string" then return v end
    return nil
end

-- Position of an aura form's spell name in the mockup's list; a form it does not list sorts after.
local function AuraRank(name)
    for rank, def in ipairs(SB.AURAS) do
        if def[1] == name then return rank end
    end
    return #SB.AURAS + 1
end

-- The shapeshift forms as aura entries, in mockup order (the row shows the first seven):
-- { { spell = <form spell id>, id, icon, form = <form index>, active }, ... }. Plain values only;
-- a form whose spell id cannot be read is left out and the next sync asks again.
local function ReadForms()
    if not (GetNumShapeshiftForms and GetShapeshiftFormInfo) then
        WarnOnce("sealbar_noforms", "no shapeshift form API, the aura buttons stay empty")
        return {}
    end
    local ok, count = pcall(GetNumShapeshiftForms)
    count = ok and PlainValue(count, "number") or 0
    local out = {}
    local current   -- GetShapeshiftForm(), read at most once, false when unreadable
    for form = 1, math.min(count, SB.MAX_FORMS) do
        local okInfo, icon, active, _, id = pcall(GetShapeshiftFormInfo, form)
        id = okInfo and PlainValue(id, "number") or nil
        -- a missing or secret active flag is cross-checked against the current form (plain only)
        if id and (IsSecret(active) or active == nil) and GetShapeshiftForm then
            if current == nil then
                local okForm, index = pcall(GetShapeshiftForm)
                current = okForm and PlainValue(index, "number") or false
            end
            if current then active = (current == form) end
        end
        if id then
            out[#out + 1] = {
                spell = id, id = id, icon = PlainIcon(icon), form = form, active = active,
                rank = AuraRank(SpellName(id)),
            }
        end
    end
    table.sort(out, function(a, b)
        if a.rank ~= b.rank then return a.rank < b.rank end
        return a.form < b.form
    end)
    return out
end

-------------------------------------------------------------------------------
-- Buttons
-------------------------------------------------------------------------------

local function UpdateHotkey(button)
    local hotkey = button.HotKey
    if not hotkey then return end
    local key = GetBindingKey(button.fsCommand)
    local text = FS.FrameHelpers.FormatBindingText(key)
    if text == "" then
        hotkey:SetText("")
        hotkey:Hide()
        if button.fsHotkeyPlate then button.fsHotkeyPlate:Hide() end
        return
    end
    hotkey:SetText(text)
    hotkey:Show()
    if button.fsHotkeyPlate then button.fsHotkeyPlate:Show() end
end

-- A seal shows its spell; an aura shows its shapeshift form, like the stance bar's buttons.
local function ShowTooltip(self)
    local tip = GameTooltip
    if not tip then return end
    local byForm = self.fsFormIndex and tip.SetShapeshift
    if not (byForm or (self.fsSpellID and tip.SetSpellByID)) then return end
    if _G.GameTooltip_SetDefaultAnchor then
        _G.GameTooltip_SetDefaultAnchor(tip, self)
    else
        tip:SetOwner(self, "ANCHOR_TOP")
    end
    if byForm then
        tip:SetShapeshift(self.fsFormIndex)
    else
        tip:SetSpellByID(self.fsSpellID)
    end
    tip:Show()
end

local function HideTooltip()
    GameTooltip:Hide()
end

-- Runs once per button, from Build. Everything that creates a region, hook or frame is guarded so
-- a throw partway is finished by the next Build (the button is registered before it is styled).
local function StyleButton(button, size)
    button:SetSize(size, size)

    if not button.fsSealPlate then
        button.fsSealPlate = FS.Theme.AddCut2Texture(
            button, FS.Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    FS.Theme.SkinCutButton(button, { borderColor = FS.Theme.COLOR_POWER, glowAlpha = SB.BORDER_ALPHA })

    -- the aura row's active look: a cyan ADD wash over the face, hidden until the form is active
    if button.fsRow == "aura" and not button.fsActiveWash then
        local wash = button:CreateTexture(nil, "OVERLAY", nil, 2)
        wash:SetTexture(FS.Theme.SLICE_CUT2_FILL_TEXTURE)
        FS.Theme.ApplyNineSlice(wash, FS.Theme.SLICE_CUT_MARGIN)
        local c = FS.Theme.COLOR_POWER
        wash:SetVertexColor(c[1], c[2], c[3], SB.ACTIVE_ALPHA)
        wash:SetBlendMode("ADD")
        wash:SetAllPoints(button)
        wash:Hide()
        button.fsActiveWash = wash
    end

    if not button.fsSealHooked then
        button.fsSealHooked = true
        button:HookScript("OnEnter", ShowTooltip)
        button:HookScript("OnLeave", HideTooltip)
    end

    if not button.icon then
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        button.icon = icon
    end
    FS.FrameHelpers.SeatCutIcon(button)

    -- the swipe: a full-icon Cooldown (black .64, no edge or bling), built once
    if not button.cooldown then
        button.cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
    end
    FS.FrameHelpers.SeatButtonCooldown(button)

    if not button.HotKey then
        button.HotKey = button:CreateFontString(nil, "OVERLAY")
    end
    local hotkey = button.HotKey
    local textHost = FS.FrameHelpers.SeatButtonText(button, hotkey)
    hotkey:ClearAllPoints()
    hotkey:SetWidth(0)
    hotkey:SetPoint("TOPRIGHT", button, "TOPRIGHT", -3, -2)
    hotkey:SetJustifyH("RIGHT")
    hotkey:SetDrawLayer("OVERLAY", 4)
    FS.Theme.ApplyMono(hotkey, 10, FS.Theme.COLOR_TEXT_WHITE)

    -- Same text-sized dark plate as the action bars, above the cooldown swipe.
    if not button.fsHotkeyPlate then
        local plate = textHost:CreateTexture(nil, "OVERLAY", nil, 3)
        plate:SetColorTexture(0.024, 0.012, 0.071, 0.78)
        plate:SetPoint("TOPLEFT", hotkey, "TOPLEFT", -3, 2)
        plate:SetPoint("BOTTOMRIGHT", hotkey, "BOTTOMRIGHT", 3, -2)
        plate:Hide()
        button.fsHotkeyPlate = plate
    end
end

local function BuildButton(host, row, index)
    local button = CreateFrame("Button", row.prefix .. index, host, "SecureActionButtonTemplate")
    button.index = index
    button.fsRow = row.key
    -- a seal is clicked through a CLICK binding; an aura keeps Blizzard's own form binding, whose
    -- index follows the form the button holds (set on every sync)
    button.fsCommand = row.key == "seal" and ("CLICK " .. row.prefix .. index .. ":LeftButton")
        or ("SHAPESHIFTBUTTON" .. index)
    button:SetAttribute("type", "spell")
    button:RegisterForClicks("AnyUp", "AnyDown")
    FS.FrameHelpers.AttachQuickKeybind(button, button.fsCommand)
    return button
end

-- Paints the border and glow from the button's tint (the seal's own colour, or cyan for an aura);
-- an active button gets the ring lifted toward white and a stronger glow. Texture writes only.
local function PaintRing(button)
    local skin, color = button.fsSkin, button.fsTint
    if not (skin and color) then return end
    local r, g, b, glow = color[1], color[2], color[3], SB.BORDER_ALPHA
    if button.fsActive then
        local lift = SB.RING_LIFT
        r, g, b = r + (1 - r) * lift, g + (1 - g) * lift, b + (1 - b) * lift
        glow = SB.GLOW_ACTIVE
    end
    if skin.border and skin.border.ring then skin.border.ring:SetVertexColor(r, g, b, 1) end
    if skin.glow then skin.glow:SetVertexColor(color[1], color[2], color[3], glow) end
end

local function Tint(button, color)
    button.fsTint = color
    PaintRing(button)
end

-- Where a button stands: BOTTOMLEFT of the host, `row` 1 the seals (top), 2 the auras, `col` 1..7.
-- Returns the SetPoint arguments. With HostPoint, the only place that knows the geometry: while the
-- class shoulder (ClassShoulder.lua) exists it answers for both, from the same LS_* numbers, and these
-- are the fallback seat (no Console, so no shoulder drawn).
function SealBar.SlotPoint(row, col)
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.SlotPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.SlotPoint, SB.host, row, col)
        if ok and point then return point, rel, relPoint, x, y end
    end
    local s, pitch = Scale(), SB.BTN + SB.GAP
    return "BOTTOMLEFT", SB.host, "BOTTOMLEFT",
        (SB.PAD + (col - 1) * pitch) * s, (SB.PB + (#SB.ROWS - row) * pitch) * s
end

-- Sizes and styles the host and every button for the current scale. Out of combat only. Where a
-- button stands is ApplyRow's call (a seal stands at its packed slot).
local function SeatButtons()
    local s = Scale()
    local pitch = SB.BTN + SB.GAP
    SB.host:SetSize((2 * SB.PAD + SB.PER_ROW * SB.BTN + (SB.PER_ROW - 1) * SB.GAP) * s,
        (SB.PT + 2 * SB.BTN + SB.GAP + SB.PB) * s)
    for _, row in ipairs(SB.ROWS) do
        for _, button in ipairs(SB.buttons[row.key]) do
            StyleButton(button, SB.BTN * s)
        end
    end
end

-- The active look (wash, brighter ring and glow): lit for a plainly active form, dark for a plainly
-- inactive one, left as it was for a secret answer. Textures only, so it may change in combat.
local function SetActive(button, active)
    if IsSecret(active) then return end
    button.fsActive = active and true or false
    PaintRing(button)
    local wash = button.fsActiveWash
    if not wash then return end
    if active then wash:Show() else wash:Hide() end
end

-- The swipe: the spell's cooldown as the duration object when the client has it, else the legacy
-- start and duration, read only when both are plain. Cooldown writes, legal in combat.
local function UpdateCooldown(button)
    local cooldown = button.cooldown
    if not cooldown then return end
    local id = button.fsSpellID
    if not id then
        cooldown:Clear()
        cooldown:Hide()
        return
    end
    local modern = C_Spell and C_Spell.GetSpellCooldownDuration
    if modern then
        local ok, obj = pcall(modern, id)
        if ok and not IsSecret(obj) and obj ~= nil then
            cooldown:SetCooldownFromDurationObject(obj)
        else
            cooldown:Clear()
        end
        cooldown:Show()
        return
    end
    local start, duration, enabled
    if button.fsFormIndex and GetShapeshiftFormCooldown then
        local ok, s, d, e = pcall(GetShapeshiftFormCooldown, button.fsFormIndex)
        if ok then start, duration, enabled = s, d, e end
    elseif C_Spell and C_Spell.GetSpellCooldown then
        local ok, info = pcall(C_Spell.GetSpellCooldown, id)
        if ok and type(info) == "table" and not IsSecret(info) then
            start, duration, enabled = info.startTime, info.duration, info.isEnabled
        end
    elseif GetSpellCooldown then
        local ok, s, d, e = pcall(GetSpellCooldown, id)
        if ok then start, duration, enabled = s, d, e end
    end
    if IsSecret(start) or IsSecret(duration) or IsSecret(enabled) then
        cooldown:Hide()
        return
    end
    if type(start) == "number" and type(duration) == "number" and duration > 0
        and enabled ~= false and enabled ~= 0 then
        cooldown:SetCooldown(start, duration)
        cooldown:Show()
    else
        cooldown:Clear()
        cooldown:Hide()
    end
end

local function UpdateAllCooldowns()
    for _, row in ipairs(SB.ROWS) do
        for _, button in ipairs(SB.buttons[row.key]) do
            if button.fsSpellID then UpdateCooldown(button) end
        end
    end
end

-- Writes one row's entries onto its buttons: attribute, icon, tooltip id, form index and command,
-- border colour, seat, visibility. `entries` is indexed by BUTTON index and may have holes (seals);
-- an entry's `slot` (default: the button index) says where it stands. A button with no entry is
-- cleared and hidden, and parked at its own index. Out of combat only.
local function ApplyRow(key, entries)
    local rowIndex = SB.ROW_INDEX[key]
    for i, button in ipairs(SB.buttons[key]) do
        local entry = entries[i]
        button:ClearAllPoints()
        button:SetPoint(SealBar.SlotPoint(rowIndex, entry and entry.slot or i))
        if entry then
            if button.fsSpellKey ~= entry.spell then
                button:SetAttribute("spell", entry.spell)
                button.fsSpellKey = entry.spell
            end
            button.fsSpellID = entry.id
            button.fsFormIndex = entry.form
            if entry.form then
                button.fsCommand = "SHAPESHIFTBUTTON" .. entry.form
                button.commandName = button.fsCommand
            end
            if entry.icon then button.icon:SetTexture(entry.icon) end
            Tint(button, entry.color or FS.Theme.COLOR_POWER)
            UpdateHotkey(button)
            SetActive(button, entry.active)
            UpdateCooldown(button)
            button:Show()
        else
            if button.fsSpellKey ~= nil then
                button:SetAttribute("spell", nil)
                button.fsSpellKey = nil
            end
            button.fsSpellID, button.fsFormIndex = nil, nil
            SetActive(button, false)
            UpdateCooldown(button)
            button:Hide()
        end
    end
end

local function ApplySeals()
    ApplyRow("seal", KnownSeals())
end

local function ApplyAuras()
    ApplyRow("aura", ReadForms())
end

-- The active form moved: relight the look. No attribute, Show or Hide, so combat may run it.
local function RefreshActive()
    if not SB.built then return end
    local byForm = {}
    for _, entry in ipairs(ReadForms()) do byForm[entry.form] = entry end
    for _, button in ipairs(SB.buttons.aura) do
        local entry = button.fsFormIndex and byForm[button.fsFormIndex]
        if entry then SetActive(button, entry.active) end
    end
end

-------------------------------------------------------------------------------
-- The seat
-------------------------------------------------------------------------------

local function ConsoleApi()
    local console = FS.Console
    if type(console) == "table" and type(console.IsDrawn) == "function" then return console end
end

-- Where the host stands: the SetPoint arguments, or nil for no seat (the host then hides). While the
-- class shoulder is up it supplies the seat (the same place: the Console chassis top edge, DX in). Without
-- it: on the Console chassis top edge while the Console is drawn (the shoulder failed to build); with the
-- Console present but not drawn, just above the stance bar's seat (a normal case, not logged); with no
-- Console API at all, the same seat and a one time line.
function SealBar.HostPoint()
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.HostPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint)
        if ok and point then return point, rel, relPoint, x, y end
    end
    local s = Scale()
    local console = ConsoleApi()
    if console then
        if console.IsDrawn() and console.root then
            return "BOTTOMLEFT", console.root, "TOPLEFT", SB.DX * s, 0
        end
    else
        WarnOnce("sealbar_noconsole", "no Console, the seal and aura bar sits above the stance bar's seat")
    end
    local stance = _G.FSStanceBar
    if stance then return "BOTTOMLEFT", stance, "TOPLEFT", 0, 4 * s end
    return nil
end

-- Anchors the host where HostPoint says and shows it, or hides it with no seat. Out of combat only
-- (the host parents secure buttons, so it is protected in combat).
local function SeatHost()
    local host = SB.host
    local point, rel, relPoint, x, y = SealBar.HostPoint()
    if not point then
        host:Hide()
        return
    end
    host:ClearAllPoints()
    host:SetPoint(point, rel, relPoint, x, y)
    if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
    host:Show()
end

-- Every protected step in one place; combat parks it for PLAYER_REGEN_ENABLED. Each step is its
-- own pcall so one failure cannot stop the next.
local function Sync()
    if not SB.built then return end
    if InCombatLockdown() then
        SB.pendingSync = true
        return
    end
    SB.pendingSync = false
    for _, step in ipairs({ SeatButtons, ApplySeals, ApplyAuras, SeatHost }) do
        local ok, err = pcall(step)
        if not ok then WarnOnce("sealbar_sync", "seal bar update failed (" .. tostring(err) .. ")") end
    end
end

local function UpdateAllHotkeys()
    for _, row in ipairs(SB.ROWS) do
        for _, button in ipairs(SB.buttons[row.key]) do
            if button:IsShown() then UpdateHotkey(button) end
        end
    end
end

-------------------------------------------------------------------------------
-- Stance bar hand over
-------------------------------------------------------------------------------

-- true once this bar is built for a Paladin: StanceBar.lua then builds nothing for the forms.
function SealBar.OwnsForms()
    return SB.owns
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Build()
    SB.host = CreateFrame("Frame", "FSSealBar", UIParent)
    SB.host:SetFrameStrata("LOW")
    SB.host:Hide()
    for _, row in ipairs(SB.ROWS) do
        for i = 1, SB.PER_ROW do
            local button = SB.buttons[row.key][i]
            if not button then
                button = BuildButton(SB.host, row, i)
                SB.buttons[row.key][i] = button
            end
            button:Hide()
        end
    end
    SB.built = true
end

local function OnEvent(_, event)
    if event == "PLAYER_REGEN_ENABLED" then
        if SB.pendingSync then Sync() end
    elseif event == "UPDATE_BINDINGS" then
        UpdateAllHotkeys()
    elseif event == "UPDATE_SHAPESHIFT_FORM" then
        RefreshActive()
    elseif event == "SPELL_UPDATE_COOLDOWN" or event == "UPDATE_SHAPESHIFT_COOLDOWN" then
        UpdateAllCooldowns()
    else
        if event == "UPDATE_SHAPESHIFT_FORMS" then RefreshActive() end
        Sync()
    end
end

local function Apply()
    if not IsPaladin() then return end
    if not (FS.Theme and FS.FrameHelpers and FS.Layout) then return end

    local ok, err = pcall(Build)
    if not ok then
        print("|cff22e0ffForever STUwave|r: seal bar failed to build (" .. tostring(err) .. ")")
        return
    end

    local events = CreateFrame("Frame")
    for _, event in ipairs(SB.EVENTS) do pcall(events.RegisterEvent, events, event) end
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:RegisterEvent("UPDATE_BINDINGS")
    for _, event in ipairs(SB.LIVE_EVENTS) do events:RegisterEvent(event) end
    events:SetScript("OnEvent", OnEvent)

    if FS.Layout.OnRescale then FS.Layout.OnRescale(Sync) end
    if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(Sync) end
    FS.FrameHelpers.OnQuickKeybindChanged(UpdateAllHotkeys)

    -- The shoulder builds only for a bar that owns the forms, and its seat must exist before the first
    -- Sync seats the host and the buttons on it.
    SB.owns = true
    if FS.ClassShoulder and FS.ClassShoulder.Refresh then
        local shouldered, why = pcall(FS.ClassShoulder.Refresh)
        if not shouldered then WarnOnce("sealbar_shoulder", "class shoulder failed (" .. tostring(why) .. ")") end
    end

    Sync()

    -- The stance bar was built first at PLAYER_LOGIN; take its forms away now.
    if FS.StanceBar and FS.StanceBar.Rebuild then FS.StanceBar.Rebuild() end
end

-- Deferred to PLAYER_LOGIN with an InCombatLockdown fallback to PLAYER_REGEN_ENABLED, like
-- StanceBar.lua's loader.
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
