"""Headless-Chrome screenshot of CineSip pages at phone width, driven over CDP.

The browser_exec tool was unavailable, so this drives Chrome directly:
launch with --remote-debugging-port, talk raw CDP over the websocket.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

from websockets.sync.client import connect

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
OUT = os.path.join(os.environ["LOCALAPPDATA"], "Temp", "cinesip_shots")
os.makedirs(OUT, exist_ok=True)

PAGES = [
    ("game", "http://127.0.0.1:5199/game/JQUNH6"),
    ("lobby", "http://127.0.0.1:5199/lobby/JQUNH6"),
    ("results", "http://127.0.0.1:5199/results/JQUNH6"),
    ("home", "http://127.0.0.1:5199/"),
]

PLAYER = json.dumps({"state": {"player": {"id": 1, "name": "Daniel", "isHost": True}}, "version": 0})


def main() -> None:
    proc = subprocess.Popen(
        [CHROME, f"--remote-debugging-port={PORT}", "--headless=new",
         "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         f"--user-data-dir={OUT}/profile", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            sys.exit("chrome never came up")

        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")

        with connect(ws_url, max_size=80 * 1024 * 1024) as ws:
            n = [0]

            def cmd(method, **params):
                n[0] += 1
                ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
                while True:
                    msg = json.loads(ws.recv())
                    if msg.get("id") == n[0]:
                        if "error" in msg:
                            raise RuntimeError(f"{method}: {msg['error']}")
                        return msg.get("result", {})

            cmd("Page.enable")
            cmd("Runtime.enable")
            cmd("Emulation.setDeviceMetricsOverride",
                width=390, height=844, deviceScaleFactor=2, mobile=True)

            for name, url in PAGES:
                cmd("Page.navigate", url=url)
                time.sleep(2.0)
                cmd("Runtime.evaluate",
                    expression=f"localStorage.setItem('cinesip-player', {PLAYER!r})")
                cmd("Page.navigate", url=url)
                time.sleep(3.5)
                text = cmd("Runtime.evaluate",
                           expression="document.body.innerText.slice(0,220)",
                           returnByValue=True)["result"].get("value", "")
                shot = cmd("Page.captureScreenshot", format="png", captureBeyondViewport=True)
                path = os.path.join(OUT, f"{name}.png")
                with open(path, "wb") as f:
                    f.write(base64.b64decode(shot["data"]))
                print(f"--- {name} -> {path}")
                print(str(text).replace("\n", " | ")[:220])

            # Geometry probe: the .sip circle must actually be 46x46.
            probe = cmd("Page.navigate", url="http://127.0.0.1:5199/game/JQUNH6")
            time.sleep(3.0)
            geo = cmd("Runtime.evaluate", returnByValue=True, expression="""
                (() => {
                  const out = {};
                  const sip = document.querySelector('.sip');
                  if (sip) { const r = sip.getBoundingClientRect();
                    const cs = getComputedStyle(sip);
                    out.sip = {w: +r.width.toFixed(1), h: +r.height.toFixed(1),
                               display: cs.display, align: cs.alignItems}; }
                  const row = document.querySelector('.rule-row');
                  if (row) { const r = row.getBoundingClientRect();
                    out.row = {w: +r.width.toFixed(1), h: +r.height.toFixed(1)}; }
                  const head = document.querySelector('.team-head');
                  if (head) out.head = {align: getComputedStyle(head).alignItems};
                  out.overflowX = document.documentElement.scrollWidth > window.innerWidth;
                  out.scrollWidth = document.documentElement.scrollWidth;
                  return JSON.stringify(out);
                })()
            """)["result"].get("value")
            print("\nGEOMETRY:", geo)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
