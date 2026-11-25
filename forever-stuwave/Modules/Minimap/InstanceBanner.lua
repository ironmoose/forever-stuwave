-- Forever STUwave: Instance banner
-- The difficulty banner that hangs off the minimap inside a dungeon or raid (MinimapCluster.InstanceDifficulty) wore Blizzard's gold
-- guild-banner shield over the STUwave map body. It now wears a cut plate of the body's own ink and edge: a dark fill, a one pixel edge
-- cut at the top left and bottom right like the key row's body, and the edge tells the difficulty the way the keys' LEDs tell their job
-- (cyan normal, amber heroic or a timed run, pink mythic).
--
-- Skin only. The banner keeps its rect, its anchors, its scripts (the difficulty tooltip), its events and every texture that carries
-- information: the difficulty glyph, the guild emblem and the group size. What goes is the shield: the Background and Border of the
-- three content modes (Default, Guild, ChallengeMode) are held at alpha 0 (FS.HeldArt), and the group size is restyled in place in the
-- mono face. The plate is regions of each content frame itself (a child frame would draw over the glyph), under the stock glyph, so it
-- shows and hides with the mode Blizzard shows. Nothing is moved, resized, reparented or attributed.
--
-- Not in the approved minimap mockup (it has no banner; the shape is the key row's, not a new design). Structure: the retail 12.1.0
-- Blizzard_FrameXML/InstanceDifficulty.xml (InstanceDifficultyTemplate: Default, Guild and ChallengeMode frames in the ContentModes
-- array; the 16001 inspect dump has the frame at MinimapCluster.InstanceDifficulty, 35 x 36). Every field is feature-detected.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit
if not (Theme and HeldArt and Kit and PanelSkins and PanelSkins.RequireExport(
    Theme.AddCutSliceFill and Theme.ApplyMono and Theme.SnapCut,
    "InstanceBanner.lua disabled: FS.Theme chrome helpers, FS.HeldArt or FS.ControlKit missing")) then return end

local Banner = {}
FS.InstanceBanner = Banner

local C = {
    cyan = Theme.COLOR_POWER, amber = Theme.COLOR_AMBER, pink = Theme.COLOR_HEALTH,
    text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    plate = { 0.043, 0.024, 0.094 },   -- the minimap body's plate (#0b0618)
}

-- Physical pixels: the plate stands 2 px inside the stock rect, cut like the body (6), the group size is 12 px mono.
local G = { INSET = 2, CHAMFER = 6, FILL_ALPHA = 0.94, TEXT_PX = 12, FALLBACK_W = 42, FALLBACK_H = 44 }
Banner.GEOM = G

local S = { plates = setmetatable({}, { __mode = "k" }), hooked = setmetatable({}, { __mode = "k" }), done = false }
Banner.state = S

local function Try(fn, ...) return Kit.Try(fn, ...) end

local function Shown(region)
    return type(region) == "table" and Kit.Plain(Try(region.IsShown, region)) == true
end

-- The three content modes of the banner, from the ContentModes array and then by name.
local function ContentFrames(root)
    local list, seen = {}, {}
    local function add(frame)
        if type(frame) == "table" and not seen[frame] and Kit.TypeOf(frame) == "Frame" then
            seen[frame] = true
            list[#list + 1] = frame
        end
    end
    if type(root.ContentModes) == "table" then
        for _, frame in ipairs(root.ContentModes) do add(frame) end
    end
    add(root.Default); add(root.Guild); add(root.ChallengeMode)
    return list
end

-- The edge says the difficulty: pink mythic, amber heroic or a timed run, cyan the rest. A group (guild) banner keeps its
-- difficulty glyphs on its Instance row.
local function EdgeFor(root, frame)
    local face = type(frame.Instance) == "table" and frame.Instance or frame
    if Shown(face.MythicTexture) then return C.pink end
    if Shown(face.HeroicTexture) or Shown(face.ChallengeModeTexture) or frame == root.ChallengeMode then return C.amber end
    return C.cyan
end

local function Paint(root, frame)
    local plate = S.plates[frame]
    if plate then Kit.PaintPlate(plate, C.plate, G.FILL_ALPHA, EdgeFor(root, frame), 1, 1) end
end

-- The plate's two regions fill the stock rect less the inset, at the pixel scale of the frame.
local function Seat(frame, plate)
    local inset = Kit.U(frame, G.INSET)
    for _, region in ipairs({ plate.fill, plate.ring }) do
        region:ClearAllPoints()
        region:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
        region:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -inset, inset)
    end
end

local function SkinFrame(root, frame)
    if S.plates[frame] then return end
    HeldArt.Hold(frame.Background)
    HeldArt.Hold(frame.Border)
    local w, h = Kit.SizePx(frame)
    local plate = Kit.Plate(frame, G.CHAMFER, (w or G.FALLBACK_W) - 2 * G.INSET, (h or G.FALLBACK_H) - 2 * G.INSET)
    Kit.Snap(plate.fill); Kit.Snap(plate.ring)
    S.plates[frame] = plate
    Seat(frame, plate)
    -- the group size, on the difficulty row of a guild banner or on the frame itself
    local face = type(frame.Instance) == "table" and frame.Instance or frame
    Kit.RestyleLabel(face.Text, frame, G.TEXT_PX, C.text)
    Kit.HookScript(frame, "OnShow", function() Paint(root, frame) end)
    Paint(root, frame)
end

local function PaintAll(root)
    for _, frame in ipairs(ContentFrames(root)) do Paint(root, frame) end
end

local function Reseat()
    for frame, plate in pairs(S.plates) do Seat(frame, plate) end
end

function Banner.Build()
    local cluster = _G.MinimapCluster
    local root = type(cluster) == "table" and cluster.InstanceDifficulty
    if type(root) ~= "table" then return false end
    if S.done == root then return true end
    S.done = root
    for _, frame in ipairs(ContentFrames(root)) do
        local ok, err = pcall(SkinFrame, root, frame)
        if not ok then Kit.Fail("instance banner", err) end
    end
    if not S.hooked[root] then
        S.hooked[root] = true
        -- Blizzard re-decides the mode and re-points the difficulty glyph in Update (and in the deferred one a group event arms)
        Kit.HookFunc(root, "Update", function() PaintAll(root) end)
        Kit.HookFunc(root, "SetFlipped", function() PaintAll(root) end)
    end
    return true
end

-- Module power (Core/ModuleSwitch.lua): the banner is part of the Minimap switch. Off, Blizzard's difficulty banner keeps
-- its own shield: nothing here is hooked, held or drawn on it. Banner.Build stays defined; nothing calls it.
local function Start()
    Kit.OnReseat(Reseat)
    PanelSkins.DeferCombat(Banner.Build, "m.mini")
    local watch = CreateFrame("Frame")
    watch:RegisterEvent("PLAYER_ENTERING_WORLD")
    watch:SetScript("OnEvent", function() Kit.Defer(Banner.Build) end)
end
local MS = FS.ModuleSwitch
if MS then MS.WhenOn("m.mini", Start) else Start() end
