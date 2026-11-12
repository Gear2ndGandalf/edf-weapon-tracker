# Changelog

Versions use `vMAJOR.MINOR.PATCH`. The current version is set in `js/version.js`
and shown on the HQ page.

- **MAJOR** – the save format changes in a way older exports cannot follow
- **MINOR** – new features
- **PATCH** – fixes and data corrections

## v1.4.1 – 2026-11-12
### Fixed
- **Importing the old EDF 4.1 checklist missed most weapons.** The lookup file used different category names (`assaultRifles`) from the ones the old site saves (`assault-rifles`), so only the six one-word categories matched: a complete checklist imported 161 weapons. `data/edf41-legacy.json` now uses the old site's own names, and a complete checklist imports all 812 entries as 820 of 827 weapons (each of the two "Pure Decoy Launchers" entries covers five launchers; the other 7 weapons were never on the old list).
- Anyone who answered the import offer before this version is offered it once more, because that import was incomplete. Importing only adds weapons; nothing already marked is removed.

### Changed
- `tools/test_app.py` checks the import with the old site's real category names and export format, and with a complete checklist.

## v1.4.0 – 2026-11-12
### Added
- **Text size slider** on HQ: any size from 60% to 150% in 5% steps, in place of the four fixed sizes (100–150%). Auto still follows the device, and a size saved before this version carries over. The weapon list's star meter narrows with small text so it stays in its column.

### Fixed
- **HQ on phones:** Export progress and Import progress were cut off behind the game bar on most phones. The game cards now give up height first and each setting sits on one row, so HQ fits on one screen on phones from about 800px tall (checked at 402×874, 390×844 and 412×800). On shorter screens HQ still scrolls, and now fades out above the game bar to show that it does.
- Firefox logged about 100 "glyph bbox was incorrect" warnings: the two Rajdhani font files stored wrong bounding boxes for 51 glyphs. They are rebuilt with correct boxes; outlines, metrics and character set are unchanged.
- A new version could start out with stale copies of some files for a few minutes after publishing. The offline cache now fetches its files past the browser's HTTP cache, and so does the update check.
- HQ asks iPhones not to enlarge its text in landscape, as the game pages already did.
- `tools/test_app.py` failed on Windows because it read files without naming UTF-8.

### Changed
- The HQ title goes on one line on shorter phone screens.

## v1.3.1 – 2026-11-11
### Fixed
- Browsers with a "force dark pages" feature (Opera GX, Chrome on Android, Samsung Internet) recolored the app: icons vanished from the title bar, selected tabs lost contrast and the toast turned brown. The pages now declare themselves dark, which turns that recoloring off.

### Changed
- The toast uses each game's own colors instead of one cream style.
- EDF 5's Max button is steel blue instead of orange-brown.

## v1.3.0 – 2026-11-11
### Added
- **Where each weapon drops:** mission ranges per difficulty for Offline, Online and the mission packs, from edf-calc's drop tables. EDF 5 and 6 show it on a Drops tab next to Upgrades; EDF 4.1 shows it in the weapon panel.
- **Tap a star** to set that level directly; tap the last lit star to turn it off. The − and + buttons remain.
- **Two profiles** (for example PC and console) with their own progress. Switch and rename them on HQ; exports and imports carry both.
- **Last export date** on HQ, with a note when progress has changed since.
- **Update notices:** a one-time "Updated to vX.X.X" message, and a Reload prompt when a new version installs while the app is open.
- Credit for edf-calc's author on HQ.
- `tools/test_browsers.py`: smoke test for Firefox and WebKit. `.nojekyll` so GitHub Pages serves the files as they are.

### Changed
- Progress is only rewritten when it actually changes.
- The toast button can carry any action (Undo, Reload).

## v1.2.0 – 2026-11-11
### Added
- App version (`js/version.js`), shown on HQ and written into export files.
- HQ display settings: text size (Auto follows the device, or 100–150%) and background effects on/off.
- Each category reopens at the scroll position where it was left, including after a search or reload.
- Hover and pressed feedback on every control.
- Compact rows for mouse users on desktop; touch screens keep 44px targets.
- Escape closes the category picker; a Reload button appears if weapon data fails to load.
- A friendly page when a game is opened offline before it has been saved.

### Changed
- The "Not ★" filter is now "To upgrade".
- EDF 4.1's selected row has a steady white outline instead of blinking.
- First visit downloads HQ only; each game is saved for offline use the first time it is opened.
- Long weapon names wrap instead of being cut off.
- Large text (130% and up) switches phones to a scrolling layout; star rows drop below their label when space is short.
- HQ's game bar stays on screen while the page scrolls.
- The offline cache is named after the app version, so a version bump refreshes every phone.

### Fixed
- With "reduce motion" on, EDF 6's background showed its highlight tiles at full strength and EDF 4.1 showed frozen radar pings.
- Progress cleared in another tab is now picked up.
- Keyboard focus stays in the list when a row leaves it (for example under the Missing filter).
- Export file names use the local date.
- Icons stay visible in Windows high-contrast mode.
- A weapon with full stars still counted as fully upgraded after being unchecked. Stars now count only while the weapon is owned, and come back if it is checked again.
- Removed an unused font weight.

## v1.1.0 – 2026-11-11
### Fixed
- Progress could be overwritten by a page restored with the Back button or left open in another tab.
- The list header stayed visible over the category picker.
- Tapping the current class tab reset the category.
- Small tap targets (checkboxes, collapse button) and a cramped list on phones held sideways.

### Changed
- Fonts are bundled with the site; nothing loads from other websites.
- Stars, check marks and arrows are drawn by the app instead of relying on device fonts.
- Background animations run on the GPU.
- Export uses the share sheet on phones when available.
- Imported files are validated and cleaned.

### Added
- Arrow-key navigation in the list, screen-reader labels.
- `tools/build_pages.py`, `tools/build_data.py`, `tools/test_app.py`.

## v1.0.0 – 2026-10-29
- First release: EDF 4.1, 5 and 6 weapon and vehicle tracking, star upgrades for EDF 5 and 6,
  search, filters, undo, export/import, offline support, import from the old EDF 4.1 checklist.
