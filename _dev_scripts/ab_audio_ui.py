"""Browser A/B chooser for candidate-duplicate audio pairs.

Why a browser and not the terminal: choosing between two takes needs replay,
scrubbing, and going back — the terminal version (`ab_audio.py --manifest`) can only
play forward, and the `--auto` mode can't take input at all when a session with no
stdin is driving it.

Audio is served over localhost rather than opened as file:// so seeking works
consistently across browsers. Stdlib only (http.server), matching frame_stream.py.

Usage
    uv run _dev_scripts/ab_audio_ui.py --manifest _audio_backup/chuo_pa_ab.json
    uv run _dev_scripts/ab_audio_ui.py --manifest ... --port 8770 --no-open

Choices are written to <manifest>.choices.json on every click, so closing the tab
never loses work. Reopening restores what was already decided.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

REPO_ROOT = Path(__file__).resolve().parent.parent

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A/B audio chooser</title>
<style>
  :root {
    --bg:#12151a; --card:#1b1f27; --edge:#2b313c; --ink:#e8edf4; --dim:#98a3b3;
    --a:#4a9eff; --b:#ffb454; --keep:#39d98a; --both:#a78bfa;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f4f6f9; --card:#fff; --edge:#dde3ec; --ink:#1a1f27; --dim:#5c6675; }
  }
  * { box-sizing:border-box; }
  body { margin:0; padding:24px; background:var(--bg); color:var(--ink);
         font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { max-width:900px; margin:0 auto 20px; }
  h1 { font-size:20px; margin:0 0 4px; font-weight:650; }
  .sub { color:var(--dim); font-size:13px; }
  .bar { max-width:900px; margin:0 auto 20px; height:6px; background:var(--edge);
         border-radius:3px; overflow:hidden; }
  .bar i { display:block; height:100%; background:var(--keep); width:0; transition:width .25s; }
  .card { max-width:900px; margin:0 auto 14px; background:var(--card);
          border:1px solid var(--edge); border-radius:10px; padding:16px 18px; }
  .card.done { opacity:.55; }
  .lbl { font-weight:600; margin-bottom:2px; }
  .ctrl { font-size:12px; color:var(--dim); margin-bottom:12px; }
  .row { display:grid; grid-template-columns:28px 1fr; gap:10px; align-items:center;
         margin-bottom:8px; }
  .tag { font-weight:700; font-size:13px; text-align:center; border-radius:5px; padding:3px 0; }
  .tag.a { background:color-mix(in srgb,var(--a) 22%,transparent); color:var(--a); }
  .tag.b { background:color-mix(in srgb,var(--b) 22%,transparent); color:var(--b); }
  audio { width:100%; height:34px; }
  .path { font:11px/1.4 ui-monospace,Menlo,Consolas,monospace; color:var(--dim);
          margin:-4px 0 8px 38px; word-break:break-all; }
  .choices { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
  button { flex:1; min-width:120px; padding:9px 12px; border-radius:7px; cursor:pointer;
           border:1px solid var(--edge); background:transparent; color:var(--ink);
           font:inherit; font-weight:560; transition:.12s; }
  button:hover { border-color:var(--dim); }
  button.sel { color:#08121f; border-color:transparent; }
  button[data-c="a"].sel { background:var(--a); }
  button[data-c="b"].sel { background:var(--b); }
  button[data-c="both"].sel { background:var(--both); }
  footer { max-width:900px; margin:24px auto 0; color:var(--dim); font-size:13px; }
  code { background:var(--edge); padding:1px 5px; border-radius:4px; font-size:12px; }
</style></head><body>
<header>
  <h1>A/B audio chooser</h1>
  <div class="sub" id="sub"></div>
</header>
<div class="bar"><i id="prog"></i></div>
<div id="list"></div>
<footer>
  Saved to <code id="out"></code> on every click. Keyboard: <code>1</code> keep A ·
  <code>2</code> keep B · <code>3</code> keep both, applied to the last card you played.
</footer>
<script>
const PAIRS = __PAIRS__;
let choices = __CHOICES__;
let lastCard = 0;

function render() {
  const list = document.getElementById('list');
  list.innerHTML = '';
  PAIRS.forEach((p, i) => {
    const c = document.createElement('div');
    c.className = 'card' + (choices[p.label] ? ' done' : '');
    c.innerHTML = `
      <div class="lbl">${p.label}</div>
      <div class="ctrl">pair ${i + 1} of ${PAIRS.length}</div>
      <div class="row"><div class="tag a">A</div>
        <audio controls preload="none" src="/audio/${encodeURI(p.a)}"></audio></div>
      <div class="path">${p.a}</div>
      <div class="row"><div class="tag b">B</div>
        <audio controls preload="none" src="/audio/${encodeURI(p.b)}"></audio></div>
      <div class="path">${p.b}</div>
      <div class="choices">
        <button data-c="a">Keep A</button>
        <button data-c="b">Keep B</button>
        <button data-c="both">Keep both</button>
      </div>`;
    c.querySelectorAll('audio').forEach(el => el.addEventListener('play', () => {
      lastCard = i;
      document.querySelectorAll('audio').forEach(o => { if (o !== el) o.pause(); });
    }));
    c.querySelectorAll('button').forEach(btn => {
      if (choices[p.label] === btn.dataset.c) btn.classList.add('sel');
      btn.addEventListener('click', () => choose(i, btn.dataset.c));
    });
    list.appendChild(c);
  });
  const n = Object.keys(choices).length;
  document.getElementById('prog').style.width = (n / PAIRS.length * 100) + '%';
  document.getElementById('sub').textContent =
    `${n} of ${PAIRS.length} decided` + (n === PAIRS.length ? ' — all done' : '');
}

function choose(i, c) {
  choices[PAIRS[i].label] = c;
  fetch('/choice', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({label: PAIRS[i].label, choice: c})
  });
  render();
}

addEventListener('keydown', e => {
  const k = {'1': 'a', '2': 'b', '3': 'both'}[e.key];
  if (k) choose(lastCard, k);
});

render();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *a, pairs=None, out_path=None, **kw):
        self.pairs = pairs
        self.out_path = out_path
        super().__init__(*a, **kw)

    def log_message(self, *a):  # quiet — the console is for the operator, not the server
        pass

    def _send(self, code, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            choices = {}
            if self.out_path.exists():
                choices = json.loads(self.out_path.read_text(encoding="utf-8"))
            html = (
                PAGE.replace("__PAIRS__", json.dumps(self.pairs, ensure_ascii=False))
                .replace("__CHOICES__", json.dumps(choices, ensure_ascii=False))
                .replace('id="out"></code>', f'id="out">{self.out_path}</code>')
            )
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path.startswith("/audio/"):
            rel = path[len("/audio/") :]
            target = (REPO_ROOT / rel).resolve()
            # Never serve outside the repo, whatever the URL claims.
            if REPO_ROOT not in target.parents or not target.is_file():
                self._send(404, b"not found", "text/plain")
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype, {"Accept-Ranges": "none"})
            return

        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if urlparse(self.path).path != "/choice":
            self._send(404, b"not found", "text/plain")
            return
        n = int(self.headers.get("Content-Length", 0))
        msg = json.loads(self.rfile.read(n).decode("utf-8"))
        choices = {}
        if self.out_path.exists():
            choices = json.loads(self.out_path.read_text(encoding="utf-8"))
        choices[msg["label"]] = msg["choice"]
        self.out_path.write_text(json.dumps(choices, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {msg['choice']:<5} {msg['label']}  ({len(choices)}/{len(self.pairs)})", flush=True)
        self._send(200, b"{}", "application/json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, required=True, help="JSON list of {label, a, b} pairs")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-open", action="store_true", help="don't launch a browser")
    args = ap.parse_args()

    pairs = json.loads(args.manifest.read_text(encoding="utf-8"))
    out_path = args.manifest.with_suffix(".choices.json")

    missing = [p["label"] for p in pairs if not (REPO_ROOT / p["a"]).is_file() or not (REPO_ROOT / p["b"]).is_file()]
    if missing:
        print("missing files for: " + ", ".join(missing))
        return 1

    handler = partial(Handler, pairs=pairs, out_path=out_path)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"{len(pairs)} pairs  ->  {url}")
    print(f"choices saved to {out_path}\nCtrl-C to stop.\n")
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
