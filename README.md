<p align="center">
  <img src="docs/images/stuwave.svg" alt="Forever STUwave — WoW Forever / Custom UI / Alpha" width="1200">
</p>

<p align="center"><strong>A neon cockpit for WoW Forever.</strong></p>
<p align="center">
  <a href="#install">Install</a> · <a href="TESTING.md">Alpha testing</a> · <a href="docs/DEVELOPMENT.md">Development</a>
</p>

![The real alpha UI in Orgrimmar: neon unit frames, a central Warlock HUD, terminal chat, pet controls, and the action deck.](docs/images/in-game-alpha.png)

<sub>In game, October 3, 2026. An alpha snapshot on a Warlock; individual features are still being tested.</sub>

Built for my own Stu characters. Then guildmates watching the stream wanted the UI too. Forever STUwave is that personal setup becoming something other people can try: dark plum panels, cyan and hot pink rails, violet glow, and sharp cut corners across the screen.

<table>
  <tr>
    <td width="55%"><img src="docs/images/pet-alpha.png" alt="Real alpha pet frame with health and mana rails, cast chevrons, and pet action buttons." width="500"></td>
    <td width="45%"><img src="docs/images/party-alpha.png" alt="Real alpha party tray showing the player's name, health, mana, and violet panel chrome." width="410"></td>
  </tr>
  <tr>
    <td><sub>Pet frame and action row.</sub></td>
    <td><sub>Party tray, showing the player row.</sub></td>
  </tr>
</table>

### The alpha right now

Targets the **WoW Forever beta client, interface 16001**. The layout is currently built around **16:9**. This is an early personal UI; expect rough edges.

| Area | Where it stands |
| --- | --- |
| UI | Custom unit frames, nameplates, terminal chat, action deck, pet controls, and panel styling. The dated screenshots above show the real alpha. |
| Combat HUD | Priest and Warlock profiles, plus Paladin seal/aura controls and the Seal Chamber with a Judgement lane. Advanced Paladin rotation rules at levels 10 and 20 remain incomplete. |
| Paladin testing | Judgement behavior, its HUD lane, Quick Keybind, and compact key labels have been checked in game. Seal/aura clicks, chamber expiry and no-seal states, and the shoulder seam still need checks. |
| Mouseover casting | `/fsmouseover` is available; casting through the party rows still needs verification in game. |
| Diagnostics | `/fsbug` packages settings and recent errors; `/fsrecon class` captures class evidence. Minimap placement on a new character's first login still needs verification. |

### Install

**Close the game first.** Open a terminal in your game's `Interface/AddOns` folder and run:

```sh
git clone https://github.com/ironmoose/forever-stuwave.git ForeverSynthwave
```

The project displays as **Forever STUwave**, but its installed folder must stay **`ForeverSynthwave`**. Texture paths, the `.toc` filename, and saved settings keep that internal identity for compatibility.

```text
Interface/
└── AddOns/
    └── ForeverSynthwave/
        ├── ForeverSynthwave.toc
        ├── Bindings.xml
        ├── Theme.lua
        ├── fonts/
        └── media/
```

If you previously installed a tester ZIP, move its `ForeverSynthwave` folder **outside `AddOns`** before cloning. Keep your `WTF` folder: your saved settings live there and survive replacing the addon.

For a supplied runtime ZIP, copy its inner `ForeverSynthwave` folder into `Interface/AddOns`. For GitHub's **Code → Download ZIP**, rename the extracted folder containing `ForeverSynthwave.toc` to `ForeverSynthwave`. There must be no extra folder between it and the `.toc` file.

Start the game and enable **Forever STUwave** in the character selection AddOns menu. Git installs include development files; WoW loads the files listed in the `.toc`, while the tester ZIP contains only runtime files.

### Update

Close the game, then run this from `Interface/AddOns`:

```sh
git -C ForeverSynthwave pull --ff-only
```

If Git reports local edits or cannot fast-forward, keep those edits and resolve the reported issue before updating. Do not reset the checkout to discard them.

For a ZIP install, move the old addon folder outside `AddOns` and install the new folder. Keep your saved settings in `WTF`. Fully restart the client after updating: `/reload` cannot load newly added addon files.

### Help shape it

When something breaks, run `/fsbug` with a short note and follow the [testing guide](TESTING.md). Paladin testers can also capture `/fsrecon class` evidence at level 1 and around level 10.

Reports include class, level, zone, addon list, settings, and errors. **Inspect a report before posting it publicly.** Share the focused report first; the entire SavedVariables file contains more data. Report problems through [GitHub issues](https://github.com/ironmoose/forever-stuwave/issues/new) or send the report directly to the maintainer.

### Development and license

This repository is the canonical source, including Lua, development tools, harnesses, asset generators, and browser mockups. Start with [the development guide](docs/DEVELOPMENT.md). Mockups are design references; they do not establish live behavior.

Project code and original project assets use the [MIT License](LICENSE). Bundled fonts retain their OFL licenses, and Blizzard game imagery remains separate; see [third party notices](THIRD_PARTY_NOTICES.md). Fresh gameplay media can follow the initial alpha; the existing screenshots retain their original dates and class context.
