import time

from app.core.ids import content_id, uuid7


def test_uuid7_is_version_7_and_rfc_variant():
    u = uuid7()
    assert u.version == 7
    assert u.variant == "specified in RFC 4122"


def test_uuid7_sorts_by_creation_time():
    first = uuid7()
    time.sleep(0.002)
    assert uuid7() > first


def test_uuid7_carries_the_unix_milliseconds():
    before = time.time_ns() // 1_000_000
    millis = uuid7().int >> 80
    assert before <= millis <= time.time_ns() // 1_000_000


def test_uuid7_does_not_repeat():
    assert len({uuid7() for _ in range(50_000)}) == 50_000


def test_content_id_is_stable_for_the_same_content():
    assert content_id("a", 1) == content_id("a", 1)
    assert content_id("a", 1) != content_id("a", 2)
