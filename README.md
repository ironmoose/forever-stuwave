<p align="center">
  <img src="docs/images/stuwave.svg" alt="Forever STUwave — WoW Forever / Custom UI / Alpha" width="1200">
</p>

<p align="center">
  A custom UI for WoW Forever.<br>
  <strong>Beta · Interface 16001 · 16:9</strong>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#update">Update</a> ·
  <a href="#help-shape-it">Help shape it</a> ·
  <a href="docs/DEVELOPMENT.md">Development</a>
</p>

## Install

1. **Close WoW.**
2. Clone the repo somewhere outside your game folder:

   ```sh
   git clone https://github.com/ironmoose/forever-stuwave.git
   cd forever-stuwave
   ```

3. Copy the **inner `forever-stuwave/` folder** into your game's `_classic_beta_/Interface/AddOns/` folder. Keep its name unchanged.
4. Start WoW and enable **Forever STUwave** in the AddOns menu.

> **Existing install?** Use the [deployment script](docs/DEVELOPMENT.md#deploying-a-development-build) to migrate settings and retire the old copy.

## Update

1. **Close WoW.** From your repo checkout, run:

   ```sh
   git pull --ff-only
   ```

2. Replace the installed addon with the inner `forever-stuwave/` folder, or use the [deployment script](docs/DEVELOPMENT.md#deploying-a-development-build).
3. **Fully restart WoW.**

## Help shape it

Bugs and ideas are welcome through [GitHub issues](https://github.com/ironmoose/forever-stuwave/issues). When something breaks, describe it in chat:

```text
/fsbug what went wrong
```

`/fsbug` opens a copyable report with your class, level, addon settings, and recent errors. Review it, then paste it into your issue.

---

[Testing guide](docs/TESTING.md) · [Development](docs/DEVELOPMENT.md) · [MIT license](LICENSE) · [Third party notices](docs/THIRD_PARTY_NOTICES.md)
