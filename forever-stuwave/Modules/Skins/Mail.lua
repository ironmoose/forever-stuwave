-- Forever STUwave: Mail
-- The mailbox as three STUwave windows, from the approved MAIL v2 mockup: the INBOX (a header band with an
-- inbox / send switch and a close key, one letter card per MailItem row, pager chevrons, an "open all" key),
-- the OPEN LETTER panel docked beside it (OpenMailFrame), and the SEND form (prompt-style To and Subject, a
-- postage chip, the message pad, the cargo strip, segmented money inputs, a send / C.O.D. switch, cancel and
-- send keys).
--
-- Skin only. Blizzard's own widgets stay the click targets and keep every script: a row's item button is
-- stretched over its whole card, the attachment buttons become the wells, the money boxes sit over the
-- segments, the stock text buttons are the keys. Their art is held at alpha 0 (FS.HeldArt) and our own
-- textures and labels draw over them. Nothing here writes a script handler or an attribute on a Blizzard
-- widget, and every text we replace is read from the same API the stock code reads (GetInboxHeaderInfo,
-- GetSendMailPrice) rather than from the stock widgets. Mail is never open in combat; the layout writes
-- (sizes and anchors of non-protected frames) are skipped in combat anyway.
--
-- Pixel model. The mockup section is drawn 1:1 against the in-game capture (a 440 x 600 mock window beside a
-- 444 x 603 capture, 44 px wells equal to the stock 37 unit slot at 1.2 px per unit), so every number below is a
-- PHYSICAL pixel at the player's screen; U() turns it into UI units at the pixel scale of the frame being laid
-- out (FS.FrameHelpers.PixelsPerUnit), which keeps every edge on a whole screen pixel at any UI scale.
-- LAYOUT_SCALE is the one number to change if the mockup is ever read at another scale.
--
-- Frame names: the 16001 globals dump (reference/wow-api-dump-16001/globals.txt) for every global named here;
-- the retail 12.1.0 Blizzard_MailFrame source for the structure behind them (Name on OpenMailSender, the
-- attachment Count, MailItemNButton.index). The inbox pager buttons are anonymous on 16001 (InboxMixin,
-- InboxPrevPageMixin and InboxNextPageMixin exist, InboxPrevPageButton does not), so they are found by shape.

local _, FS = ...

local Theme, HeldArt, PanelSkins = FS.Theme, FS.HeldArt, FS.PanelSkins
if not (Theme and HeldArt and PanelSkins and PanelSkins.RequireExport(
    Theme.AddPanelChrome and Theme.AddCutSliceFill and Theme.AddSliceTexture and Theme.ApplyMono and Theme.SnapCut,
    "Mail.lua disabled: FS.Theme chrome helpers or FS.HeldArt missing")) then return end

local Mail = {}
FS.MailSkin = Mail

local LAYOUT_SCALE = 1

-- Palette: the Theme tokens plus the mockup's mail-only inks.
local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    gold = Theme.COLOR_GOLD, muted = Theme.COLOR_MUTED, line = Theme.COLOR_BAR_BORDER,
    silver = { 0.784, 0.816, 0.863 }, copper = { 0.878, 0.565, 0.353 },          -- #c8d0dc, #e0905a
    ink = { 0.027, 0.012, 0.055 }, panel = { 0.071, 0.039, 0.133, 0.96 },         -- #07030e, #120a22
    head = { 0.102, 0.051, 0.173 }, sel = { 0.110, 0.063, 0.188 },                -- #1a0d2c, #1c1030
    pinkFill = { 0.165, 0.059, 0.180 }, cyanFill = { 0.051, 0.165, 0.200 },      -- #2a0f2e, #0d2a33
    well = { 0.039, 0.024, 0.078 }, wellLine = { 0.165, 0.094, 0.275 },           -- #0a0614, #2a1846
    ledOff = { 0.227, 0.165, 0.353 }, read = { 0.784, 0.753, 0.878 },            -- #3a2a5a, #c8c0e0
    white = { 1, 1, 1 }, text = { 0.914, 0.886, 1 }, hint = { 0.361, 0.329, 0.502 },
}

-- Every number here is a physical pixel of the mockup. Window-relative y runs down from the window's top edge.
local G = {
    WIN_W = 432, HEAD_H = 48, SIDE = 14,
    ROW_Y = 62, ROW_H = 68, ROW_GAP = 10, ROW_X = 14, ROW_W = 404,
    FOOT_BOTTOM = 16, FOOT_RULE_UP = 58, PAGER_Y_UP = 46, PAGER_H = 30,
    LETTER_GAP = 22, LETTER_DROP = 48, LETTER_W = 440,
}
Mail.GEOM = G

local S = {
    ppu = 1, fonts = setmetatable({}, { __mode = "k" }), placed = setmetatable({}, { __mode = "k" }),
    keys = setmetatable({}, { __mode = "k" }), quiet = setmetatable({}, { __mode = "k" }),
    quietTexts = setmetatable({}, { __mode = "k" }),
    zeroing = setmetatable({}, { __mode = "k" }), done = {}, rows = {}, wells = {}, mailIndex = nil,
}
Mail.state = S

local ROWS = 7 -- INBOXITEMS_TO_DISPLAY, read again at build time

-------------------------------------------------------------------------------
-- Pixels
-------------------------------------------------------------------------------

local function Ppu(frame)
    local helpers = FS.FrameHelpers
    local ok, ppu = false, nil
    if helpers and helpers.PixelsPerUnit then ok, ppu = pcall(helpers.PixelsPerUnit, frame) end
    if ok and type(ppu) == "number" and ppu > 0 then return ppu end
    return 1
end

-- Physical pixels of the mockup to UI units at the pixel scale of the window being laid out.
local function U(n) return n * LAYOUT_SCALE / S.ppu end

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

local function Plain(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    return v
end

local function Try(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b, c = pcall(fn, ...)
    if ok then return a, b, c end
    return nil
end

local function Later(fn)
    if _G.C_Timer and _G.C_Timer.After then _G.C_Timer.After(0, fn) else fn() end
end

-- Seats `obj` so its `point` is at (x, y) physical pixels from the TOP LEFT of `ref`, y running down, and
-- sizes it to w x h when given. Recorded so a change of pixel scale re-seats everything in one pass.
local function Apply(obj)
    local p = S.placed[obj]
    obj:ClearAllPoints()
    obj:SetPoint(p.point, p.ref, p.relPoint, U(p.x), -U(p.y))
    if p.w then obj:SetSize(U(p.w), U(p.h)) end
end

local function Place(obj, ref, x, y, w, h, point, relPoint)
    S.placed[obj] = { ref = ref, x = x, y = y, w = w, h = h, point = point or "TOPLEFT", relPoint = relPoint or "TOPLEFT" }
    Apply(obj)
    return obj
end

local function Reseat()
    for obj in pairs(S.placed) do Apply(obj) end
    for fs, f in pairs(S.fonts) do Theme.ApplyMono(fs, U(f.px), f.color) end
end

local function Snap(t)
    if t.SetSnapToPixelGrid then
        pcall(t.SetSnapToPixelGrid, t, true)
        if t.SetTexelSnappingBias then pcall(t.SetTexelSnappingBias, t, 0) end
    end
end

local function Rect(parent, x, y, w, h, color, alpha, layer, sub)
    local t = parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
    t:SetColorTexture(color[1], color[2], color[3], alpha or color[4] or 1)
    Snap(t)
    Place(t, parent, x, y, w, h)
    return t
end

local function Label(parent, text, px, color, layer)
    local fs = parent:CreateFontString(nil, layer or "OVERLAY")
    S.fonts[fs] = { px = px, color = color }
    Theme.ApplyMono(fs, U(px), color)
    if fs.SetWordWrap then fs:SetWordWrap(false) end
    fs:SetText(text or "")
    return fs
end

-- A label whose `point` sits at (x, y) from the top left of `ref`: LEFT for a left-aligned line, RIGHT for a
-- right-aligned one, CENTER for a centred one. The point is the middle of the line, so y is the line's centre.
local function Line(parent, ref, point, x, y, text, px, color)
    local fs = Label(parent, text, px, color)
    if fs.SetJustifyH then fs:SetJustifyH(point) end
    Place(fs, ref, x, y, nil, nil, point, "TOPLEFT")
    return fs
end

local function Tint(list, color, alpha)
    for _, t in ipairs(list) do t:SetColorTexture(color[1], color[2], color[3], alpha or 1) end
end

-- Alpha-0 hold for a Blizzard FontString or frame we replace: survives Show, Hide and SetText, and a stray
-- SetAlpha puts it back to 0 (the HeldArt recipe, for objects that are not textures).
local function Quiet(obj)
    if type(obj) ~= "table" or type(obj.SetAlpha) ~= "function" then return end
    pcall(obj.SetAlpha, obj, 0)
    if S.quiet[obj] or type(hooksecurefunc) ~= "function" then return end
    if pcall(hooksecurefunc, obj, "SetAlpha", function(self, a)
        if a ~= 0 and not S.zeroing[self] then
            S.zeroing[self] = true
            pcall(self.SetAlpha, self, 0)
            S.zeroing[self] = nil
        end
    end) then S.quiet[obj] = true end
end

local function HookScript(obj, script, fn)
    if type(obj) == "table" and type(obj.HookScript) == "function" then pcall(obj.HookScript, obj, script, fn) end
end

local function HookFunc(obj, method, fn)
    if type(obj) == "table" and type(obj[method]) == "function" and type(hooksecurefunc) == "function" then
        pcall(hooksecurefunc, obj, method, fn)
    end
end

-- Holds every Blizzard caption on a button at alpha 0: its button FontString and any FontString region the
-- template draws on its own (the pager's Prev / Next, the expiry button's days, OpenAllMailText), which
-- GetFontString does not return. Our own labels (S.fonts) are skipped. SetText re-runs it, because a button's
-- FontString can be created by its first SetText, after the skin was built.
local function QuietTexts(button)
    if type(button) ~= "table" then return end
    local function sweep()
        if type(button.GetFontString) == "function" then
            local fs = button:GetFontString()
            if fs and not S.fonts[fs] then Quiet(fs) end
        end
        if type(button.GetRegions) == "function" then
            for _, region in ipairs({ button:GetRegions() }) do
                if type(region) == "table" and type(region.GetObjectType) == "function"
                    and region:GetObjectType() == "FontString" and not S.fonts[region] then
                    Quiet(region)
                end
            end
        end
    end
    sweep()
    if not S.quietTexts[button] then
        S.quietTexts[button] = true
        HookFunc(button, "SetText", sweep)
        HookFunc(button, "SetFormattedText", sweep)
        -- 16001 builds some buttons from a mixin (OpenMailReportSpamMixin) that can set its caption up outside
        -- SetText, so every visible state change sweeps again; the named ButtonText global is held directly too.
        local name = Try(button.GetName, button)
        if type(name) == "string" then Quiet(_G[name .. "Text"]) end
        for _, script in ipairs({ "OnShow", "OnEnable", "OnDisable", "OnEnter" }) do HookScript(button, script, sweep) end
    end
end

-- Holds every texture region of `button` except those in `keep` (the item icon of a well).
local function HoldRegions(button, keep)
    if type(button.GetRegions) ~= "function" then return end
    for _, region in ipairs({ button:GetRegions() }) do
        if not (keep and keep[region]) then HeldArt.Hold(region) end
    end
end

local function Above(frame, ref)
    if frame.SetFrameLevel and ref and ref.GetFrameLevel then pcall(frame.SetFrameLevel, frame, ref:GetFrameLevel() + 1) end
end

-------------------------------------------------------------------------------
-- Cut plates, keys, chips, wells
-------------------------------------------------------------------------------

-- A two-corner cut plate on `frame`: an optional nine-sliced fill and a one pixel ring, chamfer snapped to the
-- baked set. Returns { fill, ring, flat }.
local function Shape(frame, c, fill, ring, ringAlpha)
    c = Theme.SnapCut(c)
    local sh = { c = c }
    if fill then
        sh.fill = Theme.AddCutSliceFill(frame, fill, c)
        if not sh.fill then
            sh.fill = frame:CreateTexture(nil, "BACKGROUND", nil, -6)
            sh.fill:SetAllPoints(frame)
            sh.fill:SetColorTexture(fill[1], fill[2], fill[3], fill[4] or 1)
            sh.flat = true
        end
    end
    if ring then
        local path = Theme.Cut2ButtonSet(c)
        sh.ring = Theme.AddSliceTexture(frame, path, { ring[1], ring[2], ring[3], ringAlpha or 1 }, "BORDER", 1)
        Theme.ApplyNineSlice(sh.ring, c)
    end
    return sh
end

local function PaintShape(sh, fill, fillAlpha, ring, ringAlpha)
    if sh.fill and fill then
        if sh.flat then sh.fill:SetColorTexture(fill[1], fill[2], fill[3], fillAlpha or 1)
        else sh.fill:SetVertexColor(fill[1], fill[2], fill[3], fillAlpha or 1) end
    end
    if sh.ring and ring then sh.ring:SetVertexColor(ring[1], ring[2], ring[3], ringAlpha or 1) end
end

-- The state vocabulary of the other STUwave buttons: hover washes the face 16% toward the accent and takes the
-- ring to full, pressed washes 32%, disabled is the whole piece at 0.4.
local STATES = {
    normal = { ring = 0.85, wash = 0, lift = 0, al = 1 },
    hover = { ring = 1, wash = 0.16, lift = 0.12, al = 1 },
    pressed = { ring = 1, wash = 0.32, lift = 0.40, al = 1 },
    disabled = { ring = 0.85, wash = 0, lift = 0, al = 0.4 },
}

local function PaintKey(button)
    local k = S.keys[button]
    if not k then return end
    local name = "normal"
    if type(button.IsEnabled) == "function" and not button:IsEnabled() then name = "disabled"
    elseif k.pressed then name = "pressed"
    elseif k.hover then name = "hover" end
    local st = STATES[name]
    local face = Mix(k.fill, k.accent, st.wash)
    PaintShape(k.shape, face, (k.fill[4] or 1) * st.al, k.accent, st.ring * st.al)
    local ink = Mix(k.accent, C.white, st.lift)
    if k.label then k.label:SetTextColor(ink[1], ink[2], ink[3], st.al) end
    if k.glyph then Tint(k.glyph, ink, st.al) end
end

local function SetKeyAccent(button, accent)
    local k = S.keys[button]
    if k and k.accent ~= accent then k.accent = accent; PaintKey(button) end
end

-- Draws `button` as a key: its Blizzard art held, a cut plate and ring of the mockup, a lowercase label that
-- mirrors the stock text (the stock font string is held at alpha 0, never written), the state vocabulary.
-- o: accent, fill, c (chamfer), px (label size), text (fixed label for a proxy), glyph (builder), hold (false),
-- shorten (a lowercase stock text that is drawn as another word: the mockup's "open all" for "open all mail").
local function Key(button, o)
    if S.keys[button] then return S.keys[button] end
    local k = { accent = o.accent, fill = o.fill or C.ink }
    S.keys[button] = k
    if o.hold ~= false then
        HeldArt.HoldButton(button)
        QuietTexts(button)
    end
    k.shape = Shape(button, o.c or 4, k.fill, k.accent, STATES.normal.ring)
    if o.px or o.text then
        k.label = Label(button, o.text or "", o.px or 14, k.accent)
        k.label:SetPoint("CENTER", button, "CENTER", 0, 0)
        if not o.text then
            local function mirror()
                local text = Plain(Try(button.GetText, button))
                if type(text) == "string" then
                    text = text:lower()
                    k.label:SetText(o.shorten and o.shorten[text] or text)
                end
            end
            mirror()
            HookFunc(button, "SetText", mirror)
            HookScript(button, "OnShow", mirror)
        end
    end
    if o.glyph then k.glyph = o.glyph(button) end
    HookScript(button, "OnEnter", function() k.hover = true; PaintKey(button) end)
    HookScript(button, "OnLeave", function() k.hover, k.pressed = false, false; PaintKey(button) end)
    HookScript(button, "OnMouseDown", function() k.pressed = true; PaintKey(button) end)
    HookScript(button, "OnMouseUp", function() k.pressed = false; PaintKey(button) end)
    HookScript(button, "OnHide", function() k.hover, k.pressed = false, false end)
    HookScript(button, "OnShow", function() PaintKey(button) end)
    HookScript(button, "OnEnable", function() PaintKey(button) end)
    HookScript(button, "OnDisable", function() PaintKey(button) end)
    PaintKey(button)
    return k
end

-- A new plain frame at a pixel rect of `ref`.
local function Box(parent, ref, x, y, w, h, kind)
    local f = CreateFrame(kind or "Frame", nil, parent)
    Place(f, ref, x, y, w, h)
    return f
end

-- Glyphs, built from one pixel runs so every edge is on the pixel grid. Each builder returns the run list.
local function Runs(parent, list, color)
    local out = {}
    for _, r in ipairs(list) do out[#out + 1] = Rect(parent, r[1], r[2], r[3], r[4], color, 1, "OVERLAY", 3) end
    return out
end

local function AddRuns(a, b) for _, t in ipairs(b) do a[#a + 1] = t end return a end

-- A chevron, 8 wide and 14 tall, two pixels thick; dir "<" or ">".
local function ChevronCells(x, y, dir)
    local cells = {}
    for r = 0, 13 do
        local d = r < 7 and r or 13 - r
        cells[#cells + 1] = { x + (dir == ">" and d or 6 - d), y + r, 2, 1 }
    end
    return cells
end

-- An X, n x n, two pixels thick.
local function XCells(x, y, n)
    local cells = {}
    for r = 0, n - 1 do
        cells[#cells + 1] = { x + r, y + r, 2, 1 }
        cells[#cells + 1] = { x + n - 2 - r, y + r, 2, 1 }
    end
    return cells
end

-- A right pointing triangle, 7 wide and 14 tall.
local function TriangleCells(x, y)
    local cells = {}
    for col = 0, 6 do cells[#cells + 1] = { x + col, y + col, 1, 14 - 2 * col } end
    return cells
end

-- An envelope outline, w x h, with its flap.
local function EnvelopeCells(x, y, w, h)
    local cells = {
        { x, y, w, 1 }, { x, y + h - 1, w, 1 }, { x, y, 1, h }, { x + w - 1, y, 1, h },
    }
    local mid, depth = w / 2, math.floor(h / 2)
    for r = 1, depth do
        local d = math.floor(mid * r / depth + 0.5)
        cells[#cells + 1] = { x + d - 1, y + r, 2, 1 }
        cells[#cells + 1] = { x + w - d - 1, y + r, 2, 1 }
    end
    return cells
end

-- A segment in a two way switch: the plate holds both segments, the active one wears the pink plate.
local function Switch(parent, ref, x, y, w, h, o)
    local plate = Box(parent, ref, x, y, w, h)
    local sw = { plate = plate, segs = {}, shape = Shape(plate, 6, C.ink, C.violet, 0.6) }
    local segW = (w - 6 - o.gap) / 2
    for i = 1, 2 do
        local b = o.buttons and o.buttons[i] or CreateFrame("Button", nil, plate)
        if o.buttons and o.buttons[i] then HeldArt.HoldButton(b) end
        Above(b, plate)
        Place(b, plate, 3 + (i - 1) * (segW + o.gap), 3, segW, h - 6)
        local seg = { button = b, shape = Shape(b, 4, C.pinkFill, C.pink, 1) }
        seg.label = Label(b, o.labels[i], o.px, C.muted)
        seg.label:SetPoint("CENTER", b, "CENTER", 0, 0)
        sw.segs[i] = seg
        HookScript(b, "OnEnter", function() seg.hover = true; if sw.paint then sw.paint() end end)
        HookScript(b, "OnLeave", function() seg.hover = false; if sw.paint then sw.paint() end end)
    end
    function sw.paint()
        for i, seg in ipairs(sw.segs) do
            local on = sw.active == i
            PaintShape(seg.shape, C.pinkFill, on and 1 or 0, C.pink, on and 1 or (seg.hover and 0.5 or 0))
            local ink = on and C.pink or (seg.hover and C.white or C.muted)
            local enabled = type(seg.button.IsEnabled) ~= "function" or seg.button:IsEnabled()
            seg.label:SetTextColor(ink[1], ink[2], ink[3], enabled and 1 or 0.4)
        end
    end
    function sw.set(i) sw.active = i; sw.paint() end
    sw.paint()
    return sw
end

-- A chip: a ring and a label, sized to its text (7 px each side).
local function NewChip(parent)
    local chip = CreateFrame("Frame", nil, parent)
    chip.fsShape = Shape(chip, 4, nil, C.cyan, 0.7)
    chip.fsLabel = Label(chip, "", 13, C.cyan)
    chip.fsLabel:SetPoint("CENTER", chip, "CENTER", 0, 0)
    return chip
end

local function FillChip(chip, text, color)
    chip.fsLabel:SetText(text)
    Theme.ApplyMono(chip.fsLabel, U(13), color)
    S.fonts[chip.fsLabel].color = color
    PaintShape(chip.fsShape, nil, nil, color, 0.7)
    local width = Try(chip.fsLabel.GetStringWidth, chip.fsLabel)
    local px = type(width) == "number" and math.ceil(width * S.ppu / LAYOUT_SCALE) or #text * 8
    return px + 14
end

local function FormatMoney(copper)
    copper = math.floor(tonumber(copper) or 0)
    local g, s, c = math.floor(copper / 10000), math.floor(copper % 10000 / 100), copper % 100
    local parts = {}
    if g > 0 then parts[#parts + 1] = g .. "g" end
    if s > 0 then parts[#parts + 1] = s .. "s" end
    if c > 0 or #parts == 0 then parts[#parts + 1] = c .. "c" end
    return table.concat(parts, " ")
end

local function Hex(c) return ("|cff%02x%02x%02x"):format(c[1] * 255 + 0.5, c[2] * 255 + 0.5, c[3] * 255 + 0.5) end

local function MoneyText(copper)
    copper = math.floor(tonumber(copper) or 0)
    local g, s, c = math.floor(copper / 10000), math.floor(copper % 10000 / 100), copper % 100
    return Hex(C.gold) .. g .. "g|r " .. Hex(C.silver) .. s .. "s|r " .. Hex(C.copper) .. c .. "c|r"
end

-- A well: the stock slot button as a 44 px cut well. The item icon is 30 px inset 7 on every side; an empty
-- well is dark. `icon` is the region that carries the item picture and stays visible; `chip` is the money
-- chip (a gold ring, no fill, no icon).
local function SkinWell(button, icon, count, chip)
    if S.wells[button] then return S.wells[button] end
    HoldRegions(button, icon and { [icon] = true } or nil)
    local w = { icon = icon, chip = chip }
    S.wells[button] = w
    if chip then
        w.shape = Shape(button, 6, nil, C.gold, 0.6)
    else
        w.shape = Shape(button, 4, C.sel, C.cyan, 0.8)
    end
    if icon then
        Place(icon, button, 7, 7, 30, 30)
        icon:SetDrawLayer("ARTWORK", 1)
    end
    if count then
        if chip then
            Quiet(count)
        else
            Theme.ApplyMono(count, U(13), C.white)
            S.fonts[count] = { px = 13, color = C.white }
            count:ClearAllPoints()
            count:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -U(4), U(4))
            count:SetDrawLayer("OVERLAY", 4)
        end
    end
    return w
end

local function PaintWell(button, filled)
    local w = S.wells[button]
    if not w or w.chip then return end
    if filled then PaintShape(w.shape, C.sel, 1, C.cyan, 0.8)
    else PaintShape(w.shape, C.well, 1, C.wellLine, 1) end
end

-------------------------------------------------------------------------------
-- Window chrome and header
-------------------------------------------------------------------------------

local function InCombat() return type(InCombatLockdown) == "function" and InCombatLockdown() end

-- Gives a Blizzard window the panel chrome: its art stripped, the fill, glow and ring in `accent`.
local function Chrome(win, accent)
    Theme.StripBlizzardChrome(win)
    Theme.AddPanelChrome(win, { fillColor = C.panel, accent = accent, glowAlpha = 0.30 })
end

local function TabButton(which)
    local names = which == 1 and { "MailFrameTab1", "MailFrameLeftTabButton" } or { "MailFrameTab2", "MailFrameRightTabButton" }
    for _, name in ipairs(names) do
        local b = _G[name]
        if b and type(b.Click) == "function" then return b end
    end
end

local function SendShown()
    return _G.SendMailFrame and Try(_G.SendMailFrame.IsShown, _G.SendMailFrame) == true
end

local function UnreadCount()
    if type(GetInboxNumItems) ~= "function" then return nil end
    local n = Plain(Try(GetInboxNumItems))
    if type(n) ~= "number" then return nil end
    local unread = 0
    for i = 1, n do
        local info = { pcall(GetInboxHeaderInfo, i) }
        if info[1] and not info[10] then unread = unread + 1 end
    end
    return unread
end

local function RefreshHeader()
    local h = S.header
    if not h then return end
    h.switch.set(SendShown() and 2 or 1)
    local unread = UnreadCount()
    h.switch.segs[1].label:SetText(unread and unread > 0 and ("inbox " .. unread) or "inbox")
end

local function BuildHeader(win)
    local W, H = G.WIN_W, G.HEAD_H
    -- The band is flush against the ring; its top left stops short of the 6 px chamfer.
    local tl = Rect(win, 7, 1, W - 8, 5, C.head, 1, "ARTWORK", 0)
    local band = Rect(win, 1, 6, W - 2, H - 6, C.head, 1, "ARTWORK", 0)
    local rule = Rect(win, 1, H, W - 2, 1, C.violet, 1, "ARTWORK", 1)
    local env = Runs(win, EnvelopeCells(18, 16, 22, 16), C.cyan)
    local title = Line(win, win, "LEFT", 52, H / 2, "stuwave://mail", 16, C.muted)

    local sw = Switch(win, win, 206, 10, 170, 28, { gap = 4, px = 14, labels = { "inbox", "send" } })
    for i = 1, 2 do
        local b = sw.segs[i].button
        b:SetScript("OnClick", function()
            local tab = TabButton(i)
            if tab then pcall(tab.Click, tab) end
        end)
    end

    local close = _G.MailFrameCloseButton
    if close then
        Key(close, { accent = C.pink, c = 4, glyph = function(b) return Runs(b, XCells(7, 7, 14), C.pink) end })
        Above(close, win)
        Place(close, win, 386, 10, 28, 28)
    end

    S.header = { switch = sw, close = close, band = { tl, band, rule }, env = env, title = title }

    -- The stock tabs hang under the window and the switch replaces them; they stay clickable by script (the
    -- switch drives their own Click), just never drawn or hit.
    for i = 1, 2 do
        local tab = TabButton(i)
        if tab then
            Quiet(tab)
            if tab.EnableMouse then pcall(tab.EnableMouse, tab, false) end
        end
    end
    Quiet(_G.MailFrameTitleText)

    if type(_G.MailFrameTab_OnClick) == "function" then HookFunc(_G, "MailFrameTab_OnClick", RefreshHeader) end
    for _, name in ipairs({ "InboxFrame", "SendMailFrame" }) do
        HookScript(_G[name], "OnShow", RefreshHeader)
        HookScript(_G[name], "OnHide", RefreshHeader)
    end
    RefreshHeader()
end

-------------------------------------------------------------------------------
-- Inbox
-------------------------------------------------------------------------------

local function RowIndex(i, button)
    local idx = button.index
    if type(idx) ~= "number" and button.GetID then idx = Try(button.GetID, button) end
    if type(idx) ~= "number" or idx <= 0 then
        local page = (_G.InboxFrame and _G.InboxFrame.pageNum) or 1
        idx = (page - 1) * ROWS + i
    end
    return idx
end

local function Age(days)
    if type(days) ~= "number" then return "" end
    if days >= 1 then return math.floor(days) .. "d" end
    local hours = math.floor(days * 24)
    if hours >= 1 then return hours .. "h" end
    return math.max(1, math.floor(days * 1440)) .. "m"
end

-- The cyan bracket from the selected card to the open letter: a line across the gap and a square at its end.
local function SeatBracket()
    local b = S.bracket
    if not b then return end
    local row = S.selected and S.rows[S.selected]
    local show = row and row.card:IsShown() and _G.OpenMailFrame and _G.OpenMailFrame:IsShown()
    b.line:SetShown(show and true or false)
    b.knob:SetShown(show and true or false)
    if not show then return end
    -- the line runs from the card's right edge across the window's 14 px margin and the 22 px gap to the open
    -- letter, and the square ends flush with the letter's left edge
    local span = (G.WIN_W - G.ROW_X - G.ROW_W) + G.LETTER_GAP
    S.placed[b.line] = { ref = row.card, x = G.ROW_W, y = G.ROW_H / 2 - 1, w = span - 4, h = 2, point = "TOPLEFT", relPoint = "TOPLEFT" }
    Apply(b.line)
    S.placed[b.knob] = { ref = row.card, x = G.ROW_W + span - 10, y = G.ROW_H / 2 - 5, w = 10, h = 10, point = "TOPLEFT", relPoint = "TOPLEFT" }
    Apply(b.knob)
end

local function RefreshRow(i)
    local r = S.rows[i]
    if not r then return end
    local button = r.button
    local shown = Try(button.IsShown, button) == true
    r.card:SetShown(shown)
    if not shown then
        if S.selected == i then S.selected = nil; SeatBracket() end
        return
    end
    local idx = RowIndex(i, button)
    local info = { pcall(GetInboxHeaderInfo, idx) }
    local sender, subject, money, cod, days, items, wasRead
    if info[1] then
        sender, subject, money, cod, days, items, wasRead =
            Plain(info[4]), Plain(info[5]), Plain(info[6]), Plain(info[7]), Plain(info[8]), Plain(info[9]), Plain(info[10])
    else
        sender = Plain(Try(r.stockSender.GetText, r.stockSender))
        subject = Plain(Try(r.stockSubject.GetText, r.stockSubject))
    end
    local unread = not wasRead
    r.sender:SetText(type(sender) == "string" and sender or (_G.UNKNOWN or "?"))
    r.subject:SetText(type(subject) == "string" and subject or "")
    r.age:SetText(Age(days))
    local ink = unread and C.white or C.read
    r.sender:SetTextColor(ink[1], ink[2], ink[3], 1)
    r.led:SetColorTexture((unread and C.pink or C.ledOff)[1], (unread and C.pink or C.ledOff)[2], (unread and C.pink or C.ledOff)[3], 1)
    r.glow:SetShown(unread)

    local chips = {}
    local count = items == true and 1 or (type(items) == "number" and items or 0)
    if count > 0 then chips[#chips + 1] = { "x" .. count, C.cyan } end
    if type(money) == "number" and money > 0 then chips[#chips + 1] = { FormatMoney(money), C.gold } end
    if type(cod) == "number" and cod > 0 then chips[#chips + 1] = { "COD " .. FormatMoney(cod), C.amber } end
    -- chips run right to left from the card's right inset; the first chip of the list is the leftmost
    local used = #chips
    local right = G.ROW_W - 12
    for n = used, 1, -1 do
        local chip = r.chips[n]
        local w = FillChip(chip, chips[n][1], chips[n][2])
        Place(chip, r.card, right - w, 35, w, 20)
        right = right - w - 6
        chip:Show()
    end
    for n = used + 1, #r.chips do r.chips[n]:Hide() end
    -- the subject ends 8 px short of the leftmost chip, or of the card's right inset when there is none
    r.subject:SetWidth(U(math.max(1, (used > 0 and right - 2 or G.ROW_W - 12) - 32)))

    local selected = Try(button.GetChecked, button) == true
        or (_G.InboxFrame and _G.InboxFrame.openMailID == idx)
    r.selected = selected
    if selected then
        S.selected, S.mailIndex = i, idx
        PaintShape(r.shape, C.sel, 1, C.cyan, 1)
    else
        if S.selected == i then S.selected = nil end
        PaintShape(r.shape, C.ink, 1, C.line, 1)
    end
    SeatBracket()
end

local function RefreshInbox()
    for i = 1, ROWS do RefreshRow(i) end
    RefreshHeader()
    if S.RefreshPager then S.RefreshPager() end
end

local function BuildRow(i, win)
    local row, button = _G["MailItem" .. i], _G["MailItem" .. i .. "Button"]
    if not (row and button) then return end
    Theme.StripBlizzardChrome(row)
    local y = G.ROW_Y + (i - 1) * (G.ROW_H + G.ROW_GAP)
    Place(row, S.inbox, G.ROW_X, y, G.ROW_W, G.ROW_H)

    local card = CreateFrame("Frame", nil, row)
    card:SetAllPoints(row)
    local r = { row = row, button = button, card = card, chips = {} }
    r.shape = Shape(card, 8, C.ink, C.line, 1)
    r.glow = Rect(card, 9, 12, 14, 14, C.pink, 0.25, "ARTWORK", 1)
    r.led = Rect(card, 12, 15, 8, 8, C.ledOff, 1, "ARTWORK", 2)
    r.sender = Line(card, card, "LEFT", 32, 19, "", 16, C.white)
    r.age = Line(card, card, "RIGHT", G.ROW_W - 12, 19, "", 13, C.amber)
    r.subject = Line(card, card, "LEFT", 32, 45, "", 13, C.muted)
    for n = 1, 3 do r.chips[n] = NewChip(card) end

    -- The item button becomes the whole card's click target (its scripts are Blizzard's own: it opens the letter
    -- and, shift clicked, loots it); its picture, slot, count and COD stamp are held, the chips replace them.
    HeldArt.HoldButton(button)
    button:ClearAllPoints()
    button:SetAllPoints(row)
    Above(button, card)
    Quiet(_G["MailItem" .. i .. "ButtonCOD"])
    Quiet(_G["MailItem" .. i .. "ButtonCount"])
    r.stockSender, r.stockSubject = _G["MailItem" .. i .. "Sender"], _G["MailItem" .. i .. "Subject"]
    Quiet(r.stockSender)
    Quiet(r.stockSubject)

    -- The stock expiry button keeps its tooltip (time until deleted or returned) over our age text.
    local expire = _G["MailItem" .. i .. "ExpireTime"]
    if expire then
        QuietTexts(expire)
        Place(expire, card, G.ROW_W - 12 - 60, 9, 60, 20)
        Above(expire, button)
    end

    S.rows[i] = r
    HookFunc(r.stockSender, "SetText", function() RefreshRow(i) end)
    HookFunc(button, "SetChecked", function() RefreshRow(i) end)
    HookScript(button, "OnShow", function() RefreshRow(i) end)
    HookScript(button, "OnHide", function() RefreshRow(i) end)
    HookScript(button, "OnClick", function() Later(RefreshInbox) end)
end

-- The inbox pager buttons are anonymous on 16001: found by the mixin functions the engine copied onto them, then
-- by the retail global names and parentKeys.
local function FindPager(inbox, mixinName, globalName, key)
    local mixin = _G[mixinName]
    if type(mixin) == "table" and type(inbox.GetChildren) == "function" then
        for _, child in ipairs({ inbox:GetChildren() }) do
            for k, v in pairs(mixin) do
                if type(v) == "function" and type(child) == "table" and rawget(child, k) == v then return child end
            end
        end
    end
    return _G[globalName] or inbox[key]
end

local function BuildFooter(win, inbox)
    local H = S.height
    local rule = Rect(inbox, G.ROW_X, H - G.FOOT_RULE_UP, G.ROW_W, 1, C.violet, 0.35, "ARTWORK", 1)
    local top = H - G.PAGER_Y_UP
    local prev = FindPager(inbox, "InboxPrevPageMixin", "InboxPrevPageButton", "PrevPageButton")
    local nxt = FindPager(inbox, "InboxNextPageMixin", "InboxNextPageButton", "NextPageButton")
    if prev then
        Key(prev, { accent = C.violet, c = 4, glyph = function(b) return Runs(b, ChevronCells(13, 8, "<"), C.violet) end })
        Place(prev, inbox, G.ROW_X, top, 34, G.PAGER_H)
    end
    if nxt then
        Key(nxt, { accent = C.violet, c = 4, glyph = function(b) return Runs(b, ChevronCells(13, 8, ">"), C.violet) end })
        Place(nxt, inbox, G.ROW_X + 94, top, 34, G.PAGER_H)
    end
    local count = Line(inbox, inbox, "CENTER", G.ROW_X + 64, top + G.PAGER_H / 2, "1/1", 14, C.muted)
    Quiet(_G.InboxCurrentPage)
    function S.RefreshPager()
        local items = Plain(Try(GetInboxNumItems)) or 0
        local pages = math.max(1, math.ceil(items / ROWS))
        local page = math.min((_G.InboxFrame and _G.InboxFrame.pageNum) or 1, pages)
        count:SetText(page .. "/" .. pages)
    end
    for _, b in ipairs({ prev, nxt }) do HookScript(b, "OnClick", function() Later(RefreshInbox) end) end

    local open = _G.OpenAllMail
    if open then
        Key(open, { accent = C.cyan, c = 4, px = 15, shorten = { [(_G.OPEN_ALL_MAIL_BUTTON or "Open All Mail"):lower()] = "open all" } })
        Place(open, inbox, G.ROW_X + G.ROW_W - 148, top, 148, G.PAGER_H)
    end
    S.footer = { rule = rule, prev = prev, nxt = nxt, count = count, open = open }
    Quiet(_G.InboxTooMuchMail)
end

local function BuildInbox(win)
    local inbox = _G.InboxFrame
    if not inbox then return end
    S.inbox = inbox
    Theme.StripBlizzardChrome(inbox)
    inbox:ClearAllPoints()
    inbox:SetAllPoints(win)
    ROWS = type(_G.INBOXITEMS_TO_DISPLAY) == "number" and _G.INBOXITEMS_TO_DISPLAY or ROWS
    S.height = G.ROW_Y + ROWS * (G.ROW_H + G.ROW_GAP) - G.ROW_GAP + 14 + G.FOOT_RULE_UP
    G.WIN_H = S.height
    for i = 1, ROWS do BuildRow(i, win) end
    BuildFooter(win, inbox)
    S.bracket = {
        line = Rect(win, 0, 0, 32, 2, C.cyan, 1, "OVERLAY", 5),
        knob = Rect(win, 0, 0, 10, 10, C.cyan, 1, "OVERLAY", 5),
    }
    HookScript(inbox, "OnShow", RefreshInbox)
end

-------------------------------------------------------------------------------
-- Open letter
-------------------------------------------------------------------------------

local LETTER_KEYS = { "OpenMailReplyButton", "OpenMailDeleteButton", "OpenMailReportSpamButton" }

local function OpenIndex()
    local idx = _G.InboxFrame and _G.InboxFrame.openMailID
    if type(idx) ~= "number" then idx = S.mailIndex end
    return idx
end

local function ShownList(prefix, max)
    local list = {}
    for i = 1, max do
        local b = _G[prefix .. i]
        if b and Try(b.IsShown, b) == true then list[#list + 1] = b end
    end
    return list
end

-- "0g 12s", "1g 42s 39c": gold and silver always, copper when there is some.
local function ChipMoney(copper)
    copper = math.floor(tonumber(copper) or 0)
    local g, s, c = math.floor(copper / 10000), math.floor(copper % 10000 / 100), copper % 100
    local text = Hex(C.gold) .. g .. "g|r " .. Hex(C.silver) .. s .. "s|r"
    if c > 0 then text = text .. " " .. Hex(C.copper) .. c .. "c|r" end
    return text
end

-- Seats the letter panel's body, package wells, money chip and keys for what is shown now. The panel's height is
-- the window's less the header drop; everything below the body pad hangs from the bottom of it.
local function LayoutLetter()
    local L = S.letter
    if not L or InCombat() then return end
    local win = L.win
    local E = L.height - 544
    local takeY, keysY = 358 + E, 418 + E
    S.ppu = Ppu(win)

    local cells = {}
    local letter = _G.OpenMailLetterButton
    if letter and Try(letter.IsShown, letter) == true then cells[#cells + 1] = { b = letter, w = 44 } end
    for _, b in ipairs(ShownList("OpenMailAttachmentButton", type(_G.ATTACHMENTS_MAX_RECEIVE) == "number"
        and _G.ATTACHMENTS_MAX_RECEIVE or 16)) do
        cells[#cells + 1] = { b = b, w = 44 }
    end
    local moneyBtn = _G.OpenMailMoneyButton
    if moneyBtn and Try(moneyBtn.IsShown, moneyBtn) == true then cells[#cells + 1] = { b = moneyBtn, w = 120, chip = true } end

    local x, row, left, right = 18, 0, 18, G.LETTER_W - 18
    for n, cell in ipairs(cells) do
        local gap = n > 1 and (cell.chip and 12 or 6) or 0
        if x + gap + cell.w > right + 6 then row, x, gap = row + 1, left, 0 end
        cell.x, cell.row = x + gap, row
        x = x + gap + cell.w
    end
    local rows = #cells > 0 and row + 1 or 0
    local bottom = takeY - 18
    local top = bottom - (rows > 0 and (rows * 44 + (rows - 1) * 6) or 0)
    for _, cell in ipairs(cells) do
        local h = 44
        Place(cell.b, win, cell.x, top + cell.row * 50, cell.w, h)
        PaintWell(cell.b, true)
    end
    L.package:SetShown(rows > 0)
    Place(L.package, win, 18, top - 14, nil, nil, "LEFT", "TOPLEFT")
    local padBottom = rows > 0 and (top - 14 - 24) or bottom
    Place(L.pad, win, G.SIDE, 88, G.LETTER_W - 2 * G.SIDE, padBottom - 88)
    if L.scroll then Place(L.scroll, L.pad, 12, 10, G.LETTER_W - 2 * G.SIDE - 24, padBottom - 88 - 20) end

    Place(L.take, win, G.SIDE, takeY, G.LETTER_W - 2 * G.SIDE, 46)
    -- Take all is our own button, made at the letter's base level, so stock children stacked above it (the body
    -- text's hyperlink frame and scroll child run past the visible pad) took the clicks over most of its face.
    -- Keep it above every other child of the letter.
    if L.take.SetFrameLevel and win.GetFrameLevel then
        local top = win:GetFrameLevel()
        local function scan(frame, depth)
            for _, child in ipairs({ frame:GetChildren() }) do
                if child ~= L.take then
                    local level = Try(child.GetFrameLevel, child)
                    if type(level) == "number" and level > top then top = level end
                    if depth < 3 and type(child.GetChildren) == "function" then scan(child, depth + 1) end
                end
            end
        end
        scan(win, 1)
        pcall(L.take.SetFrameLevel, L.take, top + 1)
    end
    L.take:SetEnabled(#cells > 0)
    PaintKey(L.take)

    local keys = {}
    for _, name in ipairs(LETTER_KEYS) do
        local b = _G[name]
        if b and Try(b.IsShown, b) == true then keys[#keys + 1] = b end
    end
    if #keys > 0 then
        local inner = G.LETTER_W - 2 * G.SIDE
        local w = (inner - 8 * (#keys - 1)) / #keys
        for k, b in ipairs(keys) do Place(b, win, G.SIDE + (k - 1) * (w + 8), keysY, w, 36) end
    end
    Place(L.hint, win, G.LETTER_W / 2, L.height - 28, nil, nil, "CENTER", "TOPLEFT")
end

local function RefreshLetter()
    local L = S.letter
    if not L then return end
    local idx = OpenIndex()
    local info = { pcall(GetInboxHeaderInfo, idx or 0) }
    local sender, subject, money, days
    if info[1] then sender, subject, money, days = Plain(info[4]), Plain(info[5]), Plain(info[6]), Plain(info[8]) end
    L.from:SetText(type(sender) == "string" and sender or (_G.UNKNOWN or ""))
    L.re:SetText(type(subject) == "string" and subject or "")
    L.expires:SetText(type(days) == "number" and ("expires " .. Age(days)) or "")
    if L.money then L.money.label:SetText(ChipMoney(type(money) == "number" and money or 0)) end
    local del = _G.OpenMailDeleteButton
    if del then
        local text = Plain(Try(del.GetText, del))
        local ret = type(_G.MAIL_RETURN) == "string" and text == _G.MAIL_RETURN
        SetKeyAccent(del, ret and C.amber or C.pink)
    end
    LayoutLetter()
    SeatBracket()
end

local STOCK_LETTER_TEXT = {
    "OpenMailSenderLabel", "OpenMailSubjectLabel", "OpenMailSender", "OpenMailSubject", "OpenMailFrameTitleText",
    "OpenMailAttachmentText",
}
local STOCK_LETTER_FRAMES = { "OpenMailFrameCloseButton", "OpenMailCancelButton" }
local INVOICE_TEXT = {
    "OpenMailInvoiceItemLabel", "OpenMailInvoicePurchaser", "OpenMailInvoiceSalePrice", "OpenMailInvoiceDeposit",
    "OpenMailInvoiceHouseCut", "OpenMailInvoiceAmountReceived", "OpenMailInvoiceMoneyDelay", "OpenMailInvoiceNotYetSent",
}

local function SkinInvoice()
    for _, name in ipairs(INVOICE_TEXT) do
        local fs = _G[name]
        if fs and type(fs.SetFont) == "function" then
            Theme.ApplyMono(fs, U(12), C.text)
            S.fonts[fs] = { px = 12, color = C.text }
        end
    end
    for _, name in ipairs({ "OpenMailSalePriceMoneyFrame", "OpenMailDepositMoneyFrame", "OpenMailHouseCutMoneyFrame",
        "OpenMailTransactionAmountMoneyFrame" }) do
        if _G[name] and Theme.StyleMoney then Theme.StyleMoney(_G[name]) end
    end
    -- The stock receipt is laid out for a 296 unit parchment: the item block 30 in and 35 down, the price column
    -- 27 in from the right, and Amount Received hung off the 256 unit arithmetic line we hold at alpha 0, which
    -- puts it past the price column. Re-seat it against the pad: the item block at the top left inset, the price
    -- column 22 px in (the money frames hang 16 units right of their labels), Amount Received under House Cut.
    local inv = _G.OpenMailInvoiceFrame
    local item, buyer, sale = _G.OpenMailInvoiceItemLabel, _G.OpenMailInvoicePurchaser, _G.OpenMailInvoiceSalePrice
    local cut, received = _G.OpenMailInvoiceHouseCut, _G.OpenMailInvoiceAmountReceived
    if inv and item and sale and cut and received and type(item.ClearAllPoints) == "function" then
        item:ClearAllPoints()
        item:SetPoint("TOPLEFT", inv, "TOPLEFT", U(6), -U(6))
        item:SetPoint("RIGHT", inv, "RIGHT", -U(6), 0)
        if buyer then
            buyer:ClearAllPoints()
            buyer:SetPoint("TOPLEFT", item, "BOTTOMLEFT", 0, -U(5))
            buyer:SetPoint("RIGHT", inv, "RIGHT", -U(6), 0)
        end
        sale:ClearAllPoints()
        sale:SetPoint("TOPRIGHT", inv, "TOPRIGHT", -U(22), -U(52))
        received:ClearAllPoints()
        received:SetPoint("TOPRIGHT", cut, "BOTTOMRIGHT", 0, -U(26))
    end
end

-- The body text is SimpleHTML: Mononoki through its own SetFont, one call per element it formats.
local function SkinBodyText()
    local body = _G.OpenMailBodyText
    if not (body and type(body.SetFont) == "function") then return end
    for _, element in ipairs({ "P", "H1", "H2", "H3" }) do
        pcall(body.SetFont, body, element, Theme.FONT_MONO, U(15), "")
        if body.SetTextColor then pcall(body.SetTextColor, body, element, C.text[1], C.text[2], C.text[3]) end
    end
end

local function SkinLetter()
    local win = _G.OpenMailFrame
    if not win then return end
    S.height = S.height or G.WIN_H or 670
    local height = S.height - G.LETTER_DROP
    Chrome(win, C.cyan)
    win.fsMailSkin = true
    local L = { win = win, height = height }
    S.letter = L
    S.ppu = Ppu(win)

    win:ClearAllPoints()
    S.placed[win] = { ref = _G.MailFrame, x = G.WIN_W + G.LETTER_GAP, y = G.LETTER_DROP, w = G.LETTER_W, h = height,
        point = "TOPLEFT", relPoint = "TOPLEFT" }
    Apply(win)

    for _, name in ipairs(STOCK_LETTER_TEXT) do Quiet(_G[name]) end
    for _, name in ipairs(STOCK_LETTER_FRAMES) do
        local f = _G[name]
        Quiet(f)
        if f and f.EnableMouse then pcall(f.EnableMouse, f, false) end
    end
    PanelSkins.HideNamed({
        { name = "OpenMailHorizontalBarLeft", alpha0 = true }, { name = "OpenMailArithmeticLine", alpha0 = true },
        { name = "OpenStationeryBackgroundLeft", alpha0 = true }, { name = "OpenStationeryBackgroundRight", alpha0 = true },
    })

    Line(win, win, "LEFT", 18, 28, "FROM", 12, C.muted)
    L.from = Line(win, win, "LEFT", 70, 27, "", 17, C.white)
    Line(win, win, "LEFT", 18, 56, "RE", 12, C.muted)
    L.re = Line(win, win, "LEFT", 70, 56, "", 15, C.cyan)
    L.expires = Line(win, win, "RIGHT", G.LETTER_W - 18, 28, "", 13, C.amber)
    -- long senders and subjects end in an ellipsis inside the card: the subject runs to the right inset, the
    -- sender stops 12 px short of the expiry text (its widest form, "expires 30d", is about 110 px)
    L.re:SetWidth(U(G.LETTER_W - 70 - 18))
    L.from:SetWidth(U(G.LETTER_W - 70 - 18 - 110 - 12))
    Rect(win, G.SIDE, 76, G.LETTER_W - 2 * G.SIDE, 1, C.violet, 0.35, "ARTWORK", 1)

    L.pad = Box(win, win, G.SIDE, 88, G.LETTER_W - 2 * G.SIDE, 170)
    L.pad.fsShape = Shape(L.pad, 6, C.ink, C.violet, 0.35)
    L.scroll = _G.OpenMailScrollFrame
    if L.scroll then
        Above(L.scroll, L.pad)
        local function fit(self)
            local w = Plain(Try(self.GetWidth, self))
            if type(w) ~= "number" or w <= 0 then return end
            local child, body = _G.OpenMailScrollChildFrame, _G.OpenMailBodyText
            if child and child.SetWidth then pcall(child.SetWidth, child, w) end
            if body and body.SetWidth then pcall(body.SetWidth, body, w) end
        end
        HookScript(L.scroll, "OnSizeChanged", fit)
    end
    SkinBodyText()
    SkinInvoice()

    L.package = Line(win, win, "LEFT", 18, 282, "PACKAGE", 12, C.muted)
    for i = 1, (type(_G.ATTACHMENTS_MAX_RECEIVE) == "number" and _G.ATTACHMENTS_MAX_RECEIVE or 16) do
        local b = _G["OpenMailAttachmentButton" .. i]
        if b then
            Above(b, win)
            SkinWell(b, _G["OpenMailAttachmentButton" .. i .. "IconTexture"], _G["OpenMailAttachmentButton" .. i .. "Count"])
            Quiet(_G["OpenMailAttachmentButton" .. i .. "Stock"])
            HookScript(b, "OnShow", function() Later(LayoutLetter) end)
            HookScript(b, "OnHide", function() Later(LayoutLetter) end)
        end
    end
    for _, name in ipairs({ "OpenMailLetterButton", "OpenMailMoneyButton" }) do
        local b = _G[name]
        if b then
            Above(b, win)
            SkinWell(b, name == "OpenMailLetterButton" and _G[name .. "IconTexture"] or nil, _G[name .. "Count"],
                name == "OpenMailMoneyButton")
            Quiet(_G[name .. "Stock"])
            HookScript(b, "OnShow", function() Later(LayoutLetter) end)
            HookScript(b, "OnHide", function() Later(LayoutLetter) end)
        end
    end
    local moneyBtn = _G.OpenMailMoneyButton
    if moneyBtn then
        L.money = { label = Label(moneyBtn, "", 17, C.white) }
        L.money.label:SetPoint("CENTER", moneyBtn, "CENTER", 0, 0)
    end

    L.take = CreateFrame("Button", nil, win)
    L.take:SetScript("OnClick", function()
        local idx = OpenIndex()
        if idx and type(AutoLootMailItem) == "function" then pcall(AutoLootMailItem, idx) end
    end)
    Key(L.take, { accent = C.cyan, c = 6, px = 17, text = "take all", hold = false,
        glyph = function(b) return Runs(b, TriangleCells(16, 16), C.cyan) end })

    local accents = { OpenMailReplyButton = C.violet, OpenMailDeleteButton = C.pink, OpenMailReportSpamButton = C.violet }
    for _, name in ipairs(LETTER_KEYS) do
        local b = _G[name]
        if b then
            Key(b, { accent = accents[name], c = 6, px = 15,
                shorten = name == "OpenMailReportSpamButton" and { ["report player"] = "report", ["report spam"] = "report" } or nil })
            HookScript(b, "OnShow", function() Later(LayoutLetter) end)
            HookScript(b, "OnHide", function() Later(LayoutLetter) end)
        end
    end
    HookFunc(_G.OpenMailDeleteButton, "SetText", function() Later(RefreshLetter) end)
    L.hint = Line(win, win, "CENTER", G.LETTER_W / 2, height - 28, "click another letter to swap, esc closes the panel", 12, C.hint)

    local sender = _G.OpenMailSender
    HookFunc(sender and sender.Name, "SetText", function() Later(RefreshLetter) end)
    if type(_G.OpenMail_Update) == "function" then HookFunc(_G, "OpenMail_Update", function() Later(RefreshLetter) end) end
    HookScript(win, "OnShow", function()
        Apply(win)
        RefreshLetter()
        Later(function() PanelSkins.SweepScrollBars(win) end)
    end)
    HookScript(win, "OnHide", SeatBracket)

    if type(_G.UISpecialFrames) == "table" then
        local present = false
        for _, name in ipairs(_G.UISpecialFrames) do if name == "OpenMailFrame" then present = true end end
        if not present then table.insert(_G.UISpecialFrames, "OpenMailFrame") end
    end
    RefreshLetter()
end

-------------------------------------------------------------------------------
-- Send
-------------------------------------------------------------------------------

local SEND_GAP = 4

-- The icon of a send slot is its normal texture: seated inside the well, and the well lit when it holds one.
local function SeatSendSlot(button, index)
    local texture = Try(button.GetNormalTexture, button)
    local has = type(HasSendMailItem) == "function" and Try(HasSendMailItem, index) or texture ~= nil
    if texture and has then
        S.placed[texture] = { ref = button, x = 7, y = 7, w = 30, h = 30, point = "TOPLEFT", relPoint = "TOPLEFT" }
        Apply(texture)
    end
    PaintWell(button, has and true or false)
    return has and true or false
end

-- On 16001 an EditBox lists the FontString that draws its own typed text among its regions, so only the template's
-- caption ("To:", "Subject:") is held: a FontString with text that is not the box's current text. Quieting every
-- FontString region hid what the player typed.
local function SkinEditField(box, px, color, justify)
    if not box then return end
    local typed = Plain(Try(box.GetText, box)) or ""
    for _, region in ipairs({ box:GetRegions() }) do
        local kind = Try(region.GetObjectType, region)
        if kind == "Texture" then
            HeldArt.Hold(region)
        elseif kind == "FontString" then
            local text = Plain(Try(region.GetText, region))
            if type(text) == "string" and text ~= "" and text ~= typed then Quiet(region) end
        end
    end
    Theme.ApplyMono(box, U(px), color)
    S.fonts[box] = { px = px, color = color }
    if box.SetHighlightColor then pcall(box.SetHighlightColor, box, C.cyan[1], C.cyan[2], C.cyan[3], 0.35) end
    if box.SetTextInsets then box:SetTextInsets(0, 0, 0, 0) end
    if box.SetJustifyH then box:SetJustifyH(justify or "LEFT") end
end

-- The non-zero parts of an amount in their coin colours ("30c", "1s 5c").
local function PostageText(copper)
    copper = math.floor(tonumber(copper) or 0)
    local g, s2, c = math.floor(copper / 10000), math.floor(copper % 10000 / 100), copper % 100
    local parts = {}
    if g > 0 then parts[#parts + 1] = Hex(C.gold) .. g .. "g|r" end
    if s2 > 0 then parts[#parts + 1] = Hex(C.silver) .. s2 .. "s|r" end
    if c > 0 or #parts == 0 then parts[#parts + 1] = Hex(C.copper) .. c .. "c|r" end
    return table.concat(parts, " ")
end

local function RefreshSend()
    local L = S.send
    if not L then return end
    local price = type(GetSendMailPrice) == "function" and Plain(Try(GetSendMailPrice)) or 0
    L.postage:SetText(type(price) == "number" and PostageText(price) or "")
    local have = type(GetMoney) == "function" and Plain(Try(GetMoney)) or nil
    L.balance:SetText(type(have) == "number" and MoneyText(have) or "")
    if L.reseat then L.reseat() end
    local filled, total = 0, #L.slots
    for i, b in ipairs(L.slots) do if SeatSendSlot(b, i) then filled = filled + 1 end end
    L.cargo:SetText(filled .. "/" .. total)
    local sendMoney = _G.SendMailSendMoneyButton
    if sendMoney then L.mode.set(Try(sendMoney.GetChecked, sendMoney) == true and 1 or 2) end
end

-- The name suggestions under TO (AutoCompleteBox, a TooltipBackdropTemplate frame shared with whisper boxes): our
-- panel chrome, Mononoki rows through font objects (the buttons swap Normal and Highlight fonts on their own), a cyan
-- row highlight in place of the gold bar. Blizzard sizes the box from the row text widths each time it shows.
local function SkinAutoComplete()
    local box = _G.AutoCompleteBox
    if not box or box.fsMailSkin or type(CreateFont) ~= "function" then return end
    box.fsMailSkin = true
    -- TooltipBackdropTemplate draws its gold border and fill on a NineSlice CHILD frame at the box's own level
    -- (SharedTooltipTemplates.xml), which a region strip never reaches: hold it at alpha 0 under our chrome.
    Quiet(box.NineSlice)
    pcall(Theme.SkinPanel, box, { scanline = false })
    local normal = CreateFont("ForeverSTUwaveAutoCompleteNormal")
    normal:SetFont(Theme.FONT_MONO, U(14), "")
    normal:SetTextColor(C.text[1], C.text[2], C.text[3])
    local lit = CreateFont("ForeverSTUwaveAutoCompleteHighlight")
    lit:SetFont(Theme.FONT_MONO, U(14), "")
    lit:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3])
    for i = 1, (type(_G.AUTOCOMPLETE_MAX_BUTTONS) == "number" and _G.AUTOCOMPLETE_MAX_BUTTONS or 5) do
        local b = _G["AutoCompleteButton" .. i]
        if b then
            if b.SetNormalFontObject then pcall(b.SetNormalFontObject, b, normal) end
            if b.SetHighlightFontObject then pcall(b.SetHighlightFontObject, b, lit) end
            local hl = Try(b.GetHighlightTexture, b)
            if hl and hl.SetColorTexture then
                hl:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.16)
                if hl.SetBlendMode then hl:SetBlendMode("BLEND") end
            end
        end
    end
    local hint = _G.AutoCompleteInstructions
    if hint and hint.SetFont then
        Theme.ApplyMono(hint, U(11), C.muted)
        S.fonts[hint] = { px = 11, color = C.muted }
    end
end

local function SkinSend(win)
    local send = _G.SendMailFrame
    if not send then return end
    Theme.StripBlizzardChrome(send)
    send:ClearAllPoints()
    send:SetAllPoints(win)
    send.fsMailSkin = true
    local L = { slots = {} }
    S.send = L
    SkinAutoComplete()

    local rows = 1
    local total = math.min(type(_G.ATTACHMENTS_MAX_SEND) == "number" and _G.ATTACHMENTS_MAX_SEND or 8, 16)
    rows = math.max(1, math.ceil(total / 8))
    local E = S.height - 592 - 48 * (rows - 1)
    local H = S.height
    S.ppu = Ppu(win)

    for _, name in ipairs({ "SendMailMoneyText", "SendMailCostMoneyFrame", "SendMailMoneyFrame", "SendMailMoneyBg" }) do
        Quiet(_G[name])
    end
    PanelSkins.HideNamed({
        { name = "SendMailHorizontalBarLeft", alpha0 = true }, { name = "SendMailHorizontalBarLeft2", alpha0 = true },
        { name = "SendStationeryBackgroundLeft", alpha0 = true }, { name = "SendStationeryBackgroundRight", alpha0 = true },
    })
    HeldArt.Hold(_G.SendMailErrorCoin)

    -- prompt lines
    -- The typed text starts 12 px after its label: label widths in Mononoki at 13 px (0.6 em advance) are
    -- 16 px for TO and 55 px for SUBJECT.
    local function prompt(y, label, box, right)
        Line(send, send, "LEFT", 18, y, ">", 17, C.cyan)
        Line(send, send, "LEFT", 36, y, label, 13, C.muted)
        Rect(send, 18, y + 18, G.WIN_W - 36, 1, C.cyan, 0.4, "ARTWORK", 1)
        if box then
            local x = 36 + math.ceil(#label * 13 * 0.6) + 12
            SkinEditField(box, 17, C.white)
            Above(box, send)
            Place(box, send, x, y - 12, right - x, 24)
        end
    end
    prompt(80, "TO", _G.SendMailNameEditBox, 310 - 12)
    prompt(122, "SUBJECT", _G.SendMailSubjectEditBox, G.WIN_W - 18)

    -- postage chip
    local chip = Box(send, send, 310, 68, 104, 24)
    chip.fsShape = Shape(chip, 4, nil, C.amber, 0.6)
    Line(chip, chip, "LEFT", 8, 12, "POST", 12, C.muted)
    L.postage = Line(chip, chip, "RIGHT", 96, 12, "", 14, C.copper)

    -- message pad
    local padH = 150 + E
    local pad = Box(send, send, 18, 152, G.WIN_W - 36, padH)
    pad.fsShape = Shape(pad, 6, C.ink, C.violet, 0.35)
    local scroll = _G.SendMailScrollFrame
    if scroll then
        Above(scroll, pad)
        Place(scroll, pad, 12, 10, G.WIN_W - 36 - 24, padH - 20)
        HookScript(scroll, "OnSizeChanged", function(self)
            local w = Plain(Try(self.GetWidth, self))
            if type(w) ~= "number" or w <= 0 then return end
            local child, body = _G.SendMailScrollChildFrame, _G.SendMailBodyEditBox
            if child and child.SetWidth then pcall(child.SetWidth, child, w) end
            if body and body.SetWidth then pcall(body.SetWidth, body, w) end
        end)
    end
    local body = _G.SendMailBodyEditBox
    if body then
        Theme.ApplyMono(body, U(15), C.text)
        S.fonts[body] = { px = 15, color = C.text }
    end

    -- cargo strip
    local cargoY = 336 + E
    Line(send, send, "LEFT", 18, cargoY - 8, "CARGO", 12, C.muted)
    L.cargo = Line(send, send, "RIGHT", G.WIN_W - 18, cargoY - 8, "", 13, C.cyan)
    local strip = Box(send, send, 18, cargoY, G.WIN_W - 36, 14 + rows * 48 - SEND_GAP)
    strip.fsShape = Shape(strip, 6, C.ink, C.cyan, 0.3)
    for i = 1, total do
        local b = _G["SendMailAttachment" .. i]
        if b then
            L.slots[#L.slots + 1] = b
            local col, row = (i - 1) % 8, math.floor((i - 1) / 8)
            Above(b, strip)
            Place(b, strip, 8 + col * 48, 7 + row * 48, 44, 44)
            SkinWell(b, nil, _G["SendMailAttachment" .. i .. "Count"])
            HookFunc(b, "SetNormalTexture", function() SeatSendSlot(b, i) end)
            HookFunc(b, "ClearNormalTexture", function() SeatSendSlot(b, i) end)
        end
    end

    -- money inputs, one segment each
    local moneyY = cargoY + (14 + rows * 48 - SEND_GAP) + 38
    Line(send, send, "LEFT", 18, moneyY - 12, "MONEY", 12, C.muted)
    local segs = {
        { "SendMailMoneyGold", C.gold, "g" }, { "SendMailMoneySilver", C.silver, "s" }, { "SendMailMoneyCopper", C.copper, "c" },
    }
    for k, def in ipairs(segs) do
        local seg = Box(send, send, 18 + (k - 1) * 80, moneyY, 74, 36)
        seg.fsShape = Shape(seg, 6, C.ink, def[2], 0.55)
        Line(seg, seg, "CENTER", 67, 18, def[3], 13, C.muted)
        local box = _G[def[1]]
        if box then
            SkinEditField(box, 19, def[2], "RIGHT")
            Above(box, seg)
            Place(box, seg, 6, 6, 48, 24)
        end
    end

    -- send money / c.o.d. switch, over the two stock radio buttons
    local radios = { _G.SendMailSendMoneyButton, _G.SendMailCODButton }
    L.mode = Switch(send, send, 264, moneyY, 150, 36, { gap = 2, px = 13, labels = { "SEND", "C.O.D." }, buttons = radios })
    for i = 1, 2 do
        local b = radios[i]
        if b then
            HeldArt.Hold(Try(b.GetCheckedTexture, b))
            HeldArt.Hold(Try(b.GetDisabledCheckedTexture, b))
            Quiet(_G[i == 1 and "SendMailSendMoneyButtonText" or "SendMailCODButtonText"])
            HookFunc(b, "SetChecked", function() RefreshSend() end)
            HookScript(b, "OnClick", function() Later(RefreshSend) end)
        end
    end

    -- error line under the money row
    local err = _G.SendMailErrorText
    if err then
        Theme.ApplyMono(err, U(12), C.pink)
        S.fonts[err] = { px = 12, color = C.pink }
        S.placed[err] = { ref = send, x = G.WIN_W / 2, y = moneyY + 36 + 22, point = "CENTER", relPoint = "TOPLEFT" }
        Apply(err)
    end

    -- footer: balance, cancel, send
    Rect(send, 18, H - 69, G.WIN_W - 36, 1, C.violet, 0.35, "ARTWORK", 1)
    L.balance = Line(send, send, "LEFT", 18, H - 34, "", 17, C.white)
    local cancel, mail = _G.SendMailCancelButton, _G.SendMailMailButton
    if cancel then
        Key(cancel, { accent = C.pink, c = 6, px = 15 })
        Place(cancel, send, 204, H - 52, 110, 36)
    end
    if mail then
        Key(mail, { accent = C.cyan, fill = C.cyanFill, c = 6, px = 16 })
        Place(mail, send, 322, H - 52, 92, 36)
    end

    -- SendMailFrame_Update re-anchors every attachment button to the stock grid and resizes the scroll frame each
    -- time it runs (MailFrame.lua), which dropped the wells onto the money row: put ours back right after it.
    local function reseat()
        for _, b in ipairs(L.slots) do if S.placed[b] then Apply(b) end end
        if scroll and S.placed[scroll] then Apply(scroll) end
    end
    L.reseat = reseat
    if type(_G.SendMailFrame_Update) == "function" then
        HookFunc(_G, "SendMailFrame_Update", function() reseat(); Later(RefreshSend) end)
    end
    HookScript(send, "OnShow", function() RefreshSend(); Later(function() PanelSkins.SweepScrollBars(send) end) end)
    RefreshSend()
end

-------------------------------------------------------------------------------
-- Build and drive
-------------------------------------------------------------------------------

local STRIP = { "MailFrameInset", "OpenMailFrameInset", "SendMailMoneyInset" }

local function SizeWindow()
    local win = _G.MailFrame
    if not win or InCombat() or not S.height then return end
    S.ppu = Ppu(win)
    win:SetSize(U(G.WIN_W), U(S.height))
end

local function Relayout()
    local win = _G.MailFrame
    if not win then return end
    local ppu = Ppu(win)
    if ppu ~= S.ppu then
        S.ppu = ppu
        Reseat()
    end
    SizeWindow()
end

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("mail:" .. name, ("|cffff4488Forever STUwave|r: mail skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

local function Build()
    local win = _G.MailFrame
    if not win or S.done.window or InCombat() then return end
    S.done.window = true
    S.ppu = Ppu(win)
    win.fsMailSkin = true
    PanelSkins.StripNamed(STRIP)
    Step("chrome", Chrome, win, C.violet)
    Step("header", BuildHeader, win)
    Step("inbox", BuildInbox, win)
    Step("send", SkinSend, win)
    SizeWindow()
    Step("letter", SkinLetter)
    HookScript(win, "OnShow", function()
        Relayout()
        RefreshInbox()
        Later(function() PanelSkins.SweepScrollBars(win) end)
    end)
    RefreshInbox()
end

local watcher = CreateFrame("Frame")
for _, event in ipairs({ "MAIL_INBOX_UPDATE", "MAIL_SHOW", "MAIL_SEND_INFO_UPDATE", "MAIL_SEND_SUCCESS", "PLAYER_MONEY",
    "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED" }) do
    pcall(watcher.RegisterEvent, watcher, event)
end
watcher:SetScript("OnEvent", function(_, event)
    if not S.done.window then return end
    if event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then
        Step("relayout", Relayout)
        return
    end
    Step("refresh", function()
        RefreshInbox()
        RefreshSend()
        RefreshLetter()
    end)
end)

PanelSkins.RegisterInspect("Mail", {
    { name = "MailFrame", guard = "fsMailSkin" },
    { name = "OpenMailFrame", guard = "fsMailSkin" },
})

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
