-- Forever STUwave: Talents and Spellbook
-- The talent trees and the spellbook (PlayerSpellsFrame, readout debug/tree-PlayerSpellsFrame-2026-11-12.txt) restyled in place,
-- from the approved SPELLS mockup (mockups/character-spells-2026-11-12.html, section 2). The window chrome, the Primary and
-- Secondary tabs' plates, the search box and the Apply Changes button already wear the shared panel and control skins (Panels.lua
-- and the controls sweep); this adds the parts that were still stock. Live review 2026-11-14 ("lines through stuff, text
-- overlapping, and it just looks blah") rebuilt the talent page: no line of ours or Blizzard's crosses an icon or a text any more.
--
--   * the TalentsFrame: the painted background, the class paintings, the gold top band, inner frame border, dividers, clouds and
--     particles are all held. Three panels (a cut plate each, a frame of ours below the talent buttons) fill the gaps the stock
--     dividers marked, measured from the held dividers and inner frame, lit violet on the tree that has points and dim on the
--     others. Nothing is drawn across a header, an icon or a number;
--   * the three spec headers are one tidy row: the icon unmasked as a square in a cyan cut plate, the name mono to its right, and
--     the points spent as a chip (amber with points, dim at zero) right after the name. The stock ring, count box and divider
--     art are held;
--   * the Unspent Talents box: our own box wrapped around the label and the number (measured, so it fits the text), mono texts,
--     the number and the box amber while points are unspent;
--   * every talent button is a cut plate over its icon, its edge told by the state the stock code gave the border atlas and the
--     rank data it keeps: locked and idle dim, available violet, learned cyan, maxed amber, refund-invalid pink, hover cyan. A
--     locked or idle icon is dimmed by a veil of ours (the icon stays readable). The rank is a legible "x/y" chip in the bottom
--     right corner. The stock ring, hover ring, shadow, dimmer and rank text are held;
--   * the arrows between talent buttons (pooled edge frames): a solid line, thick enough to read, in the palette (violet idle,
--     dimmer when locked, cyan on a learned path, pink on a refund), the head always the bright art tinted to match. The state is
--     read from the atlas the stock code set, and follows each swap. The respec ghost parts stay stock;
--   * the Primary and Secondary tabs: the inline check and lock atlases of the stock label (and its colour code) are replaced by
--     a tick or a lock of ours beside the label, and each tab is sized to its text;
--   * the window's minimise and maximise buttons: held art, a plate, a glyph;
--   * the spellbook: parchment page art held with a dark underlay, dark parchment text retinted, category tab frames held;
--   * every spellbook entry (the pooled SpellBookItemTemplate frames of the two page views) is a cut card: its stock backplate,
--     icon frame, trainable art and sheen held, an edge by state (learned violet, passive cyan, can be learned now pink, level
--     locked dim), a hover that lights the card from the icon, the name and sub text mono with the state colour following the stock
--     repaint, the required level amber (pink when it can be learned now), and the icon button seated as a square slot
--     (Quest.lua's SquareSlot, asked for lazily: Quest.lua loads after this file). A section header gets a rule under it and mono
--     text. The page keys are Quest.lua's cut keys with a cyan chevron, the "Page 1/3" text mono.
--
-- Skin only: no SetScript, no SetAttribute, no reparent, no field written on a talent or spell button, post-hooks only. The stock
-- rank text and its outline copies are held at alpha 0 (a region write, the way FS.HeldArt holds a texture) and our chip reads the
-- node data the stock code keeps on the button; the tab labels and a header's name and count are re-seated by us (their own
-- regions, on frames that are not protected). Talent buttons and arrows are met again whenever the tree is rebuilt (spec change,
-- respec); the sweep is idempotent. A pooled spell entry is met once and repainted by a post-hook on its own UpdateVisuals;
-- frames the pool hands out later are met when the pages redisplay.
--
-- Left out on purpose (the mockup draws them, but they are computed, animated or invented, not a skin of a stock part): the action
-- key echo strip and the key LED on each entry, the live trace from an entry to its key and the free-key pulse while dragging, the
-- cooldown sweep over the icon, the separate "train / passive / lvl" chips and the "on" state of a toggle (the edge colour carries
-- the same facts), the circuit-board trace layout, the level gates and the hold-to-commit button of the talent page (the stock
-- Apply Changes flow stays), the slanted school tabs, and the help plate button.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.SkinSquare and PanelSkins.RequireExport(
    Theme.ApplyMono and PanelSkins.RetintDarkText,
    "Talents.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local Tal = {}
FS.TalentsSkin = Tal

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 }, dis = Theme.COLOR_CTRL_DIS or { 0.361, 0.329, 0.502 },
}
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = {
    done = false, nodes = Weak(), edges = Weak(), specs = Weak(), tabs = Weak(), books = Weak(), rules = {}, fits = {},
    texts = Weak(), items = Weak(), heads = Weak(),
}
Tal.state = S

local Plain, Try = Kit.Plain, Kit.Try
local List, AtlasOf = Char.List, Char.AtlasOf

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("talents:" .. name, ("|cffff4488Forever STUwave|r: talents skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

local function Num(v)
    v = Plain(v)
    return type(v) == "number" and v or nil
end

-- A 1 px line anchored over `ref` (a frame or a texture): across it ("h", through its middle) or along it ("v", through its
-- middle), colour `color`. Re-sized on a change of pixel scale. (The spellbook's section headers.)
local function Rule(host, ref, orient, color, alpha)
    local t = host:CreateTexture(nil, "OVERLAY", nil, 5)
    t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
    local rec = { t = t, host = host, ref = ref, orient = orient }
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        if orient == "h" then
            t:SetPoint("LEFT", ref, "LEFT", 0, 0)
            t:SetPoint("RIGHT", ref, "RIGHT", 0, 0)
            t:SetHeight(u)
        else
            t:SetPoint("TOP", ref, "TOP", 0, 0)
            t:SetPoint("BOTTOM", ref, "BOTTOM", 0, 0)
            t:SetWidth(u)
        end
    end
    S.rules[#S.rules + 1] = rec
    rec.apply()
    return t
end

-- `t` (a texture of ours, no art) stands `px` physical pixels out from `ref` (a text or a texture) on x and `py` on y: the rect
-- a chip or a box is drawn around. Anchored, so it follows the text it wraps; re-seated on a change of pixel scale.
local function Around(t, ref, px, py, host)
    local function apply()
        local ux, uy = Kit.U(host, px), Kit.U(host, py)
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", ref, "TOPLEFT", -ux, uy)
        t:SetPoint("BOTTOMRIGHT", ref, "BOTTOMRIGHT", ux, -uy)
    end
    S.fits[#S.fits + 1] = apply
    apply()
end

-- A plate's textures seated on `host`'s own rect, again whenever its pixel size changes (a plate made for a frame whose size
-- is not known yet, or one that is re-laid out).
local function SeatPlate(rec, host)
    local w, h = Kit.SizePx(host)
    if not w or (rec.w == w and rec.h == h) then return end
    rec.w, rec.h = w, h
    local plate = rec.plate
    Kit.Place(plate.fill, host, 0, 0, w, h)
    Kit.Place(plate.ring, host, 0, 0, w, h)
    if plate.ring2 then Kit.Place(plate.ring2, host, 1, 1, w - 2, h - 2) end
end

-- A text of the stock UI held at alpha 0 the way FS.HeldArt holds a texture (a region write, safe on a protected button): the
-- alpha is written again by a post-hook after any stock SetAlpha or SetTextColor, which is what a state repaint calls.
local heldText = Weak()
local function HoldText(fs)
    if type(fs) ~= "table" or heldText[fs] or type(fs.SetAlpha) ~= "function" then return end
    local busy = false
    local function zero()
        if busy then return end
        busy = true
        pcall(fs.SetAlpha, fs, 0)
        busy = false
    end
    zero()
    heldText[fs] = true
    Kit.HookFunc(fs, "SetAlpha", zero)
    Kit.HookFunc(fs, "SetTextColor", zero)
end

-- A text whose colour is ours and moves with a state: the stock SetTextColor is answered with `read()`. Returns the function that
-- applies it now.
local function Follow(fs, read)
    if type(fs) ~= "table" or type(fs.SetTextColor) ~= "function" then return function() end end
    local busy = false
    local function apply()
        local c = read()
        if busy or not c then return end
        busy = true
        pcall(fs.SetTextColor, fs, c[1], c[2], c[3], 1)
        busy = false
    end
    Kit.HookFunc(fs, "SetTextColor", function() if not busy then apply() end end)
    return apply
end

local function Tint(region, color, desaturate)
    if type(region) ~= "table" then return end
    if desaturate and type(region.SetDesaturated) == "function" then pcall(region.SetDesaturated, region, true) end
    if type(region.SetVertexColor) == "function" then pcall(region.SetVertexColor, region, color[1], color[2], color[3], 1) end
end

-- The state the stock code means by an atlas of a talent button's border or an arrow's parts: locked (gated or locked), gray (a
-- node that cannot be taken yet), yellow (taken, or maxed), green (a point can be spent on it now), red (refund invalid or an
-- error); nil for one this does not know (the ghost art, other trees' art).
local function AtlasToken(atlas)
    if type(atlas) ~= "string" then return nil end
    atlas = atlas:lower()
    if atlas:find("ghost") then return nil end
    if atlas:find("locked") then return "locked" end
    if atlas:find("gray") or atlas:find("grey") or atlas:find("disabled") then return "gray" end
    if atlas:find("yellow") or atlas:find("gold") or atlas:find("maxed") then return "yellow" end
    if atlas:find("green") or atlas:find("learn") then return "green" end
    if atlas:find("red") then return "red" end
    return nil
end

-------------------------------------------------------------------------------
-- Talent buttons: a cut plate, a veil on a locked icon, a rank chip
-------------------------------------------------------------------------------

local NODE = { CUT = 4, CHIP_PX = 11, PAD_X = 3, PAD_Y = 2, OUT = 2 }
local NODE_ART = { "StateBorder", "StateBorderHover", "Shadow", "DisabledOverlay" }

-- How a node looks in each state: its edge, the edge width in pixels, the rank text colour and the veil over a dimmed icon.
local LOOK = {
    locked = { edge = C.dim, px = 1, text = C.muted, veil = 0.55 },
    idle = { edge = C.dim, px = 1, text = C.muted, veil = 0.3 },
    open = { edge = C.violet, px = 2, text = C.text },
    learned = { edge = C.cyan, px = 2, text = C.cyan },
    maxed = { edge = C.amber, px = 2, text = C.amber },
    refund = { edge = C.pink, px = 2, text = C.pink },
}

-- The rank and the most ranks of the node a button shows; nil for one the stock code keeps secret or has not set.
local function Ranks(btn)
    local info = Plain(btn.nodeInfo)
    if type(info) ~= "table" then return nil, nil end
    return Num(info.currentRank), Num(info.maxRanks)
end

local function NodeLook(token, cur, max)
    if token == "red" then return LOOK.refund end
    if token == "yellow" then
        if cur and max and cur < max then return LOOK.learned end
        return LOOK.maxed
    end
    if token == "green" then return LOOK.open end -- a point can be spent on it now, whatever it holds already
    if token == "locked" then return LOOK.locked end
    return LOOK.idle
end

-- "x/y" from the node data; the stock number alone when only it is known; nil when there is nothing to say.
local function ChipText(btn, cur, max)
    if cur and max then return tostring(cur) .. "/" .. tostring(max) end
    local fs = btn.SpendText
    local stock = type(fs) == "table" and Plain(Try(fs.GetText, fs)) or nil
    if type(stock) == "string" and stock ~= "" then return stock end
    return nil
end

local function ShowBox(box, shown)
    box.fill:SetShown(shown)
    for _, e in ipairs(box.edges) do e:SetShown(shown) end
end

local function PaintNode(btn)
    local rec = S.nodes[btn]
    if not rec then return end
    SeatPlate(rec, btn)
    local cur, max = Ranks(btn)
    local look = NodeLook(AtlasToken(AtlasOf(btn.StateBorder)), cur, max)
    local fill, edge, px = C.ink, look.edge, look.px
    if rec.state and rec.state.hover then fill, edge, px = Kit.Mix(C.ink, C.cyan, 0.2), C.cyan, 2 end
    Kit.PaintPlate(rec.plate, fill, 1, edge, 1, px)
    if look.veil then
        rec.dim:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], look.veil)
        rec.dim:Show()
    else
        rec.dim:Hide()
    end
    local text = ChipText(btn, cur, max)
    local chip = rec.chip
    if text then
        chip.text:SetText(text)
        Kit.Recolor(chip.text, look.text)
        Char.PaintBox(chip, C.ink, 0.94, look.edge, 1, 1)
    end
    chip.text:SetShown(text ~= nil)
    ShowBox(chip, text ~= nil)
    Tint(btn.Glow, C.violet, true)
    Tint(btn.SelectableGlow, C.violet, true)
end

local NODE_HOOKS = {
    "UpdateStateBorder", "UpdateVisualState", "UpdateNonStateVisuals", "SetVisualState", "UpdateAll", "UpdateSpendText",
    "UpdateNodeInfo", "FullUpdate", "ApplyVisualState",
}

local function SkinNode(btn)
    if type(btn) ~= "table" or S.nodes[btn] or type(btn.StateBorder) ~= "table" then return end
    for _, key in ipairs(NODE_ART) do HeldArt.Hold(btn[key]) end
    HoldText(btn.SpendText)
    for _, shadow in ipairs(type(btn.spendTextShadows) == "table" and btn.spendTextShadows or {}) do HoldText(shadow) end
    local w, h = Kit.SizePx(btn)
    local rec = { plate = Kit.Plate(btn, NODE.CUT, w or 48, h or 48) }
    -- a veil over the icon, for the nodes that cannot be taken (the stock dimmer is held)
    rec.dim = btn:CreateTexture(nil, "ARTWORK", nil, 1)
    rec.dim:SetAllPoints(type(btn.Icon) == "table" and btn.Icon or btn)
    rec.dim:Hide()
    -- the rank chip: text in the bottom right corner (a little outside it), a box around the text
    local text = Kit.Label(btn, "", NODE.CHIP_PX, C.text, "OVERLAY")
    Kit.Place(text, btn, -(NODE.PAD_X - NODE.OUT), NODE.OUT - NODE.PAD_Y, nil, nil, "BOTTOMRIGHT", "BOTTOMRIGHT", btn)
    local pad = btn:CreateTexture(nil, "ARTWORK", nil, 1)
    Around(pad, text, NODE.PAD_X, NODE.PAD_Y, btn)
    rec.chip = Char.Box(btn, "ARTWORK", pad)
    rec.chip.fill:SetDrawLayer("ARTWORK", 2)
    for _, e in ipairs(rec.chip.edges) do e:SetDrawLayer("ARTWORK", 3) end
    rec.chip.text = text
    S.nodes[btn] = rec
    local function again() Step("node", PaintNode, btn) end
    if type(btn.StateBorder.SetAtlas) == "function" then Kit.HookFunc(btn.StateBorder, "SetAtlas", again) end
    if type(btn.SpendText) == "table" then Kit.HookFunc(btn.SpendText, "SetText", again) end
    for _, m in ipairs(NODE_HOOKS) do Kit.HookFunc(btn, m, again) end
    rec.state = Kit.Track(btn, again)
    PaintNode(btn)
end

-------------------------------------------------------------------------------
-- The arrows between talent buttons
-------------------------------------------------------------------------------

-- TalentEdgeArrowTemplate (children of the ButtonsParent, pooled): a Line (a stock Line region, thickness 6) and an ArrowHead
-- whose atlas the stock UpdateState swaps by state (gray, yellow, locked, red). The line becomes a solid colour (the engine
-- drops a region's atlas when it is given a colour, so the state is taken from the atlas argument of each stock SetAtlas, not
-- read back), thick enough to read; the head is always the bright art, tinted to the same colour. The ghost line and ghost head
-- (the respec preview) stay stock.
local EDGE = { IDLE_PX = 3, LIT_PX = 4, HEAD = "talents-arrow-head-yellow" }
local EDGE_LOOK = {
    gray = { color = Kit.Mix(C.violet, C.ink, 0.25), px = EDGE.IDLE_PX },
    locked = { color = Kit.Mix(C.dim, C.violet, 0.35), px = EDGE.IDLE_PX },
    yellow = { color = C.cyan, px = EDGE.LIT_PX },
    red = { color = C.pink, px = EDGE.LIT_PX },
}
local EDGE_PARTS = { "Line", "ArrowHead" }

local function PaintEdge(edge)
    local rec = S.edges[edge]
    if not rec then return end
    local look = EDGE_LOOK[rec.token] or EDGE_LOOK.gray
    local c = look.color
    rec.busy = true
    local line, head = edge.Line, edge.ArrowHead
    if type(line.SetColorTexture) == "function" then pcall(line.SetColorTexture, line, c[1], c[2], c[3], 1) end
    if type(line.SetThickness) == "function" then pcall(line.SetThickness, line, Kit.U(edge, look.px)) end
    if type(head.SetAtlas) == "function" then pcall(head.SetAtlas, head, EDGE.HEAD) end
    Tint(head, c, true)
    rec.busy = false
end

local function IsEdge(frame)
    return type(frame.Line) == "table" and type(frame.ArrowHead) == "table" and frame.StateBorder == nil
end

local function SkinEdge(edge)
    if S.edges[edge] or not IsEdge(edge) then return end
    local rec = { token = AtlasToken(AtlasOf(edge.Line)) or AtlasToken(AtlasOf(edge.ArrowHead)) }
    S.edges[edge] = rec
    for _, key in ipairs(EDGE_PARTS) do
        local part = edge[key]
        if type(part.SetAtlas) == "function" then
            Kit.HookFunc(part, "SetAtlas", function(_, atlas)
                if rec.busy then return end
                rec.token = AtlasToken(Plain(atlas)) or rec.token
                Step("edge", PaintEdge, edge)
            end)
        end
    end
    Kit.HookFunc(edge, "UpdateState", function() Step("edge", PaintEdge, edge) end)
    PaintEdge(edge)
end

local function SkinNodes(frame)
    local parent = frame.ButtonsParent
    if type(parent) ~= "table" then return end
    for _, child in ipairs(List(parent, "GetChildren")) do
        if type(child) == "table" then
            Step("node", SkinNode, child)
            Step("edge", SkinEdge, child)
        end
    end
end

-------------------------------------------------------------------------------
-- The talent frame: art, panels, headers, the Unspent Talents box, the tabs
-------------------------------------------------------------------------------

local FRAME_ART = {
    "Background", "BackgroundBorder", "DividerHorizontalLeft", "DividerHorizontalRight", "DividerVerticalLeft",
    "DividerVerticalRight", "Clouds1", "Clouds2", "AirParticlesClose", "AirParticlesFar", "ClassBackground", "BackgroundFlash",
    "OverlayBackgroundRight", "OverlayBackgroundMid",
}

local function SkinFrameArt(frame)
    for _, key in ipairs(FRAME_ART) do HeldArt.Hold(frame[key]) end
end

local function Rect4(o)
    if type(o) ~= "table" then return nil end
    local l, t, r, b = Num(Try(o.GetLeft, o)), Num(Try(o.GetTop, o)), Num(Try(o.GetRight, o)), Num(Try(o.GetBottom, o))
    if l and t and r and b then return l, t, r, b end
    return nil
end

-- The three spec headers (anonymous 48 x 48 frames of the TalentsFrame: Icon and its mask, MainRing, TextBackground, Name, Text,
-- Divider), left to right.
local function SpecHeaders(frame)
    local out = {}
    for _, child in ipairs(List(frame, "GetChildren")) do
        if type(child) == "table" and child.MainRing and child.TextBackground and child.Name then out[#out + 1] = child end
    end
    table.sort(out, function(a, b) return (Num(Try(a.GetLeft, a)) or 0) < (Num(Try(b.GetLeft, b)) or 0) end)
    return out
end

-- The points spent in a tree: the number the stock count shows.
local function Points(head)
    local fs = type(head) == "table" and head.Text
    if type(fs) ~= "table" then return 0 end
    return tonumber(Plain(Try(fs.GetText, fs))) or 0
end

-- Three panels, one per tree, in the gaps the stock vertical dividers marked: from the inner frame's left edge to the first
-- divider, between the dividers, from the last divider to the inner frame's right edge, MARGIN from the frame and GAP from each
-- divider. They are frames of ours at the talent frame's own level, so below the talent buttons, arrows and headers (children of
-- the ButtonsParent and the talent frame, one level up or more). Measured from the held stock pieces, laid out again whenever
-- the frame is resized.
local COL = { CUT = 6, MARGIN = 6, GAP = 6 }

local function PaintCols()
    for _, col in ipairs(S.cols or {}) do
        local lit = Points(col.head) > 0
        Kit.PaintPlate(col.plate, C.ink, 1, lit and C.violet or C.dim, 1, lit and 2 or 1)
    end
end

local function HeadAt(heads, l, r)
    for _, h in ipairs(heads) do
        local hl = Num(Try(h.GetLeft, h))
        if hl and hl >= l - 1 and hl <= r then return h end
    end
    return nil
end

local function LayoutCols(tf)
    local inner = tf.BackgroundBorder
    local il, it, ir, ib = Rect4(inner)
    local tl, tt = Num(Try(tf.GetLeft, tf)), Num(Try(tf.GetTop, tf))
    if not (il and tl and tt) then return end
    local divs = {}
    for _, key in ipairs({ "DividerVerticalLeft", "DividerVerticalRight" }) do
        local dl, _, dr = Rect4(tf[key])
        if dl then divs[#divs + 1] = { l = dl, r = dr } end
    end
    if #divs == 0 then return end
    table.sort(divs, function(a, b) return a.l < b.l end)
    local heads = SpecHeaders(tf)
    if #heads == 0 then return end
    local margin, gap = Kit.U(tf, COL.MARGIN), Kit.U(tf, COL.GAP)
    local bounds, left = {}, il + margin
    for _, d in ipairs(divs) do
        bounds[#bounds + 1] = { left, d.l - gap }
        left = d.r + gap
    end
    bounds[#bounds + 1] = { left, ir - margin }
    local top, bottom = it - margin, ib + margin
    for _, h in ipairs(heads) do
        local _, ht = Rect4(h)
        if ht and ht + margin > top then top = ht + margin end
    end
    if top - bottom < 20 then return end
    S.cols = S.cols or {}
    for i, b in ipairs(bounds) do
        if b[2] - b[1] > 20 then
            local col = S.cols[i]
            if not col then
                local frame = CreateFrame("Frame", nil, tf)
                frame:SetFrameLevel(tf:GetFrameLevel())
                col = { frame = frame, plate = Kit.Plate(frame, COL.CUT, 64, 64) }
                S.cols[i] = col
            end
            col.head = HeadAt(heads, b[1], b[2])
            col.frame:ClearAllPoints()
            col.frame:SetPoint("TOPLEFT", tf, "TOPLEFT", b[1] - tl, top - tt)
            col.frame:SetSize(b[2] - b[1], top - bottom)
            SeatPlate(col, col.frame)
        end
    end
    PaintCols()
end

-- The header row: the icon (unmasked, a square) in a cyan cut plate, the name to its right, the points chip right after the name.
local HEAD = { CUT = 4, INSET = 3, GAP = 10, CHIP_GAP = 8, PAD_X = 5, PAD_Y = 3, NAME_PX = 15, CHIP_PX = 13 }

local function SeatSpecPlate(head, rec)
    local icon = head.Icon
    local ppu = Kit.Ppu(head)
    local iw, ih = Num(Try(icon.GetWidth, icon)), Num(Try(icon.GetHeight, icon))
    if not (iw and ih and iw > 0 and ih > 0) then return end
    iw, ih = math.floor(iw * ppu + 0.5), math.floor(ih * ppu + 0.5)
    if rec.iw == iw and rec.ih == ih then return end
    rec.iw, rec.ih = iw, ih
    local p, plate = HEAD.INSET, rec.plate
    local w, h = iw + 2 * p, ih + 2 * p
    Kit.Place(plate.fill, icon, -p, -p, w, h, "TOPLEFT", "TOPLEFT", head)
    Kit.Place(plate.ring, icon, -p, -p, w, h, "TOPLEFT", "TOPLEFT", head)
    if plate.ring2 then Kit.Place(plate.ring2, icon, -p + 1, -p + 1, w - 2, h - 2, "TOPLEFT", "TOPLEFT", head) end
end

-- The name and the count are seated again from the icon (the stock code seats them from the ring and the count box, both held).
local function SeatSpecTexts(head)
    local name, text = head.Name, head.Text
    if type(name) == "table" then
        pcall(name.SetWidth, name, 0)
        pcall(name.ClearAllPoints, name)
        pcall(name.SetPoint, name, "LEFT", head.Icon, "RIGHT", Kit.U(head, HEAD.INSET + HEAD.GAP), 0)
    end
    if type(text) == "table" and type(name) == "table" then
        pcall(text.SetWidth, text, 0)
        pcall(text.ClearAllPoints, text)
        pcall(text.SetPoint, text, "LEFT", name, "RIGHT", Kit.U(head, HEAD.CHIP_GAP + HEAD.PAD_X), 0)
    end
end

local function PaintSpec(head)
    local rec = S.specs[head]
    if type(rec) ~= "table" then return end
    local lit = Points(head) > 0
    local edge = lit and C.amber or C.dim
    Char.PaintBox(rec.chip, C.ink, 1, edge, 1, 1)
    rec.textColor = lit and C.amber or C.muted
    rec.applyText()
    Kit.PaintPlate(rec.plate, C.ink, 1, C.cyan, lit and 1 or 0.6, lit and 2 or 1)
    SeatSpecPlate(head, rec)
    PaintCols()
end

local function SkinSpecHeader(head)
    if S.specs[head] then return end
    HeldArt.Hold(head.TextBackground)
    HeldArt.Hold(head.Divider)
    HeldArt.Hold(head.MainRing)
    local icon, name, text = head.Icon, head.Name, head.Text
    if type(icon) ~= "table" or type(name) ~= "table" or type(text) ~= "table" then return end
    -- the round mask off, the art's own border cropped: a square icon
    for _, region in ipairs(List(head, "GetRegions")) do
        if Try(region.GetObjectType, region) == "MaskTexture" and type(icon.RemoveMaskTexture) == "function" then
            pcall(icon.RemoveMaskTexture, icon, region)
        end
    end
    if type(icon.SetTexCoord) == "function" then pcall(icon.SetTexCoord, icon, 0.07, 0.93, 0.07, 0.93) end
    local rec = { plate = Kit.Plate(head, HEAD.CUT, 64, 64) }
    Kit.RestyleLabel(name, head, HEAD.NAME_PX, C.text)
    Char.PinColor(name, C.text)
    Kit.RestyleLabel(text, head, HEAD.CHIP_PX, C.amber)
    rec.applyText = Follow(text, function() return rec.textColor end)
    SeatSpecTexts(head)
    -- the chip around the count: an invisible rect of ours around the text, a box on it
    local pad = head:CreateTexture(nil, "BACKGROUND")
    Around(pad, text, HEAD.PAD_X, HEAD.PAD_Y, head)
    rec.chip = Char.Box(head, "OVERLAY", pad)
    S.specs[head] = rec
    Kit.HookFunc(text, "SetText", function() Step("spec", PaintSpec, head) end)
    PaintSpec(head)
end

local function SkinSpecHeaders(frame)
    for _, head in ipairs(SpecHeaders(frame)) do Step("spec", SkinSpecHeader, head) end
    for _, head in ipairs(SpecHeaders(frame)) do
        if S.specs[head] then SeatSpecTexts(head) end
    end
end

-- The Unspent Talents box: a frame of ours (below the readout, so the texts draw over it) holding a box, sized and seated around
-- the label and the number each time they change; the stock box art is held.
local CUR = { PAD_X = 6, PAD_Y = 3, LABEL_PX = 12, AMOUNT_PX = 22 }

local function PaintCurrency()
    local rec = S.currency
    if type(rec) ~= "table" then return end
    local amount = rec.amount
    local lit = type(amount) == "table" and (tonumber(Plain(Try(amount.GetText, amount))) or 0) > 0
    rec.numColor = lit and C.amber or C.muted
    Char.PaintBox(rec, C.ink, 1, lit and C.amber or C.dim, 1, 1)
    if rec.applyAmount then rec.applyAmount() end
end

local function FitCurrency(tf)
    local rec = S.currency
    if type(rec) ~= "table" then return end
    local label, amount = rec.label, rec.amount
    local ll, lt, lr, lb = Rect4(label)
    local al, at, ar, ab = Rect4(amount)
    local tl, tt = Num(Try(tf.GetLeft, tf)), Num(Try(tf.GetTop, tf))
    if not (ll and al and tl and tt) then
        rec.frame:Hide()
        return
    end
    local px, py = Kit.U(tf, CUR.PAD_X), Kit.U(tf, CUR.PAD_Y)
    local left, right = math.min(ll, al), math.max(lr, ar)
    local top, bottom = math.max(lt, at), math.min(lb, ab)
    rec.frame:ClearAllPoints()
    rec.frame:SetPoint("TOPLEFT", tf, "TOPLEFT", left - px - tl, top + py - tt)
    rec.frame:SetSize(right - left + 2 * px, top - bottom + 2 * py)
    rec.frame:Show()
end

local function SkinCurrency(frame)
    local cur = frame.ClassCurrencyDisplay
    if type(cur) ~= "table" or S.currency then return end
    local label = cur.UnspentLabel
    local amount = cur.CurrentAmountContainer and cur.CurrentAmountContainer.CurrencyAmount
    if type(label) ~= "table" or type(amount) ~= "table" then return end
    HeldArt.Hold(cur.Border)
    local wrap = CreateFrame("Frame", nil, frame)
    wrap:SetFrameLevel(frame:GetFrameLevel())
    local rec = Char.Box(wrap, "OVERLAY")
    rec.frame, rec.label, rec.amount = wrap, label, amount
    Kit.RestyleLabel(label, cur, CUR.LABEL_PX, C.muted)
    Char.PinColor(label, C.muted)
    Kit.RestyleLabel(amount, cur, CUR.AMOUNT_PX, C.amber)
    rec.applyAmount = Follow(amount, function() return rec.numColor end)
    -- the stock layout sized the label for the stock font; it is as wide as our text now
    pcall(label.SetWidth, label, 0)
    if type(cur.MarkDirty) == "function" then pcall(cur.MarkDirty, cur) end
    S.currency = rec
    Kit.HookFunc(amount, "SetText", function() Step("currency", PaintCurrency) end)
    Kit.HookFunc(label, "SetText", function() Kit.Later(function() Step("currency", FitCurrency, frame) end) end)
    Kit.HookScript(cur, "OnSizeChanged", function() Kit.Later(function() Step("currency", FitCurrency, frame) end) end)
    PaintCurrency()
end

-- The Primary and Secondary tabs (a TabSystem under the talent frame): the stock label carries an inline check or lock atlas and
-- a colour code, which draw outside our plate. Both go; a tick or a lock of ours sits right after the label, the label and the
-- glyph are centred as one, and the tab is as wide as its text (the layout is asked to flow again).
local TAB = { PAD = 20, GLYPH = 16, GAP = 4 }
local TAB_GLYPH = { tick = MEDIA .. "ctl_tick.tga", lock = MEDIA .. "ctl_lock.tga" }

-- The label without its markup, and which glyph its markup asked for ("tick", "lock" or nil).
local function Unmark(text)
    local kind = nil
    if text:find("Talents%-Checkmark") then kind = "tick" elseif text:find("Talents%-lock") then kind = "lock" end
    local clean = text:gsub("|A.-|a", ""):gsub("|T.-|t", ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    clean = clean:gsub("^%s+", ""):gsub("%s+$", "")
    return clean, kind
end

local function Guarded(tab)
    return type(InCombatLockdown) == "function" and InCombatLockdown() and Plain(Try(tab.IsProtected, tab)) == true
end

-- The label's centre is moved left by half the glyph and its gap, from where the stock code (or TabSkins) last put it.
local function SeatTabLabel(tab, rec)
    local label = tab.Text
    local ok, point, rel, relPoint, x, y = pcall(label.GetPoint, label, 1)
    x, y = Num(x), Num(y)
    if not (ok and point == "CENTER" and x and y) then return end
    if rec.base == nil then rec.base = x end
    local want = rec.base - (rec.kind and Kit.U(tab, (TAB.GLYPH + TAB.GAP) / 2) or 0)
    if math.abs(want - x) < 0.001 then return end
    rec.busy = true
    pcall(label.SetPoint, label, point, rel, relPoint, want, y)
    rec.busy = false
end

local function FitTab(tab, rec)
    local label = tab.Text
    if rec.fitting or Guarded(tab) then return end
    local sw = Num(Try(label.GetStringWidth, label))
    if not sw or sw <= 0 then return end
    rec.fitting = true
    pcall(label.SetWidth, label, 0)
    local width = sw + Kit.U(tab, 2 * TAB.PAD + (rec.kind and (TAB.GLYPH + TAB.GAP) or 0))
    width = math.max(width, sw + 34) -- TabSkins widens a tab that is narrower than its label plus 34
    local was = Num(Try(tab.GetWidth, tab))
    pcall(tab.SetWidth, tab, width)
    if not was or math.abs(was - width) > 0.01 then
        local ts = Try(tab.GetParent, tab)
        if type(ts) == "table" and type(ts.MarkDirty) == "function" then pcall(ts.MarkDirty, ts) end
    end
    SeatTabLabel(tab, rec)
    rec.fitting = nil
end

local function PaintTab(tab)
    local rec = S.tabs[tab]
    local label = tab.Text
    if type(rec) ~= "table" or rec.busy then return end
    local text = Plain(Try(label.GetText, label))
    if type(text) ~= "string" or text == "" then return end
    local clean, kind = Unmark(text)
    -- the glyph the stock text asked for (none when it has no markup); the markup itself is taken off
    rec.kind = kind
    if clean ~= text then
        rec.busy = true
        pcall(label.SetText, label, clean)
        rec.busy = false
    end
    local glyph = rec.glyph
    if kind then
        glyph:SetTexture(TAB_GLYPH[kind])
        local c = kind == "tick" and C.cyan or C.dis
        glyph:SetVertexColor(c[1], c[2], c[3], 1)
        glyph:Show()
    else
        glyph:Hide()
    end
    FitTab(tab, rec)
end

local function SkinTab(tab)
    if S.tabs[tab] or type(tab.Text) ~= "table" or type(tab.CreateTexture) ~= "function" then return end
    local label = tab.Text
    local glyph = tab:CreateTexture(nil, "OVERLAY", nil, 6)
    Kit.Snap(glyph)
    glyph:Hide()
    local rec = { glyph = glyph }
    S.tabs[tab] = rec
    local function seat()
        local u = Kit.U(tab, TAB.GLYPH)
        glyph:ClearAllPoints()
        glyph:SetPoint("LEFT", label, "RIGHT", Kit.U(tab, TAB.GAP), 0)
        glyph:SetSize(u, u)
    end
    S.fits[#S.fits + 1] = seat
    seat()
    local function again() Step("tab", PaintTab, tab) end
    Kit.HookFunc(label, "SetText", again)
    Kit.HookFunc(tab, "SetText", again)
    -- the tab skin puts its mono font on the label after we first measured it
    Kit.HookFunc(label, "SetFont", function() Step("tab", FitTab, tab, rec) end)
    Kit.HookFunc(tab, "UpdateTabWidth", function() Step("tab", FitTab, tab, rec) end)
    Kit.HookFunc(tab, "SetTabWidth", function() Step("tab", FitTab, tab, rec) end)
    Kit.HookFunc(label, "SetPoint", function()
        if rec.busy or rec.fitting then return end
        rec.base = nil
        Step("tab", SeatTabLabel, tab, rec)
    end)
    PaintTab(tab)
end

local function SkinTabs(frame)
    local ts = frame.TabSystem
    if type(ts) ~= "table" then return end
    for _, tab in ipairs(List(ts, "GetChildren")) do
        if type(tab) == "table" then Step("tab", SkinTab, tab) end
    end
end

-- Lays out what is measured from stock pieces (the panels, the Unspent Talents box); run after the stock layout settles.
function Tal.Layout()
    local tf = S.tf
    if not tf then return end
    Step("cols", LayoutCols, tf)
    Step("currency", FitCurrency, tf)
end

local function SkinTalents(frame)
    S.tf = frame
    SkinFrameArt(frame)
    SkinSpecHeaders(frame)
    SkinCurrency(frame)
    SkinTabs(frame)
    SkinNodes(frame)
    Tal.Layout()
end

-------------------------------------------------------------------------------
-- Minimise and maximise
-------------------------------------------------------------------------------

-- The window's size toggle wears the close button's key, cyan, seated just left of the close button: a window glyph to
-- maximise, a bar to restore.
local function SkinSizeButton(btn, glyph, close)
    if type(btn) ~= "table" or not (FS.ButtonSkins and FS.ButtonSkins.SkinCloseButton) then return end
    FS.ButtonSkins.SkinCloseButton(btn, { glyph = glyph, accent = C.cyan, beside = close })
end

local function SkinSizeButtons(win)
    local pair = win.MaximizeMinimizeButton
    if type(pair) ~= "table" then return end
    local close = type(win.CloseButton) == "table" and win.CloseButton or nil
    SkinSizeButton(pair.MinimizeButton, "minus", close)
    SkinSizeButton(pair.MaximizeButton, "max", close)
end

-------------------------------------------------------------------------------
-- The spellbook entries, headers and page keys
-------------------------------------------------------------------------------

-- The book's pages are a PagedContent frame: its two views hold pooled frames (a SpellBookItemTemplate entry: Backplate, a
-- TextContainer with Name, SubName and RequiredLevel, and a Button with the icon, an icon frame and the trainable art; a
-- SpellBookHeaderTemplate header). A pooled frame is met once (weak table) and repainted by a post-hook on its own UpdateVisuals,
-- the stock code's one repaint of an entry.

local ENTRY = { CUT = 6, PAD = 2, OVER = 6, W = 220, H = 60 }
local ENTRY_BUTTON_ART = { "Border", "TrainableBackplate", "TrainableShadow", "BorderSheen", "IconHighlight" }

local function Flag(v) return Plain(v) == true end

-- learned, passive, trainable (learnable at a trainer now) and level locked (unlearned and not trainable), read from the fields the
-- stock code writes on the entry; a value the client keeps secret reads as plain false.
local function EntryState(item)
    local info = Plain(item.spellBookItemInfo)
    local passive = type(info) == "table" and Flag(info.isPassive)
    local unlearned, trainable = Flag(item.isUnlearned), Flag(item.isTrainable)
    return { unlearned = unlearned, trainable = trainable, passive = passive, locked = unlearned and not trainable }
end

local function PaintEntry(item)
    local rec = S.items[item]
    if not rec then return end
    local st = EntryState(item)
    local hover = rec.state and rec.state.hover
    local edge, edgeAlpha, fill, fillAlpha = C.violet, 0.6, C.ink, 0.85
    if st.trainable then edge, edgeAlpha = C.pink, 1
    elseif st.locked then edge, edgeAlpha, fillAlpha = C.dim, 0.9, 0.55
    elseif st.passive then edge, edgeAlpha = C.cyan, 0.6 end
    if hover then fill, fillAlpha, edgeAlpha = Kit.Mix(C.ink, edge, 0.22), 1, 1 end
    Kit.PaintPlate(rec.plate, fill, fillAlpha, edge, edgeAlpha, 1)
    rec.colors.name = st.trainable and C.pink or (st.locked and C.muted or C.text)
    rec.colors.sub = C.muted
    rec.colors.req = st.trainable and C.pink or C.amber
    for _, apply in pairs(rec.pins) do apply() end
end

-- The card is the entry's rect, PAD physical pixels in on the top, right and bottom so two neighbours never share an edge, and
-- OVER pixels out on the left, so the icon (the stock code seats it flush at the entry's left edge) has a margin inside the card.
-- Re-seated when the entry's pixel size is not the one it was seated at (a change of scale).
local function SeatEntry(item, rec)
    local w, h = Kit.SizePx(item)
    w, h = w or ENTRY.W, h or ENTRY.H
    if rec.w == w and rec.h == h then return end
    rec.w, rec.h = w, h
    local pad, over = ENTRY.PAD, ENTRY.OVER
    local x, y, pw, ph = -over, pad, w + over - pad, h - 2 * pad
    Kit.Place(rec.plate.fill, item, x, y, pw, ph)
    Kit.Place(rec.plate.ring, item, x, y, pw, ph)
    if rec.plate.ring2 then Kit.Place(rec.plate.ring2, item, x + 1, y + 1, pw - 2, ph - 2) end
end

local function BuildEntry(item, btn)
    HeldArt.Hold(item.Backplate)
    for _, key in ipairs(ENTRY_BUTTON_ART) do HeldArt.Hold(btn[key]) end
    local w, h = Kit.SizePx(item)
    local rec = { plate = Kit.Plate(item, ENTRY.CUT, (w or ENTRY.W) + ENTRY.OVER - ENTRY.PAD, (h or ENTRY.H) - 2 * ENTRY.PAD), colors = {}, pins = {} }
    S.items[item] = rec
    SeatEntry(item, rec)
    local host = item.TextContainer or item
    for _, spec in ipairs({ { "Name", 14, "name" }, { "SubName", 11, "sub" }, { "RequiredLevel", 11, "req" } }) do
        local fs = item[spec[1]]
        if type(fs) == "table" then
            Kit.RestyleLabel(fs, host, spec[2], C.text)
            local key = spec[3]
            rec.pins[key] = Follow(fs, function() return rec.colors[key] end)
        end
    end
    -- the card follows the icon's hover (that is the stock widget under the hand), and the stock repaint of the entry
    rec.state = Kit.Track(btn, function() PaintEntry(item) end)
    Kit.HookFunc(item, "UpdateVisuals", function() SeatEntry(item, rec); PaintEntry(item) end)
    PaintEntry(item)
    return rec
end

-- An entry is built once; the slot on its icon button is asked for on every pass until the shared slot layer (Quest.lua, loaded
-- after this file) answers: the icon button is the slot, with the stock art held, the cut plate, the quality-less slot layer (hover
-- brackets, cooldown drain) and the icon seated.
local function SkinEntry(item)
    local btn = item.Button
    if type(btn) ~= "table" then return end
    local rec = S.items[item] or BuildEntry(item, btn)
    if rec.slot then return end
    local Q = FS.QuestSkin
    if Q and Q.SquareSlot then
        Q.SquareSlot(btn)
        rec.slot = true
    end
end

local function SkinHeader(head)
    if S.heads[head] then return end
    S.heads[head] = true
    HeldArt.Hold(head.Backplate)
    HeldArt.Hold(head.Border)
    if head.Border then Rule(head, head.Border, "h", C.violet, 0.8) end
    if head.Text then Kit.RestyleLabel(head.Text, head, 16, C.text); Char.PinColor(head.Text, C.text) end
end

local function IsEntry(f)
    return type(f.Button) == "table" and type(f.TextContainer) == "table" and type(f.Button.Icon) == "table"
end

local function IsHeader(f)
    return f.Button == nil and type(f.Text) == "table" and type(f.Backplate) == "table" and type(f.Border) == "table"
end

-- Every entry and header the two views hold now: through the paged frame's own ForEachFrame and by the views' children (the
-- second covers a client where the first is missing; a frame met twice is skipped by the weak tables).
local function PageFrames(paged)
    local out = {}
    if type(paged.ForEachFrame) == "function" then pcall(paged.ForEachFrame, paged, function(f) out[#out + 1] = f end) end
    for _, key in ipairs({ "View1", "View2" }) do
        for _, f in ipairs(List(paged[key], "GetChildren")) do out[#out + 1] = f end
    end
    return out
end

local function SkinPages(paged)
    for _, f in ipairs(PageFrames(paged)) do
        if type(f) == "table" then
            if IsEntry(f) then Step("entry", SkinEntry, f) elseif IsHeader(f) then Step("header", SkinHeader, f) end
        end
    end
end

-- The page keys are Quest.lua's cut keys (resolved now: Quest.lua loads after this file); the stock "Page 1/3" text goes mono.
local function SkinPaging(paging)
    if type(paging) ~= "table" then return end
    local Q = FS.QuestSkin
    if Q and Q.PagerKey then
        Q.PagerKey(paging.PrevPageButton, "<")
        Q.PagerKey(paging.NextPageButton, ">")
    end
    if type(paging.PageText) == "table" then
        Kit.RestyleLabel(paging.PageText, paging, 13, C.text)
        Char.PinColor(paging.PageText, C.text)
    end
end

local PAGED_REFRESH = { "DisplayViewsForCurrentPage", "OnPageChanged", "SetDataProvider", "SetViewsPerPage" }

local function SkinPaged(book)
    local paged = book.PagedSpellsFrame
    if type(paged) ~= "table" then return end
    if not S.books[paged] then
        S.books[paged] = true
        for _, m in ipairs(PAGED_REFRESH) do Kit.HookFunc(paged, m, function() Kit.Later(function() SkinPages(paged) end) end) end
    end
    Step("paging", SkinPaging, paged.PagingControls)
    SkinPages(paged)
end

-------------------------------------------------------------------------------
-- The spellbook
-------------------------------------------------------------------------------

local BOOK_KEEP = { "rotationhelper", "Tab%-Frame" }

local function IsBookArt(atlas)
    if not atlas:find("^spellbook%-") then return false end
    for _, p in ipairs(BOOK_KEEP) do if atlas:find(p) then return false end end
    return true
end

local function HoldBookArt(frame, depth)
    if type(frame) ~= "table" or depth > 7 then return end
    for _, region in ipairs(List(frame, "GetRegions")) do
        local kind = Try(region.GetObjectType, region)
        if kind == "Texture" then
            local atlas = AtlasOf(region)
            if atlas and IsBookArt(atlas) then HeldArt.Hold(region) end
        elseif kind == "FontString" then
            -- the pages were written for parchment: dark text is lifted to the light text colour, state colours pass through
            pcall(PanelSkins.RetintDarkText, region, C.text)
        end
    end
    for _, child in ipairs(List(frame, "GetChildren")) do
        if type(child) == "table" and child.Track == nil then HoldBookArt(child, depth + 1) end
    end
end

-- The names the book's own refresh runs under (SpellBookFrameMixin: UpdateAllSpellData, UpdateDisplayedSpells, OnActiveCategoryChanged),
-- and older guesses kept for a client that names them differently.
local BOOK_REFRESH = { "UpdateAllSpellData", "UpdateDisplayedSpells", "OnActiveCategoryChanged", "UpdateDisplay", "Update", "UpdateTabs", "DisplayPage", "SetCategory", "RefreshDisplay" }

local function RefreshBook(book)
    HoldBookArt(book, 0)
    SkinPaged(book)
end

local function SkinBook(book)
    if type(book) ~= "table" then return end
    for _, key in ipairs({ "BookBGHalved", "BookBGLeft", "BookBGRight", "BookCornerFlipbook" }) do HeldArt.Hold(book[key]) end
    if not S.books[book] then
        S.books[book] = true
        local under = book:CreateTexture(nil, "BACKGROUND", nil, -6)
        under:SetAllPoints(book)
        under:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.55)
        for _, m in ipairs(BOOK_REFRESH) do Kit.HookFunc(book, m, function() Kit.Later(function() Step("book", RefreshBook, book) end) end) end
        Kit.HookScript(book, "OnShow", function() Kit.Later(function() Step("book", RefreshBook, book) end) end)
    end
    -- the category tabs keep their STUwave plate; the stock gold square frame behind each icon is held
    local tabs = book.tabSystem
    for _, tab in ipairs(List(tabs, "GetChildren")) do
        for _, key in ipairs({ "SquareBackground", "SquareBackgroundActive", "SquareBackgroundActiveGlow" }) do HeldArt.Hold(tab[key]) end
    end
    RefreshBook(book)
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

function Tal.Refresh()
    if not S.done then return end
    local win = _G.PlayerSpellsFrame
    if not win then return end
    Step("size", SkinSizeButtons, win)
    if win.TalentsFrame then Step("talents", SkinTalents, win.TalentsFrame) end
    if win.SpellBookFrame then Step("book", SkinBook, win.SpellBookFrame) end
end

local function Relayout()
    for _, rec in ipairs(S.rules) do rec.apply() end
    for _, apply in ipairs(S.fits) do pcall(apply) end
    Tal.Layout()
end

local TALENT_REFRESH = { "UpdateTreeInfo", "UpdateInspecting", "RefreshAllData", "ReleaseAllTalentButtons", "UpdateAll", "LoadTalentTree" }

local function Build()
    local win = _G.PlayerSpellsFrame
    if not win or S.done then return end
    S.done = true
    win.fsTalentsSkin = true
    local talents = win.TalentsFrame
    if talents then
        for _, m in ipairs(TALENT_REFRESH) do Kit.HookFunc(talents, m, function() Kit.Later(Tal.Refresh) end) end
        Kit.HookScript(talents, "OnShow", function() Kit.Later(Tal.Refresh) end)
        Kit.HookScript(talents, "OnSizeChanged", function() Step("layout", Tal.Layout) end)
    end
    Kit.HookScript(win, "OnShow", function() Kit.Later(Tal.Refresh) end)
    Kit.OnReseat(function() Relayout(); Tal.Refresh() end)
    Tal.Refresh()
end

-- Module power: this listener starts only with the Window skins switch on.
PanelSkins.WhenSkinsOn(function()
    local watcher = CreateFrame("Frame")
    for _, event in ipairs({ "TRAIT_CONFIG_UPDATED", "TRAIT_TREE_CURRENCY_INFO_UPDATED", "PLAYER_TALENT_UPDATE", "ACTIVE_PLAYER_SPECIALIZATION_CHANGED" }) do
        pcall(watcher.RegisterEvent, watcher, event)
    end
    watcher:SetScript("OnEvent", function()
        if not S.done then return end
        -- A closed window catches up in its OnShow hook; the refresh walks every talent node (2026-11-24 hitch audit).
        local win = _G.PlayerSpellsFrame
        if not (win and win:IsShown()) then return end
        Kit.Later(Tal.Refresh)
    end)
end)

PanelSkins.RegisterInspect("Talents", { { name = "PlayerSpellsFrame", guard = "fsTalentsSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
