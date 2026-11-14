# Changelog

Versions use `vMAJOR.MINOR.PATCH`. The current version is set in `js/version.js`
and shown on the HQ page.

- **MAJOR** – the save format changes in a way older exports cannot follow
- **MINOR** – new features
- **PATCH** – fixes and data corrections

## v1.9.1 – 2026-11-13
### Fixed
- **Italic text was cut off at the right edge** of the class tabs (Ranger, W.Diver, A.Raider, Fencer), the category button and, with some fonts, the title. Slanted letters lean out of their box, and those boxes clip their text; they now leave room for the last letter. Seen on phones with Italic switched on for a game.
- **The list of upgrades jumped back to the top** every time a star was changed, because the panel is redrawn on each change. It now stays where it was scrolled to while the same weapon is shown (EDF 5 and 6, on phones with Game pages set to Fit screen, upright or sideways).
- **Edits under Missing or To upgrade went to the wrong weapon.** When a change took the current weapon out of the filtered list (the first star marks it owned; the last star finishes it), the panel jumped to the first weapon in the list, and the next taps changed that one, without any notice. The panel now stays on the weapon you are editing until you pick another or change the list.
- **Undo took back too much.** After Clear or Mark all, an Undo pressed a few seconds later also removed everything changed in between. Undo is now withdrawn as soon as something else is changed.
- **Short phone screens** (about 680 px tall or less with the browser's bars showing, for example Safari on a small iPhone): with Fit screen, an opened weapon had room for one row of upgrades or none. Such a screen now scrolls as a page once a weapon with a longer list is opened.
- **Opening a game or profile that has no progress** no longer counts as a change (HQ said "Progress has changed since the last export").
- **Fully upgraded on HQ** is counted again after a backup is imported, instead of trusting the number in the file.
- **Import from game save:** if "Also read star levels" is unticked after a preview, Add and Match now leave the stars alone in every case.
- **Keyboard:** when "+" reaches the top or "−" reaches zero, the focus moves to the other button instead of being lost. Changing the filter shows the list from the top.
- **A value of a Lock-on line that has its row elsewhere** is now named for what it is on that line: "Targets · same as Capacity" instead of a second "Capacity" (missile launchers).
- **Search** finds the two EDF 5 weapons whose names the game writes with two spaces or a full-width letter (HS99 Bound Gun, Stardust Cannon A) when you type them as they look. The hint under an empty search no longer suggests setting the filter to All when it already is.
- **Wording.** The update note on HQ reads as sentences. The import preview says "Raise stars:" when that is the button. The warning before importing a backup says that a profile that is empty in the file becomes empty here. Messages about a wrong save file no longer suggest changing the Game, which is chosen by the file itself. Screen readers hear "Lock-on, Range" instead of "Lock-on: Range:".

### Notes
- Everything after the first two fixes was found by a check of the whole app that followed them.
- Still open, because they change counts or how the app behaves and should be decided first: the "Empty" / "Not Equipped" placeholders are counted as weapons (4 per game in EDF 5 and 6); stars for upgrades with fewer than five steps can be set by hand to values the game never shows (4 of a 4-step upgrade); "Fully upgraded" has no "out of" number; the Undo note covers a star row of the panel for a few seconds on phones; Import from game save needs one online use before it works offline; Safari fetches the weapon list twice on a first visit.

## v1.9.0 – 2026-11-13
### Changed
- **Upgrades follow the game's equipment screen exactly** (EDF 5 and 6). The lines, their names and their order are now read from the games' own weapon text, weapon by weapon, instead of being guessed from a list of stat names. So a rifle shows Capacity, ROF, Damage, Reload Time, Range, Shot Speed, Accuracy, a sentry gun shows Number, and an air strike shows Re-request, as in the game. Saved stars are not affected: only names and the order on screen change.
- **Lines with two values show the game's star.** Where the game prints one star for two values (Damage × Count on shotguns and Wing Diver weapons, Lock-on range and targets, a Fencer's melee Damage and Range), the tracker shows that line with "In game: ☆4" and the two values under it. The game's star is their average, and half a star is printed as "+" (☆4+ is 4.5).
- A value the game shows on two lines (Range and Shot Speed come from the same upgrade) has one row of stars; the second line says which row it repeats.

### Added
- **Three Fencer upgrades that were missing**: Charge Speed, Swing Speed and Ready Speed (45 weapons in EDF 5, 60 in EDF 6). They are added after each weapon's other upgrades, so saved stars keep their places. A weapon that counted as fully upgraded without them is no longer counted until they are filled in.

### Fixed
- **Imported stars for upgrades with fewer than five steps.** v1.8.1 showed such an upgrade as its level plus the missing steps. That was right for a finished upgrade and wrong for an unfinished one. The game stretches the level onto 0 to 5 (level × 5 ÷ steps, rounded down): with 3 steps the levels 0, 1, 2, 3 are ☆0, ☆1, ☆3 and ★5. The import now does the same.
  - **If you imported stars with v1.8.0 or v1.8.1, import the same save again and choose Match the save.** That sets every star to what the game shows. (Add never lowers a star, and stars imported with v1.8.1 have to come down.) If Match the save is not offered, nothing has to come down: choose Raise stars or Add.
- `tools/build_data.py` as published with v1.8.1 stopped with an error (a variable was used for two things). It runs again.

### Notes
- The rules above were read from the games' program code (EDF 5: `EDF5.exe`, EDF 6: `EDF.dll`) and the lines from `WEAPONTEXT` in `Root.cpk`. Checked against the game: EDF 5 Spark Vine Y3 matches on every line, including Damage ☆4 (Damage ☆3 and Count ★5). On three real saves, all 2,342 star lines the tracker shows after an import equal a separate calculation from the save's bytes.
- New facts file `tools/game-lines/` (which lines each weapon has and what they show). Item format in `data/edf5.json` and `data/edf6.json` gained a sixth entry, `lines`.
- Changing one upgrade's stars keeps stars saved for upgrades the page does not know yet (an older copy of the weapon list during an update).
- `tools/build_data.py` refuses to write data in which a weapon's upgrades would change places.

## v1.8.1 – 2026-11-13
### Fixed
- **Star maximums are back to what the game shows.** v1.8.0 lowered the maximum of stats that have fewer than five upgrade steps (to one to four stars). That was a mistake: the game shows such a stat on a scale that still ends at five, so a stat with two steps reads ★5 when it is finished, not ★2. Every maximum is again what it was up to v1.7.0.
- **Imported stars match the game's equipment screen** (not for unfinished upgrades with fewer than five steps; corrected in v1.9.0). A save holds each stat's level, from 0 up to its number of steps. For a stat with fewer than five steps the game shows the level plus the missing steps (level 2 of 2 is shown as 5), and the import now does the same. v1.8.0 brought such stats over too low.
  - **If you imported stars with v1.8.0, import the same save again and choose Add (or Raise stars).** That lifts the stats that came over too low. Nothing is lowered. (Superseded: see v1.9.0, which asks for Match the save.)
  - A weapon whose stars you changed by hand in v1.8.0 may have kept the lowered value on such a stat; set it again or import your save.
- **Stat names follow the game.** The reload stat of Wing Diver weapons that run on energy is **Charge Time**, and EDF 5's shot speed stat is **Range**, as on the game's equipment screen (since v1.9.0 each weapon uses its own line names, so some show Shot Speed). Saved stars are not affected by the new names.
- **Stats are listed in the order of the game's equipment screen** (Capacity, Rate of Fire, Damage, … Energy Cost, Charge Time) instead of the order of the source data. Only the order on screen changes; saved stars stay with their stat. The order was compared with the game on three weapons; stats those do not have (Burst Rate, Blast Radius, Lock Range, Lock Time, and the Fencer's spin-up Charge Time) are placed by best guess.

### Notes
- Checked against the game on two weapons (EDF 6 Lightning Bow and EDF 5 Spark Vine Y3): every star the tracker imports is the one on the equipment screen, with one difference that remains. The game shows a single star for Damage on weapons that fire several shots at once ("44.4 × 3") and folds the number of shots into it; the tracker keeps **Damage** and **Count** as two stats, so the Damage star can differ from the game's by one or two on those weapons. (Resolved in v1.9.0: that star is the average of Damage and Count, and the tracker shows it.)
- The scale for stats with fewer than five steps was confirmed on finished stats (level 2 of 2 and 3 of 3 both read ★5 in the game). Levels in between follow from how the games work out a stat's value (★5 is always the listed value), but have not been compared with the equipment screen yet. (Wrong for levels in between; corrected in v1.9.0.)
- HQ now lists what is new also when the update was first met on a game page, and counts fully upgraded weapons again after this update (the count had been made with the lowered maximums).
- Changing one stat's stars no longer rewrites the weapon's other stats.

## v1.8.0 – 2026-11-13
### Added
- **Import from game save reads star levels** (EDF 5 and 6). **Add** raises stars and never lowers one. **Match the save** sets them to the save's levels. **Undo** puts them back, except on a weapon whose stars you changed again afterwards; such a weapon also stays marked. Untick "Also read star levels" to bring over the weapons only.
- A profile that already has a save's weapons but not its stars is offered **Raise stars**.

### Fixed
- **Stats that stop below five stars** (this was wrong and is undone in v1.8.1). Some upgrades end at one to four stars in the games, but the tracker showed five for them, so a weapon that was finished in the game still looked unfinished here: 269 stats on 262 weapons in EDF 5, and 334 stats on 322 weapons in EDF 6. They now show the games' own maximum. Stars saved above a new maximum count as that maximum; nothing else about saved progress changes.

### Notes
- The star maximums and the place of each stat's stars in a save come from the games' own weapon files (`tools/game-stars/`), and were checked against real saves: every one of 2,380 star values fits, and 623 sit exactly at their maximum.
- 45 weapons in EDF 5 and 60 in EDF 6 (Fencer melee weapons among them) have one more upgradable stat in the game than edf-calc and the tracker list. That stat is not shown or imported yet.
- `tools/build_data.py` now also needs `tools/game-stars/`, and writes the "stars" lists of `data/edf5-save.json` and `data/edf6-save.json`.

## v1.7.0 – 2026-11-13
### Added
- **Import from game save** (HQ, PC version on Steam): choose your `MAIN.GST` and the tracker marks the weapons that save owns, for EDF 4.1, 5 and 6. The file is read on the device and never uploaded.
  - Pick the game and the profile to fill. The four PC profiles match the game's four save slots (`saveslot00` to `saveslot03`).
  - Nothing changes until you have seen the result: how many weapons the save owns and how that differs from the profile. **Add** only marks more weapons; **Match the save** also unmarks weapons the save does not own. **Undo** puts the profile back.
  - A save picked under the wrong game is recognised by its size. Files that are damaged, cut off, or in a format the tracker does not know are refused with nothing changed.
  - Star levels are not read yet (EDF 5 and 6): the save holds them, but in an order that still has to be worked out per weapon type.
- `js/savefile.js` (the reader) and `data/<game>-save.json` (which weapon each position in a save stands for).

### Notes
- Console saves cannot be read: PlayStation and Switch do not give players a readable save file.
- Save layouts were checked against real saves of all three games. Thanks to FevGrave's public-domain EDFSaveEditor for the first description of them.
- `tools/test_app.py` builds its own sample saves from a second, independent description of the layouts, so no real save is stored in the repository.

## v1.6.0 – 2026-11-12
### Added
- **Each game's own text**, set on HQ under the game's profiles: a font, a size and a style (Bold, Italic, Caps), with a line of sample text. Size starts on Same, which follows the Text size for all pages; the slider gives that game its own size from 60% to 150%.
- **Six more fonts** to pick from, all under the SIL Open Font License (texts in `fonts/licenses`): Orbitron, Exo 2, Chakra Petch, Tektur, Quantico and Jura. Each game's own font and the three other fonts the app already had (Oxanium, Rajdhani, Saira Condensed, Share Tech Mono) are in the list too. A font is only downloaded once a page uses it, and it is kept for offline use with that game.

### Fixed
- On very narrow phones (about 280px wide) the header of the details panel, with its Max and Clear buttons, was partly cut off. A game page that cannot fit one screen now switches to the scrolling layout by itself, which also covers wide fonts and capitals.

### Changed
- The Text size setting is unchanged, and now also stands for every game set to Same.
- On a game page, the Owned and star counters move below the title when a wide font leaves no room beside it.
- The two Chakra Petch files had an invalid header field that Firefox would warn about; it is corrected, with the letter shapes untouched.
- Game pages also apply their settings when opened without `.html` in the address.

## v1.5.0 – 2026-11-12
### Added
- **Eight profiles per game**, one for each save slot: four for PC and four for console, so 24 in all. Each game has its own profile in use. On HQ, pick a game under Profiles, then tap a profile to use it; every profile shows its own progress and can be renamed. Game cards and game pages name the profile in use once a game uses more than one.
- **Game pages: Taller lists** (HQ setting, for phones and tablets). The weapon list becomes nearly as tall as the screen, upgrades and drops are shown in full, and the page scrolls. Fit screen, the layout until now, stays the default.

### Changed
- The two profiles of v1.3–v1.4 carry over without any conversion: Profile 1 is PC 1 and Profile 2 is Console 1 in every game, with their names and progress. Whichever was selected stays selected.
- Export files hold all 24 profiles and their names. Files from earlier versions still import, and v1.4 can still read the PC 1 and Console 1 parts of a new file.
- HQ scrolls on phones now that it holds the profile list; the three game cards stay on the first screen.
- On wide screens the HQ game cards shrink a little on short windows.

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
