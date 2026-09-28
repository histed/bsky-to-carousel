"""Opt-in live tests against the real public.api.bsky.app.

Skipped unless LIVE_TESTS=1, so the default suite never touches the network.
Run with:  LIVE_TESTS=1 pixi run pytest tests/test_live_api.py -q

These guard against Bluesky API drift: they assert the response fields this
project depends on still exist and still have the shapes the pure functions
expect (verified 2026-09-27).
"""
import os

import pytest

import bsky_thread_to_png as mod

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_TESTS") != "1",
    reason="live network test; set LIVE_TESTS=1 to run",
)

# A stable, well-known account. The rkey is discovered dynamically from the
# author feed rather than hardcoded, so the test survives content changes.
KNOWN_HANDLE = "bsky.app"


def test_resolve_did_returns_did():
    did = mod.resolve_did(KNOWN_HANDLE)
    assert did.startswith("did:")


def _latest_rkey(did):
    import requests
    r = requests.get(f"{mod.API}/app.bsky.feed.getAuthorFeed",
                     params={"actor": did, "limit": 1}, timeout=20)
    r.raise_for_status()
    uri = r.json()["feed"][0]["post"]["uri"]  # at://did/app.bsky.feed.post/<rkey>
    return uri.rsplit("/", 1)[1]


def test_get_thread_and_collect_shapes():
    did = mod.resolve_did(KNOWN_HANDLE)
    rkey = _latest_rkey(did)
    thread = mod.get_thread(f"at://{did}/app.bsky.feed.post/{rkey}")

    # shape the pure functions rely on
    assert "post" in thread
    post = thread["post"]
    for key in ("author", "record", "indexedAt"):
        assert key in post, f"missing post.{key}"
    for key in ("did", "handle"):
        assert key in post["author"], f"missing post.author.{key}"
    assert "text" in post["record"]

    posts = mod.collect_self_thread(thread)
    assert len(posts) >= 1
    # slide_html and thread_markdown must not raise on real data
    assert mod.slide_html(posts[0], 1, len(posts), dark=False)
    assert mod.thread_markdown(posts)
