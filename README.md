# EDF Unlock Tracker

Track weapon and vehicle unlocks for **Earth Defense Force 4.1, 5 and 6**, per class and category, plus star upgrades for every stat in EDF 5 and 6. It also shows where each weapon drops, keeps eight profiles per game (four PC and four console save slots), works offline once visited and installs as an app on phones.

**[▶ Open the tracker](https://gear2ndgandalf.github.io/edf-weapon-tracker/)**: HQ, or jump straight to [EDF 4.1](https://gear2ndgandalf.github.io/edf-weapon-tracker/edf41.html) · [EDF 5](https://gear2ndgandalf.github.io/edf-weapon-tracker/edf5.html) · [EDF 6](https://gear2ndgandalf.github.io/edf-weapon-tracker/edf6.html)

## Pages
| File | What it is |
|---|---|
| `index.html` | HQ: progress for all three games, export and import |
| `edf41.html` | EDF 4.1 – owned checklist |
| `edf5.html`, `edf6.html` | EDF 5 / EDF 6 – owned checklist plus star upgrades |

## Deploying on GitHub Pages
1. Create a new repository (for example `edf-weapon-tracker`) and upload everything in this folder to its root, including the empty `.nojekyll` file.
   GitHub Pages needs a **public** repository on the Free plan; a private repository needs GitHub Pro. The published site is public either way.
2. Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
3. Open `https://<user>.github.io/edf-weapon-tracker/` (this copy: <https://gear2ndgandalf.github.io/edf-weapon-tracker/>).

Because it lives on the same `<user>.github.io` domain as the old EDF-4.1-PWA, the EDF 4.1 page and HQ offer to import the old checklist's progress automatically. Old export files (`version: 1`) can also be imported from HQ.

## Versions
The app version lives in one place: `js/version.js` (`vMAJOR.MINOR.PATCH`). It is shown on HQ, written into export files, and names the offline cache.

**For every published change:** raise the number in `js/version.js` and add an entry to `CHANGELOG.md`. Phones then drop their old offline copy and fetch the new files.

- MAJOR: the save format changes in a way older exports cannot follow
- MINOR: new features
- PATCH: fixes and data corrections

## How it fits together
The site is plain HTML, CSS and JavaScript (ES modules). Nothing is compiled, and nothing is loaded from other websites.

| Path | Role |
|---|---|
| `js/app.js` | The game page. One script runs all three games (`<body data-game="edf5">`). Click → `act()` → `render()` → save. |
| `js/store.js` | All saving, export and import. localStorage keys start with `edfTracker.` |
| `js/hq.js` | HQ page: progress, profiles, display settings, export, import |
| `js/version.js` | The app version (single source) |
| `js/prefs.js` | Applies the HQ display settings on every page: text size, game-page layout, background effects, and each game's own font, size and style. Holds the list of fonts a game can use |
| `sw.js`, `js/sw-register.js` | Offline cache. HQ is saved on the first visit; each game is saved the first time it is opened |
| `css/base.css` | Fonts, icons, shared helpers (every page) |
| `css/app.css` | Layout shared by the game pages; all colors are CSS variables |
| `css/theme-41.css`, `theme-5.css`, `theme-6.css` | Colors, fonts and animated background per game |
| `css/hq.css` | HQ page |
| `data/edf41.json`, `edf5.json`, `edf6.json` | Weapon data, one file per game |
| `data/edf41-legacy.json` | Maps the old checklist's saved positions to the new weapon ids |
| `fonts/` | Self-hosted fonts (SIL Open Font License, texts in `fonts/licenses`) |

Each data file also holds the drop tables: `drops = [{name, pack, missions, diffs}]`, where `diffs` has one `[lowestLevels, highestLevels]` pair per difficulty, listing what each mission can drop.

Data item format: `[id, name, level, source, upgrades]`; source `0` base, `1` starter, `2` DLC, `3` Mission Pack 1, `4` Mission Pack 2; upgrades `[[statIndex, maxStars], ...]`.

## Tools (Python 3)
| Command | What it does |
|---|---|
| `python3 tools/build_pages.py` | Regenerates `edf41.html`, `edf5.html`, `edf6.html` from one template. Edit the template, not the three pages. |
| `python3 tools/build_data.py ../edf-calc` | Rebuilds the data files from a clone of edf-calc. |
| `python3 tools/test_app.py` | Drives the whole app in headless Chromium (needs `pip install playwright` and `playwright install chromium`). Set `EDF_QUICK=1` for a faster run. |
| `python3 tools/test_browsers.py firefox` (or `webkit`) | Smoke test in Firefox and WebKit, the engine behind Safari (needs `pip install selenium` and the browser's driver). |

## Browser support
Written for browsers released since spring 2021: Safari and iOS 14.5+, Chrome and Edge 84+, Firefox 83+, Samsung Internet 14+. The JavaScript is ES2017 syntax in ES modules. On older browsers the layout loses its spacing (flex `gap`) and some background effects.

## Data source
Weapon names, levels, star caps and drop tables come from [edf-calc](https://github.com/zeddidragon/edf-calc) by Tony Sæle (zeddidragon), its sole contributor.
