#!/usr/bin/env python3
"""Rebuilds data/edf41.json, data/edf5.json and data/edf6.json from edf-calc.

Source: https://github.com/zeddidragon/edf-calc  (files public/edf/weapons-41.json,
weapons-5.json, weapons-6.json). That repository has no license file; ask its
author before publishing the data.

Usage (from the repository root):
    git clone --depth 1 https://github.com/zeddidragon/edf-calc.git ../edf-calc
    python3 tools/build_data.py ../edf-calc

Output item format: [id, name, level, source, upgrades]
    source   0 base, 1 starter, 2 DLC/bonus, 3 Mission Pack 1, 4 Mission Pack 2
    upgrades [[statIndex, maxStars], ...]  (only for games with star upgrades)
Drop tables: drops = [{name, pack, missions, diffs: [[lowLevels], [highLevels]] per difficulty}]

Star upgrades also use tools/game-stars/edf5.json and edf6.json. Those hold, for every weapon,
what the game's own weapon files say about each upgradable stat: [slot, stat code, steps].
"Slot" is where the game's save file keeps that stat's level. "Steps" is how many levels the
stat has. The game shows a level as stars so that 5 is always reachable: a stat with 5 or more
steps shows its level as it is (up to "steps" stars), and a stat with fewer steps shows its
level plus (5 - steps), so its top is 5 stars. That is why edf-calc's maxStars is never below 5;
this script checks that it equals max(5, steps) for every stat.
Slot and steps are written into data/edf5-save.json and data/edf6-save.json ("stars": for each
save position, two characters per upgrade in the item's order: the slot, then the steps as a
base-36 digit), which js/savefile.js uses for "Import from game save". The "rows" of those
files are kept as they are.

Stat names follow the games' own equipment screens where they are known: EDF 5 shows the
shot-speed stat as Range, and Wing Diver weapons that draw energy show reloading as Charge Time.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# edf-calc class key -> (full name, short tab label), in in-game order
CLASSES = [("ranger", "Ranger", "Ranger"), ("winger", "Wing Diver", "W.Diver"),
           ("bomber", "Air Raider", "A.Raider"), ("fencer", "Fencer", "Fencer")]

# edf-calc stat key -> label shown in the upgrade panel
STAT_LABELS = {
    "damage": "Damage", "reload": "Reload", "ammo": "Capacity", "speed": "Shot Speed",
    "interval": "Rate of Fire", "accuracy": "Accuracy", "radius": "Blast Radius",
    "energy": "Energy Cost", "count": "Count", "lockRange": "Lock Range",
    "lockTime": "Lock Time", "burstRate": "Burst Rate", "windup": "Charge Time", "hp": "Durability",
}

def stat_label(key: str, stat: str, weapon: dict) -> str:
    """The name the game's equipment screen uses for a stat, where that differs from STAT_LABELS."""
    energy = weapon.get("energy")
    uses_energy = isinstance(energy, dict) or (isinstance(energy, (int, float)) and energy > 0)
    if stat == "reload" and weapon.get("character") == "winger" and uses_energy:
        return "Charge Time"
    if stat == "speed" and key == "5":
        return "Range"
    return STAT_LABELS.get(stat, stat)


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
    short = unlisted = 0

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
                    mine = facts.get(w["id"], [])
                    known = {code: (slot, steps) for slot, code, steps in mine}
                    if len(known) != len(mine) or len({slot for slot, _, _ in mine}) != len(mine):
                        raise SystemExit(f"EDF {key} {w['id']}: tools/game-stars/edf{key}.json repeats a stat code or a slot")
                    ups, where = [], ""
                    for k, v in w.items():
                        if not (isinstance(v, dict) and "lvMax" in v):
                            continue
                        if k not in STAT_CODES or v.get("algo") != STAT_CODES[k] or STAT_CODES[k] not in known:
                            raise SystemExit(f"EDF {key} {w['id']}: stat {k!r} is not in tools/game-stars/edf{key}.json as expected")
                        slot, steps = known[STAT_CODES[k]]
                        if not (0 <= slot <= 7 and 1 <= steps <= 10 and max(5, steps) == v["lvMax"]):
                            raise SystemExit(f"EDF {key} {w['id']}: unexpected star data for {k!r}: slot {slot}, steps {steps}, edf-calc max {v['lvMax']}")
                        short += steps < 5
                        ups.append([stat_index(stat_label(key, k, w)), v["lvMax"]])
                        where += str(slot) + DIGITS[steps]
                    if len({s for s, _ in ups}) != len(ups):
                        raise SystemExit(f"EDF {key} {w['id']}: two of its stats would get the same name")
                    unlisted += len(known) > len(ups)
                    places[w["id"]] = where
                    if ups:
                        item.append(ups)
                items.append(item)
            cats.append({"name": header["names"]["en"], "items": items})
        classes.append({"name": full, "short": short, "cats": cats})

    difficulties, drops = drop_tables(src)
    out = {"game": title, "key": "edf" + key, "hasStars": has_stars, "stats": stats,
           "difficulties": difficulties, "drops": drops, "classes": classes}
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    save_map = ROOT / "data" / f"edf{key}-save.json"
    rows = json.loads(save_map.read_text(encoding="utf-8"))["rows"] if has_stars else []
    if has_stars and set(rows) != seen_ids:  # checked before anything is written, so the two files cannot fall out of step
        raise SystemExit(f"data/edf{key}-save.json does not list the same weapons as edf-calc; nothing was written for EDF {key}")
    (ROOT / "data" / f"edf{key}.json").write_text(text, encoding="utf-8")
    if has_stars:
        save_map.write_text(json.dumps({"game": "edf" + key, "rows": rows, "stars": [places[i] for i in rows]},
                                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {title}: {short} stats have fewer than 5 steps (the game shows their top as 5 stars); "
              f"{unlisted} weapons have a star stat in the game that edf-calc does not list")
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
