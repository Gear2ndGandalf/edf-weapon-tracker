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
