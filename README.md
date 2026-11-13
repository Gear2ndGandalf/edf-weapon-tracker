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
| `js/savefile.js` | Reads the owned weapons, and in EDF 5 and 6 their star levels, out of a game's own PC save file (HQ: Import from game save). The layout is described at the top of the file |
| `data/edf41-save.json`, `edf5-save.json`, `edf6-save.json` | For each position in a save's weapon table, the tracker's weapon id and, in EDF 5 and 6, where that weapon's star levels are |
| `tools/game-stars/edf5.json`, `edf6.json` | From the games' own weapon files: for every weapon, each upgradable value's place in a save, the game's number for the kind of value, and how many upgrade steps it has |
| `tools/game-lines/edf5.json`, `edf6.json` | From the games' own weapon text: for every weapon, the lines of the equipment screen that carry a star, in the game's order, with the game's label and the values each line shows |
| `fonts/` | Self-hosted fonts (SIL Open Font License, texts in `fonts/licenses`) |

Each data file also holds the drop tables: `drops = [{name, pack, missions, diffs}]`, where `diffs` has one `[lowestLevels, highestLevels]` pair per difficulty, listing what each mission can drop.

Data item format: `[id, name, level, source, upgrades, lines]`; source `0` base, `1` starter, `2` DLC, `3` Mission Pack 1, `4` Mission Pack 2; upgrades `[[statIndex, maxStars], ...]`; lines `[[statIndex, [upgrade, ...]], ...]` are the lines of the game's equipment screen that carry a star, in the game's order (the label, and which upgrades the line shows). Saved stars follow the order of `upgrades`, which must never change for a weapon; new upgrades are added at the end.

## Tools (Python 3)
| Command | What it does |
|---|---|
| `python3 tools/build_pages.py` | Regenerates `edf41.html`, `edf5.html`, `edf6.html` from one template. Edit the template, not the three pages. |
| `python3 tools/build_data.py ../edf-calc` | Rebuilds the data files from a clone of edf-calc, together with `tools/game-stars/` and `tools/game-lines/` (see Data source). It also writes where each upgrade's stars sit in a save into `data/edf5-save.json` and `data/edf6-save.json`. |
| `python3 tools/test_app.py` | Drives the whole app in headless Chromium (needs `pip install playwright` and `playwright install chromium`). Set `EDF_QUICK=1` for a faster run. |
| `python3 tools/test_browsers.py firefox` (or `webkit`) | Smoke test in Firefox and WebKit, the engine behind Safari (needs `pip install selenium` and the browser's driver). |

## Browser support
Written for browsers released since spring 2021: Safari and iOS 14.5+, Chrome and Edge 84+, Firefox 83+, Samsung Internet 14+. The JavaScript is ES2017 syntax in ES modules. On older browsers the layout loses its spacing (flex `gap`) and some background effects.

## Data source
Weapon names, levels and drop tables come from [edf-calc](https://github.com/zeddidragon/edf-calc) by Tony Sæle (zeddidragon), its sole contributor.

The layout of the games' PC save files, used by Import from game save, was first described in [EDFSaveEditor](https://github.com/FevGrave/EDFSaveEditor) by FevGrave (public domain, CC0). Each game's layout was then checked against real saves. The tracker only reads a save; it never changes one, and the file never leaves the device.

The upgrades of EDF 5 and EDF 6 come from the games' own files (PC), read from an installed copy: which lines the equipment screen shows for a weapon, their names and order (the weapon text, `WEAPONTEXT`), how many steps each upgradable value has, and where a save keeps its level (the weapon files). A save holds a level from 0 up to the number of steps. The games print it as a star: with five steps or more the star is the level; with fewer, the level is stretched onto 0 to 5 (level × 5 ÷ steps, rounded down), so every upgrade can reach at least ★5. A line that shows two values prints the average of their stars, and half a star as "+". These rules were read from the games' program code. The tracker's star maximums are therefore the larger of five and the number of steps, which is also what edf-calc lists, and Import from game save converts levels the same way.
