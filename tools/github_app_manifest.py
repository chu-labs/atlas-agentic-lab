#!/usr/bin/env python3
"""Create the atlas-agents GitHub App via the manifest flow.

Run it, open http://localhost:8765 in a browser, click "Create GitHub App" on
GitHub, and the callback lands back here. Credentials are written to
~/.config/atlas-lab/github-app.json (mode 600) and never into the repo.
Then install the app on the org using the printed URL.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ORG = os.environ.get("ATLAS_GH_ORG", "chu-labs")
PORT = int(os.environ.get("ATLAS_MANIFEST_PORT", "8765"))
OUT = Path.home() / ".config" / "atlas-lab" / "github-app.json"
STATE = secrets.token_urlsafe(16)

MANIFEST = {
    "name": "atlas-agents",
    "url": f"https://github.com/{ORG}",
    "description": "Agent fleet identity for the ATLAS Agentic SDLC Demo Lab. Ephemeral.",
    "public": False,
    "redirect_url": f"http://localhost:{PORT}/callback",
    "hook_attributes": {"url": "https://example.invalid/unused", "active": False},
    "default_permissions": {
        "contents": "write",
        "pull_requests": "write",
        "issues": "write",
        "actions": "write",
        "workflows": "write",
        "checks": "read",
        "metadata": "read",
        "deployments": "write",
        "administration": "write",
    },
    "default_events": [],
}

FORM = f"""<!doctype html><meta charset=utf-8><title>atlas-agents manifest</title>
<body style="font:18px system-ui;max-width:40em;margin:4em auto">
<h1>Create the <code>atlas-agents</code> GitHub App</h1>
<p>Submitting sends the manifest below to GitHub for org <b>{ORG}</b>. On GitHub, click
<b>Create GitHub App</b>. You will be redirected back here.</p>
<form method="post" action="https://github.com/organizations/{ORG}/settings/apps/new?state={STATE}">
<input type="hidden" name="manifest" id="manifest">
<button style="font-size:20px;padding:.5em 1em">Continue to GitHub</button>
</form>
<pre style="font-size:13px;background:#eee;padding:1em;overflow:auto">{json.dumps(MANIFEST, indent=2)}</pre>
<script>document.getElementById('manifest').value = {json.dumps(json.dumps(MANIFEST))};</script>
</body>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, body: str, code: int = 200):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/callback"):
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            if q.get("state", [""])[0] != STATE:
                return self._send("<h1>Bad state</h1>", 400)
            code = q.get("code", [""])[0]
            req = urllib.request.Request(
                f"https://api.github.com/app-manifests/{code}/conversions",
                method="POST",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "atlas-lab"},
            )
            with urllib.request.urlopen(req) as r:
                data = json.load(r)
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(data, indent=2))
            OUT.chmod(0o600)
            install = f"https://github.com/apps/{data['slug']}/installations/new"
            print(f"\nApp created: id={data['id']} slug={data['slug']}\nSaved: {OUT}\nInstall it on {ORG}: {install}\n", flush=True)
            self._send(
                f"<body style='font:18px system-ui;max-width:40em;margin:4em auto'><h1>Done</h1>"
                f"<p>App <b>{data['slug']}</b> (id {data['id']}) created. Credentials saved locally.</p>"
                f"<p><a href='{install}' style='font-size:22px'>Now install it on {ORG} →</a></p></body>"
            )
            # stop after success
            import threading

            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._send(FORM)


def main():
    if OUT.exists() and "--force" not in sys.argv:
        print(f"{OUT} already exists; pass --force to create another app.")
        return
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Open http://localhost:{PORT} in your browser.", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
