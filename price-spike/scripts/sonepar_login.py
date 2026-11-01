"""
One-time, human-in-the-loop Sonepar login.

Opens a REAL (headful) browser at the Sonepar login page. You log in and solve the
reCAPTCHA yourself (we never automate/bypass it). The script then dumps the browser's
localStorage/sessionStorage to data/sonepar_session.json so we can recover the
refresh_token and client/user ids needed by services/sonepar_auth.py.

Usage:
    python scripts/sonepar_login.py
Prereq (once):
    python -m playwright install chromium
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sonepar_session.json"
LOGIN_URL = "https://shop.sonepar.cl/login"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(LOGIN_URL)
        print("==============================================================")
        print("  Inicia sesión manualmente en la ventana del navegador.")
        print("  (Resuelve el reCAPTCHA tú mismo/a — no lo automatizamos.)")
        print("  Cuando hayas terminado, vuelve aquí y presiona ENTER.")
        print("==============================================================")
        input()

        dump = page.evaluate("() => ({...localStorage})")
        session = page.evaluate("() => ({...sessionStorage})")
        cookies = browser.contexts[0].cookies()

        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(
            {"localStorage": dump, "sessionStorage": session, "cookies": cookies},
            indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"\nGuardado en {OUT}")
        print("\nCandidatos (claves que parecen tokens/ids):")
        for key, value in dump.items():
            if any(hint in key.lower() for hint in ("token", "auth", "client", "user", "refresh", "access")):
                preview = str(value)[:120]
                print(f"  {key} = {preview}")

        browser.close()
    print("\nRevisa data/sonepar_session.json y copia los valores a .env: SONEPAR_REFRESH_TOKEN, SONEPAR_CLIENT_ID, SONEPAR_USER_ID.")


if __name__ == "__main__":
    main()
