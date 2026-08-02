"""SSON Digital Works reseller API adapter.

Normalizes SSON responses to the internal Canboso-shaped supplier contract so
catalogue syncing and fulfilment remain provider-independent.
"""

from __future__ import annotations

from typing import Any

import requests

from .canboso import (
    CanbosoAuthError,
    CanbosoBadRequest,
    CanbosoInventoryError,
    CanbosoNetworkError,
    CanbosoNotFound,
)


DEFAULT_BASE_URL = "https://ssondigitalworks.online/api/reseller"


def _first(mapping: dict, *names, default=None):
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    return default


class SsonDigitalClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.api_key = (api_key or "").strip()
        supplied_url = (base_url or "").strip().rstrip("/")
        if not supplied_url or "canboso.com" in supplied_url:
            supplied_url = DEFAULT_BASE_URL
        self.base_url = supplied_url
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Toolsology-Supplier-Sync/1.0",
        })

    def _request(self, action: str, *, body: dict | None = None) -> Any:
        try:
            if body is None:
                response = self._session.get(
                    self.base_url, params={"action": action}, timeout=self.timeout
                )
            else:
                response = self._session.post(
                    self.base_url, params={"action": action}, json=body,
                    timeout=self.timeout,
                )
        except requests.Timeout as exc:
            raise CanbosoNetworkError("SSON request timed out; outcome may be unknown.") from exc
        except requests.RequestException as exc:
            raise CanbosoNetworkError(f"SSON request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise CanbosoNetworkError(
                f"SSON returned a non-JSON response (HTTP {response.status_code})."
            ) from exc

        message = ""
        if isinstance(payload, dict):
            message = str(_first(payload, "detail", "message", "error", default="") or "")
        if response.status_code in (401, 403):
            raise CanbosoAuthError(message or "Invalid SSON API key.", status=response.status_code)
        if response.status_code == 404:
            raise CanbosoNotFound(message or "SSON product not found.", status=404)
        if response.status_code == 409:
            raise CanbosoInventoryError(message or "SSON inventory is unavailable.", status=409)
        if response.status_code in (400, 422):
            raise CanbosoBadRequest(message or "Invalid SSON request.", status=response.status_code)
        if response.status_code >= 429:
            raise CanbosoNetworkError(message or f"SSON HTTP {response.status_code}.", status=response.status_code)
        if isinstance(payload, dict) and payload.get("success") is False:
            raise CanbosoBadRequest(message or "SSON rejected the request.", payload=payload)
        return payload

    @staticmethod
    def _data(payload):
        if not isinstance(payload, dict):
            return payload
        data = payload.get("data")
        return data if data is not None else payload

    def list_products(self) -> dict:
        payload = self._request("products")
        data = self._data(payload)
        if isinstance(data, dict):
            products = _first(data, "products", "items", "catalog", default=[])
        else:
            products = data
        if not isinstance(products, list):
            raise CanbosoNetworkError("SSON products response has an invalid format.")

        normalized = []
        for item in products:
            if not isinstance(item, dict):
                continue
            product_id = _first(item, "product_id", "id", "_id")
            if product_id is None:
                continue
            price = _first(
                item, "wholesale_price", "api_price", "reseller_price", "price", "cost"
            )
            stock = _first(item, "available", "stock", "stock_quantity", "quantity")
            normalized.append({
                "_id": str(product_id),
                "product_name": str(_first(item, "product_name", "name", "title", default="")),
                "product_name_raw": str(_first(item, "product_name_raw", "name", "title", default="")),
                "walletCurrency": str(_first(item, "currency", "wallet_currency", default="USDT")),
                "walletPricing": price,
                "usdPricing": price,
                "stats": {"available": stock},
                "isSlotProduct": bool(_first(item, "is_slot", "isSlotProduct", default=False)),
                "slotDurations": _first(item, "slot_durations", "slotDurations", default=[]) or [],
                "providerRaw": item,
            })
        return {"walletCurrency": "USDT", "products": normalized, "providerRaw": payload}

    def get_balance(self) -> dict:
        payload = self._request("balance")
        data = self._data(payload)
        if not isinstance(data, dict):
            raise CanbosoNetworkError("SSON balance response has an invalid format.")
        balance = _first(data, "balance", "api_balance", "wallet_balance", "amount")
        currency = str(_first(data, "currency", "wallet_currency", default="USDT"))
        return {
            "balance": balance,
            "balanceText": f"{balance} {currency}" if balance is not None else "",
            "walletCurrency": currency,
        }

    def purchase(
        self, product_id: str, quantity: int = 1, *, idempotency_key: str,
        customer_email: str | None = None, slot_months: int | None = None,
    ) -> dict:
        body = {
            "product_id": str(product_id),
            "quantity": int(quantity or 1),
            "external_order_id": str(idempotency_key),
        }
        payload = self._request("order", body=body)
        data = self._data(payload)
        if not isinstance(data, dict):
            raise CanbosoNetworkError("SSON order response has an invalid format.")
        accounts = _first(
            data, "deliveredAccounts", "delivered_accounts", "accounts",
            "credentials", "items", default=[],
        ) or []
        if isinstance(accounts, dict):
            accounts = [accounts]
        normalized_accounts = []
        for account in accounts if isinstance(accounts, list) else []:
            if not isinstance(account, dict):
                continue
            normalized_accounts.append({
                "user": str(_first(account, "user", "username", "email", "account", default="")),
                "password": str(_first(account, "password", "pass", default="")),
                "verifyEmail": str(_first(
                    account, "verifyEmail", "verify_email", "recovery_email", "recovery", default=""
                )),
                "details": account,
            })
        return {
            "success": True,
            "orderCode": str(_first(data, "order_id", "id", "orderCode", default=idempotency_key)),
            "amount": _first(data, "cost", "amount", "total", "price"),
            "walletCurrency": str(_first(data, "currency", "wallet_currency", default="USDT")),
            "deliveredAccounts": normalized_accounts,
            "providerRaw": payload,
        }
