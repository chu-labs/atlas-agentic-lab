#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyjwt[crypto]>=2.8"]
# ///
"""Print an installation access token for the lab's GitHub App.

Reads ~/.config/atlas-lab/github-app.json (from github_app_manifest.py).
With --check, lists installations instead and writes installation_id back into the file.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

import jwt

CFG = Path.home() / ".config" / "atlas-lab" / "github-app.json"


def app_jwt(cfg: dict) -> str:
    now = int(time.time())
    return jwt.encode({"iat": now - 30, "exp": now + 540, "iss": str(cfg["id"])}, cfg["pem"], algorithm="RS256")


def api(path: str, token: str, method: str = "GET"):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "atlas-lab"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    cfg = json.loads(CFG.read_text())
    tok = app_jwt(cfg)
    if "--check" in sys.argv:
        inst = api("/app/installations", tok)
        for i in inst:
            print(f"installation {i['id']} on {i['account']['login']} ({i['repository_selection']} repos)")
            if i["account"]["login"] == "chu-labs":
                cfg["installation_id"] = i["id"]
                CFG.write_text(json.dumps(cfg, indent=2))
        if not inst:
            print("not installed anywhere yet")
        return
    iid = cfg.get("installation_id")
    if not iid:
        sys.exit("no installation_id; run with --check after installing the app")
    print(api(f"/app/installations/{iid}/access_tokens", tok, "POST")["token"])


if __name__ == "__main__":
    main()
