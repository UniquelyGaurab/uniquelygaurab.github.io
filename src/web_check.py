"""Headless check of the Minim share pages with links made by the Kotlin encoder (links.tsv).

Serves the site locally (extensionless paths -> .html, like GitHub Pages), opens every link in
Chromium at a phone size, with DecompressionStream and with the inlined inflate fallback, and checks
the page shows exactly what the payload holds (decoded here with zlib), plus both buttons.
"""
import base64, http.server, json, os, sys, threading, zlib
from functools import partial
from playwright.sync_api import sync_playwright

SITE = os.path.expanduser("~/minim-pages")
LINKS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/links.tsv"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/tmp/web-shots"
os.makedirs(SHOTS, exist_ok=True)


class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = super().translate_path(path)
        if not os.path.exists(p) and os.path.exists(p + ".html"):
            return p + ".html"
        return p

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), partial(H, directory=SITE))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8765"


def payload(link):
    frag = link.split("#", 1)[1]
    v, data = frag.split(".", 1)
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return int(v), json.loads(zlib.decompress(raw, -15).decode("utf-8"))


links = [l.rstrip("\n").split("\t") for l in open(LINKS, encoding="utf-8") if l.strip()]
fails, checks = [], 0


def check(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)
        print("FAIL", what)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for mode in ("native", "fallback"):
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, color_scheme="light")
        if mode == "fallback":
            ctx.add_init_script("window.__forceFallback = true;")
        external = []
        ctx.on("request", lambda r: external.append(r.url) if not r.url.startswith(BASE) else None)
        ctx.route("https://music.youtube.com/**", lambda route: route.fulfill(status=200, body="ytm", content_type="text/plain"))
        ctx.route("https://github.com/**", lambda route: route.fulfill(status=200, body="gh", content_type="text/plain"))
        for name, link in links:
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            url = BASE + link.split("uniquelygaurab.github.io", 1)[1]
            page.goto(url)
            page.wait_for_selector("body[data-state]", timeout=10000)
            state = page.get_attribute("body", "data-state")
            tag = f"[{mode}] {name}"
            check(not errors, f"{tag}: page errors {errors}")
            if name == "too_new":
                check(state == "new", f"{tag}: state {state}")
                check("newer Minim" in page.inner_text("#ptitle"), f"{tag}: title")
                check(page.is_visible("#pitch"), f"{tag}: pitch")
            elif name == "broken":
                check(state == "broken", f"{tag}: state {state}")
                check("didn't come through" in page.inner_text("#ptitle"), f"{tag}: title")
                check(page.is_visible("#pitch"), f"{tag}: pitch")
            else:
                v, data = payload(link)
                if name.startswith("song"):
                    check(state == "song", f"{tag}: state {state}")
                    check(page.inner_text("#title") == data["t"], f"{tag}: title {page.inner_text('#title')!r} vs {data['t']!r}")
                    check(page.inner_text("#sub") == data["a"], f"{tag}: artist")
                    if "n" in data:
                        check(page.inner_text("#by") == "Shared by " + data["n"], f"{tag}: by {page.inner_text('#by')!r}")
                    else:
                        check(not page.is_visible("#by"), f"{tag}: by should be hidden")
                    check(page.is_visible("#ytm"), f"{tag}: YT Music button")
                    check(page.get_attribute("#ytm", "href") == "https://music.youtube.com/watch?v=" + data["i"], f"{tag}: ytm href")
                else:
                    check(state == "playlist", f"{tag}: state {state}")
                    check(page.inner_text("#title") == data["l"], f"{tag}: name")
                    n = len(data["s"])
                    check(page.inner_text("#sub") == f"{n} songs", f"{tag}: count {page.inner_text('#sub')}")
                    rows = page.eval_on_selector_all("#songs li", "ls => ls.map(l => [l.querySelector('.n').textContent, l.querySelector('.a').textContent])")
                    check(rows == [[s[1], s[2]] for s in data["s"]], f"{tag}: rows differ")
                    check(page.eval_on_selector_all("#art .tile", "t => t.length") == 4, f"{tag}: collage")
                    check(not page.is_visible("#ytm"), f"{tag}: no YT Music for playlists")
                    check(page.inner_text("#by") == "Shared by " + data["n"], f"{tag}: by")
                check(page.get_attribute("#get", "href") == "https://github.com/UniquelyGaurab/minim/releases/latest", f"{tag}: download href")
                # covers load and the colours follow the cover
                try:
                    if name == "playlist_100": raise Exception("no covers")
                    page.wait_for_function("document.querySelectorAll('#art img.on').length > 0", timeout=8000)
                    page.wait_for_function("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() !== '#fff'", timeout=4000)
                    page.wait_for_timeout(700)
                    covers_ok = True
                except Exception:
                    covers_ok = False
                if name == "playlist_100":
                    # made-up video ids have no thumbnails: every tile falls back to the note
                    page.wait_for_function("[...document.querySelectorAll('#art .tile')].every(t => !t.querySelector('img.on'))", timeout=8000)
                    page.wait_for_timeout(2500)
                    notes = page.eval_on_selector_all("#songs .tile .note", "ns => ns.filter(n => getComputedStyle(n).display !== 'none').length")
                    check(notes == len(data["s"]), f"{tag}: fallback notes {notes}")
                    check(page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()") == "#fff", f"{tag}: plain colours")
                else:
                    check(covers_ok, f"{tag}: cover or colours didn't load")
                if mode == "native" and name in ("song", "playlist", "song_noname", "song_unicode"):
                    page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)
                # the buttons go where they should
                if name == "song":
                    page.click("#ytm")
                    page.wait_for_url("https://music.youtube.com/**", timeout=5000)
                    check(page.url == "https://music.youtube.com/watch?v=" + data["i"], f"{tag}: ytm click {page.url}")
                    page.go_back()
                    page.wait_for_selector("#get")
                page.click("#get")
                page.wait_for_url("https://github.com/**", timeout=5000)
                check(page.url == "https://github.com/UniquelyGaurab/minim/releases/latest", f"{tag}: get click {page.url}")
            if mode == "native" and name in ("broken", "too_new"):
                page.goto(url)
                page.wait_for_selector("body[data-state]")
                page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)
            page.close()
        # missing fragment and the home page
        page = ctx.new_page()
        page.goto(BASE + "/m/p")
        page.wait_for_selector("body[data-state]")
        check(page.get_attribute("body", "data-state") == "broken", f"[{mode}] no fragment")
        page.goto(BASE + "/")
        page.wait_for_selector("body[data-state]")
        check(page.get_attribute("body", "data-state") == "home" and page.is_visible("#pitch") and not page.is_visible("#problem"), f"[{mode}] home")
        page.close()
        bad = [u for u in external if not (u.startswith("https://i.ytimg.com/vi/") or u.startswith("https://music.youtube.com/") or u.startswith("https://github.com/UniquelyGaurab/minim/releases/latest"))]
        check(not bad, f"[{mode}] unexpected requests {bad[:5]}")
        ctx.close()
    # dark mode: the page goes dark with the cover's colours
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    page = ctx.new_page()
    song = dict(links)["song"]
    page.goto(BASE + song.split("uniquelygaurab.github.io", 1)[1])
    page.wait_for_function("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() !== '#fff'", timeout=8000)
    page.wait_for_timeout(700)
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    nums = [int(x) for x in bg[bg.index("(") + 1:bg.index(")")].split(",")[:3]]
    check(sum(nums) < 200, f"dark mode bg {bg}")
    page.screenshot(path=f"{SHOTS}/song-dark.png", full_page=True)
    ctx.close()
    browser.close()
srv.shutdown()
print(f"WEB CHECKS {checks - len(fails)}/{checks} passed")
sys.exit(1 if fails else 0)
