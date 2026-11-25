-- Forever STUwave: the class tab kit (FS.ClassTabKit) and the Druid shapeshift tab (ticket T1)
--
-- THE KIT. Six class tabs share one body (Druid shapeshift, Hunter call pet, Mage portals and teleports, Mage food and water,
-- Rogue poisons, Warlock summon demon), so the body lives here, in the first of their files, and the others call
-- FS.ClassTabKit.New. A tab is a shoulder block on the Console's top edge (ClassShoulder.lua seats it; OWNERS in that file
-- names each tab's OwnsShoulder, Cols and Sync) holding SECURE buttons built like the Paladin's seals (SealBar.lua): plain
-- SecureActionButtonTemplate buttons whose attributes are set directly from Lua, no snippet, RegisterForClicks("AnyUp",
-- "AnyDown"), a cut icon, the violet cooldown fill and a ring that lights when the thing is active.
--
-- A tab hands New a `def` and gets back the module table (FS[def.field]):
--   field, class, shoulder (the ClassShoulder key), host and prefix (frame names), slots (button count), settings (name ->
--   { key, default, label, tip }), master (the setting name whose off hides the whole tab), config (the section on the Addon
--   tabs page: title, tip, rows by setting name), entries(Tab) (the ordered list of what to show), syncEvents (events that
--   can change WHAT the buttons are: spellbook, bags, pets), liveEvents (events that only repaint), unitEvents (the same,
--   for the player's own units), pre/post hooks.
-- An entry is plain data: { key, id (spell id: icon, tooltip, cooldown), spell (secure spell NAME) or macro (secure macro
-- text), icon, item (tooltip item id), tipText, lit, count, top, dim, nudge, row, col }. Entries are read, never stored: Paint
-- reads them again and matches by key.
--
-- COMBAT. SetAttribute, Show, Hide, SetPoint and SetSize on a secure button or its host are refused in combat, so Sync (the one
-- place that does any of them) runs out of combat only; combat sets pendingSync and PLAYER_REGEN_ENABLED replays it. Paint
-- writes only textures, font strings, cooldowns and animation groups, which are legal in combat. A value that is secret is
-- never compared: a read that cannot be told keeps what was painted last.
--
-- The tabs have no key bindings (a binding needs a Bindings.xml line). No Console drawn means no shoulder, so no tab.
-- UNVERIFIED in game; the tools/*tab-harness.py files pin the logic against a mock.
--
-- THE DRUID TAB. One button per learned form, in this order: Bear (Dire Bear when learned), Cat, Travel, Aquatic, Moonkin
-- (Forever spell ids 5487/9634, 768, 783, 1066, 24858, checked against the client data). The button casts the form by name, so
-- a click shifts. The lit one is the form the player is in (GetShapeshiftForm, then GetShapeshiftFormInfo's spell id); out of
-- form nothing is lit, or the caster button is when it exists. The caster button (off by default) is a macro, /cancelform.
--
-- Loads after SealBar.lua and before the other class tab files and ConfigWindow.lua.

local _, FS = ...

local IsSecret = FS.IsSecret

local Kit = {}
FS.ClassTabKit = Kit

-------------------------------------------------------------------------------
-- Reads every tab shares
-------------------------------------------------------------------------------

-- A value only when it is plain (not secret) and of the wanted type, else nil.
function Kit.Plain(v, kind)
    if IsSecret(v) or v == nil or type(v) ~= kind then return nil end
    return v
end
local Plain = Kit.Plain

function Kit.PlayerClass()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok then return nil end
    return Plain(token, "string")
end

-- true when the player knows the spell (every spellbook API the client has; none answering secret counts as no).
function Kit.Known(id)
    local FH = FS.FrameHelpers
    return FH and FH.IsKnownSpellId and FH.IsKnownSpellId(id, false) or false
end

-- name, icon of a spell id, plain values only.
function Kit.SpellInfo(id)
    local FH = FS.FrameHelpers
    if not (FH and FH.SpellById) then return nil end
    return FH.SpellById(id)
end

-- The carried count of an item id (bags and the ammo slot are the client's business), a plain number or nil.
function Kit.ItemCount(id)
    local fn = (C_Item and C_Item.GetItemCount) or _G.GetItemCount
    if type(fn) ~= "function" then return nil end
    local ok, n = pcall(fn, id)
    if not ok then return nil end
    return Plain(n, "number")
end

function Kit.Setting(def)
    local config = FS.Config
    if config and config.Get then
        local value = config.Get(def.key)
        if type(value) == "boolean" then return value end
    end
    return def.default
end

local function Scale()
    return (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
end

-- The mockup numbers of the shoulder block (ClassShoulder.C), with the Paladin block's as the fallback.
local function Metrics()
    local c = FS.ClassShoulder and FS.ClassShoulder.C
    if type(c) ~= "table" then return { BTN = 38, GAP = 4.8, PAD = 6, PT = 6, PB = 5 } end
    return c
end

-- The look of a lit and an idle button (SealBar's numbers).
Kit.LOOK = {
    BORDER_ALPHA = 0.35, ACTIVE_ALPHA = 0.4, RING_LIFT = 0.5, GLOW_ACTIVE = 0.7,
    DIM_ALPHA = 0.55, NUDGE_ALPHA = 0.45, NUDGE_TIME = 0.8, TEXT_PX = 10,
    PLATE = { 0.024, 0.012, 0.071, 0.78 },
}
local LOOK = Kit.LOOK

-------------------------------------------------------------------------------
-- A tab
-------------------------------------------------------------------------------

local SYNC_EVENTS = { "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD" }

function Kit.New(def)
    local Tab = { def = def, SETTINGS = def.settings }
    FS[def.field] = Tab
    local T = { built = false, pendingSync = false, host = nil, buttons = {}, warned = {}, events = nil }
    Tab.T = T
    local master = def.settings[def.master]

    if FS.Config and FS.Config.RegisterDefault then
        for _, setting in pairs(def.settings) do FS.Config.RegisterDefault(setting.key, setting.default) end
    end

    local function WarnOnce(key, text)
        if T.warned[key] then return end
        T.warned[key] = true
        if FS.LogDegradeOnce then FS.LogDegradeOnce(def.field .. "_" .. key, "|cffff4488Forever STUwave|r: " .. text) end
    end
    Tab.WarnOnce = WarnOnce

    ---------------------------------------------------------------------------
    -- Who gets it, and what it shows
    ---------------------------------------------------------------------------

    function Tab.Applies()
        return Kit.PlayerClass() == def.class
    end

    function Tab.Enabled()
        return Kit.Setting(master)
    end

    -- The entries to show now, in seat order; empty for another class, the master off or nothing learned. A throwing or
    -- malformed read shows nothing and says so once.
    function Tab.Entries()
        if not (Tab.Applies() and Tab.Enabled()) then return {} end
        local ok, list = pcall(def.entries, Tab)
        if not ok or type(list) ~= "table" then
            WarnOnce("entries", def.field .. " could not read its list (" .. tostring(ok and "not a list" or list) .. ")")
            return {}
        end
        local out = {}
        for i = 1, math.min(#list, def.slots) do
            local entry = list[i]
            if type(entry) == "table" and entry.key then out[#out + 1] = entry end
        end
        return out
    end

    -- The columns and rows the shown entries need: the shoulder block is this wide. At least 1.
    function Tab.Cols()
        local cols = 1
        for i, entry in ipairs(Tab.Entries()) do cols = math.max(cols, entry.col or i) end
        return cols
    end

    function Tab.Shown()
        return T.built and #Tab.Entries() > 0
    end

    -- ClassShoulder.lua stands the block while this is true.
    function Tab.OwnsShoulder()
        return Tab.Shown()
    end

    function Tab.Buttons()
        return T.buttons
    end

    ---------------------------------------------------------------------------
    -- Buttons
    ---------------------------------------------------------------------------

    local function ShowTooltip(self)
        local tip = GameTooltip
        if not tip then return end
        tip:SetOwner(self, "ANCHOR_TOP")
        local shown = false
        if self.fsSpellID and tip.SetSpellByID then
            shown = pcall(tip.SetSpellByID, tip, self.fsSpellID)
        elseif self.fsItem and tip.SetItemByID then
            shown = pcall(tip.SetItemByID, tip, self.fsItem)
        end
        if not shown and self.fsTipText and tip.SetText then
            tip:SetText(self.fsTipText)
            if self.fsTipLine and tip.AddLine then tip:AddLine(self.fsTipLine, 0.7, 0.7, 0.7, true) end
            shown = true
        end
        if shown then tip:Show() else tip:Hide() end
    end
    Tab.ShowTooltip = ShowTooltip

    local function HideTooltip()
        GameTooltip:Hide()
    end

    local function MakeText(button, anchor, x, y)
        local fs = button:CreateFontString(nil, "OVERLAY")
        fs:SetPoint(anchor, button, anchor, x, y)
        fs:SetDrawLayer("OVERLAY", 4)
        FS.Theme.ApplyMono(fs, LOOK.TEXT_PX, FS.Theme.COLOR_TEXT_WHITE)
        local host = FS.FrameHelpers.SeatButtonText(button, fs)
        local plate = host:CreateTexture(nil, "OVERLAY", nil, 3)
        local p = LOOK.PLATE
        plate:SetColorTexture(p[1], p[2], p[3], p[4])
        plate:SetPoint("TOPLEFT", fs, "TOPLEFT", -2, 0)
        plate:SetPoint("BOTTOMRIGHT", fs, "BOTTOMRIGHT", 2, 0)
        plate:Hide()
        fs.fsPlate = plate
        return fs
    end

    -- Runs once per scale per button; everything that creates a region or hook is guarded so a throw partway is finished by
    -- the next Sync.
    local function StyleButton(button, size)
        local Theme, FH = FS.Theme, FS.FrameHelpers
        button:SetSize(size, size)
        if not button.fsPlate then
            button.fsPlate = Theme.AddCut2Texture(button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
        end
        Theme.SkinCutButton(button, { borderColor = Theme.COLOR_POWER, glowAlpha = LOOK.BORDER_ALPHA })
        if not button.fsWash then
            local wash = button:CreateTexture(nil, "OVERLAY", nil, 2)
            wash:SetTexture(Theme.SLICE_CUT2_FILL_TEXTURE)
            Theme.ApplyNineSlice(wash, Theme.SLICE_CUT_MARGIN)
            local c = Theme.COLOR_POWER
            wash:SetVertexColor(c[1], c[2], c[3], LOOK.ACTIVE_ALPHA)
            wash:SetBlendMode("ADD")
            wash:SetAllPoints(button)
            wash:Hide()
            button.fsWash = wash
        end
        if not button.fsHooked then
            button.fsHooked = true
            button:HookScript("OnEnter", ShowTooltip)
            button:HookScript("OnLeave", HideTooltip)
        end
        if not button.icon then
            local icon = button:CreateTexture(nil, "ARTWORK")
            icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
            button.icon = icon
        end
        FH.SeatCutIcon(button)
        if not button.cooldown then
            button.cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
        end
        FH.SeatButtonCooldown(button)
        if not button.fsCount then button.fsCount = MakeText(button, "BOTTOMRIGHT", -3, 3) end
        if not button.fsTop then button.fsTop = MakeText(button, "TOPRIGHT", -3, -2) end
        if not button.fsNudge then
            -- the pulse: a soft white wash over the face, hidden until a tab asks for it
            local nudge = button:CreateTexture(nil, "OVERLAY", nil, 3)
            nudge:SetTexture(Theme.SLICE_CUT2_FILL_TEXTURE)
            Theme.ApplyNineSlice(nudge, Theme.SLICE_CUT_MARGIN)
            nudge:SetVertexColor(1, 1, 1, LOOK.NUDGE_ALPHA)
            nudge:SetBlendMode("ADD")
            nudge:SetAllPoints(button)
            nudge:Hide()
            button.fsNudge = nudge
            if nudge.CreateAnimationGroup then
                local group = nudge:CreateAnimationGroup()
                group:SetLooping("REPEAT")
                local up = group:CreateAnimation("Alpha")
                up:SetFromAlpha(0.15)
                up:SetToAlpha(1)
                up:SetDuration(LOOK.NUDGE_TIME)
                up:SetOrder(1)
                local down = group:CreateAnimation("Alpha")
                down:SetFromAlpha(1)
                down:SetToAlpha(0.15)
                down:SetDuration(LOOK.NUDGE_TIME)
                down:SetOrder(2)
                button.fsNudgeGroup = group
            end
        end
    end

    local function BuildButton(index)
        local button = CreateFrame("Button", def.prefix .. index, T.host, "SecureActionButtonTemplate")
        button.index = index
        button:RegisterForClicks("AnyUp", "AnyDown")
        return button
    end

    ---------------------------------------------------------------------------
    -- Paint: texture, font string, cooldown and animation writes only (legal in combat)
    ---------------------------------------------------------------------------

    local function PaintRing(button)
        local skin, color = button.fsSkin, FS.Theme.COLOR_POWER
        if not (skin and color) then return end
        local r, g, b, glow = color[1], color[2], color[3], LOOK.BORDER_ALPHA
        if button.fsLit then
            local lift = LOOK.RING_LIFT
            r, g, b = r + (1 - r) * lift, g + (1 - g) * lift, b + (1 - b) * lift
            glow = LOOK.GLOW_ACTIVE
        end
        if skin.border and skin.border.ring then skin.border.ring:SetVertexColor(r, g, b, 1) end
        if skin.glow then skin.glow:SetVertexColor(color[1], color[2], color[3], glow) end
    end

    -- lit true or false is painted; nil (unreadable, or the tab's own light switch off) paints it dark too, unless
    -- `keep` says the answer was only unreadable.
    local function SetLit(button, lit, keep)
        if IsSecret(lit) then return end
        if lit == nil and keep then return end
        button.fsLit = lit == true
        PaintRing(button)
        local wash = button.fsWash
        if not wash then return end
        if button.fsLit then wash:Show() else wash:Hide() end
    end

    local function SetText(fs, text)
        if not fs then return end
        if text == nil or text == "" then
            fs:SetText("")
            if fs.fsPlate then fs.fsPlate:Hide() end
            return
        end
        fs:SetText(tostring(text))
        if fs.fsPlate then fs.fsPlate:Show() end
    end

    local function SetPulse(button, on)
        local nudge, group = button.fsNudge, button.fsNudgeGroup
        if not nudge then return end
        on = on == true
        if on == button.fsPulsing then return end
        button.fsPulsing = on
        if on then
            nudge:Show()
            if group then group:Play() end
        else
            if group then group:Stop() end
            nudge:Hide()
        end
    end

    local function PaintButton(button, entry)
        SetLit(button, entry.lit, entry.litUnknown)
        -- the tooltip lines are plain fields, so a live change (the poison on a weapon) reaches them in combat too
        button.fsTipText, button.fsTipLine = entry.tipText, entry.tipLine
        local icon = button.icon
        if icon then
            if icon.SetDesaturated then icon:SetDesaturated(entry.dim == true) end
            icon:SetAlpha(entry.dim and LOOK.DIM_ALPHA or 1)
        end
        SetText(button.fsCount, entry.count)
        SetText(button.fsTop, entry.top)
        SetPulse(button, entry.nudge)
    end
    local EMPTY = { key = false }

    -- The cooldown of the button's spell: the violet fill and the swipe, the way SealBar does it.
    local function UpdateCooldown(button)
        local cooldown = button.cooldown
        if not cooldown then return end
        local FH = FS.FrameHelpers
        local id = button.fsCdID
        if not id then
            cooldown:Clear()
            cooldown:Hide()
            FH.ClearCooldownFill(button)
            return
        end
        local modern = C_Spell and C_Spell.GetSpellCooldownDuration
        if modern then
            local ok, obj = false, nil
            if FH.HasCooldownFill(button) then ok, obj = pcall(modern, id, true) end
            if ok and not IsSecret(obj) and FH.SetCooldownFill(button, obj) then
                obj = FH.GcdDuration()
            else
                FH.ClearCooldownFill(button)
                ok, obj = pcall(modern, id)
                if not ok then obj = nil end
            end
            if not IsSecret(obj) and obj ~= nil then
                cooldown:SetCooldownFromDurationObject(obj)
            else
                cooldown:Clear()
            end
            cooldown:Show()
            return
        end
        local start, duration, enabled
        if C_Spell and C_Spell.GetSpellCooldown then
            local ok, info = pcall(C_Spell.GetSpellCooldown, id)
            if ok and type(info) == "table" and not IsSecret(info) then
                start, duration, enabled = info.startTime, info.duration, info.isEnabled
            end
        elseif _G.GetSpellCooldown then
            local ok, s, d, e = pcall(_G.GetSpellCooldown, id)
            if ok then start, duration, enabled = s, d, e end
        end
        FH.ApplyPlainCooldown(button, start, duration, enabled)
    end

    local function UpdateAllCooldowns()
        for _, button in ipairs(T.buttons) do
            if button.fsCdID then UpdateCooldown(button) end
        end
    end

    -- Repaints the lit state, counts and pulse of every bound button from a fresh read. Reads only what is bound: a
    -- change in WHAT is shown waits for Sync.
    function Tab.Paint()
        if not T.built then return end
        local byKey = {}
        for _, entry in ipairs(Tab.Entries()) do byKey[entry.key] = entry end
        for _, button in ipairs(T.buttons) do
            local entry = button.fsKey and byKey[button.fsKey]
            if entry then
                local ok, err = pcall(PaintButton, button, entry)
                if not ok then WarnOnce("paint", def.field .. " repaint failed (" .. tostring(err) .. ")") end
            end
        end
    end

    ---------------------------------------------------------------------------
    -- The seat
    ---------------------------------------------------------------------------

    function Tab.HostPoint()
        local shoulder = FS.ClassShoulder
        if shoulder and shoulder.HostPoint then
            local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint, def.shoulder)
            if ok and point then return point, rel, relPoint, x, y end
        end
        return nil
    end

    function Tab.SlotPoint(row, col)
        local shoulder = FS.ClassShoulder
        if shoulder and shoulder.SlotPoint then
            local ok, point, rel, relPoint, x, y = pcall(shoulder.SlotPoint, T.host, row, col, def.shoulder)
            if ok and point then return point, rel, relPoint, x, y end
        end
        local m, s = Metrics(), Scale()
        local pitch = m.BTN + m.GAP
        return "BOTTOMLEFT", T.host, "BOTTOMLEFT", (m.PAD + (col - 1) * pitch) * s,
            (m.PB + ((def.rows or 1) - row) * pitch) * s
    end

    local function BlockSize()
        local shoulder = FS.ClassShoulder
        if shoulder and shoulder.BlockSize then
            local ok, w, h = pcall(shoulder.BlockSize, def.shoulder)
            if ok and w then return w, h end
        end
        local m, s = Metrics(), Scale()
        local cols, rows = Tab.Cols(), def.rows or 1
        return (2 * m.PAD + cols * m.BTN + (cols - 1) * m.GAP) * s,
            (m.PT + rows * m.BTN + (rows - 1) * m.GAP + m.PB) * s
    end

    -- Anchors the host where the shoulder says and shows it, or hides it with no seat. Out of combat only.
    local function SeatHost()
        local host = T.host
        local point, rel, relPoint, x, y = Tab.HostPoint()
        if not point then
            host:Hide()
            return false
        end
        host:ClearAllPoints()
        host:SetPoint(point, rel, relPoint, x, y)
        host:SetSize(BlockSize())
        if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
        host:Show()
        return true
    end

    ---------------------------------------------------------------------------
    -- Sync: every protected step, out of combat
    ---------------------------------------------------------------------------

    local function SetAttributes(button, entry)
        local sig = entry.macro and ("m:" .. entry.macro) or entry.spell and ("s:" .. tostring(entry.spell)) or nil
        if sig == button.fsAttr then return end
        button.fsAttr = sig
        if entry.macro then
            button:SetAttribute("type", "macro")
            button:SetAttribute("macrotext", entry.macro)
            button:SetAttribute("spell", nil)
        elseif entry.spell then
            button:SetAttribute("type", "spell")
            button:SetAttribute("spell", entry.spell)
            button:SetAttribute("macrotext", nil)
        else
            button:SetAttribute("type", nil)
            button:SetAttribute("spell", nil)
            button:SetAttribute("macrotext", nil)
        end
    end

    local function ClearButton(button)
        SetAttributes(button, {})
        button.fsKey, button.fsSpellID, button.fsItem, button.fsCdID, button.fsTipText, button.fsTipLine = nil
        PaintButton(button, EMPTY)
        UpdateCooldown(button)
        button:Hide()
    end

    local function Apply(entries)
        local s = Scale()
        local m = Metrics()
        for i, button in ipairs(T.buttons) do
            StyleButton(button, m.BTN * s)
            local entry = entries[i]
            if not entry then
                ClearButton(button)
            else
                SetAttributes(button, entry)
                button.fsKey, button.fsSpellID, button.fsItem = entry.key, entry.id, entry.item
                button.fsCdID = entry.cd == nil and entry.id or entry.cd or nil
                button.fsTipText, button.fsTipLine = entry.tipText, entry.tipLine
                if entry.icon then FS.FrameHelpers.SetSpellIcon(button.icon, entry.icon) end
                button:ClearAllPoints()
                button:SetPoint(Tab.SlotPoint(entry.row or 1, entry.col or i))
                PaintButton(button, entry)
                UpdateCooldown(button)
                button:Show()
            end
        end
    end

    local function Sync()
        if not T.built then return end
        if InCombatLockdown() then
            T.pendingSync = true
            return
        end
        T.pendingSync = false
        local entries = Tab.Entries()
        local ok, err = pcall(function()
            local seated = #entries > 0 and SeatHost()
            if not seated then
                for _, button in ipairs(T.buttons) do ClearButton(button) end
                T.host:Hide()
                return
            end
            Apply(entries)
        end)
        if not ok then WarnOnce("sync", def.field .. " update failed (" .. tostring(err) .. ")") end
    end
    Tab.Sync = Sync

    -- What the buttons ARE changed (a spell learned, a pet called, a bag): the shoulder may come, go or change its width,
    -- then the buttons are written. Out of combat only; combat parks it.
    local function Relearn()
        if not T.built then return end
        if InCombatLockdown() then
            T.pendingSync = true
            return
        end
        if FS.ClassShoulder and FS.ClassShoulder.Refresh then
            local ok, err = pcall(FS.ClassShoulder.Refresh)
            if not ok then WarnOnce("shoulder", "class shoulder failed (" .. tostring(err) .. ")") end
        end
        Sync()
    end
    Tab.Relearn = Relearn

    ---------------------------------------------------------------------------
    -- Init
    ---------------------------------------------------------------------------

    local function Build()
        T.host = CreateFrame("Frame", def.host, UIParent)
        T.host:SetFrameStrata("LOW")
        T.host:Hide()
        for i = 1, def.slots do
            T.buttons[i] = BuildButton(i)
            T.buttons[i]:Hide()
        end
        T.built = true
        if FS.ModuleSwitch then FS.ModuleSwitch.MarkBuilt("m.class") end
    end

    local function OnEvent(_, event, ...)
        if event == "PLAYER_REGEN_ENABLED" then
            if T.pendingSync then Relearn() end
            Tab.Paint()
            return
        end
        if event == "SPELL_UPDATE_COOLDOWN" then
            UpdateAllCooldowns()
            return
        end
        if def.onEvent then pcall(def.onEvent, Tab, event, ...) end
        if T.syncSet[event] then
            Relearn()
            Tab.Paint()
        else
            Tab.Paint()
        end
    end

    local function RegisterEvents()
        local events = CreateFrame("Frame")
        T.events = events
        T.syncSet = {}
        local function reg(event, unit)
            local ok = false
            if unit then ok = pcall(events.RegisterUnitEvent, events, event, unit) end
            if not ok then pcall(events.RegisterEvent, events, event) end
        end
        for _, event in ipairs(SYNC_EVENTS) do T.syncSet[event] = true; reg(event) end
        for _, event in ipairs(def.syncEvents or {}) do T.syncSet[event] = true; reg(event) end
        for _, event in ipairs(def.liveEvents or {}) do reg(event) end
        for _, pair in ipairs(def.unitEvents or {}) do
            if pair[3] then T.syncSet[pair[1]] = true end
            reg(pair[1], pair[2])
        end
        reg("SPELL_UPDATE_COOLDOWN")
        reg("PLAYER_REGEN_ENABLED")
        events:SetScript("OnEvent", OnEvent)
    end

    local function Init()
        if not Tab.Applies() then return end
        if not (FS.Theme and FS.FrameHelpers and FS.Layout) then return end
        local ok, err = pcall(Build)
        if not ok then
            WarnOnce("build", def.field .. " failed to build (" .. tostring(err) .. ")")
            return
        end
        RegisterEvents()
        if FS.Config and FS.Config.OnChange then
            for _, setting in pairs(def.settings) do
                FS.Config.OnChange(setting.key, function()
                    Relearn()
                    Tab.Paint()
                end)
            end
        end
        if FS.Layout.OnRescale then FS.Layout.OnRescale(Sync) end
        if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(Sync) end
        if def.post then pcall(def.post, Tab) end
        Relearn()
    end
    Tab.Init = Init

    -- The Addon tabs page section (every class's rows exist for the class strip; `when` shows the chosen class's). Registered
    -- at login, once the window file has loaded.
    local function AddConfig()
        local CW = FS.ConfigWindow
        local spec = def.config
        if not (spec and CW and CW.ExtendTab and CW.UI and CW.ClassWhen) then return end
        CW.ExtendTab("tabs", "general", { title = spec.title, tip = spec.tip, when = CW.ClassWhen(def.class) }, function(content)
            for i, name in ipairs(spec.rows) do
                local setting = def.settings[name]
                CW.UI.Toggle(content, {
                    label = setting.label, key = setting.key, tip = setting.tip,
                    sub = i > 1 or nil, needs = i > 1 and master.key or nil, nl = i > 1 and master.label or nil,
                })
            end
        end)
    end
    Tab.AddConfig = AddConfig

    -- Built at PLAYER_LOGIN out of combat; a login in combat waits for regen (secure frames are made out of combat).
    local loader = CreateFrame("Frame")
    loader:RegisterEvent("PLAYER_LOGIN")
    loader:SetScript("OnEvent", function(self)
        self:UnregisterEvent("PLAYER_LOGIN")
        pcall(AddConfig)
        -- Module power (m.class): the config rows stay (the page is covered while it is off); nothing is built or listened for.
        local MS = FS.ModuleSwitch
        if MS and not MS.On("m.class") then return end
        if InCombatLockdown() then
            self:RegisterEvent("PLAYER_REGEN_ENABLED")
            self:SetScript("OnEvent", function(inner)
                inner:UnregisterEvent("PLAYER_REGEN_ENABLED")
                Init()
            end)
            return
        end
        Init()
    end)

    return Tab
end

-------------------------------------------------------------------------------
-- The Druid shapeshift tab
-------------------------------------------------------------------------------

local SETTINGS = {
    forms = {
        key = "tabs.druid.forms", default = true, label = "Shapeshift tab",
    },
    formsLit = {
        key = "tabs.druid.formsLit", default = true, label = "Light the form you are in",
    },
    formsCaster = {
        key = "tabs.druid.formsCaster", default = false, label = "Add a caster form button",
        tip = "One more button that drops you back out of any form.",
    },
}

-- Forms in button order, each with the spell ids that can be it (the first learned wins: Dire Bear replaces Bear).
local FORMS = {
    { key = "bear", ids = { 9634, 5487 } },
    { key = "cat", ids = { 768 } },
    { key = "travel", ids = { 783 } },
    { key = "aquatic", ids = { 1066 } },
    { key = "moonkin", ids = { 24858 } },
}
local CASTER_ICON = "Interface\\Icons\\Spell_Nature_Rejuvenation"

-- The form the player is in: 0 for none, the form index, and the spell id GetShapeshiftFormInfo says it is; nil when the
-- client will not say (secret or missing), so the light is left as it was.
local function CurrentForm()
    if type(GetShapeshiftForm) ~= "function" then return nil end
    local ok, index = pcall(GetShapeshiftForm)
    index = ok and Plain(index, "number") or nil
    if index == nil then return nil end
    if index == 0 then return 0, nil end
    if type(GetShapeshiftFormInfo) ~= "function" then return index, nil end
    local okInfo, _, _, _, id = pcall(GetShapeshiftFormInfo, index)
    return index, okInfo and Plain(id, "number") or nil
end

local function IsForm(form, id)
    for _, candidate in ipairs(form.ids) do
        if candidate == id then return true end
    end
    return false
end

local function Entries(Tab)
    local lit = Kit.Setting(SETTINGS.formsLit)
    local index, formId
    if lit then index, formId = CurrentForm() end
    local list = {}
    for _, form in ipairs(FORMS) do
        for _, id in ipairs(form.ids) do
            if Kit.Known(id) then
                local name, icon = Kit.SpellInfo(id)
                if name then
                    local entry = { key = form.key, id = id, spell = name, icon = icon }
                    if lit then
                        if index == nil or (index > 0 and formId == nil) then
                            entry.litUnknown = true
                        else
                            entry.lit = index > 0 and IsForm(form, formId)
                        end
                    end
                    list[#list + 1] = entry
                end
                break
            end
        end
    end
    if #list > 0 and Kit.Setting(SETTINGS.formsCaster) then
        local entry = { key = "caster", macro = "/cancelform", icon = CASTER_ICON, tipText = "Caster form",
            tipLine = "Leaves the form you are in." }
        if lit then
            if index == nil then entry.litUnknown = true else entry.lit = index == 0 end
        end
        list[#list + 1] = entry
    end
    return list
end

local Tab = Kit.New({
    field = "ShapeshiftTab", class = "DRUID", shoulder = "druid", host = "FSShapeshiftTab", prefix = "FSShapeshiftButton",
    slots = #FORMS + 1, rows = 1,
    settings = SETTINGS, master = "forms", entries = Entries,
    syncEvents = { "UPDATE_SHAPESHIFT_FORMS" },
    liveEvents = { "UPDATE_SHAPESHIFT_FORM" },
    config = {
        title = "Shapeshift tab",
        tip = "New. Your forms as buttons on the action bars: Bear, Cat, Travel, Aquatic and Moonkin, learned ones only. "
            .. "Click one to shift.",
        rows = { "forms", "formsLit", "formsCaster" },
    },
})
Tab.FORMS = FORMS

-- While this tab is on for a Druid it draws the forms, so StanceBar.lua builds none (the same hand over as a Paladin's
-- SealBar.OwnsForms); the stock bar stays dimmed either way. Turning the tab off hands the forms back to StanceBar.
function Tab.OwnsForms()
    local MS = FS.ModuleSwitch
    if MS and not MS.On("m.class") then return false end
    return Tab.Applies() and Tab.Enabled() == true
end
if FS.Config and FS.Config.OnChange then
    FS.Config.OnChange(SETTINGS.forms.key, function()
        if FS.StanceBar and FS.StanceBar.Rebuild then FS.StanceBar.Rebuild() end
    end)
end
