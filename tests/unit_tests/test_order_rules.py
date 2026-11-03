from datetime import date

import pytest

from cadenza import order_rules as rules
from cadenza import store_data as sd
from cadenza.context import DATA_DIR


@pytest.fixture(scope="module")
def customers():
    return sd.load_store(DATA_DIR).customers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(67) 99812-3456", "67998123456"),
        ("+55 67 99812-3456", "67998123456"),
        ("(55) 99999-1234", "55999991234"),
        ("+55 (55) 99999-1234", "55999991234"),
        ("(67) 3341-4444", "6733414444"),
        ("99812-3456", None),
        ("3456", None),
    ],
)
def test_normalize_phone_requires_area_code_and_keeps_ddd_55(raw, expected):
    assert rules.normalize_phone(raw) == expected


def test_find_customer_ids_by_email_phone_or_none_for_partial_phone(customers):
    assert rules.find_customer_ids(customers, " Lucas.Mendes@jmail.com ") == [1]
    assert rules.find_customer_ids(customers, "67 99812 3456") == [1]
    assert rules.find_customer_ids(customers, "bruno.martins@jmail.com") == [11, 43]
    assert rules.find_customer_ids(customers, "nobody@jmail.com") == []
    assert rules.find_customer_ids(customers, "3456") is None


def test_return_windows_are_inclusive_and_use_the_right_start_date():
    ordered, delivered = date(2026, 2, 3), date(2026, 2, 17)
    on_last_day = rules.return_windows(ordered, delivered, date(2026, 2, 24))
    assert on_last_day["regret_return"] == rules.ReturnWindow(True, date(2026, 2, 24))
    assert on_last_day["defect_exchange"].deadline == date(2026, 3, 5)
    assert on_last_day["legal_warranty"].deadline == date(2026, 5, 18)
    day_after = rules.return_windows(ordered, delivered, date(2026, 2, 25))
    assert not day_after["regret_return"].eligible
    assert not day_after["preference_exchange"].eligible
    assert day_after["defect_exchange"].eligible
