"""
Canboso "Buyer API" client (v1.2.0).

Only three public endpoints exist, all keyed by a single buyer `key`:
    GET  /api/telegram-buyer/products?key=...
    GET  /api/telegram-buyer/balance?key=...
    POST /api/telegram-buyer/purchase   {key, product_id, quantity, ...}

Design notes / hard constraints from the spec:
  * Auth is just the buyer key. Keep it server-side only, never expose it.
  * Wallet is prepaid (VND or USD depending on the key). A purchase deducts
    from the wallet; there is no per-request payment.
  * Purchase is SYNCHRONOUS and returns delivered credentials inline. There is
    NO order-lookup endpoint and NO idempotency key. Therefore a network
    timeout is AMBIGUOUS: the purchase may or may not have gone through. We
    must never blindly retry the same purchase on a timeout, or we risk a
    double charge. This client surfaces that difference by raising
    CanbosoNetworkError (ambiguous) vs the definitive HTTP errors below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_BASE_URL = "https://canboso.com"
DEFAULT_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CanbosoError(Exception):
    """Base class for all Canboso client errors."""

    def __init__(self, message: str, *, status: int | None = None,
                 payload: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload or {}


class CanbosoAuthError(CanbosoError):
    """401 — invalid API key. This bot cannot be used; skip it."""


class CanbosoBadRequest(CanbosoError):
    """400 — invalid request, most importantly *insufficient wallet balance*.

    A definitive 'this purchase did not happen' response, so it is SAFE to
    fall back to the next bot.
    """

    @property
    def is_insufficient_balance(self) -> bool:
        msg = (self.message or "").lower()
        return "balance" in msg and (
            "not enough" in msg or "insufficient" in msg
        )


class CanbosoNotFound(CanbosoError):
    """404 — product not found on this bot. Safe to fall back."""


class CanbosoInventoryError(CanbosoError):
    """409 — inventory not enough on this bot. Safe to fall back."""


class CanbosoNetworkError(CanbosoError):
    """Timeout / connection error / non-JSON response.

    AMBIGUOUS outcome for a purchase — do NOT assume it failed and do NOT
    auto-retry the same purchase. The caller must reconcile manually.
    """


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

@dataclass
class CanbosoClient:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout: int = DEFAULT_TIMEOUT

    def __post_init__(self):
        self._session = requests.Session()
        # A browser-like User-Agent avoids some WAF/Cloudflare 403/404 pages
        # that block plain server-to-server requests.
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })
        self.base_url = self.base_url.rstrip("/")

    # -- low level ---------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _raise_for_status(self, resp: requests.Response) -> dict[str, Any]:
        """Parse JSON and map HTTP status codes to typed exceptions."""
        try:
            data = resp.json()
        except ValueError:
            # Not JSON — capture a snippet of the body so we can see what the
            # server actually returned (Cloudflare page, Next.js 404, etc.).
            snippet = " ".join((resp.text or "").split())[:200]
            raise CanbosoNetworkError(
                f"Non-JSON response (HTTP {resp.status_code}): {snippet}",
                status=resp.status_code,
            )

        if resp.status_code == 200:
            return data

        message = data.get("message") or f"HTTP {resp.status_code}"
        if resp.status_code == 401:
            raise CanbosoAuthError(message, status=401, payload=data)
        if resp.status_code == 400:
            raise CanbosoBadRequest(message, status=400, payload=data)
        if resp.status_code == 404:
            raise CanbosoNotFound(message, status=404, payload=data)
        if resp.status_code == 409:
            raise CanbosoInventoryError(message, status=409, payload=data)
        # anything else (5xx etc.) — ambiguous, treat as network-ish
        raise CanbosoNetworkError(message, status=resp.status_code, payload=data)

    # -- endpoints ---------------------------------------------------------

    def list_products(self) -> dict[str, Any]:
        """GET /products — returns the full response dict (products + wallet meta)."""
        try:
            resp = self._session.get(
                self._url("/api/telegram-buyer/products"),
                params={"key": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise CanbosoNetworkError(f"Request failed: {exc}") from exc
        return self._raise_for_status(resp)

    def get_balance(self) -> dict[str, Any]:
        """GET /balance — wallet balance for this key."""
        try:
            resp = self._session.get(
                self._url("/api/telegram-buyer/balance"),
                params={"key": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise CanbosoNetworkError(f"Request failed: {exc}") from exc
        return self._raise_for_status(resp)

    def purchase(
        self,
        product_id: str,
        quantity: int = 1,
        *,
        customer_email: str | None = None,
        slot_months: int | None = None,
    ) -> dict[str, Any]:
        """POST /purchase.

        For the ChatGPT Business Slot product (product_id == 'slot_chatgpt_business')
        pass customer_email and slot_months instead of quantity.

        Raises CanbosoNetworkError on an AMBIGUOUS outcome (timeout / connection
        loss / 5xx). On that error the caller must assume the charge *might* have
        happened and reconcile — never silently retry the same bot.
        """
        body: dict[str, Any] = {"key": self.api_key, "product_id": product_id}
        if slot_months is not None:
            body["slot_months"] = slot_months
        if customer_email is not None:
            body["customer_email"] = customer_email
        if quantity is not None and slot_months is None:
            body["quantity"] = quantity

        try:
            resp = self._session.post(
                self._url("/api/telegram-buyer/purchase"),
                json=body,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise CanbosoNetworkError(
                "Purchase timed out — outcome UNKNOWN, do not retry blindly"
            ) from exc
        except requests.RequestException as exc:
            raise CanbosoNetworkError(f"Purchase request failed: {exc}") from exc
        return self._raise_for_status(resp)
