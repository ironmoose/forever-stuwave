-- Forever STUwave: ButtonSkins
-- The STUwave close button (a 6 x 6 pixel X on a small cut plate) and, below it, the text button, drawn
-- ON Blizzard's own buttons. Blizzard's art is held invisible (FS.HeldArt); the plate, ring, halo and
-- glyph are textures added to the button, and its label's font objects are our own.
--
-- Skin only. Nothing here writes a script handler, an attribute or the enabled state, so every button
-- keeps its own click path (Log Out, Exit Game and Options among them); the one geometry write, the
-- X's size and seat, is skipped for a protected button in combat. State is kept in weak-keyed tables,
-- never as fields on a Blizzard frame, so a pooled button that is recycled in a secure call chain is not
-- tainted by a field we wrote.
--
-- One state vocabulary for both (the ConfigWindow convention, the console keys' halo): hover washes the
-- face 16% toward the ring colour and takes the ring to full alpha, pressed washes 32%, disabled is the
-- whole piece at 0.4 and takes no hover or press. Design study: the close-button mockup of 2026-10-21.

local _, FS = ...
local Theme = FS.Theme

local ButtonSkins = {}
FS.ButtonSkins = ButtonSkins

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local GLOW_ROUND_TEXTURE = MEDIA .. "glow_round.tga"

local WHITE = { 1, 1, 1, 1 }

-- The close button, in UI units (the glyph is in physical pixels): a 14 x 14 plate with a 3 unit chamfer at
-- the two cut corners, seated 5 in and 3 down from the panel's top-right corner so it sits inside the border
-- and inside the 18 unit title band, a hit rect 3 wider each side and below and 2 above, and a 6 x 6 pixel X.
local X = {
    PLATE = 14, CHAMFER = 3, GLYPH = 6, SEAT_R = 5, SEAT_T = 3, DISC = 12,
    HIT = { -3, -3, -2, -3 },
}
ButtonSkins.X = X

-- Per state: ring alpha, halo alpha, face wash toward the ring colour, label/glyph lift toward white,
-- glow behind the glyph, and the alpha the whole piece is drawn at.
local STATES = {
    normal   = { ring = 0.70, halo = 0.35, wash = 0,    lift = 0,    glow = 0,    al = 1 },
    hover    = { ring = 1.00, halo = 0.70, wash = 0.16, lift = 0.12, glow = 0.45, al = 1 },
    pressed  = { ring = 1.00, halo = 0.50, wash = 0.32, lift = 0.40, glow = 0.30, al = 1 },
    disabled = { ring = 0.70, halo = 0,    wash = 0,    lift = 0,    glow = 0,    al = 0.4 },
}

local parts = setmetatable({}, { __mode = "k" })  -- button -> its skin pieces and state

function ButtonSkins.Parts(button)
    return parts[button]
end

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

-- The state a button is drawn in. A disabled button takes no hover or press (motion scripts still fire on one).
local function StateName(button, p)
    if type(button.IsEnabled) == "function" and not button:IsEnabled() then return "disabled" end
    if p.pressed then return "pressed" end
    if p.hover then return "hover" end
    return "normal"
end

-------------------------------------------------------------------------------
-- Pixels
-------------------------------------------------------------------------------

-- Physical pixels per UI unit at `frame`; 1 when the client will not say.
local function PixelsPerUnit(frame)
    local helpers = FS.FrameHelpers
    local ppu = helpers and helpers.PixelsPerUnit and helpers.PixelsPerUnit(frame)
    if type(ppu) == "number" and ppu > 0 then return ppu end
    return 1
end

-- An even pixel count for `units`, so a glyph of even size centres on a pixel edge.
local function EvenPixels(units, es)
    local n = math.max(2, math.ceil(units * es - 1e-6))
    if n % 2 == 1 then n = n + 1 end
    return n
end

local function RoundPx(units, es)
    return math.floor(units * es + 0.5) / es
end

local function Snap(texture)
    if texture and texture.SetSnapToPixelGrid then
        pcall(texture.SetSnapToPixelGrid, texture, true)
        if texture.SetTexelSnappingBias then pcall(texture.SetTexelSnappingBias, texture, 0) end
    end
end

-- The close X: two one pixel diagonals of an even n x n square (they never share a pixel). { x, y } cells
-- from the glyph's top left.
function ButtonSkins.XCells(n)
    local cells = {}
    for k = 0, n - 1 do
        cells[#cells + 1] = { k, k }
        cells[#cells + 1] = { n - 1 - k, k }
    end
    return cells
end

-- True when the button is protected AND we are in combat: its size, anchors and hit rect are off limits.
local function Locked(button)
    if not (InCombatLockdown and InCombatLockdown()) then return false end
    if type(button.IsProtected) ~= "function" then return false end
    local ok, protected = pcall(button.IsProtected, button)
    return ok and protected and true or false
end

-------------------------------------------------------------------------------
-- Hooks shared by both skins
-------------------------------------------------------------------------------

-- Post-hooks the scripts a button's look follows. HookScript throws for a script the object does not have,
-- so each is its own pcall; the primary handlers (Blizzard's OnClick above all) are never replaced.
local function HookScripts(button, p, paint, onShow)
    local function hook(script, fn)
        if type(button.HookScript) == "function" then pcall(button.HookScript, button, script, fn) end
    end
    hook("OnEnter", function(self) p.hover = true; paint(self) end)
    hook("OnLeave", function(self) p.hover, p.pressed = false, false; paint(self) end)
    hook("OnMouseDown", function(self) p.pressed = true; paint(self) end)
    hook("OnMouseUp", function(self) p.pressed = false; paint(self) end)
    hook("OnHide", function() p.hover, p.pressed = false, false end)
    hook("OnShow", function(self) if onShow then onShow(self) end; paint(self) end)
    hook("OnEnable", paint)
    hook("OnDisable", paint)
end

-- The textures an earlier Theme.SkinButton call drew on a button (ring and glow): not Blizzard's, so not held.
local function OwnPieces(button)
    local keep = {}
    local skin = button.fsSkin
    if type(skin) == "table" then
        if skin.glow then keep[skin.glow] = true end
        if skin.border and skin.border.ring then keep[skin.border.ring] = true end
    end
    return keep
end

-- Ring, halo and face of a button at chamfer `c`: the Theme.SkinButton ring and glow (reused when an earlier
-- call drew them) plus a cut slice fill under them. Returns skin, face, flatFace.
local function BuildPlate(button, accent, chamfer)
    local skin = Theme.SkinButton(button, { borderColor = accent, chamfer = chamfer, glowAlpha = STATES.normal.halo })
    local face = Theme.AddCutSliceFill(button, Theme.COLOR_BUTTON_INK, chamfer)
    local flat = false
    if not face then
        -- "round" corners, or a client that cannot slice a texture: a flat fill is what is left
        face = button:CreateTexture(nil, "BACKGROUND")
        face:SetAllPoints(button)
        flat = true
    end
    return skin, face, flat
end

local function PaintPlate(p, accent, S)
    local face = Mix(Theme.COLOR_BUTTON_INK, accent, S.wash)
    if p.flat then
        p.face:SetColorTexture(face[1], face[2], face[3], S.al)
    else
        p.face:SetVertexColor(face[1], face[2], face[3], S.al)
    end
    p.ring:SetVertexColor(accent[1], accent[2], accent[3], S.ring * S.al)
    p.halo:SetVertexColor(accent[1], accent[2], accent[3], S.halo * S.al)
end

-------------------------------------------------------------------------------
-- The close button (the X)
-------------------------------------------------------------------------------

local function PaintX(button)
    local p = parts[button]
    if not p then return end
    local S = STATES[StateName(button, p)]
    local pink = Theme.COLOR_HEALTH
    PaintPlate(p, pink, S)
    local g = Mix(pink, WHITE, S.lift)
    for i = 1, #p.glyph do p.glyph[i]:SetColorTexture(g[1], g[2], g[3], S.al) end
    p.disc:SetVertexColor(pink[1], pink[2], pink[3], S.glow * S.al)
    p.disc:SetShown(S.glow > 0)
end

-- Size, seat and glyph. The size and seat are skipped for a protected button in combat; the glyph is then
-- centred on whatever size the button has.
local function SeatX(button, p)
    local es = PixelsPerUnit(button)
    if not Locked(button) and p.es ~= es then
        local size = EvenPixels(X.PLATE, es) / es
        button:SetSize(size, size)
        button:ClearAllPoints()
        button:SetPoint("TOPRIGHT", p.anchor, "TOPRIGHT", -RoundPx(X.SEAT_R, es), -RoundPx(X.SEAT_T, es))
        if button.SetHitRectInsets then button:SetHitRectInsets(X.HIT[1], X.HIT[2], X.HIT[3], X.HIT[4]) end
        p.es = es
    end
    local bw = math.floor((button:GetWidth() or 0) * es + 0.5)
    local bh = math.floor((button:GetHeight() or 0) * es + 0.5)
    local key = bw .. ":" .. bh .. ":" .. es
    if p.glyphKey == key then return end
    p.glyphKey = key
    local px = 1 / es
    local mx, my = math.floor((bw - X.GLYPH) / 2), math.floor((bh - X.GLYPH) / 2)
    for i, cell in ipairs(ButtonSkins.XCells(X.GLYPH)) do
        local t = p.glyph[i]
        t:ClearAllPoints()
        t:SetSize(px, px)
        t:SetPoint("TOPLEFT", button, "TOPLEFT", (mx + cell[1]) * px, -(my + cell[2]) * px)
    end
end

-- Skins an icon-only close button as the STUwave X: its Blizzard art held hidden, a 14 unit cut plate with a
-- pink ring and halo, a 6 x 6 pixel X. opts.anchor is the frame it is seated to (default its parent).
-- Idempotent; returns the skin pieces ({ face, ring, halo, disc, glyph }).
function ButtonSkins.SkinCloseButton(button, opts)
    if type(button) ~= "table" or type(button.CreateTexture) ~= "function" then return nil end
    if parts[button] then return parts[button] end
    opts = opts or {}

    if FS.HeldArt then FS.HeldArt.HoldButton(button, OwnPieces(button)) end

    local p = { hover = false, pressed = false, glyph = {} }
    parts[button] = p
    p.anchor = opts.anchor or (button.GetParent and button:GetParent()) or UIParent

    local skin, face, flat = BuildPlate(button, Theme.COLOR_HEALTH, X.CHAMFER)
    p.face, p.flat, p.halo, p.ring = face, flat, skin.glow, skin.border.ring

    p.disc = button:CreateTexture(nil, "OVERLAY", nil, 2)
    p.disc:SetTexture(GLOW_ROUND_TEXTURE)
    p.disc:SetBlendMode("ADD")
    p.disc:SetSize(X.DISC, X.DISC)
    p.disc:SetPoint("CENTER", button, "CENTER", 0, 0)

    for i = 1, #ButtonSkins.XCells(X.GLYPH) do
        local t = button:CreateTexture(nil, "OVERLAY", nil, 3)
        Snap(t)
        p.glyph[i] = t
    end

    SeatX(button, p)
    PaintX(button)
    HookScripts(button, p, PaintX, function(self) SeatX(self, p) end)
    return p
end

-- A new close button on `parent`, seated top right, calling `onClick` (the parent's own Hide, usually).
function ButtonSkins.NewCloseButton(parent, onClick)
    local button = CreateFrame("Button", nil, parent)
    if button.RegisterForClicks then button:RegisterForClicks("LeftButtonUp") end
    if onClick then button:SetScript("OnClick", onClick) end
    ButtonSkins.SkinCloseButton(button, { anchor = parent })
    return button
end

-------------------------------------------------------------------------------
-- Which button of a panel is the X
-------------------------------------------------------------------------------

local function IsButton(obj)
    if type(obj) ~= "table" or type(obj.GetObjectType) ~= "function" or type(obj.HookScript) ~= "function" then
        return false
    end
    local ok, kind = pcall(obj.GetObjectType, obj)
    return ok and kind == "Button"
end

-- A button with a label is a text button, whatever it is called: Blizzard's SettingsPanel.CloseButton is the
-- bottom "Close" button, its real X is ClosePanelButton.
local function HasLabel(button)
    local function labelled(text)
        if text == nil then return false end
        if FS.IsSecret and FS.IsSecret(text) then return true end
        return type(text) == "string" and text ~= ""
    end
    if type(button.GetText) == "function" and labelled(button:GetText()) then return true end
    local fs = type(button.GetFontString) == "function" and button:GetFontString()
    return (fs and type(fs.GetText) == "function" and labelled(fs:GetText())) or false
end

-- The close-type buttons of `frame`, each { button, kind = "x" | "text" }: ClosePanelButton, CloseButton, the
-- border frame's CloseButton and the <Name>CloseButton / <Name>ClosePanelButton globals, a button reachable
-- two ways listed once.
function ButtonSkins.ResolveCloseButtons(frame)
    local out, seen = {}, {}
    if type(frame) ~= "table" then return out end
    local function add(button)
        if IsButton(button) and not seen[button] then
            seen[button] = true
            out[#out + 1] = { button = button, kind = HasLabel(button) and "text" or "x" }
        end
    end
    add(frame.ClosePanelButton)
    add(frame.CloseButton)
    if type(frame.BorderFrame) == "table" then add(frame.BorderFrame.CloseButton) end
    local name = type(frame.GetName) == "function" and frame:GetName()
    if type(name) == "string" and name ~= "" then
        add(_G[name .. "CloseButton"])
        add(_G[name .. "ClosePanelButton"])
    end
    return out
end

-- Skins the close controls of a panel: the icon-only X as the STUwave X seated to the panel, a labelled
-- Close as a text button. Called by Theme.SkinPanel.
function ButtonSkins.SkinFrameClose(frame)
    for _, found in ipairs(ButtonSkins.ResolveCloseButtons(frame)) do
        if found.kind == "x" then
            ButtonSkins.SkinCloseButton(found.button, { anchor = frame })
        elseif ButtonSkins.SkinTextButton then
            ButtonSkins.SkinTextButton(found.button)
        end
    end
end
