"""Best-effort parsing of Pakistani wallet/bank payment SMS.

Formats vary a lot between JazzCash, EasyPaisa, NayaPay and banks, so we try a
list of patterns and return whatever we can. Anything unparsed is still stored
raw for manual reconciliation in admin.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Transaction-id patterns, tried in order.
_TRX_PATTERNS = [
    r"TID[:\s]*([A-Za-z0-9]{4,})",
    r"Trx[n]?\.?\s*ID[:\s]*([A-Za-z0-9]{4,})",
    r"Transaction\s*ID[:\s]*([A-Za-z0-9]{4,})",
    r"\bTrxID[:\s]*([A-Za-z0-9]{4,})",
    r"Ref(?:erence)?\s*(?:No|#|ID)?[:\s]*([A-Za-z0-9]{6,})",
]

# Amount patterns.
_AMOUNT_PATTERNS = [
    r"(?:Rs\.?|PKR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    r"amount\s*(?:of)?\s*(?:Rs\.?|PKR)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
]


def parse_trx_id(text: str) -> str:
    for pat in _TRX_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def parse_amount(text: str):
    for pat in _AMOUNT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return Decimal(raw)
            except (InvalidOperation, ValueError):
                continue
    return None


def parse_sms(text: str) -> tuple[str, Decimal | None]:
    """Return (trx_id, amount). Either may be empty/None if not found."""
    text = text or ""
    return parse_trx_id(text), parse_amount(text)


def normalize_trx(trx_id: str) -> str:
    return (trx_id or "").strip().upper()
