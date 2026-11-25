local _, FS = ...

-- The class modules explained, ONE source for two readers:
--   * the Help page in /fsconfig (ConfigWindow.lua), which draws the pictures, pins and arrows from Layout() below,
--     and the Gunsight HUD page's class ? tip (Tip());
--   * tools/assets/help_pictures.py, which runs this same file to bake the picture atlas and to render the same
--     annotated images and numbered lines for the CurseForge listing.
-- Change a word or a pin here and both follow.
--
-- A class has one page, or a few (Druid forms, Mage specs) with a `label` each. A page has:
--   picture  a picture name (tools/assets/help_frames/<name>.png, packed into help_pictures.tga by the generator)
--   lines    { name, text }, numbered in order; line n is explained by pin n or extra picture n
--   pins     { n, targetX, targetY, pinX, pinY } in picture pixels (one per art pixel). The pin may sit in the margin
--            round the picture; the arrow leaves the pin square on its long axis and turns once, so it stays square
--   extras   { n = line number, picture = name }: a part that only shows in another state, drawn small below
--   note     optional plain line after the numbered ones
-- A line with neither a pin nor an extra is listed with a dashed number.

local H = {}
FS.HelpModules = H

H.SCALE = 2          -- screen pixels per picture pixel for the main picture; extras draw at 1
H.MARGIN = 17        -- picture pixels of margin round the main picture, where the pins sit
H.PIN = 18           -- pin square, screen pixels
H.LINE = 2           -- arrow thickness, screen pixels
H.GAP = 10           -- between extras, and between the picture and the extras
H.CAPTION = 18       -- height of the caption row above the extras

H.ORDER = { "WARRIOR", "PALADIN", "HUNTER", "ROGUE", "PRIEST", "SHAMAN", "MAGE", "WARLOCK", "DRUID" }

H.CLASSES = {
    WARRIOR = { pages = { {
        picture = "warrior",
        lines = {
            { "Red helm", "Battle Shout. The runes around it go dark as the shout runs out." },
            { "Violet helm", "Demoralizing Shout, same idea." },
            { "Amber, pulsing helm", "your shout is down. Shout again. Click a helm to cast it." },
            { "Bar under the helms", "Overpower, Revenge or Victory Rush is ready. Use it before the bar runs out." },
            { "Big alert over your character", "the same chances, big enough to catch from the corner of your eye. Each one can be turned off." },
        },
        pins = { { 1, 8, 35, -9, 35 }, { 2, 114, 5, 114, -9 }, { 4, 20, 84, -9, 84 } },
        extras = { { n = 3, picture = "warrior_down" }, { n = 5, picture = "warrior_alert" } },
    } } },
    PALADIN = { pages = { {
        picture = "paladin",
        lines = {
            { "Wax seal", "your seal. The color tells you which one, and the wax drains as it runs out." },
            { "Cracked amber seal", "about to drop. Recast it." },
            { "Warhammer", "Judgement. It fills up as the cooldown comes back and glows when ready." },
            { "The slam", "cast Judgement and the hammer smashes down." },
            { "Rune on the ground", "the Judgement on your target and how long it has left." },
        },
        pins = { { 1, 25, 38, -9, 38 }, { 3, 95, 8, 95, -9 }, { 5, 140, 66, 159, 66 } },
        extras = { { n = 2, picture = "paladin_crack" }, { n = 4, picture = "paladin_slam" } },
    } } },
    HUNTER = { pages = { {
        picture = "hunter",
        lines = {
            { "Scope", "you are the dot, the skull is your target. The rings show melee, dead zone, shooting range and too far." },
            { "Rim", "your Auto Shot timer. Walk while it fills." },
            { "PLANT", "stand still, the shot is coming." },
            { "Pink rim", "you moved and the shot was late." },
            { "Jaws", "your traps. Open and READY means you can lay one." },
        },
        pins = { { 1, 10, 37, -9, 37 }, { 2, 66, 69, 66, 95 }, { 5, 112, 15, 112, -9 } },
        extras = { { n = 3, picture = "hunter_plant" }, { n = 4, picture = "hunter_late" } },
    } } },
    ROGUE = { pages = { {
        picture = "rogue",
        lines = {
            { "Dagger fan", "your combo points, one dagger per point." },
            { "Gold fan and FINISH", "five points. Spend them." },
            { "Shadow fan and OPENER", "you are in stealth." },
            { "Spinning star", "Slice and Dice and its time. It pulses amber in a fight when it is down." },
            { "Gold bar", "your energy. The two gems light up when you can afford your builder and your finisher." },
        },
        pins = { { 1, 13, 32, -9, 32 }, { 4, 137, 40, 163, 40 }, { 5, 60, 85, 60, 110 } },
        extras = { { n = 2, picture = "rogue_finish" }, { n = 3, picture = "rogue_opener" } },
    } } },
    PRIEST = { pages = { {
        picture = "priest",
        lines = {
            { "Shield", "Power Word: Shield on your friendly target, or on you. The light inside is how much it can still absorb, and the number is the amount." },
            { "Shield rim", "violet means Weakened Soul, cyan means you can shield again." },
            { "Amber dashed shield in a fight", "nobody has a shield. Put one up." },
            { "Skull", "Spirit Tap after a kill, with its time. Pull the next mob while it lasts." },
            { "Gold flame", "Inner Fire and its charges. It pulses amber when it is missing." },
        },
        pins = { { 1, 14, 45, -9, 45 }, { 2, 38, 3, 38, -9 }, { 5, 96, 82, 96, 109 } },
        extras = { { n = 3, picture = "priest_empty" }, { n = 4, picture = "priest_tap" } },
        note = "In a group the right side can show Prayer of Mending instead. Pick it with Show in the Priest group of the Gunsight HUD page.",
    } } },
    SHAMAN = { pages = { {
        picture = "shaman",
        lines = {
            { "Four totem poles", "Fire, Earth, Water and Air. The pole shrinks as your totem runs out." },
            { "Amber top block", "your totem is nearly gone. Drop it again." },
            { "DROP", "no totem in that element. Click the pole to drop one." },
            { "FAR", "you walked away from your totem." },
            { "Lightning disc", "your shock cooldown. RDY means shock now." },
            { "Flame disc", "Fire Nova, shown while you have a Fire totem down." },
        },
        pins = { { 1, 112, 17, 112, -9 }, { 2, 6, 74, -9, 74 }, { 3, 77, 100, 77, 133 }, { 5, 198, 40, 211, 40 }, { 6, 195, 103, 211, 103 } },
    } } },
    MAGE = { pages = {
        {
            label = "Frost", picture = "mage_frost",
            lines = {
                { "Snowflake", "Frost Nova. The ring around it fills back up as the cooldown comes back." },
                { "Ice ring", "your target is frozen, and the time under it is about how long." },
                { "Ice spike", "Ice Lance. It shines when it hits hardest." },
                { "Ice oval", "Ice Barrier and how much it can still absorb. Click it to cast." },
            },
            pins = { { 1, 29, 25, -9, 25 }, { 2, 37, 4, 37, -9 }, { 3, 15, 62, -9, 62 }, { 4, 143, 28, 159, 28 } },
        },
        {
            label = "Arcane", picture = "mage_arcane",
            lines = {
                { "Eye", "opens wider as Arcane Blast stacks up, with the time the stacks have left." },
                { "Number under the eye", "what your next Blast costs." },
                { "Purple oval", "Mana Shield and how much it can still absorb. Click it to cast." },
            },
            pins = { { 1, 31, 32, -9, 32 }, { 2, 28, 64, -9, 64 }, { 3, 143, 30, 159, 30 } },
        },
        {
            label = "Fire", picture = "mage_fire",
            lines = {
                { "Flame", "grows with your Fire Vulnerability stacks on the target, with their time." },
                { "Comet", "Fire Blast. Bright when it is ready, dark while it cools." },
                { "Purple oval", "Mana Shield and how much it can still absorb. Click it to cast." },
            },
            pins = { { 1, 38, 16, 38, -9 }, { 2, 15, 64, -9, 64 }, { 3, 143, 30, 159, 30 } },
        },
    } },
    WARLOCK = { pages = { {
        picture = "warlock",
        lines = {
            { "The book", "your demon's pact book. The cover lights up from the bottom with your demon's health." },
            { "Dark, smoking book", "your demon is gone. SUMMON names the demon and what it costs." },
            { "Five crystals", "your soul shards, one per crystal. +2 means you carry two more." },
            { "Lightning into the gem", "BOLT, your next Shadow Bolt is instant." },
            { "Burning pages", "FIRE, Soul Fire is free and fast." },
            { "Blood dripping", "TAP, use Life Tap before your next Shadow Bolt." },
            { "Souls flying into the book", "REAPING, keep channeling Drain Soul." },
        },
        pins = { { 1, 8, 45, -9, 45 }, { 3, 138, 53, 159, 53 }, { 4, 80, 8, 80, -9 } },
        extras = { { n = 2, picture = "warlock_summon" }, { n = 5, picture = "warlock_fire" },
                   { n = 6, picture = "warlock_tap" }, { n = 7, picture = "warlock_reaping" } },
        note = "Each prompt can be turned off on the Gunsight HUD page.",
    } } },
    DRUID = { pages = {
        {
            label = "Caster form", picture = "druid_caster",
            lines = {
                { "Rose", "Rejuvenation. It greys out as the time runs down." },
                { "Seven petals", "Regrowth. One petal wilts each time it heals." },
                { "Pink and teal numbers", "time left on Rejuvenation and Regrowth." },
                { "Bramble wreath", "your Thorns time. It dries out as Thorns runs down and drops a leaf every minute." },
            },
            pins = { { 1, 75, 24, 75, -9 }, { 2, 95, 22, 159, 22 }, { 3, 30, 35, -9, 35 }, { 4, 54, 57, -9, 57 } },
        },
        {
            label = "Bear form", picture = "druid_bear",
            lines = {
                { "Bear head", "Demoralizing Roar. Bright and snarling while it is on the enemies, grey when it is not." },
                { "Sound arcs", "the roar's time, turning amber near the end." },
                { "Ring of thorns", "your Thorns time." },
            },
            pins = { { 1, 78, 7, 78, -9 }, { 2, 133, 35, 159, 35 }, { 3, 7, 11, -9, 11 } },
        },
        {
            label = "Cat form", picture = "druid_cat",
            lines = {
                { "Hide with five slots", "your combo points. The paw rakes a gash for each one." },
                { "Gold gashes and FINISH", "five points. Spend them." },
                { "The finisher", "the paw swipes across the hide." },
                { "Ring of thorns", "your Thorns time." },
            },
            pins = { { 1, 36, 40, -9, 40 }, { 4, 4, 11, -9, 11 } },
            extras = { { n = 2, picture = "druid_cat_finish" }, { n = 3, picture = "druid_cat_swipe" } },
        },
    } },
}

-- "Name: text" lines of one class, for the Gunsight HUD page's ? tip. Pages with a label prefix it.
function H.Tip(token)
    local class = H.CLASSES[token]
    if not class then return nil end
    local out = {}
    for _, page in ipairs(class.pages) do
        for _, line in ipairs(page.lines) do
            out[#out + 1] = (page.label and (page.label .. ", ") or "") .. line[1] .. ": " .. line[2]
        end
    end
    return table.concat(out, "\n")
end

-- The arrow from a pin to its target, as screen pixel rectangles { x, y, w, h } (top left origin): one or two straight
-- runs LINE thick and a stepped head of three bands (2, 6 and 10 wide) at the target.
local function Arrow(rects, px, py, tx, ty)
    local L, half = H.LINE, H.LINE / 2
    local horizontal = math.abs(tx - px) > math.abs(ty - py)
    local sx, sy = px, py
    if horizontal then sx = px + (tx > px and 1 or -1) * H.PIN / 2 else sy = py + (ty > py and 1 or -1) * H.PIN / 2 end
    local cx, cy = horizontal and tx or sx, horizontal and sy or ty
    -- the last run's direction decides the head
    local dx, dy = 0, 0
    if cx ~= tx or cy ~= ty then
        dx, dy = (tx > cx and 1 or tx < cx and -1 or 0), (ty > cy and 1 or ty < cy and -1 or 0)
    else
        dx, dy = (tx > sx and 1 or tx < sx and -1 or 0), (ty > sy and 1 or ty < sy and -1 or 0)
    end
    local function run(ax, ay, bx, by)
        if ax == bx and ay == by then return end
        rects[#rects + 1] = { math.min(ax, bx) - half, math.min(ay, by) - half, math.abs(bx - ax) + L, math.abs(by - ay) + L }
    end
    local ex, ey = tx - dx * 4, ty - dy * 4      -- the shaft stops inside the head
    if cx == tx and cy == ty or (cx == sx and cy == sy) then
        run(sx, sy, ex, ey)
    else
        run(sx, sy, cx, cy)
        run(cx, cy, ex, ey)
    end
    for i, width in ipairs({ 2, 6, 10 }) do
        local back = (i - 1) * 2
        if dy ~= 0 then
            local y = dy > 0 and (ty - back - 2) or (ty + back)
            rects[#rects + 1] = { tx - width / 2, y, width, 2 }
        else
            local x = dx > 0 and (tx - back - 2) or (tx + back)
            rects[#rects + 1] = { x, ty - width / 2, 2, width }
        end
    end
end

-- Where everything of one page goes, in screen pixels inside a box `width` wide, top left origin:
--   { w, h, picture = { name, x, y, w, h }, arrows = { rects }, pins = { { n, x, y } } (square top left),
--     caption = y or nil, extras = { { n, name, x, y, w, h } } }
-- `size(name)` returns a picture's width and height in picture pixels.
function H.Layout(page, width, size)
    local S, M = H.SCALE, H.MARGIN
    local pw, ph = size(page.picture)
    local boxW, boxH = (pw + 2 * M) * S, (ph + 2 * M) * S
    local left = math.floor((width - boxW) / 2 / S) * S
    if left < 0 then left = 0 end
    local ox, oy = left + M * S, M * S
    local out = { w = width, picture = { page.picture, ox, oy, pw * S, ph * S }, box = { left, 0, boxW, boxH }, arrows = {}, pins = {}, extras = {} }
    for _, pin in ipairs(page.pins or {}) do
        local n, tx, ty, px, py = pin[1], pin[2], pin[3], pin[4], pin[5]
        Arrow(out.arrows, ox + px * S, oy + py * S, ox + tx * S, oy + ty * S)
        out.pins[#out.pins + 1] = { n, ox + px * S - H.PIN / 2, oy + py * S - H.PIN / 2 }
    end
    local y = boxH
    if page.extras and #page.extras > 0 then
        y = y + H.GAP
        out.caption = y
        y = y + H.CAPTION
        local x, rowH = 0, 0
        for _, e in ipairs(page.extras) do
            local ew, eh = size(e.picture)
            if x > 0 and x + ew > width then
                x, y = 0, y + rowH + H.GAP
                rowH = 0
            end
            out.extras[#out.extras + 1] = { e.n, e.picture, x, y, ew, eh }
            x = x + ew + H.GAP
            if eh > rowH then rowH = eh end
        end
        y = y + rowH
    end
    out.h = y
    return out
end
