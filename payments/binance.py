"""Read-only Binance deposit-history client and currency helpers."""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from urllib.parse import urlencode

import requests
from django.conf import settings


class BinanceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_enabled() -> bool:
    return bool(settings.BINANCE_PAYMENT_ENABLED and settings.BINANCE_API_KEY
                and settings.BINANCE_API_SECRET and settings.BINANCE_DEPOSIT_ADDRESS)


def is_pay_id_enabled() -> bool:
    return bool(settings.BINANCE_PAYMENT_ENABLED and settings.BINANCE_PAY_API_KEY
                and settings.BINANCE_PAY_API_SECRET and settings.BINANCE_PAY_ID)


def pkr_rate() -> Decimal:
    try:
        rate = Decimal(str(settings.USD_TO_PKR_RATE))
    except (InvalidOperation, TypeError):
        rate = Decimal("0")
    if rate <= 0:
        raise BinanceError("bad_config", "Binance conversion rate is not configured.")
    return rate


def pkr_to_coin(amount_pkr: Decimal) -> Decimal:
    return (Decimal(amount_pkr) / pkr_rate()).quantize(Decimal("0.01"), rounding=ROUND_UP)


def coin_to_pkr(amount: Decimal) -> Decimal:
    return (Decimal(amount) * pkr_rate()).quantize(Decimal("1"), rounding=ROUND_DOWN)


def public_config() -> dict:
    wallet_enabled = is_enabled()
    pay_id_enabled = is_pay_id_enabled()
    return {
        "enabled": wallet_enabled or pay_id_enabled,
        "wallet_enabled": wallet_enabled,
        "pay_id_enabled": pay_id_enabled,
        "coin": settings.BINANCE_COIN,
        "network": settings.BINANCE_NETWORK,
        "address": settings.BINANCE_DEPOSIT_ADDRESS if wallet_enabled else "",
        "pay_id": settings.BINANCE_PAY_ID if pay_id_enabled else "",
        "pkr_per_coin": str(pkr_rate()) if (wallet_enabled or pay_id_enabled) else None,
    }


def currency_config() -> dict:
    return {"usd_to_pkr_rate": str(pkr_rate())}


def find_successful_deposit(tx_id: str) -> dict:
    if not is_enabled():
        raise BinanceError("not_configured", "Binance payments are not available yet.")
    tx_id = (tx_id or "").strip()
    if not tx_id:
        raise BinanceError("missing_trx", "Binance TxID is required.")
    params = {
        "coin": settings.BINANCE_COIN,
        "status": 1,
        "txId": tx_id,
        "startTime": int((time.time() - 30 * 86400) * 1000),
        "timestamp": int(time.time() * 1000),
        "recvWindow": 5000,
    }
    query = urlencode(params)
    signature = hmac.new(settings.BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{settings.BINANCE_API_BASE_URL.rstrip('/')}/sapi/v1/capital/deposit/hisrec"
    try:
        response = requests.get(
            url, params={**params, "signature": signature},
            headers={"X-MBX-APIKEY": settings.BINANCE_API_KEY}, timeout=12,
        )
        response.raise_for_status()
        deposits = response.json()
    except (requests.RequestException, ValueError) as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            try:
                detail = exc.response.json().get("msg", "")
            except (ValueError, AttributeError):
                pass
        raise BinanceError("api_unavailable", detail or "Could not verify with Binance right now. Please retry shortly.") from exc

    wanted = tx_id.casefold()
    deposit = next((d for d in deposits if str(d.get("txId", "")).strip().casefold() == wanted), None)
    if not deposit:
        raise BinanceError("not_found", "Successful Binance deposit not found yet. Check the TxID and confirmations, then retry.")
    if str(deposit.get("coin", "")).upper() != settings.BINANCE_COIN:
        raise BinanceError("wrong_coin", f"Payment must use {settings.BINANCE_COIN}.")
    network = str(deposit.get("network", "")).upper()
    if settings.BINANCE_NETWORK and network != settings.BINANCE_NETWORK:
        raise BinanceError("wrong_network", f"Payment must use {settings.BINANCE_NETWORK} network.")
    address = str(deposit.get("address", "")).strip()
    if address.casefold() != settings.BINANCE_DEPOSIT_ADDRESS.strip().casefold():
        raise BinanceError("wrong_address", "This deposit was not sent to our payment address.")
    return deposit


def find_pay_transaction(transaction_id: str) -> dict:
    """Find an incoming Binance Pay/C2C transfer sent to our Binance ID."""
    if not is_pay_id_enabled():
        raise BinanceError("not_configured", "Binance ID payments are not available yet.")
    transaction_id = (transaction_id or "").strip()
    if not transaction_id:
        raise BinanceError("missing_trx", "Binance Pay transaction ID is required.")

    now_ms = int(time.time() * 1000)
    params = {
        "startTime": now_ms - 30 * 86400 * 1000,
        "endTime": now_ms,
        "limit": 100,
        "timestamp": now_ms,
        "recvWindow": 5000,
    }
    query = urlencode(params)
    signature = hmac.new(
        settings.BINANCE_PAY_API_SECRET.encode(), query.encode(), hashlib.sha256
    ).hexdigest()
    url = f"{settings.BINANCE_API_BASE_URL.rstrip('/')}/sapi/v1/pay/transactions"
    try:
        response = requests.get(
            url, params={**params, "signature": signature},
            headers={"X-MBX-APIKEY": settings.BINANCE_PAY_API_KEY}, timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            try:
                detail = exc.response.json().get("message", "") or exc.response.json().get("msg", "")
            except (ValueError, AttributeError):
                pass
        normalized = detail.casefold()
        if "invalid api-key" in normalized or "api-key id" in normalized:
            raise BinanceError(
                "invalid_api_key",
                "Binance Pay verification key is invalid. The site administrator must update the Binance Pay API credentials.",
            ) from exc
        if "restricted location" in normalized or "service unavailable from a restricted" in normalized:
            raise BinanceError(
                "binance_region_restricted",
                "Binance Pay API is unavailable from the server region. Please contact support.",
            ) from exc
        raise BinanceError("api_unavailable", detail or "Could not verify Binance ID payment right now. Please retry shortly.") from exc

    if payload.get("success") is False:
        raise BinanceError("api_unavailable", payload.get("message") or "Binance Pay verification failed.")
    wanted = transaction_id.casefold()
    item = next((row for row in (payload.get("data") or [])
                 if str(row.get("transactionId", "")).strip().casefold() == wanted), None)
    if not item:
        raise BinanceError("not_found", "Incoming Binance ID payment not found. Check the transaction ID and retry.")
    receiver_info = item.get("receiverInfo") or {}
    receiver_id = str(receiver_info.get("binanceId", "")).strip() if isinstance(receiver_info, dict) else ""
    # The user-data endpoint is scoped to the API-key owner. Some Binance
    # response versions omit receiverInfo; validate it whenever it is supplied.
    if receiver_id and receiver_id.casefold() != settings.BINANCE_PAY_ID.casefold():
        raise BinanceError("wrong_receiver", "This payment was not sent to our Binance ID.")
    if str(item.get("currency", "")).upper() != settings.BINANCE_COIN:
        raise BinanceError("wrong_coin", f"Payment must use {settings.BINANCE_COIN}.")
    return item
