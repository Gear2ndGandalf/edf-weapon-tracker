#!/usr/bin/env python3
"""End-to-end checks for the tracker, run in a headless browser.

Setup once:   pip install playwright && playwright install chromium
Run:          python3 tools/test_app.py
(Set EDF_CHROME to a browser binary to use one that is already installed.)

The script serves the repository on a local port, drives every control and
checks layout at several screen sizes. It exits with status 1 on any failure.
"""
import asyncio
import base64
import hashlib
import json
import re
import struct
import zlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765
BASE = f"http://localhost:{PORT}/"
PHONE = {"width": 390, "height": 844}
SIZES = [(280, 653), (320, 568), (360, 640), (375, 667), (390, 700), (390, 844), (430, 932),
         (667, 375), (844, 390), (932, 430), (768, 1024), (1280, 800), (1920, 1080)]
if os.environ.get("EDF_QUICK"):  # faster run while developing: four representative sizes
    SIZES = [(320, 568), (390, 844), (844, 390), (1280, 800)]
fails: list[str] = []
SERVER = None
# The old EDF 4.1 checklist (EDF-4.1-PWA): its storage keys, category ids and the number of
# weapons in each category, copied from that site's Ranger.js, Wingdiver.js, AirRaider.js and
# Fencer.js. A save is { categoryId: [position, ...] }. data/edf41-legacy.json must match this.
OLD_CHECKLIST = {
    "rangerSave": {"assault-rifles": 30, "shotguns": 24, "sniper-rifles": 26, "rocket-launchers": 21, "missile-launchers": 18, "grenades": 40, "special-weapons": 34},
    "wingdiverSave": {"short-range": 31, "mid-range-lasers": 19, "mid-range-electro": 20, "particle-cannons": 22, "sniper-weapons": 23, "ranged-attacks": 32, "homing-weapons": 18, "special-weapons": 14},
    "airraiderSave": {"guidance": 11, "calling-support": 50, "support-equip": 32, "limpet-guns": 31, "stationary": 34, "special-weapons": 24, "tanks": 24, "ground-vehicles": 23, "helicopters": 15, "power-suits": 33},
    "fencerSave": {"cc-strikers": 24, "cc-piercers": 26, "shields": 23, "automatic-artillery": 32, "artillery": 35, "missile-launchers": 23},
}
# The games' own save files (PC, Steam), as js/savefile.js reads them. This is written out a second
# time here on purpose: the sample saves below are built from THIS description, and the keys of
# EDF 5 and 6 are worked out from the recipe, so a mistake in savefile.js cannot hide by being
# copied into its own test. Each layout was checked against real saves of that game.
def _md5_utf16(text: str) -> bytes:
    return hashlib.md5(text.encode("utf-16-le")).digest()


SAVE_LAYOUT = {
    "edf41": {"size": 16504, "format": 1, "body": 0x18, "table": 0x2078, "row": 4, "sum": "crc32",
              "key": bytes.fromhex("DBD394C9E09C52CE77467D6A9F913C81"), "counter": bytes.fromhex("F5A9402744EE8C270B2E6D97A9C430CA")},
    "edf5": {"size": 56584, "format": 3, "body": 0x20, "table": 0x7D08, "row": 12, "sum": "crc32c-inverted",
             "key": _md5_utf16("edf5MAIN.GST.sav") + b"Edf5.*_Steam_Ver", "counter": _md5_utf16("edf5MAIN.GST.stm")},
    "edf6": {"size": 56572, "format": 3, "body": 0x14, "table": 0x7CFC, "row": 12, "sum": "crc32c-inverted",
             "key": _md5_utf16("edf6MAIN.GST.sav") + b"Edf5.*_Steam_Ver", "counter": _md5_utf16("edf6MAIN.GST.stm")},
}


def _crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x82F63B78 if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


def save_plaintext(game: str, conds: dict, fmt=None, fix_sum: bool = True, stars=None) -> bytes:
    """A decoded save: header, zeroes, and a weapon table whose entry `row` starts with the number conds[row].
    stars[row] is that entry's eight star bytes (EDF 5 and 6)."""
    lay = SAVE_LAYOUT[game]
    plain = bytearray(lay["size"])
    plain[0:4] = b"MDB0"
    struct.pack_into("<II", plain, 4, lay["format"] if fmt is None else fmt, lay["size"] - lay["body"])
    for row, cond in conds.items():
        struct.pack_into("<I", plain, lay["table"] + row * lay["row"], cond)
    for row, eight in (stars or {}).items():
        plain[lay["table"] + row * lay["row"] + 4: lay["table"] + row * lay["row"] + 12] = bytes(eight)
    body = bytes(plain[lay["body"]:])
    total = zlib.crc32(body) if lay["sum"] == "crc32" else _crc32c(body) ^ 0xFFFFFFFF
    struct.pack_into("<I", plain, 12, (total if fix_sum else total ^ 1) & 0xFFFFFFFF)
    return bytes(plain)


# Encrypts in the browser (AES in counter mode) with the key and counter worked out above.
ENCRYPT = """async ([keyB64, counterB64, dataB64]) => { const b = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
    const key = await crypto.subtle.importKey('raw', b(keyB64), { name: 'AES-CTR' }, false, ['encrypt']);
    const out = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-CTR', counter: b(counterB64), length: 128 }, key, b(dataB64)));
    let s = ''; for (let i = 0; i < out.length; i += 8192) s += String.fromCharCode.apply(null, out.subarray(i, i + 8192)); return btoa(s); }"""


async def save_file(page, folder: Path, name: str, game: str, plain: bytes) -> str:
    lay = SAVE_LAYOUT[game]
    enc = await page.evaluate(ENCRYPT, [base64.b64encode(lay["key"]).decode(), base64.b64encode(lay["counter"]).decode(), base64.b64encode(plain).decode()])
    path = folder / name / "MAIN.GST"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(enc))
    return str(path)


# Moves the HQ text-size slider the way a drag does: set the value, then fire "input".
SET_TEXT = "(v) => { const r = document.querySelector('#textRange'); r.value = String(v); r.dispatchEvent(new Event('input', { bubbles: true })); }"


def check(ok: bool, msg: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + msg)
    if not ok:
        fails.append(msg)


async def watch(page, errors: list, external: list) -> None:
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: external.append(r.url) if not r.url.startswith(BASE) and not r.url.startswith("data:") and not r.url.startswith("blob:") else None)


async def run(browser) -> None:
    errors, external = [], []
    ctx = await browser.new_context(viewport=PHONE, accept_downloads=True)
    pg = await ctx.new_page()
    await watch(pg, errors, external)

    # ---- every game loads its first category
    for game, first, rows in [("edf41", "AF14", 30), ("edf5", "PA-11", 48), ("edf6", "Broken PA-11", 54)]:
        await pg.goto(BASE + game + ".html")
        await pg.wait_for_selector(".row")
        check(await pg.locator(".row").count() == rows, f"{game}: first category has {rows} rows")
        check((await pg.locator(".row__label").first.inner_text()).strip() == first, f"{game}: first weapon is {first}")

    # ---- EDF 6: owning, stars, undo, filters
    await pg.goto(BASE + "edf6.html")
    await pg.wait_for_selector(".row")
    await pg.locator(".box").nth(1).click()
    check(await pg.locator(".box").nth(1).get_attribute("aria-pressed") == "true", "tap box marks owned")
    await pg.reload()
    await pg.wait_for_selector(".row")
    check(await pg.locator(".box").nth(1).get_attribute("aria-pressed") == "true", "owned survives reload")
    await pg.locator(".row__name").nth(2).click()
    await pg.locator('[data-act="inc"]').first.click()
    check(await pg.locator(".row.is-cur .box").get_attribute("aria-pressed") == "true", "adding a star marks the weapon owned")
    drawn = await pg.evaluate("""() => { const s = document.querySelector('.stat__stars'); const r = s.getBoundingClientRect();
        const stars = [...s.querySelectorAll('i')]; const last = stars[stars.length - 1].getBoundingClientRect();
        return { count: stars.length, filled: s.querySelectorAll('i:not(.off)').length, fits: last.right <= r.right + 0.5, w: last.width }; }""")
    check(drawn["count"] == 7 and drawn["filled"] == 1 and drawn["fits"] and drawn["w"] > 5, "stars are drawn, one filled, none cut off")
    # tap a star to set the level directly
    stars = pg.locator(".stat").nth(1).locator(".stat__stars i")
    await stars.nth(4).click()
    check(await pg.locator(".stat").nth(1).locator(".stat__stars i:not(.off)").count() == 5, "tapping the 5th star sets 5 stars")
    await stars.nth(4).click()
    check(await pg.locator(".stat").nth(1).locator(".stat__stars i:not(.off)").count() == 4, "tapping the last lit star turns it off")
    await stars.nth(0).click()
    await stars.nth(0).click()
    check(await pg.locator(".stat").nth(1).locator(".stat__stars i:not(.off)").count() == 0, "stars can be tapped down to zero")
    await pg.locator('[data-act="max"]').click()
    check(await pg.locator(".row.is-cur .row__title .ico--star").count() == 1, "Max shows the gold star on the row")
    check((await pg.locator(".pill").nth(1).inner_text()).strip().endswith("1"), "title shows 1 fully upgraded")
    check(await pg.locator('[data-act="inc"]').first.is_disabled(), "+ is disabled at the star cap")
    await pg.locator(".row.is-cur .box").click()
    check(await pg.locator(".row.is-cur .row__title .ico--star").count() == 0 and (await pg.locator(".pill").nth(1).inner_text()).strip().endswith("0"), "an unchecked weapon no longer counts as fully upgraded")
    await pg.locator(".row.is-cur .box").click()
    check(await pg.locator(".row.is-cur .row__title .ico--star").count() == 1, "checking it again brings its stars back")
    await pg.locator('[data-act="clear"]').click()
    check(await pg.locator(".row.is-cur .row__title .ico--star").count() == 0, "Clear removes the stars")
    await pg.locator("#toastundo").click()
    check(await pg.locator(".row.is-cur .row__title .ico--star").count() == 1, "Undo restores the stars")
    await pg.locator('[data-act="filter"][data-i="1"]').click()
    check(await pg.locator(".row").count() == 52, "Missing filter hides the 2 owned weapons")
    await pg.locator('[data-act="filter"][data-i="2"]').click()
    check(await pg.locator(".row").count() == 1, "To upgrade filter shows the 1 owned weapon with stars left")
    check((await pg.locator('[data-act="filter"][data-i="2"]').inner_text()).strip() == "To upgrade", "third filter is labelled To upgrade")
    await pg.locator('[data-act="filter"][data-i="0"]').click()

    # ---- where a weapon drops
    data6 = json.loads((ROOT / "data" / "edf6.json").read_text(encoding="utf-8"))
    await pg.locator(".row__name").nth(2).click()
    await pg.locator('[data-act="view"][data-i="1"]').click()
    level = int(await pg.locator(".row.is-cur .row__lv").inner_text())
    low, high = data6["drops"][0]["diffs"][0]  # Offline, Easy
    first = next(k for k, v in enumerate(high) if v >= level) + 1
    last = max(k for k, v in enumerate(low) if v <= level) + 1
    shown = await pg.locator(".drops__mode").first.inner_text()
    check("Offline" in shown and f"Easy {first}–{last}" in shown.replace("\n", " "), f"drop missions match the data (Offline Easy {first}–{last})")
    check(await pg.locator('[data-act="max"]').count() == 0, "Max and Clear are hidden on the Drops view")
    await pg.locator(".row__name").nth(0).click()
    check("You start with this weapon" in await pg.locator("#detail").inner_text(), "starter weapons say they do not drop")
    await pg.fill("#q", "Slugger NN5")
    await pg.locator(".row__name").first.click()
    modes = await pg.locator(".drops__name").all_inner_texts()
    check(modes == ["Mission Pack 1"], f"mission-pack weapons only list their pack {modes}")
    await pg.locator("#qclear").click()
    await pg.locator(".tab").nth(0).click()
    await pg.locator(".picker__item, #catbtn").first.click()
    await pg.locator(".picker__item").nth(0).click()
    await pg.locator('[data-act="view"][data-i="0"]').click()
    check(await pg.locator(".stat").count() > 0, "Upgrades view comes back")

    # ---- search, picker, tabs, select all
    await pg.fill("#q", "raven")
    n = await pg.locator(".row").count()
    check(n > 5 and await pg.locator(".row__sub").count() == n, f"search finds {n} weapons across the game, each labelled")
    await pg.fill("#q", "zzzz")
    check("No weapons match" in await pg.locator(".empty").inner_text(), "search with no match explains what to do")
    await pg.locator("#qclear").click()
    check(await pg.locator(".row").count() == 54, "clearing search returns to the category")
    await pg.locator("#catbtn").click()
    check(await pg.locator(".picker__item").count() == 15, "picker lists the 15 Ranger categories")
    check(not await pg.locator("#listhead").is_visible(), "list header is hidden while the picker is open")
    await pg.keyboard.press("Escape")
    check(await pg.locator(".picker__item").count() == 0, "Escape closes the picker")
    await pg.locator("#catbtn").click()
    await pg.locator(".picker__item").nth(12).click()
    check("Tanks" in await pg.locator("#catname").inner_text(), "picker jumps to Tanks")
    check("Tanks" in (await pg.locator("#catbtn").inner_text()), "category button's name includes the category")
    await pg.locator(".tab").nth(0).click()
    check("Tanks" in await pg.locator("#catname").inner_text(), "tapping the current class tab keeps the category")
    await pg.locator(".tab").nth(2).click()
    check("A.Raider" in await pg.locator('.tab[aria-pressed="true"]').inner_text(), "class tab switches")
    before = await pg.locator('.box[aria-pressed="true"]').count()
    await pg.locator(".allbox").click()
    check(await pg.locator('.box[aria-pressed="true"]').count() == await pg.locator(".row").count(), "header box marks all shown")
    await pg.locator("#toastundo").click()
    check(await pg.locator('.box[aria-pressed="true"]').count() == before, "Undo reverts mark all")
    await pg.locator(".row__name").first.focus()
    await pg.keyboard.press("ArrowDown")
    check(await pg.evaluate("document.activeElement === document.querySelectorAll('.row__name')[1]"), "Down arrow moves to the next weapon")
    await pg.reload()
    await pg.wait_for_selector(".row")
    check("A.Raider" in await pg.locator('.tab[aria-pressed="true"]').inner_text(), "class is remembered after reload")

    # ---- scroll memory: a category reopens where it was left
    await pg.locator(".tab").nth(0).click()
    await pg.evaluate("document.querySelector('#list').scrollTop = 500")
    await pg.locator('[data-act="next"]').click()
    top_next = await pg.evaluate("document.querySelector('#list').scrollTop")
    await pg.locator('[data-act="prev"]').click()
    check(top_next == 0 and await pg.evaluate("document.querySelector('#list').scrollTop") == 500, "category scroll position is remembered")
    await pg.fill("#q", "pa")
    await pg.locator("#qclear").click()
    check(await pg.evaluate("document.querySelector('#list').scrollTop") == 500, "scroll position returns after a search")
    await pg.reload()
    await pg.wait_for_selector(".row")
    check(await pg.evaluate("document.querySelector('#list').scrollTop") == 500, "scroll position survives a reload")
    await pg.evaluate("document.querySelector('#list').scrollTop = 0")

    # ---- tap targets
    await pg.locator(".tab").nth(0).click()
    await pg.locator(".row__name").nth(0).click()
    sizes = await pg.evaluate("""() => { const m = (s) => { const r = document.querySelector(s).getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; };
        return { box: m('.box'), allbox: m('.allbox'), stat: m('.stat__btn'), collapse: m('.collapse'), chip: m('.chip'), clear: m('[data-act=clear]') }; }""")
    small = {k: v for k, v in sizes.items() if v[0] < 44 or v[1] < 42}
    check(not small, f"tap targets are at least 44x42 {small or ''}")

    # ---- progress changed elsewhere must not be overwritten
    pg2 = await ctx.new_page()
    await pg2.goto(BASE + "index.html")
    await pg2.evaluate("localStorage.setItem('edfTracker.edf6', JSON.stringify({owned:['AssultRifle01','aWeapon001','aWeapon002'],stars:{}}))")
    await pg.wait_for_timeout(300)
    await pg.locator(".box").nth(10).click()
    await pg.wait_for_timeout(500)
    saved = json.loads(await pg.evaluate("localStorage.getItem('edfTracker.edf6')"))
    check(len(saved["owned"]) == 4 and "aWeapon002" in saved["owned"], "change from another tab is kept (storage event)")
    await pg.evaluate("localStorage.setItem('edfTracker.edf6', JSON.stringify({owned:['AssultRifle01'],stars:{}}))")
    await pg.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
    await pg.locator(".box").nth(11).click()
    await pg.wait_for_timeout(500)
    saved = json.loads(await pg.evaluate("localStorage.getItem('edfTracker.edf6')"))
    check(len(saved["owned"]) == 2, "page restored by Back button reloads progress first (bfcache)")
    await pg2.close()

    # ---- EDF 4.1 detail toggle
    await pg.goto(BASE + "edf41.html")
    await pg.wait_for_selector(".row")
    await pg.locator(".row__name").nth(3).click()
    await pg.locator('[data-act="ownsel"]').click()
    check(await pg.locator(".row.is-cur .box").get_attribute("aria-pressed") == "true", "EDF 4.1 Owned button works")
    check(not await pg.locator(".drops").is_visible(), "EDF 4.1 drop details start closed on phones")
    await pg.locator('[data-act="collapse"]').click()
    check(await pg.locator(".drops__mode").count() >= 2 and "Offline" in await pg.locator(".drops").inner_text(), "EDF 4.1 shows where the weapon drops")
    await pg.locator('[data-act="collapse"]').click()

    # ---- HQ: counts, export, import, bad files
    await pg.goto(BASE + "index.html")
    await pg.wait_for_timeout(200)
    check("2/1564" in await pg.locator('[data-count="edf6"]').inner_text(), "HQ shows EDF 6 owned count")
    check("1/827" in await pg.locator('[data-count="edf41"]').inner_text(), "HQ shows EDF 4.1 owned count")
    check("Not exported yet" in await pg.locator("#backup").inner_text(), "HQ reminds you that progress was never exported")
    async with pg.expect_download() as dl:
        await pg.click("#export")
    path = await (await dl.value).path()
    exp = json.loads(Path(path).read_text(encoding="utf-8"))
    check(exp["app"] == "edf-unlock-tracker" and len(exp["games"]["edf6"]["owned"]) == 2, "export file has the progress")
    backup = await pg.locator("#backup").inner_text()
    check(backup.startswith("Last export:") and "changed" not in backup, f"HQ shows the last export date ({backup})")
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    await pg.locator(".tab").nth(3).click()   # browsing alone is not a change
    await pg.wait_for_timeout(400)
    await pg.goto(BASE + "index.html")
    check("changed" not in await pg.locator("#backup").inner_text(), "browsing does not count as a change")
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    await pg.locator(".box").nth(0).click()
    await pg.wait_for_timeout(400)
    await pg.locator(".box").nth(0).click()
    await pg.wait_for_timeout(400)
    await pg.goto(BASE + "index.html")
    check("Progress has changed since" in await pg.locator("#backup").inner_text(), "HQ says when progress changed after the last export")
    version = (await pg.locator("#version").inner_text()).strip()
    check(version.startswith("v") and version.count(".") == 2 and exp.get("appVersion") == version[1:], f"version {version} shows on HQ and is written to exports")

    # ---- update notices
    # the count of fully upgraded weapons is made again after an update (an older version may have counted with other star maximums)
    def fully_upgraded(g, stored):
        data = json.loads((ROOT / "data" / f"{g}.json").read_text(encoding="utf-8"))
        return sum(1 for c in data["classes"] for k in c["cats"] for it in k["items"] if len(it) > 4 and it[4] and it[0] in stored["owned"]
                   and all((stored["stars"].get(it[0], []) + [0] * 9)[i] >= m for i, (_, m) in enumerate(it[4])))
    real = {g: fully_upgraded(g, json.loads(await pg.evaluate("(g) => localStorage.getItem('edfTracker.' + g) || '{\"owned\":[],\"stars\":{}}'", g))) for g in ("edf5", "edf6")}
    await pg.evaluate("""() => { ['edf5', 'edf6'].forEach((g) => { const s = JSON.parse(localStorage.getItem('edfTracker.summary.' + g) || '{}');
        s.maxed = 7; localStorage.setItem('edfTracker.summary.' + g, JSON.stringify(s)); });
        localStorage.setItem('edfTracker.seenVersion', '0.9.0'); }""")
    await pg.reload()
    check("Updated to " + version in await pg.locator("#notice").inner_text(), "HQ announces an update once")
    await pg.wait_for_timeout(700)
    recounted = {g: json.loads(await pg.evaluate("(g) => localStorage.getItem('edfTracker.summary.' + g)", g)).get("maxed") for g in ("edf5", "edf6")}
    check(recounted == real, f"after an update HQ counts fully upgraded weapons again {recounted} {real}")
    await pg.reload()
    check(not await pg.locator("#notice").is_visible(), "the update note does not repeat")
    # an update first met on a game page: the game page says so, and HQ still lists what is new, once
    await pg.evaluate("localStorage.setItem('edfTracker.seenVersion', '0.9.0'); localStorage.setItem('edfTracker.newsVersion', '0.9.0')")
    await pg.goto(BASE + "edf6.html")
    await pg.wait_for_selector(".row")
    check("Updated to " + version in await pg.locator("#toast").inner_text(), "game pages announce an update")
    await pg.evaluate("window.dispatchEvent(new Event('edf-update'))")
    check((await pg.locator("#toastundo").inner_text()).strip() == "Reload", "a version installed while the page is open offers Reload")
    await pg.goto(BASE + "index.html")
    said = await pg.locator("#notice").inner_text()
    await pg.reload()
    check("Updated to " + version in said and "New:" in said and not await pg.locator("#notice").is_visible(), "HQ lists what is new once, also when a game page met the update first")
    # someone who has never used the tracker is not told about an update
    cnew = await browser.new_context(viewport=PHONE)
    pnew = await cnew.new_page()
    await pnew.goto(BASE + "index.html")
    await pnew.wait_for_selector("#version")
    await pnew.wait_for_timeout(300)
    check(not await pnew.locator("#notice").is_visible() and await pnew.evaluate("localStorage.getItem('edfTracker.newsVersion')") == version[1:], "a first visit shows no update note")
    await cnew.close()

    # ---- display settings
    await pg.evaluate(SET_TEXT, 130)
    check(await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ts').trim()") == "1.3", "text size 130% applies on HQ")
    check((await pg.locator("#textValue").inner_text()).strip() == "130%" and await pg.locator("#textAuto").get_attribute("aria-pressed") == "false", "the slider shows 130% and Auto is off")
    await pg.locator('#segFx button[data-fx="off"]').click()
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    ts = await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ts').trim()")
    size = await pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.row__title')).fontSize)")
    check(ts == "1.3" and abs(size - 17 * 1.3) < 0.2, "text size carries over to game pages")
    moving = await pg.evaluate("document.getAnimations().filter((a) => a.animationName && a.playState === 'running').length")
    check(moving == 0 and await pg.evaluate("document.documentElement.classList.contains('no-fx')"), "Background effects Off stops every animation")
    await pg.goto(BASE + "index.html")
    await pg.locator('#segFx button[data-fx="on"]').click()
    await pg.evaluate(SET_TEXT, 60)
    small = await pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.card__name')).fontSize)")
    check(await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ts').trim()") == "0.6" and abs(small - 18) < 0.2, "text size goes down to 60%")
    await pg.locator("#textRange").focus()
    await pg.keyboard.press("ArrowRight")
    check((await pg.locator("#textValue").inner_text()).strip() == "65%" and json.loads(await pg.evaluate("localStorage.getItem('edfTracker.prefs')"))["text"] == "0.65", "arrow keys move the slider in 5% steps and the size is saved")
    await pg.reload()
    check(await pg.locator("#textRange").input_value() == "65" and await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ts').trim()") == "0.65", "the chosen text size survives a reload")
    await pg.evaluate("localStorage.setItem('edfTracker.prefs', JSON.stringify({text: '9', fx: 'on'}))")
    await pg.reload()
    check(await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ts').trim()") == "1.5" and await pg.locator("#textRange").input_value() == "150", "an out-of-range saved text size is limited to 150%")
    await pg.locator("#textAuto").click()
    check(await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ts').trim()") == "1", "Auto text size is 100% on a default device")
    check(await pg.locator("#textAuto").get_attribute("aria-pressed") == "true" and await pg.locator("#textRange").input_value() == "100", "Auto is on and the slider shows the size in use")

    # ---- Game pages: Fit screen / Taller lists
    LAYOUT = """() => { const l = document.querySelector('.list').getBoundingClientRect(), n = document.querySelector('nav').getBoundingClientRect(), s = document.querySelector('.stats');
        return { tall: document.documentElement.classList.contains('page-scroll'), listH: Math.round(l.height), statsMax: s ? getComputedStyle(s).maxHeight : '',
                 docH: document.documentElement.scrollHeight, winH: innerHeight, navBottom: Math.round(n.bottom) }; }"""
    check(await pg.locator('#segLayout button[data-layout="fit"]').get_attribute("aria-pressed") == "true", "game pages start on Fit screen")
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    fit = await pg.evaluate(LAYOUT)
    check(not fit["tall"] and fit["docH"] <= fit["winH"], f"Fit screen: the game page does not scroll {fit}")
    await pg.goto(BASE + "index.html")
    await pg.locator('#segLayout button[data-layout="scroll"]').click()
    check(await pg.locator('#segLayout button[data-layout="scroll"]').get_attribute("aria-pressed") == "true" and json.loads(await pg.evaluate("localStorage.getItem('edfTracker.prefs')"))["layout"] == "scroll", "Taller lists can be chosen on HQ and is saved")
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    tall = await pg.evaluate(LAYOUT)
    check(tall["tall"] and abs(tall["listH"] - (PHONE["height"] - 260)) <= 2 and tall["listH"] >= fit["listH"] + 150 and tall["statsMax"] == "none" and tall["docH"] > tall["winH"] and tall["navBottom"] == tall["winH"],
          f"Taller lists: a much taller weapon list, full details, a page that scrolls, and the game bar stays at the bottom {tall}")
    await pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    end = await pg.evaluate("""() => { const d = document.querySelector('.detail').getBoundingClientRect(), n = document.querySelector('nav').getBoundingClientRect(); return { clear: d.bottom <= n.top + 0.5, navBottom: Math.round(n.bottom), winH: innerHeight }; }""")
    check(end["clear"] and end["navBottom"] == end["winH"], f"Taller lists: at the end of the page the details sit clear of the game bar {end}")
    await pg.goto(BASE + "index.html")
    await pg.locator('#segLayout button[data-layout="fit"]').click()
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    back = await pg.evaluate(LAYOUT)
    check(not back["tall"] and back["listH"] == fit["listH"] and back["docH"] <= back["winH"], "switching back to Fit screen restores the one-screen layout")
    await pg.goto(BASE + "index.html")

    # ---- each game's own text: font, size and style
    TYPE = """() => { const cs = getComputedStyle(document.querySelector('.row__title')), root = document.documentElement;
        return { font: cs.fontFamily.split(',')[0].replace(/['"]/g, ''), size: parseFloat(cs.fontSize), ts: root.style.getPropertyValue('--ts'), italic: cs.fontStyle,
                 caps: getComputedStyle(document.querySelector('.row__name')).textTransform, stroke: parseFloat(cs.webkitTextStrokeWidth) || 0,
                 cls: [...root.classList].filter((c) => c.indexOf('type-') === 0).sort(), docW: root.scrollWidth, winW: innerWidth }; }"""
    await pg.locator('#segGame button[data-game="edf5"]').click()
    menu = await pg.evaluate("[...document.querySelector('#typeFont').options].map((o) => o.value)")
    check(menu[0] == "default" and len(menu) == 11 and len(set(menu)) == 11 and (await pg.locator("#lblGameText").inner_text()).strip().upper() == "EDF 5 TEXT" and await pg.locator("#typeSame").get_attribute("aria-pressed") == "true",
          f"HQ offers the game's own font plus ten others, and starts on the same size as everywhere else {menu}")
    await pg.select_option("#typeFont", "orbitron")
    await pg.evaluate("(v) => { const r = document.querySelector('#typeRange'); r.value = String(v); r.dispatchEvent(new Event('input', { bubbles: true })); }", 80)
    await pg.locator('#segTypeStyle button[data-style="bold"]').click()
    await pg.locator('#segTypeStyle button[data-style="italic"]').click()
    await pg.locator('#segTypeStyle button[data-style="caps"]').click()
    saved = json.loads(await pg.evaluate("localStorage.getItem('edfTracker.prefs')"))["type"]
    sample = await pg.evaluate("(() => { const s = getComputedStyle(document.querySelector('#typePreview')); return [s.fontFamily.split(',')[0].replace(/['\"]/g, ''), Math.round(parseFloat(s.fontSize) * 10) / 10, s.fontStyle, s.textTransform]; })()")
    check(saved["edf5"] == {"font": "orbitron", "size": "0.8", "bold": True, "italic": True, "caps": True} and saved["edf6"]["font"] == "default" and sample == ["Orbitron", 13.6, "italic", "uppercase"]
          and await pg.evaluate("document.documentElement.style.getPropertyValue('--ts')") == "1" and not await pg.evaluate("[...document.documentElement.classList].some((c) => c.indexOf('type-') === 0)"),
          f"font, size and style are saved for EDF 5 only; the sample line shows them and HQ itself stays as it was {sample}")
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    await pg.evaluate("document.fonts.ready")
    t5 = await pg.evaluate(TYPE)
    check(t5["font"] == "Orbitron" and t5["ts"] == "0.8" and abs(t5["size"] - 17 * 0.8) < 0.2 and t5["italic"] == "italic" and t5["caps"] == "uppercase" and t5["stroke"] > 0 and t5["cls"] == ["type-bold", "type-caps", "type-italic"]
          and t5["docW"] <= t5["winW"] and await pg.evaluate("document.fonts.check('500 14px Orbitron') && document.fonts.check('700 14px Orbitron')"), f"the EDF 5 page uses its own font, size and style, and the font files load {t5}")
    await pg.goto(BASE + "edf6.html")
    await pg.wait_for_selector(".row")
    t6 = await pg.evaluate(TYPE)
    check(t6["font"] == "Share Tech Mono" and t6["ts"] == "1" and t6["cls"] == [] and t6["caps"] == "none" and t6["italic"] == "normal", f"the other games keep their own look {t6}")
    await pg.goto(BASE + "index.html")
    await pg.locator('#segGame button[data-game="edf5"]').click()
    check(await pg.locator("#typeFont").input_value() == "orbitron" and await pg.locator("#typeRange").input_value() == "80" and await pg.locator('#segTypeStyle button[aria-pressed="true"]').count() == 3, "HQ shows the saved text settings again")
    await pg.evaluate(SET_TEXT, 110)
    kept = json.loads(await pg.evaluate("localStorage.getItem('edfTracker.prefs')"))
    check(kept["text"] == "1.1" and kept["type"]["edf5"] == {"font": "orbitron", "size": "0.8", "bold": True, "italic": True, "caps": True} and await pg.locator("#typeRange").input_value() == "80",
          "changing the Text size for all pages leaves a game's own text settings alone")
    await pg.locator("#typeSame").click()
    await pg.select_option("#typeFont", "default")
    for style in ("bold", "italic", "caps"):
        await pg.locator(f'#segTypeStyle button[data-style="{style}"]').click()
    await pg.evaluate(SET_TEXT, 120)
    check((await pg.locator("#typeValue").inner_text()).strip() == "120%" and await pg.locator("#typeRange").input_value() == "120" and json.loads(await pg.evaluate("localStorage.getItem('edfTracker.prefs')"))["type"]["edf5"] == {"font": "default", "size": "same", "bold": False, "italic": False, "caps": False},
          "Same follows the Text size for all pages, and every text setting can be put back")
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    t5 = await pg.evaluate(TYPE)
    check(t5["font"] == "Rajdhani" and t5["ts"] == "1.2" and t5["cls"] == [], f"back on the game's own font, at the size set for all pages {t5}")
    # ---- upgrades are listed in the order of the game's equipment screen, under the game's names
    listed = {}
    # (the lines as the games show them; a line without buttons is marked with what it says instead)
    LINES = "[...document.querySelectorAll('#detail .stat, #detail .statline')].map((r) => r.querySelector('.stat__label').textContent.trim() + (r.classList.contains('stat') ? '' : ' [' + r.querySelector('.statline__note').textContent.trim() + ']'))"
    for g, name, expect in (("edf6", "Lightning Bow", ["Capacity", "ROF", "Damage", "Shot Speed", "Range [☆0 · same as Shot Speed]", "Energy Cost", "Charge Time"]),
                            ("edf5", "Vibro Hammer", ["Regular Attack [In game: ☆0]", "Damage", "Range", "Maximum [In game: ☆0 · set above]", "Charge Speed", "Capacity", "Reload"]),
                            ("edf5", "ME1 Emerald", ["Capacity", "ROF", "Damage", "Reload Time", "Blast Area", "Lock-on [In game: ☆0]", "Range", "Capacity [☆0 · set above]", "Lock-on Time"]),
                            ("edf5", "Spark Vine Y3", ["Capacity", "Damage [In game: ☆0]", "Damage", "Count", "Range", "Energy Cost", "Charge Time"]),
                            ("edf5", "PA-11", ["Capacity", "ROF", "Damage", "Reload Time", "Range", "Shot Speed [☆0 · same as Range]", "Accuracy"])):
        await pg.goto(BASE + g + ".html")
        await pg.wait_for_selector(".row")
        await pg.fill("#q", name)
        await pg.locator(".row__name").first.click()
        listed[name] = await pg.evaluate(LINES)
        if name == "Spark Vine Y3":  # the game prints one star for Damage and Count: their average, with "+" for a half
            said = []
            for dmg, cnt in ((3, 5), (4, 5), (8, 5)):
                await pg.evaluate("""(a) => { const rows = [...document.querySelectorAll('#detail .stat--part')];
                    rows[0].querySelectorAll('.stat__stars i')[a[0] - 1].click(); }""", [dmg, cnt])
                await pg.evaluate("""(a) => { const rows = [...document.querySelectorAll('#detail .stat--part')]; const on = rows[1].querySelectorAll('.stat__stars i:not(.off)').length;
                    if (on !== a[1]) rows[1].querySelectorAll('.stat__stars i')[a[1] - 1].click(); }""", [dmg, cnt])
                said.append((await pg.locator("#detail .statline__note").first.inner_text()).strip())
            check(said == ["In game: ☆4", "In game: ☆4+", "In game: ★6+"], f"a line with two values shows the star the game prints for it {said}")
            await pg.locator('[data-act="clear"]').click()
            await pg.locator('.row.is-cur .box').click()
            await pg.wait_for_timeout(400)
        check(listed[name] == expect, f"{name}: upgrades are listed as on the game's equipment screen {listed[name]}")
    tapped = await pg.evaluate("""() => { const rows = [...document.querySelectorAll('.stat')]; const reload = rows.find((r) => r.querySelector('.stat__label').textContent === 'Reload Time');
        reload.querySelector('[data-act=inc]').click(); return +reload.querySelector('[data-act=inc]').dataset.i; }""")
    await pg.wait_for_timeout(400)
    pa11 = json.loads(await pg.evaluate("localStorage.getItem('edfTracker.edf5')"))["stars"].get("AssultRifle01")
    pa11_data = [it for c in json.loads((ROOT / "data" / "edf5.json").read_text(encoding="utf-8"))["classes"] for k in c["cats"] for it in k["items"] if it[0] == "AssultRifle01"][0]
    reload_at = [json.loads((ROOT / "data" / "edf5.json").read_text(encoding="utf-8"))["stats"][s] for s, _ in pa11_data[4]].index("Reload Time")
    check(tapped == reload_at and pa11 == [1 if i == reload_at else 0 for i in range(len(pa11_data[4]))], f"a tap in the reordered list changes the stat it is on (Reload Time is upgrade {reload_at} in the data) {pa11}")
    # changing one stat writes the other stats back as they were saved, even a value above what the data allows
    other = 0 if reload_at else 1
    await pg.goto(BASE + "index.html")  # leave the game page first: it saves what it has when it is left
    await pg.evaluate("(a) => { const p = JSON.parse(localStorage.getItem('edfTracker.edf5')); p.stars.AssultRifle01[a] = 10; p.stars.AssultRifle01.push(3, 2); localStorage.setItem('edfTracker.edf5', JSON.stringify(p)); }", other)
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    await pg.fill("#q", "PA-11")
    await pg.locator(".row__name").first.click()
    shown_other = await pg.evaluate("(i) => document.querySelector('.stat [data-act=inc][data-i=\"' + i + '\"]').disabled", other)
    await pg.evaluate("(i) => document.querySelector('.stat [data-act=inc][data-i=\"' + i + '\"]').click()", reload_at)
    await pg.wait_for_timeout(400)
    pa11 = json.loads(await pg.evaluate("localStorage.getItem('edfTracker.edf5')"))["stars"].get("AssultRifle01")
    check(shown_other and pa11_data[4][other][1] < 10 and pa11 == [10 if i == other else 2 if i == reload_at else 0 for i in range(len(pa11_data[4]))] + [3, 2],
          f"changing one stat leaves the saved values of the others alone, also stars saved for upgrades this weapon list does not have {pa11}")
    await pg.locator('[data-act="max"]').click()
    await pg.wait_for_timeout(400)
    pa11 = json.loads(await pg.evaluate("localStorage.getItem('edfTracker.edf5')"))["stars"].get("AssultRifle01")
    check(pa11 == [m for _, m in pa11_data[4]] + [3, 2], f"Max fills the upgrades it knows and keeps the rest {pa11}")
    await pg.locator('[data-act="clear"]').click()
    await pg.locator('.row.is-cur .box').click()
    await pg.wait_for_timeout(400)
    await pg.goto(BASE + "index.html")
    await pg.locator("#textAuto").click()
    # damaged or hand-edited settings never stop a page from loading; a game's own large size also gets the scrolling layout
    cbad = await browser.new_context(viewport=PHONE)
    pbad = await cbad.new_page()
    await watch(pbad, errors, external)
    await pbad.add_init_script("""localStorage.setItem('edfTracker.prefs', JSON.stringify({ text: '1', type: { edf5: 'x', edf6: { font: 5, size: 'huge', bold: 'yes', caps: 1 }, edf41: { font: '__proto__', size: '1.4', italic: true }, edf9: { font: 'orbitron' } } }))""")
    odd = {}
    for g in ("edf5", "edf6", "edf41"):
        await pbad.goto(BASE + g + ".html")
        await pbad.wait_for_selector(".row")
        odd[g] = await pbad.evaluate(TYPE)
        odd[g]["big"] = await pbad.evaluate("document.documentElement.classList.contains('big-text')")
    check(odd["edf5"]["font"] == "Rajdhani" and odd["edf5"]["cls"] == [] and odd["edf6"]["font"] == "Share Tech Mono" and odd["edf6"]["ts"] == "1" and odd["edf6"]["cls"] == []
          and odd["edf41"]["font"] == "Saira Condensed" and odd["edf41"]["ts"] == "1.4" and odd["edf41"]["cls"] == ["type-italic"] and odd["edf41"]["big"] and not odd["edf5"]["big"],
          f"damaged text settings fall back safely, and a game's own size of 130% or more switches that game to the scrolling layout {odd}")
    await pbad.goto(BASE + "index.html")
    await pbad.locator('#segGame button[data-game="edf6"]').click()
    check(await pbad.locator("#typeFont").input_value() == "default" and await pbad.locator('#segTypeStyle button[aria-pressed="true"]').count() == 0 and await pbad.locator("#typeSame").get_attribute("aria-pressed") == "true", "HQ shows damaged text settings as the defaults")
    await cbad.close()

    # ---- profiles: eight per game (4 PC + 4 console save slots), each game with its own
    SLOT_STATE = """(g) => ({ pressed: [...document.querySelectorAll('#segProfile .slot[aria-pressed=true]')].map((b) => b.dataset.slot),
        game: [...document.querySelectorAll('#segGame button[aria-pressed=true]')].map((b) => b.dataset.game),
        names: Object.fromEntries([...document.querySelectorAll('#segProfile .slot')].map((b) => [b.dataset.slot, b.querySelector('.slot__name').textContent])),
        counts: Object.fromEntries([...document.querySelectorAll('#segProfile .slot')].map((b) => [b.dataset.slot, b.querySelector('.slot__count').textContent])),
        tag: document.querySelector('[data-slotname="' + g + '"]').hidden ? null : document.querySelector('[data-slotname="' + g + '"]').textContent,
        now: document.querySelector('#slotNow').textContent })"""
    p1_count = await pg.locator('[data-count="edf6"]').inner_text()
    count41 = await pg.locator('[data-count="edf41"]').inner_text()
    await pg.locator('#segGame button[data-game="edf6"]').click()
    st = await pg.evaluate(SLOT_STATE, "edf6")
    check(list(st["names"].values()) == ["PC 1", "PC 2", "PC 3", "PC 4", "Console 1", "Console 2", "Console 3", "Console 4"] and st["pressed"] == ["pc1"] and st["tag"] is None,
          "HQ lists 4 PC and 4 console profiles per game; PC 1 is in use and the card shows no profile name yet")
    check(st["counts"]["pc1"] == "2/1564" and st["counts"]["con2"] == "Empty", f"each profile shows its own progress {st['counts']}")
    await pg.locator('#segProfile .slot[data-slot="con2"]').click()
    check("0/1564" in await pg.locator('[data-count="edf6"]').inner_text(), "a profile that was never used starts empty")
    check(await pg.locator('[data-count="edf41"]').inner_text() == count41, "switching EDF 6's profile leaves the other games alone")
    pg.once("dialog", lambda d: asyncio.ensure_future(d.accept("  Console <b>  ")))
    await pg.locator("#renameProfile").click()
    st = await pg.evaluate(SLOT_STATE, "edf6")
    check(st["names"]["con2"] == "Console <b>" and st["tag"] == "Console <b>" and st["pressed"] == ["con2"] and "Console <b>" in st["now"], "a profile can be renamed (shown as plain text) and the game card names it")
    await pg.locator('#segGame button[data-game="edf5"]').click()
    st5 = await pg.evaluate(SLOT_STATE, "edf5")
    check(st5["pressed"] == ["pc1"] and st5["names"]["con2"] == "Console 2" and st5["tag"] is None, "EDF 5 has its own eight profiles and names")
    await pg.goto(BASE + "edf6.html")
    await pg.wait_for_selector(".row")
    check((await pg.locator(".pill--profile").inner_text()).strip() == "Console <b>", "game pages show which profile is in use")
    await pg.locator(".box").nth(7).click()
    await pg.wait_for_timeout(400)
    both = await pg.evaluate("[JSON.parse(localStorage.getItem('edfTracker.con2.edf6')).owned.length, JSON.parse(localStorage.getItem('edfTracker.edf6')).owned.length]")
    check(both == [1, 2], f"Console 2 saves separately from PC 1 {both}")
    await pg.goto(BASE + "edf5.html")
    await pg.wait_for_selector(".row")
    check(await pg.locator(".pill--profile").count() == 0, "a game that only uses PC 1 shows no profile name")
    await pg.goto(BASE + "index.html")
    st = await pg.evaluate(SLOT_STATE, "edf6")
    check("1/1564" in await pg.locator('[data-count="edf6"]').inner_text() and st["game"] == ["edf5"] and st["tag"] == "Console <b>", "HQ shows the progress of each game's profile in use and remembers which game's profiles were listed")
    await pg.locator('#segGame button[data-game="edf6"]').click()
    st = await pg.evaluate(SLOT_STATE, "edf6")
    check(st["counts"]["con2"] == "1/1564" and st["counts"]["pc1"] == "2/1564", f"the profile list shows both EDF 6 profiles' progress {st['counts']}")
    async with pg.expect_download() as dl2:
        await pg.click("#export")
    path2 = await (await dl2.value).path()
    exp2 = json.loads(Path(path2).read_text(encoding="utf-8"))
    check(len(exp2["slots"]["edf6"]["con2"]["owned"]) == 1 and len(exp2["games"]["edf6"]["owned"]) == 2 and exp2["slotNames"]["edf6"]["con2"] == "Console <b>"
          and sorted(exp2["slots"]["edf5"]) == ["con2", "con3", "con4", "pc2", "pc3", "pc4"] and "edf6" in exp2["profile2"]["games"], "export holds all 24 profiles and their names")
    await pg.locator('#segProfile .slot[data-slot="pc1"]').click()
    check(await pg.locator('[data-count="edf6"]').inner_text() == p1_count, "switching back to PC 1 restores its progress")
    c7 = await browser.new_context(viewport=PHONE)
    p7 = await c7.new_page()
    p7.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await p7.goto(BASE + "index.html")
    await p7.set_input_files("#importfile", path2)
    await p7.wait_for_timeout(400)
    restored = await p7.evaluate("[JSON.parse(localStorage.getItem('edfTracker.con2.edf6')).owned.length, JSON.parse(localStorage.getItem('edfTracker.edf6')).owned.length]")
    await p7.locator('#segGame button[data-game="edf6"]').click()
    st7 = await p7.evaluate(SLOT_STATE, "edf6")
    check(restored == [1, 2] and st7["names"]["con2"] == "Console <b>" and st7["counts"]["con2"] == "1/1564" and st7["pressed"] == ["pc1"] and st7["tag"] == "PC 1",
          f"import restores every profile and its name on another device {st7['counts']}")
    # a file exported by v1.3-v1.4 (two profiles shared by all games) still imports: profile 1 -> PC 1, profile 2 -> Console 1
    old_file = {"app": "edf-unlock-tracker", "version": 1, "appVersion": "1.4.1", "games": {"edf5": {"owned": ["AssultRifle01"], "stars": {}}},
                "profile2": {"games": {"edf5": {"owned": ["AssultRifle01", "aWeapon001", "aWeapon002"], "stars": {}}}}, "profileNames": {"1": "Steam", "2": "Profile 2"}}
    old_path = Path(tempfile.mkdtemp()) / "v14.json"
    old_path.write_text(json.dumps(old_file), encoding="utf-8")
    await c7.close()
    c7 = await browser.new_context(viewport=PHONE)  # a browser that has never held any progress
    p7 = await c7.new_page()
    p7.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await p7.goto(BASE + "index.html")
    await p7.set_input_files("#importfile", str(old_path))
    await p7.wait_for_timeout(400)
    await p7.locator('#segGame button[data-game="edf5"]').click()
    st7 = await p7.evaluate(SLOT_STATE, "edf5")
    check("(2 profiles)" in await p7.locator("#notice").inner_text() and st7["names"]["pc1"] == "Steam" and st7["names"]["con1"] == "Console 1" and st7["counts"]["con1"] == "3/1187" and st7["counts"]["pc1"] == "1/1187" and st7["tag"] == "Steam",
          f"a v1.4 export imports into a fresh browser as PC 1 and Console 1 {st7['counts']}")
    # the names v1.3-v1.4 scripts pass ('1' and '2') reach PC 1 and Console 1 until a profile is chosen here, then follow it
    keys = await p7.evaluate("""async () => { const s = await import('./js/store.js'); const out = [s.progressKey('edf5', '1'), s.progressKey('edf5', '2'), s.progressKey('edf5')];
        s.setActiveSlot('edf5', 'pc3'); out.push(s.progressKey('edf5', '1'), s.progressKey('edf5', '2'), s.progressKey('edf5'), s.progressKey('edf5', 'con4'), s.progressKey('edf6', '2'));
        s.setActiveSlot('edf5', 'pc1'); return out; }""")
    check(keys == ["edfTracker.edf5", "edfTracker.p2.edf5", "edfTracker.edf5", "edfTracker.pc3.edf5", "edfTracker.pc3.edf5", "edfTracker.pc3.edf5", "edfTracker.con4.edf5", "edfTracker.p2.edf6"],
          f"a page still running the previous scripts saves into the profile HQ shows as in use {keys}")
    await c7.close()
    # a browser that used v1.4 with profile 2 selected and renamed: after updating, Console 1 is in use with that name and progress
    c10 = await browser.new_context(viewport=PHONE)
    p10 = await c10.new_page()
    await p10.add_init_script("""if (!localStorage.getItem('edfTracker.seeded')) { localStorage.setItem('edfTracker.seeded', '1');
        localStorage.setItem('edfTracker.profile', '2'); localStorage.setItem('edfTracker.p2used', '1');
        localStorage.setItem('edfTracker.profileNames', JSON.stringify({ 1: 'Storm', 2: 'Deck' }));
        localStorage.setItem('edfTracker.edf5', JSON.stringify({ owned: ['AssultRifle01'], stars: {} }));
        localStorage.setItem('edfTracker.p2.edf5', JSON.stringify({ owned: ['AssultRifle01', 'aWeapon001'], stars: {} })); }""")
    await p10.goto(BASE + "index.html")
    await p10.locator('#segGame button[data-game="edf5"]').click()
    st10 = await p10.evaluate(SLOT_STATE, "edf5")
    check(st10["pressed"] == ["con1"] and st10["names"]["pc1"] == "Storm" and st10["names"]["con1"] == "Deck" and st10["counts"]["con1"] == "2/1187" and st10["tag"] == "Deck" and "2/1187" in await p10.locator('[data-count="edf5"]').inner_text(),
          f"the two profiles of v1.4 become PC 1 and Console 1, with their names, progress and selection {st10['pressed']} {st10['counts']}")
    await p10.goto(BASE + "edf5.html")
    await p10.wait_for_selector(".row")
    check((await p10.locator(".pill--profile").inner_text()).strip() == "Deck" and await p10.locator('.box[aria-pressed="true"]').count() == 2, "the game page opens that profile after the update")
    await p10.goto(BASE + "index.html")
    await p10.locator('#segGame button[data-game="edf5"]').click()
    p10.once("dialog", lambda d: asyncio.ensure_future(d.accept("")))
    await p10.locator("#renameProfile").click()
    check((await p10.evaluate(SLOT_STATE, "edf5"))["names"]["con1"] == "Console 1", "clearing a name puts the default name back")
    await c10.close()
    # a game page that fell behind (phone tab asleep): elsewhere its profile got newer progress and the game was
    # switched to another profile. It must move to the new profile without writing its old copy over the newer data.
    c11 = await browser.new_context(viewport=PHONE)
    p11 = await c11.new_page()
    await p11.goto(BASE + "edf5.html")
    await p11.wait_for_selector(".row")
    await p11.locator(".box").nth(0).click()
    await p11.wait_for_timeout(500)
    newer = json.dumps({"owned": ["AssultRifle01", "aWeapon001", "aWeapon002"], "stars": {}}, separators=(",", ":"))
    await p11.evaluate("""(newer) => { localStorage.setItem('edfTracker.edf5', newer); localStorage.setItem('edfTracker.slot.edf5', 'pc2'); window.__stale = true;
        window.dispatchEvent(new StorageEvent('storage', { key: 'edfTracker.edf5', newValue: newer })); }""", newer)
    await p11.wait_for_function("!window.__stale && document.querySelector('.row')")
    await p11.wait_for_timeout(400)
    after = await p11.evaluate("({ pc1: localStorage.getItem('edfTracker.edf5'), pc2: localStorage.getItem('edfTracker.pc2.edf5'), marked: document.querySelectorAll('.box[aria-pressed=true]').length, pill: (document.querySelector('.pill--profile') || {}).textContent })")
    check(after["pc1"] == newer and after["marked"] == 0 and after["pill"] == "PC 2" and (after["pc2"] is None or json.loads(after["pc2"])["owned"] == []),
          f"a profile switched elsewhere reloads the game page onto it and keeps the other profile's newer progress {after['marked']} {after['pill']!r}")
    await p11.locator(".box").nth(3).click()   # a change made here in the last 250 ms is still written, to the profile this page was showing
    await p11.evaluate("""() => { localStorage.setItem('edfTracker.slot.edf5', 'pc1'); window.__stale = true; window.dispatchEvent(new StorageEvent('storage', { key: 'edfTracker.slot.edf5', newValue: 'pc1' })); }""")
    await p11.wait_for_function("!window.__stale && document.querySelector('.row')")
    last = await p11.evaluate("({ pc2: JSON.parse(localStorage.getItem('edfTracker.pc2.edf5') || '{}').owned || [], pc1: localStorage.getItem('edfTracker.edf5'), marked: document.querySelectorAll('.box[aria-pressed=true]').length })")
    check(len(last["pc2"]) == 1 and last["pc1"] == newer and last["marked"] == 3, f"an unsaved tick is written to its own profile before the page switches {last['pc2']} {last['marked']}")
    await c11.close()

    ctx2 = await browser.new_context(viewport=PHONE)
    p2 = await ctx2.new_page()
    await watch(p2, errors, external)
    p2.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await p2.goto(BASE + "index.html")
    await p2.set_input_files("#importfile", path)
    await p2.wait_for_timeout(400)
    check("2/1564" in await p2.locator('[data-count="edf6"]').inner_text(), "import restores progress in a fresh browser")
    tmp = Path(tempfile.mkdtemp())
    (tmp / "legacy.json").write_text(json.dumps({"version": 1, "data": {"rangerSave": {"assault-rifles": [0, 1, 2], "special-weapons": [0]}, "fencerSave": {"missile-launchers": [0, 1]}}}), encoding="utf-8")
    await p2.set_input_files("#importfile", str(tmp / "legacy.json"))
    await p2.wait_for_timeout(400)
    check("Imported 10" in await p2.locator("#notice").inner_text(), "old EDF 4.1 export imports (3 rifles + 5 decoys + 2 missiles)")
    (tmp / "bad.json").write_text("not json", encoding="utf-8")
    await p2.set_input_files("#importfile", str(tmp / "bad.json"))
    await p2.wait_for_timeout(300)
    check("not valid JSON" in await p2.locator("#notice").inner_text(), "broken file gives a clear message")
    evil = {"app": "edf-unlock-tracker", "version": 1, "games": {"edf6": {"owned": ["AssultRifle01", 5, {"x": 1}, "<img src=x onerror=alert(1)>"], "stars": {"AssultRifle01": [99, -3, "x"], "__proto__": [1], "bad": "str"}}},
            "slots": {"edf6": {"pc2": {"owned": ["aWeapon001", 7, None], "stars": "no"}, "pc9": {"owned": ["aWeapon002"]}, "con3": "text", "__proto__": {"owned": ["x"]}}, "edf9": {"pc2": {"owned": ["x"]}}, "__proto__": {"pc2": {"owned": ["x"]}}},
            "slotNames": {"edf6": {"pc2": "<img src=x onerror=alert(2)> and a very long name", "pc9": "nope", "con3": 5, "__proto__": "x"}, "edf9": {"pc1": "nope"}, "__proto__": {"pc1": "x"}}}
    (tmp / "evil.json").write_text(json.dumps(evil), encoding="utf-8")
    await p2.set_input_files("#importfile", str(tmp / "evil.json"))
    await p2.wait_for_timeout(300)
    await p2.locator('#segGame button[data-game="edf6"]').click()
    hostile = await p2.evaluate("""() => ({ keys: Object.keys(localStorage).filter((k) => /pc9|edf9|proto/.test(k)), pc2: JSON.parse(localStorage.getItem('edfTracker.pc2.edf6')), con3: JSON.parse(localStorage.getItem('edfTracker.con3.edf6')),
        name: document.querySelector('#segProfile .slot[data-slot=pc2] .slot__name').textContent, names: JSON.parse(localStorage.getItem('edfTracker.slotNames')),
        polluted: ({}).owned !== undefined || ({}).pc1 !== undefined, imgs: document.querySelectorAll('img').length })""")
    n6 = hostile["names"]["edf6"]
    check(hostile["keys"] == [] and hostile["pc2"] == {"owned": ["aWeapon001"], "stars": {}} and hostile["con3"] == {"owned": [], "stars": {}} and hostile["name"] == "<img src=x onerr" == n6["pc2"]
          and n6["con3"] == "Console 3" and "pc9" not in n6 and sorted(hostile["names"]) == ["edf41", "edf5", "edf6"] and not hostile["polluted"] and hostile["imgs"] == 0,
          f"profiles and names in an import are cleaned: unknown games and slots are ignored, names are cut to 16 characters and shown as text {hostile['keys']} {hostile['name']!r}")
    await p2.goto(BASE + "edf6.html")
    await p2.wait_for_selector(".row")
    stored = json.loads(await p2.evaluate("localStorage.getItem('edfTracker.edf6')"))
    await p2.locator(".box").nth(5).click()
    await p2.wait_for_timeout(500)
    stored = json.loads(await p2.evaluate("localStorage.getItem('edfTracker.edf6')"))
    check(sorted(stored["owned"]) == ["AssultRifle01", stored["owned"][-1]] or len(stored["owned"]) == 2, "malformed import is cleaned (unknown ids dropped)")
    check(stored["stars"].get("AssultRifle01", [0])[0] <= 10 and "bad" not in stored["stars"], "imported stars are clamped")
    check(await p2.locator("img").count() == 0, "imported text is never treated as HTML")

    # ---- old checklist found on this device
    ctx3 = await browser.new_context(viewport=PHONE)
    p3 = await ctx3.new_page()
    await p3.goto(BASE + "edf41.html")
    await p3.evaluate("localStorage.setItem('wingdiverSave', JSON.stringify({'short-range':[0,1,2,3]}))")
    await p3.reload()
    await p3.wait_for_selector(".row")
    check(await p3.locator("#banner").is_visible(), "EDF 4.1 page offers to import the old checklist")
    await p3.locator('[data-act="legacy-import"]').click()
    await p3.wait_for_timeout(400)
    await p3.locator(".tab").nth(1).click()
    check(await p3.locator('.box[aria-pressed="true"]').count() == 4, "old checklist import marks the 4 weapons")

    # ---- the lookup file uses the old site's real category names, and a complete checklist imports in full
    legacy_map = json.loads((ROOT / "data" / "edf41-legacy.json").read_text(encoding="utf-8"))
    shape = {key: {cat: len(slots) for cat, slots in cats.items()} for key, cats in legacy_map.items()}
    check(shape == OLD_CHECKLIST, "edf41-legacy.json has the old checklist's own category names and sizes")
    full = {key: {cat: list(range(n)) for cat, n in cats.items()} for key, cats in OLD_CHECKLIST.items()}
    ticks = sum(n for cats in OLD_CHECKLIST.values() for n in cats.values())
    export = {"version": 1, "exportedAt": "2026-01-01T00:00:00.000Z", "data": {}}  # the old site's export file
    for key, cats in full.items():
        export["data"][key] = cats
        export["data"][key + "_count"] = str(sum(len(v) for v in cats.values()))
        export["data"][key + "_total"] = str(sum(len(v) for v in cats.values()))
    (tmp / "old-full.json").write_text(json.dumps(export, indent=2), encoding="utf-8")
    c8 = await browser.new_context(viewport=PHONE)
    p8 = await c8.new_page()
    p8.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await p8.goto(BASE + "index.html")
    await p8.set_input_files("#importfile", str(tmp / "old-full.json"))
    await p8.wait_for_timeout(500)
    check(ticks == 812 and "Imported 820" in await p8.locator("#notice").inner_text() and "820/827" in await p8.locator('[data-count="edf41"]').inner_text(),
          "a complete old checklist export (812 entries) imports as 820 of 827 weapons")
    await c8.close()
    # the same checklist left in this browser by the old site, imported from the offer on HQ
    c9 = await browser.new_context(viewport=PHONE)
    p9 = await c9.new_page()
    await p9.goto(BASE + "index.html")
    await p9.evaluate("(save) => { for (const k of Object.keys(save)) localStorage.setItem(k, JSON.stringify(save[k])); }", full)
    await p9.reload()
    check("812 weapons checked" in await p9.locator("#notice").inner_text(), "HQ offers to import a checklist left on this device")
    await p9.locator("#notice button", has_text="Import").click()
    await p9.wait_for_timeout(500)
    check("Imported 820" in await p9.locator("#notice").inner_text() and "820/827" in await p9.locator('[data-count="edf41"]').inner_text(), "the offer on HQ imports the complete checklist")
    check((await p9.locator('#segProfile .slot[data-slot="pc1"] .slot__count').inner_text()).strip() == "820/827", "the profile list shows the imported progress straight away")
    await p9.reload()
    check(not await p9.locator("#notice").is_visible(), "the offer does not come back after importing")
    # someone who imported before v1.4.1 (when most weapons were missed) is offered it once more; it only adds
    await p9.evaluate("""() => { localStorage.setItem('edfTracker.legacyDone', '1');
        localStorage.setItem('edfTracker.edf41', JSON.stringify({ owned: ['GenocideGun'], stars: {} })); }""")
    await p9.goto(BASE + "edf41.html")
    await p9.wait_for_selector(".row")
    check(await p9.locator("#banner").is_visible() and "missed most of them" in await p9.locator("#banner").inner_text(), "an import from before the fix is offered once more")
    await p9.locator('[data-act="legacy-import"]').click()
    await p9.wait_for_timeout(500)
    owned = json.loads(await p9.evaluate("localStorage.getItem('edfTracker.edf41')"))["owned"]
    check(len(owned) == 821 and "GenocideGun" in owned, "importing again adds the missing weapons and keeps what was already marked")
    await p9.reload()
    await p9.wait_for_selector(".row")
    check(not await p9.locator("#banner").is_visible(), "after that the offer is gone for good")
    await c9.close()

    # ---- mouse users get compact rows
    c6 = await browser.new_context(viewport={"width": 1280, "height": 800})
    p6 = await c6.new_page()
    await p6.goto(BASE + "edf6.html")
    await p6.wait_for_selector(".row")
    check(await p6.evaluate("Math.round(document.querySelector('.row').getBoundingClientRect().height)") <= 38, "desktop rows are compact")
    await c6.close()

    # ---- HQ on phones: the three game cards are on the first screen, and everything below
    # them can be scrolled clear of the game bar (nothing is left cut off behind it)
    for w, h in [(402, 874), (390, 844), (360, 640)]:
        c = await browser.new_context(viewport={"width": w, "height": h})
        p = await c.new_page()
        await p.goto(BASE + "index.html")
        await p.evaluate("document.fonts.ready")
        fit = await p.evaluate("""() => { const m = document.querySelector('.hq-main'), b = m.getBoundingClientRect();
            const cards = [...document.querySelectorAll('.card')].map((e) => e.getBoundingClientRect());
            const cardsOnScreen = cards.every((r) => r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5);
            m.scrollTop = m.scrollHeight;
            const cut = [...document.querySelectorAll('.hq-main .settings button, .hq-main .settings input, .actions button, .credit a')].filter((e) => { const r = e.getBoundingClientRect(); return r.height && r.bottom > b.bottom - 19.5; }).length;
            return { cardsOnScreen, cut, atEnd: Math.abs(m.scrollTop + m.clientHeight - m.scrollHeight) < 1, cards: cards.map((r) => Math.round(r.height)) }; }""")
        check(fit["cardsOnScreen"] and fit["atEnd"] and fit["cut"] == 0 and min(fit["cards"]) >= 70, f"HQ on a {w}x{h} phone: cards on the first screen, the rest scrolls clear of the game bar {fit}")
        await c.close()

    # ---- 60% text: the star meter stays inside its own column
    c = await browser.new_context(viewport=PHONE)
    p = await c.new_page()
    await p.add_init_script("localStorage.setItem('edfTracker.prefs', JSON.stringify({text: '0.6', fx: 'on'}))")
    await p.goto(BASE + "edf5.html")
    await p.wait_for_selector(".row")
    gap = await p.evaluate("""() => { const row = document.querySelector('.row');
        return row.querySelector('.meter__track').getBoundingClientRect().left - row.querySelector('.row__lv').getBoundingClientRect().right; }""")
    check(gap >= -0.5, f"at 60% text the star meter does not run into the level ({gap:.1f}px apart)")
    await c.close()

    # ---- import from the game's own save file (PC): owned weapons, for all three games
    js_src = (ROOT / "js" / "savefile.js").read_text(encoding="utf-8")
    js_keys = {g: re.search(g + r": \{.*?key: hex\('([0-9a-f]+)'\),\s*counter: hex\('([0-9a-f]+)'\)", js_src, re.S).groups() for g in SAVE_LAYOUT}
    check(all(js_keys[g] == (SAVE_LAYOUT[g]["key"].hex(), SAVE_LAYOUT[g]["counter"].hex()) for g in SAVE_LAYOUT), "the save keys in savefile.js are the ones the documented recipe gives")
    totals = {"edf41": 827, "edf5": 1187, "edf6": 1564}
    # Which weapon sits at a few positions of each game's save, as found in real saves (owned starter weapons,
    # weapons seen in a young save), and a fingerprint of each whole list so that it cannot change unnoticed.
    KNOWN = {
        "edf41": ({29: "Weapon028", 66: "Weapon064", 232: "Weapon213", 410: "Weapon384", 608: "Weapon569", 739: "eVehicle_Tank_DcZero"}, "aff6eeef9757de2756ee3c76d509ba28f3a8904491c02750cdb35aafb6ecb1c6"),
        "edf5": ({0: "AssultRifle01", 104: "RocketLauncher01", 327: "pRapier01", 613: "hPileBanker01", 799: "eWeapon001", 979: "eLifeBender"}, "410c4ddac5e689025ddf67777e5d120d5a2c4f6e621e69b3d4da1303acfc9a3b"),
        "edf6": ({0: "AssultRifle01", 1: "aWeapon001", 111: "aWeapon110", 392: "pWeapon008", 694: "hWeapon004", 925: "eRequestMortar02", 1563: "INDLC_holo_decoy_irys"}, "f352f1e4640f68d61f04379a37c5cfb16aa58b24881fd4dc0267bf59e5afe42f"),
    }
    maps, caps = {}, {}
    for g in SAVE_LAYOUT:
        rows = json.loads((ROOT / "data" / f"{g}-save.json").read_text(encoding="utf-8"))["rows"]
        data = json.loads((ROOT / "data" / f"{g}.json").read_text(encoding="utf-8"))
        items = [it for c in data["classes"] for k in c["cats"] for it in k["items"]]
        maps[g] = rows
        caps[g] = {it[0]: [u[1] for u in (it[4] if len(it) > 4 else [])] for it in items}
        spots, print_ = KNOWN[g]
        check(len(rows) == totals[g] and len(set(rows)) == len(rows) and set(rows) == set(caps[g]) and all(rows[i] == w for i, w in spots.items())
              and hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest() == print_,
              f"{g}: the list of save positions names every one of the {totals[g]} weapons once, in the order found in real saves")
    cs = await browser.new_context(viewport=PHONE)
    ps = await cs.new_page()
    await watch(ps, errors, external)
    await ps.goto(BASE + "index.html")
    sdir = Path(tempfile.mkdtemp())
    check(await ps.locator("#saveOpen").is_visible() and not await ps.locator("#saveIn").is_visible(), "HQ has an Import from game save button; its panel starts closed")
    await ps.locator("#saveOpen").click()
    await ps.wait_for_selector("#saveIn:not([hidden])")
    check(await ps.evaluate("[...document.querySelector('#saveGame').options].map((o) => o.value)") == ["edf41", "edf5", "edf6"] and await ps.locator("#saveSlot option").count() == 8
          and await ps.evaluate("document.activeElement === document.querySelector('#saveTitle')"), "the panel offers all three games and the eight profiles, and takes the keyboard focus")
    RESULT = "!document.querySelector('#saveResult').hidden && !/Reading/.test(document.querySelector('#saveResult').textContent)"
    STORED = "(k) => JSON.parse(localStorage.getItem(k) || '{\"owned\":[],\"stars\":{}}')"
    ALL = "JSON.stringify(Object.keys(localStorage).sort().map((k) => [k, localStorage.getItem(k)]))"

    async def stored(g, slot):
        return await ps.evaluate(STORED, "edfTracker." + slot + "." + g)

    async def choose(path):
        await ps.set_input_files("#saveFile", path)
        await ps.wait_for_function(RESULT)
        return [t.strip() for t in await ps.locator("#saveResult button").all_inner_texts()]

    # What the games' own files say. tools/game-stars: weapon -> [[slot, kind of value, steps]] for every upgradable
    # value ("steps" is how many levels it has; a save holds 0..steps in the byte numbered "slot").
    # tools/game-lines: weapon -> [[label, [slot, ...]]], the lines of the equipment screen that carry a star.
    # The game prints a level as a star: the level itself with 5 steps or more, and level * 5 // steps with
    # fewer, so the most an upgrade can show is max(5, steps). The expected results below are worked out
    # from these facts and the upgrade names, not from the "stars" strings in data/<game>-save.json that
    # the app itself reads.
    PART = {0: "Capacity", 1: "Count", 2: "Damage", 4: "Range", 9: "Range", 20: "Speed"}
    STAR_PRINTS = {"edf5": "4d6fc70f5a5bd748fa7b13f776634ea8632f145a0910617fa1985968a51c6cf2", "edf6": "327d8aed8001b5aa4fc7edfbd6ecbc6d2b06237e1dba8ba1104d70b20b5f5db0"}
    ups_of, slot_of, steps_of, lines_of = {}, {}, {}, {}

    def upgrade_names(lines, kinds):
        """slot -> the upgrade's name: the label of the first line that shows it; "<line>: <part>" when it shares that line."""
        names = {}
        for label, slots in lines:
            for slot in slots:
                if len(slots) == 1:
                    names.setdefault(slot, label)
                    continue
                part = "Targets" if label.startswith("Lock-on") and kinds[slot] >> 2 in (0, 1) else PART[kinds[slot] >> 2]
                names.setdefault(slot, label if part == label else label + ": " + part)
        return names

    for g in ("edf5", "edf6"):
        data = json.loads((ROOT / "data" / f"{g}.json").read_text(encoding="utf-8"))
        facts = json.loads((ROOT / "tools" / "game-stars" / f"{g}.json").read_text(encoding="utf-8"))
        shown = json.loads((ROOT / "tools" / "game-lines" / f"{g}.json").read_text(encoding="utf-8"))
        save_map = json.loads((ROOT / "data" / f"{g}-save.json").read_text(encoding="utf-8"))
        items = {it[0]: it for c in data["classes"] for k in c["cats"] for it in k["items"]}
        ups_of[g] = {w: [(data["stats"][s], m) for s, m in (it[4] if len(it) > 4 else [])] for w, it in items.items()}
        lines_of[g] = {w: [(data["stats"][l], us) for l, us in (it[5] if len(it) > 5 else [])] for w, it in items.items()}
        steps_of[g] = {w: {slot: steps for slot, _, steps in rows_} for w, rows_ in facts.items()}
        slot_of[g], wrong = {}, []
        for w, ups in ups_of[g].items():
            by_name = {name: slot for slot, name in upgrade_names(shown.get(w, []), {slot: kind for slot, kind, _ in facts.get(w, [])}).items()}
            slot_of[g][w] = [by_name.get(name) for name, _ in ups]
            want_lines = [(label, [slot_of[g][w].index(slot) if slot in slot_of[g][w] else None for slot in slots]) for label, slots in shown.get(w, [])]
            if (None in slot_of[g][w] or sorted(slot_of[g][w]) != sorted(steps_of[g].get(w, {})) or lines_of[g][w] != want_lines
                    or any(most != max(5, steps_of[g][w][slot]) for (_, most), slot in zip(ups, slot_of[g][w]))):
                wrong.append(w)
        described = ["".join(str(slot) + "0123456789a"[steps_of[g][w][slot]] for slot in slot_of[g][w]) for w in save_map["rows"]]
        check(not wrong and save_map.get("stars") == described and hashlib.sha256(json.dumps(save_map["stars"], separators=(",", ":")).encode()).hexdigest() == STAR_PRINTS[g],
              f"{g}: every upgradable value in the game's files is an upgrade, named and lined up as on the game's screen, with max(5, steps) stars and its own place in a save {wrong[:3]}")

    async def maxed_is(g, slot, n):
        """True once the profile's summary says n weapons are fully upgraded (the recount runs after the import)."""
        try:
            await ps.wait_for_function("(a) => { try { return JSON.parse(localStorage.getItem(a[0]) || '{}').maxed === a[1]; } catch (e) { return false; } }",
                                       arg=["edfTracker." + slot + ".summary." + g, n], timeout=5000)
            return True
        except Exception:
            return False

    def star_of(level, steps):
        """The star the game prints for a level."""
        level = min(level, steps)
        return level if steps >= 5 else level * 5 // steps

    def stars_in_save(g, weapon, bytes8):
        """The stars the game shows, and so the tracker should, for a weapon whose eight level bytes in the save are `bytes8`."""
        return [star_of(bytes8[slot], steps_of[g][weapon][slot]) for slot in slot_of.get(g, {}).get(weapon, [])]

    for g in ("edf41", "edf5", "edf6"):
        rows = maps[g]
        last = len(rows) - 1
        has_stars = g != "edf41"
        # owned in several ways (lowest bit set), one entry that is not owned (2), and one past the tracker's list
        conds = {0: 1, 1: 3, 2: 2, 7: 5, 40: 11, last: 9, len(rows) + 3: 1}
        want = sorted([rows[0], rows[1], rows[7], rows[40], rows[last]])
        # star bytes: a mix of levels for the first weapon, everything far above the most for the second,
        # other levels for the third; the rest have none. The entry that is not owned has stars too.
        star_bytes = {0: [1, 2, 3, 4, 5, 6, 7, 8], 1: [10] * 8, 2: [5] * 8, 7: [3, 0, 2, 1, 0, 4, 2, 1]} if has_stars else {}
        # (a weapon whose levels are all 0 has no stars)
        in_save = {rows[r]: stars_in_save(g, rows[r], star_bytes.get(r, [0] * 8)) for r in (0, 1, 7, 40, last)} if has_stars else {}
        in_save = {w: s for w, s in in_save.items() if any(s)}
        path = await save_file(ps, sdir, g, g, save_plaintext(g, conds, stars=star_bytes))
        card = await ps.locator('[data-count="' + g + '"]').inner_text()
        await ps.select_option("#saveGame", g)
        await ps.select_option("#saveSlot", "con3")
        check(await ps.locator("#saveStarsRow").is_visible() == has_stars and await ps.locator("#saveStars").is_checked(), f"{g}: reading star levels is {'offered and on' if has_stars else 'not offered (the game has none)'}")
        buttons = await choose(path)
        said = " ".join([t.strip() for t in await ps.locator("#saveResult p").all_inner_texts()])
        check(f"owns 5 of {totals[g]} weapons" in said and buttons == ["Add 5", "Cancel"] and (await stored(g, "con3"))["owned"] == [] and (("raises the stars of %d weapons" % len(in_save)) in said) == has_stars,
              f"{g}: the save is read and shown before anything changes ({said[:60]})")
        await ps.locator("#saveResult button", has_text="Add").click()
        counted = await maxed_is(g, "con3", 1 if has_stars else 0)
        got = await stored(g, "con3")
        slot_count = (await ps.evaluate("(g) => { document.querySelector('#segGame button[data-game=' + g + ']').click(); return document.querySelector('#segProfile .slot[data-slot=con3] .slot__count').textContent; }", g)).strip()
        check(sorted(got["owned"]) == want and got["stars"] == in_save and await ps.locator('[data-count="' + g + '"]').inner_text() == card and slot_count == f"5/{totals[g]}"
              and await ps.evaluate("localStorage.getItem('edfTracker.slotsUsed.' + '%s')" % g) == "1" and counted,
              f"{g}: Add marks exactly the weapons the save owns, with the star levels the save holds, in the chosen profile only ({slot_count}, {len(got['stars'])} with stars)")
        # later the player marks another weapon, earns stars on it, and changes the stars of one imported weapon;
        # Undo must take back only what the import did and leave those later changes (that weapon stays marked)
        later = rows[9]
        changed = [0] * len(in_save.get(rows[7], [1]))
        changed[0] = 1
        await ps.evaluate("(a) => { const p = JSON.parse(localStorage.getItem(a[0])); p.owned.push(a[1]); p.stars[a[1]] = [2]; if (a[3]) p.stars[a[2]] = a[4]; localStorage.setItem(a[0], JSON.stringify(p)); }",
                          ["edfTracker.con3." + g, later, rows[7], has_stars, changed])
        await ps.locator("#saveResult button", has_text="Undo").click()
        got = await stored(g, "con3")
        check(sorted(got["owned"]) == sorted([later, rows[7]] if has_stars else [later]) and got["stars"] == ({later: [2], rows[7]: changed} if has_stars else {later: [2]})
              and "taken back" in await ps.locator("#saveResult").inner_text() and await ps.locator("#saveResult button").count() == 0,
              f"{g}: Undo takes back the import and keeps what was done afterwards")
        # a profile that already has one of the save's weapons and one the save does not own, both fully upgraded
        extra = rows[2]
        full = {w: [m for _, m in ups_of[g][w]] for w in (rows[0], extra)} if has_stars else {}
        mine = {"owned": [rows[0], extra], "stars": dict(full)}
        await ps.evaluate("(a) => localStorage.setItem(a[0], JSON.stringify(a[1]))", ["edfTracker.pc2." + g, mine])
        await ps.select_option("#saveSlot", "pc2")
        buttons = await choose(path)
        said = " ".join([t.strip() for t in await ps.locator("#saveResult p").all_inner_texts()])
        check(buttons == ["Add 4", "Match the save", "Cancel"] and ("lowers the stars of 1 weapon" in said) == has_stars, f"{g}: with other weapons marked, both Add and Match are offered {buttons}")
        await ps.locator("#saveResult button", has_text="Add 4").click()
        got = await stored(g, "pc2")
        after_add = dict(full)
        after_add.update({w: s for w, s in in_save.items() if w != rows[0]})
        check(sorted(got["owned"]) == sorted(want + [extra]) and got["stars"] == after_add, f"{g}: Add never unmarks a weapon and never lowers a star level")
        await ps.locator("#saveResult button", has_text="Undo").click()
        got = await stored(g, "pc2")
        check(sorted(got["owned"]) == sorted(mine["owned"]) and got["stars"] == mine["stars"], f"{g}: Undo after Add puts the profile back exactly")
        buttons = await choose(path)
        await ps.locator("#saveResult button", has_text="Match the save").click()
        counted = await maxed_is(g, "pc2", 1 if has_stars else 0)  # the count of fully upgraded weapons is redone from the weapon list
        got = await stored(g, "pc2")
        summary = await ps.evaluate(STORED, "edfTracker.pc2.summary." + g)
        after_match = dict(in_save)
        if has_stars:
            after_match[extra] = full[extra]  # its stars stay stored; they only count again if it is marked
        check(sorted(got["owned"]) == want and got["stars"] == after_match and summary.get("owned") == 5 and counted,
              f"{g}: Match makes the profile own what the save owns, at the save's star levels, and recounts fully upgraded weapons ({summary})")
        await ps.locator("#saveResult button", has_text="Undo").click()
        counted = await maxed_is(g, "pc2", 2 if has_stars else 0)
        got = await stored(g, "pc2")
        summary = await ps.evaluate(STORED, "edfTracker.pc2.summary." + g)
        check(sorted(got["owned"]) == sorted(mine["owned"]) and got["stars"] == mine["stars"] and counted,
              f"{g}: Undo after Match brings back the unmarked weapon and the earlier star levels ({summary})")
        if has_stars:  # with "Also read star levels" unticked only the weapons are imported
            await ps.select_option("#saveSlot", "con2")
            await ps.locator("#saveStars").uncheck()
            buttons = await choose(path)
            said = " ".join([t.strip() for t in await ps.locator("#saveResult p").all_inner_texts()])
            await ps.locator("#saveResult button", has_text="Add").click()
            got = await stored(g, "con2")
            check("stars" not in said and sorted(got["owned"]) == want and got["stars"] == {}, f"{g}: with star levels unticked only the weapons are marked")
            await ps.locator("#saveStars").check()
            buttons = await choose(path)  # the weapons are there now; only stars are left to bring over
            check(buttons == ["Raise stars", "Cancel"], f"{g}: a profile that has the weapons but not the stars is offered the stars alone {buttons}")
            await ps.locator("#saveResult button", has_text="Raise stars").click()
            got = await stored(g, "con2")
            check(sorted(got["owned"]) == want and got["stars"] == in_save, f"{g}: Raise stars brings the star levels over")
            await ps.locator("#saveStars").uncheck()
            await ps.locator("#saveStars").check()
            check(await ps.locator("#saveResult button", has_text="Undo").count() == 1, f"{g}: ticking the star box after an import leaves its Undo in place")
            buttons = await choose(path)
            check(buttons == ["Cancel"] and "already match, weapons and stars" in await ps.locator("#saveResult").inner_text(), f"{g}: importing the same save again finds nothing to do")
            await ps.select_option("#saveSlot", "con4")
            buttons = await choose(path)
            await ps.locator("#saveStars").uncheck()
            dropped = not await ps.locator("#saveResult").is_visible()
            await ps.locator("#saveStars").check()
            check(buttons[0] == "Add 5" and dropped and (await stored(g, "con4"))["owned"] == [], f"{g}: unticking the star box drops a preview that was made with stars")
            # v1.8.0 stored a stat that has fewer than 5 steps as its bare level (2 for a full 2-step stat) instead
            # of the 5 stars the game shows. Importing again must offer to raise those, and bring them to the top.
            bare = {w: [steps_of[g][w][slot] for slot in slot_of[g][w]] for w in (rows[0], rows[1])}
            tops = {w: [m for _, m in ups_of[g][w]] for w in (rows[0], rows[1])}
            path_top = await save_file(ps, sdir, g + "-top", g, save_plaintext(g, {0: 1, 1: 1}, stars={0: [10] * 8, 1: [10] * 8}))
            await ps.evaluate("(a) => localStorage.setItem(a[0], JSON.stringify(a[1]))", ["edfTracker.pc3." + g, {"owned": [rows[0], rows[1]], "stars": bare}])
            await ps.select_option("#saveSlot", "pc3")
            buttons = await choose(path_top)
            if "Raise stars" in buttons:
                await ps.locator("#saveResult button", has_text="Raise stars").click()
            got = await stored(g, "pc3")
            check(bare != tops and buttons == ["Raise stars", "Cancel"] and got["stars"] == tops and await maxed_is(g, "pc3", 2),
                  f"{g}: stars that v1.8.0 imported too low are raised to what the game shows by importing again {buttons}")
            # v1.8.1 stored an unfinished upgrade with fewer than 5 steps as level + (5 - steps), which is more than
            # the game shows. Add never lowers a star, so only Match is offered, and it brings them down.
            short = next(i for i, w in enumerate(rows) if any(1 < st < 5 for st in steps_of[g].get(w, {}).values()))
            w_short = rows[short]
            high = [min(1, steps_of[g][w_short][slot]) + max(0, 5 - steps_of[g][w_short][slot]) for slot in slot_of[g][w_short]]
            real = stars_in_save(g, w_short, [1] * 8)
            path_low = await save_file(ps, sdir, g + "-low", g, save_plaintext(g, {short: 1}, stars={short: [1] * 8}))
            await ps.evaluate("(a) => localStorage.setItem(a[0], JSON.stringify(a[1]))", ["edfTracker.pc4." + g, {"owned": [w_short], "stars": {w_short: high}}])
            await ps.select_option("#saveSlot", "pc4")
            buttons = await choose(path_low)
            if "Match the save" in buttons:
                await ps.locator("#saveResult button", has_text="Match the save").click()
            got = await stored(g, "pc4")
            check(high != real and all(a >= b for a, b in zip(high, real)) and buttons == ["Match the save", "Cancel"] and got["stars"] == {w_short: real},
                  f"{g}: stars that v1.8.1 imported too high are brought down by Match the save {buttons} {high} -> {got['stars'].get(w_short)}")
            # The star the game prints for every level of an upgrade with 1, 2, 3 or 4 steps. Written out here, not
            # worked out, and read straight from the save reader.
            SHOWN = {1: [0, 5], 2: [0, 2, 5], 3: [0, 1, 3, 5], 4: [0, 1, 2, 3, 5]}
            pick = {}  # steps -> (row in the save, upgrade, slot) of the first weapon that has such an upgrade
            for i, w in enumerate(rows):
                for u, slot in enumerate(slot_of[g].get(w, [])):
                    pick.setdefault(steps_of[g][w][slot], (i, u, slot))
            seen = {st: [] for st in SHOWN}
            for level in range(5):
                eights = {}
                for st in SHOWN:
                    eights.setdefault(pick[st][0], [0] * 8)[pick[st][2]] = level
                blob = Path(await save_file(ps, sdir, f"{g}-lv{level}", g, save_plaintext(g, {r: 1 for r in eights}, stars=eights))).read_bytes()
                found = await ps.evaluate("""async (a) => { const lib = await import('./js/savefile.js');
                    const read = await lib.readSave(a[0], Uint8Array.from(atob(a[1]), (c) => c.charCodeAt(0)).buffer); return read.stars; }""", [g, base64.b64encode(blob).decode()])
                for st in SHOWN:
                    if level <= st:
                        seen[st].append(found[rows[pick[st][0]]][pick[st][1]])
            check(seen == SHOWN, f"{g}: an upgrade with fewer than 5 steps is read as the star the game prints, level by level {seen}")
        # files that must be refused, with nothing changed
        before = await ps.evaluate(ALL)
        good = Path(path).read_bytes()
        bad = {
            "another file of the same size": (bytes(len(good)), "is not MAIN.GST from this game"),
            "a damaged save": (Path(await save_file(ps, sdir, g + "-sum", g, save_plaintext(g, conds, fix_sum=False))).read_bytes(), "damaged"),
            "a save in a newer format": (Path(await save_file(ps, sdir, g + "-fmt", g, save_plaintext(g, conds, fmt=9))).read_bytes(), "format the tracker does not know"),
            "a cut-off file": (good[:-16], "not the right file"),
            "an empty file": (b"", "not the right file"),
        }
        refused = {}
        for what, (blob, expect) in bad.items():
            p_bad = sdir / (g + "-bad") / "MAIN.GST"
            p_bad.parent.mkdir(exist_ok=True)
            p_bad.write_bytes(blob)
            await choose(str(p_bad))
            refused[what] = expect in await ps.locator("#saveResult").inner_text() and await ps.locator("#saveResult button").count() == 0
        check(all(refused.values()) and await ps.evaluate(ALL) == before, f"{g}: files that are not a readable save are refused and nothing changes {refused}")
    # a save picked while another game is chosen is recognised by its size
    await ps.select_option("#saveGame", "edf41")
    await ps.select_option("#saveSlot", "con4")
    await choose(str(sdir / "edf6" / "MAIN.GST"))
    check(await ps.locator("#saveGame").input_value() == "edf6" and await ps.locator("#saveSlot").input_value() == "con4" and "Game was changed to EDF 6" in await ps.locator("#saveResult").inner_text()
          and "owns 5 of 1564" in await ps.locator("#saveResult").inner_text(), "a save chosen under the wrong game switches the Game and keeps the chosen profile")
    # changing the profile while a preview is showing clears it, so its buttons cannot act on another profile
    await ps.select_option("#saveSlot", "pc3")
    check(not await ps.locator("#saveResult").is_visible(), "changing the profile clears a preview that was for another profile")
    # the list of profiles in the panel follows a rename and a switch made while it is open
    ps.once("dialog", lambda d: asyncio.ensure_future(d.accept("Storm 1")))
    await ps.evaluate("document.querySelector('#segGame button[data-game=edf6]').click()")
    await ps.evaluate("document.querySelector('#segProfile .slot[data-slot=pc3]').click()")
    await ps.evaluate("document.querySelector('#renameProfile').click()")
    check(await ps.evaluate("[...document.querySelector('#saveSlot').options].map((o) => o.textContent)[2]") == "Storm 1 (in use)", "the panel's profile list follows a rename and a switch")
    await ps.locator("#saveClose").focus()
    await ps.keyboard.press("Enter")  # by keyboard: Safari does not give a clicked button the focus
    check(not await ps.locator("#saveIn").is_visible() and await ps.locator("#saveOpen").get_attribute("aria-expanded") == "false" and await ps.evaluate("document.activeElement === document.querySelector('#saveOpen')"),
          "the panel closes again and hands the keyboard focus back to its button")
    await cs.close()
    # when the weapon list cannot be fetched the player is told plainly, in the app's own words, and can try again
    cs2 = await browser.new_context(viewport=PHONE)
    ps2 = await cs2.new_page()
    await ps2.add_init_script("""window.__list = 'gone'; const realFetch = window.fetch.bind(window);
        window.fetch = (url, opts) => { if (String(url).indexOf('edf5-save.json') === -1 || window.__list === 'ok') return realFetch(url, opts);
            return window.__list === 'gone' ? Promise.reject(new TypeError('Failed to fetch')) : Promise.resolve(new Response('<html>not found</html>', { status: 200 })); };""")
    await ps2.goto(BASE + "index.html")
    await ps2.locator("#saveOpen").click()
    await ps2.wait_for_selector("#saveIn:not([hidden])")
    await ps2.select_option("#saveGame", "edf5")
    said = []
    for mode in ("gone", "html", "ok"):
        await ps2.evaluate("(m) => { window.__list = m; }", mode)
        await ps2.set_input_files("#saveFile", str(sdir / "edf5" / "MAIN.GST"))
        await ps2.wait_for_function(RESULT)
        said.append((await ps2.locator("#saveResult p").first.inner_text()).strip())
    check(all("weapon list for reading saves did not load" in s for s in said[:2]) and "owns 5 of 1187" in said[2], f"a weapon list that cannot be fetched gives a plain message, and trying again works {[s[:34] for s in said]}")
    await cs2.close()
    cs3 = await browser.new_context(viewport=PHONE)
    ps3 = await cs3.new_page()
    await ps3.add_init_script("""const realFetch = window.fetch.bind(window);
        window.fetch = (url, opts) => (String(url).indexOf('edf5-save.json') === -1 ? realFetch(url, opts)
            : realFetch(url, opts).then((r) => r.json()).then((m) => new Response(JSON.stringify({ game: m.game, rows: m.rows }))));""")
    await ps3.goto(BASE + "index.html")
    await ps3.locator("#saveOpen").click()
    await ps3.wait_for_selector("#saveIn:not([hidden])")
    await ps3.select_option("#saveGame", "edf5")
    await ps3.set_input_files("#saveFile", str(sdir / "edf5" / "MAIN.GST"))
    await ps3.wait_for_function(RESULT)
    told = await ps3.locator("#saveResult").inner_text()
    await ps3.locator("#saveResult button", has_text="Add").click()
    old_map = await ps3.evaluate(STORED, "edfTracker.edf5")  # PC 1, the profile in use, keeps the plain key
    check("Star levels could not be read this time" in told and len(old_map["owned"]) == 5 and old_map["stars"] == {}, "with a weapon list from before star levels were added, the weapons still import and the player is told the stars were not read")
    await cs3.close()

    # ---- a page that cannot fit one screen scrolls instead of clipping the details header (very narrow phones, wide fonts)
    for (w, h), type_prefs, expect in (((280, 653), {}, True), ((402, 874), {}, False), ((320, 568), {"edf5": {"font": "orbitron", "bold": True, "caps": True}}, None)):
        c = await browser.new_context(viewport={"width": w, "height": h})
        p = await c.new_page()
        await p.add_init_script("localStorage.setItem('edfTracker.prefs', JSON.stringify({text: '1', fx: 'on', type: %s}))" % json.dumps(type_prefs))
        await p.goto(BASE + "edf5.html")
        await p.wait_for_selector(".row")
        await p.evaluate("document.fonts.ready")
        await p.wait_for_timeout(100)
        r = await p.evaluate("""() => { const d = document.querySelector('.detail'), hd = document.querySelector('.detail__head');
            return { noFit: document.documentElement.classList.contains('no-fit'), headWhole: hd.getBoundingClientRect().bottom <= d.getBoundingClientRect().bottom + 1, scrolls: document.documentElement.scrollHeight > innerHeight }; }""")
        check(r["headWhole"] and (expect is None or (r["noFit"] == expect and r["scrolls"] == expect)), f"EDF 5 at {w}x{h}{' in a wide font' if type_prefs else ''}: the details header is whole ({'scrolling' if r['noFit'] else 'one screen'}) {r}")
        await c.close()

    # ---- layout at every size
    WIDE = {g: {"font": "orbitron", "size": "same", "bold": True, "italic": False, "caps": True} for g in ("edf41", "edf5", "edf6")}  # the widest font, bold, in capitals
    for page_name, text, layout, wide in [(n, t, l, w) for t, l, w in (("0.6", "fit", False), ("1", "fit", False), ("1.5", "fit", False), ("1", "scroll", False), ("1", "fit", True), ("1.5", "fit", True)) for n in ("edf41", "edf5", "edf6", "index")]:
        if wide and page_name == "index":
            continue
        bad = []
        tall_note = (", Taller lists" if layout == "scroll" else "") + (", Orbitron bold capitals" if wide else "")
        for w, h in SIZES:
            c = await browser.new_context(viewport={"width": w, "height": h})
            p = await c.new_page()
            await p.add_init_script("localStorage.setItem('edfTracker.prefs', JSON.stringify({text: '%s', fx: 'on', layout: '%s', type: %s}))" % (text, layout, json.dumps(WIDE if wide else {})))
            await p.goto(BASE + page_name + ".html")
            if page_name != "index":
                await p.wait_for_selector(".row")
            await p.evaluate("document.fonts.ready")  # measure in the real font, not the fallback shown while it loads
            # When the page scrolls, the game bar floats over it; measure at the end of the page.
            r = await p.evaluate("""() => { window.scrollTo(0, document.documentElement.scrollHeight);
                const nav = document.querySelector('nav').getBoundingClientRect();
                const d = document.querySelector('.detail'), l = document.querySelector('.list');
                const off = [...document.querySelectorAll('button, a, .pill, h1')].filter((e) => { const b = e.getBoundingClientRect(); return b.width && (b.right > innerWidth + 0.5 || b.left < -0.5); }).length;
                const nm = document.querySelector('.detail__name');
                const hd = document.querySelector('.detail__head');
                const cut = d && nm ? (nm.getBoundingClientRect().height < 10 || nm.getBoundingClientRect().bottom > d.getBoundingClientRect().bottom + 0.5 || nm.getBoundingClientRect().top < d.getBoundingClientRect().top - 0.5
                    || (hd && hd.getBoundingClientRect().bottom > d.getBoundingClientRect().bottom + 1)) : false;  // the name, and the whole header with its buttons
                return { docW: document.documentElement.scrollWidth, overlap: d ? d.getBoundingClientRect().bottom > nav.top + 0.5 : false, listH: l ? l.getBoundingClientRect().height : 999, off, cut }; }""")
            if r["docW"] > w or r["overlap"] or r["off"] or r["cut"] or r["listH"] < 130:
                bad.append((w, h, r))
            await c.close()
        check(not bad, f"{page_name}: layout holds at {len(SIZES)} screen sizes, text {round(float(text) * 100)}%{tall_note} {bad or ''}")

    check(not external, f"no requests leave the site {sorted(set(external))[:3] or ''}")
    check(not errors, f"no script or console errors {errors[:3] or ''}")

    # ---- offline (the local server is stopped to cut the connection for real)
    c4 = await browser.new_context(viewport=PHONE)
    p4 = await c4.new_page()
    await p4.goto(BASE + "index.html")
    await p4.wait_for_function("navigator.serviceWorker.ready.then(() => true)")
    await p4.wait_for_timeout(1200)
    cached = await p4.evaluate("caches.keys().then((k) => caches.open(k[0]).then((c) => c.keys()).then((r) => r.map((x) => new URL(x.url).pathname)))")
    check(not any(u.endswith("edf6.json") for u in cached) and any(u.endswith("hq.css") for u in cached), "first visit downloads HQ only, not the game data")
    await p4.goto(BASE + "edf5.html")
    await p4.wait_for_selector(".row")
    c5 = await browser.new_context(viewport=PHONE)
    p5 = await c5.new_page()
    await p5.goto(BASE + "edf41.html")  # very first visit lands on a game page
    await p5.wait_for_selector(".row")
    await p5.wait_for_function("navigator.serviceWorker.ready.then(() => true)")
    c12 = await browser.new_context(viewport=PHONE)
    p12 = await c12.new_page()
    await p12.add_init_script("localStorage.setItem('edfTracker.prefs', JSON.stringify({ type: { edf6: { font: 'tektur' } } }))")
    await p12.goto(BASE + "edf6.html")  # first visit, with a font picked for this game
    await p12.wait_for_selector(".row")
    await p12.wait_for_function("navigator.serviceWorker.ready.then(() => true)")
    c13 = await browser.new_context(viewport=PHONE)
    p13 = await c13.new_page()
    await p13.goto(BASE + "index.html")
    await p13.wait_for_function("navigator.serviceWorker.controller !== null")
    await p13.goto(BASE + "edf41.html")  # the game is saved for offline use with its own font
    await p13.wait_for_selector(".row")
    await p13.goto(BASE + "index.html")
    await p13.locator('#segGame button[data-game="edf41"]').click()
    await p13.select_option("#typeFont", "jura")  # picked on HQ; the game page is not opened again before going offline
    await p4.wait_for_timeout(2000)
    SERVER.terminate()
    SERVER.wait()
    await p4.goto(BASE + "edf5.html")
    await p4.wait_for_selector(".row", timeout=5000)
    check(await p4.locator(".row").count() == 48, "a game that was opened once works offline")
    check(await p4.evaluate("document.fonts.ready.then(() => document.fonts.check('600 16px Rajdhani') && document.fonts.check('13px \\'Share Tech Mono\\''))"), "fonts load offline (self-hosted)")
    await p4.goto(BASE + "index.html")
    check(await p4.locator(".card").count() == 3 and (await p4.locator("#version").inner_text()).startswith("v"), "HQ works offline")
    await p4.goto(BASE + "edf6.html")
    check("Not saved for offline use yet" in await p4.inner_text("body"), "a game never opened explains how to make it available offline")
    await p5.reload()
    await p5.wait_for_selector(".row", timeout=5000)
    check(await p5.locator(".row").count() == 30, "landing directly on a game page also saves it for offline use")
    await p12.reload()
    await p12.wait_for_selector(".row", timeout=5000)
    check(await p12.evaluate("document.fonts.ready.then(() => document.fonts.check('500 17px Tektur') && document.fonts.check('600 17px Tektur') && /^['\"]?Tektur/.test(getComputedStyle(document.querySelector('.row__title')).fontFamily))"), "a font picked for a game is kept for offline use with it, in both weights")
    await p13.goto(BASE + "edf41.html")
    await p13.wait_for_selector(".row", timeout=5000)
    check(await p13.evaluate("document.fonts.ready.then(() => document.fonts.check('500 17px Jura') && document.fonts.check('700 17px Jura') && /^['\"]?Jura/.test(getComputedStyle(document.querySelector('.row__title')).fontFamily))"), "a font picked on HQ is ready on a game page that is next opened offline")


async def main() -> None:
    global SERVER
    SERVER = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT)], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        async with async_playwright() as p:
            exe = os.environ.get("EDF_CHROME")
            browser = await p.chromium.launch(executable_path=exe) if exe else await p.chromium.launch()
            await run(browser)
            await browser.close()
    finally:
        SERVER.terminate()
    print("\n%d failed" % len(fails) if fails else "\nAll checks passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    asyncio.run(main())
