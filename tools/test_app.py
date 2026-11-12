#!/usr/bin/env python3
"""End-to-end checks for the tracker, run in a headless browser.

Setup once:   pip install playwright && playwright install chromium
Run:          python3 tools/test_app.py
(Set EDF_CHROME to a browser binary to use one that is already installed.)

The script serves the repository on a local port, drives every control and
checks layout at several screen sizes. It exits with status 1 on any failure.
"""
import asyncio
import json
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
    await pg.evaluate("localStorage.setItem('edfTracker.seenVersion', '0.9.0')")
    await pg.reload()
    check("Updated to " + version in await pg.locator("#notice").inner_text(), "HQ announces an update once")
    await pg.reload()
    check(not await pg.locator("#notice").is_visible(), "the update note does not repeat")
    await pg.evaluate("localStorage.setItem('edfTracker.seenVersion', '0.9.0')")
    await pg.goto(BASE + "edf6.html")
    await pg.wait_for_selector(".row")
    check("Updated to " + version in await pg.locator("#toast").inner_text(), "game pages announce an update")
    await pg.evaluate("window.dispatchEvent(new Event('edf-update'))")
    check((await pg.locator("#toastundo").inner_text()).strip() == "Reload", "a version installed while the page is open offers Reload")
    await pg.goto(BASE + "index.html")

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

    # ---- profiles
    p1_count = await pg.locator('[data-count="edf6"]').inner_text()
    await pg.locator('#segProfile button[data-profile="2"]').click()
    check("0/1564" in await pg.locator('[data-count="edf6"]').inner_text(), "profile 2 starts empty")
    pg.once("dialog", lambda d: asyncio.ensure_future(d.accept("  Console <b>  ")))
    await pg.locator("#renameProfile").click()
    check((await pg.locator('#segProfile button[data-profile="2"]').inner_text()).strip() == "Console <b>", "a profile can be renamed (shown as plain text)")
    await pg.goto(BASE + "edf6.html")
    await pg.wait_for_selector(".row")
    check((await pg.locator(".pill--profile").inner_text()).strip() == "Console <b>", "game pages show which profile is active")
    await pg.locator(".box").nth(7).click()
    await pg.wait_for_timeout(400)
    both = await pg.evaluate("[JSON.parse(localStorage.getItem('edfTracker.p2.edf6')).owned.length, JSON.parse(localStorage.getItem('edfTracker.edf6')).owned.length]")
    check(both == [1, 2], f"profile 2 saves separately from profile 1 {both}")
    await pg.goto(BASE + "index.html")
    check("1/1564" in await pg.locator('[data-count="edf6"]').inner_text(), "HQ shows the active profile's progress")
    async with pg.expect_download() as dl2:
        await pg.click("#export")
    path2 = await (await dl2.value).path()
    exp2 = json.loads(Path(path2).read_text(encoding="utf-8"))
    check(len(exp2["profile2"]["games"]["edf6"]["owned"]) == 1 and len(exp2["games"]["edf6"]["owned"]) == 2 and exp2["profileNames"]["2"] == "Console <b>", "export holds both profiles and their names")
    await pg.locator('#segProfile button[data-profile="1"]').click()
    check(await pg.locator('[data-count="edf6"]').inner_text() == p1_count, "switching back restores profile 1")
    c7 = await browser.new_context(viewport=PHONE)
    p7 = await c7.new_page()
    p7.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await p7.goto(BASE + "index.html")
    await p7.set_input_files("#importfile", path2)
    await p7.wait_for_timeout(400)
    restored = await p7.evaluate("[JSON.parse(localStorage.getItem('edfTracker.p2.edf6')).owned.length, JSON.parse(localStorage.getItem('edfTracker.edf6')).owned.length]")
    check(restored == [1, 2] and (await p7.locator('#segProfile button[data-profile="2"]').inner_text()).strip() == "Console <b>", "import restores both profiles")
    await c7.close()

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
    evil = {"app": "edf-unlock-tracker", "version": 1, "games": {"edf6": {"owned": ["AssultRifle01", 5, {"x": 1}, "<img src=x onerror=alert(1)>"], "stars": {"AssultRifle01": [99, -3, "x"], "__proto__": [1], "bad": "str"}}}}
    (tmp / "evil.json").write_text(json.dumps(evil), encoding="utf-8")
    await p2.set_input_files("#importfile", str(tmp / "evil.json"))
    await p2.wait_for_timeout(300)
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

    # ---- HQ fits on one phone screen: nothing is cut off above the game bar
    for w, h in [(402, 874), (390, 844), (412, 800)]:
        c = await browser.new_context(viewport={"width": w, "height": h})
        p = await c.new_page()
        await p.goto(BASE + "index.html")
        await p.evaluate("document.fonts.ready")
        fit = await p.evaluate("""() => { const m = document.querySelector('.hq-main'), b = m.getBoundingClientRect();
            const cut = [...document.querySelectorAll('.hq-main button, .hq-main a, .hq-main input')].filter((e) => { const r = e.getBoundingClientRect(); return r.height && r.bottom > b.bottom + 0.5; }).length;
            return { over: m.scrollHeight - m.clientHeight, cut, cards: [...document.querySelectorAll('.card')].map((e) => Math.round(e.getBoundingClientRect().height)) }; }""")
        check(fit["over"] <= 0 and fit["cut"] == 0 and min(fit["cards"]) >= 70, f"HQ fits a {w}x{h} phone without scrolling {fit}")
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

    # ---- layout at every size
    for page_name, text in [(n, t) for t in ("0.6", "1", "1.5") for n in ("edf41", "edf5", "edf6", "index")]:
        bad = []
        for w, h in SIZES:
            c = await browser.new_context(viewport={"width": w, "height": h})
            p = await c.new_page()
            await p.add_init_script("localStorage.setItem('edfTracker.prefs', JSON.stringify({text: '%s', fx: 'on'}))" % text)
            await p.goto(BASE + page_name + ".html")
            if page_name != "index":
                await p.wait_for_selector(".row")
            # When the page scrolls, the game bar floats over it; measure at the end of the page.
            r = await p.evaluate("""() => { window.scrollTo(0, document.documentElement.scrollHeight);
                const nav = document.querySelector('nav').getBoundingClientRect();
                const d = document.querySelector('.detail'), l = document.querySelector('.list');
                const off = [...document.querySelectorAll('button, a')].filter((e) => { const b = e.getBoundingClientRect(); return b.width && (b.right > innerWidth + 0.5 || b.left < -0.5); }).length;
                const nm = document.querySelector('.detail__name');
                const cut = d && nm ? (nm.getBoundingClientRect().height < 10 || nm.getBoundingClientRect().bottom > d.getBoundingClientRect().bottom + 0.5 || nm.getBoundingClientRect().top < d.getBoundingClientRect().top - 0.5) : false;
                return { docW: document.documentElement.scrollWidth, overlap: d ? d.getBoundingClientRect().bottom > nav.top + 0.5 : false, listH: l ? l.getBoundingClientRect().height : 999, off, cut }; }""")
            if r["docW"] > w or r["overlap"] or r["off"] or r["cut"] or r["listH"] < 130:
                bad.append((w, h, r))
            await c.close()
        check(not bad, f"{page_name}: layout holds at {len(SIZES)} screen sizes, text {round(float(text) * 100)}% {bad or ''}")

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
