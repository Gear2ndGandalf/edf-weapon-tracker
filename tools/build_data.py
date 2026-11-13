#!/usr/bin/env python3
"""Rebuilds data/edf41.json, data/edf5.json and data/edf6.json from edf-calc.

Source: https://github.com/zeddidragon/edf-calc  (files public/edf/weapons-41.json,
weapons-5.json, weapons-6.json). That repository has no license file; ask its
author before publishing the data.

Usage (from the repository root):
    git clone --depth 1 https://github.com/zeddidragon/edf-calc.git ../edf-calc
    python3 tools/build_data.py ../edf-calc

Output item format: [id, name, level, source, upgrades, lines]
    source   0 base, 1 starter, 2 DLC/bonus, 3 Mission Pack 1, 4 Mission Pack 2
    upgrades [[statIndex, maxStars], ...]  (only for games with star upgrades)
    lines    [[statIndex, [upgrade, ...]], ...]  the lines of the game's equipment screen that
             carry a star, in the game's order: the line's label and which upgrades it shows
Drop tables: drops = [{name, pack, missions, diffs: [[lowLevels], [highLevels]] per difficulty}]

Star upgrades use two sets of facts taken from the games' own files (EDF 5 and EDF 6):

tools/game-stars/<game>.json   id -> [[slot, stat code, steps], ...]
    Every upgradable value of a weapon. "Slot" is where the game's save file keeps its level,
    "steps" is how many levels it has (a save holds 0..steps).
tools/game-lines/<game>.json   id -> [[label, [slot, ...]], ...]
    The lines of the equipment screen that show a star, in the game's order and wording, and the
    values each line shows. They come from the game's weapon text (WEAPONTEXT in Root.cpk).

How the game turns a level into the star it prints (read from the games' program code):
    5 steps or more:  the star is the level, and the top is "steps" stars.
    fewer than 5:     the star is level * 5 // steps, so the top is always 5.
    A line with several values (Damage x Count, Lock-on range and targets) prints the average of
    their stars. Half a star is printed as "+".
So an upgrade's maxStars is max(5, steps), which is what edf-calc lists too; this script checks it.

Upgrades are named as the game names their line. A value that shares a line with another is
named "<line>: <part>" (the Damage line itself keeps "Damage"); the first line that shows a
value decides. The upgrades edf-calc lists come
first, in its order, and values only the game files have (three Fencer speeds) are added after
them, so the positions that saved progress uses never move.

Slot and steps are written into data/edf5-save.json and data/edf6-save.json ("stars": for each
save position, two characters per upgrade in the item's order: the slot, then the steps as a
base-36 digit), which js/savefile.js uses for "Import from game save". The "rows" of those
files are kept as they are.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# edf-calc class key -> (full name, short tab label), in in-game order
CLASSES = [("ranger", "Ranger", "Ranger"), ("winger", "Wing Diver", "W.Diver"),
           ("bomber", "Air Raider", "A.Raider"), ("fencer", "Fencer", "Fencer")]

# What a value is called when it shares its line with another: the game's number for the kind of
# value (stat code // 4) -> name. On a Lock-on line the second value is the number of targets.
PART_LABELS = {0: "Capacity", 1: "Count", 2: "Damage", 3: "Accuracy", 4: "Range", 5: "Reload", 6: "ROF", 7: "ROF",
               8: "Blast Area", 9: "Range", 10: "Lock-on Time", 11: "Energy Cost", 20: "Speed"}


def part_label(line: str, code: int) -> str:
    kind = code >> 2
    part = "Targets" if line.startswith("Lock-on") and kind in (0, 1) else PART_LABELS[kind]
    return line if part == line else f"{line}: {part}"


# The game's own number for each kind of stat (the second number of a star entry in a weapon file).
STAT_CODES = {"ammo": 0, "count": 4, "damage": 8, "hp": 8, "accuracy": 13, "speed": 16, "reload": 21,
              "interval": 25, "burstRate": 29, "radius": 32, "lockRange": 36, "lockTime": 41, "energy": 45, "windup": 80}
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"

# Spelling fixes applied to the source names
NAME_FIXES = {"Elerctormagnetic": "Electromagnetic"}

GAMES = [("41", "EDF 4.1", False), ("5", "EDF 5", True), ("6", "EDF 6", True)]

# edf-calc mode name -> (label, mission pack number; 0 = main game)
MODES = {"OFF": ("Offline", 0), "ON": ("Online", 0), "DLC1": ("Mission Pack 1", 1), "DLC2": ("Mission Pack 2", 2)}


def drop_tables(src: dict) -> tuple[list[str], list[dict]]:
    """Per mode and difficulty: the lowest and highest weapon level each mission can drop."""
    difficulties = [d["name"] for d in src["modes"][0]["difficulties"]]
    tables = []
    for mode in src["modes"]:
        label, pack = MODES.get(mode["name"], (mode["name"], 0))
        n = mode["missions"]
        if [d["name"] for d in mode["difficulties"]] != difficulties:
            raise SystemExit(f"difficulty list differs in mode {mode['name']}")
        tables.append({"name": label, "pack": pack, "missions": n,
                       "diffs": [[d["dropsLow"][:n], d["dropsHigh"][:n]] for d in mode["difficulties"]]})
    return difficulties, tables


def source_code(weapon: dict) -> int:
    if str(weapon.get("odds")) == "starter":
        return 1
    if weapon.get("dlc") == 1:
        return 3
    if weapon.get("dlc") == 2:
        return 4
    if str(weapon.get("odds")) == "dlc":
        return 2
    return 0


def build(calc_dir: Path, key: str, title: str, has_stars: bool) -> int:
    src = json.loads((calc_dir / "public" / "edf" / f"weapons-{key}.json").read_text(encoding="utf-8"))
    stats: list[str] = []
    # From the game's weapon files: id -> [[slot, stat code, steps], ...]
    facts = json.loads((ROOT / "tools" / "game-stars" / f"edf{key}.json").read_text(encoding="utf-8")) if has_stars else {}
    places: dict[str, str] = {}   # id -> where its upgrades' stars are in a save (see the note at the top)
    game_lines = json.loads((ROOT / "tools" / "game-lines" / f"edf{key}.json").read_text(encoding="utf-8")) if has_stars else {}
    few = unlisted = 0   # values with fewer than 5 steps; values edf-calc does not list

    def stat_index(label: str) -> int:
        if label not in stats:
            stats.append(label)
        return stats.index(label)

    seen_ids: set[str] = set()
    classes = []
    for char, full, short in CLASSES:
        cats = []
        for header in src["headers"][char]:
            mine = [w for w in src["weapons"] if w["character"] == char and w["category"] == header["category"]]
            if not mine:
                continue
            mine.sort(key=lambda w: max(0, w["level"]))  # stable: ties keep the source order
            items = []
            for w in mine:
                if w["id"] in seen_ids:
                    raise SystemExit(f"duplicate weapon id in EDF {key}: {w['id']}")
                seen_ids.add(w["id"])
                name = w["names"]["en"]
                for wrong, right in NAME_FIXES.items():
                    name = name.replace(wrong, right)
                item = [w["id"], name, max(0, w["level"]), source_code(w)]
                if has_stars:
                    star_facts = facts.get(w["id"], [])
                    known = {code: (slot, steps) for slot, code, steps in star_facts}
                    if len(known) != len(star_facts) or len({slot for slot, _, _ in star_facts}) != len(star_facts):
                        raise SystemExit(f"EDF {key} {w['id']}: tools/game-stars/edf{key}.json repeats a stat code or a slot")
                    order = []   # (slot, steps, stat code) of each upgrade, in the order progress is saved in
                    for k, v in w.items():
                        if not (isinstance(v, dict) and "lvMax" in v):
                            continue
                        if k not in STAT_CODES or v.get("algo") != STAT_CODES[k] or STAT_CODES[k] not in known:
                            raise SystemExit(f"EDF {key} {w['id']}: stat {k!r} is not in tools/game-stars/edf{key}.json as expected")
                        slot, steps = known[STAT_CODES[k]]
                        if not (0 <= slot <= 7 and 1 <= steps <= 10 and max(5, steps) == v["lvMax"]):
                            raise SystemExit(f"EDF {key} {w['id']}: unexpected star data for {k!r}: slot {slot}, steps {steps}, edf-calc max {v['lvMax']}")
                        order.append((slot, steps, STAT_CODES[k]))
                    listed = {slot for slot, _, _ in order}
                    if len(listed) != len(order):
                        raise SystemExit(f"EDF {key} {w['id']}: two of edf-calc's stats are the same value in the game's files")
                    extra = sorted((slot, steps, code) for slot, code, steps in star_facts if slot not in listed)
                    if any(not (0 <= slot <= 7 and 1 <= steps <= 10) for slot, steps, _ in extra):
                        raise SystemExit(f"EDF {key} {w['id']}: unexpected star data in tools/game-stars/edf{key}.json")
                    unlisted += len(extra)
                    order += extra   # values edf-calc does not list go last, so saved progress keeps its places
                    few += sum(steps < 5 for _, steps, _ in order)
                    at = {slot: i for i, (slot, _, _) in enumerate(order)}
                    code_of = {slot: code for slot, _, code in order}
                    shown = game_lines.get(w["id"], [])
                    if ({s for _, slots in shown for s in slots} != set(at)
                            or any(not label or not slots or len(set(slots)) != len(slots) for label, slots in shown)):
                        raise SystemExit(f"EDF {key} {w['id']}: tools/game-lines/edf{key}.json does not show the star values of tools/game-stars/edf{key}.json")
                    names: dict[int, str] = {}   # slot -> the name of its upgrade: the first line that shows it
                    for label, slots in shown:
                        for slot in slots:
                            if slot not in names:
                                names[slot] = label if len(slots) == 1 else part_label(label, code_of[slot])
                    if len(set(names.values())) != len(names):
                        raise SystemExit(f"EDF {key} {w['id']}: two of its upgrades would get the same name {sorted(names.values())}")
                    ups = [[stat_index(names[slot]), max(5, steps)] for slot, steps, _ in order]
                    places[w["id"]] = "".join(str(slot) + DIGITS[steps] for slot, steps, _ in order)
                    if ups:
                        item.append(ups)
                        item.append([[stat_index(label), [at[slot] for slot in slots]] for label, slots in shown])
                items.append(item)
            cats.append({"name": header["names"]["en"], "items": items})
        classes.append({"name": full, "short": short, "cats": cats})

    difficulties, drops = drop_tables(src)
    out = {"game": title, "key": "edf" + key, "hasStars": has_stars, "stats": stats,
           "difficulties": difficulties, "drops": drops, "classes": classes}
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    save_map = ROOT / "data" / f"edf{key}-save.json"
    before = json.loads(save_map.read_text(encoding="utf-8")) if has_stars else {}
    rows = before.get("rows", [])
    if has_stars and set(rows) != seen_ids:  # checked before anything is written, so the two files cannot fall out of step
        raise SystemExit(f"data/edf{key}-save.json does not list the same weapons as edf-calc; nothing was written for EDF {key}")
    # Saved progress goes by an upgrade's place in its weapon's list. A place must never change: upgrades may only be added at the end.
    moved = [i for i, was in zip(rows, before.get("stars", [])) if not places[i].startswith(was)]
    if moved:
        raise SystemExit(f"EDF {key}: the upgrades of {moved[:5]} would change places, which would mix up saved stars; nothing was written")
    (ROOT / "data" / f"edf{key}.json").write_text(text, encoding="utf-8")
    if has_stars:
        save_map.write_text(json.dumps({"game": "edf" + key, "rows": rows, "stars": [places[i] for i in rows]},
                                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {title}: {few} upgrades have fewer than 5 steps (the game shows their top as 5 stars); "
              f"{unlisted} upgrades come from the game files only (edf-calc does not list them)")
    missing = len(src["weapons"]) - len(seen_ids)
    if missing:
        print(f"  warning: {missing} source weapons were not placed in any category")
    return len(seen_ids)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    calc = Path(sys.argv[1]).resolve()
    for key, title, has_stars in GAMES:
        total = build(calc, key, title, has_stars)
        print(f"{title}: {total} weapons  ->  data/edf{key}.json")
    print("If a total changed, update TOTALS in js/store.js. Raise the version in js/version.js before publishing.")
