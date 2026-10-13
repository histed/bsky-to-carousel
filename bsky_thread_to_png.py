#!/usr/bin/env python3
"""
Bluesky thread -> one PNG per post. Each PNG is a fixed 1080x1350 (Instagram
4:5) canvas with a solid --bgcolor (default light sky blue) or transparent; the
post renders as a rounded card ~800px wide, centered and top-aligned, whose
height follows its content.

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
# Canvas is a fixed, transparent 1080x1350 (4:5). The card floats on it: a fixed
# width, centered with a transparent gutter each side, top-aligned, with a
# transparent margin above and below. The card's height is content-driven and
# capped (CARD_MAX_H) so it always fits the canvas.
W, H = 1080, 1350
CARD_W = 800          # card width; the rest of the 1080 is transparent gutter
CARD_TOP = 70         # margin above (and min below) the card, shows the canvas bg
CARD_GAP = 32         # transparent gap between two cards packed on one slide
CARD_MAX_H = H - 2 * CARD_TOP
DEFAULT_BG = "#bde0fe"  # light sky blue canvas; --bgcolor none for transparent


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


def canvas_bg_css(bgcolor):
    """Resolve the --bgcolor value to a CSS background for the canvas."""
    return "transparent" if bgcolor.strip().lower() in ("none", "transparent", "") else bgcolor


def _card_html(idx, post, total, esc, header=True):
    """One post card: author header, body (text, images, quote), and n/N footer.
    `header` can suppress the author row, but every card shows it by default."""
    text = esc(post["record"].get("text", ""))
    imgs = "".join(
        f'<img class="media" src="{esc(u)}" alt="{esc(alt)}">'
        for u, alt in embed_images(post)
    )
    quote = _quote_html(embed_quote(post), esc)
    head = ""
    if header:
        a = post["author"]
        name = esc(a.get("displayName") or a["handle"])
        handle = esc(a["handle"])
        avatar = a.get("avatar", "")
        av = f'<img class="av" src="{esc(avatar)}">' if avatar else '<div class="av"></div>'
        head = (f'<div class="head">{av}'
                f'<div><div class="name">{name}</div>'
                f'<div class="handle">@{handle}</div></div></div>')
    return (f'<div class="card">{head}'
            f'<div class="body"><div class="text">{text}</div>{imgs}{quote}</div>'
            f'<div class="foot">{idx}/{total}</div></div>')


def slide_group_html(group, total, dark, bgcolor=DEFAULT_BG):
    """A slide holding one or two posts. `group` is [(idx, post), ...]; each card
    shows the author header and its own n/N footer. Cards are stacked in a
    top-aligned .stack and float on the fixed {W}x{H} canvas."""
    esc = html.escape
    bg, fg, sub = ("#161e27", "#f1f3f5", "#8b98a5") if dark else ("#ffffff", "#0b0f14", "#5b6b7b")
    canvas = canvas_bg_css(bgcolor)
    cards = "".join(
        _card_html(idx, post, total, esc)
        for idx, post in group
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
html,body{{width:{W}px;background:transparent;color:{fg};
  font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Color Emoji",sans-serif}}
/* Fixed {W}x{H} canvas (transparent or a solid --bgcolor). One or two cards
   stack in .stack ({CARD_W}px wide, centered, top-aligned); the stack height is
   content-driven and capped at {CARD_MAX_H}px by the fit step in JS. */
.canvas{{width:{W}px;height:{H}px;background:{canvas};
  display:flex;justify-content:center;align-items:flex-start;padding:{CARD_TOP}px 0}}
.stack{{width:{CARD_W}px;display:flex;flex-direction:column;gap:{CARD_GAP}px}}
.card{{width:100%;background:{bg};border-radius:40px;overflow:hidden;
  display:flex;flex-direction:column;padding:64px 56px 52px}}
.head{{display:flex;align-items:center;gap:22px;margin-bottom:40px}}
.av{{width:88px;height:88px;border-radius:50%;background:{sub};object-fit:cover;flex:none}}
.name{{font-size:36px;font-weight:700}}
.handle{{font-size:28px;color:{sub}}}
.body{{flex:1;display:flex;flex-direction:column;gap:28px}}
.text{{font-size:48px;line-height:1.3;white-space:pre-wrap;word-wrap:break-word}}
.media{{max-width:100%;max-height:520px;border-radius:20px;object-fit:contain;align-self:flex-start}}
.quote{{border:2px solid {sub};border-radius:20px;padding:26px 30px;display:flex;
  flex-direction:column;gap:16px}}
.qhead{{display:flex;align-items:center;gap:14px}}
.qav{{width:46px;height:46px;border-radius:50%;background:{sub};object-fit:cover;flex:none}}
.qname{{font-size:26px;font-weight:700}}
.qhandle{{font-size:21px;color:{sub}}}
.qtext{{font-size:30px;line-height:1.3;white-space:pre-wrap;word-wrap:break-word}}
.qmedia{{max-width:100%;max-height:300px;border-radius:14px;object-fit:contain;align-self:flex-start}}
.foot{{font-size:24px;color:{sub};text-align:right;margin-top:26px}}
</style></head><body><div class="canvas"><div class="stack">{cards}</div></div></body></html>"""


def slide_html(post, idx, total, dark, bgcolor=DEFAULT_BG):
    """A single-post slide (thin wrapper over slide_group_html)."""
    return slide_group_html([(idx, post)], total, dark, bgcolor)


# Set the main text of every card on the slide to `uniformSize`, then, if the
# stack overflows CARD_MAX_H, compress each card's quote first (quoted text, then
# quoted image) so the quoting post keeps its size, and only as a last resort
# shrink the main text of all cards together. Returns the main size it settled on
# (pass 1 uses this per single post to find the smallest size the thread needs).
FIT_JS = """(uniformSize) => {
  const MAX_H = %d, MIN_MAIN = 20, MIN_QUOTE = 16, MIN_QIMG = 110;
  const stack = document.querySelector('.stack');
  const cards = Array.from(document.querySelectorAll('.card'));
  const h = () => Math.ceil(stack.getBoundingClientRect().height);
  let s = uniformSize || 48;
  const setMain = px => cards.forEach(c => {
    const t = c.querySelector('.text'); if (t) t.style.fontSize = px + 'px';
  });
  setMain(s);
  if (h() > MAX_H) {
    cards.forEach(c => {
      const q = c.querySelector('.qtext');
      if (q) { let qs = 30; while (h() > MAX_H && qs > MIN_QUOTE) { qs -= 2; q.style.fontSize = qs + 'px'; } }
      const qm = c.querySelectorAll('.qmedia');
      if (qm.length) { let cap = 300; while (h() > MAX_H && cap > MIN_QIMG) { cap -= 20; qm.forEach(m => m.style.maxHeight = cap + 'px'); } }
    });
    while (h() > MAX_H && s > MIN_MAIN) { s -= 2; setMain(s); }
  }
  return s;
}""" % CARD_MAX_H


# Set all cards' main text to `uniformSize` and return the stack height, without
# any compression. Used to decide whether two posts naturally fit on one slide.
MEASURE_JS = """(uniformSize) => {
  const stack = document.querySelector('.stack');
  document.querySelectorAll('.text').forEach(t => t.style.fontSize = (uniformSize || 48) + 'px');
  return Math.ceil(stack.getBoundingClientRect().height);
}"""


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
    ap.add_argument("--bgcolor", default=DEFAULT_BG,
                    help=f"canvas background as a hex color (default {DEFAULT_BG}, a light "
                         f"sky blue); use 'none' for a transparent canvas")
    ap.add_argument("--no-pack", action="store_true",
                    help="one post per slide; by default two consecutive posts share "
                         "a slide when both fit")
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
        n = len(posts)
        indexed = list(enumerate(posts, 1))  # [(idx, post), ...]

        def show(group):
            page.set_content(slide_group_html(group, n, args.dark, args.bgcolor),
                             wait_until="networkidle")

        # Pass 1: smallest main-text size any single post needs, so the whole
        # carousel can share one uniform size.
        uniform = 48
        for idx, post in indexed:
            show([(idx, post)])
            uniform = min(uniform, int(page.evaluate(FIT_JS, 48)))

        # Group consecutive posts: pack two on a slide when they fit at `uniform`.
        groups, i = [], 0
        while i < len(indexed):
            if not args.no_pack and i + 1 < len(indexed):
                pair = [indexed[i], indexed[i + 1]]
                show(pair)
                if int(page.evaluate(MEASURE_JS, uniform)) <= CARD_MAX_H:
                    groups.append(pair)
                    i += 2
                    continue
            groups.append([indexed[i]])
            i += 1

        # Pass 2: render each slide at the uniform size.
        for s, group in enumerate(groups, 1):
            show(group)
            page.evaluate(FIT_JS, uniform)  # quotes still compress; main stays uniform
            f = out / f"{s:02d}.png"
            # Every PNG is the full fixed canvas; omit_background keeps a
            # 'none' bgcolor transparent in the output.
            page.screenshot(path=str(f), clip={"x": 0, "y": 0, "width": W, "height": H},
                            omit_background=True)
            print(f)
        browser.close()


if __name__ == "__main__":
    main()
