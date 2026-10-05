-- Forever STUwave: ChatEditBox
-- Split out of the original Chat.lua (2026-09-23): the chat edit box -- hiding
-- Blizzard's own art, the ">" prompt caret, seating and focus glow, and the
-- arrow-key behaviour change. Reads/writes the shared FS.Chat state table; see
-- ChatCore.lua's header for why cross-module names live there instead of as
-- locals.

local _, FS = ...
local Chat = FS.Chat

local ApplyMono = FS.Theme.ApplyMono

-------------------------------------------------------------------------------
-- Edit box
-------------------------------------------------------------------------------

-- EditBox is itself a FontInstance (native SetFont/SetTextColor/SetShadow*),
-- so ApplyMono can restyle it directly without hunting for a child fontstring.
-- Blizzard's own edit-box art -- the pale rounded border in the default UI --
-- sits ON TOP of anything we draw, so the box read as stock with our chrome
-- hidden behind it. Names confirmed in the 16001 globals dump:
--   ChatFrameNEditBox{Left,Mid,Right}            the resting border
--   ChatFrameNEditBoxFocus{Left,Mid,Right}       the focus glow
-- SetAlpha rather than Hide: Blizzard's focus handlers call Show() on the Focus
-- set when the box gains focus, and a hidden-then-shown texture would pop back.
local BLIZZARD_EDITBOX_TEXTURES = {
    "Left", "Mid", "Right",
    "FocusLeft", "FocusMid", "FocusRight",
}

function Chat.HideBlizzardEditBoxArt(index)
    for _, suffix in ipairs(BLIZZARD_EDITBOX_TEXTURES) do
        local region = _G["ChatFrame" .. index .. "EditBox" .. suffix]
        if region and region.SetAlpha then
            region:SetAlpha(0)
        end
    end
end

-- Mockup, .termbody .prompt + .cursor:
--     .prompt { color: var(--green) }                      -- #39ff14
--     .cursor { width:6px; height:11px; background:var(--green);
--               box-shadow:0 0 6px var(--green);
--               animation: blink 1s steps(1) infinite }
--
-- The input is a PROMPT LINE inside the terminal, not a box: no border, no
-- ground, a green ">" and a blinking green BLOCK caret. The previous pass drew
-- a bordered slab, which is what Parker meant by "doesn't look like the mockup
-- with the carret".
local COLOR_PROMPT = { 0.224, 1, 0.078, 1 }   -- --green #39ff14
local CARET_W = 6
local CARET_H = 11
local PROMPT_GAP = 6                          -- gap between ">" and the text
-- Caret geometry, matched against VS Code's block cursor, which is what Parker
-- pointed at as the reference. Measured off his screenshot of it: the block's
-- top is level with the ASCENDERS (the tops of l, k, d, h) and its bottom sits
-- a couple of pixels BELOW the baseline -- it covers the character cell, not
-- the line box.
--
-- The engine reports the full line box and anchors it at the top, so ours was
-- wrong at both ends: proud above the cap height, and stopping dead on the
-- baseline.
--
-- Two independent constants rather than one offset, because "move it down"
-- alone would push the bottom past the baseline and overshoot the look it is
-- copying.
--
-- MEASURE THESE ON A 1:1 CROP. The first pass read them off a full-screen
-- screenshot that had been scaled to 0.78 and treated the rows as native
-- pixels, which put the trim at 9 instead of 3 and dropped the block six
-- pixels below the text. A native crop of the prompt line gives:
--   row  9  "Say:" cap height      <- where the block top belongs
--   row 20  baseline
--   row 23  block bottom           <- 3 below the baseline, as VS Code has it
-- How far the glow extends past the block on each axis, total. The halo is
-- re-sized from the block's REAL height on every cursor move; see AddPromptCaret.
local GLOW_PAD = 12
local CARET_TOP_TRIM = 3    -- pull the top down onto the cap height
local CARET_BOTTOM_DROP = 3 -- ... and let the bottom sit below the baseline

-- Blizzard's native text cursor is a thin vertical line drawn by the engine.
-- There is NO API to hide or recolour it -- that is not a guess, it is the
-- whole EditBox method surface in the client's own
-- Blizzard_APIDocumentationGenerated: the only cursor-related entries are
-- GetCursorPosition, SetCursorPosition, GetBlinkSpeed and SetBlinkSpeed.
--
-- So it is COVERED rather than hidden: the block is drawn at the same cursor
-- position, opaque, wider and at least as tall. Two consequences follow, and
-- both are deliberate:
--
--  * SetBlinkSpeed(0) parks Blizzard's caret in a single phase, and measuring
--    it settled which phase: INVISIBLE. A screenshot of the rows just above
--    the block came back empty, so the block is free to blink like the mock's
--    without ever uncovering a line underneath.
--  * Sitting mid-line, the block hides the character under it. That is what a
--    terminal block cursor does, and at the end of a line -- where the cursor
--    almost always is -- there is nothing under it anyway.
local function AddPromptCaret(editBox)
    local caret = editBox:CreateTexture(nil, "OVERLAY", nil, 2)
    caret:SetColorTexture(COLOR_PROMPT[1], COLOR_PROMPT[2], COLOR_PROMPT[3], 1)
    caret:SetSize(CARET_W, CARET_H)
    caret:SetPoint("LEFT", editBox, "LEFT", 0, 0)

    -- box-shadow: 0 0 6px var(--green). Centred on the block, and RESIZED with
    -- it in OnCursorChanged below -- sizing it here from the CARET_H constant
    -- was wrong, because the block's real height comes from the engine and
    -- changes with the font. The halo stayed a fixed 23px tall while the block
    -- shrank to 11, so it hung past both ends (and bled into the rows I was
    -- measuring the block from, which is how the trim came out wrong twice).
    local glow = editBox:CreateTexture(nil, "OVERLAY", nil, 1)
    glow:SetTexture(Chat.GLOW_ROUND_TEXTURE)
    glow:SetBlendMode("ADD")
    glow:SetVertexColor(COLOR_PROMPT[1], COLOR_PROMPT[2], COLOR_PROMPT[3], 0.55)
    glow:SetPoint("CENTER", caret, "CENTER", 0, 0)
    glow:SetSize(CARET_W + GLOW_PAD, CARET_H + GLOW_PAD)

    -- OnCursorChanged's x is measured from the TEXT ORIGIN, not from the edit
    -- box's left edge, so it has to be pushed out by the left text inset --
    -- which is exactly the width of "> Say:". Dropping it put the block that
    -- many pixels early, landing it mid-word while Blizzard's line sat at the
    -- end. Read back with GetTextInsets rather than recomputed, so it cannot
    -- drift from whatever SeatPrompt last set.
    editBox:HookScript("OnCursorChanged", function(self, x, y, _, height)
        local insetLeft = self.GetTextInsets and self:GetTextInsets() or 0
        height = (height and height > 0) and height or CARET_H

        -- y is measured DOWN from the box top and arrives already negative, so
        -- pushing the top down means subtracting further.
        local blockHeight = math.max(height - CARET_TOP_TRIM + CARET_BOTTOM_DROP, 4)

        caret:ClearAllPoints()
        caret:SetPoint("TOPLEFT", self, "TOPLEFT", insetLeft + x, y - CARET_TOP_TRIM)
        caret:SetHeight(blockHeight)

        -- The halo has to follow the block, or it hangs past it.
        glow:SetSize(CARET_W + GLOW_PAD, blockHeight + GLOW_PAD)
    end)

    -- Blizzard's own caret occupies the strip the block just vacated, and there
    -- is no API to hide it -- the entire EditBox surface in the client's
    -- generated docs offers only GetCursorPosition, SetCursorPosition,
    -- GetBlinkSpeed and SetBlinkSpeed. SetBlinkSpeed(0) parks it in one phase
    -- rather than toggling; which phase is undocumented.
    --
    -- So this is a MEASUREMENT, not a known fix. If a pale sliver of line shows
    -- above the block, the parked phase is "visible" and CARET_DROP has to go
    -- back to 0 -- at which point dropping the block and hiding Blizzard's are
    -- genuinely mutually exclusive, and that is worth saying out loud rather
    -- than quietly picking one.
    if editBox.SetBlinkSpeed then
        editBox:SetBlinkSpeed(0)
    end

    -- steps(1) is a hard on/off, not a fade: two Alpha animations with
    -- from == to. Engine-side, so nothing runs per frame for something that
    -- pulses the whole time a line is being typed.
    -- Blinks the block AND its glow together, as one group on the block: with
    -- the native caret parked invisible there is nothing left to cover, so
    -- this can follow the mock exactly. The glow is parented to the block for
    -- position but alpha has to be driven on both.
    local group = caret.CreateAnimationGroup and caret:CreateAnimationGroup()
    if group then
        group:SetLooping("REPEAT")
        for order, alpha in ipairs({ 1, 0 }) do
            local step = group:CreateAnimation("Alpha")
            step:SetFromAlpha(alpha)
            step:SetToAlpha(alpha)
            step:SetDuration(0.5)
            step:SetOrder(order)
        end

        local glowGroup = glow.CreateAnimationGroup and glow:CreateAnimationGroup()
        if glowGroup then
            glowGroup:SetLooping("REPEAT")
            for order, alpha in ipairs({ 0.55, 0 }) do
                local step = glowGroup:CreateAnimation("Alpha")
                step:SetFromAlpha(alpha)
                step:SetToAlpha(alpha)
                step:SetDuration(0.5)
                step:SetOrder(order)
            end
            glowGroup:Play()
        end

        group:Play()
    end

    return caret, glow
end

function Chat.StyleEditBox(editBox)
    if not editBox or editBox.fsChatSkin then return end
    if not editBox.CreateTexture then return end

    if editBox.SetFont and editBox.GetFont then
        local _, size = editBox:GetFont()
        ApplyMono(editBox, size or 12)
    end
    -- Deliberately NOT recoloured. The mock's prompt line is all green, but
    -- Blizzard sets the edit box text colour per channel inside
    -- ChatEdit_UpdateHeader (guild green, whisper pink, and so on) and would
    -- overwrite anything set here on the next Tab. Fighting it would also lose
    -- a genuinely useful signal about where the line is going, so the ">" and
    -- the caret carry the green and the text keeps its channel colour.

    -- The ">" lives on its OWN frame, not on the edit box, and that is the
    -- whole fix for "the > is still behind the chat bg when not active".
    --
    -- It was never behind anything. Measured at the moment the box loses
    -- focus, Blizzard drops the edit box from DIALOG back to LOW *and fades it
    -- to alpha 0.35*. The prompt is OVERLAY at alpha 1.0 on top of it, but
    -- alpha is INHERITED MULTIPLICATIVELY, so it renders at 0.35 over an
    -- opaque backdrop -- which looks identical to being covered by it. An
    -- earlier pass raised the edit box's strata and fixed nothing, because
    -- z-order was never what was wrong.
    --
    -- Re-asserting SetAlpha(1) from a focus-lost hook would be a race against
    -- whatever Blizzard fades it with. A separate host cannot be faded by the
    -- edit box at all, so the prompt is full strength by construction, focused
    -- or not. Anchored to the edit box, so it still tracks it exactly.
    local promptHost = editBox.fsChatPromptHost
    if not promptHost then
        promptHost = CreateFrame("Frame", nil, Chat.termPanel)
        editBox.fsChatPromptHost = promptHost
    end
    promptHost:SetAllPoints(editBox)

    -- Visibility has to be mirrored BY HAND, and forgetting it puts a stray
    -- ">" in the middle of the panel. As a child of the edit box the prompt
    -- was hidden for free whenever the box was; on its own frame under
    -- UIParent nothing hides it, so every docked-but-inactive window's prompt
    -- draws over the message area at its own edit box's position.
    promptHost:SetShown(editBox:IsShown())
    editBox:HookScript("OnShow", function(self)
        if self.fsChatPromptHost then self.fsChatPromptHost:Show() end
    end)
    editBox:HookScript("OnHide", function(self)
        if self.fsChatPromptHost then self.fsChatPromptHost:Hide() end
    end)

    local prompt = promptHost:CreateFontString(nil, "OVERLAY")
    ApplyMono(prompt, 12, COLOR_PROMPT)
    prompt:SetText(">")
    prompt:SetPoint("LEFT", promptHost, "LEFT", 0, 0)
    editBox.fsChatPrompt = prompt

    -- The channel label ("Say:", "Guild:") is a separate fontstring. The mockup
    -- shows a bare ">" with no label, but dropping it means no visible
    -- difference between typing into say and typing into guild, which is a real
    -- way to say the wrong thing in the wrong place. Kept, restyled onto the
    -- prompt line, and seated after the ">" by SeatPrompt -- a deliberate
    -- deviation from the mock, not a miss.
    local header = editBox.GetName and _G[editBox:GetName() .. "Header"]
    if header and ApplyMono then
        local _, headerSize = header:GetFont()
        ApplyMono(header, headerSize or 12, FS.Theme.COLOR_POWER)
    end

    editBox.fsChatCaret, editBox.fsChatCaretGlow = AddPromptCaret(editBox)

    -- Records the z-order AT THE MOMENT THE BOX GOES INACTIVE, which is the
    -- only state the ">" bug exists in and the one state no typed probe can
    -- ever see: sending /fschat levels through the chat box ACTIVATES the box,
    -- so the probe measures the good state and reports everything is fine.
    -- Hooked to the focus-lost event rather than deferred on a timer, because
    -- a timer races the dev tool's own keystrokes for the reload.
    editBox:HookScript("OnEditFocusLost", function(self)
        ForeverSTUwaveDB = ForeverSTUwaveDB or {}
        local chrome = ForeverSTUwaveTermChrome
        local backdrop = chrome and chrome.backdrop
        local idlePrompt = self.fsChatPrompt
        -- EFFECTIVE alpha on the host is the number that matters: the prompt's
        -- own alpha was always 1.00 and told us nothing, because the fade it
        -- was suffering belonged to its parent.
        local host = self.fsChatPromptHost
        ForeverSTUwaveDB.promptIdle = ("editbox strata=%s level=%s shown=%s alpha=%.2f"
            .. " | backdrop strata=%s level=%s | host strata=%s level=%s eff=%.2f"
            .. " | prompt layer=%s shown=%s alpha=%.2f")
            :format(tostring(self:GetFrameStrata()), tostring(self:GetFrameLevel()),
                tostring(self:IsShown()), self:GetAlpha() or -1,
                tostring(backdrop and backdrop:GetFrameStrata()),
                tostring(backdrop and backdrop:GetFrameLevel()),
                tostring(host and host:GetFrameStrata()),
                tostring(host and host:GetFrameLevel()),
                (host and host:GetEffectiveAlpha()) or -1,
                tostring(idlePrompt and idlePrompt:GetDrawLayer()),
                tostring(idlePrompt and idlePrompt:IsShown()),
                (idlePrompt and idlePrompt:GetAlpha()) or -1)
    end)

    editBox.fsChatSkin = true
end

-- Pushes the typed text (and Blizzard's channel header) clear of the ">".
--
-- Blizzard recomputes both the header anchor and the text insets inside
-- ChatEdit_UpdateHeader every time the channel changes, so setting them once
-- would last until the first Tab press. Re-applied from a hook on it.
function Chat.SeatPrompt(editBox)
    local prompt = editBox and editBox.fsChatPrompt
    if not prompt then return end

    local offset = prompt:GetStringWidth() + PROMPT_GAP

    local header = editBox.GetName and _G[editBox:GetName() .. "Header"]
    if header and header:IsShown() then
        header:ClearAllPoints()
        header:SetPoint("LEFT", editBox, "LEFT", offset, 0)
        offset = offset + header:GetStringWidth() + PROMPT_GAP
    end

    if editBox.SetTextInsets then
        editBox:SetTextInsets(offset, 8, 0, 0)
    end
end

local promptHookInstalled = false
function Chat.HookPromptSeating()
    if promptHookInstalled then return end
    if type(hooksecurefunc) ~= "function" then return end
    if type(ChatEdit_UpdateHeader) ~= "function" then return end

    hooksecurefunc("ChatEdit_UpdateHeader", Chat.SeatPrompt)
    promptHookInstalled = true
end

-- WoW ships chat edit boxes in ALT-arrow mode: plain Left/Right steer the
-- character and only Alt+Arrow walks the text cursor, so a typed line cannot be
-- edited without a modifier. Measured on this client --
-- ChatFrame1EditBox:GetAltArrowKeyMode() returned 1 -- and clearing it fixed it
-- live. This is Blizzard's default, not something the skin caused.
--
-- Deliberately NOT guarded by a once-flag: Blizzard re-asserts the mode when a
-- chat box is activated, so this has to be cheap and re-runnable. It is a plain
-- setter on a non-secure frame, so calling it repeatedly costs nothing.
--
-- To restore Blizzard's behaviour, delete this function and its call sites.
function Chat.ApplyEditBoxArrowKeys(editBox)
    if not editBox then return end
    if type(editBox.SetAltArrowKeyMode) ~= "function" then return end
    editBox:SetAltArrowKeyMode(false)
end

-- Re-applies the arrow-key mode whenever Blizzard activates a chat edit box,
-- which is the point it would otherwise be reset back to the default.
local arrowKeyHookInstalled = false
function Chat.HookEditBoxArrowKeys()
    if arrowKeyHookInstalled then return end
    if type(hooksecurefunc) ~= "function" then return end
    if type(ChatEdit_ActivateChat) ~= "function" then return end

    hooksecurefunc("ChatEdit_ActivateChat", Chat.ApplyEditBoxArrowKeys)
    arrowKeyHookInstalled = true
end

-- Re-anchors the edit box into the bottom of the terminal, in the gap
-- PAD_BOTTOM reserves for it, instead of leaving it as a detached slab below
-- the chat frame. Blizzard re-anchors it whenever the chat dock changes, so the
-- placement is re-applied on show rather than set once.
function Chat.SeatEditBox(editBox, backdrop)
    if not editBox or not backdrop then return end

    local function Seat()
        editBox:ClearAllPoints()
        editBox:SetPoint("BOTTOMLEFT", backdrop, "BOTTOMLEFT", Chat.EDITBOX_MARGIN, Chat.EDITBOX_MARGIN)
        editBox:SetPoint("BOTTOMRIGHT", backdrop, "BOTTOMRIGHT", -Chat.EDITBOX_MARGIN, Chat.EDITBOX_MARGIN)
        editBox:SetHeight(Chat.EDITBOX_HEIGHT)
    end

    Seat()
    if not editBox.fsSeatHook then
        editBox:HookScript("OnShow", Seat)
        editBox.fsSeatHook = true
    end
end

-- There is no border left to brighten -- the input is a prompt line now -- so
-- focus is signalled by the caret instead: shown and blinking while the box
-- holds focus, hidden when it does not. Guarded by fsChatFocusHook so a second
-- call never double-installs the hooks.
function Chat.HookEditBoxFocusGlow(editBox)
    if not editBox or editBox.fsChatFocusHook then return end
    if not editBox.HookScript then return end

    local caret, glow = editBox.fsChatCaret, editBox.fsChatCaretGlow

    -- Hidden unless the box has focus, which is Parker's call after seeing the
    -- passive version: "you can hide the blinking cursor unless you are going
    -- to type something."
    --
    -- The passive caret was tried and reverted. Shown without focus it drew
    -- BEHIND the chat panel -- the edit box only wins the z fight once it is
    -- focused and the client raises it, and a caret that is present but buried
    -- is worse than no caret. Hiding it sidesteps that entirely, and focus
    -- stays signalled by the caret appearing.
    editBox:HookScript("OnEditFocusGained", function(self)
        if caret then caret:Show() end
        if glow then glow:Show() end
        Chat.SeatPrompt(self)
    end)
    editBox:HookScript("OnEditFocusLost", function(_)
        if caret then caret:Hide() end
        if glow then glow:Hide() end
        -- Re-assert the layer. Seating it once is not enough: the client
        -- raises the edit box on focus and drops it again on blur, which put
        -- the ">" back behind the panel -- "this is still behind the terminal
        -- bg when the input is inactive."
        Chat.SeatTerminalChrome()
    end)

    if caret then caret:Hide() end
    if glow then glow:Hide() end

    editBox.fsChatFocusHook = true
end
