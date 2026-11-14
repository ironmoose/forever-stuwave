#!/usr/bin/env python3
"""Runs the real Modules/Minimap/InstanceBanner.lua headless against a mock MinimapCluster.InstanceDifficulty (tools/charskin_support.py).

Pinned: the stock gold shield of all three content modes (Default, Guild, ChallengeMode) is held at alpha 0 while every glyph, the
guild emblem and the group size stay; each mode wears a cut plate of ours made of regions of that content frame (no child frame, so
nothing draws over the glyph), standing 2 px inside the stock rect, re-seated when the pixel scale changes; the edge tells the
difficulty (cyan normal or a delve, amber heroic or a timed run, pink mythic) and follows the stock Update and SetFlipped; the group
size is mono at 12 px; no script or attribute is written on a Blizzard widget and no anchor, size or child of the banner changes;
nothing is built in combat, a banner that appears after load is built on PLAYER_ENTERING_WORLD, a missing frame is skipped quietly
and a second build adds nothing. Run `python3 tools/instancebanner-harness.py [--png debug/banner]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard

function AllObjects() return ALL end

local function centred(region, rel, w, h, y)
    region.w, region.h = w or region.w, h or region.h
    region.points[1] = { point = "CENTER", rel = rel, relPoint = "CENTER", x = 0, y = y or 0 }
    return region
end
-- the glyph stand-in: a path the renderer draws as a flat gold block
local function glyph(parent, key, w, h, y)
    local t = centred(tex(parent, nil, "ARTWORK"), parent, w, h, y)
    t.path = "Interface\\Icons\\banner_" .. key
    t.shown = false
    parent[key] = t
    return t
end
local function shield(frame, w, h)
    frame.Background = centred(tex(frame, nil, "BACKGROUND"), frame, w, h)
    frame.Border = centred(tex(frame, nil, "ARTWORK"), frame, w, h)
    for _, t in ipairs({ frame.Background, frame.Border }) do
        t.SetAtlas = function(self, atlas) self.atlas = atlas end
    end
end
local function text(parent, value)
    local fs = fstring(parent, nil, value or "", 11)
    fs.points[1] = { point = "CENTER", rel = parent, relPoint = "CENTER", x = 0, y = -10 }
    fs.justify = "CENTER"
    return fs
end

function BuildBlizzard()
    build()
    MinimapCluster = nil
    local cluster = blz("Frame", "MinimapCluster", UIParent, 70, 62, "TOPRIGHT", -40, -40)
    local root = blz("Frame", nil, cluster, 35.5, 36.5, "TOPRIGHT", -3, -3)
    cluster.InstanceDifficulty = root
    root.scripts.OnEnter = function() end
    root.scripts.OnLeave = function() end

    local def = blz("Frame", nil, root, 0, 0)
    def:SetAllPoints(root)
    shield(def, 34, 40)
    root.Default = def
    def.DifficultyTextures = {}
    for _, key in ipairs({ "NormalTexture", "HeroicTexture", "MythicTexture", "WalkInTexture" }) do
        def.DifficultyTextures[#def.DifficultyTextures + 1] = glyph(def, key, 16, 16, 5)
    end
    def.Text = text(def, "5")

    local guild = blz("Frame", nil, root, 0, 0)
    guild:SetAllPoints(root)
    shield(guild, 34, 40)
    root.Guild = guild
    guild.scripts.OnEnter = function() end
    guild.scripts.OnLeave = function() end
    guild.Emblem = centred(tex(guild, nil, "ARTWORK"), guild, 16, 16)
    guild.Emblem.path = "Interface\\GuildFrame\\GuildEmblems_01"
    guild.Emblem.points[1].y = 7
    local inst = blz("Frame", nil, guild, 23, 12, "BOTTOM", 0, 7)
    guild.Instance = inst
    inst.DifficultyTextures = {}
    for _, key in ipairs({ "NormalTexture", "HeroicTexture", "MythicTexture", "ChallengeModeTexture", "WalkInTexture" }) do
        inst.DifficultyTextures[#inst.DifficultyTextures + 1] = glyph(inst, key, 10, 10)
        inst.DifficultyTextures[#inst.DifficultyTextures].points[1] = { point = "LEFT", rel = inst, relPoint = "LEFT", x = 0, y = 0 }
    end
    inst.Text = text(inst, "25")
    inst.Text.points[1] = { point = "RIGHT", rel = inst, relPoint = "RIGHT", x = 0, y = 0 }

    local challenge = blz("Frame", nil, root, 0, 0)
    challenge:SetAllPoints(root)
    shield(challenge, 34, 40)
    root.ChallengeMode = challenge
    glyph(challenge, "ChallengeModeTexture", 14, 16).shown = true

    root.ContentModes = { def, guild, challenge }
    root.mode, root.diff, root.size = "default", "NormalTexture", 5
    function root:Update()
        local face = self.mode == "guild" and guild.Instance or def
        if self.mode == "default" or self.mode == "guild" then
            face.Text:SetText(self.size and tostring(self.size) or "")
            for _, t in ipairs(face.DifficultyTextures) do t:SetShown(t == face[self.diff]) end
        end
        def:SetShown(self.mode == "default")
        guild:SetShown(self.mode == "guild")
        challenge:SetShown(self.mode == "challenge")
    end
    function root:SetFlipped(flipped)
        for _, f in ipairs(self.ContentModes) do
            f.Background:SetAtlas(flipped and "background-bottom" or "background-top")
            f.Border:SetAtlas(flipped and "border-bottom" or "border-top")
        end
    end
    root:Update()
end
"""

H = Harness({"InstanceBanner": "Modules/Minimap/InstanceBanner.lua"}, BLIZZARD)
case = H.case

PRE = """
local B = FS.InstanceBanner
local S = B.state
local C = FS.Theme
local root = MinimapCluster.InstanceDifficulty
local def, guild, challenge = root.Default, root.Guild, root.ChallengeMode
local function same(a, b) return math.abs(a[1] - b[1]) < 0.01 and math.abs(a[2] - b[2]) < 0.01 and math.abs(a[3] - b[3]) < 0.01 end
local function edge(frame) return S.plates[frame].ring.vertex end
local function mode(m, diff, size) root.mode, root.diff, root.size = m, diff or 'NormalTexture', size; root:Update() end
local function mono(fs) return fs.fontPath ~= 'stock.ttf' and fs.fontPath ~= 'chat.ttf' end
local LOAD = { 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'InstanceBanner' }
"""

case("the stock shield of all three modes is held; the glyphs, the emblem and the texts stay", PRE + """
    for _, f in ipairs({ def, guild, challenge }) do
        assert(f.Background.alpha == 0 and f.Border.alpha == 0, 'a shield piece is kept')
    end
    for _, t in ipairs(def.DifficultyTextures) do assert(t.alpha == 1, 'a difficulty glyph is held') end
    for _, t in ipairs(guild.Instance.DifficultyTextures) do assert(t.alpha == 1, 'a guild difficulty glyph is held') end
    assert(guild.Emblem.alpha == 1, 'the guild emblem is held')
    assert(challenge.ChallengeModeTexture.alpha == 1, 'the timed run glyph is held')
    assert(def.Text.alpha == 1 and guild.Instance.Text.alpha == 1, 'a group size is held')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("each mode wears a cut plate of ours, made of regions of the content frame, and no child frame is added", PRE + """
    for _, f in ipairs({ def, guild, challenge }) do
        local p = S.plates[f]
        assert(p and p.fill and p.ring, 'no plate')
        assert(p.fill.parent == f and p.ring.parent == f, 'the plate is not regions of the content frame')
        assert(p.c == 6, 'chamfer is ' .. tostring(p.c))
    end
    assert(#def.children == 0 and #challenge.children == 0 and #guild.children == 1 and #root.children == 3, 'a child frame was added')
    local fill = S.plates[def].fill.vertex
    assert(same(fill, { 0.043, 0.024, 0.094 }) and math.abs(fill[4] - 0.94) < 0.001, 'fill is not the body plate')
""")

case("the plate stands 2 px inside the stock rect and follows a change of pixel scale", PRE + """
    local function inside(what)
        for _, f in ipairs({ def, guild, challenge }) do
            local l, t, r, b = Px(f, f)
            for _, region in ipairs({ S.plates[f].fill, S.plates[f].ring }) do
                Expect(region, f, 2, 2, (r - l) - 4, (b - t) - 4, what)
            end
        end
    end
    inside('at 1.2')
    local l, t, r, b = Px(def, def)
    assert(Near(r - l, 35.5 * 1.2) and Near(b - t, 36.5 * 1.2), 'stock rect moved')
    PPU = 1.5
    FS.ControlKit.Reseat()
    inside('at 1.5')
    local fs = def.Text
    assert(Near(fs.size * PPU, 12), 'group size is not 12 px: ' .. fs.size * PPU)
""")

case("the edge tells the difficulty: cyan normal, amber heroic or a timed run, pink mythic", PRE + """
    mode('default', 'NormalTexture', 5)
    assert(same(edge(def), C.COLOR_POWER), 'normal is not cyan')
    mode('default', 'WalkInTexture')
    assert(same(edge(def), C.COLOR_POWER), 'a delve is not cyan')
    mode('default', 'HeroicTexture', 5)
    assert(same(edge(def), C.COLOR_AMBER), 'heroic is not amber')
    mode('default', 'MythicTexture', 5)
    assert(same(edge(def), C.COLOR_HEALTH), 'mythic is not pink')
    mode('guild', 'MythicTexture', 25)
    assert(same(edge(guild), C.COLOR_HEALTH), 'a mythic guild group is not pink')
    mode('guild', 'ChallengeModeTexture', 5)
    assert(same(edge(guild), C.COLOR_AMBER), 'a timed guild run is not amber')
    mode('guild', 'NormalTexture', 5)
    assert(same(edge(guild), C.COLOR_POWER), 'a normal guild group is not cyan')
    mode('challenge')
    assert(same(edge(challenge), C.COLOR_AMBER), 'a timed run is not amber')
    assert(S.plates[def].ring.vertex[4] == 1, 'the edge is not solid')
""")

case("the stock Update and SetFlipped keep the shield held and the edge current", PRE + """
    mode('default', 'NormalTexture', 5)
    assert(def.shown and not guild.shown and not challenge.shown, 'only one mode is shown')
    root.diff = 'MythicTexture'
    root:Update()
    assert(same(edge(def), C.COLOR_HEALTH), 'the edge did not follow Update')
    root:SetFlipped(true)
    for _, f in ipairs({ def, guild, challenge }) do
        assert(f.Background.alpha == 0 and f.Border.alpha == 0, 'a flip brought the shield back')
    end
    assert(same(edge(def), C.COLOR_HEALTH), 'a flip changed the edge')
    -- a stock write of alpha is zeroed again
    def.Border:SetAlpha(1)
    assert(def.Border.alpha == 0, 'the hold did not survive SetAlpha')
    -- a mode shown later (its glyphs set while it was hidden) is painted by its own OnShow
    for _, t in ipairs(guild.Instance.DifficultyTextures) do t:Hide() end
    guild.Instance.HeroicTexture:Show()
    assert(not guild.shown, 'the guild banner should be hidden here')
    guild:Show()
    assert(same(edge(guild), C.COLOR_AMBER), 'a mode shown later has a stale edge')
""")

case("the group size is mono on the banner's ink and the stock text keeps its words", PRE + """
    for _, fs in ipairs({ def.Text, guild.Instance.Text }) do
        assert(mono(fs), 'text is not mono')
        local r, g, b = fs:GetTextColor()
        assert(same({ r, g, b }, C.COLOR_CTRL_TEXT), 'text is not the control ink')
    end
    mode('default', 'NormalTexture', 10)
    assert(def.Text:GetText() == '10', 'the size is not the stock text')
    mode('default', 'NormalTexture', nil)
    assert(def.Text:GetText() == '', 'an empty size is not empty')
""")

case("nothing on the Blizzard banner is moved, resized, reparented, scripted or attributed", """
    Reset()
    local function sig(o)
        local parts = { tostring(o.parent), tostring(o.w), tostring(o.h), tostring(#o.children) }
        for _, p in ipairs(o.points) do parts[#parts + 1] = table.concat({ p.point, tostring(p.rel), p.relPoint, p.x, p.y }, ',') end
        local keys = {}
        for k in pairs(o.scripts) do keys[#keys + 1] = k end
        table.sort(keys)
        parts[#parts + 1] = table.concat(keys, ',')
        return table.concat(parts, '|')
    end
    local before, regions, list = {}, {}, {}
    for _, o in ipairs(AllObjects()) do
        if o.blizz then
            list[#list + 1] = o
            before[o] = sig(o)
            regions[o] = { unpack(o.regions) }
        end
    end
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'InstanceBanner' })
    local root = MinimapCluster.InstanceDifficulty
    assert(FS.InstanceBanner.state.done == root, 'not built')
    for _, o in ipairs(list) do
        assert(sig(o) == before[o], 'a Blizzard widget changed: ' .. tostring(o.fsName or o.kind))
        for i, r in ipairs(regions[o]) do assert(o.regions[i] == r, 'a stock region was replaced') end
    end
    assert(root.scripts.OnEnter and root.scripts.OnLeave and root.Guild.scripts.OnEnter, 'a tooltip script was lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is built in combat; it is built when combat ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'InstanceBanner' })
    local root = MinimapCluster.InstanceDifficulty
    assert(not FS.InstanceBanner.state.plates[root.Default], 'built in combat')
    assert(root.Default.Background.alpha == 1, 'the shield was held in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.InstanceBanner.state.plates[root.Default], 'not built when combat ended')
    assert(root.Default.Background.alpha == 0, 'the shield was not held after combat')
""")

case("a banner that appears after load is built on PLAYER_ENTERING_WORLD", """
    Reset()
    local cluster = MinimapCluster
    MinimapCluster = nil
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'InstanceBanner' })
    assert(not FS.InstanceBanner.state.done, 'built with no frame')
    MinimapCluster = cluster
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(FS.InstanceBanner.state.plates[cluster.InstanceDifficulty.Default], 'not built on entering the world')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("a client without the banner degrades quietly, and a second build adds nothing", PRE + """
    local n, hooks = ObjCount(), HookCount()
    assert(B.Build() == true)
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    root:Update(); root:SetFlipped(false); root:SetFlipped(true)
    assert(ObjCount() == n, 'objects grew: ' .. n .. ' -> ' .. ObjCount())
    assert(HookCount() == hooks, 'hooks grew')
    MinimapCluster.InstanceDifficulty = nil
    assert(B.Build() == false)
    MinimapCluster = nil
    assert(B.Build() == false)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {}
STEPS = [
    ("normal", "mode('default', 'NormalTexture', 5)"),
    ("heroic", "mode('default', 'HeroicTexture', 5)"),
    ("mythic", "mode('default', 'MythicTexture', 20)"),
    ("guild", "mode('guild', 'HeroicTexture', 25)"),
    ("timed", "mode('challenge')"),
]
for key, step in STEPS:
    SCENES[key] = (PRE + f"""
    local back = MinimapCluster:CreateTexture(nil, 'BACKGROUND', nil, -8)
    back:SetColorTexture(0.16, 0.26, 0.2, 1)
    back:SetAllPoints(MinimapCluster)
    {step}
    return DumpOps({{ MinimapCluster }})
""")
# the stock banner as Blizzard draws it, a flat gold stand-in for the shield (a mock cannot draw an atlas)
SCENES["stock"] = ("""
    Reset()
    local root = MinimapCluster.InstanceDifficulty
    local back = MinimapCluster:CreateTexture(nil, 'BACKGROUND', nil, -8)
    back:SetColorTexture(0.16, 0.26, 0.2, 1)
    back:SetAllPoints(MinimapCluster)
    root.Default.Background:SetColorTexture(0.55, 0.42, 0.1, 1)
    root.Default.Border:SetColorTexture(0.85, 0.7, 0.25, 0.6)
    return DumpOps({ MinimapCluster })
""")


def contact_sheet(prefix: str) -> None:
    from PIL import Image, ImageDraw

    names = ["stock", "normal", "heroic", "mythic", "guild", "timed"]
    tiles = [Image.open(f"{prefix}-{n}.png").convert("RGB") for n in names]
    zoom = 6
    tiles = [t.resize((t.width * zoom, t.height * zoom), Image.NEAREST) for t in tiles]
    w, h = max(t.width for t in tiles), max(t.height for t in tiles)
    sheet = Image.new("RGB", (w * len(tiles) + 8 * (len(tiles) - 1), h + 18), (30, 22, 50))
    d = ImageDraw.Draw(sheet)
    for i, (n, t) in enumerate(zip(names, tiles)):
        x = i * (w + 8)
        sheet.paste(t, (x, 18))
        d.text((x + 4, 3), n, fill=(233, 226, 255))
    out = f"{prefix}-sheet.png"
    sheet.save(out)
    print("wrote", out)


if __name__ == "__main__":
    code = H.main("instance banner", SCENES)
    if "--png" in sys.argv:
        contact_sheet(sys.argv[sys.argv.index("--png") + 1])
    raise SystemExit(code)
