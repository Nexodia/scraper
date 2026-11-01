"""
Sonepar (Checkbuy) authentication + API client.

Findings from reverse-engineering the SPA bundle (public info embedded in JS):
  * API base:  https://api-shop.sonepar.cl/
  * OAuth2 token endpoint: POST /oauth/token  (HTTP Basic = public client credentials)
      - grant_type=password        -> needs a Google reCAPTCHA token (NOT automated here)
      - grant_type=refresh_token   -> uses the app's own refresh flow (no interactive CAPTCHA)
      - grant_type=guest_credentials -> anonymous "guest" token
  * Authenticated price endpoints:
      GET /products/client/details?client=<clientId>&product=<productId>&searchIdSonepar=<...>
      GET /products/pricing?client=<clientId>&user=<userId>&products=<id1;id2;...>
  * Anonymous /products/details returns metadata but an EMPTY "price":{}.

Compliance: we do NOT solve/bypass CAPTCHAs. The initial login is done ONCE by a human
in a real browser (scripts/sonepar_login.py), which stores the refresh_token locally.
This module then mints access tokens via the standard refresh grant.
"""
import os
import re
from pathlib import Path

import httpx

API_BASE = "https://api-shop.sonepar.cl/"
OAUTH_BASIC = (
    "NzI0NjE0ZjBjODU4ZmQ1ZDNmNDYwZjYxZTRlNWE3YzM6"
    "ZTBjMmU4YjE4MmRiZjQ5Nzg1ZDY4MjU1Zjc4YWQzOTY2Nzg1OTM1MzFlMGI4Y2Y0YThhZTllZDg3YTc2NTM2OA=="
)
# The bundle's hardcoded value the app sends for the refresh grant (not a CAPTCHA solution).
NO_RECAPTCHA = "ZGVzZW52b2x2aWRvIHBvciB2aXRhbw=="
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36 "
    "price-spike/0.1 (university research; polite, rate-limited)"
)


def oauth_refresh(refresh_token: str) -> dict:
    """Exchange a refresh_token for a fresh access_token (standard OAuth2 refresh grant)."""
    data = {
        "refresh_token": refresh_token,
        "reCaptchaVerify": NO_RECAPTCHA,
        "grant_type": "refresh_token",
    }
    headers = {
        "Authorization": f"Basic {OAUTH_BASIC}",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }
    r = httpx.post(API_BASE + "oauth/token", data=data, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def client_details(client_id: str, product_id: str, access_token: str) -> dict:
    """Authenticated product details (includes the client-specific price)."""
    params = {"client": client_id, "product": product_id, "searchIdSonepar": ""}
    headers = {"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT}
    r = httpx.get(API_BASE + "products/client/details", params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def pricing(client_id: str, user_id: str, product_ids: list[str], access_token: str) -> dict:
    """Batch pricing for a set of product ids (semicolon-separated)."""
    params = {"client": client_id, "user": user_id, "products": ";".join(product_ids)}
    headers = {"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT}
    r = httpx.get(API_BASE + "products/pricing", params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


class SoneparClient:
    """Small stateful client: mints a token once and reuses it for product calls."""

    def __init__(self, refresh_token: str, client_id: str, user_id: str | None = None,
                 env_path: str | None = None):
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.user_id = user_id
        self.env_path = env_path
        self._access_token: str | None = None

    def ensure_token(self) -> str:
        if not self._access_token:
            token = oauth_refresh(self.refresh_token)
            self._access_token = token["access_token"]
            # Refresh tokens ROTATE on every use; persist the new one immediately
            # so it is never lost (the old token becomes invalid after refresh).
            if token.get("refresh_token"):
                self.refresh_token = token["refresh_token"]
                self._persist_refresh()
        return self._access_token

    def _persist_refresh(self) -> None:
        if not self.env_path:
            return
        env_file = Path(self.env_path)
        if not env_file.exists():
            return
        txt = env_file.read_text(encoding="utf-8")
        new_txt = re.sub(r"^SONEPAR_REFRESH_TOKEN=.*$",
                         f"SONEPAR_REFRESH_TOKEN={self.refresh_token}",
                         txt, count=1, flags=re.MULTILINE)
        if new_txt != txt:
            env_file.write_text(new_txt, encoding="utf-8")

    def get_product(self, product_id: str) -> dict:
        tok = self.ensure_token()
        return client_details(self.client_id, product_id, tok)

    def get_prices(self, product_ids: list[str]) -> dict:
        if not self.user_id:
            raise ValueError("user_id is required for pricing; set it from the auth/login session")
        tok = self.ensure_token()
        return pricing(self.client_id, self.user_id, product_ids, tok)
