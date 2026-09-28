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


def embed_images(post):
    e = post.get("embed") or {}
    t = e.get("$type", "")
    if t.startswith("app.bsky.embed.images"):
        return [(i["fullsize"], i.get("alt", "")) for i in e.get("images", [])]
    if t.startswith("app.bsky.embed.recordWithMedia"):
        m = e.get("media", {})
        return [(i["fullsize"], i.get("alt", "")) for i in m.get("images", [])]
    if t.startswith("app.bsky.embed.external"):
        th = e.get("external", {}).get("thumb")
        return [(th, "")] if th else []
    return []


def slide_html(post, idx, total, dark):
    a = post["author"]
    name = html.escape(a.get("displayName") or a["handle"])
    handle = html.escape(a["handle"])
    avatar = a.get("avatar", "")
    text = html.escape(post["record"].get("text", ""))
    imgs = "".join(
        f'<img class="media" src="{html.escape(u)}" alt="{html.escape(alt)}">'
        for u, alt in embed_images(post)
    )
    bg, fg, sub = ("#161e27", "#f1f3f5", "#8b98a5") if dark else ("#ffffff", "#0b0f14", "#5b6b7b")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
html,body{{width:{W}px;height:{H}px;background:{bg};color:{fg};
  font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Color Emoji",sans-serif}}
.wrap{{display:flex;flex-direction:column;height:100%;padding:90px 90px 70px}}
.head{{display:flex;align-items:center;gap:28px;margin-bottom:50px}}
.av{{width:110px;height:110px;border-radius:50%;background:{sub};object-fit:cover}}
.name{{font-size:44px;font-weight:700}}
.handle{{font-size:34px;color:{sub}}}
#body{{flex:1;overflow:hidden;display:flex;flex-direction:column;gap:36px}}
#text{{font-size:64px;line-height:1.3;white-space:pre-wrap;word-wrap:break-word}}
.media{{max-width:100%;max-height:600px;border-radius:24px;object-fit:contain;align-self:flex-start}}
.foot{{font-size:30px;color:{sub};text-align:right;margin-top:30px}}
</style></head><body><div class="wrap">
<div class="head">{f'<img class="av" src="{html.escape(avatar)}">' if avatar else '<div class="av"></div>'}
<div><div class="name">{name}</div><div class="handle">@{handle}</div></div></div>
<div id="body"><div id="text">{text}</div>{imgs}</div>
<div class="foot">{idx}/{total}</div>
</div></body></html>"""


FIT_JS = """() => {
  const b = document.getElementById('body'), t = document.getElementById('text');
  let s = 64;
  while (b.scrollHeight > b.clientHeight && s > 24) { s -= 2; t.style.fontSize = s + 'px'; }
}"""


def main():
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("-o", "--outdir", default="bsky_slides")
    ap.add_argument("--dark", action="store_true")
    args = ap.parse_args()

    actor, rkey = parse_url(args.url)
    did = resolve_did(actor)
    posts = collect_self_thread(get_thread(f"at://{did}/app.bsky.feed.post/{rkey}"))

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        for i, post in enumerate(posts, 1):
            page.set_content(slide_html(post, i, len(posts), args.dark), wait_until="networkidle")
            page.evaluate(FIT_JS)
            f = out / f"{i:02d}.png"
            page.screenshot(path=str(f))
            print(f)
        browser.close()


if __name__ == "__main__":
    main()
