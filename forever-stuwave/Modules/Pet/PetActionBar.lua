-- Forever STUwave: Pet Action Bar
--
-- BUILD-CUSTOM, same design as ActionBars.lua/StanceBar.lua: our own
-- SecureActionButtonTemplate buttons with attributes set DIRECTLY from Lua, no
-- secure snippet, no RegisterStateDriver.
--
-- Secure attributes: type="pet" + action=<index>. Engine-resolved C-side, same
-- no-snippet mechanism as type="action"/type="shapeshift".
--
-- Phase 5: buttons now build INTO FS.PetFrame.barSlot (built by PetFrame.lua's
-- Phase 2) instead of owning a standalone top-level container. Because our
-- SecureActionButtonTemplate buttons parent into barSlot, barSlot's ANCESTOR
-- (FS.PetFrame.container) becomes implicitly protected the moment the first
-- button is built -- Show()/Hide()/SetAttribute on IT throw ADDON_ACTION_BLOCKED
-- in combat, exactly as this file's own RequestBuild comment used to document
-- (verified against Wowpedia's Secure Execution and Tainting article plus two
-- real addon bug reports with the identical symptom). That is PetFrame.lua's
-- problem now, not this file's: it already builds combat-safe from day one
-- (its own header comment says so) and owns the whole show/hide gate. This
-- file's only remaining combat concern is SetAttribute on brand-new buttons at
-- build time (EnsureButtons below), never Show()/Hide()/SetAlpha() on any
-- container -- there is no container-visibility dance left in this file at all.
--
-- Native pet-bar suppression (PetActionBar / PetActionButton1-10 /
-- PetActionBarButtonContainer1-10) is likewise no longer this file's job --
-- PetFrame.lua's SuppressBlizzardPetBar owns it exclusively now. Duplicating it
-- here would just be redundant-safe noise on top of a job already done.
--
-- Drag-and-drop deferred (see ActionBars.lua's shift/ctrl/alt-type1 dance for
-- what that would look like).

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme
-------------------------------------------------------------------------------

local SkinCutButton = FS.Theme.SkinCutButton
local IsSecret = FS.IsSecret
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH
-- Green autocast-ring token: FS.Theme.COLOR_CARET_HEALTH is the addon's
-- canonical #39ff14 green (Theme.COLOR_HEAL aliases the same triple), not a
-- new hex invented for this file.
local COLOR_AUTOCAST = FS.Theme.COLOR_CARET_HEALTH

-- Not exported from Theme.lua as a canonical token (glow_round.tga is a
-- module-local literal path repeated per consuming file throughout this
-- addon -- ChatCore.lua/DataBar.lua/Minimap.lua/XPBar.lua/UnitFrames.lua all
-- declare their own copy of this exact string rather than share one field).
local GLOW_ROUND_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"

local BTN_SIZE_DESIGN = 30 -- design px at 2560x1440, matches PetFrame.lua's own BAR_HEIGHT
local BTN_GAP_DESIGN = 4   -- design px, matches PetFrame.lua's own GAP

-- NUM_PET_ACTION_SLOTS is a Blizzard-supplied constant on most clients; 10 is
-- the historical value and the hardcoded fallback if the global is absent.
local NUM_SLOTS = (type(NUM_PET_ACTION_SLOTS) == "number") and NUM_PET_ACTION_SLOTS or 10

-- Console-dock look (mockup option C, peButton). Cooldown seconds: white, mono 11,
-- outlined, centred on the button (the mockup's peT(..., 11, K.white, ..., 2.4)). Not scaled with the
-- UI scale; see StyleCountdown.
local COUNTDOWN_SIZE = 11
-- Hotkey: text size, and the dark plate behind it (the mockup's AB_PLATE, the same colour
-- ActionBars.lua gives its hotkey plate), all in design units and multiplied by the UI scale in
-- SeatHotkey so the text, its seat and the plate padding move together. The plate is anchored
-- to the FontString (not given a size), so it hugs the text whatever the key name is.
local HOTKEY_SIZE_DESIGN = 10
local HOTKEY_INSET_DESIGN = 1.5     -- the mockup's plate inset from the button's top and right edge
local PLATE_PAD_X_DESIGN = 2        -- plate padding beside the text (the mockup's is about 1.7)
local PLATE_PAD_Y_DESIGN = 0.5
local AB_PLATE = { 0.024, 0.012, 0.071, 0.78 }   -- rgba(6,3,18,.78)

-------------------------------------------------------------------------------
-- Cooldown
-------------------------------------------------------------------------------

-- C_ActionBar.GetPetActionCooldownDuration does NOT exist on this client
-- (confirmed absent from the 16001 globals dump) -- the duration-object branch
-- this file used to try first is dead code and has been removed outright.
-- Legacy GetPetActionCooldown is the only path left, same as it always was for
-- every client where the modern API is missing.
local HAS_LEGACY_PET_COOLDOWN = type(GetPetActionCooldown) == "function"
local warnedNoCooldownApi = false

local function UpdateCooldown(button)
    local cooldown = button.cooldown
    if not cooldown then return end

    if HAS_LEGACY_PET_COOLDOWN then
        local start, duration, enable = GetPetActionCooldown(button.index)
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
        return
    end

    if not warnedNoCooldownApi then
        warnedNoCooldownApi = true
        FS.LogDegradeOnce("petactionbar_nocooldownapi",
            "|cffff4488Forever STUwave|r: no pet action cooldown API available, " ..
            "pet bar cooldown display disabled")
    end
    cooldown:Hide()
end

-------------------------------------------------------------------------------
-- Autocast ring (the approved "Pet slot rings" of
-- mockups/castbar-v2-chevrons-locked-2026-10-01.html)
--
-- A circle of sixteen arcs (media/pet_slot_ring_00..15.tga, radius 11.5 design units on the 30
-- unit button, drawn 38 units square so the baked glow fits) in the addon green
-- (COLOR_AUTOCAST), on FS.ChevronCastBar.Fx, the cast bar's own motion. Steady lit while
-- autocast is enabled, a steady faint ring (the mockup's permanent unlit circle,
-- RING_UNLIT_ALPHA) while it is allowed but off, and absent when it is not allowed. Turning it
-- ON ignites the arcs (the bar segments' flicker); turning it OFF runs the 1.0 s power outage
-- (brownout, stutter, cut, fade) and ends on the faint ring. Reduced motion
-- (ForeverSTUwaveDB.reducedMotion, nothing sets it yet), a missing Fx, a button that is not
-- visible, and any read that is not a real transition of the SAME action all SNAP to the steady
-- state: the first paint after login, a reload or a pet summon (the slot's action name changes)
-- never ignites ten rings or burns one out. A secret autocast read is "unknown": the last look
-- stays and no new animation starts (one already running finishes and ends steady), and the next
-- plain read snaps (the slot was not read, so it cannot be a transition).
--
-- ONE driver frame carries ONE OnUpdate for every ring and only while some ring animates; a
-- steady ring costs nothing per frame. The arcs live on an insecure child frame of the secure
-- button (above its cooldown swipe, mouse disabled) and are shown and hidden one texture at a
-- time: the button itself is never shown, hidden or given an attribute. The ring is built
-- lazily, on the first slot that can show one (autocast allowed) and never in combat (the build
-- creates and anchors a child of the secure button; the PLAYER_REGEN_ENABLED refresh builds it,
-- snapped). media/hud_key_ring_NN.tga (ConsoleKeys) is a cut-corner key outline and does not fit
-- a square button; ConsoleKeys.lua's RingUpdate is the model for this file's PaintRing.
-------------------------------------------------------------------------------

local RING_N = 16
local RING_SPAN_DESIGN = 38    -- the 30 unit button plus a 4 unit pad on every side (the glow)
-- the mockup's faint unlit ring: under the lit arcs, and alone when off
local RING_UNLIT_ALPHA = 0.14
local RING_MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\pet_slot_ring_%02d.tga"

local ringDriver
local driverRunning = false
local activeRings = {}         -- ring record -> true while it animates

local function GetFx()
    return FS.ChevronCastBar and FS.ChevronCastBar.Fx
end

local function ReducedMotion()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

local function SetRingShown(ring, shown)
    if ring.shown == shown then return end
    ring.shown = shown
    for i = 1, RING_N do
        if shown then ring.arcs[i]:Show() else ring.arcs[i]:Hide() end
    end
end

local function ResetSegs(ring, litSince)
    if not ring.segs then return end
    for i = 1, RING_N do ring.segs[i].litSince = litSince end
end

-- Seats the arcs on the button's current size (called at build and from ResizeButtons).
local function SeatRing(button, ring)
    local span = button:GetWidth() * RING_SPAN_DESIGN / BTN_SIZE_DESIGN
    for i = 1, RING_N do ring.arcs[i]:SetSize(span, span) end
end

local function BuildRing(button)
    if button.fsAutoCastRing then return button.fsAutoCastRing end
    local Fx = GetFx()
    local ring = { arcs = {}, phase = "off", allowed = false, t0 = 0, shown = false }

    local host = CreateFrame("Frame", nil, button)
    host:SetAllPoints(button)
    host:EnableMouse(false)
    -- Above the cooldown swipe, below the keybind text.
    local cooldown = button.cooldown
    local level = math.max(button:GetFrameLevel(), cooldown and cooldown:GetFrameLevel() or 0) + 1
    host:SetFrameLevel(level)
    local textHost = button.fsTextHost
    if textHost and textHost:GetFrameLevel() <= level then textHost:SetFrameLevel(level + 1) end
    ring.host = host

    for n = 1, RING_N do
        local t = host:CreateTexture(nil, "OVERLAY", nil, 1)
        t:SetTexture(string.format(RING_MEDIA, n - 1))
        t:SetPoint("CENTER", button, "CENTER", 0, 0)
        t:SetVertexColor(COLOR_AUTOCAST[1], COLOR_AUTOCAST[2], COLOR_AUTOCAST[3], 0)
        t:Hide()
        ring.arcs[n] = t
    end
    SeatRing(button, ring)

    if Fx then
        ring.pal = Fx.MakePalette({
            base = { COLOR_AUTOCAST[1], COLOR_AUTOCAST[2], COLOR_AUTOCAST[3] },
        })
        ring.ctx = Fx.NewContext()
        ring.segs = {}
        for n = 1, RING_N do
            -- the mockup's ring seeds
            local seg = Fx.NewSeg(9000 + (button.index - 1) * 977 + (n - 1) * 131)
            seg.a = (n - 1) / RING_N
            seg.litSince = false
            ring.segs[n] = seg
        end
    end

    button.fsAutoCastRing = ring
    return ring
end

-- The steady look of a ring that is not animating: lit, faint, or absent.
local function PaintSteady(ring, lit)
    if ring.allowed then
        local a = lit and 1 or RING_UNLIT_ALPHA
        for i = 1, RING_N do
            ring.arcs[i]:SetVertexColor(COLOR_AUTOCAST[1], COLOR_AUTOCAST[2], COLOR_AUTOCAST[3], a)
        end
    end
    SetRingShown(ring, ring.allowed)
end

-- No Fx: the plain steady ring.
local function PaintFlat(ring)
    PaintSteady(ring, ring.phase == "on")
end

-- One frame of one ring (the mockup's ringUpdate, minus its idle breathing so a steady ring needs
-- no frames). Returns true while the ring still needs frames.
local function PaintRing(ring, Fx, now)
    local anim, intr = false, nil
    local lit = ring.phase ~= "off"
    if ring.phase == "outage" then
        local uT = (now - ring.t0) / Fx.INTR_MS
        if uT >= 1 then
            ring.phase = "off"
            lit = false
        else
            intr = Fx.phaseOf(uT < 0 and 0 or uT)
            anim = true
        end
    end
    if not lit then
        ResetSegs(ring, false)
        PaintSteady(ring, false)
        return false
    end
    local ctx = ring.ctx
    local ip = Fx.intrParams(intr)
    ctx.lit, ctx.snap, ctx.intr, ctx.ip = true, false, intr, ip
    ctx.level, ctx.fadeLit, ctx.extent = ip.level, 1, 1
    SetRingShown(ring, true)
    for i = 1, RING_N do
        local look = Fx.segLook(ring.pal, ring.segs[i], now, ctx)
        if look.anim then anim = true end
        if look.alpha > 0 then
            -- the unlit arcs are the faint ring under the lit ones
            local a = look.alpha
            if a < RING_UNLIT_ALPHA then a = RING_UNLIT_ALPHA end
            ring.arcs[i]:SetVertexColor(look.r, look.g, look.b, a)
        else
            ring.arcs[i]:SetVertexColor(
                COLOR_AUTOCAST[1], COLOR_AUTOCAST[2], COLOR_AUTOCAST[3], RING_UNLIT_ALPHA)
        end
    end
    return anim
end

-- Puts `button`'s ring into its steady state with no animation: lit, faint (allowed but off) or
-- absent.
local function SnapRing(ring, allowed, on)
    ring.allowed = allowed
    ring.phase = on and "on" or "off"
    activeRings[ring] = nil
    ResetSegs(ring, on and -1e9 or false)
    local Fx = ring.pal and GetFx()
    if Fx then PaintRing(ring, Fx, GetTime() * 1000) else PaintFlat(ring) end
end

local function TickRings()
    local Fx = GetFx()
    if not Fx then
        -- Fx vanished mid animation: end every running ring on its steady look, never mid frame.
        for ring in pairs(activeRings) do SnapRing(ring, ring.allowed, ring.phase == "on") end
        driverRunning = false
        ringDriver:SetScript("OnUpdate", nil)
        return
    end
    local now = GetTime() * 1000
    for ring in pairs(activeRings) do
        if not PaintRing(ring, Fx, now) then activeRings[ring] = nil end
    end
    if next(activeRings) == nil then
        driverRunning = false
        ringDriver:SetScript("OnUpdate", nil)
    end
end

local function ActivateRing(ring)
    activeRings[ring] = true
    if not driverRunning then
        driverRunning = true
        ringDriver = ringDriver or CreateFrame("Frame")
        ringDriver:SetScript("OnUpdate", TickRings)
    end
end

-- `animate` is true only for a real change of the same action's state, read after the first paint.
local function SetRingState(button, allowed, enabled, animate)
    local on = allowed and enabled and true or false
    local ring = button.fsAutoCastRing
    if not ring then
        -- The first build creates and anchors a child of the secure button: never in combat. The
        -- PLAYER_REGEN_ENABLED refresh builds it, and a first build always snaps.
        if not allowed or InCombatLockdown() then return end
        ring = BuildRing(button)
    end
    local Fx = ring.pal and GetFx()
    local visible = button.IsVisible and button:IsVisible()
    if not (allowed and animate and Fx and visible) or ReducedMotion() or not ring.allowed then
        SnapRing(ring, allowed, on)
        return
    end
    if (ring.phase == "on") == on then return end   -- an outage in progress keeps running
    if on then
        ring.phase = "on"
        ResetSegs(ring, false)
    else
        ring.phase = "outage"
    end
    ring.t0 = GetTime() * 1000
    ActivateRing(ring)
end

local warnedNoAutoCast = false

-- Positions 5/6 of GetPetActionInfo: autoCastAllowed (can this action ever autocast) and
-- autoCastEnabled (is it toggled on right now); `name` (position 1) says whether the slot still
-- holds the same action. The ring is lit only when both are true, faint when only `allowed` is,
-- absent when neither is. A secret in either is unknown: the last look stays and no new animation
-- starts.
local function UpdateAutoCast(button, name, autoCastAllowed, autoCastEnabled)
    if IsSecret(autoCastAllowed) or IsSecret(autoCastEnabled) then
        if not warnedNoAutoCast then
            warnedNoAutoCast = true
            FS.LogDegradeOnce("petactionbar_autocastsecret",
                "|cffff4488Forever STUwave|r: autocast fields returned a secret value, " ..
                "pet bar autocast ring keeps its last look for this button")
        end
        -- The slot was not read: forget its action so the next plain read snaps, never animates.
        button.fsAutoCastName = nil
        return
    end

    local same = false
    if name ~= nil and not IsSecret(name) then
        same = button.fsAutoCastName == name
        button.fsAutoCastName = name
    else
        button.fsAutoCastName = nil
    end
    SetRingState(button, autoCastAllowed and true or false, autoCastEnabled and true or false, same)
end

-------------------------------------------------------------------------------
-- Attack-active flash (locked slot-state visual)
--
-- IsPetAttackAction/IsPetAttackActive are feature-detected and pcall'd:
-- neither is confirmed present on this client (no probe result exists for
-- them anywhere in this addon's Diagnostics.lua), so a missing/throwing API
-- just means the flash never shows rather than an addon error. Built lazily,
-- not in StyleButton -- only ever one button (the attack slot) will ever need
-- it, unlike the autocast ring which is plausible on several slots at once.
-- The glow_round.tga + AnimationGroup technique XPBar.lua uses for its head glow, pink,
-- a faster ~0.25s cadence so it reads as a FLASH rather than a breathing
-- pulse -- the hand-rolled stand-in for native StartFlash, which this bare
-- SecureActionButtonTemplate build never inherited.
-------------------------------------------------------------------------------

local function BuildAttackFlash(button)
    if button.fsAttackFlash then return button.fsAttackFlash end

    local flash = button:CreateTexture(nil, "OVERLAY", nil, 5)
    flash:SetTexture(GLOW_ROUND_TEXTURE)
    flash:SetBlendMode("ADD")
    flash:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], 1)
    flash:SetPoint("TOPLEFT", button, "TOPLEFT", -4, 4)
    flash:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 4, -4)
    flash:Hide()

    local anim
    if flash.CreateAnimationGroup then
        anim = flash:CreateAnimationGroup()
        anim:SetLooping("REPEAT")
        local up = anim:CreateAnimation("Alpha")
        up:SetFromAlpha(0.25); up:SetToAlpha(1); up:SetDuration(0.25); up:SetOrder(1)
        local down = anim:CreateAnimation("Alpha")
        down:SetFromAlpha(1); down:SetToAlpha(0.25); down:SetDuration(0.25); down:SetOrder(2)
    end

    button.fsAttackFlash = { texture = flash, anim = anim }
    return button.fsAttackFlash
end

local function SetAttackFlashShown(button, shown)
    if shown then
        local flash = BuildAttackFlash(button)
        flash.texture:Show()
        if flash.anim and not flash.anim:IsPlaying() then flash.anim:Play() end
    elseif button.fsAttackFlash then
        local flash = button.fsAttackFlash
        if flash.anim then flash.anim:Stop() end
        flash.texture:Hide()
    end
end

local HAS_PET_ATTACK_ACTION = type(IsPetAttackAction) == "function"
local HAS_PET_ATTACK_ACTIVE = type(IsPetAttackActive) == "function"

local function UpdateAttackFlash(button)
    if not (HAS_PET_ATTACK_ACTION and HAS_PET_ATTACK_ACTIVE) then
        SetAttackFlashShown(button, false)
        return
    end

    local ok1, isAttackAction = pcall(IsPetAttackAction, button.index)
    local ok2, attackActive = pcall(IsPetAttackActive)
    if not (ok1 and ok2) then
        SetAttackFlashShown(button, false)
        return
    end
    if IsSecret(isAttackAction) or IsSecret(attackActive) then
        SetAttackFlashShown(button, false)
        return
    end

    SetAttackFlashShown(button, isAttackAction and attackActive and true or false)
end

-------------------------------------------------------------------------------
-- Button visuals
-------------------------------------------------------------------------------

-- Resolves a GetPetActionInfo texture: when isToken is true, `texture` is a
-- GLOBAL STRING NAME to look up via _G[texture], not a direct texture path --
-- replicated here to match Blizzard's own stock PetActionButton, or the
-- "unlearned"/special action tokens render as a nil texture.
local function ResolveTexture(texture, isToken)
    if not texture then return nil end
    if isToken then
        return _G[texture]
    end
    return texture
end

-- GetPetActionInfo, like the cooldown APIs above, is feature-detected rather
-- than assumed -- if it's absent, degrade once rather than let every button
-- silently fail through UpdateAll's outer pcall.
local HAS_PET_ACTION_INFO = type(GetPetActionInfo) == "function"
local warnedNoActionInfoApi = false

-- Keybind text, top-right of the button. Mirrors ActionBars.lua's own
-- UpdateHotkey: GetBindingKey resolves the player's actual binding, and the
-- shared formatter shortens mouse labels. "BONUSACTIONBUTTON"..i is the binding action name
-- for pet-bar slot i, matching the historical Blizzard pet-bar binding names.
-- Neither of these returns a secret value; bindings are player config, not
-- combat state.
local function UpdateHotkey(button)
    local hotkey = button.HotKey
    if not hotkey then return end

    local key = GetBindingKey("BONUSACTIONBUTTON" .. button.index)
    local text = FS.FrameHelpers.FormatBindingText(key)

    if text == "" then
        hotkey:SetText("")
        hotkey:Hide()
        if button.fsHotkeyPlate then button.fsHotkeyPlate:Hide() end
        return
    end

    hotkey:SetText(text)
    hotkey:Show()
    -- Anchored to the text, so it only needs showing alongside it.
    if button.fsHotkeyPlate then button.fsHotkeyPlate:Show() end
end

-- Re-derives the current-mode check from GetPetActionInfo. The button is a native
-- CheckButton, which flips its own checked state on every click; clicking the mode
-- that is already active (Follow while following) changes nothing server side, so no
-- PET_BAR_UPDATE comes to put the check back. Blizzard clears it in PreClick for the
-- same reason. Run after every click (StyleButton's PostClick hook).
-- IsSecret-guarded: a secret flag is never read, compared or written. When the flag is
-- secret the native flip is undone with the last known plain boolean instead
-- (button.fsLastActive, kept by UpdateButton and here); with none cached the flip stays.
local function SyncChecked(button)
    if not HAS_PET_ACTION_INFO then return end
    local _, _, _, isActive = GetPetActionInfo(button.index)
    if not IsSecret(isActive) then
        local active = isActive and true or false
        button.fsLastActive = active
        button:SetChecked(active)
    elseif button.fsLastActive ~= nil then
        button:SetChecked(button.fsLastActive)
    end
end

local function UpdateButton(button)
    UpdateHotkey(button)

    if not HAS_PET_ACTION_INFO then
        if not warnedNoActionInfoApi then
            warnedNoActionInfoApi = true
            FS.LogDegradeOnce("petactionbar_noactioninfoapi",
                "|cffff4488Forever STUwave|r: GetPetActionInfo unavailable, " ..
                "pet bar button info disabled")
        end
        return
    end

    -- Read positionally rather than assume all 9 return values always come
    -- back on every client -- a client returning fewer trailing values just
    -- leaves them nil, which every branch below already handles.
    local name, texture, isToken, isActive, autoCastAllowed, autoCastEnabled,
        spellID, checksRange, inRange = GetPetActionInfo(button.index)

    if button.icon then
        local resolved = ResolveTexture(texture, isToken)
        if resolved then
            button.icon:SetTexture(resolved)
            button.icon:Show()
        else
            button.icon:Hide()
        end
    end

    -- Current-pet-mode cyan check: button:SetChecked drives the native
    -- CheckedTexture StyleButton wires up below (button:SetCheckedTexture),
    -- so this IsSecret-guarded call is the only driver the visual needs -- the
    -- engine shows/hides that texture in sync with SetChecked automatically.
    if not IsSecret(isActive) then
        local active = isActive and true or false
        button.fsLastActive = active
        button:SetChecked(active)
    end

    -- Range feedback: dim when out of range, mirroring ActionBars.lua's
    -- UpdateUsable range handling. Skip when the range flags aren't usable.
    if button.icon then
        if not IsSecret(checksRange) and checksRange and not IsSecret(inRange) and inRange == false then
            button.icon:SetAlpha(0.55)
        else
            button.icon:SetAlpha(1)
        end
    end

    button.fsName = name
    button.spellID = spellID
    UpdateAutoCast(button, name, autoCastAllowed, autoCastEnabled)
    UpdateAttackFlash(button)
    UpdateCooldown(button)
end

local allButtons = {}

local function UpdateAll()
    for _, button in ipairs(allButtons) do
        pcall(UpdateButton, button)
    end
end

-------------------------------------------------------------------------------
-- Tooltip
--
-- These buttons are built from plain "SecureActionButtonTemplate" alone (see
-- BuildButton below) -- no ActionButtonTemplate, so no tooltip wiring of any
-- kind ships with them. SetPetAction is a Lua mixin method, not a C-side
-- widget method, so feature-detect it rather than trust a metatable dump.
--
-- Anchored ANCHOR_TOP (above the button) rather than the default
-- ANCHOR_RIGHT: this addon's GameTooltip is already a synthwave dark panel
-- addon-wide, skinned once by Tooltip.lua (SkinPanelCached, rounded fill +
-- gradient border + glow). GameTooltip is a single SHARED global frame reused
-- by every tooltip-showing surface in the game, not something this file can
-- give its own distinct chrome to without permanently fighting Tooltip.lua's
-- skin on every OTHER tooltip too (item tooltips, unit tooltips, etc.) -- so
-- this file changes only the anchor, and lets the already-applied panel skin
-- carry the "synthwave dark panel" requirement for free.
-------------------------------------------------------------------------------

local HAS_TOOLTIP_SETPETACTION = type(GameTooltip) == "table" and type(GameTooltip.SetPetAction) == "function"
local warnedNoTooltipApi = false

local function ShowPetActionTooltip(self)
    if not HAS_TOOLTIP_SETPETACTION then
        if not warnedNoTooltipApi then
            warnedNoTooltipApi = true
            FS.LogDegradeOnce("petactionbar_notooltipapi",
                "|cffff4488Forever STUwave|r: GameTooltip:SetPetAction unavailable, " ..
                "pet bar tooltips disabled")
        end
        return
    end

    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetPetAction(self.index)
    -- Right click toggles autocast (BuildButton's type2 route); say so only where the
    -- slot can autocast at all (position 5 of GetPetActionInfo).
    if HAS_PET_ACTION_INFO then
        local autoCastAllowed = select(5, GetPetActionInfo(self.index))
        if not IsSecret(autoCastAllowed) and autoCastAllowed then
            GameTooltip:AddLine("Right-click: toggle autocast", 0.7, 0.7, 0.7)
        end
    end
    GameTooltip:Show()
end

local function HidePetActionTooltip()
    GameTooltip:Hide()
end

-------------------------------------------------------------------------------
-- Button construction
-------------------------------------------------------------------------------

-- Cooldown seconds. CooldownFrameTemplate draws the countdown itself (engine-driven, so it keeps
-- counting through combat); this only switches it on and dresses its FontString like the mockup.
-- StyleCountdown runs at build and from ResizeButtons and reads no cooldown values (a secret
-- cooldown is hidden by UpdateCooldown before SetCooldown, never here). The size is a literal 11,
-- not multiplied by the UI scale, deliberately: a cooldown number is read at a glance and 11 is
-- the mockup's own size. The preferred route is a named font object handed to SetCountdownFont
-- (the engine re-reads it, so the template cannot revert the face), as Nameplates.lua does
-- for aura cooldowns; the direct SetFont on the countdown FontString is the fallback, and is why
-- ResizeButtons re-applies this on every rescale. Every call is guarded: a client without
-- these methods keeps the template's own look.
local COUNTDOWN_FONT = "FSPetCountdownFont"
local countdownFontReady

local function EnsureCountdownFont()
    if countdownFontReady ~= nil then return countdownFontReady end
    countdownFontReady = false
    if type(CreateFont) ~= "function" then return false end
    local Theme = FS.Theme
    local ok, fontObject = pcall(CreateFont, COUNTDOWN_FONT)
    if not ok or not fontObject then return false end
    local set = pcall(function()
        if fontObject:SetFont(Theme.FONT_MONO, COUNTDOWN_SIZE, "OUTLINE") == false then
            fontObject:SetFont("Fonts\\FRIZQT__.TTF", COUNTDOWN_SIZE, "OUTLINE")
        end
        local c = Theme.COLOR_TEXT_WHITE or { 1, 1, 1, 1 }
        fontObject:SetTextColor(c[1], c[2], c[3], c[4] or 1)
    end)
    countdownFontReady = set and true or false
    return countdownFontReady
end

local function StyleCountdown(cooldown)
    if cooldown.SetHideCountdownNumbers then
        pcall(cooldown.SetHideCountdownNumbers, cooldown, false)
    end
    if cooldown.SetCountdownFont and EnsureCountdownFont() then
        if pcall(cooldown.SetCountdownFont, cooldown, COUNTDOWN_FONT) then return end
    end
    if not cooldown.GetCountdownFontString then return end
    local ok, countdown = pcall(cooldown.GetCountdownFontString, cooldown)
    if not (ok and countdown) then return end
    local Theme = FS.Theme
    if Theme.ApplyFontGeneric and Theme.FONT_MONO then
        pcall(Theme.ApplyFontGeneric, countdown, Theme.FONT_MONO, COUNTDOWN_SIZE,
            Theme.COLOR_TEXT_WHITE, "OUTLINE")
    end
end

-- Seats the hotkey text in the button's top right corner and its plate around it, all from the
-- current UI scale. Called at build (StyleButton) and from ResizeButtons on every rescale, so the
-- text size, its seat and the plate padding scale together; the plate is anchored to the text, so
-- its size follows the key name and the font size with no width ever computed.
local function SeatHotkey(button)
    local hotkey = button.HotKey
    if not hotkey then return end
    local scale = (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
    local padX, padY = PLATE_PAD_X_DESIGN * scale, PLATE_PAD_Y_DESIGN * scale
    if FS.Theme.ApplyMono then
        FS.Theme.ApplyMono(hotkey, HOTKEY_SIZE_DESIGN * scale, FS.Theme.COLOR_TEXT_WHITE)
    end
    hotkey:ClearAllPoints()
    hotkey:SetWidth(0) -- auto width, so the plate hugs the text
    hotkey:SetPoint("TOPRIGHT", button, "TOPRIGHT",
        -(HOTKEY_INSET_DESIGN * scale + padX), -(HOTKEY_INSET_DESIGN * scale + padY))
    hotkey:SetJustifyH("RIGHT")
    local plate = button.fsHotkeyPlate
    if plate then
        plate:ClearAllPoints()
        plate:SetPoint("TOPLEFT", hotkey, "TOPLEFT", -padX, padY)
        plate:SetPoint("BOTTOMRIGHT", hotkey, "BOTTOMRIGHT", padX, -padY)
    end
end

local function StyleButton(button)
    -- Same two-corner cut look as ActionBars.lua (top-left and bottom-right chamfered):
    -- gradient plate, then the cut border and glow via SkinCutButton.
    FS.Theme.AddCut2Texture(
        button, FS.Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)

    if SkinCutButton then
        SkinCutButton(button, {
            borderColor = COLOR_POWER,
            glowAlpha = 0.35,
        })
    end

    if not button.icon then
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        button.icon = icon
    end
    -- Seated inside the cut shape (FrameHelpers.SeatCutIcon): inset 3px so the square
    -- corners clear the chamfer, since masks do not clip on this client. The washes
    -- below carry the cut shape themselves, for the same reason.
    FS.FrameHelpers.SeatCutIcon(button)

    if not button.cooldown then
        local cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
        button.cooldown = cooldown
        -- Full-icon already (the icon is inset like the main bars'), so this is not
        -- the template-inset bug ActionBars.lua had; it just pins the shared flags
        -- (no edge, no bling, black 0.64 swipe). Square swipe (no swipeTexture): the
        -- icon is square because masks don't clip here (see SeatCutIcon).
        FS.FrameHelpers.SeatButtonCooldown(button)
        StyleCountdown(cooldown)
    end

    -- Current-pet-mode cyan check: a translucent wash, handed to
    -- SetCheckedTexture, which the native CheckButton widget shows/hides
    -- automatically in sync with SetChecked -- the WIP already called
    -- SetChecked(isActive) but never gave the button a CheckedTexture at all, so
    -- that call rendered nothing. This is the fix, not new machinery. (2026-09-26:
    -- was a near-invisible 6x6px corner dot; now covers the whole face so the
    -- active state actually reads.)
    --
    -- The wash is the baked cut2 fill, nine-sliced at the chamfer, ADD blended and
    -- sized to the button, the same construction as the main bars' hover wash. A
    -- flat square plus an icon mask would tint the two chamfered-away corners,
    -- because the mask does not clip on this client.
    if not button.fsCheckedTextureSet then
        local checked = button:CreateTexture(nil, "OVERLAY", nil, 3)
        checked:SetTexture(FS.Theme.SLICE_CUT2_FILL_TEXTURE)
        FS.Theme.ApplyNineSlice(checked, FS.Theme.SLICE_CUT_MARGIN)
        checked:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.4)
        checked:SetBlendMode("ADD")
        checked:SetAllPoints(button)
        button:SetCheckedTexture(checked)
        button.fsCheckedTextureSet = true
    end

    -- Keybind label. Built here (the WIP had none at all) since this addon's
    -- own ActionBars.lua only gets a HotKey region for free by inheriting
    -- Blizzard's fuller ActionButtonTemplate -- our buttons, like StanceBar's
    -- and the old PetActionBar's, inherit the bare SecureActionButtonTemplate
    -- and have to build their own FontString. Theme.FONT_MONO is already the
    -- BOLD weight font file, so ApplyMono alone gives bold, no extra flags
    -- needed. SeatHotkey (below) sizes, seats and plates it from the UI scale.
    if not button.HotKey then
        button.HotKey = button:CreateFontString(nil, "OVERLAY")
    end

    -- The full-face swipe would otherwise dim the keybind (drawn on the button,
    -- under the cooldown's child frame). The same host carries the plate.
    local textHost = FS.FrameHelpers.SeatButtonText(button, button.HotKey)

    -- A dark plate behind the key (the mockup's AB_PLATE), on the text host so it stays above
    -- the swipe with the text; it hides and shows with the text (UpdateHotkey).
    if not button.fsHotkeyPlate then
        local plate = textHost:CreateTexture(nil, "OVERLAY", nil, 3)
        plate:SetColorTexture(AB_PLATE[1], AB_PLATE[2], AB_PLATE[3], AB_PLATE[4])
        plate:Hide()
        button.fsHotkeyPlate = plate
    end
    button.HotKey:SetDrawLayer("OVERLAY", 4)
    SeatHotkey(button)

    -- Mouseover: a white ADD-blend overlay sized to the button, alpha 0 by
    -- default -- the icon "brighten" is the additive wash itself, not a
    -- SetVertexColor multiply on the icon (which would fight the range-dim
    -- tint UpdateButton already drives). Same cut2 fill shape as the checked wash
    -- above, for the same reason.
    if not button.fsHighlight and button.icon then
        local highlight = button:CreateTexture(nil, "OVERLAY", nil, 4)
        highlight:SetTexture(FS.Theme.SLICE_CUT2_FILL_TEXTURE)
        FS.Theme.ApplyNineSlice(highlight, FS.Theme.SLICE_CUT_MARGIN)
        highlight:SetAllPoints(button)
        highlight:SetBlendMode("ADD")
        highlight:SetVertexColor(1, 1, 1, 0)
        button.fsHighlight = highlight
    end

    button:HookScript("OnEnter", function(self)
        ShowPetActionTooltip(self)
        if self.fsHighlight then self.fsHighlight:SetVertexColor(1, 1, 1, 0.35) end
    end)
    button:HookScript("OnLeave", function(self)
        HidePetActionTooltip()
        if self.fsHighlight then self.fsHighlight:SetVertexColor(1, 1, 1, 0) end
    end)

    -- The native CheckButton flip must not outlive the click (see SyncChecked). Runs
    -- for both halves of AnyDown+AnyUp, so the final state is right whatever the
    -- engine's flip count was; insecure, touches only the check.
    button:HookScript("PostClick", SyncChecked)
end

local function BuildButton(parent, index)
    local button = CreateFrame(
        "CheckButton", "FSPetActionButton" .. index, parent, "SecureActionButtonTemplate")

    button.index = index

    button:SetAttribute("type", "pet")
    button:SetAttribute("action", index)
    -- The secure "pet" action runs CastPetAction for EVERY mouse button, so without
    -- this a right click casts and autocast could never be turned back on. Route an
    -- UNMODIFIED right click to Blizzard's own hidden PetActionButton<index>, whose
    -- OnClick does LeftButton -> CastPetAction, anything else -> TogglePetAutocast
    -- (untainted Blizzard code). type2/macrotext2 do not match shift-, ctrl- or alt-
    -- prefixed clicks, so a modified right click falls back to type="pet" and casts.
    -- Index-stable, so this is written once here (SetAttribute is combat-protected)
    -- and never changes with the pet.
    button:SetAttribute("type2", "macro")
    button:SetAttribute("macrotext2", "/click PetActionButton" .. index .. " RightButton")
    button:RegisterForClicks("AnyUp", "AnyDown")

    -- Take part in Blizzard's Quick Keybind mode, under the same command the
    -- hotkey text reads. See FrameHelpers.AttachQuickKeybind.
    FS.FrameHelpers.AttachQuickKeybind(button, "BONUSACTIONBUTTON" .. index)

    return button
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

local buttons = {}
local built = false

-- Re-derives every button's size/gap/anchor from the current UI Scale,
-- mirroring PetFrame.lua's own ApplySlotGeometry -- BTN_SIZE_DESIGN/
-- BTN_GAP_DESIGN are literal scaled-pixel values, not automatic like a plain
-- SetPoint offset, so they need their own recompute on rescale exactly like
-- PetFrame.lua's slot heights/gaps do. Called once at build time and again
-- from the OnRescale callback EnsureButtons registers below.
local function ResizeButtons(barSlot)
    local scale = (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
    local size = BTN_SIZE_DESIGN * scale
    local gap = BTN_GAP_DESIGN * scale

    local previous
    for _, button in ipairs(buttons) do
        button:SetSize(size, size)
        if button.fsAutoCastRing then SeatRing(button, button.fsAutoCastRing) end
        SeatHotkey(button)
        if button.cooldown then StyleCountdown(button.cooldown) end
        button:ClearAllPoints()
        if previous then
            button:SetPoint("LEFT", previous, "RIGHT", gap, 0)
        else
            button:SetPoint("LEFT", barSlot, "LEFT", 0, 0)
        end
        previous = button
    end
end

local pendingResize = false

-- UI_SCALE_CHANGED/DISPLAY_SIZE_CHANGED (FS.Layout.OnRescale's trigger) can
-- fire mid-combat -- the player alt-tabbing or the game auto-adjusting
-- resolution mid-fight are both real cases, not hypothetical. ResizeButtons
-- mutates SetSize/ClearAllPoints/SetPoint on the buttons themselves, and
-- those are combat-restricted on a genuinely secure SecureActionButtonTemplate
-- frame exactly like Show()/Hide() already are on this file's implicitly-
-- protected ancestor (see this file's header comment). Mirrors PetFrame.lua's
-- own pendingLockApply idiom: a mid-combat request just flags itself here and
-- is re-applied for real once PLAYER_REGEN_ENABLED fires, in OnEvent below.
local function RequestResize(barSlot)
    if InCombatLockdown() then
        pendingResize = true
        return
    end
    pendingResize = false
    ResizeButtons(barSlot)
end

local function BuildButtons(barSlot)
    for i = 1, NUM_SLOTS do
        local button = BuildButton(barSlot, i)
        StyleButton(button)
        buttons[#buttons + 1] = button
        allButtons[#allButtons + 1] = button
    end
    ResizeButtons(barSlot)
end

local warnedNoBarSlot = false

-- Idempotent: returns immediately once built. Two independent conditions can
-- defer a build, and both simply retry on the NEXT event fire rather than a
-- timer, since every OnEvent branch below calls this again regardless of
-- outcome:
--   1. FS.PetFrame.barSlot not built yet (PetFrame.lua's own Init deferred
--      across a load-order/combat race). Read fresh off the table every call,
--      never captured into a permanent file-scope local, per this addon's
--      established multi-file sharing contract (PetFrame.lua's own header
--      comment states this explicitly for exactly this field).
--   2. InCombatLockdown(): SetAttribute("type"/"action") on brand-new buttons
--      is combat-restricted (same family as the Show()/Hide() restriction
--      this file's header describes for barSlot's ancestor), so a first build
--      requested mid-combat waits for PLAYER_REGEN_ENABLED like every other
--      combat-gated build in this addon.
local function EnsureButtons()
    if built then return true end

    local barSlot = FS.PetFrame and FS.PetFrame.barSlot
    if not barSlot then
        if not warnedNoBarSlot then
            warnedNoBarSlot = true
            FS.LogDegradeOnce("petactionbar_nobarslot",
                "|cffff4488Forever STUwave|r: FS.PetFrame.barSlot not ready yet, " ..
                "pet action bar build deferred")
        end
        return false
    end

    if InCombatLockdown() then return false end

    BuildButtons(barSlot)
    built = true

    if FS.Layout and FS.Layout.OnRescale then
        FS.Layout.OnRescale(function() RequestResize(barSlot) end)
    end

    return true
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local events = CreateFrame("Frame")

local function OnEvent(_, event, unit)
    -- UNIT_PET is a plain RegisterEvent (it fires on the pet's OWNER token,
    -- "player", not "pet" -- same reason UnitFrames.lua/PetFrame.lua both
    -- register it the identical way), so without this guard it would re-run
    -- for every visible unit's pet change, not just the player's own.
    if event == "UNIT_PET" and unit ~= "player" then return end
    -- UNIT_FLAGS is registered via SafeRegisterUnitEvent below, which already
    -- filters to "pet" -- this guard is defensive/explicit anyway, mirroring
    -- PetFrame.lua's identical stated reasoning for its own UNIT_FLAGS guard.
    if event == "UNIT_FLAGS" and unit ~= "pet" then return end

    EnsureButtons()

    if event == "PLAYER_REGEN_ENABLED" and pendingResize then
        local barSlot = FS.PetFrame and FS.PetFrame.barSlot
        if barSlot then RequestResize(barSlot) end
    end

    UpdateAll()
end

local function RegisterEvents()
    for _, event in ipairs({
        "PLAYER_ENTERING_WORLD",
        "PET_BAR_UPDATE",
        "PET_BAR_UPDATE_COOLDOWN",
        "UNIT_PET",
        "PLAYER_CONTROL_LOST",
        "PLAYER_CONTROL_GAINED",
        "PLAYER_REGEN_ENABLED",
        "SPELLS_CHANGED",
        "UPDATE_BINDINGS",
    }) do
        pcall(events.RegisterEvent, events, event)
    end
    FS.FrameHelpers.SafeRegisterUnitEvent(events, "UNIT_FLAGS", "pet", function(ev, err)
        FS.LogDegradeOnce("petactionbar_unitflags",
            "|cffff4488Forever STUwave|r: failed to register " .. ev
                .. " for pet action bar (" .. tostring(err) .. ")")
    end)
    events:SetScript("OnEvent", OnEvent)
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- No container to create anymore -- barSlot belongs to PetFrame.lua, and this
-- file only ever builds buttons INTO it (via EnsureButtons, itself deferred
-- until barSlot exists and combat allows attribute writes) plus keeps their
-- content updated. Visibility is entirely PetFrame.lua's gate now.
local function Apply()
    FS.FrameHelpers.OnQuickKeybindChanged(function()
        for _, button in ipairs(allButtons) do UpdateHotkey(button) end
    end)
    RegisterEvents()
    EnsureButtons()
    UpdateAll()
end

-- Mirrors PetFrame.lua's own Init(): a construction-time failure degrades
-- gracefully rather than surfacing as an uncaught addon error at
-- PLAYER_LOGIN/PLAYER_REGEN_ENABLED.
local function Init()
    local ok, err = pcall(Apply)
    if not ok then
        print("|cff22e0ffForever STUwave|r: pet action bar failed to build ("
            .. tostring(err) .. "); pet action bar not created.")
    end
end

-- Deferred to PLAYER_LOGIN with an InCombatLockdown fallback to
-- PLAYER_REGEN_ENABLED, mirroring PetFrame.lua's own loader.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
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
