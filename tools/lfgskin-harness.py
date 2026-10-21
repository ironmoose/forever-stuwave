#!/usr/bin/env python3
"""Runs the real Modules/Skins/LookingForGroup.lua headless against a mock Looking For Group window.

The window is Blizzard's group finder (`LFGParentFrame` with the Listing, Browse and Who pages, from the
load-on-demand `Blizzard_GroupFinder_VanillaStyle`). The skin is chrome only: it must never replace a script,
write an attribute or move a Blizzard button, because the list, apply and invite buttons run protected group
flows. The mock makes `SetScript` and `SetAttribute` throw, so any such write fails a check. Pinned here:

  * the window gets the panel chrome (with a title) once, the shared X coming from SkinPanel itself;
  * nothing happens, and nothing is logged, while the group finder is not loaded; it is skinned when
    `Blizzard_GroupFinder_VanillaStyle` loads and on PLAYER_ENTERING_WORLD, and not for another addon;
  * the three pages' own backgrounds, art, portraits and titles are hidden by name and stay hidden when
    Blizzard shows the page again; their tab state textures and every child button are left alone;
  * Send Message, Group Invite, Back, List Self, the role poll button and the invite popup's Accept and
    Decline wear the shared text button, in their accents; the refresh, options and search buttons, the
    dropdowns, the role buttons and the tabs are not skinned (no shared skin for them exists yet);
  * the Who page's Filter button is found by its label, however deep it sits, and not by guessing a key;
  * category buttons get a ring and halo as they are added and when they are already there, once each;
  * a second scan adds no second hook.

The mock is NOT the real client. Run:

    python3 tools/lfgskin-harness.py

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
PANELSKINS_SRC = (ADDON / "Core/PanelSkins.lua").read_text(encoding="utf-8")
LFG_SRC = (ADDON / "Modules/Skins/LookingForGroup.lua").read_text(encoding="utf-8")

MOCK = r"""
SECRET = "<secret>"
SlashCmdList = {}
FILTER = "Filter"

-- Frames made by CreateFrame (the addon's own watchers): they record their events and OnEvent script.
local watchers = {}
function CreateFrame()
    local f = { events = {} }
    function f:RegisterEvent(e) self.events[e] = true end
    function f:UnregisterEvent(e) self.events[e] = nil end
    function f:SetScript(script, fn) if script == "OnEvent" then self.onEvent = fn end end
    watchers[#watchers + 1] = f
    return f
end
function FireEvent(event, ...)
    for _, f in ipairs(watchers) do
        if f.events[event] and f.onEvent then f.onEvent(f, event, ...) end
    end
end
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

-- A Blizzard widget. SetScript and SetAttribute throw: this file may add textures and post-hooks only.
function Blizz(name, kind, fields)
    local f = { fsName = name, kind = kind or "Frame", hidden = false, hides = 0, hooks = {}, children = {} }
    function f:GetObjectType() return self.kind end
    function f:GetName() return self.fsName end
    function f:Hide() self.hidden = true; self.hides = self.hides + 1 end
    function f:Show() self.hidden = false end
    function f:GetParent() return self.parent end
    function f:HookScript(script, fn)
        self.hooks[script] = self.hooks[script] or {}
        table.insert(self.hooks[script], fn)
    end
    function f:SetScript() error("SetScript on a Blizzard widget: " .. tostring(self.fsName)) end
    function f:SetAttribute() error("SetAttribute on a Blizzard widget: " .. tostring(self.fsName)) end
    function f:GetChildren() return unpack(self.children) end
    function f:GetText() return self.text end
    function f:CreateTexture() return {} end -- the real Theme.SkinButton draws on the button; here it is a recorder
    if fields then for k, v in pairs(fields) do f[k] = v end end
    if name then _G[name] = f end
    return f
end
function Adopt(parent, child) child.parent = parent; parent.children[#parent.children + 1] = child; return child end
function ShowAgain(f)
    f.hidden = false
    for _, fn in ipairs(f.hooks.OnShow or {}) do fn(f) end
end

-- The window as the 16001 globals dump names it. Only what the checks look at is built.
function BuildWindow()
    local W = {}
    W.parent = Blizz("LFGParentFrame")
    W.portrait = Adopt(W.parent, Blizz("LFGParentFramePortrait"))
    W.close = Adopt(W.parent, Blizz("LFGParentFrameCloseButton", "Button"))
    W.tab1 = Adopt(W.parent, Blizz("LFGParentFrameTab1", "Button"))
    W.listing = Adopt(W.parent, Blizz("LFGListingFrame"))
    W.browse = Adopt(W.parent, Blizz("LFGBrowseFrame"))
    W.who = Adopt(W.parent, Blizz("LFGWhoListFrame"))
    W.art = {}
    for _, name in ipairs({
        "LFGListingFrameBg", "LFGListingFramePortrait", "LFGListingFrameTitleText", "LFGListingFrameRoleBackground",
        "LFGListingFrameActivityViewBarMiddle",
        "LFGBrowseFrameBg", "LFGBrowseFramePortrait", "LFGBrowseFrameTitleText", "LFGBrowseFrameBackgroundArt",
        "LFGWhoListFrameBg", "LFGWhoListFramePortrait", "LFGWhoListFrameTitleText",
    }) do
        local owner = name:find("^LFGListing") and W.listing or name:find("^LFGBrowse") and W.browse or W.who
        W.art[name] = Adopt(owner, Blizz(name, "Texture"))
    end
    -- what must be left alone
    W.keep = {
        listingNormal = Adopt(W.listing, Blizz("LFGListingFrameNormalTexture", "Texture")),
        browseHover = Adopt(W.browse, Blizz("LFGBrowseFrameHoverTexture", "Texture")),
        whoActive = Adopt(W.who, Blizz("LFGWhoListFrameActiveTexture", "Texture")),
        roleDps = Adopt(W.listing, Blizz("LFGListingFrameSoloRoleButtonsRoleButtonDPS", "Button")),
        refresh = Adopt(W.browse, Blizz("LFGBrowseFrameRefreshButton", "Button")),
        options = Adopt(W.browse, Blizz("LFGBrowseFrameOptionsButton", "Button")),
        category = Adopt(W.browse, Blizz("LFGBrowseFrameCategoryDropdown", "Button")),
    }
    W.buttons = {
        sendMessage = Adopt(W.browse, Blizz("LFGBrowseFrameSendMessageButton", "Button", { text = "Send Message" })),
        groupInvite = Adopt(W.browse, Blizz("LFGBrowseFrameGroupInviteButton", "Button", { text = "Group Invite" })),
        back = Adopt(W.listing, Blizz("LFGListingFrameBackButton", "Button", { text = "Back" })),
        post = Adopt(W.listing, Blizz("LFGListingFramePostButton", "Button", { text = "List Self" })),
        poll = Adopt(W.listing, Blizz("LFGListingFrameGroupRoleButtonsInitiateRolePoll", "Button", { text = "Role Poll" })),
        accept = Blizz("LFGInvitePopupAcceptButton", "Button", { text = "Accept" }),
        decline = Blizz("LFGInvitePopupDeclineButton", "Button", { text = "Decline" }),
    }
    return W
end

-- Loads the real PanelSkins.lua and LookingForGroup.lua over recorders for the Theme and the button skins.
function Load()
    local calls = { panels = {}, text = {}, rings = {}, degraded = {} }
    local FS = {
        calls = calls,
        LogDegradeOnce = function(key, msg) calls.degraded[#calls.degraded + 1] = { key, msg } end,
        IsSecret = function(v) return v == SECRET end,
        Theme = {
            COLOR_BG = { 0, 0, 0 }, COLOR_BORDER = { 1, 1, 1 },
            SkinPanel = function(frame, opts) calls.panels[#calls.panels + 1] = { frame = frame, opts = opts } end,
            SkinButton = function(button, opts) calls.rings[#calls.rings + 1] = { button = button, opts = opts } end,
        },
        ButtonSkins = {
            SkinTextButton = function(button, opts) calls.text[#calls.text + 1] = { button = button, opts = opts or {} } end,
        },
    }
    assert(loadstring(PANELSKINS_SRC, "@PanelSkins.lua"))("forever-stuwave", FS)
    assert(loadstring(LFG_SRC, "@LookingForGroup.lua"))("forever-stuwave", FS)
    return FS
end

function TextCall(FS, button)
    for _, c in ipairs(FS.calls.text) do if c.button == button then return c end end
end
function CountTextCalls(FS, button)
    local n = 0
    for _, c in ipairs(FS.calls.text) do if c.button == button then n = n + 1 end end
    return n
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("the_window_gets_the_panel_chrome_once_with_a_title", """
    local W = BuildWindow()
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    FireEvent("PLAYER_ENTERING_WORLD")
    assert(#FS.calls.panels == 1, "SkinPanel calls: " .. #FS.calls.panels)
    local call = FS.calls.panels[1]
    assert(call.frame == W.parent, "SkinPanel was not given LFGParentFrame")
    assert(type(call.opts.title) == "string" and call.opts.title ~= "", "no title: " .. tostring(call.opts.title))
    assert(call.opts.strip ~= false, "the Blizzard art sweep (and the shared X) was switched off")
""")

case("nothing_happens_or_is_logged_while_the_group_finder_is_not_loaded", """
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    FireEvent("ADDON_LOADED", "Blizzard_GroupFinder_VanillaStyle")
    assert(#FS.calls.panels == 0 and #FS.calls.text == 0 and #FS.calls.rings == 0, "something was skinned")
    assert(#FS.calls.degraded == 0, "a missing window logged: " .. tostring(FS.calls.degraded[1] and FS.calls.degraded[1][2]))
""")

case("it_is_skinned_when_the_group_finder_loads_and_not_for_another_addon", """
    local FS = Load()
    local W = BuildWindow()
    FireEvent("ADDON_LOADED", "Blizzard_Calendar")
    assert(#FS.calls.panels == 0, "an unrelated addon load skinned the window")
    FireEvent("ADDON_LOADED", "Blizzard_GroupFinder_VanillaStyle")
    assert(#FS.calls.panels == 1 and FS.calls.panels[1].frame == W.parent, "the group finder load did not skin it")
""")

case("the_page_backgrounds_art_portraits_and_titles_are_hidden_by_name", """
    local W = BuildWindow()
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    for name, texture in pairs(W.art) do
        assert(texture.hidden, name .. " is still showing")
    end
    assert(W.portrait.hidden, "the window's portrait is still showing")
""")

case("hidden_chrome_stays_hidden_when_blizzard_shows_a_page_again", """
    local W = BuildWindow()
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    for _, page in ipairs({ W.listing, W.browse, W.who }) do
        for _, child in ipairs(page.children) do child.hidden = false end
        ShowAgain(page)
    end
    for name, texture in pairs(W.art) do
        assert(texture.hidden, name .. " came back with its page")
    end
""")

case("the_tab_state_textures_role_buttons_and_other_children_are_left_alone", """
    local W = BuildWindow()
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    for name, obj in pairs(W.keep) do
        assert(obj.hides == 0, name .. " was hidden")
        assert(TextCall(FS, obj) == nil, name .. " was given the text button skin")
    end
    for _, ring in ipairs(FS.calls.rings) do
        assert(ring.button.fsName ~= "LFGListingFrameSoloRoleButtonsRoleButtonDPS", "a role button got a ring")
    end
    assert(W.tab1.hides == 0 and TextCall(FS, W.tab1) == nil, "a side tab was touched")
""")

case("the_action_buttons_wear_the_shared_text_button_in_their_accents", """
    local W = BuildWindow()
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    local expected = {
        sendMessage = "violet", groupInvite = "cyan", back = "violet", post = "cyan", poll = "violet",
        accept = "cyan", decline = "pink",
    }
    for key, accent in pairs(expected) do
        local call = TextCall(FS, W.buttons[key])
        assert(call, key .. " was not skinned")
        assert((call.opts.accent or "violet") == accent, key .. " accent: " .. tostring(call.opts.accent))
    end
""")

case("the_close_x_is_left_to_skinpanel_not_skinned_as_a_text_button", """
    local W = BuildWindow()
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    assert(TextCall(FS, W.close) == nil, "the close X was given the text skin")
""")

case("the_who_page_filter_button_is_found_by_its_label_however_deep", """
    local W = BuildWindow()
    local header = Adopt(W.who, Blizz("LFGWhoListFrameHeader"))
    local other = Adopt(header, Blizz(nil, "Button", { text = "Search" }))
    local filter = Adopt(header, Blizz(nil, "Button", { text = FILTER }))
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    assert(TextCall(FS, filter), "the Filter button was not skinned")
    assert(TextCall(FS, other) == nil, "a button with another label was skinned")
""")

case("a_filter_button_that_is_a_direct_child_is_found_too", """
    local W = BuildWindow()
    local filter = Adopt(W.who, Blizz(nil, "Button", { text = FILTER }))
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    assert(TextCall(FS, filter), "a direct-child Filter button was not skinned")
""")

case("a_secret_or_missing_label_and_a_missing_filter_string_do_not_error", """
    local W = BuildWindow()
    Adopt(W.who, Blizz(nil, "Button", { text = SECRET }))
    Adopt(W.who, Blizz(nil, "Button"))
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    FILTER = nil
    FireEvent("PLAYER_ENTERING_WORLD")
""")

case("category_buttons_get_a_ring_when_added_and_when_already_there_once_each", """
    local W = BuildWindow()
    local early = Blizz(nil, "Button")
    local view = Adopt(W.listing, Blizz("LFGListingFrameCategoryView", "Frame", { CategoryButtons = { early } }))
    function LFGListingCategorySelection_AddButton(frame, index) end
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    local function ringsOf(button)
        local n = 0
        for _, r in ipairs(FS.calls.rings) do if r.button == button then n = n + 1 end end
        return n
    end
    assert(ringsOf(early) == 1, "a button already there got " .. ringsOf(early) .. " rings")
    local late = Blizz(nil, "Button")
    view.CategoryButtons[2] = late
    LFGListingCategorySelection_AddButton(view, 2)
    assert(ringsOf(late) == 1, "a button added later got " .. ringsOf(late) .. " rings")
    LFGListingCategorySelection_AddButton(view, 2)
    FireEvent("PLAYER_ENTERING_WORLD")
    assert(ringsOf(late) == 1 and ringsOf(early) == 1, "a button was ringed twice")
""")

case("an_add_button_call_with_no_button_does_not_error", """
    local W = BuildWindow()
    function LFGListingCategorySelection_AddButton(frame, index) end
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    LFGListingCategorySelection_AddButton({ CategoryButtons = {} }, 3)
    LFGListingCategorySelection_AddButton(nil, 1)
    LFGListingCategorySelection_AddButton({}, 1)
""")

case("a_second_scan_adds_no_second_hook_and_still_never_writes_a_script_or_attribute", """
    local W = BuildWindow()
    local FS = Load()
    FireEvent("PLAYER_ENTERING_WORLD")
    local counts = {}
    for _, f in ipairs({ W.parent, W.listing, W.browse, W.who }) do counts[f] = #(f.hooks.OnShow or {}) end
    FireEvent("ADDON_LOADED", "Blizzard_GroupFinder_VanillaStyle")
    FireEvent("PLAYER_ENTERING_WORLD")
    for f, n in pairs(counts) do
        assert(#(f.hooks.OnShow or {}) == n, f.fsName .. " gained OnShow hooks: " .. n .. " -> " .. #(f.hooks.OnShow or {}))
    end
    assert(#FS.calls.panels == 1, "SkinPanel ran again")
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().PANELSKINS_SRC = PANELSKINS_SRC
    rt.globals().LFG_SRC = LFG_SRC
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
