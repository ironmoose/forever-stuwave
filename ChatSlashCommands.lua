-- Forever Synthwave: ChatSlashCommands
-- Split out of the original Chat.lua (2026-09-23): the cycle-tabs affordance,
-- the /fschat + /fstab dispatcher and its diagnostics, late-created window
-- handling (whispers, tear-offs), and the Apply() init that wires up every
-- other Chat* module. Apply() is the one thing that has to run after every
-- other module has defined its exports -- ChatFormat.lua is the one file
-- that still loads after this one (see ForeverSynthwave.toc). Reads/writes
-- the shared FS.Chat state table; see ChatCore.lua's header for why
-- cross-module names live there instead of as locals.

local _, FS = ...
local Chat = FS.Chat

-------------------------------------------------------------------------------
-- Cycle-tabs affordance
-------------------------------------------------------------------------------

-- Cycles the selected docked chat window forward through GeneralDockManager's
-- tab list. No-ops if the dock manager or either FCF function is missing.
-- Exposed globally so the user can bind a key to it later; also wired to
-- /fschat and /fstab below.
function ForeverSynthwave_CycleChatTab()
    if type(FCFDock_GetChatFrames) ~= "function" then return end
    if type(FCF_SelectDockFrame) ~= "function" then return end
    if not GeneralDockManager then return end

    local frames = FCFDock_GetChatFrames(GeneralDockManager)
    if not frames or #frames < 2 then return end

    local currentIndex
    for i, cf in ipairs(frames) do
        if cf == Chat.ActiveChatFrame() then
            currentIndex = i
            break
        end
    end

    local nextIndex = (currentIndex and (currentIndex % #frames) + 1) or 1
    FCF_SelectDockFrame(frames[nextIndex])
end

-- `/fschat` with no argument keeps its old job, cycling the docked tab.
--
-- `/fschat levels` prints the draw order of the terminal chrome against the
-- window it is seated on. That exists because the chrome moved off ChatFrame1
-- and onto UIParent, which makes strata and frame level the only things
-- deciding what is on top -- and "the tabs are behind the bg" is a draw-order
-- report, not a position one. Reading it beats a 200-character /run line, which
-- is also the answer to "don't you have /fsreload and not need to type all
-- that": the RELOAD is short, it was the ad-hoc probes that were long. Probes
-- belong in here.
SLASH_FSCHAT1 = "/fschat"
SLASH_FSCHAT2 = "/fstab"
SlashCmdList["FSCHAT"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")

    -- `/fschat paint` outlines EVERY drawable in the chat stack in a different
    -- colour; `/fschat spill` outlines only the ones that hang outside the
    -- panel border and prints them. Parker's idea, after the invisible frames
    -- defeated three rounds of reasoning from numbers: "you should just update
    -- the lua to go through each part a different color."
    --
    -- Three things the first version got wrong, all of which hid the culprit:
    --
    --   1. It only walked DIRECT CHILDREN. The offender can be a grandchild.
    --   2. It only walked FRAMES. A loose Blizzard TEXTURE region draws just
    --      as visibly and has no children to find it by. Parker: "there is
    --      something there that we are not painting."
    --   3. It FILLED each rect, so the topmost paint hid every rect beneath
    --      it and the whole panel went one colour.
    --
    -- So: recurse, include regions, and draw OUTLINES on a separate overlay
    -- frame. Outlines nest visibly; fills do not. Marking from an overlay
    -- rather than parenting a texture to each object also means the tool
    -- cannot alter what it measures.
    if msg == "paint" or msg == "paintoff" or msg == "spill" then
        local overlay = ForeverSynthwavePaintOverlay
        if not overlay then
            overlay = CreateFrame("Frame", nil, UIParent)
            overlay:SetAllPoints(UIParent)
            overlay:SetFrameStrata("TOOLTIP")
            overlay.marks = {}
            ForeverSynthwavePaintOverlay = overlay
        end
        for _, mark in ipairs(overlay.marks) do mark:Hide() end

        if msg == "paintoff" then
            print("|cff22e0ffsynthwave://chat|r  paint cleared")
            return
        end

        local used = 0
        local function Edge(x1, y1, x2, y2, r, g, b)
            used = used + 1
            local tex = overlay.marks[used]
            if not tex then
                tex = overlay:CreateTexture(nil, "OVERLAY")
                overlay.marks[used] = tex
            end
            tex:ClearAllPoints()
            tex:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", x1, y1)
            tex:SetPoint("TOPRIGHT", UIParent, "BOTTOMLEFT", x2, y2)
            tex:SetColorTexture(r, g, b, 0.9)
            tex:Show()
        end

        -- Effective alpha, computed by WALKING THE PARENTS rather than asking
        -- for it. Region:GetEffectiveAlpha is not reliable on a Texture here:
        -- it reported 1.00 for every region including ones inside a frame we
        -- had explicitly SetAlpha(0), so the filter passed all 24 hits through
        -- and the report was no better than the geometry-only one it replaced.
        --
        -- A missing method returning the "everything is fine" value is the
        -- same silent fallback this file has been bitten by before, so
        -- this does the multiplication itself and treats a hidden ancestor as
        -- zero, which is what actually decides whether Parker can see it.
        local function VisibleAlpha(obj)
            local alpha = (obj.GetAlpha and obj:GetAlpha()) or 1
            local parent = obj.GetParent and obj:GetParent()
            while parent do
                if parent.IsShown and not parent:IsShown() then return 0 end
                alpha = alpha * ((parent.GetAlpha and parent:GetAlpha()) or 1)
                parent = parent.GetParent and parent:GetParent()
            end
            return alpha
        end

        local function Outline(obj, r, g, b)
            local l, rt = obj:GetLeft(), obj:GetRight()
            local t, bt = obj:GetTop(), obj:GetBottom()
            if not (l and rt and t and bt) then return false end
            Edge(l, bt, rt, bt + 2, r, g, b)      -- bottom
            Edge(l, t - 2, rt, t, r, g, b)        -- top
            Edge(l, bt, l + 2, t, r, g, b)        -- left
            Edge(rt - 2, bt, rt, t, r, g, b)      -- right
            return true
        end

        local backdrop = ChatFrame1 and ChatFrame1.fsBackdrop
        if not backdrop then print("no backdrop yet") return end
        local bl, br = backdrop:GetLeft(), backdrop:GetRight()
        local bt, bb = backdrop:GetTop(), backdrop:GetBottom()

        local palette = {
            { 1, 1, 1 }, { 1, 0, 0 }, { 0, 1, 0 }, { 1, 1, 0 }, { 1, 0, 1 },
            { 0, 1, 1 }, { 1, 0.5, 0 }, { 0.6, 0, 1 }, { 0, 0.6, 0.3 },
        }
        local index, scanned, spilled = 0, 0, 0

        local function Consider(obj, label)
            if not obj or (obj.IsShown and not obj:IsShown()) then return end
            local l, r2 = obj.GetLeft and obj:GetLeft(), obj.GetRight and obj:GetRight()
            local t, b2 = obj.GetTop and obj:GetTop(), obj.GetBottom and obj:GetBottom()
            if not (l and r2 and t and b2) then return end

            -- Effective alpha, not IsShown. Half this panel's furniture is
            -- "shown" at alpha 0 because that is how it was silenced, and a
            -- geometry-only report lists all of it as spilling -- 27 hits, of
            -- which most draw nothing. What is asked here is "what can Parker
            -- SEE outside the border", and only alpha answers that.
            local alpha = VisibleAlpha(obj)
            if alpha < 0.05 then return end
            scanned = scanned + 1

            -- Positive means it hangs OUTSIDE the panel on that side.
            local over = math.max(bl - l, r2 - br, t - bt, bb - b2)
            local isSpill = over > 0.5
            if isSpill then spilled = spilled + 1 end
            if msg == "spill" and not isSpill then return end

            index = index + 1
            local c = palette[((index - 1) % #palette) + 1]
            if isSpill then c = { 1, 0, 0 } end
            if not Outline(obj, c[1], c[2], c[3]) then return end

            print(("|cff%02x%02x%02x####|r %-30s %.0fx%.0f L=%.0f R=%.0f a=%.2f%s")
                :format(c[1] * 255, c[2] * 255, c[3] * 255, label,
                    r2 - l, t - b2, l, r2, alpha,
                    isSpill and ("  |cffff2e97SPILL %.1f|r"):format(over) or ""))
        end

        local function Walk(frame, depth, path)
            if depth > 3 then return end
            for i, region in ipairs({ frame:GetRegions() }) do
                Consider(region, ("%s.r%d[%s]"):format(path, i,
                    tostring(region.GetObjectType and region:GetObjectType())))
            end
            for i = 1, select("#", frame:GetChildren()) do
                local child = select(i, frame:GetChildren())
                if child then
                    local name = child.GetName and child:GetName()
                    Consider(child, ("%s.c%d %s"):format(path, i, name or "<anon>"))
                    Walk(child, depth + 1, ("%s.c%d"):format(path, i))
                end
            end
        end

        Consider(backdrop, "fsBackdrop (the border)")
        Walk(ChatFrame1, 1, "cf1")

        print(("|cff22e0ffsynthwave://chat|r  scanned=%d spilled=%d  panel L=%.0f R=%.0f T=%.0f B=%.0f")
            :format(scanned, spilled, bl, br, bt, bb))
        return
    end

    -- `/fschat scroll` dumps the scroll bar's whole subtree. The bar is
    -- anonymous on this client (no ChatFrame1ScrollBar global, only
    -- ChatFrame1.ScrollBar), so the field names its skin depends on -- Track,
    -- Thumb, Back, Forward -- are guesses until something reads them back.
    if msg == "scroll" then
        local bar = ChatFrame1 and ChatFrame1.ScrollBar
        if not bar then print("no ChatFrame1.ScrollBar") return end

        print(("|cff22e0ffscrollbar|r %.0fx%.0f shown=%s alpha=%.2f")
            :format(bar:GetWidth(), bar:GetHeight(), tostring(bar:IsShown()),
                bar:GetAlpha()))
        -- Named fields first, because those are what the skin addresses.
        for _, key in ipairs({ "Background", "Track", "Backplate", "Thumb",
                               "Back", "Forward", "ScrollUpButton",
                               "ScrollDownButton" }) do
            local part = bar[key]
            print(("  .%-18s %s"):format(key, part and
                (tostring(part.GetObjectType and part:GetObjectType()) ..
                 (part.GetWidth and (" %.0fx%.0f"):format(part:GetWidth(), part:GetHeight()) or ""))
                or "nil"))
        end
        local track = bar.Track
        if track then
            print(("  .Track.Thumb       %s"):format(tostring(track.Thumb)))
        end
        local function Dump(obj, prefix)
            for i, region in ipairs({ obj:GetRegions() }) do
                print(("  %s.r%d %s %s atlas=%s"):format(prefix, i,
                    tostring(region:GetObjectType()),
                    (region.GetWidth and ("%.0fx%.0f"):format(region:GetWidth(), region:GetHeight()) or ""),
                    tostring(region.GetAtlas and region:GetAtlas())))
            end
            for i = 1, select("#", obj:GetChildren()) do
                local child = select(i, obj:GetChildren())
                print(("  %s.c%d %s %s shown=%s"):format(prefix, i,
                    tostring(child:GetObjectType()),
                    ("%.0fx%.0f"):format(child:GetWidth(), child:GetHeight()),
                    tostring(child:IsShown())))
                Dump(child, prefix .. ".c" .. i)
            end
        end
        Dump(bar, "bar")
        return
    end

    -- `/fschat api` reports which of the functions these features might use
    -- actually exist on this client, and of what type. Cheaper than shipping a
    -- feature-detect chain and finding out from an error log, and the answer
    -- decides the implementation rather than merely guarding it.
    if msg == "api" then
        local names = {
            -- tab context menu
            "FCF_Tab_OnClick", "FCFTab_OnClick", "FCF_ToggleLock",
            "ChatFrame1Tab", "ChatMenu", "EasyMenu", "MenuUtil",
            "UIDropDownMenu_Initialize", "ToggleDropDownMenu",
            "FCF_ToggleLockOnDockedFrame", "FCF_RenameChatWindow_Popup",
            -- minimize / maximize
            "FCF_MaximizeFrame", "FCF_MinimizeFrame", "FCF_SetWindowSize",
            "FCF_DockUpdate", "FCFDock_GetChatFrames", "FCF_SelectDockFrame",
            "FCF_SetTemporaryWindowType", "GeneralDockManager",
        }
        local found, missing = {}, {}
        for _, name in ipairs(names) do
            local value = _G[name]
            if value == nil then
                missing[#missing + 1] = name
            else
                found[#found + 1] = ("%s=%s"):format(name, type(value))
            end
        end
        -- Methods on the frame itself, which is where 12.0 moved a lot of it.
        local methods = {}
        for _, name in ipairs({ "IsDocked", "SetMinimized", "IsMinimized",
                                "GetMinimized", "AtBottom", "SetJustifyH" }) do
            methods[#methods + 1] = ("%s=%s"):format(name, type(ChatFrame1[name]))
        end
        print("|cff22e0ffFOUND|r   " .. table.concat(found, " "))
        print("|cffff2e97MISSING|r " .. table.concat(missing, " "))
        print("|cff22e0ffMETHODS|r " .. table.concat(methods, " "))
        return
    end

    -- `/fschat min|max|normal` drives the same state machine the two lamps do.
    -- Worth shipping rather than keeping as a test hook: a slash command can go
    -- in a macro and onto a key, which a title-bar button cannot.
    if msg == "min" or msg == "max" or msg == "normal" or msg == "restore" then
        local target = (msg == "restore") and "normal" or msg
        if target == "normal" then
            Chat.windowState = "normal"
            Chat.ApplyWindowState()
        else
            Chat.ToggleWindowState(target)
        end
        print("|cff22e0ffsynthwave://chat|r  window: " .. Chat.windowState)
        return
    end

    if msg == "parts" then
        -- Recon for the pieces we do not own yet: the loose Blizzard buttons
        -- beside the terminal, the scroll widgets, and whether the message
        -- text is overflowing the panel. Dumped to ForeverSynthwaveDB rather
        -- than printed, because there is far too much of it to read in chat.
        ForeverSynthwaveDB = ForeverSynthwaveDB or {}
        local out = { when = date("%Y-%m-%d %H:%M:%S") }

        local function Describe(label, f)
            if not f then out[label] = "nil" return end
            local parent = f.GetParent and f:GetParent()
            out[label] = ("%-28s parent=%-22s shown=%-5s w=%.0f h=%.0f left=%.0f top=%.0f")
                :format(tostring(f.GetName and f:GetName() or "<anon>"),
                    tostring(parent and parent.GetName and parent:GetName() or "<anon>"),
                    tostring(f.IsShown and f:IsShown()),
                    f.GetWidth and f:GetWidth() or -1, f.GetHeight and f:GetHeight() or -1,
                    f.GetLeft and f:GetLeft() or -1, f.GetTop and f:GetTop() or -1)
        end

        -- The three loose buttons, by the names confirmed in the 16001 dump.
        Describe("quickJoin", _G.QuickJoinToastButton)
        Describe("voiceDeafen", _G.ChatFrameToggleVoiceDeafenButton)
        Describe("voiceMute", _G.ChatFrameToggleVoiceMuteButton)
        Describe("menuButton", _G.ChatFrameMenuButton)
        Describe("channelButton", _G.ChatFrameChannelButton)
        Describe("buttonFrame", _G.ChatFrame1ButtonFrame)

        -- Every texture region on the two title buttons, with its atlas or
        -- file path. "Just the icons, no borders" is only verifiable if we can
        -- see WHICH regions are still drawing: a leftover Blizzard backdrop
        -- and a border we forgot to drop look identical on screen.
        local function DescribeRegions(label, f)
            if not f then out[label] = "nil" return end
            local parts = {}
            for _, region in ipairs({ f:GetRegions() }) do
                if region.GetObjectType and region:GetObjectType() == "Texture" then
                    parts[#parts + 1] = ("%s shown=%s a=%.2f tex=%s atlas=%s")
                        :format(tostring(region:GetDrawLayer()),
                            tostring(region:IsShown()), region:GetAlpha() or -1,
                            tostring(region.GetTexture and region:GetTexture()),
                            tostring(region.GetAtlas and region:GetAtlas()))
                end
            end
            out[label] = ("alpha=%.2f | %s"):format(f:GetAlpha() or -1,
                table.concat(parts, " || "))
        end
        DescribeRegions("menuButtonRegions", _G.ChatFrameMenuButton)
        DescribeRegions("channelButtonRegions", _G.ChatFrameChannelButton)

        -- Where each tab label actually comes from. The stale-"chat" bug was
        -- invisible in the rendered strip once anyone clicked a tab, so the
        -- only way to see it is to read all three sources side by side at the
        -- state that reproduces it: freshly loaded, nothing clicked.
        local labels = {}
        for i = 1, Chat.MAX_CHAT_FRAMES do
            local cf = _G["ChatFrame" .. i]
            if not cf then break end
            local tab = _G["ChatFrame" .. i .. "Tab"]
            local text = tab and (tab.Text or _G["ChatFrame" .. i .. "TabText"])
            local ok, stored = pcall(GetChatWindowInfo, i)
            labels[#labels + 1] = ("%d stored=%s tabText=%s cf.name=%s -> %s")
                :format(i, tostring(ok and stored), tostring(text and text:GetText()),
                    tostring(cf.name), tostring(Chat.TabLabel(cf)))
        end
        out.tabLabels = table.concat(labels, " | ")

        -- Overflow: the message frame against the panel that is meant to hold it.
        local cf, bd = ChatFrame1, ChatFrame1 and ChatFrame1.fsBackdrop
        if cf and bd then
            out.overflow = ("chat L=%.1f R=%.1f  panel L=%.1f R=%.1f  spill L=%.1f R=%.1f")
                :format(cf:GetLeft(), cf:GetRight(), bd:GetLeft(), bd:GetRight(),
                    bd:GetLeft() - cf:GetLeft(), cf:GetRight() - bd:GetRight())
        end

        -- The scrollbar is NOT a global on this client (checked against the
        -- 16001 dump: no ChatFrame1ScrollBar, only Wow*ScrollBar* mixins), so
        -- walk the children and report what is actually there.
        local kids = {}
        for i = 1, (cf and cf.GetNumChildren and select("#", cf:GetChildren())) or 0 do
            local child = select(i, cf:GetChildren())
            if child then
                kids[#kids + 1] = ("%s[%s] %.0fx%.0f shown=%s")
                    :format(tostring(child.GetName and child:GetName() or "<anon>"),
                        tostring(child.GetObjectType and child:GetObjectType()),
                        child:GetWidth() or -1, child:GetHeight() or -1,
                        tostring(child:IsShown()))
            end
        end
        out.chatChildren = table.concat(kids, " | ")

        -- Does the TEXT itself overhang the frame that holds it? Parker:
        -- "Some of the text is overlapping the white bg."
        --
        -- Frames do NOT clip their children unless told to, so a message line
        -- wider than its container simply draws past it. The message
        -- fontstrings live on an anonymous child, not on ChatFrame1's own
        -- regions, so this walks one level down as well.
        local worst, overhanging, total = 0, 0, 0
        local function ScanText(host)
            if not host then return end
            for _, region in ipairs({ host:GetRegions() }) do
                if region.GetObjectType and region:GetObjectType() == "FontString"
                    and region:IsShown() and (region:GetText() or "") ~= "" then
                    total = total + 1
                    local right = region:GetRight()
                    if right and cf:GetRight() then
                        local over = right - cf:GetRight()
                        if over > 0.5 then
                            overhanging = overhanging + 1
                            if over > worst then worst = over end
                        end
                    end
                end
            end
        end
        ScanText(cf)
        for i = 1, (cf and select("#", cf:GetChildren())) or 0 do
            ScanText((select(i, cf:GetChildren())))
        end
        out.textOverhang = ("%d/%d lines overhang ChatFrame1, worst=%.1fpx | cf R=%.1f w=%.1f")
            :format(overhanging, total, worst, cf and cf:GetRight() or -1,
                cf and cf:GetWidth() or -1)
        out.scrollBarField = tostring(cf and cf.ScrollBar)

        ForeverSynthwaveDB.chatParts = out
        print("|cff22e0ffsynthwave://chat|r  parts written to ForeverSynthwaveDB")
        return
    end

    if msg ~= "levels" then
        return ForeverSynthwave_CycleChatTab()
    end

    -- Also recorded into ForeverSynthwaveDB, not just printed. A chat line is
    -- readable by whoever is sitting at the client; the saved variable is
    -- readable by fsdev.py, which is what turns "the tabs are behind the bg"
    -- into numbers someone can act on without a screenshot round trip.
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    local report = { when = date("%Y-%m-%d %H:%M:%S") }

    local function describe(label, f)
        if not f then
            report[label] = "nil"
            print(("|cff22e0ff%-10s|r  nil"):format(label))
            return
        end
        local name = (f.GetName and f:GetName()) or "<anon>"
        -- Alpha as well as level, because "it is behind the background" and
        -- "it is drawn on top at a fifth of its colour" look identical on
        -- screen and have nothing to do with each other. GetAlpha is this
        -- frame's own; GetEffectiveAlpha multiplies in every parent, which is
        -- where an inherited fade would hide.
        -- GEOMETRY as well, because level and alpha together still cannot tell
        -- you that a frame is half-swallowed by the one below it. Parker's
        -- screenshot of the COMBAT LOG selected shows the tab glyphs sheared
        -- in half by the panel's top edge, which no amount of correct strata
        -- would show up in -- and which the chat-tab measurement missed
        -- entirely, because it only goes wrong on the other window.
        local line = ("%-18s strata=%-12s level=%-4s shown=%-5s alpha=%.2f eff=%.2f top=%.1f bottom=%.1f h=%.1f")
            :format(name,
                tostring(f.GetFrameStrata and f:GetFrameStrata()),
                tostring(f.GetFrameLevel and f:GetFrameLevel()),
                tostring(f.IsShown and f:IsShown()),
                f.GetAlpha and f:GetAlpha() or -1,
                f.GetEffectiveAlpha and f:GetEffectiveAlpha() or -1,
                f.GetTop and f:GetTop() or -1,
                f.GetBottom and f:GetBottom() or -1,
                f.GetHeight and f:GetHeight() or -1)
        report[label] = line
        print(("|cff22e0ff%-10s|r  %s"):format(label, line))
    end

    local c = ForeverSynthwaveTermChrome
    if not c then
        report.error = "chrome not seated yet"
        ForeverSynthwaveDB.chatLevels = report
        print("|cff22e0ffsynthwave://chat|r  chrome not seated yet")
        return
    end

    -- Seated-on vs actually-selected, side by side. If SeatTerminalChrome ever
    -- misses a selection change these disagree, and then the chrome is sitting
    -- in the band reserved by a window that is no longer the visible one --
    -- which would put it straight underneath the one that is.
    report.seatedVsSelected = ("seated=%s selected=%s"):format(
        tostring(c.target and c.target.GetName and c.target:GetName()),
        tostring(SELECTED_CHAT_FRAME and SELECTED_CHAT_FRAME.GetName
            and SELECTED_CHAT_FRAME:GetName()))
    print("|cff22e0ffseat|r  " .. report.seatedVsSelected)

    -- The container first, because it is the single highest-value reading in
    -- this whole probe. Everything else in the terminal takes its strata from
    -- this one frame; if the max-state strata/level change never lands here,
    -- nothing downstream can be right either, and if it DOES land here the bug
    -- is somewhere in what is built on top of it, not in the container itself.
    describe("termpanel", Chat.termPanel)
    -- GeneralDockManager is reparented into the container (see the seating
    -- code above); ApplyDockState (ChatTabs.lua) DOES set its frame level on
    -- every pass, to the container's own level plus LEVEL_DOCK. That is no
    -- longer an open question -- this probe just reports the level that
    -- gets assigned.
    describe("dockmgr", GeneralDockManager)

    describe("selected", c.target)
    describe("backdrop", c.backdrop)
    describe("termbar", c.bar)
    describe("termtabs", c.tabs)
    describe("editbox", c.target and _G[(c.target:GetName() or "") .. "EditBox"])
    describe("buttons", c.target and _G[(c.target:GetName() or "") .. "ButtonFrame"])
    -- Per pill, because the strip can be perfectly placed and fully opaque
    -- while the LABELS are the thing that is faint. GetTextColor is the only
    -- way to tell an active pill that was never repainted from one that was
    -- painted correctly and is being washed out by something else.
    for i, pill in ipairs(Chat.termTabs and Chat.termTabs.pills or {}) do
        local label = pill.label
        local r, g, b, a = 0, 0, 0, 0
        if label and label.GetTextColor then r, g, b, a = label:GetTextColor() end
        report["pill" .. i] = ("%-12s active=%-5s alpha=%.2f eff=%.2f rgba=%.2f,%.2f,%.2f,%.2f wash=%s")
            :format(tostring(label and label:GetText()), tostring(pill.isActive),
                pill:GetAlpha(), pill:GetEffectiveAlpha(), r, g, b, a,
                tostring(pill.wash and pill.wash:IsShown()))
        print(("|cff22e0ff%-10s|r  %s"):format("pill" .. i, report["pill" .. i]))
    end

    -- Every docked window and ITS backdrop, not just the seated one. The
    -- backdrop is anchored to its own chat frame with fixed padding, so its
    -- height is whatever that frame's height is -- and if the dock does not
    -- hand every window the same height, the panel changes size as you switch
    -- tabs. Comparing them is the only way to see that.
    for i, cf in ipairs(Chat.DockedChatFrames()) do
        local bd = cf.fsBackdrop
        report["dock" .. i] = ("%-12s shown=%-5s h=%-7.1f top=%-7.1f bottom=%-7.1f | "
            .. "backdrop h=%-7.1f top=%-7.1f bottom=%.1f")
            :format(tostring(cf.GetName and cf:GetName()),
                tostring(cf:IsShown()), cf:GetHeight(), cf:GetTop() or -1, cf:GetBottom() or -1,
                bd and bd:GetHeight() or -1,
                bd and bd:GetTop() or -1,
                bd and bd:GetBottom() or -1)
        print(("|cff22e0ff%-10s|r  %s"):format("dock" .. i, report["dock" .. i]))
    end

    -- The real Blizzard tab, not our pill. HideBlizzardTab leaves the tab
    -- frame SHOWN at alpha 0 and hides every region it draws instead (alpha
    -- alone did not survive the dock's own layout pass -- see that function's
    -- comment). shownRegions/totalRegions is the direct measurement of
    -- whether that hide is still in effect or something has undone it; a tab
    -- with regions showing again is the tabs-drawing-over-the-panel symptom
    -- caught at its source instead of guessed at from a screenshot.
    for i, cf in ipairs(Chat.DockedChatFrames()) do
        local tab = _G[(cf.GetName and cf:GetName() or "") .. "Tab"]
        if tab then
            -- Built in two steps, not the usual `a and b() or c` one-liner:
            -- GetRegions() returns multiple values, and folded into an "and"
            -- like that Lua truncates it to just the first one.
            local regions = {}
            if tab.GetRegions then regions = { tab:GetRegions() } end
            local shownRegions, totalRegions = 0, 0
            for _, region in ipairs(regions) do
                totalRegions = totalRegions + 1
                if region.IsShown and region:IsShown() then
                    shownRegions = shownRegions + 1
                end
            end
            report["blizztab" .. i] = ("%-18s strata=%-12s level=%-4s shown=%-5s alpha=%.2f "
                .. "fsHidden=%-5s regions=%d/%d")
                :format(tab.GetName and tab:GetName() or "<anon>",
                    tostring(tab.GetFrameStrata and tab:GetFrameStrata()),
                    tostring(tab.GetFrameLevel and tab:GetFrameLevel()),
                    tostring(tab.IsShown and tab:IsShown()),
                    tab.GetAlpha and tab:GetAlpha() or -1,
                    tostring(tab.fsTabHidden),
                    shownRegions, totalRegions)
        else
            report["blizztab" .. i] = "nil"
        end
        print(("|cff22e0ff%-10s|r  %s"):format("blizztab" .. i, report["blizztab" .. i]))
    end

    ForeverSynthwaveDB.chatLevels = report
    print("  higher level wins WITHIN a strata; across strata the strata wins.")
end

-------------------------------------------------------------------------------
-- Late-created windows (whispers, temporary tear-offs)
-------------------------------------------------------------------------------

-- Runs the existing per-frame skin (+ tab color refresh) on a chat window
-- created after login. frame:GetID() is the numeric N that names ChatFrameN,
-- which holds for temporary/tear-off windows too.
local function SkinLateChatFrame(frame)
    if not frame or not frame.GetID then return end
    local index = frame:GetID()
    if not index or index < 1 then return end

    Chat.SkinChatFrame(frame, index)
    -- A late window (whisper, combat log) joins the dock, so the strip has a
    -- new pill to draw and Blizzard has a new tab to hide.
    Chat.HideAllBlizzardTabs()
    Chat.ApplyDockState()
end

-- Hooks the two window-creation entry points so whisper windows and
-- FCF_OpenNewWindow tear-offs get skinned without polling. hooksecurefunc
-- hands the hook the ORIGINAL call's arguments, not its return value, so
-- identifying the created frame also requires FCF_GetCurrentChatFrame
-- (Blizzard selects the new/reused frame before returning); that lookup is
-- feature-detected the same as the two hook targets.
local function HookLateWindowCreation()
    if type(hooksecurefunc) ~= "function" then return end
    if type(FCF_GetCurrentChatFrame) ~= "function" then return end

    if type(FCF_OpenTemporaryWindow) == "function" then
        hooksecurefunc("FCF_OpenTemporaryWindow", function()
            SkinLateChatFrame(FCF_GetCurrentChatFrame())
        end)
    end

    if type(FCF_OpenNewWindow) == "function" then
        hooksecurefunc("FCF_OpenNewWindow", function()
            SkinLateChatFrame(FCF_GetCurrentChatFrame())
        end)
    end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Chat frames are plain non-secure frames, so none of this is combat-illegal;
-- deferred anyway for consistency with the rest of the addon's Init pattern.
local function Apply()
    -- First, so the seat log starts at our own first seat and Blizzard's
    -- first-login Edit Mode re-seat is caught from here on.
    Chat.HookPrimaryChatReseat()

    for i = 1, Chat.MAX_CHAT_FRAMES do
        local frame = _G["ChatFrame" .. i]
        if not frame then break end
        Chat.SkinChatFrame(frame, i)
    end

    Chat.SeatPrimaryChat(_G["ChatFrame1"])
    Chat.HideAllBlizzardTabs()

    -- Restore the collapsed/maximised state before the first paint, so a
    -- minimised chat does not flash full size on every reload. Validated
    -- against the three known values rather than trusted: this is saved
    -- variables, which anything can have written.
    local saved = ForeverSynthwaveDB and ForeverSynthwaveDB.chatWindowState
    if saved == "min" or saved == "max" or saved == "normal" then
        Chat.windowState = saved
    end
    if Chat.windowState ~= "normal" then
        Chat.ApplyWindowState()
    else
        Chat.ApplyDockState()
    end

    -- Snapshot the labels AT THE MOMENT THAT REPRODUCES THE BUG. Reading them
    -- from a slash command afterwards proves nothing: by then the chat windows
    -- have finished setting up and every source agrees. The only state worth
    -- measuring is this one, before anything has been clicked.
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    local snap = {}
    for _, cf in ipairs(Chat.DockedChatFrames()) do
        snap[#snap + 1] = Chat.TabLabel(cf)
    end
    ForeverSynthwaveDB.labelsAtApply = table.concat(snap, ",")
    Chat.HookTabSelection()
    HookLateWindowCreation()
    Chat.HookEditBoxArrowKeys()
    Chat.HookPromptSeating()
end

if InCombatLockdown() then
    local regen = CreateFrame("Frame")
    regen:RegisterEvent("PLAYER_REGEN_ENABLED")
    regen:SetScript("OnEvent", function(self)
        self:UnregisterEvent("PLAYER_REGEN_ENABLED")
        Apply()
    end)
else
    Apply()
end
