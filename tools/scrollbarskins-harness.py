#!/usr/bin/env python3
"""Runs the real Core/ScrollBarSkins.lua headless against mock Blizzard scroll bars.

The shared scroll bar skin is the chat scroll bar's approved look, lifted out of Chat so every skinned panel
can wear it: Blizzard's art goes invisible, one dim cyan rail runs the whole bar, and the thumb is a magenta
slice of the same rail texture that tracks the thumb and comes up to full white under the mouse. It is SKIN
ONLY on Blizzard's scroll bar templates (MinimalScrollBar and WowTrimScrollBar, the bars that sit beside a
ScrollBox): textures and post-hooks, never a script, an attribute, an anchor or a size of a Blizzard frame.
The mock makes SetScript and SetAttribute throw, so any such write fails a check. Pinned here:

  * a bar is recognised by shape (a Track frame that holds a Thumb), a horizontal bar and anything else is not;
  * the MinimalScrollBar art (atlases naming the scroll bar, anywhere in the subtree) and the
    WowTrimScrollBar extras (Backplate, Background, knob, stepper Texture and Overlay) all end up at alpha 0
    and STAY there when Blizzard shows a region or sets an atlas again (HeldArt), so a hover highlight that
    Blizzard re-shows is still invisible; a region that is not scroll bar art is left alone;
  * the steppers keep their rect (the track measures against them) but stop taking clicks;
  * the rail is one cyan texture over the bar's whole rect, a bar wider than the chat bar gets a rail the
    chat bar's width, centred; the thumb slice follows the thumb vertically and the rail horizontally, and
    hover/leave moves it between full white and its idle magenta;
  * a second skin adds nothing, and a thing that is not a bar is a quiet no-op;
  * the chat scroll bar (Chat.SkinChatScrollBar) still seats itself inside the panel on every show and wears
    the same skin once, however often the chat frame is skinned.

The mock is NOT the real client. Run:

    python3 tools/scrollbarskins-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
HELDART_SRC = (ADDON / "Core/HeldArt.lua").read_text(encoding="utf-8")
SKIN_SRC = (ADDON / "Core/ScrollBarSkins.lua").read_text(encoding="utf-8")
CHAT_SRC = (ADDON / "Modules/Chat/ChatTermBar.lua").read_text(encoding="utf-8")

MOCK = r"""
function InCombatLockdown() return false end

function hooksecurefunc(a, b, c)
    local tbl, name, fn = _G, a, b
    if type(a) == "table" then tbl, name, fn = a, b, c end
    local orig = tbl[name]
    tbl[name] = function(...)
        local r = orig(...)
        fn(...)
        return r
    end
end

local function Anchored(self)
    function self:ClearAllPoints() self.points = {} end
    function self:SetPoint(...) self.points[#self.points + 1] = { ... } end
end

-- A texture region. SetTexture really clears the atlas; SetAtlas and Show do not touch the alpha.
function Region(fields)
    local r = { kind = "Texture", shown = true, alpha = 1, points = {} }
    function r:GetObjectType() return self.kind end
    function r:GetAtlas() return self.atlas end
    function r:SetAtlas(a) self.atlas = a end
    function r:SetTexture(t) self.texture = t; self.atlas = nil end
    function r:SetVertexColor(...) self.color = { ... } end
    function r:SetAlpha(a) self.alpha = a end
    function r:GetAlpha() return self.alpha end
    function r:Hide() self.shown = false end
    function r:Show() self.shown = true end
    function r:SetShown(v) self.shown = v end
    function r:IsShown() return self.shown end
    function r:SetWidth(w) self.width = w end
    function r:SetAllPoints() end
    Anchored(r)
    if fields then for k, v in pairs(fields) do r[k] = v end end
    return r
end

-- A Blizzard frame. SetScript and SetAttribute throw: the skin may add textures and post-hooks only.
function Frame(kind, fields)
    local f = { kind = kind or "Frame", regions = {}, children = {}, hooks = {}, points = {}, mouse = true,
                width = 0, height = 0, shown = true, created = {} }
    function f:GetObjectType() return self.kind end
    function f:GetRegions() return unpack(self.regions) end
    function f:GetChildren() return unpack(self.children) end
    function f:HookScript(script, fn)
        self.hooks[script] = self.hooks[script] or {}
        table.insert(self.hooks[script], fn)
    end
    function f:SetScript() error("SetScript on a Blizzard widget") end
    function f:SetAttribute() error("SetAttribute on a Blizzard widget") end
    function f:EnableMouse(v) self.mouse = v end
    function f:IsMouseEnabled() return self.mouse end
    function f:GetWidth() return self.width end
    function f:SetWidth(w) self.width = w end
    function f:GetHeight() return self.height end
    function f:SetSize(w, h) self.width, self.height = w, h end
    function f:IsShown() return self.shown end
    function f:SetShown(v) self.shown = v end
    function f:CreateTexture(name, layer)
        local t = Region({ layer = layer })
        self.regions[#self.regions + 1] = t
        self.created[#self.created + 1] = t
        return t
    end
    Anchored(f)
    if fields then for k, v in pairs(fields) do f[k] = v end end
    return f
end
function AddChild(parent, child) parent.children[#parent.children + 1] = child; return child end
function AddRegion(frame, key, atlas)
    local r = Region({ atlas = atlas })
    frame.regions[#frame.regions + 1] = r
    if key then frame[key] = r end
    return r
end
function Fire(frame, script, ...)
    for _, fn in ipairs(frame.hooks[script] or {}) do fn(frame, ...) end
end

-- MinimalScrollBar as the 12.1.0 source builds it: art is atlases that name the scroll bar.
function MinimalBar()
    local bar = Frame("EventFrame", { width = 8, height = 286 })
    bar.Track = AddChild(bar, Frame("Frame"))
    AddRegion(bar.Track, "Begin", "minimal-scrollbar-track-top")
    AddRegion(bar.Track, "End", "minimal-scrollbar-track-bottom")
    AddRegion(bar.Track, "Middle", "!minimal-scrollbar-track-middle")
    bar.Track.Thumb = AddChild(bar.Track, Frame("Button", { width = 8, height = 60 }))
    AddRegion(bar.Track.Thumb, "Begin", "minimal-scrollbar-small-thumb-top")
    AddRegion(bar.Track.Thumb, "End", "minimal-scrollbar-small-thumb-bottom")
    AddRegion(bar.Track.Thumb, "Middle", "minimal-scrollbar-small-thumb-middle")
    bar.Back = AddChild(bar, Frame("Button", { width = 17, height = 11 }))
    AddRegion(bar.Back, "Texture", "minimal-scrollbar-arrow-top")
    bar.Forward = AddChild(bar, Frame("Button", { width = 17, height = 11 }))
    AddRegion(bar.Forward, "Texture", "minimal-scrollbar-arrow-bottom")
    return bar
end

-- WowTrimScrollBar: a solid backplate (no atlas), a Background frame, a knob whose regions only get their
-- atlas when a state changes, and steppers with a Texture and a highlight Overlay.
function TrimBar()
    local bar = Frame("EventFrame", { width = 25, height = 400 })
    AddRegion(bar, "Backplate", nil)
    bar.Background = AddChild(bar, Frame("Frame"))
    AddRegion(bar.Background, "Begin", "UI-ScrollBar-EndCap-Top")
    AddRegion(bar.Background, "End", "UI-ScrollBar-EndCap-Bottom")
    AddRegion(bar.Background, "Middle", "!UI-ScrollBar-Center")
    bar.Track = AddChild(bar, Frame("Frame"))
    bar.Track.Thumb = AddChild(bar.Track, Frame("Button", { width = 18, height = 80 }))
    AddRegion(bar.Track.Thumb, "Begin", nil)
    AddRegion(bar.Track.Thumb, "End", nil)
    AddRegion(bar.Track.Thumb, "Middle", "UI-ScrollBar-Knob-Center")
    for _, key in ipairs({ "Back", "Forward" }) do
        bar[key] = AddChild(bar, Frame("Button", { width = 18, height = 16 }))
        AddRegion(bar[key], "Texture", nil)
        AddRegion(bar[key], "Overlay", "UI-ScrollBar-ScrollUpButton-Highlight").shown = false
    end
    return bar
end

function Colors()
    return { COLOR_POWER = { 0.133, 0.878, 1, 1 }, COLOR_HEALTH = { 1, 0.180, 0.592, 1 } }
end

-- HeldArt and ScrollBarSkins, the real files.
function LoadSkin()
    local FS = { Theme = Colors() }
    assert(loadstring(HELDART_SRC, "@HeldArt.lua"))("forever-stuwave", FS)
    assert(loadstring(SKIN_SRC, "@ScrollBarSkins.lua"))("forever-stuwave", FS)
    return FS
end

-- ChatTermBar over a Theme stub, with the real shared skin beneath it.
function LoadChat()
    local FS = { Chat = {}, Theme = Colors() }
    FS.Theme.SkinButton = function() end
    FS.Theme.StripBlizzardChrome = function() end
    FS.Theme.ApplyMono = function() end
    assert(loadstring(HELDART_SRC, "@HeldArt.lua"))("forever-stuwave", FS)
    assert(loadstring(SKIN_SRC, "@ScrollBarSkins.lua"))("forever-stuwave", FS)
    assert(loadstring(CHAT_SRC, "@ChatTermBar.lua"))("forever-stuwave", FS)
    return FS
end

function ChatFrameWithBar()
    local frame = Frame("ScrollingMessageFrame", { width = 500, height = 300 })
    frame.ScrollBar = MinimalBar()
    return frame
end

-- Every texture region in a subtree that has the given atlas-name marker or none (the whole bar).
function AllRegions(obj, out)
    out = out or {}
    for _, r in ipairs({ obj:GetRegions() }) do out[#out + 1] = r end
    for _, c in ipairs({ obj:GetChildren() }) do AllRegions(c, out) end
    return out
end
function Invisible(region) return region.alpha == 0 or region.shown == false end
function PointOf(region, name)
    for _, p in ipairs(region.points) do if p[1] == name then return p end end
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("a_bar_is_recognised_by_its_track_and_thumb_and_nothing_else_is", """
    local S = LoadSkin().ScrollBarSkins
    assert(S.IsScrollBar(MinimalBar()), "a MinimalScrollBar")
    assert(S.IsScrollBar(TrimBar()), "a WowTrimScrollBar")
    assert(not S.IsScrollBar(Frame("Frame")), "a plain frame")
    assert(not S.IsScrollBar(Frame("Button", { Left = {}, Middle = {}, Right = {} })), "a text button")
    assert(not S.IsScrollBar(Frame("Frame", { Track = Frame("Frame") })), "a track without a thumb")
    assert(not S.IsScrollBar(nil) and not S.IsScrollBar({}) and not S.IsScrollBar("bar"), "non-frames")
    local horizontal = MinimalBar()
    horizontal.Track.Thumb.isHorizontal = true
    assert(not S.IsScrollBar(horizontal), "a horizontal bar would need a different slice")
""")

case("a_minimal_bar_loses_every_scroll_bar_atlas_region_in_its_whole_subtree", """
    local S = LoadSkin().ScrollBarSkins
    local bar = MinimalBar()
    assert(S.Skin(bar) == true, "Skin did not report that it skinned")
    for _, key in ipairs({ "Begin", "End", "Middle" }) do
        assert(Invisible(bar.Track[key]), "Track." .. key)
        assert(Invisible(bar.Track.Thumb[key]), "Thumb." .. key)
    end
    assert(Invisible(bar.Back.Texture) and Invisible(bar.Forward.Texture), "stepper arrows")
""")

case("a_trim_bar_loses_its_backplate_background_knob_and_stepper_art_even_without_an_atlas", """
    local S = LoadSkin().ScrollBarSkins
    local bar = TrimBar()
    S.Skin(bar)
    assert(Invisible(bar.Backplate), "the solid black backplate (no atlas) is still drawn")
    for _, key in ipairs({ "Begin", "End", "Middle" }) do
        assert(Invisible(bar.Background[key]), "Background." .. key)
        assert(Invisible(bar.Track.Thumb[key]), "Thumb." .. key .. " (atlas not set yet)")
    end
    for _, step in ipairs({ bar.Back, bar.Forward }) do
        assert(Invisible(step.Texture), "stepper Texture (atlas not set yet)")
        assert(Invisible(step.Overlay), "stepper highlight Overlay")
    end
""")

case("blizzard_showing_or_resetting_the_art_later_does_not_bring_it_back", """
    local S = LoadSkin().ScrollBarSkins
    local bar = TrimBar()
    S.Skin(bar)
    -- WowTrimScrollBarStepperMixin:OnButtonStateChanged: SetAtlas on Texture, SetShown on the Overlay.
    bar.Back.Texture:SetAtlas("UI-ScrollBar-ScrollUpButton-Up")
    bar.Back.Overlay:SetShown(true)
    bar.Track.Thumb.Middle:SetAtlas("UI-ScrollBar-Knob-MouseOver-Center")
    bar.Track.Thumb.Middle:Show()
    bar.Backplate:SetAlpha(0.75) -- WowTrimScrollBarMixin:OnLoad with backplateAlpha
    for _, r in ipairs({ bar.Back.Texture, bar.Back.Overlay, bar.Track.Thumb.Middle, bar.Backplate }) do
        assert(r.alpha == 0, "a region came back at alpha " .. r.alpha)
    end
    -- and it does not clear atlases, which Blizzard's own OnSizeChanged reads back
    assert(bar.Track.Thumb.Middle:GetAtlas() == "UI-ScrollBar-Knob-MouseOver-Center", "the atlas was cleared")
""")

case("a_minimal_thumb_keeps_the_atlas_blizzards_size_handler_reads_back", """
    local S = LoadSkin().ScrollBarSkins
    local bar = MinimalBar()
    S.Skin(bar)
    assert(bar.Track.Thumb.Middle:GetAtlas() == "minimal-scrollbar-small-thumb-middle", "Thumb.Middle atlas cleared")
""")

case("a_region_that_is_not_scroll_bar_art_is_left_alone", """
    local S = LoadSkin().ScrollBarSkins
    local bar = MinimalBar()
    local other = AddRegion(bar.Track, "Other", "some-other-atlas")
    local plain = AddRegion(bar, "Plain", nil)
    local text = Region({ kind = "FontString" }); bar.regions[#bar.regions + 1] = text
    S.Skin(bar)
    assert(other.alpha == 1 and other.shown, "a foreign atlas region was held")
    assert(plain.alpha == 1 and plain.shown, "an atlas-less region of a Minimal bar was held")
    assert(text.alpha == 1, "a font string was held")
""")

case("the_steppers_keep_their_rect_and_visibility_but_stop_taking_clicks", """
    local S = LoadSkin().ScrollBarSkins
    local bar = MinimalBar()
    S.Skin(bar)
    for _, step in ipairs({ bar.Back, bar.Forward }) do
        assert(step.mouse == false, "a stepper still takes clicks")
        assert(step.shown and step.width == 17 and step.height == 11, "a stepper was hidden or resized")
    end
    assert(bar.Track.mouse == true and bar.Track.Thumb.mouse == true, "the track or the thumb lost the mouse")
""")

case("the_rail_is_one_dim_cyan_texture_over_the_whole_bar", """
    local FS = LoadSkin()
    local bar = MinimalBar()
    FS.ScrollBarSkins.Skin(bar)
    local rail = FS.ScrollBarSkins.Parts(bar).rail
    assert(rail and rail.layer == "BACKGROUND", "no rail on the BACKGROUND layer")
    assert(rail.texture == "Interface\\\\AddOns\\\\forever-stuwave\\\\Media\\\\Textures\\\\scroll_rail.tga", tostring(rail.texture))
    local c = rail.color
    assert(c and math.abs(c[1] - 0.133) < 1e-6 and math.abs(c[2] - 0.878) < 1e-6 and c[3] == 1, "not cyan")
    assert(math.abs(c[4] - 0.22) < 1e-6, "rail alpha " .. tostring(c[4]))
    local tl, br = PointOf(rail, "TOPLEFT"), PointOf(rail, "BOTTOMRIGHT")
    assert(tl and tl[2] == bar and br and br[2] == bar, "the rail is not pinned to the bar's corners")
    assert(#rail.points == 2 and rail.width == nil, "a fixed width on a bar that is not wider than the chat bar")
""")

case("the_thumb_slice_is_magenta_and_follows_the_thumb_vertically_and_the_rail_across", """
    local FS = LoadSkin()
    local bar = MinimalBar()
    FS.ScrollBarSkins.Skin(bar)
    local parts = FS.ScrollBarSkins.Parts(bar)
    local fill = parts.fill
    local thumb = bar.Track.Thumb
    assert(fill and fill.layer == "ARTWORK" and fill == thumb.created[1], "no ARTWORK slice on the thumb")
    assert(fill.texture == parts.rail.texture, "the slice is not cut from the rail texture")
    local c = fill.color
    assert(math.abs(c[1] - 1) < 1e-6 and math.abs(c[2] - 0.180) < 1e-6 and math.abs(c[3] - 0.592) < 1e-6, "not magenta")
    assert(math.abs(c[4] - 0.95) < 1e-6, "thumb alpha " .. tostring(c[4]))
    assert(PointOf(fill, "TOP")[2] == thumb and PointOf(fill, "BOTTOM")[2] == thumb, "not tracking the thumb vertically")
    assert(PointOf(fill, "LEFT")[2] == parts.rail and PointOf(fill, "RIGHT")[2] == parts.rail,
        "not as wide as the rail")
""")

case("hovering_the_thumb_brings_the_slice_to_full_white_and_leaving_restores_it", """
    local FS = LoadSkin()
    local bar = MinimalBar()
    FS.ScrollBarSkins.Skin(bar)
    local fill = FS.ScrollBarSkins.Parts(bar).fill
    local thumb = bar.Track.Thumb
    Fire(thumb, "OnEnter")
    local c = fill.color
    assert(c[1] == 1 and c[2] == 1 and c[3] == 1 and c[4] == 1, "hover is not full white")
    Fire(thumb, "OnLeave")
    c = fill.color
    assert(math.abs(c[2] - 0.180) < 1e-6 and math.abs(c[4] - 0.95) < 1e-6, "leave did not restore the magenta")
""")

case("a_bar_wider_than_the_chat_bar_gets_a_rail_the_chat_bars_width_centred", """
    local FS = LoadSkin()
    local bar = TrimBar()
    FS.ScrollBarSkins.Skin(bar)
    local parts = FS.ScrollBarSkins.Parts(bar)
    assert(parts.rail.width == 14, "rail width " .. tostring(parts.rail.width))
    assert(PointOf(parts.rail, "TOP")[2] == bar and PointOf(parts.rail, "BOTTOM")[2] == bar, "not centred over the bar")
    assert(PointOf(parts.rail, "TOPLEFT") == nil, "pinned to both sides of a wide bar")
    assert(PointOf(parts.fill, "LEFT")[2] == parts.rail and PointOf(parts.fill, "RIGHT")[2] == parts.rail,
        "the slice does not follow the narrower rail")
""")

case("a_bar_with_no_width_yet_takes_the_whole_bar_whatever_it_becomes", """
    local FS = LoadSkin()
    local bar = MinimalBar()
    bar.width = 0
    FS.ScrollBarSkins.Skin(bar)
    local rail = FS.ScrollBarSkins.Parts(bar).rail
    assert(PointOf(rail, "TOPLEFT") and PointOf(rail, "BOTTOMRIGHT") and rail.width == nil, "not pinned to the corners")
""")

case("skinning_a_bar_twice_adds_nothing", """
    local FS = LoadSkin()
    local bar = MinimalBar()
    assert(FS.ScrollBarSkins.Skin(bar) == true)
    local regions, hooks = #AllRegions(bar), #(bar.Track.Thumb.hooks.OnEnter or {})
    assert(FS.ScrollBarSkins.Skin(bar) == false, "the second skin claimed to skin")
    assert(#AllRegions(bar) == regions, "a second rail or slice was drawn")
    assert(#(bar.Track.Thumb.hooks.OnEnter or {}) == hooks, "a second hover hook")
""")

case("it_only_adds_textures_and_post_hooks_never_a_script_or_attribute", """
    local FS = LoadSkin()
    local bar = TrimBar()
    -- SetScript and SetAttribute throw on every mock widget; reaching here means neither was called.
    FS.ScrollBarSkins.Skin(bar)
    assert(next(bar.hooks) == nil, "the bar itself was hooked")
    assert(#bar.points == 0 and bar.width == 25 and bar.height == 400, "the bar was moved or resized")
    local thumb = bar.Track.Thumb
    assert(thumb.width == 18 and thumb.height == 80 and #thumb.points == 0, "the thumb was moved or resized")
    local n = 0
    for script in pairs(thumb.hooks) do n = n + 1 end
    assert(n == 2 and thumb.hooks.OnEnter and thumb.hooks.OnLeave, "the thumb should hold exactly its hover pair")
""")

case("a_bar_with_no_thumb_gets_the_rail_only", """
    local FS = LoadSkin()
    local bar = Frame("Frame", { width = 8 })
    bar.Track = AddChild(bar, Frame("Frame"))
    assert(FS.ScrollBarSkins.Skin(bar) == true)
    local parts = FS.ScrollBarSkins.Parts(bar)
    assert(parts.rail and parts.fill == nil, "rail only")
""")

case("something_that_is_not_a_bar_is_a_quiet_no_op", """
    local FS = LoadSkin()
    local S = FS.ScrollBarSkins
    assert(S.Skin(nil) == false and S.Skin({}) == false and S.Skin("bar") == false)
    assert(S.Parts(nil) == nil and S.Parts(Frame("Frame")) == nil, "parts for an unskinned frame")
    local broken = Frame("Frame", { CreateTexture = function() error("no textures for you") end })
    assert(S.Skin(broken) == false, "an erroring frame was reported as skinned")
    assert(S.Skin(broken) == false and S.Parts(broken) ~= nil, "a failed bar must not be retried into a second rail")
""")

case("it_works_in_combat_because_nothing_it_touches_is_protected", """
    function InCombatLockdown() return true end
    local FS = LoadSkin()
    local bar = TrimBar()
    assert(FS.ScrollBarSkins.Skin(bar) == true, "not skinned in combat")
    assert(FS.ScrollBarSkins.Parts(bar).rail, "no rail in combat")
""")

# ---- chat: the scroll bar the shared skin was lifted from ----

case("the_chat_bar_is_seated_inside_the_panel_and_reseated_every_time_it_is_shown", """
    local FS = LoadChat()
    local frame = ChatFrameWithBar()
    FS.Chat.SkinChatScrollBar(frame)
    local bar = frame.ScrollBar
    local function seat()
        local tr, br = PointOf(bar, "TOPRIGHT"), PointOf(bar, "BOTTOMRIGHT")
        assert(tr and tr[2] == frame and tr[4] == -3 and tr[5] == 0, "TOPRIGHT")
        assert(br and br[2] == frame and br[4] == -3 and br[5] == 14 + 4, "BOTTOMRIGHT")
        assert(#bar.points == 2 and bar.width == 14, "points " .. #bar.points .. " width " .. bar.width)
    end
    seat()
    -- Blizzard re-anchors it afterwards and wins; the OnShow hook takes it back.
    bar:ClearAllPoints(); bar:SetPoint("LEFT", frame, "RIGHT", 0, 0); bar.width = 8
    Fire(bar, "OnShow")
    seat()
""")

case("the_chat_bar_wears_the_shared_skin_once_however_often_the_frame_is_skinned", """
    local FS = LoadChat()
    local frame = ChatFrameWithBar()
    FS.Chat.SkinChatScrollBar(frame)
    FS.Chat.SkinChatScrollBar(frame)
    FS.Chat.SkinChatScrollBar(frame)
    local bar = frame.ScrollBar
    local parts = FS.ScrollBarSkins.Parts(bar)
    assert(parts and parts.rail and parts.fill, "the chat bar did not get the shared skin")
    assert(#(bar.hooks.OnShow or {}) == 1, "OnShow hooks: " .. #(bar.hooks.OnShow or {}))
    assert(#bar.created == 1, "rails drawn: " .. #bar.created)
    assert(#bar.Track.Thumb.created == 1, "slices drawn: " .. #bar.Track.Thumb.created)
    assert(Invisible(bar.Track.Begin) and Invisible(bar.Track.Thumb.Middle) and Invisible(bar.Back.Texture),
        "Blizzard's art is still showing")
    assert(bar.Back.mouse == false and bar.Forward.mouse == false, "the steppers still take clicks")
""")

case("the_chat_rail_spans_the_whole_14_wide_bar_exactly_as_before", """
    local FS = LoadChat()
    local frame = ChatFrameWithBar()
    FS.Chat.SkinChatScrollBar(frame)
    local rail = FS.ScrollBarSkins.Parts(frame.ScrollBar).rail
    assert(PointOf(rail, "TOPLEFT")[2] == frame.ScrollBar and PointOf(rail, "BOTTOMRIGHT")[2] == frame.ScrollBar,
        "the rail is not the bar's whole rect")
    assert(rail.width == nil, "the 14 wide chat bar got a fixed width")
""")

case("a_chat_frame_with_no_scroll_bar_is_a_quiet_no_op", """
    local FS = LoadChat()
    FS.Chat.SkinChatScrollBar(Frame("ScrollingMessageFrame"))
    FS.Chat.SkinChatScrollBar(nil)
""")

case("the_jump_button_still_shows_only_when_away_from_the_live_edge", """
    local FS = LoadChat()
    local frame = ChatFrameWithBar()
    local jump = Frame("Button")
    jump.SetShown = function(self, v) self.shown = v end
    frame.ScrollToBottomButton = jump
    local atBottom = true
    frame.AtBottom = function() return atBottom end
    frame.ScrollUp = function() end
    FS.Chat.SkinChatScrollBar(frame)
    assert(jump.shown == false, "shown while already at the bottom")
    atBottom = false
    frame:ScrollUp()
    assert(jump.shown == true, "not shown after scrolling away")
    assert(PointOf(jump, "BOTTOMRIGHT")[2] == frame and jump.width == 14 and jump.height == 14, "button not seated")
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().HELDART_SRC = HELDART_SRC
    rt.globals().SKIN_SRC = SKIN_SRC
    rt.globals().CHAT_SRC = CHAT_SRC
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    total = len(CASES)
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{total - failures}/{total} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
