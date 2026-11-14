-- Forever STUwave: Group window skin kit
-- The small pieces the Social, Guild, Chat settings and PvP skins (Social.lua, Guild.lua, ChatSettings.lua, PvP.lua) share, so
-- each of those files is only about its own window: a logged pcall step, a texture region hold, a mono label, a square key,
-- a column header, a left edge LED bar and a rule, all drawn in the vocabulary of the approved mockup
-- (mockups/social-group-2026-11-12.html): ink cards with a violet or dim edge, cyan for live and selected, pink for leave and
-- danger, amber for attention, mono text.
--
-- Skin only, as in Commerce.lua: Blizzard's own art is held at alpha 0 (FS.HeldArt) and ours is drawn in textures we add to the
-- widget, so no script, attribute, parent, size or anchor of a Blizzard object is ever written. The square key and the column
-- header HOLD THE STOCK ART FIRST and only then add their box: HeldArt.HoldButton holds every region the button has at that
-- moment, and a box made before it would be held invisible with the rest (Char.SkinSquare holds first too since the fix of its
-- box-held bug, so the two now agree).

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.PaintBox and Char.List and PanelSkins.RequireExport(
    Theme.ApplyMono and Theme.AddPanelChrome,
    "GroupKit.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local G = {}
FS.GroupSkin = G

G.C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 }, band = Theme.COLOR_CTRL_BAND or { 0.102, 0.051, 0.173 },
    row = { 0.059, 0.031, 0.125 }, gold = Theme.COLOR_GOLD or { 1, 0.824, 0.247 },
}
local C = G.C

local Try, Plain, List = Kit.Try, Kit.Plain, Char.List

function G.Weak() return setmetatable({}, { __mode = "k" }) end

-------------------------------------------------------------------------------
-- Plumbing
-------------------------------------------------------------------------------

local logged = {}

-- Runs `fn(...)` in a pcall; a failure is logged once per `tag:name` and never stops the pieces after it.
function G.Step(tag, name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[tag .. name] then
        logged[tag .. name] = true
        FS.LogDegradeOnce(tag .. ":" .. name, ("|cffff4488Forever STUwave|r: %s skin step '%s' failed: %s"):format(tag, name, tostring(err)))
    end
    return ok
end

function G.Region(frame, key)
    return type(frame) == "table" and type(frame[key]) == "table" and frame[key] or nil
end

-- A global frame by name, nil when this client has no such frame.
function G.Named(name)
    local f = _G[name]
    return type(f) == "table" and f or nil
end

-- Holds every texture region of `frame` (not its sub frames), except those in `keep` (a set keyed by region).
function G.HoldRegions(frame, keep)
    for _, region in ipairs(List(frame, "GetRegions")) do
        if not (keep and keep[region]) then HeldArt.Hold(region) end
    end
end

-- Holds the keyed art of `frame`: each key that names a texture is held, a key that names a frame is held as one.
function G.HoldKeys(frame, keys)
    if type(frame) ~= "table" then return end
    for _, key in ipairs(keys) do
        local part = frame[key]
        if type(part) == "table" then
            if Kit.TypeOf(part) == "Texture" then HeldArt.Hold(part) else Kit.HoldFrame(part) end
        end
    end
end

-- Restyles a stock label in mono and leaves its colour to the stock code (a class colour, a red state).
function G.Mono(fs, host, px, color)
    if type(fs) == "table" and Kit.TypeOf(fs) == "FontString" then Kit.RestyleLabel(fs, host, px, color or C.text) end
end

-- Runs `fn(row)` on every row of a ScrollBox now and after each update of it (rows are pooled; the hold and the box of a row
-- the pool already made stay, so `fn` must be idempotent). Nothing is written when the ScrollBox is not there.
function G.Rows(box, fn)
    if type(box) == "table" then Char.WatchRows(box, fn) end
end

-------------------------------------------------------------------------------
-- Edges: the left LED bar and a rule
-------------------------------------------------------------------------------

local rules = {}

local function Relayout()
    for _, rec in ipairs(rules) do rec.apply() end
end
Kit.OnReseat(Relayout)

-- A bar `w` pixels wide down the left edge of `host`, `inset` pixels in from its top and bottom, `x` pixels in from its left.
-- Returns the record; rec.t is the texture, rec.Paint(color, alpha) recolours it.
function G.Bar(host, color, w, inset, x)
    local t = host:CreateTexture(nil, "BORDER", nil, 7)
    local rec = { t = t, w = w or 3, inset = inset or 0, x = x or 0 }
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", host, "TOPLEFT", rec.x * u, -rec.inset * u)
        t:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", rec.x * u, rec.inset * u)
        t:SetWidth(rec.w * u)
    end
    function rec.Paint(c, a) t:SetColorTexture(c[1], c[2], c[3], a or c[4] or 1) end
    rec.Paint(color)
    rules[#rules + 1] = rec
    rec.apply()
    return rec
end

-- A one pixel line across `host`, `y` pixels from its top (negative: from its bottom), `inset` pixels in from each side.
function G.Rule(host, color, alpha, y, inset)
    local t = host:CreateTexture(nil, "BORDER", nil, 5)
    local rec = { t = t }
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        local edge = y >= 0 and "TOP" or "BOTTOM"
        t:SetPoint(edge .. "LEFT", host, edge .. "LEFT", (inset or 0) * u, -y * u)
        t:SetPoint(edge .. "RIGHT", host, edge .. "RIGHT", -(inset or 0) * u, -y * u)
        t:SetHeight(u)
    end
    t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
    rules[#rules + 1] = rec
    rec.apply()
    return t
end

-- A one pixel line through the vertical middle of `host`, `inset` pixels in from each side.
function G.MidRule(host, color, alpha, inset)
    local t = host:CreateTexture(nil, "BORDER", nil, 5)
    local rec = {}
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        t:SetPoint("LEFT", host, "LEFT", (inset or 0) * u, 0)
        t:SetPoint("RIGHT", host, "RIGHT", -(inset or 0) * u, 0)
        t:SetHeight(u)
    end
    t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
    rules[#rules + 1] = rec
    rec.apply()
    return t
end

-- An inset or well of the stock frames (InsetFrameTemplate, the column display, the guild pages): its nine slice frame, background and
-- border tiles held, so only our ring shows. Safe on a frame that has none of them.
function G.HoldInset(frame)
    if type(frame) ~= "table" then return end
    Kit.HoldFrame(frame.NineSlice)
    HeldArt.Hold(frame.Bg)
    HeldArt.Hold(frame.Background)
    G.HoldRegions(frame)
end

-------------------------------------------------------------------------------
-- Square key: a small button whose own icon is the picture
-------------------------------------------------------------------------------

local squares = G.Weak()
G.squares = squares

local function PaintSquare(btn)
    local s = squares[btn]
    if not s then return end
    local on = Kit.IsEnabled(btn)
    local hover = on and s.state and (s.state.hover or s.state.pressed)
    local sel = s.selected and s.selected() or false
    local edge = not on and C.dim or (sel and C.cyan or (hover and C.cyan or s.accent))
    Char.PaintBox(s.box, sel and C.band or C.ink, 1, edge, on and 1 or 0.6, (sel or hover) and 2 or 1)
    if s.icon and s.icon.SetVertexColor then
        local v = on and ((hover or sel) and 1 or 0.8) or 0.4
        pcall(s.icon.SetVertexColor, s.icon, v, v, v, 1)
    end
end

-- Skins `btn` in place as a square key. opts.icon is the button's own picture (kept, not held), opts.accent the idle edge colour
-- (violet by default), opts.selected a function that says it is the chosen one (a cyan edge and band). The stock art is held
-- FIRST and the box made after it. Returns the record.
function G.Square(btn, opts)
    if type(btn) ~= "table" or type(btn.CreateTexture) ~= "function" then return nil end
    if squares[btn] then return squares[btn] end
    opts = opts or {}
    HeldArt.HoldButton(btn, opts.icon and { [opts.icon] = true } or nil)
    local s = { box = Char.Box(btn, "BORDER"), icon = opts.icon, accent = opts.accent or C.violet, selected = opts.selected }
    squares[btn] = s
    s.state = Kit.Track(btn, PaintSquare)
    PaintSquare(btn)
    return s
end

G.PaintSquare = PaintSquare

-------------------------------------------------------------------------------
-- Column header: the sortable heading of a list
-------------------------------------------------------------------------------

local headers = G.Weak()
G.headers = headers

local function PaintHeader(btn)
    local s = headers[btn]
    if not s then return end
    local hover = s.state and (s.state.hover or s.state.pressed)
    Char.PaintBox(s.box, C.band, 1, hover and C.cyan or C.dim, 1, 1)
    if s.label then Kit.Recolor(s.label, hover and C.cyan or C.muted) end
end

-- Skins a stock column header button: its Left / Middle / Right art, nine slice frames and highlight held, a band box over the same rect, the
-- label in mono. Clicking, sorting and the arrow stay stock.
function G.Header(btn, px)
    if type(btn) ~= "table" or type(btn.CreateTexture) ~= "function" or headers[btn] then return nil end
    HeldArt.HoldButton(btn)
    for _, key in ipairs({ "Left", "Middle", "Right", "HighlightTexture" }) do HeldArt.Hold(btn[key]) end
    for _, key in ipairs({ "NormalNineSlice", "PushedNineSlice", "HighlightNineSlice", "CheckedNineSlice" }) do Kit.HoldFrame(btn[key]) end
    local s = { box = Char.Box(btn, "BORDER") }
    headers[btn] = s
    local label = type(btn.GetFontString) == "function" and Try(btn.GetFontString, btn) or btn.Text
    if type(label) == "table" then
        s.label = label
        G.Mono(label, btn, px or 11, C.muted)
    end
    s.state = Kit.Track(btn, PaintHeader)
    PaintHeader(btn)
    return s
end

G.PaintHeader = PaintHeader

-------------------------------------------------------------------------------
-- Card row: a pooled list row (or any frame) drawn as an ink card
-------------------------------------------------------------------------------

local cards = G.Weak()
G.cards = cards

local function PaintCard(host)
    local rec = cards[host]
    if not rec then return end
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    local lit = rec.selected or hover
    Char.PaintBox(rec.box, rec.selected and C.band or (rec.fill or C.row), 1, lit and rec.accent or C.dim, rec.edgeAlpha or 1, rec.selected and 2 or 1)
    if rec.led then rec.led.Paint(rec.ledColor and rec.ledColor() or rec.accent) end
end
G.PaintCard = PaintCard

-- Holds the keyed texture art of `frame` whose key matches one of `patterns` (a key that names a frame is held as a frame). The
-- stock art of a list row is told by its key (Background, Bg, Highlight, Selected ...); an icon or a label is never named so.
function G.HoldNamed(frame, patterns)
    if type(frame) ~= "table" then return end
    for key, part in pairs(frame) do
        if type(key) == "string" and type(part) == "table" and Kit.TypeOf(part) then
            for _, pattern in ipairs(patterns) do
                if key:find(pattern) then
                    if Kit.TypeOf(part) == "Texture" then HeldArt.Hold(part) else Kit.HoldFrame(part) end
                    break
                end
            end
        end
    end
end

G.ROW_ART = { "^Background", "^Bg$", "Highlight", "^Selected", "^Selection", "^Stripe", "^Texture$", "^Flash" }

-- Skins `host` as an ink card: the stock row art named by opts.hold (patterns, default G.ROW_ART) held, a box over its rect, a
-- violet edge that lights with opts.accent (cyan by default) on hover and when the stock code locks the highlight, an optional
-- LED bar down the left edge (opts.led, a colour or a function that returns one, read on every paint) and every label in mono.
-- Returns the record; call G.PaintCard(host) after a change of state it does not follow.
function G.Card(host, opts)
    if type(host) ~= "table" or type(host.CreateTexture) ~= "function" then return nil end
    if cards[host] then PaintCard(host) return cards[host] end
    opts = opts or {}
    G.HoldNamed(host, opts.hold or G.ROW_ART)
    local rec = { box = Char.Box(host, "BORDER"), accent = opts.accent or C.cyan, fill = opts.fill, edgeAlpha = opts.edgeAlpha }
    if opts.led then
        rec.led = G.Bar(host, C.dim, 3, 0)
        rec.ledColor = type(opts.led) == "function" and opts.led or function() return opts.led end
    end
    cards[host] = rec
    for _, region in ipairs(List(host, "GetRegions")) do
        if Kit.TypeOf(region) == "FontString" then G.Mono(region, host, opts.px or 11, C.text) end
    end
    rec.state = Kit.Track(host, PaintCard)
    Kit.HookFunc(host, "LockHighlight", function() rec.selected = true; PaintCard(host) end)
    Kit.HookFunc(host, "UnlockHighlight", function() rec.selected = false; PaintCard(host) end)
    PaintCard(host)
    return rec
end
