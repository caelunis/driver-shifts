import pytest

from app.services.commission import commission_for


@pytest.mark.parametrize(
    "amount, pct, expected",
    [
        (2400, 15, 360),
        (2350, 15, 353),  # 352.5 rounds half up (Python's round() would give 352)
        (1000, 12.35, 124),  # 123.5: exact decimal math, no float drift to 123.4999…
        (1000, 0, 0),
        (999, 33.33, 333),
    ],
)
def test_commission_for(amount, pct, expected):
    assert commission_for(amount, pct) == expected
