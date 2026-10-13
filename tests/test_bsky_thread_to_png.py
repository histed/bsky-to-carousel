"""Unit tests for the network-free, pure functions of bsky_thread_to_png.

Fixtures mirror the real shapes returned by public.api.bsky.app
(app.bsky.feed.getPostThread), verified against the live API 2026-09-27:
thread nodes are `{post, parent?, replies?}`; posts carry
`author.{did,handle,displayName,avatar}`, `record.text`, `indexedAt`, and
`embed` whose `$type` uses a `#view` suffix (e.g. `app.bsky.embed.images#view`).
"""
import pytest

import bsky_thread_to_png as mod


# --- helpers ----------------------------------------------------------------

def make_post(did, *, handle=None, name=None, avatar=None, text="hi",
              indexed_at="2026-01-01T00:00:00Z", embed=None):
    author = {"did": did, "handle": handle or f"{did}.bsky.social"}
    if name is not None:
        author["displayName"] = name
    if avatar is not None:
        author["avatar"] = avatar
    post = {"author": author, "record": {"text": text}, "indexedAt": indexed_at}
    if embed is not None:
        post["embed"] = embed
    return post


def node(post, *, parent=None, replies=None):
    n = {"post": post}
    if parent is not None:
        n["parent"] = parent
    if replies is not None:
        n["replies"] = replies
    return n


# --- parse_url --------------------------------------------------------------

def test_parse_url_basic():
    assert mod.parse_url("https://bsky.app/profile/alice.bsky.social/post/3abc") == (
        "alice.bsky.social", "3abc")


def test_parse_url_strips_query_and_fragment():
    assert mod.parse_url("https://bsky.app/profile/alice.test/post/3xyz?foo=1#frag") == (
        "alice.test", "3xyz")


def test_parse_url_accepts_did_actor():
    handle, rkey = mod.parse_url("https://bsky.app/profile/did:plc:abc123/post/3rk")
    assert handle == "did:plc:abc123" and rkey == "3rk"


def test_parse_url_rejects_non_post_url():
    with pytest.raises(SystemExit):
        mod.parse_url("https://example.com/not/a/post")


# --- embed_images -----------------------------------------------------------

def test_embed_images_none_when_no_embed():
    assert mod.embed_images(make_post("did:a")) == []


def test_embed_images_images_view_suffix():
    embed = {
        "$type": "app.bsky.embed.images#view",
        "images": [
            {"fullsize": "https://cdn/a.jpg", "alt": "a cat"},
            {"fullsize": "https://cdn/b.jpg"},  # alt missing -> ""
        ],
    }
    assert mod.embed_images(make_post("did:a", embed=embed)) == [
        ("https://cdn/a.jpg", "a cat"),
        ("https://cdn/b.jpg", ""),
    ]


def test_embed_images_record_with_media():
    # media is itself a typed view (images#view here), per the real API
    embed = {
        "$type": "app.bsky.embed.recordWithMedia#view",
        "media": {"$type": "app.bsky.embed.images#view",
                  "images": [{"fullsize": "https://cdn/m.jpg", "alt": "x"}]},
    }
    assert mod.embed_images(make_post("did:a", embed=embed)) == [("https://cdn/m.jpg", "x")]


def test_embed_images_external_is_not_an_image():
    # external embeds are link cards, not plain media images
    embed = {
        "$type": "app.bsky.embed.external#view",
        "external": {"thumb": "https://cdn/thumb.jpg", "uri": "https://ex"},
    }
    assert mod.embed_images(make_post("did:a", embed=embed)) == []


def test_embed_images_unknown_type():
    embed = {"$type": "app.bsky.embed.record#view", "record": {}}
    assert mod.embed_images(make_post("did:a", embed=embed)) == []


# --- embed_external (link cards) --------------------------------------------

def _external_view(uri="https://www.aol.com/articles/adventure",
                   title="A Title", desc="A description", thumb="https://cdn/t.jpg"):
    ext = {"uri": uri}
    if title is not None:
        ext["title"] = title
    if desc is not None:
        ext["description"] = desc
    if thumb is not None:
        ext["thumb"] = thumb
    return {"$type": "app.bsky.embed.external#view", "external": ext}


def test_embed_external_fields():
    e = mod.embed_external(make_post("did:a", embed=_external_view()))
    assert e == {"uri": "https://www.aol.com/articles/adventure", "title": "A Title",
                 "description": "A description", "thumb": "https://cdn/t.jpg"}


def test_embed_external_none_without_embed():
    assert mod.embed_external(make_post("did:a")) is None


def test_embed_external_requires_uri():
    embed = {"$type": "app.bsky.embed.external#view", "external": {"title": "no uri"}}
    assert mod.embed_external(make_post("did:a", embed=embed)) is None


def test_embed_external_record_with_media():
    embed = {
        "$type": "app.bsky.embed.recordWithMedia#view",
        "media": _external_view(uri="https://example.com/x", title="RWM"),
        "record": {"$type": "app.bsky.embed.record#view", "record": {}},
    }
    e = mod.embed_external(make_post("did:a", embed=embed))
    assert e["uri"] == "https://example.com/x" and e["title"] == "RWM"


def test_domain_strips_scheme_and_www():
    assert mod._domain("https://www.aol.com/articles/x?y=1") == "aol.com"
    assert mod._domain("http://example.org") == "example.org"


def test_external_html_renders_card_parts():
    out = mod._external_html(mod.embed_external(make_post("did:a", embed=_external_view())),
                             __import__("html").escape)
    assert 'class="linkcard"' in out
    assert 'class="lcdomain">aol.com<' in out
    assert 'class="lctitle">A Title<' in out
    assert 'class="lcdesc">A description<' in out
    assert 'class="lcthumb" src="https://cdn/t.jpg"' in out


def test_external_html_empty_when_none():
    assert mod._external_html(None, __import__("html").escape) == ""


# --- embed_quote ------------------------------------------------------------

def _quote_view(handle, text, *, name=None, avatar=None, images=None):
    """A app.bsky.embed.record#view wrapping a viewRecord."""
    rec = {
        "$type": "app.bsky.embed.record#viewRecord",
        "author": {"handle": handle, "did": "did:q"},
        "value": {"text": text},
    }
    if name is not None:
        rec["author"]["displayName"] = name
    if avatar is not None:
        rec["author"]["avatar"] = avatar
    if images:
        rec["embeds"] = [{"$type": "app.bsky.embed.images#view",
                          "images": [{"fullsize": u, "alt": a} for u, a in images]}]
    return {"$type": "app.bsky.embed.record#view", "record": rec}


def test_embed_quote_none_without_embed():
    assert mod.embed_quote(make_post("did:a")) is None


def test_embed_quote_ignores_plain_media_embed():
    embed = {"$type": "app.bsky.embed.images#view",
             "images": [{"fullsize": "https://cdn/a.jpg", "alt": ""}]}
    assert mod.embed_quote(make_post("did:a", embed=embed)) is None


def test_embed_quote_record_view():
    embed = _quote_view("bob.test", "quoted words", name="Bob", avatar="https://cdn/av.jpg")
    q = mod.embed_quote(make_post("did:a", embed=embed))
    assert q == {"name": "Bob", "handle": "bob.test", "avatar": "https://cdn/av.jpg",
                 "text": "quoted words", "images": []}


def test_embed_quote_name_falls_back_to_handle():
    q = mod.embed_quote(make_post("did:a", embed=_quote_view("bob.test", "x")))
    assert q["name"] == "bob.test"


def test_embed_quote_collects_quoted_images():
    embed = _quote_view("bob.test", "with pic", images=[("https://cdn/q.jpg", "a dog")])
    q = mod.embed_quote(make_post("did:a", embed=embed))
    assert q["images"] == [("https://cdn/q.jpg", "a dog")]


def test_embed_quote_record_with_media():
    # recordWithMedia#view nests the quoted record under record.record
    inner = _quote_view("bob.test", "quoted")["record"]
    embed = {
        "$type": "app.bsky.embed.recordWithMedia#view",
        "media": {"$type": "app.bsky.embed.images#view",
                  "images": [{"fullsize": "https://cdn/m.jpg", "alt": ""}]},
        "record": {"$type": "app.bsky.embed.record#view", "record": inner},
    }
    post = make_post("did:a", embed=embed)
    q = mod.embed_quote(post)
    assert q["handle"] == "bob.test" and q["text"] == "quoted"
    # the media (not the quote) is what embed_images returns
    assert mod.embed_images(post) == [("https://cdn/m.jpg", "")]


def test_embed_quote_blocked_returns_none():
    embed = {"$type": "app.bsky.embed.record#view",
             "record": {"$type": "app.bsky.embed.record#viewBlocked", "blocked": True}}
    assert mod.embed_quote(make_post("did:a", embed=embed)) is None


# --- collect_self_thread ----------------------------------------------------

def test_collect_single_post():
    n = node(make_post("did:a", text="only"))
    assert [p["record"]["text"] for p in mod.collect_self_thread(n)] == ["only"]


def test_collect_walks_up_same_author_and_stops_at_other():
    root = node(make_post("did:a", text="root"))
    other = node(make_post("did:b", text="someone else"), parent=root)
    mid = node(make_post("did:a", text="mid"), parent=other)
    cur = node(make_post("did:a", text="cur"), parent=mid)
    # parent chain: cur <- mid <- other(did:b) <- root; walk-up stops at other
    texts = [p["record"]["text"] for p in mod.collect_self_thread(cur)]
    assert texts == ["mid", "cur"]


def test_collect_walks_down_earliest_self_reply():
    reply_late = node(make_post("did:a", text="down-late", indexed_at="2026-01-01T02:00:00Z"))
    reply_early = node(make_post("did:a", text="down-early", indexed_at="2026-01-01T01:00:00Z"))
    other_reply = node(make_post("did:b", text="stranger", indexed_at="2026-01-01T00:30:00Z"))
    root = node(make_post("did:a", text="root"),
                replies=[reply_late, other_reply, reply_early])
    texts = [p["record"]["text"] for p in mod.collect_self_thread(root)]
    assert texts == ["root", "down-early"]


def test_collect_ignores_replies_from_others():
    root = node(make_post("did:a", text="root"),
                replies=[node(make_post("did:b", text="stranger"))])
    texts = [p["record"]["text"] for p in mod.collect_self_thread(root)]
    assert texts == ["root"]


def test_collect_handles_notfound_parent_node():
    # getPostThread can return a parent lacking `post` (#notFoundPost/#blockedPost).
    blocked_parent = {"$type": "app.bsky.feed.defs#blockedPost", "blocked": True}
    n = node(make_post("did:a", text="cur"), parent=blocked_parent)
    texts = [p["record"]["text"] for p in mod.collect_self_thread(n)]
    assert texts == ["cur"]


def test_collect_handles_notfound_reply_node():
    notfound_reply = {"$type": "app.bsky.feed.defs#notFoundPost", "notFound": True}
    self_reply = node(make_post("did:a", text="down"))
    root = node(make_post("did:a", text="root"), replies=[notfound_reply, self_reply])
    texts = [p["record"]["text"] for p in mod.collect_self_thread(root)]
    assert texts == ["root", "down"]


# --- slide_html -------------------------------------------------------------

def test_slide_html_contains_identity_and_footer():
    p = make_post("did:a", handle="alice.bsky.social", name="Alice", text="hello world")
    out = mod.slide_html(p, 2, 5, dark=False)
    assert "Alice" in out
    assert "@alice.bsky.social" in out
    assert "hello world" in out
    assert "2/5" in out


def test_slide_html_escapes_text():
    p = make_post("did:a", text="<script>alert('x')</script> & <b>")
    out = mod.slide_html(p, 1, 1, dark=False)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&amp;" in out


def test_slide_html_falls_back_to_handle_when_no_display_name():
    p = make_post("did:a", handle="bob.test", name=None)
    out = mod.slide_html(p, 1, 1, dark=False)
    assert "bob.test" in out


def test_slide_html_avatar_present_vs_absent():
    with_av = mod.slide_html(make_post("did:a", avatar="https://cdn/av.jpg"), 1, 1, False)
    assert 'class="av" src="https://cdn/av.jpg"' in with_av
    without_av = mod.slide_html(make_post("did:a"), 1, 1, False)
    assert '<div class="av"></div>' in without_av


def test_slide_html_dark_vs_light_background():
    p = make_post("did:a")
    assert "#161e27" in mod.slide_html(p, 1, 1, dark=True)
    assert "#ffffff" in mod.slide_html(p, 1, 1, dark=False)


def test_slide_html_renders_image_tags():
    embed = {"$type": "app.bsky.embed.images#view",
             "images": [{"fullsize": "https://cdn/a.jpg", "alt": "cat"}]}
    out = mod.slide_html(make_post("did:a", embed=embed), 1, 1, dark=False)
    assert 'class="media" src="https://cdn/a.jpg"' in out
    assert 'alt="cat"' in out


def test_slide_html_renders_quote_card():
    embed = _quote_view("bob.test", "quoted words", name="Bob")
    out = mod.slide_html(make_post("did:a", embed=embed), 1, 1, dark=False)
    assert 'class="quote"' in out
    assert 'class="qname">Bob<' in out
    assert '@bob.test' in out
    assert 'class="qtext">quoted words<' in out


def test_slide_html_no_quote_card_when_absent():
    out = mod.slide_html(make_post("did:a", text="plain"), 1, 1, dark=False)
    assert 'class="quote"' not in out


# --- canvas / card / bgcolor ------------------------------------------------

def test_canvas_bg_css_passes_hex_through():
    assert mod.canvas_bg_css("#bde0fe") == "#bde0fe"
    assert mod.canvas_bg_css("#FFD6E7") == "#FFD6E7"


def test_canvas_bg_css_none_and_blank_are_transparent():
    for v in ("none", "None", "transparent", "", "  "):
        assert mod.canvas_bg_css(v) == "transparent"


def test_slide_html_has_canvas_and_card():
    out = mod.slide_html(make_post("did:a", text="hi"), 1, 1, dark=False)
    assert 'class="canvas"' in out
    assert 'class="card"' in out


def test_slide_html_default_bgcolor_is_sky_blue():
    out = mod.slide_html(make_post("did:a"), 1, 1, dark=False)
    assert mod.DEFAULT_BG == "#bde0fe"
    assert f"background:{mod.DEFAULT_BG}" in out


def test_slide_html_custom_and_transparent_bgcolor():
    pink = mod.slide_html(make_post("did:a"), 1, 1, dark=False, bgcolor="#ffd6e7")
    assert "background:#ffd6e7" in pink
    clear = mod.slide_html(make_post("did:a"), 1, 1, dark=False, bgcolor="none")
    # the canvas is transparent; the card keeps its own (light) fill
    assert ".canvas{width:1080px;height:1350px;background:transparent" in clear
    assert "#ffffff" in clear


# --- two-post packing -------------------------------------------------------

def test_slide_group_two_cards_each_with_header_and_footer():
    g = [(3, make_post("did:a", name="Alice", text="first")),
         (4, make_post("did:a", name="Alice", text="second"))]
    out = mod.slide_group_html(g, 11, dark=False)
    assert out.count('class="card"') == 2
    # every card draws the author header
    assert out.count('class="head"') == 2
    # and each keeps its own n/N footer
    assert "3/11" in out and "4/11" in out
    assert "first" in out and "second" in out


# --- in-text mentions (facets) ----------------------------------------------

def _mention_record(text, bs, be, did):
    return {"text": text,
            "facets": [{"index": {"byteStart": bs, "byteEnd": be},
                        "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}]}]}


def test_render_text_plain_when_no_facets():
    out = mod.render_text_html({"text": "hello <b>"}, __import__("html").escape)
    assert out == "hello &lt;b&gt;"


def test_render_text_mention_uses_display_name_in_blue():
    # "hi @c-span.bsky.social !" — the handle spans bytes 3..22
    text = "hi @c-span.bsky.social !"
    bs = len("hi ".encode())
    be = len("hi @c-span.bsky.social".encode())
    rec = _mention_record(text, bs, be, "did:plc:x")
    out = mod.render_text_html(rec, __import__("html").escape, {"did:plc:x": "C-SPAN"})
    assert '<span class="mention">@C-SPAN</span>' in out
    assert "c-span.bsky.social" not in out
    assert out.startswith("hi ") and out.endswith(" !")


def test_render_text_unresolved_keeps_handle():
    text = "yo @a.bsky.social"
    rec = _mention_record(text, 3, len(text.encode()), "did:plc:y")
    out = mod.render_text_html(rec, __import__("html").escape, {})  # no name
    assert '<span class="mention">@a.bsky.social</span>' in out


def test_render_text_byte_offsets_with_multibyte():
    # emoji before the mention: offsets are UTF-8 bytes, not chars
    text = "😀 @a.bsky.social"
    bs = len("😀 ".encode())            # 4 (emoji) + 1 (space) = 5
    be = len(text.encode())
    rec = _mention_record(text, bs, be, "did:plc:z")
    out = mod.render_text_html(rec, __import__("html").escape, {"did:plc:z": "Al"})
    assert out.startswith("😀 ")
    assert '<span class="mention">@Al</span>' in out


def test_mention_dids_collects_across_posts():
    p1 = make_post("did:a"); p1["record"] = _mention_record("x @y", 2, 4, "did:plc:1")
    p2 = make_post("did:b"); p2["record"] = _mention_record("z @w", 2, 4, "did:plc:2")
    assert mod.mention_dids([p1, p2]) == {"did:plc:1", "did:plc:2"}


def test_cards_have_bsky_butterfly():
    # one per single card, and one per card on a packed slide
    single = mod.slide_html(make_post("did:a"), 1, 1, dark=False)
    assert single.count('class="bsky"') == 1
    g = [(1, make_post("did:a")), (2, make_post("did:a"))]
    assert mod.slide_group_html(g, 2, dark=False).count('class="bsky"') == 2


def test_slide_group_single_matches_slide_html():
    p = make_post("did:a", text="solo")
    assert mod.slide_group_html([(2, p)], 5, dark=False) == mod.slide_html(p, 2, 5, dark=False)


# --- thread_markdown --------------------------------------------------------

def test_thread_markdown_numbers_and_text():
    posts = [make_post("did:a", name="Alice", handle="alice.test", text="first"),
             make_post("did:a", name="Alice", handle="alice.test", text="second")]
    md = mod.thread_markdown(posts)
    assert "## 1/2 — Alice (@alice.test)" in md
    assert "## 2/2 — Alice (@alice.test)" in md
    assert "first" in md and "second" in md


def test_thread_markdown_lists_images_with_alt():
    embed = {"$type": "app.bsky.embed.images#view",
             "images": [{"fullsize": "https://cdn/a.jpg", "alt": "a cat"}]}
    md = mod.thread_markdown([make_post("did:a", embed=embed)])
    assert "- image: https://cdn/a.jpg — alt: a cat" in md


def test_thread_markdown_empty_text_placeholder():
    md = mod.thread_markdown([make_post("did:a", text="")])
    assert "_(no text)_" in md
