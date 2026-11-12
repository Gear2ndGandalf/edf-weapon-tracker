#!/usr/bin/env python3
"""Smoke test in Firefox and WebKit (the engine behind Safari), using Selenium.

tools/test_app.py covers every feature in Chromium. This script repeats the
core paths in the other two browser engines to catch engine differences.

Setup:  pip install selenium
        Firefox + geckodriver, and/or WebKitGTK's driver (Ubuntu: apt install webkit2gtk-driver xvfb)
Run:    python3 tools/test_browsers.py firefox
        xvfb-run -a -s "-screen 0 1920x1200x24" python3 tools/test_browsers.py webkit
Paths can be overridden with EDF_FIREFOX, EDF_GECKODRIVER, EDF_MINIBROWSER, EDF_WEBKITDRIVER.
Note: WebKitGTK is the same engine as Safari but not Safari itself; still check on a real iPhone.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

ROOT = Path(__file__).resolve().parent.parent
PORT = 8766
BASE = f"http://localhost:{PORT}/"
fails: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + msg, flush=True)
    if not ok:
        fails.append(msg)


def make_driver(name: str):
    if name == "firefox":
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
        opts = Options()
        opts.add_argument("-headless")
        if os.environ.get("EDF_FIREFOX"):
            opts.binary_location = os.environ["EDF_FIREFOX"]
        gecko = os.environ.get("EDF_GECKODRIVER")
        return webdriver.Firefox(options=opts, service=Service(gecko) if gecko else Service())
    from selenium.webdriver.webkitgtk.options import Options
    from selenium.webdriver.webkitgtk.service import Service
    opts = Options()
    opts.binary_location = os.environ.get("EDF_MINIBROWSER", "/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1/MiniBrowser")
    opts.add_argument("--automation")
    return webdriver.WebKitGTK(options=opts, service=Service(os.environ.get("EDF_WEBKITDRIVER", "/usr/bin/WebKitWebDriver")))


def wait_for(drv, css: str, timeout: float = 10.0):
    end = time.time() + timeout
    while time.time() < end:
        found = drv.find_elements(By.CSS_SELECTOR, css)
        if found:
            return found
        time.sleep(0.1)
    return []


def one(drv, css: str):
    return drv.find_element(By.CSS_SELECTOR, css)


def all_(drv, css: str):
    return drv.find_elements(By.CSS_SELECTOR, css)


def js(drv, script: str, *args):
    return drv.execute_script(script, *args)


def run(drv, name: str) -> None:
    print(name, drv.capabilities.get("browserVersion"), flush=True)
    drv.set_window_size(430, 900)

    # ---- HQ
    drv.get(BASE + "index.html")
    wait_for(drv, ".card")
    check(len(all_(drv, ".card")) == 3 and one(drv, "#version").text.startswith("v"), "HQ loads with three games and the version")
    check(js(drv, "return getComputedStyle(document.documentElement).getPropertyValue('--ts').trim()") == "1", "text size is 100% by default")

    # ---- each game renders its data
    for game, first, rows in [("edf41", "AF14", 30), ("edf5", "PA-11", 48), ("edf6", "Broken PA-11", 54)]:
        drv.get(BASE + game + ".html")
        check(len(wait_for(drv, ".row")) == rows and one(drv, ".row__label").text.strip() == first, f"{game}: {rows} weapons, first is {first}")

    # ---- engine features the layout depends on
    feats = js(drv, """
        const tabs = [...document.querySelectorAll('.tab')].map((t) => t.getBoundingClientRect());
        const star = document.querySelector('.ico--star');
        const cs = star ? getComputedStyle(star) : null;
        const shell = document.querySelector('.shell').getBoundingClientRect();
        return {
          gap: Math.round(tabs[1].left - tabs[0].right),
          mask: cs ? (cs.maskImage || cs.webkitMaskImage || '') : '',
          shell: Math.round(shell.height), win: window.innerHeight,
          docW: document.documentElement.scrollWidth, winW: window.innerWidth,
          font: document.fonts ? document.fonts.check("16px 'Share Tech Mono'") : null,
          sw: 'serviceWorker' in navigator,
        };""")
    check(feats["gap"] == 4, f"flexbox/grid gaps work (gap {feats['gap']}px)")
    check("url(" in feats["mask"], "icons are drawn with CSS masks")
    check(abs(feats["shell"] - feats["win"]) <= 1, f"page fills the window exactly ({feats['shell']} of {feats['win']}px)")
    check(feats["docW"] <= feats["winW"], "no sideways scrolling")
    check(feats["font"] is True, "bundled fonts load")
    print("      service worker API available:", feats["sw"], flush=True)

    # ---- EDF 6: owning, stars, undo, filters, search, picker, drops
    all_(drv, ".box")[1].click()
    check(all_(drv, ".box")[1].get_attribute("aria-pressed") == "true", "tap marks a weapon owned")
    drv.refresh()
    wait_for(drv, ".row")
    check(all_(drv, ".box")[1].get_attribute("aria-pressed") == "true", "progress survives a reload")
    all_(drv, ".row__name")[2].click()
    if not all_(drv, ".stat"):  # short window: open the upgrade panel
        one(drv, '[data-act="collapse"]').click()
    one(drv, '[data-act="inc"]').click()
    check(one(drv, ".row.is-cur .box").get_attribute("aria-pressed") == "true", "adding a star marks the weapon owned")
    stars = all_(drv, ".stat")[1].find_elements(By.CSS_SELECTOR, ".stat__stars i")
    js(drv, "arguments[0].scrollIntoView({block: 'center'})", stars[3])
    stars[3].click()
    lit = len(all_(drv, ".stat")[1].find_elements(By.CSS_SELECTOR, ".stat__stars i:not(.off)"))
    check(lit == 4, f"tapping the 4th star sets 4 stars (got {lit})")
    one(drv, '[data-act="max"]').click()
    check(len(all_(drv, ".row.is-cur .row__title .ico--star")) == 1, "Max shows the gold star")
    one(drv, '[data-act="clear"]').click()
    check(not one(drv, "#toast").get_attribute("hidden") and one(drv, "#toastundo").text.strip() == "Undo", "Clear offers Undo")
    one(drv, "#toastundo").click()
    check(len(all_(drv, ".row.is-cur .row__title .ico--star")) == 1, "Undo restores the stars")
    one(drv, '[data-act="view"][data-i="1"]').click()
    check("Offline" in one(drv, ".drops").text, "Drops view lists missions")
    one(drv, '[data-act="view"][data-i="0"]').click()
    one(drv, '[data-act="filter"][data-i="1"]').click()
    check(len(all_(drv, ".row")) == 52, "Missing filter hides owned weapons")
    one(drv, '[data-act="filter"][data-i="0"]').click()
    box = one(drv, "#q")
    box.send_keys("raven")
    time.sleep(0.3)
    n = len(all_(drv, ".row"))
    check(n > 5 and len(all_(drv, ".row__sub")) == n, f"search finds {n} weapons across the game")
    one(drv, "#qclear").click()
    check(len(all_(drv, ".row")) == 54, "clearing the search returns to the category")
    one(drv, "#catbtn").click()
    check(len(all_(drv, ".picker__item")) == 15 and not one(drv, "#listhead").is_displayed(), "category picker opens")
    tanks = all_(drv, ".picker__item")[12]
    js(drv, "arguments[0].scrollIntoView({block: 'center'})", tanks)  # some drivers do not scroll inner lists themselves
    time.sleep(0.2)
    tanks.click()
    name_now = js(drv, "return document.querySelector('#catname').textContent")  # .text is empty for clipped text in WebKit's driver
    check("Tanks" in name_now, f"picker jumps to Tanks (now: {name_now})")
    js(drv, "window.scrollTo(0, 0)")
    all_(drv, ".tab")[2].click()
    pressed = js(drv, "return document.querySelector('.tab[aria-pressed=true] .tab__name').textContent")
    check(pressed.startswith("A.Raider"), f"class tab switches (now: {pressed})")

    # ---- settings carry across pages; profiles keep progress apart
    drv.get(BASE + "index.html")
    wait_for(drv, ".card")
    check("2/1564" in one(drv, '[data-count="edf6"]').text, "HQ shows the saved progress")
    js(drv, "arguments[0].scrollIntoView({block: 'center'})", one(drv, '#segText button[data-text="1.3"]'))
    one(drv, '#segText button[data-text="1.3"]').click()
    one(drv, '#segFx button[data-fx="off"]').click()
    one(drv, '#segProfile button[data-profile="2"]').click()
    check("0/1564" in one(drv, '[data-count="edf6"]').text, "profile 2 starts empty")
    drv.get(BASE + "edf5.html")
    wait_for(drv, ".row")
    state = js(drv, """return { ts: getComputedStyle(document.documentElement).getPropertyValue('--ts').trim(),
        size: parseFloat(getComputedStyle(document.querySelector('.row__title')).fontSize),
        moving: document.getAnimations ? document.getAnimations().filter((a) => a.animationName && a.playState === 'running').length : 0,
        profile: (document.querySelector('.pill--profile') || {}).textContent || '',
        docW: document.documentElement.scrollWidth, winW: window.innerWidth };""")
    check(state["ts"] == "1.3" and abs(state["size"] - 22.1) < 0.3, f"130% text applies on game pages ({state['size']}px)")
    check(state["moving"] == 0, "Background effects Off stops the animations")
    check(state["profile"].strip() == "Profile 2", "game page shows the active profile")
    check(state["docW"] <= state["winW"], "no sideways scrolling at 130% text")
    drv.get(BASE + "index.html")
    wait_for(drv, ".card")
    for sel in ['#segText button[data-text="auto"]', '#segFx button[data-fx="on"]', '#segProfile button[data-profile="1"]']:
        js(drv, "arguments[0].scrollIntoView({block: 'center'})", one(drv, sel))
        one(drv, sel).click()
    check("2/1564" in one(drv, '[data-count="edf6"]').text, "switching back restores profile 1")

    # ---- layout at phone and desktop widths
    for w, h in [(430, 900), (1280, 800)]:
        drv.set_window_size(w, h)
        for page in ["edf41", "edf5", "edf6", "index"]:
            drv.get(BASE + page + ".html")
            if page != "index":
                wait_for(drv, ".row")
            time.sleep(0.2)
            r = js(drv, """window.scrollTo(0, document.documentElement.scrollHeight);
                const nav = document.querySelector('nav').getBoundingClientRect();
                const d = document.querySelector('.detail'), l = document.querySelector('.list');
                const off = [...document.querySelectorAll('button, a')].filter((e) => { const b = e.getBoundingClientRect(); return b.width && (b.right > innerWidth + 0.5 || b.left < -0.5); }).length;
                return { docW: document.documentElement.scrollWidth, winW: innerWidth, overlap: d ? d.getBoundingClientRect().bottom > nav.top + 0.5 : false,
                         listH: l ? l.getBoundingClientRect().height : 999, off: off, navVisible: nav.bottom <= innerHeight + 1 && nav.height > 40 };""")
            ok = r["docW"] <= r["winW"] and not r["overlap"] and not r["off"] and r["listH"] >= 130 and r["navVisible"]
            check(ok, f"{page} layout holds at {w}x{h}" + ("" if ok else f" {r}"))
    drv.set_window_size(430, 900)
    drv.get(BASE + "edf6.html")
    wait_for(drv, ".row")
    all_(drv, ".row__name")[1].click()
    time.sleep(0.5)
    shot = os.environ.get("EDF_SHOT")
    if shot:
        drv.save_screenshot(shot)


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "firefox"
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT)], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    drv = None
    try:
        drv = make_driver(name)
        run(drv, name)
    finally:
        if drv:
            drv.quit()
        server.terminate()
    print("\n%d failed" % len(fails) if fails else "\nAll checks passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
