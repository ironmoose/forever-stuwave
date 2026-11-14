-- Forever STUwave: HUD alerts and timers
-- The mirror timers (breath, fatigue, feign death), the item, money and recipe toasts and the vehicle exit key, restyled in
-- place from the approved HUD ALERTS mockup (mockups/hud-alerts-2026-11-12.html). Loss of control is LossOfControl.lua, the
-- zone and error text fonts and the territory colours are HudText.lua; this file adds the parts that were still stock.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, post-hooks
-- and alpha holds (FS.HeldArt) only, so the timers, the toast clicks and tooltips and the vehicle exit stay stock. Our plates and
-- cells are REGIONS of the stock frame (never a child frame), so the stock texts and the item icon keep drawing above them. A
-- stock frame is never given a Lua field: the state lives in weak tables, because the mirror timer container and the vehicle
-- exit key are Edit Mode system frames. Names are the real 12.1 tree (Blizzard_MirrorTimer, Blizzard_FrameXML AlertFrames.lua and
-- AlertFrameSystems.xml, Blizzard_ActionBar VehicleLeaveButton.xml), each feature-detected; a missing frame is skipped silently.
--
-- The toasts are found by SHAPE (a lootItem and an ItemName, an Amount with an IconBorder, a Title and a Name with a glow), and
-- a frame whose queue is a different alert system than the shape suggests is left alone. The alert system keeps its set up
-- function by reference, so the hooks are on the globals AlertFrame_ShowNewAlert, AlertFrame_PlayOutAnimation and
-- AlertFrame_PauseOutAnimation: the fuse line burns down over the very delay the stock code hands PlayOutAnimation.
--
-- Left out on purpose, because the mockup shows a computed or invented display and the rule for this pass is "keep the
-- functionality the same as vanilla": the level up banner (no LevelUpDisplay on this client), the achievement toast (the content
-- has no achievements), the toast acts beyond the icon flash (coin spin, scroll unroll, gem glint), the "need 87 / 4g 12s" chips,
-- the death recap health chart, the death, resurrect and corpse popup objects (candle, ankh, compass), the durability knight and
-- its percent chip, the mirror timer glyphs, bubbles, grains, monitor trace and time text, the marching hazard stripes and the
-- tooltip chip of the exit key, the error scrim and the stamped zone text with its territory pip.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit
if not (Theme and HeldArt and Kit and PanelSkins and PanelSkins.RequireExport(
    Theme.ApplyMono and Theme.AddCutSliceFill and Theme.Cut2ButtonSet and Kit.Plate and Kit.Animate and Kit.Track,
    "HudAlerts.lua disabled: FS.Theme, FS.HeldArt or FS.ControlKit missing")) then return end

local HA = {}
FS.HudAlerts = HA

local TEXTURES = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local HAZARD, PROMPT = TEXTURES .. "ctl_hazard.tga", TEXTURES .. "ctl_prompt.tga"
local HAZARD_SHEET = 64

local C = {
    ink = Theme.COLOR_CTRL_INK, cell = Theme.COLOR_CTRL_CELL, dim = Theme.COLOR_CTRL_DIM, sel = Theme.COLOR_CTRL_SEL,
    text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 }, dis = Theme.COLOR_CTRL_DIS or { 0.36, 0.33, 0.5 },
    cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER, gold = Theme.COLOR_GOLD,
    violet = Theme.COLOR_BORDER, blue = (Theme.COLOR_TOTEM and Theme.COLOR_TOTEM.water) or { 0.29, 0.66, 1, 1 },
    white = { 1, 1, 1, 1 },
}

-- Settings: each new visible part has an off switch (ConfigWindow.lua lists them under Panels).
HA.SETTINGS = {
    fuse = {
        key = "hud.alerts.fuse", label = "Toast timer line",
        tip = "A thin line burns down along the bottom of an item, money or recipe toast while it waits to fade.",
    },
    flash = {
        key = "hud.alerts.act", label = "Toast icon flash",
        tip = "The ring around the icon of a new item, money or recipe toast flashes once.",
    },
    low = {
        key = "hud.mirror.low", label = "Breath and fatigue warning",
        tip = "Under ten seconds the breath, fatigue and feign death bar turns pink and its last cells blink.",
    },
}
local SETTINGS = HA.SETTINGS
if FS.Config and FS.Config.RegisterDefault then
    for _, s in pairs(SETTINGS) do FS.Config.RegisterDefault(s.key, true) end
end

local function On(setting)
    local cfg = FS.Config
    if not (cfg and cfg.Get) then return true end
    local ok, v = pcall(cfg.Get, setting.key)
    if not ok or v == nil then return true end
    return v and true or false
end

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { mirror = Weak(), toast = Weak(), timing = Weak(), vehicle = Weak(), done = {} }
HA.state = S

local Plain, Try = Kit.Plain, Kit.Try

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("hudalerts:" .. name, ("|cffff4488Forever STUwave|r: HUD alert skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

local function List(frame, method)
    local fn = type(frame) == "table" and frame[method]
    if type(fn) ~= "function" then return {} end
    local out = { pcall(fn, frame) }
    if not table.remove(out, 1) then return {} end
    return out
end

-- Holds every texture region of `frame` (not its sub frames), except those in `keep`.
local function HoldRegions(frame, keep)
    for _, region in ipairs(List(frame, "GetRegions")) do
        if not (keep and keep[region]) then HeldArt.Hold(region) end
    end
end

local function Mono(fs, host, px, color)
    if type(fs) == "table" then Kit.RestyleLabel(fs, host, px, color or C.text) end
end

local function Clamp(v, lo, hi) return v < lo and lo or (v > hi and hi or v) end

-- UI units rounded to whole screen pixels at the pixel scale of `frame`.
local function Snap(frame, units)
    local ppu = Kit.Ppu(frame)
    return math.floor(units * ppu + 0.5) / ppu
end

-------------------------------------------------------------------------------
-- A plate laid over a stock frame, inset from its rect (stock units)
-------------------------------------------------------------------------------

local plates = Weak() -- host -> { plate, l, t, r, b }

local function SeatPlate(host)
    local rec = plates[host]
    if not rec then return end
    local p = rec.plate
    local l, t, r, b = Snap(host, rec.l), Snap(host, rec.t), Snap(host, rec.r), Snap(host, rec.b)
    local function seat(tex, extra)
        tex:ClearAllPoints()
        tex:SetPoint("TOPLEFT", host, "TOPLEFT", l + extra, -(t + extra))
        tex:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", -(r + extra), b + extra)
    end
    seat(p.fill, 0)
    seat(p.ring, 0)
    if p.ring2 then seat(p.ring2, 1 / Kit.Ppu(host)) end
end

local function AddPlate(host, c, l, t, r, b)
    local w, h = Kit.SizePx(host)
    local plate = Kit.Plate(host, c, w or 200, h or 60)
    plates[host] = { plate = plate, l = l, t = t, r = r, b = b }
    SeatPlate(host)
    return plate
end

-------------------------------------------------------------------------------
-- Mirror timers: breath, fatigue, feign death
-------------------------------------------------------------------------------

local MIRROR = { CELLS = 27, PAD = 12, GAP = 2, CELL_H = 10, TOP = 6, LOW = 10, BLINK = 4 }
local KIND = { BREATH = C.cyan, EXHAUSTION = C.amber, FEIGNDEATH = C.violet, DEATH = C.violet }

local function MirrorLayout(t)
    local m = S.mirror[t]
    if not m then return end
    -- the exact pixel width (206 units is 247.2 px at a pixel scale of 1.2), so the side margins differ by under a pixel
    local width = Plain(Try(t.GetWidth, t))
    local W = type(width) == "number" and width > 0 and width * Kit.Ppu(t) or 247.2
    local pitch = math.max(3, math.floor((W - 2 * MIRROR.PAD + MIRROR.GAP) / MIRROR.CELLS))
    local total = MIRROR.CELLS * pitch - MIRROR.GAP
    local x0 = math.floor((W - total) / 2 + 0.5)
    for i, cell in ipairs(m.cells) do
        Kit.Move(cell, x0 + (i - 1) * pitch, MIRROR.TOP, pitch - MIRROR.GAP, MIRROR.CELL_H)
    end
    SeatPlate(t)
end

local function MirrorPaint(t)
    local m = S.mirror[t]
    if not m then return end
    local kind = Plain(t.timer)
    local accent = KIND[type(kind) == "string" and kind or ""] or C.cyan
    local low = m.low and On(SETTINGS.low)
    if low then accent = C.pink end
    Kit.PaintPlate(m.plate, C.ink, 0.92, accent, 1, 2)
    for i, cell in ipairs(m.cells) do
        local lit = i <= m.lit
        local color = lit and accent or C.cell
        local alpha = 1
        if lit and low and m.blink and i > m.lit - 3 then alpha = 0.25 end
        cell:SetColorTexture(color[1], color[2], color[3], alpha)
    end
    if t.Text then Kit.Recolor(t.Text, low and C.pink or C.text) end
end

-- Reads the stock bar and repaints when the lit count or the low state changed.
local function MirrorSync(t)
    local m = S.mirror[t]
    local bar = t.StatusBar
    if not (m and type(bar) == "table") then return end
    local v = Plain(Try(bar.GetValue, bar))
    local lo, hi = Try(bar.GetMinMaxValues, bar)
    lo, hi = Plain(lo), Plain(hi)
    if type(v) ~= "number" or type(lo) ~= "number" or type(hi) ~= "number" then return end
    local frac = hi > lo and Clamp((v - lo) / (hi - lo), 0, 1) or 0
    local lit = math.ceil(frac * MIRROR.CELLS - 1e-6)
    local low = v >= 0 and v <= MIRROR.LOW and hi > MIRROR.LOW
    local kind = Plain(t.timer)
    if lit == m.lit and low == m.low and kind == m.kind then return end
    m.lit, m.low, m.kind = lit, low, kind
    local blinking = low and On(SETTINGS.low)
    if blinking and not Kit.IsAnimating(t, "low") then
        Kit.Animate(t, "low", function(_, elapsed)
            local on = math.floor(elapsed * MIRROR.BLINK) % 2 == 1
            if on ~= m.blink then
                m.blink = on
                MirrorPaint(t)
            end
        end)
    elseif not blinking then
        Kit.StopAnimate(t, "low")
        m.blink = false
    end
    MirrorPaint(t)
end

local function SkinMirrorTimer(t)
    if type(t) ~= "table" or S.mirror[t] or type(t.StatusBar) ~= "table" then return end
    HoldRegions(t)
    Kit.HoldFrame(t.StatusBar)
    local w, h = Kit.SizePx(t)
    local m = { cells = {}, lit = 0, low = false, blink = false }
    S.mirror[t] = m
    m.plate = AddPlate(t, 4, 0, 1, 0, 1)
    for i = 1, MIRROR.CELLS do
        m.cells[i] = Kit.Rect(t, 0, MIRROR.TOP, 4, MIRROR.CELL_H, C.cell, 1, "ARTWORK", 1)
    end
    Mono(t.Text, t, 12, C.text)
    MirrorLayout(t)
    MirrorPaint(t)
    local function again() MirrorSync(t) end
    Kit.HookFunc(t, "Setup", again)
    Kit.HookFunc(t.StatusBar, "SetValue", again)
    Kit.HookFunc(t.StatusBar, "SetMinMaxValues", again)
    Kit.HookScript(t, "OnShow", again)
    again()
end

local function BuildMirror()
    local container = _G.MirrorTimerContainer
    if type(container) ~= "table" then return end
    for _, t in ipairs(type(container.mirrorTimers) == "table" and container.mirrorTimers or {}) do
        Step("mirror", SkinMirrorTimer, t)
    end
end

-------------------------------------------------------------------------------
-- Alert toasts: item, money, recipe
-------------------------------------------------------------------------------

local TOAST = {
    loot = { accent = C.blue, c = 6, inset = { 10, 12, 10, 12 }, fuseLeft = 80, system = "LootAlertSystem" },
    money = { accent = C.gold, c = 6, inset = { 6, 8, 6, 8 }, fuseLeft = 60, system = "MoneyWonAlertSystem" },
    recipe = { accent = C.cyan, c = 6, inset = { 8, 5, 8, 5 }, fuseLeft = 88, system = "NewRecipeLearnedAlertSystem" },
}
local FUSE = { PAD = 12, UP = 7, H = 2, FLASH = 0.6, RING = 3 }

local function ToastKind(f)
    if type(f) ~= "table" then return nil end
    local kind
    if type(f.lootItem) == "table" and f.ItemName and f.Label then kind = "loot"
    elseif f.Amount and f.Label and f.Icon and f.IconBorder and not f.lootItem then kind = "money"
    elseif f.Title and f.Name and f.Icon and f.glow and f.shine and not f.Unlocked then kind = "recipe" end
    if not kind then return nil end
    -- a frame that names its alert system must be the one the shape suggests (honor awards look like money toasts)
    local system = _G[TOAST[kind].system]
    if type(system) == "table" and f.queue ~= nil and f.queue ~= system then return nil end
    return kind
end

local function ToastIcon(f, kind)
    if kind == "loot" then return type(f.lootItem) == "table" and f.lootItem.Icon or nil end
    return f.Icon
end

-- Where the fuse line runs, in physical pixels of the toast: inside the plate, under the text and clear of the icon ring
-- (`fuseLeft` is the stock x of the ring's right edge in units: the icon sits 22, 16 or 18 units in and is 52, 38 or 64 wide).
local function SeatFuse(f)
    local rec = S.toast[f]
    local W, H = Kit.SizePx(f)
    if not (rec and W) then return end
    local ppu = Kit.Ppu(f)
    local ins = rec.spec.inset
    local left, bottom, right = math.floor(ins[1] * ppu + 0.5), math.floor(ins[4] * ppu + 0.5), math.floor(ins[3] * ppu + 0.5)
    rec.fuseX = math.max(left + FUSE.PAD, math.floor(rec.spec.fuseLeft * ppu + 0.5))
    rec.fuseW = math.max(8, W - right - FUSE.PAD - rec.fuseX)
    rec.fuseY = H - bottom - FUSE.UP
    Kit.Move(rec.track, rec.fuseX, rec.fuseY, rec.fuseW, FUSE.H)
    rec.fuseNow = nil
end

local function SeatRing(rec, f)
    local icon = rec.icon
    if not icon then return end
    local pad = Snap(f, FUSE.RING)
    rec.ring:ClearAllPoints()
    rec.ring:SetPoint("TOPLEFT", icon, "TOPLEFT", -pad, pad)
    rec.ring:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT", pad, -pad)
end

-- One step of the fuse: the width of the lit line from the stock hold time. False when it has burnt out or is frozen.
local function FuseStep(f)
    local rec, tm = S.toast[f], S.timing[f]
    if not (rec and tm and rec.fuseW) then return false end
    local frac
    if tm.paused then frac = tm.frozen or 1
    else frac = 1 - (Kit.Now() - tm.t0) / math.max(tm.hold, 0.05) end
    frac = Clamp(frac, 0, 1)
    local wpx = math.floor(rec.fuseW * frac + 0.5)
    if wpx ~= rec.fuseNow then
        rec.fuseNow = wpx
        if wpx > 0 then
            Kit.Move(rec.fill, rec.fuseX, rec.fuseY, wpx, FUSE.H)
            rec.fill:Show()
        else
            rec.fill:Hide()
        end
    end
    return frac > 0 and not tm.paused
end

local function ArmFuse(f)
    local rec = S.toast[f]
    if not rec then return end
    if not On(SETTINGS.fuse) then
        Kit.StopAnimate(f, "fuse")
        rec.track:Hide()
        rec.fill:Hide()
        return
    end
    rec.track:Show()
    rec.fuseNow = nil
    FuseStep(f)
    Kit.Animate(f, "fuse", function()
        if not FuseStep(f) then Kit.StopAnimate(f, "fuse") end
    end)
end

local function ArmFlash(f)
    local rec = S.toast[f]
    if not rec then return end
    local accent = rec.spec.accent
    rec.ring:SetVertexColor(accent[1], accent[2], accent[3], 1)
    if not On(SETTINGS.flash) then
        Kit.StopAnimate(f, "flash")
        return
    end
    Kit.Animate(f, "flash", function(_, elapsed)
        local p = Clamp(elapsed / FUSE.FLASH, 0, 1)
        local c = Kit.Mix(C.white, accent, Kit.Ease.outQuad(p))
        rec.ring:SetVertexColor(c[1], c[2], c[3], 1)
        if p >= 1 then Kit.StopAnimate(f, "flash") end
    end)
end

local function LayoutToast(f)
    local rec = S.toast[f]
    if not rec then return end
    SeatPlate(f)
    SeatRing(rec, f)
    SeatFuse(f)
    if rec.fuseW and S.timing[f] then rec.fuseNow = nil; FuseStep(f) end
end

local function SkinToast(f, kind)
    local spec = TOAST[kind]
    local rec = { kind = kind, spec = spec, icon = ToastIcon(f, kind) }
    S.toast[f] = rec
    -- the stock plate, its glow and its sheen go; the icon (and the roll dice of an item toast) stay
    local keep = {}
    if kind ~= "loot" and type(f.Icon) == "table" then keep[f.Icon] = true end
    if type(f.RollTypeIcon) == "table" then keep[f.RollTypeIcon] = true end
    HoldRegions(f, keep)
    if kind == "loot" then
        local item = f.lootItem
        local keepIcon = {}
        if type(item.Icon) == "table" then keepIcon[item.Icon] = true end
        HoldRegions(item, keepIcon)
    end
    local ins = spec.inset
    rec.plate = AddPlate(f, spec.c, ins[1], ins[2], ins[3], ins[4])
    Kit.PaintPlate(rec.plate, C.ink, 0.94, spec.accent, 1, 2)
    rec.ring = Theme.AddSliceTexture(f, (Theme.Cut2ButtonSet(3)), { 1, 1, 1, 1 }, "BORDER", 3)
    Theme.ApplyNineSlice(rec.ring, Theme.SnapCut(3))
    SeatRing(rec, f)
    rec.track = Kit.Rect(f, 0, 0, 8, FUSE.H, C.dim, 0.8, "ARTWORK", 2)
    rec.fill = Kit.Rect(f, 0, 0, 8, FUSE.H, spec.accent, 1, "ARTWORK", 3)
    SeatFuse(f)
    -- the texts: kind-coloured small label over a mono name, the quality colour of an item name stays the stock code's
    if kind == "loot" then
        Mono(f.Label, f, 11, spec.accent)
        Mono(f.ItemName, f, 15, C.white)
        Mono(f.RollValue, f, 13, C.text)
    elseif kind == "money" then
        Mono(f.Label, f, 11, spec.accent)
        Mono(f.Amount, f, 15, C.white)
    else
        Mono(f.Title, f, 11, spec.accent)
        Mono(f.Name, f, 15, C.white)
    end
    return rec
end

-- AlertFrame_PlayOutAnimation(frame, delay): the stock code starts the wait before the fade; that wait is the fuse.
local function NoteOutAnimation(f, delay)
    if type(f) ~= "table" then return end
    local tm = S.timing[f] or {}
    S.timing[f] = tm
    tm.t0, tm.hold, tm.paused, tm.frozen = Kit.Now(), type(delay) == "number" and delay > 0 and delay or 1, false, nil
    if S.toast[f] then ArmFuse(f) end
end

local function NotePause(f)
    local tm = type(f) == "table" and S.timing[f]
    if not tm then return end
    local frac = Clamp(1 - (Kit.Now() - tm.t0) / math.max(tm.hold, 0.05), 0, 1)
    tm.paused, tm.frozen = true, frac
    if S.toast[f] then FuseStep(f) end
end

local function OnNewAlert(f)
    local kind = ToastKind(f)
    if not kind then return end
    local rec = S.toast[f]
    if not rec then rec = Step("toast", SkinToast, f, kind) and S.toast[f] or nil end
    if not rec then return end
    ArmFlash(f)
    ArmFuse(f)
end

local function HookAlerts()
    if S.done.alerts or type(hooksecurefunc) ~= "function" then return end
    if type(_G.AlertFrame_ShowNewAlert) ~= "function" then return end
    S.done.alerts = true
    hooksecurefunc("AlertFrame_ShowNewAlert", function(f) Step("toast", OnNewAlert, f) end)
    if type(_G.AlertFrame_PlayOutAnimation) == "function" then hooksecurefunc("AlertFrame_PlayOutAnimation", NoteOutAnimation) end
    if type(_G.AlertFrame_PauseOutAnimation) == "function" then hooksecurefunc("AlertFrame_PauseOutAnimation", NotePause) end
end

-------------------------------------------------------------------------------
-- Vehicle exit key
-------------------------------------------------------------------------------

local VEH = { C = 4, BAND = 3, GLYPH = 14 }

local function VehicleLayout(b)
    local v = S.vehicle[b]
    if not v then return end
    local W, H = Kit.SizePx(b)
    W, H = W or 38, H or 38
    local c = Theme.SnapCut(VEH.C)
    v.W, v.H = W, H
    -- a hazard band under the top edge and over the bottom edge, clear of the two cut corners
    Kit.Move(v.top, c + 3, VEH.BAND, W - c - 6, VEH.BAND)
    Kit.Move(v.bottom, 3, H - 2 * VEH.BAND, W - c - 6, VEH.BAND)
    v.top:SetTexCoord(0, (W - c - 6) / HAZARD_SHEET, 0, VEH.BAND / HAZARD_SHEET)
    v.bottom:SetTexCoord(0, (W - c - 6) / HAZARD_SHEET, 0, VEH.BAND / HAZARD_SHEET)
    v.gx, v.gy = math.floor((W - VEH.GLYPH) / 2), math.floor((H - VEH.GLYPH) / 2)
    Kit.Move(v.glyph, v.gx, v.gy, VEH.GLYPH, VEH.GLYPH)
end

local function VehiclePaint(b)
    local v = S.vehicle[b]
    if not v then return end
    local enabled = Kit.IsEnabled(b)
    local hover, pressed = v.state.hover, v.state.pressed
    local edge = (not enabled) and C.dim or (hover and C.cyan or C.pink)
    Kit.PaintPlate(v.plate, pressed and enabled and C.sel or C.ink, 1, edge, 1, 2)
    local ink = enabled and edge or C.dis
    v.glyph:SetVertexColor(ink[1], ink[2], ink[3], 1)
    local band = enabled and 0.55 or 0.25
    v.top:SetVertexColor(edge[1], edge[2], edge[3], band)
    v.bottom:SetVertexColor(edge[1], edge[2], edge[3], band)
    -- the glyph launches up and right while the key is held
    if v.gx then Kit.Move(v.glyph, v.gx + ((pressed and enabled) and 2 or 0), v.gy - ((pressed and enabled) and 2 or 0), VEH.GLYPH, VEH.GLYPH) end
end

local function SkinVehicleLeave(b)
    if type(b) ~= "table" or S.vehicle[b] then return end
    local v = {}
    S.vehicle[b] = v
    HeldArt.HoldButton(b)
    local w, h = Kit.SizePx(b)
    v.plate = Kit.Plate(b, VEH.C, w or 38, h or 38)
    v.top = Kit.Glyph(b, HAZARD, 0, 0, 8, VEH.BAND, C.pink, 0.55, "ARTWORK", 1)
    v.bottom = Kit.Glyph(b, HAZARD, 0, 0, 8, VEH.BAND, C.pink, 0.55, "ARTWORK", 1)
    v.glyph = Kit.Glyph(b, PROMPT, 0, 0, VEH.GLYPH, VEH.GLYPH, C.pink, 1, "OVERLAY", 2)
    v.state = Kit.Track(b, VehiclePaint)
    VehicleLayout(b)
    VehiclePaint(b)
end

local function BuildVehicle()
    local b = _G.MainMenuBarVehicleLeaveButton
    if type(b) == "table" then Step("vehicle", SkinVehicleLeave, b) end
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Relayout()
    for t in pairs(S.mirror) do MirrorLayout(t) end
    for f in pairs(S.toast) do LayoutToast(f) end
    for b in pairs(S.vehicle) do VehicleLayout(b); VehiclePaint(b) end
end

local function Repaint()
    for t in pairs(S.mirror) do
        local m = S.mirror[t]
        m.kind = nil
        MirrorSync(t)
    end
    for f in pairs(S.toast) do
        if S.timing[f] then ArmFuse(f) end
    end
end

local function Build()
    Step("alerts", HookAlerts)
    Step("mirror", BuildMirror)
    Step("vehicle", BuildVehicle)
    if not S.done.reseat then
        S.done.reseat = true
        Kit.OnReseat(Relayout)
        if FS.Config and FS.Config.OnChange then
            for _, s in pairs(SETTINGS) do FS.Config.OnChange(s.key, Repaint) end
        end
    end
end

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
