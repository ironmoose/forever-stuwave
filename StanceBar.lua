-- Forever Synthwave: Stance Bar
--
-- BUILD-CUSTOM, same design as ActionBars.lua: our own SecureActionButtonTemplate
-- buttons with attributes set DIRECTLY from Lua, no secure snippet, no
-- RegisterStateDriver. See ActionBars.lua's header for why -- secure snippet
-- bodies do not execute on this client.
--
-- Class-agnostic: GetNumShapeshiftForms() returns 0 for classes with no forms
-- (mage, warlock, ...), in which case the container is never shown.
--
-- Secure attributes: type="spell" + spell=<the form's spell id>, the 4th return of
-- GetShapeshiftFormInfo(index). There is NO "shapeshift" secure action type (the
-- engine's list is SECURE_ACTIONS in Blizzard_FrameXML/SecureTemplates.lua: action,
-- pet, spell, macro, item, ... no shapeshift), so a button typed that way does
-- nothing when clicked. Blizzard's own StanceButton cannot be copied either: it
-- calls CastShapeshiftForm from an insecure OnClick, which is only legal inside
-- Blizzard's untainted code, and an addon calling it is refused. A form is cast by
-- its spell like any other, so `spell` resolves C-side through CastSpellByID with
-- no snippet involved -- the same no-snippet mechanism as type="action" on the
-- main bars. The id is a protected attribute write: it is set out of combat only
-- (SyncCastSpell) and caught up at PLAYER_REGEN_ENABLED. A bound key never reaches
-- these buttons: SHAPESHIFTBUTTONn runs StanceBar:Select(n) in Blizzard's own code.
--
-- The buttons are built ONCE per form index and re-seated on every rebuild (form
-- count changes show or hide them), never re-created: a named secure frame cannot
-- be destroyed, so re-creating under the same global name leaked one per rebuild.
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
                "|cffff4488ForeverSynthwave|r: GetShapeshiftFormCooldown unavailable, " ..
                "stance bar cooldown display disabled")
        end
        cooldown:Hide()
        return
    end

    local start, duration, enable = GetShapeshiftFormCooldown(button.index)
    if not (start and duration) then
        cooldown:Hide()
        return
    end
    if IsSecret(start) or IsSecret(duration) then
        cooldown:Hide()
        return
    end

    cooldown:SetCooldown(start, duration)
    if not IsSecret(enable) and enable == 0 then
        cooldown:Hide()
    else
        cooldown:Show()
    end
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
                "|cffff4488ForeverSynthwave|r: GetShapeshiftFormInfo gave no spell id, " ..
                "stance button " .. tostring(button.index) .. " cannot cast")
        end
    end)
end

-- Points the button's click at its form's spell. The id is a plain number from the
-- form info; a secret or non-number answer leaves the attribute as it was (a button
-- that never had one is watched, see WatchForSpellId).
local function SyncCastSpell(button, spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then
        if button.fsCastSpell == nil and not IsSecret(spellID) then
            WatchForSpellId(button)
        end
        return
    end
    if button.fsCastSpell == spellID then return end
    if InCombatLockdown() then
        pendingSync = true
        return
    end
    button:SetAttribute("spell", spellID)
    button.fsCastSpell = spellID
end

-- Keybind text, top-right of the button; same shape as PetActionBar.lua's.
-- SHAPESHIFTBUTTON<i> is the binding command for stance slot i (Blizzard's own
-- StanceBar builds commandName from commandNamePrefix "SHAPESHIFT" .. "BUTTON"
-- .. i). Bindings are player config, not combat state, so never secret.
local function UpdateHotkey(button)
    local hotkey = button.HotKey
    if not hotkey then return end

    local key = GetBindingKey("SHAPESHIFTBUTTON" .. button.index)
    local text = key and GetBindingText(key, 1) or ""

    if text == "" then
        hotkey:SetText("")
        hotkey:Hide()
        return
    end

    hotkey:SetText(text)
    hotkey:Show()
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
    if not IsSecret(isActive) then
        local active = isActive and true or false
        button.fsLastActive = active
        button:SetChecked(active)
    elseif button.fsLastActive ~= nil then
        button:SetChecked(button.fsLastActive)
    end
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
                "|cffff4488ForeverSynthwave|r: GetShapeshiftFormInfo unavailable, " ..
                "stance bar button info disabled")
        end
        return
    end

    if button.icon then
        if icon then
            button.icon:SetTexture(icon)
            button.icon:Show()
        else
            button.icon:Hide()
        end
    end

    -- CheckButton native checked state mirrors Blizzard's own StanceButton
    -- rather than a hand-rolled glow toggle -- secure-safe, simplest correct
    -- option for a first pass.
    if not IsSecret(isActive) then
        button.fsLastActive = isActive and true or false
        button:SetChecked(button.fsLastActive)
    end

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

local allButtons = {}

local function UpdateAll()
    -- pendingSync is only cleared by a clean pass out of combat: in combat a write
    -- is skipped (and must stay owed), and a button that threw may not have synced.
    local clean = not InCombatLockdown()
    for _, button in ipairs(allButtons) do
        -- pcall-wrapped so one bad read doesn't kill the whole update loop,
        -- mirroring ActionBars.lua's pcall-wrapped Blizzard-bar hiding.
        if not pcall(UpdateButton, button) then clean = false end
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
                "|cffff4488ForeverSynthwave|r: GameTooltip:SetShapeshift unavailable, " ..
                "stance bar tooltips disabled")
        end
        return
    end

    if _G.GameTooltip_SetDefaultAnchor then
        _G.GameTooltip_SetDefaultAnchor(GameTooltip, self)
    else
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    end
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
local function StyleButton(button, size)
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
    FS.FrameHelpers.SeatButtonText(button, button.HotKey)
end

-- Built once per form index (see the header). `spell` is filled by SyncCastSpell
-- when the first UpdateAll reads the form info.
local function BuildButton(container, index)
    local button = CreateFrame(
        "CheckButton", "FSStanceButton" .. index, container, "SecureActionButtonTemplate")

    button.index = index

    -- Engine-resolved C-side at click time (CastSpellByID), no snippet anywhere
    -- in the path. RegisterForClicks AnyUp+AnyDown is load-bearing, see the
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

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

local container
local buttons = {}      -- built buttons by form index; only ever grows, never re-created
local pendingBuild = false

-- Form count/order can change (talent respec, druid gaining a new form), so
-- UPDATE_SHAPESHIFT_FORMS re-runs this: buttons up to the form count are re-seated
-- and shown (created the first time they are needed), the rest are hidden.
local function Build()
    if not container then return end

    wipe(allButtons)

    local numForms = GetNumShapeshiftForms and GetNumShapeshiftForms() or 0
    if not numForms or numForms < 0 then numForms = 0 end
    for i = numForms + 1, #buttons do buttons[i]:Hide() end
    if numForms == 0 then
        container:Hide()
        HideBlizzardStanceBar()
        return
    end

    local applied = FS.Layout.Apply(container, "stance")
    local h = (applied and applied.scaledH) or 38
    local size = h

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
        StyleButton(button, size)
        SeatButton(container, button, previous)
        button:Show()
        allButtons[#allButtons + 1] = button
        previous = button
    end

    container:Show()
    UpdateAll()
    HideBlizzardStanceBar()
end

local function RequestBuild()
    -- SetAttribute, Show and SetPoint on a secure button are illegal in combat;
    -- the whole build is deferred to PLAYER_REGEN_ENABLED the same way as Init below.
    if InCombatLockdown() then
        pendingBuild = true
        return
    end
    pendingBuild = false
    Build()
end

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
        elseif pendingSync then
            UpdateAll()
        end
    else
        -- UPDATE_SHAPESHIFT_FORM / UPDATE_SHAPESHIFT_COOLDOWN: state refresh
        -- only, no rebuild.
        UpdateAll()
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
        print("|cff22e0ffForeverSynthwave|r: stance bar failed to build ("
            .. tostring(err) .. "); Blizzard bars left in place.")
        return
    end

    -- A rescale re-seats the container (Layout's own watcher, which holds a protected
    -- frame back in combat) and must re-size the buttons too, which only a build does:
    -- RequestBuild defers it to PLAYER_REGEN_ENABLED in combat.
    if FS.Layout.OnRescale then
        FS.Layout.OnRescale(RequestBuild)
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
