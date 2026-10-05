-- Forever Synthwave: ChatTabs
-- Split out of the original Chat.lua (2026-09-23): the terminal's own tab
-- strip (replacing Blizzard's ChatFrameNTab entirely) and the social tab that
-- leads it. Reads/writes the shared FS.Chat state table; see ChatCore.lua's
-- header for why cross-module names live there instead of as locals.

local _, FS = ...
local Chat = FS.Chat

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local ApplyMono = FS.Theme.ApplyMono
local COLOR_POWER = FS.Theme.COLOR_POWER -- cyan accent; the mock's "neon border" color for chat
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH -- #ff2e97; matches the mock's .termbar pink status dot

-- The tab strip's own chrome; see media/generate_tab_plate.py. TAB_SLICE_MARGIN
-- MUST equal CHAMFER there, or the 45-degree cut stretches into a wedge.
local TAB_SLANT_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\tab_slant.tga"
local TAB_SLANT_GLOW_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\tab_slant_glow.tga"
local TAB_MID_GLOW_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\tab_mid_glow.tga"
local ICON_SOCIAL_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\icon_social.tga"
local TAB_MID_RASTER_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\tab_mid_raster.tga"
local TAB_SLANT_RASTER_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\tab_slant_raster.tga"

-- The unselected tab: same shape, cyan rather than magenta, and pulled down
-- far enough to read as deactivated next to the live one.
local TAB_IDLE_LINE_ALPHA  = 0.45
local TAB_IDLE_GLOW_ALPHA  = 0.30
local TAB_IDLE_PLATE_ALPHA = 0.55

-------------------------------------------------------------------------------
-- Tabs
-------------------------------------------------------------------------------

-- The terminal draws its OWN tab strip; Blizzard's ChatFrameNTab is hidden
-- outright rather than restyled.
--
-- This replaces a restyle pass that tinted Blizzard's tab fontstrings and put a
-- cyan wash behind the active one. That was the wrong target twice over. The
-- mock's `.termtabs` is a strip we draw INSIDE the terminal chassis, between the
-- term bar and the message body -- not a treatment applied to Blizzard's tabs,
-- which on this client only appear on hover. Parker: "the chat doesn't have tabs
-- my dude, we haven't built that out yet", and "they are invisible if they are
-- there and not part of the terminal design."
--
-- Mock values (full-ui-layout.html, `.termtabs`): 9px mono, per-pill padding
-- 2px 9px, inactive muted, active in the terminal accent over a 10% accent
-- wash, and a 22% accent rule along the bottom of the strip.
-- Width of each slanted end cap, i.e. how far the top edge leads the bottom.
local TAB_LEAN = 10
-- Interior padding, measured from the pill's edge. It MUST exceed TAB_LEAN:
-- the slanted cap occupies the first and last TAB_LEAN pixels, so anything
-- less puts the label inside the slant. At 7 against a lean of 10 the text was
-- literally overlapping the diagonal, which is what read as no padding at all.
-- Exterior spacing is unaffected -- that is set by the nest in ApplyDockState,
-- so widening a tab moves its label away from the seam without moving the
-- seam.
local TAB_PAD_X        = TAB_LEAN + 8
local TAB_RULE_ALPHA   = 0.22
-- The lit underline on the selected pill, the way a synthwave console marks a
-- channel. Thicker than a hairline so it reads as a light source.
-- One definition for both edges, so they cannot drift apart again.
local TAB_EDGE_LINE_H  = 1

-- No TAB_MUTED any more. The idle label was the mock's lavender `--muted`;
-- it is now muted CYAN, matching this tab's own lines, so the strip carries
-- two colours (live magenta, idle cyan) rather than three.

-- Hidden, not SetAlpha(0): a transparent tab still takes clicks, so the player
-- would be selecting chat windows by clicking apparently-empty space above the
-- terminal. Our pills own that interaction now. Blizzard re-shows tabs on dock
-- updates, hence the OnShow hook.
-- Blizzard's tab is made INVISIBLE, not hidden, and that distinction is the
-- whole right-click context menu.
--
-- Hiding it worked visually and silently took the menu with it: right-clicking
-- a pill delegates to FCF_Tab_OnClick on the real tab, and their handler
-- anchors a dropdown to that tab. Called on a hidden frame it does nothing at
-- all -- no menu, no error, tested on the live client.
--
-- Alpha 0 with the mouse off is indistinguishable on screen and leaves a
-- shown, correctly-sized anchor for Blizzard's own menu. The tab is parked on
-- top of its pill by ApplyDockState so the menu opens where the click was.
-- Same pattern this file already uses to keep QuickJoinToastButton's tooltip
-- on the social tab.
local function HideBlizzardTab(tab)
    if not tab then return end

    -- The tab stays SHOWN -- it is the anchor Blizzard's context menu opens
    -- against, and their handler does nothing on a hidden frame -- but every
    -- region it draws is hidden.
    --
    -- Alpha alone is not enough and that is what put "General" and "Combat
    -- Log" back on screen in Blizzard's own styling: the dock re-asserts tab
    -- alpha as it lays the strip out, so a cleared alpha lasts until the next
    -- dock update. Hiding the REGIONS survives that, because the dock has no
    -- reason to re-show art it did not hide. Alpha stays as belt and braces.
    -- ElvUI does the same thing by name in CH:ClearTabTextures.
    if not tab.fsTabHidden then
        tab.fsTabHidden = true
        if tab.EnableMouse then pcall(tab.EnableMouse, tab, false) end
        if tab.HookScript then
            tab:HookScript("OnShow", function(self) HideBlizzardTab(self) end)
        end
    end

    if tab.SetAlpha then pcall(tab.SetAlpha, tab, 0) end
    for _, region in ipairs({ tab:GetRegions() }) do
        if region.Hide then pcall(region.Hide, region) end
    end
end

function Chat.HideAllBlizzardTabs()
    for i = 1, Chat.MAX_CHAT_FRAMES do
        if not _G["ChatFrame" .. i] then break end
        HideBlizzardTab(_G["ChatFrame" .. i .. "Tab"])
    end
end

-- A chat window's name, lowercased. The terminal addresses things in lowercase
-- (`synthwave://general`), so "Combat Log" reading as `combat log` in the strip
-- keeps one voice rather than two.
--
-- SOURCE ORDER MATTERS, and getting it wrong is what made every window read
-- "chat" until the first tab swap. The tab's FONTSTRING is the obvious place
-- to read a tab's name and the wrong one: it is populated by Blizzard's own
-- chat-window setup, which has not necessarily run when our Apply() does. An
-- empty read then fell through to the literal "chat" -- a string plausible
-- enough to look like a real window name rather than a failure, which is why
-- it survived this long. Switching tabs re-ran ApplyDockState by which point
-- the fontstring existed, so the label "fixed itself" and only the freshly
-- logged-in state was ever wrong.
--
-- GetChatWindowInfo reads the STORED name straight out of the chat CVars, so
-- it is right from the first frame and does not depend on anything else having
-- been built yet. The fontstring stays as a fallback because it is what a
-- rename touches first.
function Chat.TabLabel(chatFrame)
    if not chatFrame then return "chat" end
    local id = chatFrame.GetID and chatFrame:GetID()
    local label

    if id and type(GetChatWindowInfo) == "function" then
        local ok, stored = pcall(GetChatWindowInfo, id)
        if ok and type(stored) == "string" and stored ~= "" then label = stored end
    end

    if not label then
        local name = chatFrame.GetName and chatFrame:GetName()
        local tab = name and _G[name .. "Tab"]
        local text = tab and (tab.Text or (tab.GetName and _G[tab:GetName() .. "Text"]))
        local fromTab = text and text.GetText and text:GetText()
        if fromTab and fromTab ~= "" then label = fromTab end
    end

    if not label or label == "" then label = chatFrame.name end

    -- Deliberately NOT "chat". A last-resort label should look obviously
    -- wrong, because the whole bug above was a fallback that read like a real
    -- answer. If this ever shows up on screen, it is a bug report by itself.
    if not label or label == "" then
        label = id and ("window " .. id) or "unnamed"
    end
    return tostring(label):lower()
end

-- HARDCODED interim ordering: comms always leads the pill strip.
--
-- A real drag-to-reorder feature is deferred -- the Forever beta client
-- discards per-character SavedVariables across a /reload (design notes),
-- so a user-chosen dock order cannot be persisted yet. Parker's call: "for
-- now hard code the comms channel as the first one." When that client bug is
-- fixed, replace this with the real reorder feature (design notes) driven
-- by a persisted user order, and this function goes away.
--
-- Matches on Chat.TabLabel's RESOLVED label, not a dock index -- index is
-- per-character and unstable (the same lesson as the channel-colour work).
-- No match is a graceful no-op: the original dock order comes back unchanged.
local function OrderedDockedFrames()
    local frames = Chat.DockedChatFrames()

    local commsIndex
    for i, cf in ipairs(frames) do
        local label = Chat.TabLabel(cf)
        if label and label:lower():find("comms", 1, true) then
            commsIndex = i
            break
        end
    end

    if not commsIndex or commsIndex == 1 then return frames end

    local ordered = { frames[commsIndex] }
    for i, cf in ipairs(frames) do
        if i ~= commsIndex then
            ordered[#ordered + 1] = cf
        end
    end
    return ordered
end

-- One pill. A Button rather than a Frame because these are the click target
-- that replaces Blizzard's tabs, and Button gives the click handling for free.
local function CreateTabPill(parent)
    local pill = CreateFrame("Button", nil, parent)
    pill:SetHeight(Chat.TERM_TABS_HEIGHT - 1)

    -- Console-tab chrome: a LEANING plate, magenta edged and lit inward.
    --
    -- Built from two fixed-size slanted caps with a stretched rectangle
    -- between them, because a leaning shape cannot be nine-sliced -- the
    -- middle band stretches, the corners do not, and a straight diagonal
    -- comes out kinked. Fixed caps also mean the ANGLE is identical on every
    -- tab regardless of how wide the label is. See media/generate_tab_slant.py.
    local mid = pill:CreateTexture(nil, "BACKGROUND")
    mid:SetColorTexture(1, 1, 1, 1)
    mid:SetPoint("TOPLEFT", pill, "TOPLEFT", TAB_LEAN, 0)
    mid:SetPoint("BOTTOMRIGHT", pill, "BOTTOMRIGHT", -TAB_LEAN, 0)
    pill.wash = mid

    local function Cap(anchor, flip)
        local cap = pill:CreateTexture(nil, "BACKGROUND")
        cap:SetTexture(TAB_SLANT_TEXTURE)
        cap:SetWidth(TAB_LEAN)
        cap:SetPoint("TOP" .. anchor, pill, "TOP" .. anchor, 0, 0)
        cap:SetPoint("BOTTOM" .. anchor, pill, "BOTTOM" .. anchor, 0, 0)
        -- The trailing cap is the SAME texture flipped on BOTH axes. Flipping
        -- only horizontally gives a lean that tapers the wrong way.
        if flip then cap:SetTexCoord(1, 0, 1, 0) end
        cap:SetVertexColor(Chat.COLOR_TERM_BG[1], Chat.COLOR_TERM_BG[2], Chat.COLOR_TERM_BG[3], 0.95)
        return cap
    end

    pill.capLeft = Cap("LEFT", false)
    pill.capRight = Cap("RIGHT", true)

    -- CRT texture over the body, so a dark plate is not a grey box.
    local scan = pill:CreateTexture(nil, "BACKGROUND", nil, 1)
    scan:SetTexture(Chat.SCANLINE_TEXTURE, "REPEAT", "REPEAT")
    scan:SetAllPoints(mid)
    if scan.SetTexCoord then
        scan:SetTexCoord(0, Chat.TERM_TABS_HEIGHT * 3 / Chat.SCANLINE_TILE_PX,
                         0, Chat.TERM_TABS_HEIGHT / Chat.SCANLINE_TILE_PX)
    end
    scan:SetAlpha(0.35)
    pill.scan = scan

    -- MAGENTA edge, glowing INWARD, on the left, right and top. The sides come
    -- from the cap's own diagonal -- a rectangular glow strip cannot follow a
    -- slope, so the falloff is baked perpendicular to it in
    -- tab_slant_glow.tga. The top is straight, so it reuses glow_edge.tga with
    -- the same rotation Theme.AddOuterGlow uses, pointing down into the plate.
    local function CapGlow(cap, flip)
        local glow = pill:CreateTexture(nil, "ARTWORK", nil, 1)
        glow:SetTexture(TAB_SLANT_GLOW_TEXTURE)
        glow:SetAllPoints(cap)
        if flip then glow:SetTexCoord(1, 0, 1, 0) end
        glow:SetBlendMode("ADD")
        glow:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], 0.95)
        return glow
    end

    pill.glowLeft = CapGlow(pill.capLeft, false)
    pill.glowRight = CapGlow(pill.capRight, true)

    -- Spans to the PILL's right edge, not the middle section's.
    --
    -- The two caps are not mirror images in what they cover at a given edge.
    -- The leading cap tapers to a point at the TOP (its filled corner is at
    -- the bottom), while the trailing cap -- the same wedge flipped on both
    -- axes -- is filled clear across its top. Anchoring the top edge to `mid`
    -- therefore left the trailing cap's top run bare: "there is a missing
    -- part". The plate's real top edge runs from mid's left to the pill's
    -- right; its real bottom edge runs from the pill's left to mid's right.
    -- ONE glow for the straight run, top and bottom together, drawn at the
    -- caps' own height with the caps' own falloff curve.
    --
    -- This replaces two glow_edge.tga rectangles. They were a DIFFERENT light
    -- from the caps -- a different curve, no solid core, spanning their own
    -- full height -- so however carefully they were sized, the two met at the
    -- cap seam as a visible step: "the corners still don't line up... i think
    -- you have a different glow." tab_mid_glow.tga is generated from the same
    -- _falloff over the same texel count as tab_slant_glow.tga, so the seam
    -- closes by construction rather than by tuning a height until it looks
    -- right.
    local midGlow = pill:CreateTexture(nil, "ARTWORK", nil, 1)
    midGlow:SetTexture(TAB_MID_GLOW_TEXTURE)
    midGlow:SetAllPoints(mid)
    midGlow:SetBlendMode("ADD")
    pill.midGlow = midGlow

    local topLine = pill:CreateTexture(nil, "ARTWORK", nil, 2)
    -- White, because SetVertexColor MULTIPLIES against this. Baking the
    -- colour in here would tint every later repaint by it.
    topLine:SetColorTexture(1, 1, 1, 1)
    topLine:SetHeight(TAB_EDGE_LINE_H)
    topLine:SetPoint("TOPLEFT", mid, "TOPLEFT", 0, 0)
    topLine:SetPoint("TOPRIGHT", pill, "TOPRIGHT", 0, 0)
    pill.topLine = topLine

    -- The cyan baseline belongs to the ACTIVE TAB, spanning that tab's whole
    -- bottom edge -- Parker: "i meant the cyan glow along the bottom of the
    -- one tab. not the whole thing." Mirroring the top: from the pill's left
    -- (where the leading cap IS filled) to mid's right (where the trailing cap
    -- is not).
    local rail = pill:CreateTexture(nil, "ARTWORK", nil, 2)
    rail:SetColorTexture(1, 1, 1, 1)
    -- 1px, the SAME as topLine. This was TAB_UNDERLINE_H (2), and a 2px solid
    -- under a glow of equal reach is what made the bottom look heavier than
    -- the top even after the glow heights matched -- Parker: "is it like there
    -- is a 2 or 3px solid then the glow?" The two edges are now the same
    -- construction, mirrored.
    rail:SetHeight(TAB_EDGE_LINE_H)
    rail:SetPoint("BOTTOMLEFT", pill, "BOTTOMLEFT", 0, 0)
    rail:SetPoint("BOTTOMRIGHT", mid, "BOTTOMRIGHT", 0, 0)
    pill.rail = rail


    local label = pill:CreateFontString(nil, "ARTWORK")
    ApplyMono(label, Chat.TAB_FONT_SIZE)
    label:SetPoint("CENTER", pill, "CENTER", 0, 0)
    pill.label = label

    pill:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    pill:SetScript("OnClick", function(self, button)
        if not self.chatFrame then return end

        if button == "RightButton" then
            -- Blizzard's tab context menu (font size, rename, unlock, filters).
            -- Hiding their tabs took it away; this gives it back.
            --
            -- DELEGATED to FCF_Tab_OnClick on the real tab rather than opening
            -- the menu ourselves. There is no *TabDropDown global on this
            -- client at all -- checked against the 16001 globals dump, which
            -- has ToggleDropDownMenu, UIDropDownMenu_Initialize, MenuUtil and
            -- FCF_Tab_OnClick but nothing matching *TabDropDown* -- so which
            -- menu system owns this is Blizzard's business and not something
            -- to guess at. Their handler knows.
            local tab = _G["ChatFrame" .. self.chatFrame:GetID() .. "Tab"]
            if tab and type(FCF_Tab_OnClick) == "function" then
                pcall(FCF_Tab_OnClick, tab, "RightButton")
            end
            return
        end

        if type(FCF_SelectDockFrame) == "function" then
            -- Drive Blizzard's own selection rather than reimplementing
            -- docking: the pills are a face on the existing system, so
            -- everything else that reacts to a dock change still fires.
            pcall(FCF_SelectDockFrame, self.chatFrame)
        end
    end)

    -- The only motion in the strip: an inactive pill warms toward the accent on
    -- hover, so the strip reads as controls rather than a printed label row.
    pill:SetScript("OnEnter", function(self)
        if not self.isActive then
            -- Its own cyan, brought up to full. The idle tab is muted, so
            -- undimming it IS the hover -- no second accent colour needed.
            self.label:SetTextColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
        end
    end)
    pill:SetScript("OnLeave", function(self)
        if not self.isActive then
            self.label:SetTextColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3],
                TAB_IDLE_LINE_ALPHA)
        end
    end)

    return pill
end

-- THE tab swap. Everything a dock-selection change has to do lives here and
-- only here -- panel geometry, chrome placement, pill paint -- so a new entry
-- point is one call and cannot half-apply the state. Two related chat bugs
-- were the symptom of that work being spread out: the chrome was
-- seated from one window while another was raised, and each panel was sized
-- from its own frame, so the background changed height per tab.
--
-- Hooked to Blizzard's own selection path rather than called speculatively, so
-- it runs exactly once per real swap.
-- Every tab wears the SAME chrome; only its colour says which one is live.
--
-- Selection used to be signalled by the chrome existing at all -- the inactive
-- tabs were a bare label. Parker's call is a state change instead: "lets have
-- the not active tabs have the same shape but instead of magents lets use the
-- cyan and do all 4 sides the same color and also mute it a little it looks
-- deactivated. For the active tab have all 4 sides magenta."
--
-- So the regions are always shown and this is the only thing that varies. It
-- also makes the strip read as a row of channels, all present, one powered,
-- rather than as one decorated word among plain ones.
local function PaintPill(pill, isActive)
    local edge = isActive and COLOR_HEALTH or COLOR_POWER
    local lineAlpha = isActive and 1 or TAB_IDLE_LINE_ALPHA
    local glowAlpha = isActive and 0.95 or TAB_IDLE_GLOW_ALPHA
    local plateAlpha = isActive and 0.95 or TAB_IDLE_PLATE_ALPHA

    for _, region in ipairs({ pill.wash, pill.capLeft, pill.capRight, pill.scan,
                              pill.glowLeft, pill.glowRight, pill.midGlow,
                              pill.topLine, pill.rail }) do
        region:Show()
    end

    for _, region in ipairs({ pill.wash, pill.capLeft, pill.capRight }) do
        region:SetVertexColor(Chat.COLOR_TERM_BG[1], Chat.COLOR_TERM_BG[2], Chat.COLOR_TERM_BG[3], plateAlpha)
    end

    -- All FOUR sides one colour. The bottom is included deliberately: it used
    -- to stay cyan while the other three went magenta, which made the active
    -- tab read as two-toned rather than as a single lit outline.
    for _, region in ipairs({ pill.glowLeft, pill.glowRight, pill.midGlow }) do
        region:SetVertexColor(edge[1], edge[2], edge[3], glowAlpha)
    end
    for _, region in ipairs({ pill.topLine, pill.rail }) do
        region:SetVertexColor(edge[1], edge[2], edge[3], lineAlpha)
    end

    pill.scan:SetAlpha(isActive and 0.35 or 0.20)

    -- The label is just one more thing wearing the edge colour, at the same
    -- alpha as the lines. Parker: "cyan text for teh deactived tabs, magenta
    -- text for activated. have the cyan text also be muted to match teh lines
    -- etc." One colour per state across the whole tab, so nothing on it has
    -- to be kept in sync by hand.
    pill.label:SetTextColor(edge[1], edge[2], edge[3], lineAlpha)
end

-------------------------------------------------------------------------------
-- The social tab: the terminal's leading element, before the channel tabs.
--
-- Parker's design. It is the old chat social button rebuilt as part of the tab
-- row rather than an icon parked beside it: "we can stick it as the starter to
-- our tabs. so the one side of the button is straight and then it goes to the
-- angled rectangle to start our tabs."
--
-- So its LEFT edge is straight (it starts the row, there is nothing to lean
-- into) and its RIGHT edge carries the same slant every tab uses, which is
-- what makes the row read as one strip instead of a button plus some tabs. It
-- is the one element here in the terminal GREEN rather than the cyan/magenta
-- duotone, because it is not a channel and should not look selectable.
-------------------------------------------------------------------------------
local SOCIAL_ICON_SIZE = 14
local SOCIAL_GAP = 5
-- Its OWN padding, not TAB_PAD_X. A tab's padding is sized to clear the
-- leading slant that eats its first TAB_LEAN pixels; this button's left edge
-- is straight, so borrowing that number padded it against a slant that is not
-- there and made the whole thing too wide. The right side still needs no
-- padding of its own beyond the lean, which is already in the width.
local SOCIAL_PAD_LEFT = 8
local SOCIAL_PAD_RIGHT = 6
-- Quieter than a tab. The tabs are the control you are meant to look at; this
-- sits beside them and should not compete -- "tone down everything a little so
-- it isn't so in your face."
local SOCIAL_LINE_ALPHA = 0.70
local SOCIAL_GLOW_ALPHA = 0.40
local SOCIAL_TEXT_ALPHA = 0.85
-- Subtle on purpose: a raster you notice is a pattern, not a surface.
local SOCIAL_RASTER_ALPHA = 0.16

local function SocialCount()
    local total = 0
    if C_FriendList and C_FriendList.GetNumOnlineFriends then
        total = C_FriendList.GetNumOnlineFriends() or 0
    end
    -- Battle.net friends are a separate list; the button counts both.
    if BNGetNumFriends then
        local _, online = BNGetNumFriends()
        total = total + (online or 0)
    end
    return total
end

local function LayoutSocialTab()
    local tab = Chat.socialTab
    if not tab then return 0 end

    tab.count:SetText(tostring(SocialCount()))

    -- Width follows the label, so 1, 2 and 3 digits all fit without the glyph
    -- shifting: "it can dynamically be sized to fix 2 or 3 digit numbers."
    local textWidth = tab.count:GetStringWidth() or 10
    tab:SetWidth(SOCIAL_PAD_LEFT + SOCIAL_ICON_SIZE + SOCIAL_GAP + textWidth
                 + SOCIAL_PAD_RIGHT + TAB_LEAN)
    return tab:GetWidth()
end

function Chat.BuildSocialTab()
    if Chat.socialTab or not Chat.termTabs then return end

    local tab = CreateFrame("Button", nil, Chat.termTabs)
    tab:SetHeight(Chat.TERM_TABS_HEIGHT - 1)
    tab:SetPoint("LEFT", Chat.termTabs, "LEFT", 0, 0)

    local green = Chat.COLOR_TERM_GREEN

    -- Declared up front because the regions register into them as they are
    -- built, and they are not built in the order they are listed: the glows
    -- come before the lines. Declaring these next to the first line that
    -- appends would leave the glows indexing a nil.
    local lines, glows, rasters = {}, {}, {}

    -- Body: straight on the left, so only ONE cap, on the trailing edge.
    local mid = tab:CreateTexture(nil, "BACKGROUND")
    mid:SetColorTexture(1, 1, 1, 1)
    mid:SetVertexColor(Chat.COLOR_TERM_BG[1], Chat.COLOR_TERM_BG[2], Chat.COLOR_TERM_BG[3], 0.95)
    mid:SetPoint("TOPLEFT", tab, "TOPLEFT", 0, 0)
    mid:SetPoint("BOTTOMRIGHT", tab, "BOTTOMRIGHT", -TAB_LEAN, 0)

    local cap = tab:CreateTexture(nil, "BACKGROUND")
    cap:SetTexture(TAB_SLANT_TEXTURE)
    cap:SetWidth(TAB_LEAN)
    cap:SetPoint("TOPRIGHT", tab, "TOPRIGHT", 0, 0)
    cap:SetPoint("BOTTOMRIGHT", tab, "BOTTOMRIGHT", 0, 0)
    cap:SetTexCoord(1, 0, 1, 0)
    cap:SetVertexColor(Chat.COLOR_TERM_BG[1], Chat.COLOR_TERM_BG[2], Chat.COLOR_TERM_BG[3], 0.95)

    local scan = tab:CreateTexture(nil, "BACKGROUND", nil, 1)
    scan:SetTexture(Chat.SCANLINE_TEXTURE, "REPEAT", "REPEAT")
    scan:SetAllPoints(mid)
    if scan.SetTexCoord then
        scan:SetTexCoord(0, Chat.TERM_TABS_HEIGHT * 3 / Chat.SCANLINE_TILE_PX,
                         0, Chat.TERM_TABS_HEIGHT / Chat.SCANLINE_TILE_PX)
    end
    scan:SetAlpha(0.35)

    -- Neon green raster over the plate, so this reads as the head of the strip
    -- rather than a differently-coloured tab. ADD-blended off scanline_glow,
    -- which is WHITE -- the ordinary scanline texture is black and would add
    -- nothing, because ADD emits src * vertexColor and a vertex colour is a
    -- multiply.
    local function Raster(texture, region, flip)
        local raster = tab:CreateTexture(nil, "BACKGROUND", nil, 2)
        raster:SetTexture(texture)
        raster:SetAllPoints(region)
        if flip then raster:SetTexCoord(1, 0, 1, 0) end
        raster:SetBlendMode("ADD")
        raster:SetVertexColor(Chat.COLOR_TERM_GREEN[1], Chat.COLOR_TERM_GREEN[2],
                              Chat.COLOR_TERM_GREEN[3], SOCIAL_RASTER_ALPHA)
        rasters[#rasters + 1] = raster
        return raster
    end

    -- The raster covers the SLANTED end too, which a tiled rectangle cannot:
    -- it would keep its full width across the wedge and spill past the
    -- diagonal, the same way a rectangular glow does. So the lines are baked
    -- into both textures from one period definition -- tab_mid_raster for the
    -- straight run, tab_slant_raster with the same lines clipped to the wedge
    -- -- and both are drawn at the pill's height, so they land at the same
    -- pitch and meet at the seam for the same reason the glows do.
    -- NOT flipped, unlike the cap's shape and glow above. tab_slant_raster is
    -- baked to the trailing silhouette already, because flipping a raster
    -- vertically mirrors its line pattern and a 4.5-texel period does not
    -- divide 32 evenly -- the lines came back a pixel or two out of phase with
    -- the straight run's at the seam.
    Raster(TAB_MID_RASTER_TEXTURE, mid, false)
    Raster(TAB_SLANT_RASTER_TEXTURE, cap, false)

    -- Same edge treatment as a tab: the diagonal's light is baked into the cap
    -- texture, the straight run's into the mid texture, one curve for both.
    local capGlow = tab:CreateTexture(nil, "ARTWORK", nil, 1)
    capGlow:SetTexture(TAB_SLANT_GLOW_TEXTURE)
    capGlow:SetAllPoints(cap)
    capGlow:SetTexCoord(1, 0, 1, 0)
    capGlow:SetBlendMode("ADD")
    capGlow:SetVertexColor(green[1], green[2], green[3], SOCIAL_GLOW_ALPHA)
    glows[#glows + 1] = capGlow

    local midGlow = tab:CreateTexture(nil, "ARTWORK", nil, 1)
    midGlow:SetTexture(TAB_MID_GLOW_TEXTURE)
    midGlow:SetAllPoints(mid)
    midGlow:SetBlendMode("ADD")
    midGlow:SetVertexColor(green[1], green[2], green[3], SOCIAL_GLOW_ALPHA)
    glows[#glows + 1] = midGlow

    -- The two horizontal edges do NOT span the same width, and anchoring both
    -- to `mid` is what left the top-right corner open.
    --
    -- The trailing cap is the wedge flipped on both axes, so it is filled
    -- clear across its TOP and empty at its BOTTOM. The top edge therefore
    -- runs the full width of the button, over the cap; the bottom edge stops
    -- where the straight part stops. Same asymmetry as the channel tabs, and
    -- it catches you out in exactly the same way.
    local top = tab:CreateTexture(nil, "ARTWORK", nil, 2)
    top:SetColorTexture(green[1], green[2], green[3], SOCIAL_LINE_ALPHA)
    top:SetHeight(TAB_EDGE_LINE_H)
    top:SetPoint("TOPLEFT", tab, "TOPLEFT", 0, 0)
    top:SetPoint("TOPRIGHT", tab, "TOPRIGHT", 0, 0)
    lines[#lines + 1] = top

    local bottom = tab:CreateTexture(nil, "ARTWORK", nil, 2)
    bottom:SetColorTexture(green[1], green[2], green[3], SOCIAL_LINE_ALPHA)
    bottom:SetHeight(TAB_EDGE_LINE_H)
    bottom:SetPoint("BOTTOMLEFT", tab, "BOTTOMLEFT", 0, 0)
    bottom:SetPoint("BOTTOMRIGHT", mid, "BOTTOMRIGHT", 0, 0)
    lines[#lines + 1] = bottom

    -- The straight leading edge, which is what distinguishes this from a tab.
    local left = tab:CreateTexture(nil, "ARTWORK", nil, 2)
    left:SetColorTexture(green[1], green[2], green[3], SOCIAL_LINE_ALPHA)
    left:SetWidth(TAB_EDGE_LINE_H)
    left:SetPoint("TOPLEFT", tab, "TOPLEFT", 0, 0)
    left:SetPoint("BOTTOMLEFT", tab, "BOTTOMLEFT", 0, 0)
    lines[#lines + 1] = left

    local icon = tab:CreateTexture(nil, "ARTWORK", nil, 3)
    icon:SetTexture(ICON_SOCIAL_TEXTURE)
    icon:SetSize(SOCIAL_ICON_SIZE, SOCIAL_ICON_SIZE)
    icon:SetPoint("LEFT", tab, "LEFT", SOCIAL_PAD_LEFT, 0)
    icon:SetVertexColor(green[1], green[2], green[3], SOCIAL_TEXT_ALPHA)
    tab.icon = icon

    local count = tab:CreateFontString(nil, "OVERLAY")
    ApplyMono(count, Chat.TAB_FONT_SIZE)
    count:SetPoint("LEFT", icon, "RIGHT", SOCIAL_GAP, 0)
    count:SetTextColor(green[1], green[2], green[3], SOCIAL_TEXT_ALPHA)
    tab.count = count

    tab:SetScript("OnClick", function()
        if type(ToggleFriendsFrame) == "function" then pcall(ToggleFriendsFrame) end
    end)
    -- Hover brings its own green up to full rather than changing hue: the
    -- icon is green now, so undimming IS the hover.
    --
    -- It also calls THROUGH to QuickJoinToastButton's own OnEnter/OnLeave.
    -- Hiding that button took its tooltip with it -- measured on the live
    -- client, it carries handlers for both -- and its tooltip lists who is
    -- queued for what, which is the whole point of the count. Delegating
    -- rather than writing our own text means the content stays whatever
    -- Blizzard shows, including anything this build adds to it.
    -- The whole button lights, not just the glyph. A control that only
    -- changes its icon on hover does not read as a control -- and this one is
    -- deliberately quiet at rest, so the hover has somewhere to go.
    local function PaintSocial(hovered)
        local lineAlpha  = hovered and 1.00 or SOCIAL_LINE_ALPHA
        local glowAlpha  = hovered and 0.75 or SOCIAL_GLOW_ALPHA
        local textAlpha  = hovered and 1.00 or SOCIAL_TEXT_ALPHA
        local rasterAlpha = hovered and (SOCIAL_RASTER_ALPHA * 2) or SOCIAL_RASTER_ALPHA

        for _, line in ipairs(lines) do
            line:SetColorTexture(green[1], green[2], green[3], lineAlpha)
        end
        for _, glow in ipairs(glows) do
            glow:SetVertexColor(green[1], green[2], green[3], glowAlpha)
        end
        for _, raster in ipairs(rasters) do
            raster:SetVertexColor(green[1], green[2], green[3], rasterAlpha)
        end
        tab.icon:SetVertexColor(green[1], green[2], green[3], textAlpha)
        tab.count:SetTextColor(green[1], green[2], green[3], textAlpha)
    end

    local function Passthrough(script)
        local button = _G.QuickJoinToastButton
        local handler = button and button.GetScript and button:GetScript(script)
        if handler then pcall(handler, button) end
    end

    tab:SetScript("OnEnter", function(self)
        PaintSocial(true)
        Passthrough("OnEnter")
        -- Re-anchor AFTER their handler, which owns the tooltip to its own
        -- button. That button is parked on this tab and hidden, so the
        -- tooltip would otherwise sit on an invisible frame.
        if GameTooltip and GameTooltip:IsShown() then
            GameTooltip:ClearAllPoints()
            GameTooltip:SetPoint("BOTTOMLEFT", self, "TOPLEFT", 0, 6)
        end
    end)
    tab:SetScript("OnLeave", function(_)
        PaintSocial(false)
        Passthrough("OnLeave")
        if GameTooltip then GameTooltip:Hide() end
    end)

    Chat.socialTab = tab

    -- The count is live, so it has to follow the friend lists rather than only
    -- being read once at build time.
    local watcher = CreateFrame("Frame")
    watcher:RegisterEvent("FRIENDLIST_UPDATE")
    watcher:RegisterEvent("BN_FRIEND_INFO_CHANGED")
    watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
    watcher:SetScript("OnEvent", function() LayoutSocialTab() end)

    LayoutSocialTab()
end

function Chat.ApplyDockState()
    if not Chat.termTabs then return end

    -- Resolve the active window ONCE, here, and let the rest of the swap read
    -- it. This is the line that makes the active pill follow the tab.
    Chat.activeChatFrame = Chat.ActiveChatFrame()

    -- One-time login restore of the tab the player had selected last session.
    -- Chat.pendingSelectedTab is captured at file load in ChatCore.lua, BEFORE
    -- this function can possibly run -- see that capture's comment for why it
    -- has to happen that early. Cleared immediately, whether or not a swap
    -- actually happens below, so this branch can never fire twice and can
    -- never fight a later manual tab switch (this same function also runs on
    -- every real selection change, via the FCF_SelectDockFrame/FCF_Tab_OnClick
    -- hooks wired up in HookTabSelection further down this file).
    if Chat.pendingSelectedTab then
        local wanted = Chat.pendingSelectedTab
        Chat.pendingSelectedTab = nil

        local current = Chat.activeChatFrame and Chat.activeChatFrame:GetID()
        if wanted ~= current and type(FCF_SelectDockFrame) == "function" then
            for _, cf in ipairs(Chat.DockedChatFrames()) do
                -- Only a frame that is CURRENTLY docked is a valid target: the
                -- saved id can name a window that was torn off or closed since
                -- the save, and selecting anything else is not this feature's
                -- job. An id matching nothing here (torn off, closed, or just
                -- corrupt SavedVariables) leaves the loop with no match and the
                -- restore is a silent no-op, same as an unset saved value.
                if cf:GetID() == wanted then
                    pcall(FCF_SelectDockFrame, cf)
                    break
                end
            end
        end

        -- Re-resolve rather than trust the swap above blindly. FCF_SelectDockFrame
        -- is not hooked back onto this function until later in the login sequence
        -- (Chat.HookTabSelection, called from ChatSlashCommands' Apply()), so
        -- nothing else would repaint the strip/backdrop for a restore performed
        -- here. Refreshing now lets the rest of THIS pass -- the loop below and
        -- the pill paint -- draw the restored tab directly, instead of waiting on
        -- a hook that has not been wired up yet.
        Chat.activeChatFrame = Chat.ActiveChatFrame()
    end

    -- Interim hardcoded default-active-tab: force comms active at login when
    -- Chat.pendingDefaultComms was set (ChatCore.lua, only when there was no
    -- saved tab for the block above to restore). Companion to
    -- OrderedDockedFrames' comms-first pill hardcode further up this file;
    -- blocked on the client SavedVariables /reload bug (design notes), to
    -- be revisited alongside the real persisted-order/selection feature (design notes
    -- design record) once the client is fixed. Cleared immediately so it can
    -- never fire twice or fight a later manual tab switch, same discipline as
    -- the pendingSelectedTab block above.
    if Chat.pendingDefaultComms then
        Chat.pendingDefaultComms = nil

        local commsFrame
        for _, cf in ipairs(Chat.DockedChatFrames()) do
            local label = Chat.TabLabel(cf)
            if label and label:lower():find("comms", 1, true) then
                commsFrame = cf
                break
            end
        end

        if commsFrame then
            local current = Chat.activeChatFrame and Chat.activeChatFrame:GetID()
            if commsFrame:GetID() ~= current and type(FCF_SelectDockFrame) == "function" then
                pcall(FCF_SelectDockFrame, commsFrame)
                Chat.activeChatFrame = Chat.ActiveChatFrame()
            end
        end
    end

    -- Persist the tab that ends up active from this pass: a restore (above), a
    -- real player selection, or just Blizzard's login default. This is the ONE
    -- reconcile point every selection change already flows through (see the
    -- hooksecurefunc wiring in HookTabSelection below), so it is also the one
    -- place that needs to save -- no separate hook on the selection itself.
    if Chat.activeChatFrame and Chat.activeChatFrame.GetID then
        ForeverSynthwaveDB = ForeverSynthwaveDB or {}
        ForeverSynthwaveDB.chatSelectedTab = Chat.activeChatFrame:GetID()
    end

    -- Order matters: geometry, then the chrome that anchors to it, then paint.
    -- Seating reads the backdrop's rect, so re-anchoring afterwards would
    -- leave the term bar and tabs one swap behind.
    for _, cf in ipairs(Chat.skinnedChatFrames) do
        if cf.fsBackdrop then Chat.AnchorBackdrop(cf) end

        -- The chat windows live in the terminal too, or the container owns
        -- only its own chrome and the thing it is meant to sit behind is still
        -- outside it. ElvUI reparents the chat frames the same way.
        --
        -- Re-asserted every pass rather than done once: the dock manager
        -- reparents frames as they are docked and undocked.
        if cf:GetParent() ~= Chat.termPanel then cf:SetParent(Chat.termPanel) end
        cf:SetFrameLevel(Chat.termPanel:GetFrameLevel() + Chat.LEVEL_CHAT)

        -- Visibility has to be mirrored BY HAND now. As a child of its chat
        -- frame a backdrop was hidden for free whenever that window was; owned
        -- by the terminal, nothing hides it, so every docked-but-inactive
        -- window's panel drew on top of the visible one -- a second bordered
        -- box floating inside the first.
        --
        -- Exactly what happened to the ">" prompt when it moved onto its own
        -- host. Reparenting to escape ONE inherited property gives up all of
        -- them; mirror back the ones that were wanted.
        --
        -- Driven off `activeChatFrame`, NOT off cf:IsShown(). Reading the
        -- window's own flag looked right and was an ordering trap: at the pass
        -- that runs during load the dock has not hidden the unselected windows
        -- yet, so every backdrop was recorded as visible and stayed that way
        -- -- measured, frames 2-10 all reported "cf false, bd true". Exactly
        -- one backdrop should ever be up, and the active window is the one
        -- thing here that already knows which.
        if cf.fsBackdrop then cf.fsBackdrop:SetShown(cf == Chat.activeChatFrame) end

        local cfTab = _G["ChatFrame" .. cf:GetID() .. "Tab"]
        if cfTab and cfTab:GetParent() ~= Chat.termPanel then cfTab:SetParent(Chat.termPanel) end
    end

    -- Blizzard's dock manager owns the tab strip's layout and sits over it, so
    -- it comes along as well; left outside, it keeps its own strata and can
    -- draw across the panel when the terminal is raised.
    --
    -- Given LEVEL_DOCK every pass, not just on reparent: measured in game
    -- 2026-09-22, an unowned level here inherited parent+1 (201, tabs at 202),
    -- which outranked our own backdrop and chrome and let Blizzard's tabs draw
    -- over the panel fill.
    if GeneralDockManager then
        if GeneralDockManager:GetParent() ~= Chat.termPanel then
            GeneralDockManager:SetParent(Chat.termPanel)
        end
        GeneralDockManager:SetFrameLevel(Chat.termPanel:GetFrameLevel() + Chat.LEVEL_DOCK)
    end

    Chat.SeatTerminalChrome()

    -- Pill LAYOUT order only -- OrderedDockedFrames() puts comms first (see
    -- its header). Every non-layout use of the dock in this function (the
    -- reparent/level loop above, the pending-tab restore) stays on
    -- Chat.DockedChatFrames()'s real dock order.
    local frames = OrderedDockedFrames()
    Chat.termTabs.pills = Chat.termTabs.pills or {}

    -- Start after the social tab, nesting into its trailing slant exactly the
    -- way the tabs nest into each other, so the row reads as one strip.
    local x = TAB_PAD_X
    if Chat.socialTab then
        x = LayoutSocialTab() - TAB_LEAN
    end
    for i, chatFrame in ipairs(frames) do
        local pill = Chat.termTabs.pills[i]
        if not pill then
            pill = CreateTabPill(Chat.termTabs)
            Chat.termTabs.pills[i] = pill
        end

        local isActive = (chatFrame == Chat.activeChatFrame)
        pill.chatFrame = chatFrame
        pill.isActive = isActive
        pill.label:SetText(Chat.TabLabel(chatFrame))

        -- Width follows the label, so a renamed window still fits its pill.
        local textWidth = pill.label:GetStringWidth() or 30
        pill:SetWidth(textWidth + TAB_PAD_X * 2)
        pill:ClearAllPoints()
        pill:SetPoint("LEFT", Chat.termTabs, "LEFT", x, 0)
        -- Advance by the width MINUS one lean, so each tab's trailing slant
        -- and the next one's leading slant land on the same diagonal. They
        -- are parallel by construction, so they meet as a single seam rather
        -- than leaving a wedge of dead strip between every pair -- which is
        -- where most of the gap was coming from, more than the padding.
        x = x + pill:GetWidth() - TAB_LEAN

        PaintPill(pill, isActive)
        pill:Show()

        -- Park the invisible Blizzard tab on this pill. It is the anchor their
        -- context menu opens against, so its rect decides where the menu
        -- appears; without this the menu opens wherever the dock left the real
        -- tab, which is nowhere near the pill that was clicked.
        local realTab = _G["ChatFrame" .. chatFrame:GetID() .. "Tab"]
        if realTab then
            realTab:ClearAllPoints()
            realTab:SetAllPoints(pill)
            realTab:SetAlpha(0)
            -- Below the backdrop, not merely below the chrome: measured in
            -- game 2026-09-22, these outranked our panel fill on level alone
            -- and drew over it even at alpha 0.40. LEVEL_DOCK puts them at
            -- the container's own level, under LEVEL_BACKDROP's +1, so the
            -- fill covers them instead of alpha fighting them.
            realTab:SetFrameLevel(Chat.termPanel:GetFrameLevel() + Chat.LEVEL_DOCK)
            if realTab.Show then realTab:Show() end
            HideBlizzardTab(realTab)
        end
    end

    for i = #frames + 1, #Chat.termTabs.pills do
        Chat.termTabs.pills[i]:Hide()
    end
end

-- Builds the strip under the term bar.
--
-- Parented to UIParent, NOT to a chat frame's backdrop, and this is the whole
-- point. It used to be built on ChatFrame1's backdrop, which is a child of
-- ChatFrame1 -- so selecting the Combat Log hid ChatFrame1, took the strip down
-- with it, and left no way back to General short of a /reload. Parker hit that
-- exactly: "when i click on the combat tab this happens. I have to reload to get
-- chat back."
--
-- The strip describes the DOCK, so it outlives any one window in it.
-- SeatTerminalChrome re-anchors it onto whichever window is selected.
function Chat.BuildTermTabs()
    if Chat.termTabs then return end

    local strip = CreateFrame("Frame", nil, Chat.termPanel)
    strip:SetHeight(Chat.TERM_TABS_HEIGHT)

    -- The strip keeps only the mock's faint hairline (`.termtabs`
    -- border-bottom, 22% accent). The BRIGHT rail is the active tab's and
    -- lives on the pill: lighting the whole strip lit tabs that are not
    -- selected, which is the opposite of what the rail is for.
    local rule = strip:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], TAB_RULE_ALPHA)
    rule:SetPoint("BOTTOMLEFT", strip, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("BOTTOMRIGHT", strip, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)
    strip.rule = rule

    Chat.termTabs = strip
end

-- Hooks the two confirmed dock-selection entry points so the strip updates
-- without polling. hooksecurefunc never runs before the original, so this
-- cannot block or taint Blizzard's own dock handling.
function Chat.HookTabSelection()
    if type(hooksecurefunc) ~= "function" then return end
    if type(FCF_SelectDockFrame) == "function" then
        hooksecurefunc("FCF_SelectDockFrame", Chat.ApplyDockState)
    end
    if type(FCF_Tab_OnClick) == "function" then
        hooksecurefunc("FCF_Tab_OnClick", Chat.ApplyDockState)
    end

    -- The other half of the stale-label fix. Selection hooks only fire when
    -- somebody CHANGES tabs, so nothing repainted the strip between our
    -- Apply() and the player's first click. These two fire when the chat
    -- window settings are read at login and whenever one is renamed, which is
    -- exactly the moment a label can become correct on its own.
    local names = CreateFrame("Frame")
    names:RegisterEvent("UPDATE_CHAT_WINDOWS")
    names:RegisterEvent("UPDATE_FLOATING_CHAT_WINDOWS")
    names:SetScript("OnEvent", Chat.ApplyDockState)

    -- Blizzard re-seats the chat furniture from FCF_SetButtonSide, so a
    -- one-time placement is undone the first time anything touches the dock.
    -- Taken from ElvUI, which hooks the same function for the same reason
    -- (CH:SecureHook('FCF_SetButtonSide', 'PositionButtonFrame')) -- that hook
    -- existing in a mature addon is the evidence that one placement is not
    -- enough, which is cheaper to borrow than to rediscover.
    if type(FCF_SetButtonSide) == "function" then
        hooksecurefunc("FCF_SetButtonSide", function()
            for _, cf in ipairs(Chat.skinnedChatFrames) do
                Chat.SeatScrollFurniture(cf)
            end
        end)
    end
end
