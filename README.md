<p align="center">
  <img src="docs/images/stuwave.svg" alt="Forever STUwave — WoW Forever / Custom UI / Alpha" width="1200">
</p>

A custom UI for WoW Forever, built for the beta client (interface 16001) and a 16:9 display.

### Install

Close WoW. Clone the repo outside your game folder:

```sh
git clone https://github.com/ironmoose/forever-stuwave.git
```

Copy `addon/ForeverSynthwave` into `_classic_beta_/Interface/AddOns/`, then start WoW and enable **Forever STUwave**. Keep the installed folder named `ForeverSynthwave`.

### Update

Close WoW, run `git pull --ff-only` in your checkout, and replace the installed addon with `addon/ForeverSynthwave`. Fully restart WoW. [Deployment scripts](docs/DEVELOPMENT.md#deploying-a-development-build) can handle the copy for you.

### Help shape it

Bugs and ideas are welcome through [GitHub issues](https://github.com/ironmoose/forever-stuwave/issues). When something breaks, run `/fsbug` and include what happened; [the testing guide](docs/TESTING.md) covers reporting and checks.

[Development](docs/DEVELOPMENT.md) · [MIT license](LICENSE) · [Third party notices](docs/THIRD_PARTY_NOTICES.md)
