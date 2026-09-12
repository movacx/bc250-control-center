"""Asking GitHub whether there is a newer release, and asking it carefully.

This is the only place the desktop application reaches the network by itself.
Everything else that touches the internet does so inside a shell workflow the
user started and can watch, so the rules this module follows are worth pinning
rather than trusting to review:

* the URL is https and constant, and a redirect off https is refused;
* the body read is capped, because whatever comes back is untrusted text — a
  captive portal, a rate-limit page, a VERSION file mid-edit;
* nothing identifying the machine is sent;
* no failure reaches the user: not reaching GitHub shows nothing at all;
* the answer is cached, so opening the dashboard repeatedly asks once.

The comparison itself is pure and lives in ``bc250cc.domain.updates``, so it
can be tested without a socket.
"""

from __future__ import annotations

import json
import time
import urllib.error

import pytest

from bc250cc.domain.updates import (
    MAX_VERSION_TEXT_BYTES,
    UpdateStatus,
    is_newer,
    parse_version,
)
from bc250cc.infrastructure import release_check

# --------------------------------------------------------------- the comparison


@pytest.mark.parametrize(
    ("published", "installed", "expected"),
    [
        ("1.20.0", "1.19.0", True),
        ("1.19.1", "1.19.0", True),
        ("2.0.0", "1.99.99", True),
        ("v1.20.0\n", "1.19.0", True),
        ("1.19.0", "1.19.0", False),
        ("1.19.0", "1.20.0", False),
        # ``1.19`` and ``1.19.0`` name one release.
        ("1.19", "1.19.0", False),
        ("1.19.0", "1.19", False),
        ("1.19.1", "1.19", True),
    ],
)
def test_a_release_is_newer_only_when_it_really_is(published, installed, expected):
    assert is_newer(published, installed) is expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "development",
        "<!DOCTYPE html>",
        "404: Not Found",
        "1.19.0-rc1",
        "1.19.0+build7",
        "not a version",
        "1" * 200,
        None,
        1.19,
    ],
)
def test_anything_that_is_not_a_release_is_no_answer(text):
    """Untrusted text must fail closed, never into a confident badge."""
    assert parse_version(text) is None
    assert is_newer(text, "1.19.0") is False


def test_a_development_checkout_is_never_told_it_is_behind():
    """``application_version`` reports ``development`` outside a release."""
    assert is_newer("1.20.0", "development") is False


def test_an_oversized_body_is_refused_rather_than_truncated():
    oversized = "1." * MAX_VERSION_TEXT_BYTES
    assert parse_version(oversized) is None


# ----------------------------------------------------------------- the status


def test_an_unreachable_network_is_not_the_same_as_being_up_to_date():
    unreachable = UpdateStatus(installed="1.19.0", published="", reachable=False)
    assert unreachable.update_available is False
    assert unreachable.summary == ""

    current = UpdateStatus(installed="1.19.0", published="1.19.0", reachable=True)
    assert current.update_available is False
    assert current.summary == ""

    behind = UpdateStatus(installed="1.19.0", published="1.20.0", reachable=True)
    assert behind.update_available is True
    assert behind.summary == "1.20.0"


def test_a_published_version_without_a_reachable_flag_claims_nothing():
    """Guards against a caller that fills in ``published`` and forgets the rest."""
    assert UpdateStatus(installed="1.19.0", published="9.9.9").update_available is False


# ------------------------------------------------------------------ the fetch


def test_the_url_is_https_and_names_one_file():
    assert release_check.RELEASE_VERSION_URL.startswith("https://")
    assert release_check.RELEASE_VERSION_URL.endswith("/VERSION")
    assert release_check.RELEASES_PAGE_URL.startswith("https://")


def test_a_plain_http_url_is_refused_without_a_request(monkeypatch):
    def explode(*_args, **_kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("an http url must not be requested")

    monkeypatch.setattr(release_check.urllib.request, "build_opener", explode)
    assert release_check.fetch_published_version(url="http://example.invalid/VERSION") == ""


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status
        self.reads: list[int | None] = []

    def read(self, amount=None):
        self.reads.append(amount)
        return self._body[:amount] if amount is not None else self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _with_response(monkeypatch, response):
    captured = {}

    class _Opener:
        def open(self, request, timeout=None):
            captured["request"] = request
            captured["timeout"] = timeout
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setattr(release_check.urllib.request, "build_opener", lambda *_h: _Opener())
    return captured


def test_a_version_is_read_and_stripped(monkeypatch):
    _with_response(monkeypatch, _Response(b"1.20.0\n"))
    assert release_check.fetch_published_version() == "1.20.0"


def test_the_body_read_is_capped(monkeypatch):
    response = _Response(b"1.20.0\n")
    _with_response(monkeypatch, response)
    release_check.fetch_published_version()
    # One byte over the limit, so a longer body is visibly wrong rather than
    # truncated into something that happens to parse.
    assert response.reads == [MAX_VERSION_TEXT_BYTES + 1]


def test_a_body_longer_than_the_cap_is_discarded(monkeypatch):
    _with_response(monkeypatch, _Response(b"x" * (MAX_VERSION_TEXT_BYTES + 40)))
    assert release_check.fetch_published_version() == ""


def test_a_non_200_response_is_not_parsed(monkeypatch):
    _with_response(monkeypatch, _Response(b"1.99.0", status=404))
    assert release_check.fetch_published_version() == ""


def test_undecodable_bytes_are_discarded(monkeypatch):
    _with_response(monkeypatch, _Response(b"\xff\xfe\x00bad"))
    assert release_check.fetch_published_version() == ""


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("no route to host"),
        OSError("connection reset"),
        TimeoutError("timed out"),
        ValueError("unknown url type"),
    ],
)
def test_no_network_failure_escapes(monkeypatch, failure):
    _with_response(monkeypatch, failure)
    assert release_check.fetch_published_version() == ""


def test_the_request_sends_nothing_about_the_machine(monkeypatch):
    captured = _with_response(monkeypatch, _Response(b"1.20.0"))
    release_check.fetch_published_version()
    request = captured["request"]
    assert request.get_method() == "GET"
    headers = {key.lower(): value for key, value in request.header_items()}
    assert headers.get("user-agent") == release_check.USER_AGENT
    # Nothing else beyond the product name and what we accept.
    assert set(headers) <= {"user-agent", "accept", "host"}
    assert "?" not in request.full_url, "a query string could carry identifiers"


def test_the_request_is_bounded_in_time(monkeypatch):
    captured = _with_response(monkeypatch, _Response(b"1.20.0"))
    release_check.fetch_published_version()
    assert captured["timeout"] == release_check.REQUEST_TIMEOUT_SECONDS
    assert release_check.REQUEST_TIMEOUT_SECONDS <= 10


def test_a_redirect_away_from_https_is_not_followed():
    handler = release_check._HttpsOnlyRedirect()
    assert handler.redirect_request(
        None, None, 302, "Found", {}, "http://example.invalid/VERSION"
    ) is None


# ------------------------------------------------------------------ the cache


def test_a_fresh_cache_answers_without_touching_the_network(tmp_path, monkeypatch):
    (tmp_path / release_check.CACHE_FILENAME).write_text(
        json.dumps({"published": "1.21.0", "checked_at_unix": time.time()}),
        encoding="utf-8",
    )

    def explode(*_args, **_kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("a fresh cache must not reach the network")

    monkeypatch.setattr(release_check, "fetch_published_version", explode)
    status = release_check.check_for_update(installed="1.19.0", cache_dir=tmp_path)
    assert status.published == "1.21.0"
    assert status.update_available is True


def test_a_stale_cache_is_refreshed(tmp_path, monkeypatch):
    (tmp_path / release_check.CACHE_FILENAME).write_text(
        json.dumps(
            {
                "published": "1.10.0",
                "checked_at_unix": time.time() - release_check.CACHE_SECONDS - 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.22.0")
    status = release_check.check_for_update(installed="1.19.0", cache_dir=tmp_path)
    assert status.published == "1.22.0"


def test_a_successful_check_is_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.23.0")
    release_check.check_for_update(installed="1.19.0", cache_dir=tmp_path)
    payload = json.loads((tmp_path / release_check.CACHE_FILENAME).read_text(encoding="utf-8"))
    assert payload["published"] == "1.23.0"
    assert isinstance(payload["checked_at_unix"], (int, float))


def test_a_failed_check_is_not_remembered_as_an_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "")
    status = release_check.check_for_update(installed="1.19.0", cache_dir=tmp_path)
    assert status.reachable is False
    assert not (tmp_path / release_check.CACHE_FILENAME).exists()


@pytest.mark.parametrize(
    "content",
    ["not json", "{}", '{"published": 7}', '{"published": "1.2.3"}', '[]'],
)
def test_a_damaged_cache_is_ignored_rather_than_trusted(tmp_path, monkeypatch, content):
    (tmp_path / release_check.CACHE_FILENAME).write_text(content, encoding="utf-8")
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.24.0")
    status = release_check.check_for_update(installed="1.19.0", cache_dir=tmp_path)
    assert status.published == "1.24.0"


def test_a_clock_from_the_future_does_not_freeze_the_cache(tmp_path, monkeypatch):
    (tmp_path / release_check.CACHE_FILENAME).write_text(
        json.dumps({"published": "0.0.1", "checked_at_unix": time.time() + 86_400}),
        encoding="utf-8",
    )
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.25.0")
    status = release_check.check_for_update(installed="1.19.0", cache_dir=tmp_path)
    assert status.published == "1.25.0"


def test_an_unwritable_cache_directory_does_not_break_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.26.0")
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    status = release_check.check_for_update(installed="1.19.0", cache_dir=blocked)
    assert status.published == "1.26.0"
    assert status.update_available is True


def test_force_skips_the_cache(tmp_path, monkeypatch):
    (tmp_path / release_check.CACHE_FILENAME).write_text(
        json.dumps({"published": "1.10.0", "checked_at_unix": time.time()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.27.0")
    status = release_check.check_for_update(
        installed="1.19.0", cache_dir=tmp_path, force=True
    )
    assert status.published == "1.27.0"


def test_the_cache_window_is_short_enough_to_notice_a_release():
    """Long enough not to ask on every visit, short enough to be believed.

    This was six hours, which made the check indistinguishable from a
    hardcoded answer: publish a version, open the dashboard, and nothing
    happens for the rest of the afternoon. The published file is a handful of
    bytes behind a CDN — asking costs far less than being silently wrong.
    """
    assert 60 <= release_check.CACHE_SECONDS <= 30 * 60


def test_a_version_published_after_the_window_is_noticed(tmp_path, monkeypatch):
    """The end of the loop: a release lands, the window lapses, the app sees it."""
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.19.0")
    first = release_check.check_for_update(installed="1.19.0", cache_dir=tmp_path)
    assert first.update_available is False

    # A new version is published, and the cached answer ages past the window.
    monkeypatch.setattr(release_check, "fetch_published_version", lambda: "1.19.1")
    later = release_check.check_for_update(
        installed="1.19.0",
        cache_dir=tmp_path,
        now=time.time() + release_check.CACHE_SECONDS + 1,
    )
    assert later.published == "1.19.1"
    assert later.update_available is True
