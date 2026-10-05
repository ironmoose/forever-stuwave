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

Targets the **WoW Forever beta client, interface 16001**. The layout is currently built around **16:9**. This is an early personal UI with an initial Paladin tester, so expect rough edges.

| Area | Where it stands |
| --- | --- |
| UI | Custom unit frames, nameplates, terminal chat, action deck, pet controls, and panel styling. The screenshots show the real alpha. |
| Combat HUD | Class profiles exist for **Priest and Warlock**. A Paladin seal, aura, and Judgement HUD is still to come. |
| Paladin | Paladin support is in progress. Dispel cues and class diagnostics are implemented; the first live alpha test is next. |
| Mouseover casting | `/fsmouseover` is available; casting through the party rows still needs verification in game. |
| Diagnostics | `/fsbug` packages settings and recent errors; `/fsrecon class` captures class evidence for the next pass. |

### Install

**Close the game first.** A new addon or new files require a full client restart.

The public repository is being prepared. Until it is published, use the alpha ZIP supplied by the maintainer. No public release download is available yet.

Once the repository is published, open a terminal in your game's `Interface/AddOns` folder:

```sh
git clone https://github.com/ironmoose/forever-stuwave.git ForeverSynthwave
```

The project is called **Forever STUwave**, but its installed folder must be **`ForeverSynthwave`**. The addon still uses that internal name for its files, textures, and saved settings.

The result must look like this:

```text
Interface/
└── AddOns/
    └── ForeverSynthwave/
        ├── ForeverSynthwave.toc
        ├── Theme.lua
        ├── fonts/
        └── media/
```

For a supplied tester ZIP, find the inner `ForeverSynthwave` folder and copy it into `Interface/AddOns`. For GitHub's **Code → Download ZIP**, extract the wrapper folder, rename the folder containing `ForeverSynthwave.toc` to `ForeverSynthwave`, and put it there. There must be no extra folder between `ForeverSynthwave` and its `.toc` file.

Start the game and enable **Forever STUwave** in the character selection AddOns menu.

### Update

Close the game, then run this from `Interface/AddOns`:

```sh
git -C ForeverSynthwave pull --ff-only
```

If you installed a ZIP, replace the installed addon folder with the new supplied `ForeverSynthwave` folder. Keep your saved settings in `WTF`; they live outside the addon folder. Restart the client after updating.

### Help shape it

When something breaks, run `/fsbug` with a short note and follow the [testing guide](TESTING.md). For the first Paladin pass, that guide also walks through `/fsrecon class` at level 1 and again around level 10.

Reports include class, level, zone, addon list, settings, and errors. **Inspect a report before posting it publicly.** Share the focused report first; the entire SavedVariables file contains more data. Public issue reporting will be available at [the repository's issue tracker](https://github.com/ironmoose/forever-stuwave/issues/new) once the repository is published.

---

This checkout is a curated runtime snapshot. Development stays in the private canonical source during the alpha; see [how updates reach this repo](docs/DEVELOPMENT.md). The project's code license is pending. Bundled fonts have their own licenses, listed in [third party notices](THIRD_PARTY_NOTICES.md).
