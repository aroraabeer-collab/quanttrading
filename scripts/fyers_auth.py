"""Refresh the daily Fyers access token and write it to .env.

Fyers tokens expire each day. Run this before a trading/data session:

    uv run scripts/fyers_auth.py

It prints the login URL, you authorize in the browser, paste back the
redirect URL, and the new FYERS_ACCESS_TOKEN is written to .env.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import PROJECT_ROOT, get_settings


def _update_env(token: str) -> None:
    env = PROJECT_ROOT / ".env"
    lines = env.read_text().splitlines() if env.exists() else []
    out, found = [], False
    for line in lines:
        if line.startswith("FYERS_ACCESS_TOKEN="):
            out.append(f"FYERS_ACCESS_TOKEN={token}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"FYERS_ACCESS_TOKEN={token}")
    env.write_text("\n".join(out) + "\n")
    print(f"Wrote FYERS_ACCESS_TOKEN to {env}")


def main() -> None:
    from fyers_apiv3 import fyersModel

    s = get_settings()
    if not s.fyers_app_id or not s.fyers_secret_id:
        raise SystemExit("Set FYERS_APP_ID and FYERS_SECRET_ID in .env first.")

    session = fyersModel.SessionModel(
        client_id=s.fyers_app_id,
        secret_key=s.fyers_secret_id,
        redirect_uri=s.fyers_redirect_uri,
        response_type="code",
        grant_type="authorization_code",
    )
    print("1) Open this URL and log in:\n")
    print("   " + session.generate_authcode() + "\n")
    redirect = input("2) Paste the full redirect URL you land on: ").strip()

    auth_code = parse_qs(urlparse(redirect).query).get("auth_code", [None])[0]
    if not auth_code:
        raise SystemExit("Could not find auth_code in the pasted URL.")

    session.set_token(auth_code)
    resp = session.generate_token()
    token = resp.get("access_token")
    if not token:
        raise SystemExit(f"Token generation failed: {resp}")
    _update_env(token)
    print("Done — token valid until end of day (IST).")


if __name__ == "__main__":
    main()
