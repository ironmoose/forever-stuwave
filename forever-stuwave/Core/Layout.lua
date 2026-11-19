-- Forever STUwave: Layout
-- FS.Layout: canonical screen anchors/sizes plus the UIParent-relative
-- Apply/Scale/OnRescale machinery every component seats itself with.
-- Split out of Theme.lua, which still owns chrome/tokens. Loads after
-- Theme.lua and before every component that consumes FS.Layout (see .toc).

local addonName, FS = ...

-------------------------------------------------------------------------------
-- Layout
-------------------------------------------------------------------------------

-- Canonical layout/anchors, baked from the player's finalized planner export
-- (artifact 7nuxcfvA6WA1eg8bMqcsZq). Every entry anchors point="CENTER" of the
-- frame to relPoint="CENTER" of UIParent; x/y are the game-px offset from
-- UIParent's center to the element's own center at 2560x1440 (Y is +up), so
-- these offsets are resolution-independent across screen sizes. w/h are the
-- element size in game px at that resolution. Not every id below has a built
-- frame yet -- this is the complete canonical map, not what exists today.
FS.Layout = FS.Layout or {
    grid        = { point = "CENTER", relPoint = "CENTER", x = 2,     y = -625, w = 2560, h = 183 },
    -- player/target keep the approved corner seat at every UI scale: TOPLEFT, raw UI
    -- units (unscaled), player 20,-20 and target one 260 wide panel plus a 20 gap to its
    -- right. UnitFrames.lua owns their size (noSize), so w/h only record its panel size.
    player      = { point = "TOPLEFT", relPoint = "TOPLEFT", x = 20,   y = -20, w = 260, h = 73, unscaled = true, noSize = true },
    target      = { point = "TOPLEFT", relPoint = "TOPLEFT", x = 300,  y = -20, w = 260, h = 73, unscaled = true, noSize = true },
    tot         = { point = "CENTER", relPoint = "CENTER", x = -451,  y = 623,  w = 150,  h = 54  },
    focus       = { point = "CENTER", relPoint = "CENTER", x = -723,  y = -142, w = 190,  h = 66  },
    pet         = { point = "CENTER", relPoint = "CENTER", x = -448,  y = -361, w = 180,  h = 62  },
    party       = { point = "CENTER", relPoint = "CENTER", x = -389,  y = -75,  w = 231,  h = 294 },
    -- The raid grid (RaidFrames.lua) has one seat per size: raid5 for a roster of 1 to 5, raid10 for 6 to 10, and so
    -- on up to raid40, each its own entry with its own saved override and its own reset (the layout editor moves the
    -- size its preview shows). The grid is never anchored to the party frames. The seat is the grid's TOP LEFT, and
    -- the grid sizes itself from the cells it shows (noSize); w/h record the grid at the full size (look A, 84 x 30
    -- mini boxes, up to 10; look C, 58 x 40 tiles, above; one column of five per group: 84, 172, 180, 241, 302, 485
    -- wide, 174 high at 5 and 10 and 224 high above). The defaults sit just left of the party seat (its left edge is
    -- -504.5): every size's right edge is on the line x -524.5, 20 clear of it, so a size grows leftward, and every
    -- top is y 140, which keeps the tallest grid (bottom -84) above the focus frame (top -109) and under the
    -- target-of-target frame and the player and target corners. Seen together in the editor the grids and the party
    -- frames do not overlap; raidframes-harness.py checks that against every default seat on that side.
    raid5       = { point = "TOPLEFT", relPoint = "CENTER", x = -608.5,  y = 140, w = 84,  h = 174, noSize = true },
    raid10      = { point = "TOPLEFT", relPoint = "CENTER", x = -696.5,  y = 140, w = 172, h = 174, noSize = true },
    raid15      = { point = "TOPLEFT", relPoint = "CENTER", x = -704.5,  y = 140, w = 180, h = 224, noSize = true },
    raid20      = { point = "TOPLEFT", relPoint = "CENTER", x = -765.5,  y = 140, w = 241, h = 224, noSize = true },
    raid25      = { point = "TOPLEFT", relPoint = "CENTER", x = -826.5,  y = 140, w = 302, h = 224, noSize = true },
    raid40      = { point = "TOPLEFT", relPoint = "CENTER", x = -1009.5, y = 140, w = 485, h = 224, noSize = true },
    boss        = { point = "CENTER", relPoint = "CENTER", x = 728,   y = 152,  w = 210,  h = 210 },
    -- Stack A's two cast bars (CastBars.lua), the cast display while the Gunsight HUD is off. UI units,
    -- not scaled (the bars have always sat on a fixed seat in UIParent units), and noSize: the bar fits its
    -- own width to whole chevrons (268 at pixel scale 1) and is 22 high. Centres: the old seat's gap centre
    -- (0, -317) less / plus half the 18 gap and half a bar (22 / 2): player -337, target -297.
    pcast       = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -337, w = 268,  h = 22, unscaled = true, noSize = true },
    tcast       = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -297, w = 268,  h = 22, unscaled = true, noSize = true },
    action      = { point = "CENTER", relPoint = "CENTER", x = -7,    y = -540, w = 1089, h = 178 },
    multibar    = { point = "CENTER", relPoint = "CENTER", x = 1253,  y = 97,   w = 50,   h = 320 },
    stance      = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -427, w = 320,  h = 38  },
    petbar      = { point = "CENTER", relPoint = "CENTER", x = -380,  y = -428, w = 320,  h = 38  },
    -- The pet component's one panel (PetFrame.lua): supersedes the `pet`/`petbar`
    -- slots above for that purpose. `pet`/`petbar` stay in the table unremoved --
    -- a concurrent lane may still reference either -- this is a new entry, not a
    -- replacement of them. 348 x 68 is the approved console dock option C
    -- (the design mockup, PE_G.dc: 5 top inset + 26 top row + 3 +
    -- 30 buttons + 4 bottom pad, 6 on the sides; HP/mana left and the cast bar right
    -- over the 10 buttons); petframe-harness.py parses the size back out of the mockup.
    -- SEAT (2026-10-03): moved from (-380, -405) to (-363, -403) because the Console
    -- chassis (Console.lua) and its halo draw OUTSIDE the action rect and had grown into it.
    -- Bottom edge -444 is CONSOLE_PET_GAP (8) above the halo top (-452.2 at the live scale
    -- 0.8333, -452 at scale 1; the stack is centred on y -540 and shrank with the narrower
    -- Console buttons). The seat is CENTER anchored, so the bottom edge is y - h / 2: when
    -- option C cut the height from 82 to 68 the y moved from -403 to -410 to keep that edge
    -- at -444 (-410 - 34; the old -403 - 41). Left edge -537 is CHAT_CLEARANCE (12) right of
    -- the chat terminal's outer edge, glow included (CHAT_CHROME_RIGHT -549, constants
    -- below). x span -537..-189 clears the shoulder tab (x 85 and right) and sits 29 left of
    -- the stance bar (x -160..160); the panel has no glow of its own. petframe-harness.py
    -- checks both gaps and the -444.
    petcontainer = { point = "CENTER", relPoint = "CENTER", x = -363, y = -410, w = 348, h = 68  },
    -- The control deck (micro keys + bag slots, Deck.lua) replaced the old
    -- `micro` (774, -664, 320x32) and `bagbar` (1073, -652, 230x36) blocks. It
    -- is DELIBERATELY not a CENTER-anchored entry: it rests on the XP bar's top
    -- edge, and that bar's height changes with /fsxp, so Deck.lua anchors
    -- BOTTOMRIGHT to the XP bar's TOPRIGHT and reads only h and rightMargin
    -- from here (a fallback in Deck.lua keeps the same numbers if this entry is
    -- missing). w is the MAX width, not the live one: the micro slot follows the
    -- number of SHOWN micro keys (MicroBars.lua tells Deck.lua), so the deck
    -- shrinks leftward from this and never grows past it. w must equal the sum
    -- of the max parts Deck.lua builds from (12 + 314 + 28 + 206 + 12 = 572;
    -- the 314 is the nested 12 key micro row, see Deck.lua);
    -- `python3 addons/microbars-harness.py` checks it. No point/x/y on purpose,
    -- so FS.Layout.Apply would do nothing with it. rightMargin 92 puts the
    -- deck's right edge at 1188 of the 1280 half-width, where the old bag block
    -- ended (1073 + 230 / 2). Measured from the xpbar entry's top edge (y -675),
    -- its footprint is y -637..-675 and x 616..1188 at most; the live XP bar's
    -- own variant height (12 for most variants, 18 for spectrum) moves that
    -- edge, and the deck with it. The action stack ends at y -629 (x to 537),
    -- professions at y -555, so the only neighbour is the action stack, 8
    -- design px clear above it.
    deck        = { w = 572, h = 38, rightMargin = 92 },
    xpbar       = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -683, w = 1000, h = 16  },
    -- x is DELIBERATELY left of the planner's export (802 / 842), and re-porting
    -- it "back" is a regression, not a fix -- that was tried on 2026-09-22 and
    -- put both blocks under the minimap. The export still assumes a 210-wide
    -- minimap; ours grew to 250 when it gained the CRT console, so its left
    -- edge moved from 1024 to 1011. At the exported x these blocks end at 1012
    -- and collide. At 773 / 808 they end at 983 / 978 and clear it.
    buffs       = { point = "CENTER", relPoint = "CENTER", x = 773,   y = 637,  w = 420,  h = 80  },
    debuffs     = { point = "CENTER", relPoint = "CENTER", x = 808,   y = 493,  w = 340,  h = 56  },
    -- x shifted from 1136 to 1126 (2026-09-25, Player: "cut off on the right
    -- side"). At the design canvas's right edge (half-width 1280), the old
    -- x=1136 left the map's own right edge (1136 + 250/2 = 1261) only 19
    -- design px of margin -- and ApplyChrome's outer glow (GLOW_SIZE =
    -- max(4, m*0.038), m the map's ~250px scaled size, Minimap.lua) reaches
    -- that same ~19px past the map's edge, with zero buffer for float
    -- rounding, CompensateClusterInset's own measured correction, or a
    -- non-16:9 display. The new x buys a ~10px buffer (margin ~29px vs the
    -- glow's ~19px reach) without touching GLOW_SIZE itself, which is sized
    -- to match the mockup's glow:60 spec and would be a visual regression to
    -- shrink. minimaptray's x moves the same ~10px (1137 -> 1127) since it
    -- must stay flush under the map. Re-verified this does not collide with
    -- buffs/debuffs above: minimap's new left edge is 1126 - 125 = 1001;
    -- buffs (x=773, w=420) right edge is 773+210=983, clearance 18px;
    -- debuffs (x=808, w=340) right edge is 808+170=978, clearance 23px --
    -- both still comfortably positive (was 28px/33px before this shift).
    -- On-screen result UNVERIFIED -- cannot launch the client to check.
    -- Raise the whole console 9 design px. Its 126px half-height and ~9.5px
    -- outer glow then fit inside the canvas top at y=720; move the tray with
    -- the map so their seam stays flush. In-game position remains unverified.
    minimap     = { point = "CENTER", relPoint = "CENTER", x = 1126,  y = 584,  w = 250,  h = 252 },
    minimaptray = { point = "CENTER", relPoint = "CENTER", x = 1127,  y = 397,  w = 250,  h = 37  },
    databar     = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -710, w = 2560, h = 20  },
    -- y raised from the planner's -493. Our terminal draws its chrome on a
    -- backdrop OUTSET below the chat frame (Chat.lua PAD_BOTTOM, which also
    -- houses the edit box), so the visible panel extends lower than the planner
    -- rect and was overlapping the XP and data bars. The offset is that padding
    -- plus a small gap, converted back to design px.
    chat        = { point = "CENTER", relPoint = "CENTER", x = -923,  y = -450, w = 677,  h = 373 },
    tracker     = { point = "CENTER", relPoint = "CENTER", x = 975,   y = 170,  w = 270,  h = 320 },
    -- Mirrors `chat` on the opposite side of the screen: same y, x negated.
    professions = { point = "CENTER", relPoint = "CENTER", x = 923,   y = -450, w = 300,  h = 210 },
    -- The Warrior power-up alerts (WarriorPowerUps.lua): 150 x 96 sprite px at 2.5 design px each, centred above the character
    -- between the rails (the Gunsight root sits at -6.4, -86.4 from the centre; the art's bottom edge is about 206 above it).
    warriorpowerup = { point = "CENTER", relPoint = "CENTER", x = -6,    y = 240,  w = 375,  h = 240 },
    -- The Druid Clearcasting alert (DruidClearcasting.lua): the same 150 x 96 grid at 2.5, in the Warrior alerts' seat.
    druidclearcasting = { point = "CENTER", relPoint = "CENTER", x = -6, y = 240, w = 375, h = 240 },
    -- Seat for the default GameTooltip anchor (TooltipAnchor.lua); the tooltip grows up and left from its
    -- bottom right corner. Blizzard's default container: BOTTOMRIGHT of UIParent, 9 in and 85 up in raw UI units
    -- (12.1.0 UI source, unconfirmed on this client), so it hugs the corner at any width and UI scale.
    tooltip     = { point = "BOTTOMRIGHT", relPoint = "BOTTOMRIGHT", x = -9, y = 85, w = 160, h = 80, unscaled = true },
}

-- Clearances the Console chassis and the pet panel keep from the chat terminal, in DESIGN
-- px (centre-relative x, like the entries above). The chat entry's own right edge is
-- -584.5, but the terminal draws OUTSIDE it: ChatCore's backdrop is outset PAD_X (10 UI
-- units) and SkinPanel's glow SLICE_GLOW_PAD (4) past that, which the code puts at about
-- -568 at the live UI scale. Measured on the live client 2026-10-03 (UIParent 1200 tall,
-- scale 0.8333, debug/gunsight-live-2026-10-03-full.png) the border sits at -554 and its
-- glow reaches about -549, so the measured edge is used: CHAT_CHROME_RIGHT is the
-- terminal's outermost right edge, glow included. THIS IS A SANITY FLOOR ONLY: the check
-- asserts it is never left of the edge the chat code implies (~-568), leaving about 19px
-- of unexplained code-implied width, so it only fires if the chat outset grows a lot. The
-- real guard is re-measuring from a live screenshot when the chat chrome changes.
-- CHAT_CLEARANCE is the gap Console.lua's halo (ActionBars narrows the stack to fit) and
-- PetFrame's panel keep from it. CONSOLE_PET_GAP is the gap between the Console's halo top
-- and the pet panel's bottom edge (the seat of the `petcontainer` entry above).
-- CONSOLE_CAST_GAP is the same gap for Stack A's cast bars (the `pcast` and `tcast` entries above): the
-- lowest edge of the player bar, its spell name tab hanging under it included, keeps this far above the top of
-- the Console art over the span the bars cover (chassis halo, class shoulders, key tab). The entries only
-- say where a bar sits when nothing is in the way; CastBars.lua lifts a bar that is still on its shipped seat
-- by whatever the gap takes (see CONSOLE CLEARANCE in its header).
FS.Layout.CHAT_CHROME_RIGHT = -549
FS.Layout.CHAT_CLEARANCE = 12
FS.Layout.CONSOLE_PET_GAP = 8
FS.Layout.CONSOLE_CAST_GAP = 8

-- The shared controls kit's measurements (mockups/shared-controls-2026-11-12.html), in PHYSICAL pixels at the player's screen:
-- one mock px is one screen px, the convention of the Mail build (FS.ControlKit turns each into UI units at the pixel scale
-- of the frame it lays out, so an edge lands on a whole screen pixel at any UI scale). It has no x and y, so the layout
-- editor does not take it for a seat. A control is never resized (a stock frame keeps its rect, the plate sits inside it).
FS.Layout.Controls = {
    -- Checkbox and radio: a 16 box, chamfer 4 (top left and bottom right), the power LED a 3 square at (11, 2), the tick
    -- (3, 8) -> (6, 11) -> (11, 6); the radio is the 16 rhombus with a 6 node and an expanding ring.
    CHECK = 16, CHECK_CUT = 4, LED = 3, LED_X = 11, LED_Y = 2, NODE = 6, NODE_OFFSET = 5,
    -- Motion, in seconds: the LED breathes to 0.3 and back, the tick draws in over the first 18 % of the mock's 3 s loop,
    -- the radio ring grows from 0.7 to 1.9 of the rhombus, and the node slides to a newly chosen option.
    LED_PULSE = 1.6, LED_FLOOR = 0.3, TICK_DRAW = 0.54, RING_PERIOD = 1.8, RING_FROM = 0.7, RING_TO = 1.9, RING_ALPHA = 0.9,
    NODE_SLIDE = 0.16,
    -- Alpha of the radio rail and of the cyan LED stub a hovered, unchecked box shows.
    RAIL_ALPHA = 0.5, HOVER_LED_ALPHA = 0.5,
    -- Slider: cells 6 x 8 on a pitch of 8 (a track of n cells is 8n - 2 wide); the thumb is a pair of lock-on brackets, spines 9
    -- either side of the head cell's centre, 20 apart top to bottom, arms 4 long, stroke 2; the value tag hangs 34 above the
    -- track centre, 18 tall, with a 4 px stem and a 28 x 24 wash under the head cell; the stepper keys are 20 square.
    CELL_W = 6, CELL_H = 8, CELL_PITCH = 8, BRACKET_SPINE = 9, BRACKET_HALF = 10, BRACKET_ARM = 4, STROKE = 2,
    TAG_H = 18, TAG_TOP = 34, TAG_CUT = 4, TAG_PAD = 12, TAG_CHAR = 7.2, TAG_ROUND = 4, TAG_STEM = 4, TAG_STEM_TOP = 16,
    WASH_W = 28, WASH_H = 24, WASH_ALPHA = 0.10, KEY = 20, KEY_CUT = 4,
    -- Slider text: the tag reads 11, a title 12, the end labels 10, all in the mono; a stepper key keeps at least 8 between
    -- itself and the first or last cell, and its glyph bars are {x, y, w, h} inside the 20 square (the minus is one bar, the
    -- plus adds the upright).
    TAG_TEXT = 11, TAG_LABEL_Y = 10, LABEL_TEXT = 12, SMALL_TEXT = 10, KEY_GAP = 8,
    KEY_MINUS = { 6, 9, 8, 2 }, KEY_PLUS_UPRIGHT = { 9, 6, 2, 8 },
    -- Edit and search boxes: chamfer 6, a 24 prompt cell (a rule at its edge, 5 short of the top and bottom) holding a 16 glyph
    -- 4 in, the text 34 in at 12 and 10 short of the right edge (28 where the clear key sits), a 2 tall LED underline 3 up from
    -- the bottom and a 3 px glow while focused, a 7 x 14 block caret that blinks every 1.1 s, a 20 tall count chip 6 from the
    -- right, and the search box's radar: a 1.6 s sweep and a 2 px dot at (centre + 3, centre - 5). A stock box under FIELD_MIN_W by
    -- FIELD_MIN_H or taller than FIELD_MAX_H is not a console line and is left alone.
    FIELD_CUT = 6, FIELD_CELL = 24, FIELD_RULE_PAD = 5, FIELD_GLYPH = 16, FIELD_GLYPH_X = 4, FIELD_TEXT_X = 34, FIELD_TEXT = 12,
    FIELD_RIGHT = 10, FIELD_CLEAR = 28, FIELD_MIN_W = 64, FIELD_MIN_H = 16, FIELD_MAX_H = 40,
    FIELD_LED_H = 2, FIELD_LED_UP = 3, FIELD_GLOW = 3, FIELD_GLOW_ALPHA = 0.08,
    CARET_W = 7, CARET_H = 14, CARET_GAP = 2, CARET_BLINK = 1.1, CARET_DIM = 0.45,
    CHIP_H = 20, CHIP_CUT = 4, CHIP_PAD = 12, CHIP_INSET = 6, CHIP_MIN_TEXT = 40, CHIP_TEXT = 11, CHIP_TEXT_Y = 11,
    RADAR_PERIOD = 1.6, RADAR_DOT = 2, RADAR_DOT_X = 3, RADAR_DOT_Y = -5,
    -- Dropdown button: the field body (chamfer 6) with an 8 square swatch of the current choice 10 in, the label 26 in and
    -- 34 short of the right edge, a hairline at the left edge of the 28 wide zone on the right (5 short of the top and
    -- bottom) and the 16 chevron 24 in from the right edge; open it takes the cyan edge, a 3 px glow, the LED underline and
    -- an upright chevron. A stock button under DD_MIN_W wide is not a dropdown body and is left alone.
    DD_ZONE = 28, DD_SWATCH = 8, DD_SWATCH_X = 10, DD_LABEL_X = 26, DD_TEXT_RIGHT = 34, DD_CHEV_X = 24, DD_MIN_W = 48,
    DD_RULE_PAD = 5,
    -- A labelless arrow dropdown is a square key at least 24 across (cut 4) on the stock rect's centre, the 16 chevron in it.
    DD_ARROW_MIN = 24, DD_ARROW_CUT = 4,
    -- Its open list keeps the stock rows (and Menus.lua's chrome). A row under the hand gets a violet wash at 0.18 and lock-on
    -- brackets (arms 4, no pad) on the row rect inset 2; the current value carries a 4 x 8 pink LED 2 in. The list is scanned
    -- open: a 2 px cyan front edge runs down it in 0.2 s and each row appears as it passes.
    ROW_PAD = 2, ROW_LED_W = 4, ROW_LED_H = 8, ROW_LED_X = 2, ROW_WASH_ALPHA = 0.18, RETICLE_LEN = 4, WIPE_TIME = 0.2,
    WIPE_FRONT = 2,
    -- Item slot (the icon area is the mockup's 32 x 30 at (4, 3) of a 40 square, here the slot's own rect less 8 wide and 10 tall):
    -- a 24 x 2 quality LED 5 up from the bottom, centred; Uncommon and up also wear a 2 px edge. The glint of an Epic or Legendary
    -- (SLOT_GLINT is its one switch) is a 6 px white band at 0.35 that crosses the icon in the first 0.6 of a 3.4 s loop, from 44
    -- left of the icon to 64 right; hover wears a 4 px wash outside the slot at 0.10, a 2 px cyan edge and lock-on brackets (pad
    -- 4, arms 6) that breathe by 0.1 over 1.2 s; a cooldown drains an ink scrim at 0.78 down the icon behind a 2 px cyan front;
    -- a locked slot is an ink scrim at 0.55 with amber tape at 0.4 and a 16 square lock glyph centred on the icon.
    SLOT_ICON_X = 4, SLOT_ICON_Y = 3, SLOT_ICON_TRIM_W = 8, SLOT_ICON_TRIM_H = 10,
    SLOT_LED_W = 24, SLOT_LED_H = 2, SLOT_LED_UP = 5, SLOT_EDGE_FROM = 2, SLOT_QUALITY_TOP = 5,
    SLOT_GLINT = true, SLOT_GLINT_MIN = 4, SLOT_GLINT_ALPHA = 0.35, SLOT_GLINT_PERIOD = 3.4, SLOT_GLINT_SWEEP = 0.6,
    SLOT_GLINT_FROM = -44, SLOT_GLINT_TO = 64, SLOT_GLINT_BAND = 20, SLOT_GLINT_SHEET = 64,
    SLOT_WASH_PAD = 4, SLOT_WASH_ALPHA = 0.10, SLOT_RETICLE_PAD = 4, SLOT_RETICLE_LEN = 6, SLOT_RETICLE_PERIOD = 1.2,
    SLOT_RETICLE_GROW = 0.1, SLOT_COOLDOWN_ALPHA = 0.78, SLOT_COOLDOWN_FRONT = 2, SLOT_LOCK_ALPHA = 0.55,
    SLOT_HAZARD_ALPHA = 0.4, SLOT_HAZARD_SHEET = 64, SLOT_LOCK = 16,
    -- Marching chevrons: the lit cells' strip moves one 8 px pitch every 0.6 s at 18 % white.
    MARCH_PERIOD = 0.6, CHEV_PITCH = 8, CHEV_ALPHA = 0.18,
    -- Slanted tab (four or more tabs), skinned in place: 28 tall, both sides leaning 8 over the full height, a 1 px edge in the
    -- state colour; the selected tab has no edge but a 4 tall pink chevron strip along its top (from the slant to the right
    -- end, 0.95, marching at MARCH_PERIOD), a 1 px pink diagonal on each side and one more row of fill under it. The label is
    -- 12 centred 16 below the plate's top; a tab with news carries a 4 square LED 14 in from the right end and 7 down.
    -- TAB_ART is the canvas of the three baked tab textures (the 8 x 28 cap sits in its top left).
    TAB_H = 28, TAB_SLANT = 8, TAB_EXTRA = 1, TAB_CHEV_H = 4, TAB_CHEV_ALPHA = 0.95, TAB_TEXT = 12, TAB_TEXT_Y = 16,
    TAB_LED = 4, TAB_LED_X = 14, TAB_LED_Y = 7, TAB_ART = 32,
    -- Switch (two or three tabs as one header control, a reusable widget nothing mounts yet): a 28 tall body, chamfer 6, items
    -- 3 in whose width is the label length x TAG_CHAR + 24 rounded up to a multiple of 4; the selected item is a 22 tall slug
    -- 3 down (chamfer 4, a 1 px pink edge) with a 3 tall pink chevron underline 19 down inside it, 4 in from each side. A hovered
    -- item is a cyan-edged 22 tall box, a badge is a 4 square pink LED 10 from the item's right end and 3 down. The slug
    -- slides to a newly chosen item in SWITCH_SLIDE seconds. SWITCH_UNDER_TILE is the rows of the baked underline tile (the art
    -- is its top 3).
    SWITCH_H = 28, SWITCH_CUT = 6, SWITCH_PAD = 3, SWITCH_ITEM_PAD = 24, SWITCH_STEP = 4, SWITCH_ITEM_Y = 3, SWITCH_ITEM_H = 22,
    SWITCH_ITEM_CUT = 4, SWITCH_TEXT_Y = 12, SWITCH_UNDER_Y = 19, SWITCH_UNDER_H = 3, SWITCH_UNDER_INSET = 4,
    SWITCH_UNDER_ALPHA = 0.9, SWITCH_UNDER_TILE = 4, SWITCH_BADGE = 4, SWITCH_BADGE_X = 10, SWITCH_BADGE_Y = 3, SWITCH_SLIDE = 0.2,
    -- Inset (InsetFrameTemplate, section 7 of the mockup): an ink face with a 1 px edge and a chamfer at the bottom right only
    -- (8 asked, the baked 6 drawn), a violet scanline every 4 px from row 3 at 5 %, and cyan register marks at the top left, top
    -- right and bottom left, 4 in with 4 long arms at 35 %. INSET_MIN is the least a frame must measure each way to be an inset
    -- (a smaller one is a divider).
    INSET_CUT = 8, INSET_SCAN_PITCH = 4, INSET_SCAN_ALPHA = 0.05, INSET_MARK_IN = 4, INSET_MARK_ARM = 4, INSET_MARK_ALPHA = 0.35,
    INSET_MIN = 12,
    -- Section header plate (an opt-in helper nothing mounts yet): 24 tall, chamfer 6 at the top left only, a 1 px violet edge on the
    -- band, a 3 x 12 pink LED at (1, 6) that breathes, the caption 14 in at 11, chips 20 tall (cut 4) 2 down, 4 apart and 6 in from
    -- the right, sized like the slider's value tag. A glint (a violet band at 28 %) crosses it every 3.6 s from 60 left of the
    -- plate to 40 past its right end.
    PLATE_H = 24, PLATE_CUT = 6, PLATE_LED_W = 3, PLATE_LED_H = 12, PLATE_LED_X = 1, PLATE_LED_Y = 6, PLATE_TEXT_X = 14,
    PLATE_TEXT = 11, PLATE_TEXT_Y = 13, PLATE_CHIP_Y = 2, PLATE_CHIP_GAP = 4, PLATE_CHIP_RIGHT = 6, PLATE_GLINT_PERIOD = 3.6,
    PLATE_GLINT_ALPHA = 0.28, PLATE_GLINT_FROM = -60, PLATE_GLINT_PAST = 40,
    -- Text area (InputScrollFrameTemplate: a multi-line box in a scroll frame): the field's cut and text, a face that reaches AREA_PAD
    -- past the frame on every side (the stock border art does the same, 5 units), the char count in the muted ink at 10.
    AREA_CUT = 6, AREA_PAD = 5, AREA_COUNT_TEXT = 10,
}

-- The layout planner exports in SCREEN PIXELS at this resolution (the "resolution"
-- field of the design mockup). WoW frames are positioned in UI units, and
-- UIParent is only ever ~768 units tall no matter the monitor, so the exported
-- numbers are roughly 1.9x too large as-is.
--
-- Measured in game 2026-09-20: the grid frame, seated at the exported
-- CENTER (2,-625) with size 2560x183, reported left = -589 and bottom = -332 --
-- entirely off-screen, which is why it drew nothing at all. Working back from
-- those two numbers gives UIParent = 1377 x 768 units against a 2560 x 1440
-- design, i.e. a factor of 768/1440. Every component using FS.Layout was
-- mis-seated by that same factor, which is also why the action bars sat far
-- lower than the mockup.
FS.Layout.DESIGN_W = 2560
FS.Layout.DESIGN_H = 1440

-- Derived from UIParent's CURRENT height rather than a baked constant, so the
-- addon follows the player's UI Scale slider instead of assuming one setting.
function FS.Layout.Scale()
    local height = UIParent and UIParent:GetHeight()
    if not height or height <= 0 then return 1 end
    return height / FS.Layout.DESIGN_H
end

-- pcall that keeps the inner frames: returns ok, err where a string err carries
-- the stack at the throw site, so rethrowing it (error(err, 0)) still lands in
-- ForeverSTUwaveErrorLog with the frames that matter instead of just the
-- rethrow line. Callers use it to reset a flag and then rethrow.
--
-- The handler must never throw (it would replace the real error with "error in
-- error handling"): a secret message or stack would make the concat throw, so
-- both are checked first (issecretvalue is a global that may not exist, and
-- FS.IsSecret is not loaded yet at this point in the .toc; same guard as
-- ErrorLog.lua), and debugstack runs under pcall. When no stack can be had the
-- error goes out alone.
--
-- A rethrow (error(err, 0)) hands the same string to an outer CallTraced; it is
-- recognised through FS.Layout._recentTraced (the last RECENT_TRACED strings
-- handed out, a ring, so several errors alive in one pass each keep their one
-- stack) and passed on as is, so an error that crosses two of them carries ONE
-- stack, and its text (the dedupe key) is the same as with one.
local RECENT_TRACED = 4

function FS.Layout.CallTraced(fn)
    return xpcall(fn, function(err)
        local function secret(v)
            local isSecret = _G.issecretvalue
            if type(isSecret) ~= "function" then return false end
            local ok, r = pcall(isSecret, v)
            return not ok or r ~= false
        end
        if type(err) ~= "string" or secret(err) then return err end
        local recent = FS.Layout._recentTraced
        if not recent then
            recent = {}
            FS.Layout._recentTraced = recent
        end
        for i = 1, #recent do
            if recent[i] == err then return err end
        end
        local stack
        if type(debugstack) == "function" then
            -- Level 3: pcall is level 1, this handler 2, the throw site 3.
            local ok, text = pcall(debugstack, 3)
            if ok and type(text) == "string" and not secret(text) then stack = text end
        elseif debug and debug.traceback then
            stack = debug.traceback("", 2)
        end
        if not stack then return err end
        local traced = err .. "\n" .. stack
        local slot = (FS.Layout._recentTracedNext or 0) % RECENT_TRACED + 1
        FS.Layout._recentTracedNext = slot
        recent[slot] = traced
        return traced
    end)
end

-- True when the entry's x/y (and any override of them) are raw UI units rather than
-- design px, so a drag handle must not divide its screen delta by Scale() for it.
function FS.Layout.IsUnscaled(id)
    local L = type(id) == "string" and FS.Layout[id]
    return type(L) == "table" and L.unscaled == true
end

-- Applies a saved layout entry to `frame`, clearing any prior anchor first.
-- Nil-safe: does nothing if `frame` or the `id` entry is missing. Returns the
-- layout entry so callers can read w/h to size children.
--
-- Returns the entry with its ORIGINAL design values, plus scaled w/h under
-- `scaledW`/`scaledH`: callers that lay out children (the action bars solve
-- their button size from w) need to know which space they are working in.
function FS.Layout.Apply(frame, id, parent)
    local L = FS.Layout[id]
    if not frame or not L then return end

    local scale = L.unscaled and 1 or FS.Layout.Scale()

    -- Edit Mode system frames (ChatFrame1) replace ClearAllPoints/SetPoint with
    -- overrides that write EditModeManagerFrame's anchor-dirty flag, which our
    -- insecure call would leave tainted. They keep the originals as
    -- ClearAllPointsBase/SetPointBase; use those when present, plain calls
    -- otherwise. `applying` tells the chat seat log this move is ours.
    local clear = frame.ClearAllPointsBase or frame.ClearAllPoints
    local set = frame.SetPointBase or frame.SetPoint

    -- A component whose frame is measured to sit off its asked seat (the minimap
    -- cluster: its header strip hangs the map below the frame) can offer
    -- FS.Layout.SeatAdjust[id], answering the anchor that puts the visible part on
    -- the seat. Writing that here, instead of the raw seat and a fix a frame later,
    -- keeps the frame from being shown at the raw seat for one rendered frame. A nil,
    -- malformed or throwing answer (or a frame seated on another parent) is the raw seat.
    local point, relPoint, x, y = L.point, L.relPoint, L.x * scale, L.y * scale
    if not parent then
        -- The lookup, the call and the whole shape check are one pcall: a registrant's
        -- number may be a secret, and arithmetic on one throws. Finite means
        -- x - x == 0 (false for NaN and for either infinity).
        local okA, aPoint, aRel, aX, aY = pcall(function()
            local adjust = FS.Layout.SeatAdjust and FS.Layout.SeatAdjust[id]
            if not adjust then return end
            local p, rp, ax, ay = adjust()
            if type(p) == "string" and type(rp) == "string"
                and type(ax) == "number" and type(ay) == "number"
                and ax - ax == 0 and ay - ay == 0 then
                return p, rp, ax, ay
            end
        end)
        if okA and aPoint then
            point, relPoint, x, y = aPoint, aRel, aX, aY
        end
    end

    FS.Layout.applying = true
    local ok, err = FS.Layout.CallTraced(function()
        clear(frame)
        set(frame, point, parent or UIParent, relPoint, x, y)
        if L.w and L.h and frame.SetSize and not L.noSize then
            frame:SetSize(L.w * scale, L.h * scale)
        end
    end)
    FS.Layout.applying = false
    if not ok then error(err, 0) end

    L.scaledW = L.w and (L.w * scale) or nil
    L.scaledH = L.h and (L.h * scale) or nil

    -- Remember it so the watcher below can re-seat it once UIParent settles.
    FS.Layout._applied[frame] = { id = id, parent = parent }
    return L
end

-- UIParent is NOT fully sized while addons are loading. Measured on this client
-- 2026-09-20: at file scope it reports 768 tall (scale -> 0.533) and by
-- PLAYER_LOGIN it reports 1200 (scale -> 0.833). Anything seated during load
-- therefore lands at ~64% of its intended size and position, which is why the
-- grid covered only part of the screen and the bars sat small and low.
--
-- Rather than make every component remember to defer, re-seat everything that
-- has ever been through Apply once UIParent is real -- and again whenever the
-- player changes UI Scale or resolution, which has the same effect.
FS.Layout._applied = FS.Layout._applied or {}

-- Components that size CHILDREN from the layout (the action bars solve their
-- button edge from the stack width) need to rebuild, not just move, so they
-- can register a callback here.
FS.Layout._rescaleCallbacks = FS.Layout._rescaleCallbacks or {}

function FS.Layout.OnRescale(fn)
    FS.Layout._rescaleCallbacks[#FS.Layout._rescaleCallbacks + 1] = fn
end

-- A protected frame (a secure button, or anything that holds or is anchored to one,
-- like the stance container) refuses ClearAllPoints/SetPoint/SetSize in combat and
-- raises ADDON_ACTION_BLOCKED, so a rescale that lands mid-fight must leave it alone
-- and re-seat it when combat ends. Frames that are not protected are seated at once.
-- IsProtected can itself throw on an odd frame, in which case it counts as protected
-- (holding one back is only a delay; touching one is a blocked action).
local function IsHeldInCombat(frame)
    if not InCombatLockdown() then return false end
    if not frame.IsProtected then return false end
    local ok, protected = pcall(frame.IsProtected, frame)
    return not ok or protected and true or false
end

local deferredRescale = false

-- `why` only labels the pass for callbacks that log it (the minimap seat log reads
-- FS.Layout.rescaleWhy); it is cleared again when the callbacks are done.
local function RunRescaleCallbacks(why)
    FS.Layout.rescaleWhy = why
    for _, fn in ipairs(FS.Layout._rescaleCallbacks) do
        pcall(fn)
    end
    FS.Layout.rescaleWhy = nil
end

local layoutWatcher = CreateFrame("Frame")
layoutWatcher:RegisterEvent("PLAYER_LOGIN")
layoutWatcher:RegisterEvent("UI_SCALE_CHANGED")
layoutWatcher:RegisterEvent("DISPLAY_SIZE_CHANGED")
layoutWatcher:RegisterEvent("PLAYER_REGEN_ENABLED")
layoutWatcher:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_ENABLED" and not deferredRescale then return end
    local deferred = false
    for frame, info in pairs(FS.Layout._applied) do
        if frame and frame.SetPoint then
            if IsHeldInCombat(frame) then
                deferred = true
            else
                FS.Layout.Apply(frame, info.id, info.parent)
            end
        end
    end
    deferredRescale = deferred
    -- Callbacks run on the rescale itself (so unprotected components rebuild at once)
    -- and again once the held frames are seated, so a component that sizes children
    -- from the layout sees their final position; each callback guards its own combat
    -- work (the action bars and the stance bar both defer to PLAYER_REGEN_ENABLED).
    RunRescaleCallbacks(event)
end)

FS.Layout.RunRescaleCallbacks = RunRescaleCallbacks

-------------------------------------------------------------------------------
-- Saved position overrides
--
-- The store is the active profile's layout table, { v = 1, frames = { [id] = { x = , y = } } },
-- bound with UseStore (Config.lua owns profiles and the SavedVariable). Offsets are in the
-- same design px as the entries above. Overrides MUTATE FS.Layout[id].x/.y in place, because
-- several modules read those fields directly instead of going through Apply.
-------------------------------------------------------------------------------

local OVERRIDE_VERSION = 1
local OVERRIDE_STEP = 0.5

FS.Layout._defaults = FS.Layout._defaults or {}

-- The bound layout table; nil refuses every write and applies nothing.
local activeStore = nil

-- Warn once when a newer addon wrote the table (OverrideStore then refuses all writes).
local lockedWarned = false

-- Finite and within 2 design widths either way, for scaled and unscaled entries alike
-- (UI units never exceed design px), so a corrupt value cannot park a frame off-screen.
local OVERRIDE_LIMIT = 2 * FS.Layout.DESIGN_W

local function IsUsableOffset(v)
    return type(v) == "number" and v - v == 0 and v >= -OVERRIDE_LIMIT and v <= OVERRIDE_LIMIT
end

local function IsFiniteNumber(v)
    return type(v) == "number" and v - v == 0
end

-- Only an entry with a numeric x and y is a seat; this also screens out the helper
-- tables hanging off FS.Layout (_applied, SeatAdjust, ...) and `deck`.
local function SeatEntry(id)
    if type(id) ~= "string" then return nil end
    local L = FS.Layout[id]
    if type(L) == "table" and IsFiniteNumber(L.x) and IsFiniteNumber(L.y) then return L end
end

local function SnapshotDefault(id)
    local L = SeatEntry(id)
    if L and not FS.Layout._defaults[id] then
        FS.Layout._defaults[id] = { x = L.x, y = L.y }
    end
    return L
end

local function RestoreDefault(id)
    local def, L = FS.Layout._defaults[id], FS.Layout[id]
    if def and L then L.x, L.y = def.x, def.y end
end

local function OverrideStore()
    local saved = activeStore
    if type(saved) ~= "table" then return nil end
    if type(saved.v) == "number" and saved.v > OVERRIDE_VERSION then
        return nil, saved
    end
    if type(saved.v) ~= "number" then saved.v = OVERRIDE_VERSION end
    if type(saved.frames) ~= "table" then saved.frames = {} end
    return saved.frames
end

function FS.Layout.LoadOverrides()
    for id in pairs(FS.Layout) do SnapshotDefault(id) end
    for id in pairs(FS.Layout._defaults) do RestoreDefault(id) end
    local frames, newer = OverrideStore()
    if newer then
        if not lockedWarned then
            lockedWarned = true
            print(("|cff22e0ffstuwave://layout|r  saved layout is version %s, newer than this addon (%d); position overrides ignored")
                :format(tostring(newer.v), OVERRIDE_VERSION))
        end
        return
    end
    if not frames then return end
    for id, pos in pairs(frames) do
        if SnapshotDefault(id) and type(pos) == "table"
            and IsUsableOffset(pos.x) and IsUsableOffset(pos.y) then
            FS.Layout[id].x, FS.Layout[id].y = pos.x, pos.y
        end
    end
end

-- Binds the layout table overrides are read from and written to, then restores the
-- defaults and applies its overrides. It moves no frames; follow with ReseatAll.
function FS.Layout.UseStore(layout)
    activeStore = type(layout) == "table" and layout or nil
    FS.Layout.LoadOverrides()
end

local function Round(v)
    return math.floor(v / OVERRIDE_STEP + 0.5) * OVERRIDE_STEP
end

-- Each write returns true when it took effect, false when refused.
function FS.Layout.SetOverride(id, x, y)
    if not SnapshotDefault(id) or not IsUsableOffset(x) or not IsUsableOffset(y) then return false end
    x, y = Round(x), Round(y)
    if not IsUsableOffset(x) or not IsUsableOffset(y) then return false end
    local frames = OverrideStore()
    if not frames then return false end
    frames[id] = { x = x, y = y }
    FS.Layout[id].x, FS.Layout[id].y = x, y
    return true
end

function FS.Layout.ClearOverride(id)
    if not SnapshotDefault(id) then return false end
    local frames = OverrideStore()
    if not frames then return false end
    frames[id] = nil
    RestoreDefault(id)
    return true
end

function FS.Layout.ClearAllOverrides()
    local frames = OverrideStore()
    if not frames then return false end
    for id in pairs(frames) do frames[id] = nil end
    for id in pairs(FS.Layout._defaults) do RestoreDefault(id) end
    return true
end

-- True when `id` sits off its shipped seat: a saved override (or a drag) is in force. Only an entry that
-- has a seat can be, and one whose override equals the shipped x and y is not. A module that adjusts a
-- seat on its own (CastBars.lua lifts Stack A over the Console) leaves an overridden one alone.
function FS.Layout.IsOverridden(id)
    local def, L = FS.Layout._defaults[id], SeatEntry(id)
    return def ~= nil and L ~= nil and (L.x ~= def.x or L.y ~= def.y)
end

-- Seats every applied frame `matches` accepts. A frame held back in combat is left to the
-- PLAYER_REGEN_ENABLED pass above, which also runs the rescale callbacks again.
local function ReseatMatching(matches)
    for frame, info in pairs(FS.Layout._applied) do
        if matches(info) and frame and frame.SetPoint then
            if IsHeldInCombat(frame) then
                deferredRescale = true
            else
                FS.Layout.Apply(frame, info.id, info.parent)
            end
        end
    end
    RunRescaleCallbacks("Reseat")
end

function FS.Layout.Reseat(id)
    ReseatMatching(function(info) return info.id == id end)
end

function FS.Layout.ReseatAll()
    ReseatMatching(function() return true end)
end

-------------------------------------------------------------------------------
-- Edit Mode re-seat
--
-- Every Edit Mode system frame we seat through Apply (ChatFrame1, MinimapCluster)
-- is parked at TOPLEFT 0,0 and re-anchored by EditModeManagerFrame:UpdateLayoutInfo,
-- which the server triggers (EDIT_MODE_LAYOUTS_UPDATED) AFTER login on a character's
-- first login, i.e. after the PLAYER_LOGIN pass above. So re-seat them from a
-- post-hook on UpdateLayoutInfo, which runs after every system applied (seating
-- from inside a system's own ApplySystemAnchor would land before its settings
-- loop; see ChatWindowState.lua). Apply uses the Base anchor calls, so this
-- writes nothing under our taint and cannot retrigger Edit Mode. An Edit Mode
-- frame is recognised by the SetPointBase Edit Mode stores on it.
--
-- A module that re-seats its own frame with more logic (the chat, which has a
-- minimised/maximised state) opts out with SkipEditModeReseat.
-------------------------------------------------------------------------------

local editModeSkip = setmetatable({}, { __mode = "k" })

function FS.Layout.SkipEditModeReseat(frame)
    if frame then editModeSkip[frame] = true end
end

-- Hands an error to the client's error handler without ever throwing (the whole
-- lookup-and-call is under pcall, as in ErrorLog.lua). For post-hooks on
-- Blizzard functions, which must not throw into Blizzard's caller (it may unwind
-- the rest of Blizzard's own function; see ReseatFromHook). The nil test is a
-- truth test INSIDE the pcall: an error value may be secret, and comparing a
-- secret with == is illegal.
function FS.Layout.ForwardError(err)
    pcall(function()
        if not err then return end
        local handler = geterrorhandler()
        if type(handler) == "function" then handler(err) end
    end)
end

local function ReseatEditModeFrames(why)
    -- `failed` is a plain flag: the error itself may be secret and is never compared.
    local any, failed, firstErr = false, false, nil
    for frame, info in pairs(FS.Layout._applied) do
        -- One frame's throw (the field lookups included) must not skip the
        -- frames after it or the callbacks below; the first error is RETURNED
        -- for the caller to report (the hook forwards it to the error handler,
        -- the event path rethrows it).
        local ok, err = FS.Layout.CallTraced(function()
            if frame and frame.SetPointBase and not editModeSkip[frame] then
                any = true
                if IsHeldInCombat(frame) then
                    -- Seated by the PLAYER_REGEN_ENABLED pass above.
                    deferredRescale = true
                else
                    FS.Layout.Apply(frame, info.id, info.parent)
                end
            end
        end)
        if not ok and not failed then failed, firstErr = true, err end
    end
    -- Components that size children from the frame (the minimap's inset
    -- compensation) rebuild after the move, as after a rescale.
    if any then RunRescaleCallbacks(why) end
    return failed, firstErr
end

local editModeHooked = false
-- Set by the post-hook, cleared by the event watcher: tells the watcher whether
-- UpdateLayoutInfo's post-hook already re-seated for this event. A hook run that
-- came from somewhere else than the event leaves it set until the next event, so
-- if that event's UpdateLayoutInfo then throws before the hook, the re-seat is
-- missed; accepted, the hook has just re-seated anyway.
local hookRanSinceEvent = false

-- The post-hook runs inside Blizzard's own call chain: a throw here may unwind
-- into EditModeManager (whose later steps are UpdateTopFramePositions,
-- NotifyChatOfLayoutChange, ManageFramePositions, ...; whether the engine
-- contains a hook's error cannot be confirmed from the UI source), so the hook
-- never throws: anything ReseatEditModeFrames returns OR throws (its per-frame
-- isolation does not cover iterating _applied or the callbacks' loop) goes to
-- the error handler instead.
local function ReseatFromHook()
    hookRanSinceEvent = true
    -- (true, failed, firstErr) normally, (false, thrown error) if it escaped.
    local ok, failed, err = FS.Layout.CallTraced(function() return ReseatEditModeFrames("UpdateLayoutInfo") end)
    if not ok then failed, err = true, failed end
    if failed then FS.Layout.ForwardError(err) end
end

local function HookUpdateLayoutInfo()
    if editModeHooked or type(hooksecurefunc) ~= "function" then return end
    if not (EditModeManagerFrame and type(EditModeManagerFrame.UpdateLayoutInfo) == "function") then return end
    editModeHooked = true
    hooksecurefunc(EditModeManagerFrame, "UpdateLayoutInfo", ReseatFromHook)
end
HookUpdateLayoutInfo()

-- The event is the fallback for a client where the post-hook could not be
-- installed, or where UpdateLayoutInfo threw before the hook ran: Blizzard's own
-- OnEvent runs first (it registered first) and calls UpdateLayoutInfo, so when
-- the hook already re-seated for this event (hookRanSinceEvent) the handler
-- stands down instead of re-seating and running every callback twice. The
-- ADDON_LOADED retry covers a client that loads Blizzard_EditMode after us.
local editModeWatcher = CreateFrame("Frame")
editModeWatcher:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
if not editModeHooked then editModeWatcher:RegisterEvent("ADDON_LOADED") end
editModeWatcher:SetScript("OnEvent", function(self, event, addon)
    if event == "ADDON_LOADED" then
        if addon == "Blizzard_EditMode" then
            HookUpdateLayoutInfo()
            self:UnregisterEvent("ADDON_LOADED")
        end
    elseif editModeHooked and hookRanSinceEvent then
        hookRanSinceEvent = false
    else
        -- Event site: nothing of Blizzard's follows our handler, so rethrow.
        local failed, err = ReseatEditModeFrames("EDIT_MODE_LAYOUTS_UPDATED")
        if failed then error(err, 0) end
    end
end)
