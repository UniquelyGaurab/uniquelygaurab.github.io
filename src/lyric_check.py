"""6.6.0 lyrics card: headless check of the song page with a start-time link (and old links)."""
import sys, time
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://uniquelygaurab.github.io"
SONG = sys.argv[2] if len(sys.argv) > 2 else "/m/s"
LYRIC = "1.q1bKVLJSCnI0yUp1Mq3KtnRU0lEqAYoElxbl5xcBOYlAjl9qRqKCd2J2dmKRgpqCU2ZOYo5CcGJqagpQPg8o755YWpSYBOQUK1mZGloYG-goJStZGekoZQBJQyMDcyMLM1PzWgA"
OLD = "1.q1bKVLJSCnI0yUp1Mq3KtnRU0lEqAYoElxbl5xcBOYlAjl9qRqKCd2J2dmKRgpqCU2ZOYo5CcGJqagpQPg8o755YWpSYpFQLAA"
HOOK = ["ਪੀਤੀ ਵੀ ਨਹੀਂ, ਪੀਤੀ ਵੀ ਨਹੀਂ", "ਹਾਏ, ਪੀਤੀ ਵੀ ਨਹੀਂ, ਫ਼ਿਰ ਵੀ ਇਕ ਸੁਰੂਰ ਜਿਹਾ ਏ"]
ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL", name, extra)

with sync_playwright() as p:
    b = p.chromium.launch()
    def page(frag, block_lrclib=False, wait_quote=True):
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        if block_lrclib: pg.route("https://lrclib.net/**", lambda r: r.abort())
        pg.goto(f"{BASE}{SONG}#{frag}", timeout=30000)
        pg.wait_for_function("document.body.getAttribute('data-state')", timeout=15000)
        if wait_quote:
            try: pg.wait_for_function("document.body.getAttribute('data-quote')", timeout=20000)
            except Exception: pass
        return pg, errors

    pg, errs = page(LYRIC)
    st = pg.evaluate("""() => ({state: document.body.dataset.state, quote: document.body.dataset.quote,
        title: document.getElementById('title').textContent, starts: document.getElementById('starts').textContent,
        startsHidden: document.getElementById('starts').hidden, by: document.getElementById('by').textContent,
        lines: Array.from(document.querySelectorAll('#quote span')).map(s => s.textContent),
        ytm: document.getElementById('ytm').href})""")
    print("lyric link:", st)
    check("state song", st["state"] == "song")
    check("title", st["title"] == "Suroor")
    check("starts shown", not st["startsHidden"] and st["starts"] == "Starts at 0:51", st["starts"])
    check("shared by", st["by"] == "Shared by Gaurab")
    check("quote shown", st["quote"] == "shown", st["quote"])
    check("quote lines", st["lines"] == HOOK, st["lines"])
    check("ytm plain", st["ytm"] == "https://music.youtube.com/watch?v=RA4jeB5zk9A", st["ytm"])
    check("no js errors", not errs, errs)
    pg.screenshot(path="/tmp/lyric-page.png", full_page=True)
    pg.close()

    pg, errs = page(LYRIC, block_lrclib=True)
    st = pg.evaluate("() => ({state: document.body.dataset.state, quote: document.body.dataset.quote, qh: document.getElementById('quote').hidden, starts: document.getElementById('starts').textContent})")
    print("lrclib blocked:", st)
    check("blocked: still song", st["state"] == "song")
    check("blocked: quote hidden", st["qh"] and st["quote"] == "none")
    check("blocked: starts", st["starts"] == "Starts at 0:51")
    check("blocked: no js errors", not errs, errs)
    pg.close()

    pg, errs = page(OLD, wait_quote=False)
    time.sleep(2)
    st = pg.evaluate("() => ({state: document.body.dataset.state, quote: document.body.dataset.quote, sh: document.getElementById('starts').hidden, qh: document.getElementById('quote').hidden, title: document.getElementById('title').textContent})")
    print("old link:", st)
    check("old: song", st["state"] == "song" and st["title"] == "Suroor")
    check("old: no start, no quote", st["sh"] and st["qh"] and st["quote"] is None)
    check("old: no js errors", not errs, errs)
    pg.close()
    b.close()
print(f"{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
