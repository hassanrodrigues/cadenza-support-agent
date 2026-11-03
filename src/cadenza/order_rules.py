"""Order rules: contact verification and return, exchange and warranty windows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

REGRET_DAYS = 7  # manual 4.1, counted from delivery
DEFECT_DAYS = 30  # manual 4.2, counted from purchase
PREFERENCE_DAYS = 7  # manual 4.3, read as counted from delivery
LEGAL_WARRANTY_DAYS = 90  # manual 8.1, counted from delivery


@dataclass(frozen=True)
class ReturnWindow:
    """Whether a return/exchange/warranty rule still applies, and until when."""

    eligible: bool
    deadline: date


def normalize_phone(raw: str) -> str | None:
    """Digits of a full Brazilian phone with area code, or None if incomplete."""
    digits = re.sub(r"\D", "", raw)
    # Drop the country code only when present: 55 is also a valid area code.
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    return digits if len(digits) in (10, 11) else None


def find_customer_ids(customers: pd.DataFrame, contact: str) -> list[int] | None:
    """Customers matching an e-mail or a full phone; None when the contact is not usable."""
    contact = contact.strip().lower()
    if "@" in contact:
        mask = customers["email"] == contact
    else:
        phone = normalize_phone(contact)
        if phone is None:
            return None
        mask = customers["phone_digits"] == phone
    return customers.loc[mask, "customer_id"].tolist()


def return_windows(
    order_date: date, delivered_on: date, today: date
) -> dict[str, ReturnWindow]:
    """Every return, exchange and warranty rule with its deadline, inclusive."""
    deadlines = {
        "regret_return": delivered_on + timedelta(days=REGRET_DAYS),
        "defect_exchange": order_date + timedelta(days=DEFECT_DAYS),
        "preference_exchange": delivered_on + timedelta(days=PREFERENCE_DAYS),
        "legal_warranty": delivered_on + timedelta(days=LEGAL_WARRANTY_DAYS),
    }
    return {rule: ReturnWindow(today <= end, end) for rule, end in deadlines.items()}
