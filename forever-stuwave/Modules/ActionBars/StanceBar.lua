-- Forever STUwave: Stance Bar
--
-- BUILD-CUSTOM, same design as ActionBars.lua: our own SecureActionButtonTemplate
-- buttons with attributes set DIRECTLY from Lua, no secure snippet, no
-- RegisterStateDriver. See ActionBars.lua's header for why -- secure snippet
-- bodies do not execute on this client.
--
-- Class-agnostic: GetNumShapeshiftForms() returns 0 for classes with no forms
-- (mage, warlock, ...), in which case the container is never shown.
--
-- Secure attributes. There is NO "shapeshift" secure action type (the engine's list is
-- SECURE_ACTIONS in Blizzard_FrameXML/SecureTemplates.lua: action, pet, spell, macro, item, ...
-- no shapeshift), so a button typed that way does nothing when clicked. Blizzard's own
-- StanceButton cannot be copied either: it calls CastShapeshiftForm from an insecure OnClick,
-- which is only legal inside Blizzard's untainted code, and an addon calling it is refused.
-- A form is cast by its spell like any other, with the spell id from the 4th return of
-- GetShapeshiftFormInfo(index).
--
-- Casting the spell is not enough for a form you can leave: CastShapeshiftForm on the ACTIVE
-- form toggles it off (the stock bar's unstealth, Druid back to caster form), but casting the
-- Stealth spell while stealthed does not cancel it. So every class but the Warrior and
-- the Death Knight gets type="macro" with a click-time conditional (macro text is expanded C-side at the click, no
-- snippet and no attribute change, so it is right even when Stealth or a form flips in combat):
--     /cancelform [form:N]
--     /cast [noform:N] <the form's spell name>
-- N is the button's index, the same index GetShapeshiftFormInfo takes and [form:N] tests. The
-- spell name comes from the id; a name that cannot be read (nil, secret, a throw) leaves the
-- button on type="spell" + spell=<id>, which casts but cannot cancel. The WARRIOR stays on
-- type="spell": a stance cannot be cancelled (the stock bar's active stance does nothing when
-- clicked), so the macro would add a path that can only do what the spell already does. The
-- DEATHKNIGHT's presences are the same case (/cancelform is a no-op for them). A
-- Paladin's auras never come here (SealBar.lua draws them). The spell id and the macro text are
-- protected attribute writes: set out of combat only (SyncCastSpell) and caught up at
-- PLAYER_REGEN_ENABLED. A bound key never reaches these buttons: SHAPESHIFTBUTTONn runs
-- StanceBar:Select(n) in Blizzard's own code.
--
-- The buttons are built ONCE per form index and re-seated on every rebuild (form
-- count changes show or hide them), never re-created: a named secure frame cannot
-- be destroyed, so re-creating under the same global name leaked one per rebuild.
--
-- WARRIOR: its three stances stand on the class shoulder (ClassShoulder.lua, mockup `{id:'st',n:3,rows:1}`)
-- like the Paladin's seals, as three fixed slots in the order Battle, Defensive, Berserker. HostPoint/SlotPoint
-- are the only places that know the seat: the shoulder answers while it stands, and the stance bar's own seat
-- (Layout "stance") is the fallback. The container is the host, anchored to the Console root and never to the art.
--
-- First pass: click-to-activate only. Drag-and-drop (the shift/ctrl/alt-type1
-- "none" dance ActionBars.lua uses) is deferred -- stances are not draggable
-- Blizzard content in the first place (nothing to pick up/place), so there is
-- no drag behavior to replicate here.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme
-------------------------------------------------------------------------------

local SkinCutButton = FS.Theme.SkinCutButton
local IsSecret = FS.IsSecret
local COLOR_POWER = FS.Theme.COLOR_POWER

local BTN_GAP = 4

-- The Warrior's stances in the mockup's order (STANCES): the slot of a form is its place here.
local WARRIOR_STANCES = { "Battle Stance", "Defensive Stance", "Berserker Stance" }

-------------------------------------------------------------------------------
-- Cooldown
-------------------------------------------------------------------------------

-- Unlike action slots, there is no documented modern duration-object API for
-- shapeshift forms (C_ActionBar.GetActionCooldownDuration is action-slot
-- specific and does not accept a form index). GetShapeshiftFormCooldown is the
-- legacy positional API (start, duration, enable), feature-detected here and
-- guarded with FS.IsSecret before ever touching Cooldown:SetCooldown, exactly
-- ActionBars.lua's legacy branch. If it's absent, cooldown display is skipped
-- entirely and degraded once -- form cooldowns are rare/short and this is a
-- first pass, not a guess at an API that may not exist.
local HAS_SHAPESHIFT_COOLDOWN = type(GetShapeshiftFormCooldown) == "function"
local warnedNoCooldownApi = false

local function UpdateCooldown(button)
    local cooldown = button.cooldown
    if not cooldown then return end

    if not HAS_SHAPESHIFT_COOLDOWN then
        if not warnedNoCooldownApi then
            warnedNoCooldownApi = true
            FS.LogDegradeOnce("stancebar_nocooldownapi",
                "|cffff4488Forever STUwave|r: GetShapeshiftFormCooldown unavailable, " ..
                "stance bar cooldown display disabled")
        end
        cooldown:Hide()
        FS.FrameHelpers.ClearCooldownFill(button)
        return
    end

    -- The GCD as the swipe, a longer cooldown as the violet fill; a secret value hides both.
    FS.FrameHelpers.ApplyPlainCooldown(button, GetShapeshiftFormCooldown(button.index))
end

-------------------------------------------------------------------------------
-- Button visuals
-------------------------------------------------------------------------------

-- GetShapeshiftFormInfo, like GetShapeshiftFormCooldown above, is feature-
-- detected rather than assumed -- if it's absent, degrade once rather than
-- let every button silently fail through UpdateAll's outer pcall.
local HAS_SHAPESHIFT_FORM_INFO = type(GetShapeshiftFormInfo) == "function"
local warnedNoFormInfoApi = false
local warnedNoSpellId = false

-- How long a button may go without a spell id before that is reported. The form
-- data can lag the first reads at login, and a later event then supplies it.
local NO_SPELL_ID_GRACE = 5

-- A spell id that changed while the player was in combat: SetAttribute on a secure
-- button is refused there, so it waits for PLAYER_REGEN_ENABLED.
local pendingSync = false

-- One delayed look at a button that has no spell id yet: only if it is still shown
-- and still has none after the grace period does that count as "cannot cast". With
-- no C_Timer there is no way to wait, so nothing is reported (it never happens on
-- the live client; the click simply does nothing, as the form data says).
local function WatchForSpellId(button)
    if button.fsSpellIdWatch or not (C_Timer and C_Timer.After) then return end
    button.fsSpellIdWatch = true
    C_Timer.After(NO_SPELL_ID_GRACE, function()
        button.fsSpellIdWatch = false
        if button.fsCastSpell == nil and button:IsShown() and not warnedNoSpellId then
            warnedNoSpellId = true
            FS.LogDegradeOnce("stancebar_nospellid",
                "|cffff4488Forever STUwave|r: GetShapeshiftFormInfo gave no spell id, " ..
                "stance button " .. tostring(button.index) .. " cannot cast")
        end
    end)
end

local isWarrior = false      -- set at Apply; the Warrior's stances stay on type="spell" (see the header)
local spellOnly = false      -- set at Apply; Warrior and Death Knight stay on type="spell" (see the header)

-- The name of a spell id, a plain string or nil (SealBar.lua keeps its own).
local function SpellName(id)
    if IsSecret(id) or type(id) ~= "number" then return nil end
    local ok, name
    if C_Spell and C_Spell.GetSpellInfo then
        local info
        ok, info = pcall(C_Spell.GetSpellInfo, id)
        name = ok and not IsSecret(info) and type(info) == "table" and info.name or nil
    elseif GetSpellInfo then
        ok, name = pcall(GetSpellInfo, id)
        if not ok then name = nil end
    end
    if IsSecret(name) or type(name) ~= "string" then return nil end
    return name
end

-- The macro that leaves the form when it is the active one and casts it otherwise (see the header),
-- or nil when this button stays on type="spell".
local function FormMacro(button, spellID)
    if spellOnly then return nil end
    local name = SpellName(spellID)
    if not name then return nil end
    local n = button.index
    return "/cancelform [form:" .. n .. "]\n/cast [noform:" .. n .. "] " .. name
end

-- Points the button's click at its form's spell: the macro above where it applies, the plain spell
-- otherwise. The id is a plain number from the form info; a secret or non-number answer leaves the
-- attributes as they were (a button that never had one is watched, see WatchForSpellId).
local function SyncCastSpell(button, spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then
        if button.fsCastSpell == nil and not IsSecret(spellID) then
            WatchForSpellId(button)
        end
        return
    end
    local macro = FormMacro(button, spellID)
    if button.fsCastSpell == spellID and button.fsCastMacro == macro then return end
    if InCombatLockdown() then
        pendingSync = true
        return
    end
    -- type first, so the button is never briefly a macro button with no macrotext or the reverse
    button:SetAttribute("type", macro and "macro" or "spell")
    button:SetAttribute("macrotext", macro)
    button:SetAttribute("spell", spellID)
    button.fsCastSpell = spellID
    button.fsCastMacro = macro
end

-- Keybind text, top-right of the button; same shape as PetActionBar.lua's.
-- SHAPESHIFTBUTTON<i> is the binding command for stance slot i (Blizzard's own
-- StanceBar builds commandName from commandNamePrefix "SHAPESHIFT" .. "BUTTON"
-- .. i). Bindings are player config, not combat state, so never secret.
local function UpdateHotkey(button)
    local hotkey = button.HotKey
    if not hotkey then return end

    local key = GetBindingKey("SHAPESHIFTBUTTON" .. button.index)
    local text = FS.FrameHelpers.FormatBindingText(key)

    if text == "" then
        hotkey:SetText("")
        hotkey:Hide()
        if button.fsHotkeyPlate then button.fsHotkeyPlate:Hide() end
        return
    end

    hotkey:SetText(text)
    hotkey:Show()
    if button.fsHotkeyPlate then button.fsHotkeyPlate:SetShown(button.fsShouldered) end
end

local allButtons = {}   -- the shown stance buttons, rebuilt by Build
local container         -- FSStanceBar, made in Apply

-- The active stance's look, "signal rail" (mockups/stance-indicator-2026-11-12.html, option B, picked 2026-11-12):
--   * idle stances drop to dim greyscale, so the active one is the only button in colour;
--   * the active stance's ring goes white and its glow rises;
--   * cast-bar chevrons (ctl_chevron_h4, the controls kit's 8 x 4 strip) march along the bottom of its face;
--   * a rail runs under the row and a cyan carriage slides to the active stance with a little overshoot.
-- The checked state alone drew nothing (the cut skin has no checked art), so a Warrior could not tell the stance
-- from the bar. Texture, anchor and alpha writes on our own regions only: legal in combat.
local GLOW_IDLE, GLOW_ACTIVE, IDLE_ALPHA = 0.35, 0.7, 0.55
local CHEV_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\ctl_chevron_h4.tga"
local CHEV_PERIOD = 0.6                     -- seconds per 8 px chevron step (the mockup's march)
local RAIL = { GAP = 4, H = 2, CAR_W = 28, CAR_H = 4, ALPHA = 0.35 }   -- physical px
local rail                                  -- { frame, line, car, glow, x, v, target }

local function Px(frame, n)
    local ppu = FS.FrameHelpers.PixelsPerUnit and FS.FrameHelpers.PixelsPerUnit(frame) or 1
    if type(ppu) ~= "number" or ppu <= 0 then ppu = 1 end
    return n / ppu
end

-- The chevron strip along the bottom of a button's face: a clipping frame 3 px in from the sides and bottom, the
-- strip texture one chevron (8 px) wider than it, starting one chevron to the left, and a looping engine Translation
-- of one chevron per CHEV_PERIOD, so the march costs no Lua per frame. A client without animation groups shows the
-- strip still.
local function EnsureChevrons(button)
    if button.fsChevClip then return button.fsChevClip end
    local clip = CreateFrame("Frame", nil, button)
    clip:SetFrameLevel(button:GetFrameLevel() + 4)
    if clip.SetClipsChildren then clip:SetClipsChildren(true) end
    local tex = clip:CreateTexture(nil, "OVERLAY")
    tex:SetTexture(CHEV_TEXTURE, "REPEAT", "CLAMP")
    tex:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.9)
    clip.tex = tex
    if tex.CreateAnimationGroup then
        local group = tex:CreateAnimationGroup()
        group:SetLooping("REPEAT")
        local move = group:CreateAnimation("Translation")
        move:SetDuration(CHEV_PERIOD)
        clip.march, clip.move = group, move
    end
    clip:Hide()
    button.fsChevClip = clip
    return clip
end

local function SeatChevrons(button)
    local clip = EnsureChevrons(button)
    local step = Px(button, 8)
    clip:ClearAllPoints()
    clip:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", Px(button, 3), Px(button, 3))
    clip:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -Px(button, 3), Px(button, 3))
    clip:SetHeight(Px(button, 4))
    local width = (button:GetWidth() or 0) - 2 * Px(button, 3) + step
    clip.tex:ClearAllPoints()
    clip.tex:SetPoint("TOPLEFT", clip, "TOPLEFT", -step, 0)
    clip.tex:SetSize(math.max(step, width), Px(button, 4))
    clip.tex:SetTexCoord(0, math.max(1, width / step), 0, 1)
    if clip.move then clip.move:SetOffset(step, 0) end
end

local function PaintActive(button)
    local active = button.fsLastActive == true
    if button.icon then
        if button.icon.SetDesaturated then button.icon:SetDesaturated(not active) end
        if button.fsLastActive ~= nil then
            local v = active and 1 or IDLE_ALPHA
            button.icon:SetVertexColor(v, v, v)
        end
    end
    local clip = button.fsChevClip
    if clip then
        clip:SetShown(active)
        if clip.march then
            if active and not clip.march:IsPlaying() then clip.march:Play()
            elseif not active and clip.march:IsPlaying() then clip.march:Stop() end
        end
    end
    local skin, c = button.fsSkin, COLOR_POWER
    if skin and c then
        if skin.border and skin.border.ring then
            if active then skin.border.ring:SetVertexColor(1, 1, 1, 1) else skin.border.ring:SetVertexColor(c[1], c[2], c[3], 1) end
        end
        if skin.glow then skin.glow:SetVertexColor(c[1], c[2], c[3], active and GLOW_ACTIVE or GLOW_IDLE) end
    end
end

-- The carriage spring (stiffness 300, damping 22: a little overshoot, like the mockup's cubic-bezier) toward the
-- active stance's centre. The OnUpdate is installed only while the carriage moves and removed when it settles.
local function PlaceCarriage()
    rail.car:ClearAllPoints()
    rail.car:SetPoint("LEFT", rail.line, "LEFT", rail.x - rail.car:GetWidth() / 2, 0)
end

local function RailTick(frame, dt)
    if not (rail and rail.target) then frame:SetScript("OnUpdate", nil) return end
    dt = math.min(dt or 0, 0.05)
    local a = (rail.target - rail.x) * 300 - rail.v * 22
    rail.v = rail.v + a * dt
    rail.x = rail.x + rail.v * dt
    if math.abs(rail.target - rail.x) < 0.05 and math.abs(rail.v) < 0.05 then
        rail.x, rail.v = rail.target, 0
        frame:SetScript("OnUpdate", nil)
    end
    PlaceCarriage()
end

-- Seats the rail under the shown buttons and aims the carriage at the active one (snapping on first sight).
local function UpdateRail()
    if not container then return end
    if not rail then
        local f = CreateFrame("Frame", nil, container)
        local line = f:CreateTexture(nil, "ARTWORK")
        line:SetColorTexture(FS.Theme.COLOR_BORDER[1], FS.Theme.COLOR_BORDER[2], FS.Theme.COLOR_BORDER[3], RAIL.ALPHA)
        local glow = f:CreateTexture(nil, "ARTWORK", nil, 1)
        glow:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.3)
        local car = f:CreateTexture(nil, "ARTWORK", nil, 2)
        car:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
        glow:SetPoint("TOPLEFT", car, "TOPLEFT", -2, 2)
        glow:SetPoint("BOTTOMRIGHT", car, "BOTTOMRIGHT", 2, -2)
        rail = { frame = f, line = line, car = car, glow = glow, x = 0, v = 0 }
    end
    local first, last, active
    for _, button in ipairs(allButtons) do
        -- a frame that cannot report where it is (no GetLeft / GetCenter) gets no rail
        if type(button.GetLeft) ~= "function" or type(button.GetCenter) ~= "function" then
            rail.frame:Hide()
            return
        end
        if button:IsShown() then
            if not first or (button:GetLeft() or 0) < (first:GetLeft() or 0) then first = button end
            if not last or (button:GetRight() or 0) > (last:GetRight() or 0) then last = button end
            if button.fsLastActive == true then active = button end
        end
    end
    if not (first and last) then rail.frame:Hide() return end
    rail.frame:SetFrameLevel(first:GetFrameLevel() + 1)
    rail.line:ClearAllPoints()
    rail.line:SetPoint("TOPLEFT", first, "BOTTOMLEFT", 0, -Px(first, RAIL.GAP))
    rail.line:SetPoint("TOPRIGHT", last, "BOTTOMRIGHT", 0, -Px(first, RAIL.GAP))
    rail.line:SetHeight(Px(first, RAIL.H))
    rail.car:SetSize(Px(first, RAIL.CAR_W), Px(first, RAIL.CAR_H))
    rail.frame:Show()
    local left, centre = first:GetLeft(), active and active:GetCenter()
    if active and left and centre then
        rail.car:Show(); rail.glow:Show()
        local target = centre - left
        if not rail.target then rail.x, rail.v = target, 0 end
        rail.target = target
        if math.abs(rail.x - target) > 0.05 then rail.frame:SetScript("OnUpdate", RailTick) end
        PlaceCarriage()
    else
        rail.car:Hide(); rail.glow:Hide()
        rail.target = nil
        rail.frame:SetScript("OnUpdate", nil)
    end
end

-- GetShapeshiftFormInfo's flag, cross-checked against GetShapeshiftForm() when the flag is nil or secret (as
-- SealBar.lua does). Returns true / false, or nil when neither answer is plain.
local function ReadActive(index, flag)
    if flag ~= nil and not IsSecret(flag) then return flag and true or false end
    if type(GetShapeshiftForm) == "function" then
        local ok, current = pcall(GetShapeshiftForm)
        if ok and type(current) == "number" and not IsSecret(current) then return current == index end
    end
    return nil
end

-- The CheckButton flips its checked state natively on every click, so clicking the
-- ACTIVE form (a cast that changes nothing, so no event follows) would leave it
-- unchecked while it is still the active one. PostClick re-derives it from the form
-- info (PetActionBar.lua's SyncChecked pattern), for both halves of AnyDown+AnyUp.
-- A secret flag is never read: the last plain answer (button.fsLastActive, kept by
-- UpdateButton and here) is put back instead; with none cached the flip stays.
local function SyncChecked(button)
    if not HAS_SHAPESHIFT_FORM_INFO then return end
    local _, isActive = GetShapeshiftFormInfo(button.index)
    local active = ReadActive(button.index, isActive)
    if active ~= nil then
        button.fsLastActive = active
        button:SetChecked(active)
    elseif button.fsLastActive ~= nil then
        button:SetChecked(button.fsLastActive)
    end
    PaintActive(button)
    pcall(UpdateRail)
end

local function UpdateButton(button)
    -- The spell id first: it is the one part of this that decides whether a click
    -- does anything, so a throw in the visuals below must not skip it.
    local icon, isActive, isCastable, spellID
    if HAS_SHAPESHIFT_FORM_INFO then
        icon, isActive, isCastable, spellID = GetShapeshiftFormInfo(button.index)
        SyncCastSpell(button, spellID)
    end

    UpdateHotkey(button)

    if not HAS_SHAPESHIFT_FORM_INFO then
        if not warnedNoFormInfoApi then
            warnedNoFormInfoApi = true
            FS.LogDegradeOnce("stancebar_noforminfoapi",
                "|cffff4488Forever STUwave|r: GetShapeshiftFormInfo unavailable, " ..
                "stance bar button info disabled")
        end
        return
    end

    if button.icon then
        if IsSecret(icon) then
            -- an unreadable icon is neither drawn nor hidden: the last plain one stays
        elseif icon then
            FS.FrameHelpers.SetSpellIcon(button.icon, icon)
            button.icon:Show()
        else
            button.icon:Hide()
        end
    end

    -- CheckButton native checked state mirrors Blizzard's own StanceButton
    -- rather than a hand-rolled glow toggle -- secure-safe, simplest correct
    -- option for a first pass.
    local active = ReadActive(button.index, isActive)
    if active ~= nil then
        button.fsLastActive = active
        button:SetChecked(active)
    end
    PaintActive(button)

    -- isCastable can in theory go secret in combat on some clients; if so,
    -- skip the dim and show full alpha rather than guess.
    if button.icon then
        if IsSecret(isCastable) then
            button.icon:SetAlpha(1)
        elseif isCastable == false then
            button.icon:SetAlpha(0.4)
        else
            button.icon:SetAlpha(1)
        end
    end

    button.spellID = spellID
    UpdateCooldown(button)
end


local function UpdateAll()
    -- pendingSync is only cleared by a clean pass out of combat: in combat a write
    -- is skipped (and must stay owed), and a button that threw may not have synced.
    local clean = not InCombatLockdown()
    for _, button in ipairs(allButtons) do
        -- pcall-wrapped so one bad read doesn't kill the whole update loop,
        -- mirroring ActionBars.lua's pcall-wrapped Blizzard-bar hiding.
        if not pcall(UpdateButton, button) then clean = false end
    end
    local okRail, railErr = pcall(UpdateRail)
    if not okRail then
        FS.LogDegradeOnce("stancebar_rail", "|cffff4488Forever STUwave|r: stance rail skipped (" .. tostring(railErr) .. ")")
    end
    if clean then pendingSync = false end
end

-------------------------------------------------------------------------------
-- Tooltip
--
-- Same gap as PetActionBar.lua: plain "SecureActionButtonTemplate" alone, no
-- Blizzard tooltip wiring shipped with it. SetShapeshift is a Lua mixin
-- method, feature-detected rather than trusted from a metatable dump.
-------------------------------------------------------------------------------

local HAS_TOOLTIP_SETSHAPESHIFT = type(GameTooltip) == "table" and type(GameTooltip.SetShapeshift) == "function"
local warnedNoTooltipApi = false

local function ShowStanceTooltip(self)
    if not HAS_TOOLTIP_SETSHAPESHIFT then
        if not warnedNoTooltipApi then
            warnedNoTooltipApi = true
            FS.LogDegradeOnce("stancebar_notooltipapi",
                "|cffff4488Forever STUwave|r: GameTooltip:SetShapeshift unavailable, " ..
                "stance bar tooltips disabled")
        end
        return
    end

    -- Over the button, like the Thunder Clap tab beside it: the default anchor
    -- parks the tooltip in the far corner, away from the shoulder.
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetShapeshift(self.index)
    GameTooltip:Show()
end

local function HideStanceTooltip()
    GameTooltip:Hide()
end

-------------------------------------------------------------------------------
-- Button construction
-------------------------------------------------------------------------------

-- Runs on EVERY rebuild, not once: Build calls it for each shown button, so a throw
-- partway (which leaves the button registered, see Build) is finished by the next
-- rebuild, and a changed size is re-applied. Everything that creates a region, a
-- hook or a frame is therefore guarded, and SkinCutButton / SeatCutIcon /
-- SeatButtonCooldown / SeatButtonText are idempotent by themselves. The chamfer does
-- not follow the size: SkinCutButton pins it to SLICE_CUT_MARGIN (6) like the action
-- bars' baked plate, so a button of another height needs no re-chamfer, only the
-- icon and swipe re-seated off the new rect (SeatCutIcon, SeatButtonCooldown).
local function StyleButton(button, size, shouldered)
    button:SetSize(size, size)

    -- Same two-corner cut look as ActionBars.lua (top-left and bottom-right chamfered):
    -- gradient plate, then the cut border and glow via SkinCutButton.
    if not button.fsStancePlate then
        button.fsStancePlate = FS.Theme.AddCut2Texture(
            button, FS.Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end

    if SkinCutButton then
        SkinCutButton(button, {
            borderColor = COLOR_POWER,
            glowAlpha = 0.35,
        })
    end

    SeatChevrons(button)
    PaintActive(button)

    if not button.fsStanceHooked then
        button.fsStanceHooked = true
        button:HookScript("OnEnter", ShowStanceTooltip)
        button:HookScript("OnLeave", HideStanceTooltip)
        -- Undo the native checked flip once the click is over (see SyncChecked).
        button:HookScript("PostClick", SyncChecked)
    end

    if not button.icon then
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        button.icon = icon
    end
    -- Seated inside the cut shape (FrameHelpers.SeatCutIcon): inset 3px so the square
    -- corners clear the chamfer, since masks do not clip on this client (inset only,
    -- no mask is created).
    FS.FrameHelpers.SeatCutIcon(button)

    if not button.cooldown then
        button.cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
    end
    -- Full-icon already (the icon is inset like the main bars'), so this is not
    -- the template-inset bug ActionBars.lua had; it just pins the shared flags
    -- (no edge, no bling, black 0.64 swipe). Square swipe (no swipeTexture): the
    -- icon is square because masks don't clip here (see SeatCutIcon).
    FS.FrameHelpers.SeatButtonCooldown(button)

    -- Keybind label. Plain SecureActionButtonTemplate carries no HotKey region,
    -- so build one the way PetActionBar.lua does.
    if not button.HotKey then
        local hotkey = button:CreateFontString(nil, "OVERLAY")
        hotkey:SetPoint("TOPRIGHT", button, "TOPRIGHT", -2, -2)
        hotkey:SetJustifyH("RIGHT")
        if FS.Theme.ApplyMono then
            FS.Theme.ApplyMono(hotkey, 10, FS.Theme.COLOR_TEXT_WHITE)
        end
        button.HotKey = hotkey
    end

    -- The full-face swipe would otherwise dim the keybind (drawn on the button,
    -- under the cooldown's child frame).
    local textHost = FS.FrameHelpers.SeatButtonText(button, button.HotKey)

    -- On the shoulder the label is SealBar's: the action bars' dark text plate, 3 px in. Off it, the stance bar's own.
    button.fsShouldered = shouldered and true or false
    local hotkey = button.HotKey
    if shouldered then
        hotkey:ClearAllPoints()
        hotkey:SetWidth(0)
        hotkey:SetPoint("TOPRIGHT", button, "TOPRIGHT", -3, -2)
        hotkey:SetDrawLayer("OVERLAY", 4)
        if not button.fsHotkeyPlate then
            local plate = textHost:CreateTexture(nil, "OVERLAY", nil, 3)
            -- cut corners, and 1 unit inside the button's top and right ring so the ring stays whole
            FS.FrameHelpers.CutHotkeyPlate(plate)
            plate:SetPoint("TOPLEFT", hotkey, "TOPLEFT", -3, 1)
            plate:SetPoint("BOTTOMRIGHT", hotkey, "BOTTOMRIGHT", 2, -2)
            plate:Hide()
            button.fsHotkeyPlate = plate
        end
    elseif button.fsHotkeyPlate then
        hotkey:ClearAllPoints()
        hotkey:SetPoint("TOPRIGHT", button, "TOPRIGHT", -2, -2)
        hotkey:SetDrawLayer("OVERLAY", 0)
        button.fsHotkeyPlate:Hide()
    end
end

-- Built once per form index (see the header). `spell` is filled by SyncCastSpell
-- when the first UpdateAll reads the form info.
local function BuildButton(container, index)
    local button = CreateFrame(
        "CheckButton", "FSStanceButton" .. index, container, "SecureActionButtonTemplate")

    button.index = index

    -- Engine-resolved C-side at click time (CastSpellByID, or the macro text
    -- SyncCastSpell writes), no snippet anywhere in the path. RegisterForClicks AnyUp+AnyDown is load-bearing, see the
    -- Quick Keybind section of FrameHelpers.
    button:SetAttribute("type", "spell")
    button:RegisterForClicks("AnyUp", "AnyDown")

    -- Take part in Blizzard's Quick Keybind mode. See
    -- FrameHelpers.AttachQuickKeybind.
    FS.FrameHelpers.AttachQuickKeybind(button, "SHAPESHIFTBUTTON" .. index)

    return button
end

-- Re-seats a built button in the row. Runs on every rebuild: ClearAllPoints first,
-- so a re-seat replaces the anchor rather than stacking a second one.
local function SeatButton(container, button, previous)
    button:ClearAllPoints()
    if previous then
        button:SetPoint("LEFT", previous, "RIGHT", BTN_GAP, 0)
    else
        button:SetPoint("LEFT", container, "LEFT", 0, 0)
    end
end

-------------------------------------------------------------------------------
-- Blizzard frame
-------------------------------------------------------------------------------

-- The stock stance bar is `StanceBar` on this client (an Edit Mode action bar, like
-- the MultiBarN set: the 16001 globals dump has StanceBar and StanceButton1, and no
-- StanceBarFrame, so the old lookup silently found nothing). Its instance Hide is
-- Blizzard's HideOverride, so HideBlizzardFrame's Hide + HookScript would run
-- Blizzard's visibility code under our taint, the same class as the action bars'
-- SetCooldown error (see ActionBars.lua's "Blizzard bars" comment). DimActionBar
-- calls only SetAlpha and EnableMouse, on the bar, its containers and every stock
-- button. `StanceBarFrame` stays as a fallback for a client that still has the old
-- name. No restore path: we never bring the stock stance bar back. Run after every
-- build, not just at login: forms arrive after PLAYER_LOGIN, and the stock bar can
-- gain buttons the first sweep never saw (alpha cascades from the bar, EnableMouse
-- does not).
local function HideBlizzardStanceBar()
    if InCombatLockdown() then return end
    local stock = _G.StanceBar or _G.StanceBarFrame
    if stock then
        FS.FrameHelpers.DimActionBar(stock)
    end
end

-- Re-dims the stock bar on UPDATE_BINDINGS, UPDATE_SHAPESHIFT_FORM and at PLAYER_REGEN_ENABLED, so a stock
-- hotkey cannot draw under ours. A throw must not cost the state refresh around it; in combat the dim waits for regen.
local function RedimBlizzardStanceBar()
    pcall(HideBlizzardStanceBar)
end

-------------------------------------------------------------------------------
-- Warrior shoulder
-------------------------------------------------------------------------------

local buttons = {}      -- built buttons by form index; only ever grows, never re-created
local pendingBuild = false
local ownsShoulder = false

local function PlayerClassToken()
    local ok, _, token = pcall(UnitClass, "player")
    if ok and not IsSecret(token) then return token end
end

-- The shoulder slot (1..3) of each form 1..numForms: the mockup order by the form's spell name, and a form
-- whose name is unread or unlisted takes the slot of its own index when that is free (the trainer order is the
-- mockup's, so a client that names the stances differently still lands right). A form with no slot stays hidden.
local function ShoulderSlots(numForms)
    local slots, taken = {}, {}
    for form = 1, numForms do
        local ok, _, _, _, id = pcall(GetShapeshiftFormInfo, form)
        local name = ok and SpellName(id) or nil
        for slot, stance in ipairs(WARRIOR_STANCES) do
            if name == stance and not taken[slot] then
                slots[form], taken[slot] = slot, true
            end
        end
    end
    for form = 1, math.min(numForms, #WARRIOR_STANCES) do
        if not slots[form] and not taken[form] then slots[form], taken[form] = form, true end
    end
    return slots
end

-- Where the container stands while the shoulder carries the Warrior's stances, or nil for the stance bar's
-- own seat. The same numbers as the shoulder: the answer is the shoulder's.
local function HostPoint()
    local shoulder = FS.ClassShoulder
    if not (ownsShoulder and shoulder and shoulder.HostPoint) then return nil end
    local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint)
    if ok and point then return point, rel, relPoint, x, y end
end

-- Where the button of shoulder slot `col` (1..3) stands on the container.
local function SlotPoint(col)
    local shoulder = FS.ClassShoulder
    if not (ownsShoulder and container and shoulder and shoulder.SlotPoint) then return nil end
    local ok, point, rel, relPoint, x, y = pcall(shoulder.SlotPoint, container, 1, col)
    if ok and point then return point, rel, relPoint, x, y end
end

-- Seats the container on the shoulder and returns the button edge, or nil when no shoulder stands. The container
-- leaves Layout's re-seat list (its watcher would pull it back to the stance seat on every rescale; Build seats it
-- again from the rescale callback), which also takes its drag handle away in /fsedit.
local function SeatOnShoulder()
    local point, rel, relPoint, x, y = HostPoint()
    if not point then return nil end
    local w, h, edge = FS.ClassShoulder.BlockSize()
    if not w then return nil end
    if FS.Layout._applied then FS.Layout._applied[container] = nil end
    container:ClearAllPoints()
    container:SetPoint(point, rel, relPoint, x, y)
    container:SetSize(w, h)
    if rel.GetFrameLevel then container:SetFrameLevel(rel:GetFrameLevel() + 5) end
    return edge
end

local warnedShoulder = false
local refreshing = false     -- the shoulder is being asked to match: its notice back must not start a nested build

-- Says whether the Warrior's stances are the shoulder's to carry (a Warrior with forms), and asks the shoulder
-- to match, since it builds only for an owner that already says so. Out of combat only (Build).
local function SetOwnsShoulder(owns)
    if owns == ownsShoulder then return end
    ownsShoulder = owns
    local shoulder = FS.ClassShoulder
    if not (shoulder and shoulder.Refresh) then return end
    refreshing = true
    local ok, why = pcall(shoulder.Refresh)
    refreshing = false
    if not ok and not warnedShoulder then
        warnedShoulder = true
        FS.LogDegradeOnce("stancebar_shoulder",
            "|cffff4488Forever STUwave|r: class shoulder failed (" .. tostring(why) .. ")")
    end
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

-- Form count/order can change (talent respec, druid gaining a new form), so
-- UPDATE_SHAPESHIFT_FORMS re-runs this: buttons up to the form count are re-seated
-- and shown (created the first time they are needed), the rest are hidden.
local function Build()
    if not container then return end

    wipe(allButtons)

    local numForms = GetNumShapeshiftForms and GetNumShapeshiftForms() or 0
    if not numForms or numForms < 0 then numForms = 0 end
    -- A Paladin's auras are its forms; SealBar.lua draws them (with the seals), so no stance
    -- bar is built. Re-asked on every build: SealBar decides after this file's first build.
    if FS.SealBar and FS.SealBar.OwnsForms and FS.SealBar.OwnsForms() then numForms = 0 end
    -- A Druid's forms are drawn by the Shapeshift tab while it is on (read on every rebuild, and when it is switched).
    if FS.ShapeshiftTab and FS.ShapeshiftTab.OwnsForms and FS.ShapeshiftTab.OwnsForms() then numForms = 0 end
    for i = numForms + 1, #buttons do buttons[i]:Hide() end
    SetOwnsShoulder(isWarrior and numForms > 0)
    if numForms == 0 then
        container:Hide()
        HideBlizzardStanceBar()
        return
    end

    -- On the shoulder: the container sits on the Console and each stance in its fixed slot. Otherwise the stance
    -- bar's own seat, the buttons in a row.
    local size = SeatOnShoulder()
    local slots = size and ShoulderSlots(numForms)
    if not size then
        local applied = FS.Layout.Apply(container, "stance")
        size = (applied and applied.scaledH) or 38
    end

    local previous
    for i = 1, numForms do
        local button = buttons[i]
        if not button then
            button = BuildButton(container, i)
            -- Registered before it is styled: a named frame cannot be destroyed, so a
            -- throw in StyleButton must leave this one in `buttons` for the next
            -- Build to finish, never to CreateFrame again under the same name.
            buttons[i] = button
        end
        StyleButton(button, size, slots ~= nil)
        if not slots then
            SeatButton(container, button, previous)
            button:Show()
            allButtons[#allButtons + 1] = button
            previous = button
        else
            local point, rel, relPoint, x, y
            if slots[i] then point, rel, relPoint, x, y = SlotPoint(slots[i]) end
            if point then
                button:ClearAllPoints()
                button:SetPoint(point, rel, relPoint, x, y)
                button:Show()
                allButtons[#allButtons + 1] = button
            else
                button:Hide()
            end
        end
    end

    container:Show()
    UpdateAll()
    HideBlizzardStanceBar()
end

local function RequestBuild()
    -- SetAttribute, Show and SetPoint on a secure button are illegal in combat;
    -- the whole build is deferred to PLAYER_REGEN_ENABLED the same way as Init below.
    -- No container means Apply never ran (the Action bars module is off): a tab asking for a rebuild gets nothing.
    if refreshing or not container then return end
    if InCombatLockdown() then
        pendingBuild = true
        return
    end
    pendingBuild = false
    Build()
end

-- SealBar.lua asks for a rebuild once it owns a Paladin's forms. ClassShoulder.lua asks OwnsShoulder.
FS.StanceBar = {
    Rebuild = RequestBuild,
    OwnsShoulder = function() return ownsShoulder end,
    HostPoint = HostPoint,
    SlotPoint = SlotPoint,
}

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local events = CreateFrame("Frame")

local function OnEvent(_, event)
    if event == "UPDATE_SHAPESHIFT_FORMS" then
        RequestBuild()
    elseif event == "PLAYER_ENTERING_WORLD" then
        RequestBuild()
    elseif event == "PLAYER_REGEN_ENABLED" then
        if pendingBuild then
            RequestBuild()
        else
            if pendingSync then UpdateAll() end
            RedimBlizzardStanceBar()
        end
    else
        -- UPDATE_BINDINGS / UPDATE_SHAPESHIFT_FORM / UPDATE_SHAPESHIFT_COOLDOWN: state
        -- refresh only, no rebuild. The first two are when a stock hotkey would redraw.
        UpdateAll()
        if event ~= "UPDATE_SHAPESHIFT_COOLDOWN" then RedimBlizzardStanceBar() end
    end
end

local function RegisterEvents()
    for _, event in ipairs({
        "PLAYER_ENTERING_WORLD",
        "UPDATE_SHAPESHIFT_FORMS",
        "UPDATE_SHAPESHIFT_FORM",
        "UPDATE_SHAPESHIFT_COOLDOWN",
        -- A form change or a new spell id that arrived in combat.
        "PLAYER_REGEN_ENABLED",
        -- Hotkey text: refreshed on the same event Blizzard's own buttons use.
        "UPDATE_BINDINGS",
    }) do
        pcall(events.RegisterEvent, events, event)
    end
    events:SetScript("OnEvent", OnEvent)
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Apply()
    if not (FS.Layout and FS.Layout.Apply and FS.Layout.stance) then return end

    local class = PlayerClassToken()
    isWarrior = class == "WARRIOR"
    spellOnly = isWarrior or class == "DEATHKNIGHT"
    container = CreateFrame("Frame", "FSStanceBar", UIParent)
    container:SetFrameStrata("LOW")
    FS.Layout.Apply(container, "stance")
    container:Hide()

    -- Mirrors ActionBars.lua's Apply(): a construction-time failure (e.g. a
    -- Theme/Layout call throwing) degrades gracefully with Blizzard's stance
    -- bar left in place, rather than surfacing as an uncaught addon error at
    -- PLAYER_LOGIN/PLAYER_REGEN_ENABLED.
    local ok, err = pcall(Build)
    if not ok then
        print("|cff22e0ffForever STUwave|r: stance bar failed to build ("
            .. tostring(err) .. "); Blizzard bars left in place.")
        return
    end

    -- A rescale re-seats the container (Layout's own watcher, which holds a protected
    -- frame back in combat) and must re-size the buttons too, which only a build does:
    -- RequestBuild defers it to PLAYER_REGEN_ENABLED in combat.
    if FS.Layout.OnRescale then
        FS.Layout.OnRescale(RequestBuild)
    end
    -- The Console going on or off moves the shoulder (ClassShoulder.lua's own notice comes first), and the
    -- Warrior's stances follow it.
    if isWarrior and FS.ActionBars and FS.ActionBars.OnGeometry then
        FS.ActionBars.OnGeometry(RequestBuild)
    end

    FS.FrameHelpers.OnQuickKeybindChanged(function()
        for _, button in ipairs(allButtons) do UpdateHotkey(button) end
    end)
    RegisterEvents()
end

-- Deferred to PLAYER_LOGIN with an InCombatLockdown fallback to
-- PLAYER_REGEN_ENABLED, mirroring ActionBars.lua's loader.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    -- Module power: the stance bar is part of the Action bars module; off, the stock stance bar is left alone.
    local MS = FS.ModuleSwitch
    if MS and not MS.On("m.ab") then return end
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
