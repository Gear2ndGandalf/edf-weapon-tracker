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
                    ups = [[stat_index(STAT_LABELS.get(k, k)), v["lvMax"]]
                           for k, v in w.items() if isinstance(v, dict) and "lvMax" in v]
                    if ups:
                        item.append(ups)
                items.append(item)
            cats.append({"name": header["names"]["en"], "items": items})
        classes.append({"name": full, "short": short, "cats": cats})

    difficulties, drops = drop_tables(src)
    out = {"game": title, "key": "edf" + key, "hasStars": has_stars, "stats": stats,
           "difficulties": difficulties, "drops": drops, "classes": classes}
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    (ROOT / "data" / f"edf{key}.json").write_text(text, encoding="utf-8")
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
    print("If a total changed, update TOTALS in js/store.js and bump VERSION in sw.js.")
