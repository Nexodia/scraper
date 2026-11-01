"""
One-time, human-in-the-loop Sonepar login (supports the GUEST flow).

Opens a REAL (headful) Chromium at the login page. You complete the flow yourself:

    Guest flow: enter name + email -> pick a delivery location -> solve the reCAPTCHA
    (we never automate/bypass the CAPTCHA).

The script polls the browser storage every 2s and, as soon as it detects the auth
token, dumps localStorage/sessionStorage to data/sonepar_session.json and prints
the values you need (refresh_token, client_id, user_id).

Usage:
    python scripts/sonepar_login.py

Prereq (once):
    python -m playwright install chromium

You can also press Ctrl+C at any time after logging in — the dump is still saved.
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sonepar_session.json"
LOGIN_URL = "https://shop.sonepar.cl/login"
POLL_SECONDS = 2
TIMEOUT_SECONDS = 15 * 60  # 15 minutes


def _find_first(d, keys):
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return None


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def extract_fields(dump):
    """Best-effort extraction of the fields we need from the storage dump."""
    ls = dump.get("localStorage", {})
    ss = dump.get("sessionStorage", {})
    merged = {**ls, **ss}  # sessionStorage wins on collisions (usually fresher)

    auth = _as_dict(merged.get("auth")) or _as_dict(merged.get("auth_token")) or {}
    if not auth:
        for k, v in merged.items():
            if "token" in k.lower() and isinstance(v, str) and "refresh" in v:
                auth = _as_dict(v)
                break

    user = _as_dict(auth.get("user")) or _as_dict(merged.get("user")) or {}
    client = _as_dict(user.get("client")) or _as_dict(merged.get("client")) or {}
    guest = _as_dict(merged.get("guestClient")) or _as_dict(merged.get("guest_client")) or {}

    refresh_token = _find_first(auth, ["refresh_token", "refreshToken"])
    access_token = _find_first(auth, ["access_token", "accessToken"])

    # user_id: the guest flow stores it in the analytics journey queue.
    user_id = _find_first(user, ["userId", "user_id", "id"])
    if not user_id:
        queue = merged.get("analytics_journey_queue")
        try:
            events = json.loads(queue) if isinstance(queue, str) else queue
            for ev in reversed(events) if isinstance(events, list) else []:
                user_id = _find_first(ev, ["user_id", "userId"])
                if user_id:
                    break
        except (json.JSONDecodeError, TypeError):
            pass

    # client_id: guest flow stores it under guestClient.clientId.
    client_id = _find_first(guest, ["clientId", "client_id", "id"])
    if not client_id:
        client_id = _find_first(client, ["id", "client_id", "clientId"])
    if not client_id:
        client_id = _find_first(user, ["clientId", "client_id"]) or _find_first(auth, ["client_id", "clientId"])

    return {
        "refresh_token": refresh_token,
        "access_token": access_token,
        "user_id": user_id,
        "client_id": client_id,
        "user_name": _find_first(user, ["name", "user_name"]) or _find_first(guest, ["name"]),
        "client_name": _find_first(client, ["name", "nickname", "client_name"]) or _find_first(guest, ["clientName"]),
    }


def detect_auth(storage):
    ls = storage.get("localStorage", {})
    ss = storage.get("sessionStorage", {})
    for blob in (ss.get("auth"), ls.get("auth")):
        d = _as_dict(blob)
        if d.get("refresh_token"):
            return True
    # fallback: any key/value hinting at a refresh token
    for k, v in {**ls, **ss}.items():
        if "refresh" in str(k).lower() and v:
            return True
    return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(LOGIN_URL)

        print("==============================================================")
        print("  SONEPAR GUEST LOGIN (one-time)")
        print("--------------------------------------------------------------")
        print("  En la ventana del navegador:")
        print("   1) Elige la opción de invitado ('¿No tienes cuenta?' / Cliente Invitado)")
        print("   2) Ingresa nombre + email")
        print("   3) Selecciona la sucursal/despacho")
        print("   4) Resuelve el reCAPTCHA tú mismo/a (no lo automatizamos)")
        print("   5) Confirma el ingreso como invitado")
        print("--------------------------------------------------------------")
        print("  Detectando token automáticamente (Ctrl+C también guarda)...")
        print("==============================================================")

        dump = None
        detected = False
        start = time.time()
        try:
            while time.time() - start < TIMEOUT_SECONDS:
                ls = page.evaluate("() => ({...localStorage})")
                ss = page.evaluate("() => ({...sessionStorage})")
                if detect_auth({"localStorage": ls, "sessionStorage": ss}):
                    detected = True
                    break
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            print("\n(interrupción manual — guardando lo capturado hasta ahora)")
        finally:
            try:
                ls = page.evaluate("() => ({...localStorage})")
                ss = page.evaluate("() => ({...sessionStorage})")
                cookies = browser.contexts[0].cookies()
                dump = {"localStorage": ls, "sessionStorage": ss, "cookies": cookies}
                OUT.parent.mkdir(exist_ok=True)
                OUT.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                print(f"    (no se pudo volcar storage: {exc})")
            browser.close()

    if not dump:
        print("\nNo se capturó nada. Vuelve a intentarlo y completa el ingreso como invitado.")
        return

    fields = extract_fields(dump)
    print("\nGuardado en", OUT)
    print("--------------------------------------------------------------")
    print("  Valores detectados para pegar en agents/price_extractor/.env:")
    print("--------------------------------------------------------------")
    for key, val in fields.items():
        if val is not None:
            preview = str(val) if len(str(val)) <= 60 else str(val)[:57] + "..."
            print(f"  {key:14s} = {preview}")
    print("--------------------------------------------------------------")
    if not fields["refresh_token"]:
        print("  ATENCIÓN: no se detectó refresh_token. Revisa el JSON y busca")
        print("  una clave 'auth' con 'refresh_token'.")
        return

    # Auto-persist to .env so downstream scripts pick up the token (and it is
    # never lost — refresh tokens rotate on use).
    if fields["client_id"] and fields["user_id"]:
        env_path = ROOT / "agents" / "price_extractor" / ".env"
        txt = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        for key, env_key in [("refresh_token", "SONEPAR_REFRESH_TOKEN"),
                             ("client_id", "SONEPAR_CLIENT_ID"),
                             ("user_id", "SONEPAR_USER_ID")]:
            val = str(fields[key])
            line = f"{env_key}={val}"
            if re.search(rf"^{env_key}=", txt, flags=re.MULTILINE):
                txt = re.sub(rf"^{env_key}=.*$", line, txt, count=1, flags=re.MULTILINE)
            else:
                txt = txt.rstrip("\n") + "\n" + line + "\n"
        env_path.write_text(txt, encoding="utf-8")
        print("  .env actualizado automáticamente con los valores anteriores.")
    else:
        print("  (no se pudo detectar client_id/user_id; pégualos a mano en el .env)")


if __name__ == "__main__":
    main()
