-- Forever STUwave: ControlKit
-- The shared pieces of the controls kit (mockups/shared-controls-2026-11-12.html): the pixel model, the cut plate,
-- the one animation clock, the state tracker for a stock widget, and the registry the PanelSkins sweep walks. The
-- skins themselves (Core/CheckSkins.lua and the files after it) own what each control looks like.
--
-- Skin only. A stock widget keeps its rect, its scripts and its attributes: our plate is a child frame inside it,
-- its Blizzard art is held at alpha 0 (FS.HeldArt) and we follow it by post-hooks (HookScript, hooksecurefunc),
-- never SetScript or SetAttribute, never a resize, a reparent or a Hide of a Blizzard frame. A widget met in
-- combat is queued and skinned when combat ends (PanelSkins.DeferCombat). A value the client hands back is read
-- through FS.IsSecret first.
--
-- Pixel model. Every number in the kit is a PHYSICAL pixel of the mockup (FS.Layout.Controls, Theme tokens for
-- colour): one mock px is one screen px, the convention of the Mail build (LAYOUT_SCALE = 1 in Modules/Skins/
-- Mail.lua). Kit.U turns it into UI units at the pixel scale of the frame being laid out
-- (FS.FrameHelpers.PixelsPerUnit), which keeps every edge on a whole screen pixel at any UI scale; Kit.Reseat
-- lays everything out again when the scale changes.
--
-- Motion. One hidden frame runs one OnUpdate for every animation of every visible control (Kit.Animate); an
-- animation exists only while its control needs it, so a screen of idle boxes costs nothing.

local _, FS = ...

local Theme = FS.Theme

local Kit = {}
FS.ControlKit = Kit

Kit.LAYOUT_SCALE = 1

local function Weak() return setmetatable({}, { __mode = "k" }) end

local placed, fonts = Weak(), Weak()

-------------------------------------------------------------------------------
-- Small safe readers
-------------------------------------------------------------------------------

function Kit.Plain(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    return v
end

function Kit.Try(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b, c, d = pcall(fn, ...)
    if ok then return a, b, c, d end
    return nil
end

function Kit.TypeOf(obj)
    if type(obj) ~= "table" or type(obj.GetObjectType) ~= "function" then return nil end
    local ok, kind = pcall(obj.GetObjectType, obj)
    return ok and kind or nil
end

function Kit.Later(fn)
    if _G.C_Timer and _G.C_Timer.After then _G.C_Timer.After(0, fn) else fn() end
end

function Kit.Now()
    if type(_G.GetTime) == "function" then
        local ok, t = pcall(_G.GetTime)
        if ok and type(t) == "number" then return t end
    end
    return 0
end

-------------------------------------------------------------------------------
-- Pixels
-------------------------------------------------------------------------------

-- Physical pixels per UI unit at `frame` (1 when the client will not say).
function Kit.Ppu(frame)
    local helpers = FS.FrameHelpers
    if helpers and helpers.PixelsPerUnit then
        local ok, ppu = pcall(helpers.PixelsPerUnit, frame)
        if ok and type(ppu) == "number" and ppu > 0 then return ppu end
    end
    return 1
end

-- Physical pixels of the mockup to UI units at the pixel scale of `frame`.
function Kit.U(frame, n)
    return n * Kit.LAYOUT_SCALE / Kit.Ppu(frame)
end

-- A frame's size in physical pixels (nil, nil before it has one).
function Kit.SizePx(frame)
    local w, h = Kit.Try(frame.GetWidth, frame), Kit.Try(frame.GetHeight, frame)
    w, h = Kit.Plain(w), Kit.Plain(h)
    if type(w) ~= "number" or type(h) ~= "number" or w <= 0 or h <= 0 then return nil, nil end
    local ppu = Kit.Ppu(frame)
    return math.floor(w * ppu + 0.5), math.floor(h * ppu + 0.5)
end

local function Apply(obj)
    local p = placed[obj]
    if not p then return end
    local ppu = Kit.Ppu(p.host)
    local k = Kit.LAYOUT_SCALE / ppu
    obj:ClearAllPoints()
    obj:SetPoint(p.point, p.ref, p.relPoint, p.x * k, -p.y * k)
    if p.w then obj:SetSize(p.w * k, p.h * k) end
end

-- Seats `obj` so its `point` is at (x, y) physical pixels from `relPoint` of `ref` (x to the right, y DOWN), and sizes it
-- to w x h when given. `host` is the frame whose pixel scale rules (default `ref`). Recorded, so a change of pixel scale
-- re-seats everything in one pass.
function Kit.Place(obj, ref, x, y, w, h, point, relPoint, host)
    placed[obj] = {
        ref = ref, x = x, y = y, w = w, h = h, point = point or "TOPLEFT", relPoint = relPoint or "TOPLEFT",
        host = host or ref,
    }
    Apply(obj)
    return obj
end

-- Re-seats one recorded object after its numbers changed (Kit.Move).
function Kit.Move(obj, x, y, w, h)
    local p = placed[obj]
    if not p then return end
    p.x, p.y = x, y
    if w then p.w, p.h = w, h end
    Apply(obj)
end

local reseaters = {}

-- Registers `fn` to run after every re-seat (a skin that centres a plate in a stock rect works out its offset again from
-- the new pixel size of that rect).
function Kit.OnReseat(fn)
    reseaters[#reseaters + 1] = fn
end

function Kit.Reseat()
    for obj in pairs(placed) do Apply(obj) end
    for fs, f in pairs(fonts) do Theme.ApplyMono(fs, f.px * Kit.LAYOUT_SCALE / Kit.Ppu(f.host), f.color) end
    for _, fn in ipairs(reseaters) do pcall(fn) end
end

function Kit.Snap(t)
    if t.SetSnapToPixelGrid then
        pcall(t.SetSnapToPixelGrid, t, true)
        if t.SetTexelSnappingBias then pcall(t.SetTexelSnappingBias, t, 0) end
    end
end

function Kit.Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

-- A solid rectangle at (x, y) physical pixels from the top left of `parent`, w x h.
function Kit.Rect(parent, x, y, w, h, color, alpha, layer, sub)
    local t = parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
    t:SetColorTexture(color[1], color[2], color[3], alpha or color[4] or 1)
    Kit.Snap(t)
    Kit.Place(t, parent, x, y, w, h)
    return t
end

-- One of the kit's baked glyph textures at (x, y) physical pixels from the top left of `parent`, w x h, white until tinted.
function Kit.Glyph(parent, path, x, y, w, h, color, alpha, layer, sub)
    local t = parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
    t:SetTexture(path)
    Kit.Snap(t)
    Kit.Place(t, parent, x, y, w, h)
    if color then t:SetVertexColor(color[1], color[2], color[3], alpha or color[4] or 1) end
    return t
end

-- A mono label whose size follows the pixel scale. `px` is the glyph size in physical pixels.
function Kit.Label(parent, text, px, color, layer)
    local fs = parent:CreateFontString(nil, layer or "OVERLAY")
    fonts[fs] = { px = px, color = color, host = parent }
    Theme.ApplyMono(fs, px * Kit.LAYOUT_SCALE / Kit.Ppu(parent), color)
    if fs.SetWordWrap then fs:SetWordWrap(false) end
    fs:SetText(text or "")
    return fs
end

-- Restyles a Blizzard label to the kit's mono at `px` physical pixels in `color`, and keeps its size on the pixel scale.
function Kit.RestyleLabel(fs, host, px, color)
    if type(fs) ~= "table" or type(fs.SetFont) ~= "function" then return end
    fonts[fs] = { px = px, color = color, host = host }
    Theme.ApplyMono(fs, px * Kit.LAYOUT_SCALE / Kit.Ppu(host), color)
end

function Kit.Recolor(fs, color, alpha)
    local f = fonts[fs]
    if f then f.color = color end
    if fs.SetTextColor then fs:SetTextColor(color[1], color[2], color[3], alpha or color[4] or 1) end
end

-------------------------------------------------------------------------------
-- Cut plate
-------------------------------------------------------------------------------

-- A two-corner cut plate drawn on `host` (a frame whose rect is the plate, w x h physical pixels): a nine-sliced fill and a
-- one pixel ring at chamfer `c` (snapped to the baked set), plus an optional inner ring one pixel in at c - 1, so a 2 px
-- edge is two rings whose diagonals sit side by side. Returns the plate; Plate.Paint recolours it.
function Kit.Plate(host, c, w, h)
    c = Theme.SnapCut(c)
    local plate = { host = host, c = c, w = w, h = h }
    plate.fill = Theme.AddCutSliceFill(host, Theme.COLOR_CTRL_INK, c)
    if not plate.fill then
        plate.fill = host:CreateTexture(nil, "BACKGROUND", nil, -6)
        plate.fill:SetAllPoints(host)
        plate.flat = true
    end
    local path = Theme.Cut2ButtonSet(c)
    plate.ring = Theme.AddSliceTexture(host, path, { 1, 1, 1, 1 }, "BORDER", 1)
    Theme.ApplyNineSlice(plate.ring, c)
    local inner = Theme.SnapCut(c - 1)
    if inner > 0 and inner < c then
        local innerPath = Theme.Cut2ButtonSet(inner)
        plate.ring2 = Theme.AddSliceTexture(host, innerPath, { 1, 1, 1, 1 }, "BORDER", 1)
        Theme.ApplyNineSlice(plate.ring2, inner)
        Kit.Place(plate.ring2, host, 1, 1, w - 2, h - 2)
        plate.ring2:Hide()
    end
    return plate
end

-- Paints a plate: the face colour (and alpha), the edge colour (and alpha) and the edge width in pixels (1 or 2).
function Kit.PaintPlate(plate, fill, fillAlpha, edge, edgeAlpha, edgePx)
    if fill then
        if plate.flat then plate.fill:SetColorTexture(fill[1], fill[2], fill[3], fillAlpha or 1)
        else plate.fill:SetVertexColor(fill[1], fill[2], fill[3], fillAlpha or 1) end
    end
    if edge then
        plate.ring:SetVertexColor(edge[1], edge[2], edge[3], edgeAlpha or 1)
        if plate.ring2 then
            if edgePx == 2 then
                plate.ring2:SetVertexColor(edge[1], edge[2], edge[3], edgeAlpha or 1)
                plate.ring2:Show()
            else
                plate.ring2:Hide()
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Motion
-------------------------------------------------------------------------------

local anims, byOwner = {}, Weak()
local ticker

local function Compact()
    local n = 0
    for i = 1, #anims do
        local a = anims[i]
        if not a.dead then
            n = n + 1
            anims[n] = a
        end
    end
    for i = #anims, n + 1, -1 do anims[i] = nil end
    if ticker and n == 0 then ticker:Hide() end
end

local function Tick(_, dt)
    local now = Kit.Now()
    local n = #anims
    local sweep = false
    for i = 1, n do
        local a = anims[i]
        if a and not a.dead then
            local visible = true
            if type(a.owner.IsVisible) == "function" then visible = a.owner:IsVisible() end
            if visible then
                if a.start == nil then a.start = now end
                local ok = pcall(a.fn, dt, now - a.start, a)
                if not ok then a.dead = true; sweep = true end
            end
        elseif a then
            sweep = true
        end
    end
    if sweep then Compact() end
end

-- Runs `fn(dt, elapsed, anim)` every frame while `owner` is visible, replacing any animation `owner` already has under
-- `key`. `elapsed` is seconds since the first frame it ran. `fn` ends itself with Kit.StopAnimate(owner, key); an `fn` that
-- throws is stopped.
function Kit.Animate(owner, key, fn)
    Kit.StopAnimate(owner, key)
    local a = { owner = owner, key = key, fn = fn }
    anims[#anims + 1] = a
    byOwner[owner] = byOwner[owner] or {}
    byOwner[owner][key] = a
    if not ticker then
        ticker = CreateFrame("Frame")
        ticker:SetScript("OnUpdate", Tick)
    end
    ticker:Show()
    return a
end

function Kit.StopAnimate(owner, key)
    local list = byOwner[owner]
    local a = list and list[key]
    if a then
        a.dead = true
        list[key] = nil
    end
end

function Kit.IsAnimating(owner, key)
    local list = byOwner[owner]
    return list ~= nil and list[key] ~= nil
end

-- Number of running animations, for the harness.
function Kit.AnimationCount()
    local n = 0
    for _, a in ipairs(anims) do
        if not a.dead then n = n + 1 end
    end
    return n
end

-- Easing, in the CSS vocabulary of the mockup: p in 0..1 to 0..1.
Kit.Ease = {
    outQuad = function(p) return 1 - (1 - p) * (1 - p) end,
    inOutSine = function(p) return 0.5 - 0.5 * math.cos(math.pi * p) end,
}

-- The breathing LED: 1 down to `floor` at the half period and back (the mockup's `pulse`, ease in out).
function Kit.Pulse(elapsed, period, floor)
    local p = (elapsed % period) / period
    local down = p < 0.5 and p * 2 or (1 - p) * 2
    return 1 - (1 - floor) * Kit.Ease.inOutSine(down)
end

-------------------------------------------------------------------------------
-- Deferral, hooks and widget state
-------------------------------------------------------------------------------

local queued, queuedFlush = {}, false

-- Runs `fn` now, or after combat ends when the player is in combat (PanelSkins.DeferCombat, one wait for any number of
-- widgets).
function Kit.Defer(fn)
    if not (type(InCombatLockdown) == "function" and InCombatLockdown()) then return fn() end
    queued[#queued + 1] = fn
    if queuedFlush then return end
    queuedFlush = true
    local panelSkins = FS.PanelSkins
    local function flush()
        queuedFlush = false
        local list = queued
        queued = {}
        for _, f in ipairs(list) do pcall(f) end
    end
    if panelSkins and panelSkins.DeferCombat then panelSkins.DeferCombat(flush) else flush() end
end

local failed = {}

-- Reports a skin that threw, once per `label` (FS.LogDegradeOnce prints every call, so the dedupe is ours): the widget keeps
-- whatever was drawn before the failure and the stock look is never hidden by a half built skin.
function Kit.Fail(label, err)
    if failed[label] then return end
    failed[label] = true
    local log = FS.LogDegradeOnce
    if log then pcall(log, "controlkit:" .. label, ("Forever STUwave: the %s skin failed: %s"):format(label, tostring(err))) end
end

function Kit.HookScript(obj, script, fn)
    if type(obj) == "table" and type(obj.HookScript) == "function" then pcall(obj.HookScript, obj, script, fn) end
end

function Kit.HookFunc(obj, method, fn)
    if type(obj) == "table" and type(obj[method]) == "function" and type(hooksecurefunc) == "function" then
        pcall(hooksecurefunc, obj, method, fn)
    end
end

-- Follows a stock widget's state for `repaint(widget)`: hover, pressed, enabled, shown. Returns the state table
-- { hover, pressed } that repaint reads. Post-hooks only.
function Kit.Track(widget, repaint)
    local state = { hover = false, pressed = false }
    local function again() repaint(widget) end
    Kit.HookScript(widget, "OnEnter", function() state.hover = true; again() end)
    Kit.HookScript(widget, "OnLeave", function() state.hover, state.pressed = false, false; again() end)
    Kit.HookScript(widget, "OnMouseDown", function() state.pressed = true; again() end)
    Kit.HookScript(widget, "OnMouseUp", function() state.pressed = false; again() end)
    Kit.HookScript(widget, "OnShow", function() state.hover, state.pressed = false, false; again() end)
    Kit.HookScript(widget, "OnEnable", again)
    Kit.HookScript(widget, "OnDisable", again)
    for _, method in ipairs({ "Enable", "Disable", "SetEnabled" }) do Kit.HookFunc(widget, method, again) end
    return state
end

-- Enabled as the stock widget reports it (true when it will not say).
function Kit.IsEnabled(widget)
    if type(widget.IsEnabled) ~= "function" then return true end
    local ok, v = pcall(widget.IsEnabled, widget)
    if not ok then return true end
    v = Kit.Plain(v)
    if v == nil then return true end
    return v and true or false
end

-------------------------------------------------------------------------------
-- Registry: what the PanelSkins sweep asks about a widget
-------------------------------------------------------------------------------

local specs = {}

-- Registers a control skin: `match(widget)` tells by object type and template traits (never by name), `skin(widget)`
-- skins it (idempotent), `parts(widget)` returns what it drew on it, or nil when it has not been skinned. `into` is
-- true for a skin that owns its whole subtree (the sweep does not walk into the widget).
function Kit.Register(name, spec)
    spec.name = name
    for i, existing in ipairs(specs) do
        if existing.name == name then specs[i] = spec return spec end
    end
    specs[#specs + 1] = spec
    return spec
end

function Kit.Classify(widget)
    for _, spec in ipairs(specs) do
        local ok, hit = pcall(spec.match, widget)
        if ok and hit then return spec end
    end
    return nil
end

-- Skins `widget` with the first skin that claims it. Returns the spec and whether it skinned now.
function Kit.SkinWidget(widget)
    local spec = Kit.Classify(widget)
    if not spec then return nil, false end
    if spec.parts(widget) then return spec, false end
    spec.skin(widget)
    return spec, spec.parts(widget) ~= nil
end

-- Re-lays out on a change of pixel scale.
local watcher = CreateFrame("Frame")
for _, event in ipairs({ "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED" }) do pcall(watcher.RegisterEvent, watcher, event) end
watcher:SetScript("OnEvent", function() Kit.Reseat() end)
