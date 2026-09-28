#!/usr/bin/env python3
"""
Bluesky thread -> one PNG per post (1080x1350, Instagram 4:5).

Usage:
    pip install requests playwright
    playwright install chromium
    python bsky_thread_to_png.py https://bsky.app/profile/HANDLE/post/RKEY [-o outdir] [--dark]

Collects the author's self-thread: walks up to the root, then follows the
author's own replies down. Other people's replies are ignored.

API field names verified against the live public.api.bsky.app responses
(app.bsky.feed.getPostThread / getAuthorFeed) on 2026-09-27.
"""
import argparse
import html
import re
import sys
from pathlib import Path

import requests

API = "https://public.api.bsky.app/xrpc"
W, H = 1080, 1350


def parse_url(url):
    m = re.search(r"bsky\.app/profile/([^/]+)/post/([^/?#]+)", url)
    if not m:
        sys.exit(f"Not a bsky.app post URL: {url}")
    return m.group(1), m.group(2)


def resolve_did(actor):
    if actor.startswith("did:"):
        return actor
    r = requests.get(f"{API}/com.atproto.identity.resolveHandle", params={"handle": actor}, timeout=20)
    r.raise_for_status()
    return r.json()["did"]


def get_thread(uri):
    r = requests.get(
        f"{API}/app.bsky.feed.getPostThread",
        params={"uri": uri, "depth": 1000, "parentHeight": 1000},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["thread"]


def _author_did(node):
    """DID of a thread node's post author, or None for notFound/blocked nodes."""
    return (node or {}).get("post", {}).get("author", {}).get("did")


def collect_self_thread(node):
    did = node["post"]["author"]["did"]

    # walk up while parent is by the same author
    up = []
    p = node.get("parent")
    while p and _author_did(p) == did:
        up.append(p["post"])
        p = p.get("parent")
    posts = list(reversed(up)) + [node["post"]]

    # walk down following the author's earliest self-reply
    cur = node
    while True:
        kids = [r for r in cur.get("replies", []) or []
                if _author_did(r) == did]
        if not kids:
            break
        kids.sort(key=lambda r: r["post"]["indexedAt"])
        cur = kids[0]
        posts.append(cur["post"])
    return posts


def _images_from_view(e):
    """Media images from a single embed *view* dict (not the quoted record)."""
    t = (e or {}).get("$type", "")
    if t.startswith("app.bsky.embed.images"):
        return [(i["fullsize"], i.get("alt", "")) for i in e.get("images", [])]
    if t.startswith("app.bsky.embed.recordWithMedia"):
        return _images_from_view(e.get("media", {}))
    if t.startswith("app.bsky.embed.external"):
        th = e.get("external", {}).get("thumb")
        return [(th, "")] if th else []
    return []


def embed_images(post):
    return _images_from_view(post.get("embed") or {})


def embed_quote(post):
    """Quoted post (name, handle, avatar, text, images), or None.

    Handles app.bsky.embed.record#view and the record half of
    app.bsky.embed.recordWithMedia#view. Returns None for
    notFound/blocked/detached quotes.
    """
    e = post.get("embed") or {}
    t = e.get("$type", "")
    if t.startswith("app.bsky.embed.recordWithMedia"):
        rec = (e.get("record") or {}).get("record")
    elif t.startswith("app.bsky.embed.record"):
        rec = e.get("record")
    else:
        return None
    if not isinstance(rec, dict):
        return None
    # viewRecord carries author + value; notFound/blocked/detached do not.
    if not rec.get("author") or not isinstance(rec.get("value"), dict):
        return None
    author = rec["author"]
    imgs = []
    for em in rec.get("embeds", []) or []:
        imgs += _images_from_view(em)
    return {
        "name": author.get("displayName") or author.get("handle", ""),
        "handle": author.get("handle", ""),
        "avatar": author.get("avatar", ""),
        "text": rec["value"].get("text", ""),
        "images": imgs,
    }


def _quote_html(q, esc):
    """Render a quoted post as a smaller nested card, or '' when q is None."""
    if not q:
        return ""
    av = (f'<img class="qav" src="{esc(q["avatar"])}">' if q["avatar"]
          else '<div class="qav"></div>')
    qtext = f'<div class="qtext">{esc(q["text"])}</div>' if q["text"] else ""
    qimgs = "".join(
        f'<img class="qmedia" src="{esc(u)}" alt="{esc(alt)}">'
        for u, alt in q["images"]
    )
    return (
        f'<div class="quote"><div class="qhead">{av}'
        f'<div><div class="qname">{esc(q["name"])}</div>'
        f'<div class="qhandle">@{esc(q["handle"])}</div></div></div>'
        f'{qtext}{qimgs}</div>'
    )


def slide_html(post, idx, total, dark):
    esc = html.escape
    a = post["author"]
    name = esc(a.get("displayName") or a["handle"])
    handle = esc(a["handle"])
    avatar = a.get("avatar", "")
    text = esc(post["record"].get("text", ""))
    imgs = "".join(
        f'<img class="media" src="{esc(u)}" alt="{esc(alt)}">'
        for u, alt in embed_images(post)
    )
    quote = _quote_html(embed_quote(post), esc)
    bg, fg, sub = ("#161e27", "#f1f3f5", "#8b98a5") if dark else ("#ffffff", "#0b0f14", "#5b6b7b")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
html,body{{width:{W}px;background:{bg};color:{fg};
  font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Color Emoji",sans-serif}}
/* Height is content-driven, capped at {H}px by the fit step in JS. */
.wrap{{display:flex;flex-direction:column;padding:90px 90px 70px}}
.head{{display:flex;align-items:center;gap:28px;margin-bottom:50px}}
.av{{width:110px;height:110px;border-radius:50%;background:{sub};object-fit:cover;flex:none}}
.name{{font-size:44px;font-weight:700}}
.handle{{font-size:34px;color:{sub}}}
#body{{flex:1;display:flex;flex-direction:column;gap:36px}}
#text{{font-size:64px;line-height:1.3;white-space:pre-wrap;word-wrap:break-word}}
.media{{max-width:100%;max-height:600px;border-radius:24px;object-fit:contain;align-self:flex-start}}
.quote{{border:2px solid {sub};border-radius:24px;padding:32px 36px;display:flex;
  flex-direction:column;gap:20px}}
.qhead{{display:flex;align-items:center;gap:18px}}
.qav{{width:56px;height:56px;border-radius:50%;background:{sub};object-fit:cover;flex:none}}
.qname{{font-size:32px;font-weight:700}}
.qhandle{{font-size:26px;color:{sub}}}
.qtext{{font-size:40px;line-height:1.3;white-space:pre-wrap;word-wrap:break-word}}
.qmedia{{max-width:100%;max-height:360px;border-radius:16px;object-fit:contain;align-self:flex-start}}
.foot{{font-size:30px;color:{sub};text-align:right;margin-top:30px}}
</style></head><body><div class="wrap">
<div class="head">{f'<img class="av" src="{esc(avatar)}">' if avatar else '<div class="av"></div>'}
<div><div class="name">{name}</div><div class="handle">@{handle}</div></div></div>
<div id="body"><div id="text">{text}</div>{imgs}{quote}</div>
<div class="foot">{idx}/{total}</div>
</div></body></html>"""


# Shrink the main post text until the whole slide fits MAX_H, then report the
# final slide height (clamped to MAX_H). A slide shorter than MAX_H keeps its
# natural height so the PNG is cropped to the content instead of padded.
FIT_JS = """() => {
  const MAX_H = %d, MIN_FONT = 24;
  const t = document.getElementById('text');
  const wrap = document.querySelector('.wrap');
  const h = () => Math.ceil(wrap.getBoundingClientRect().height);
  let s = 64;
  while (h() > MAX_H && s > MIN_FONT) { s -= 2; t.style.fontSize = s + 'px'; }
  return Math.min(h(), MAX_H);
}""" % H


def thread_markdown(posts):
    """Human-readable, browser-free preview of the collected self-thread."""
    lines = []
    total = len(posts)
    for i, post in enumerate(posts, 1):
        a = post["author"]
        who = a.get("displayName") or a["handle"]
        lines.append(f"## {i}/{total} — {who} (@{a['handle']})")
        lines.append("")
        lines.append(post["record"].get("text", "") or "_(no text)_")
        for url, alt in embed_images(post):
            lines.append("")
            lines.append(f"- image: {url}" + (f" — alt: {alt}" if alt else ""))
        q = embed_quote(post)
        if q:
            lines.append("")
            lines.append(f"> **quoting {q['name']} (@{q['handle']})**")
            for para in (q["text"] or "").splitlines() or [""]:
                lines.append(f"> {para}")
            for url, alt in q["images"]:
                lines.append(f"> - image: {url}" + (f" — alt: {alt}" if alt else ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("-o", "--outdir", default="bsky_slides")
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--markdown", metavar="FILE",
                    help="write a text-only preview of the collected thread to FILE "
                         "(no browser needed) and skip PNG rendering")
    args = ap.parse_args()

    actor, rkey = parse_url(args.url)
    did = resolve_did(actor)
    posts = collect_self_thread(get_thread(f"at://{did}/app.bsky.feed.post/{rkey}"))

    if args.markdown:
        Path(args.markdown).write_text(thread_markdown(posts), encoding="utf-8")
        print(args.markdown)
        return

    from playwright.sync_api import sync_playwright

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # Tall viewport so an over-long slide renders fully before we measure and
        # shrink it; the final screenshot is clipped to the fitted height (<= H).
        page = browser.new_page(viewport={"width": W, "height": H * 4})
        for i, post in enumerate(posts, 1):
            page.set_content(slide_html(post, i, len(posts), args.dark), wait_until="networkidle")
            height = int(page.evaluate(FIT_JS))
            f = out / f"{i:02d}.png"
            # Crop to the fitted height so short posts get a shorter image.
            page.screenshot(path=str(f), clip={"x": 0, "y": 0, "width": W, "height": height})
            print(f)
        browser.close()


if __name__ == "__main__":
    main()
