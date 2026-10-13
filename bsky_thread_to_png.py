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


def resolve_profiles(dids):
    """Map each DID to its display name (falling back to handle) via getProfiles,
    batched 25 at a time. Returns {} for no DIDs; used to label in-text mentions."""
    names = {}
    dids = list(dids)
    for i in range(0, len(dids), 25):
        chunk = dids[i:i + 25]
        r = requests.get(f"{API}/app.bsky.actor.getProfiles",
                         params=[("actors", d) for d in chunk], timeout=20)
        r.raise_for_status()
        for prof in r.json().get("profiles", []):
            names[prof["did"]] = prof.get("displayName") or prof.get("handle", "")
    return names


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
    """Media images from a single embed *view* dict (not the quoted record).
    External embeds are handled as link cards (see _external_from_view), not as
    plain images."""
    t = (e or {}).get("$type", "")
    if t.startswith("app.bsky.embed.images"):
        return [(i["fullsize"], i.get("alt", "")) for i in e.get("images", [])]
    if t.startswith("app.bsky.embed.recordWithMedia"):
        return _images_from_view(e.get("media", {}))
    return []


def embed_images(post):
    return _images_from_view(post.get("embed") or {})


def _external_from_view(e):
    """Link-card fields from an external embed view, or None.
    Handles app.bsky.embed.external#view and the media half of recordWithMedia."""
    t = (e or {}).get("$type", "")
    if t.startswith("app.bsky.embed.recordWithMedia"):
        return _external_from_view(e.get("media", {}))
    if t.startswith("app.bsky.embed.external"):
        ext = e.get("external") or {}
        if ext.get("uri"):
            return {"uri": ext["uri"], "title": ext.get("title", ""),
                    "description": ext.get("description", ""), "thumb": ext.get("thumb", "")}
    return None


def embed_external(post):
    return _external_from_view(post.get("embed") or {})


def _domain(uri):
    """Bare display domain for a URL, e.g. https://www.aol.com/x -> aol.com."""
    m = re.match(r"https?://([^/?#]+)", uri)
    host = m.group(1) if m else uri
    return host[4:] if host.startswith("www.") else host


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


def _external_html(ext, esc):
    """Render an external embed as a Bluesky-style link card, or '' when None."""
    if not ext:
        return ""
    thumb = f'<img class="lcthumb" src="{esc(ext["thumb"])}" alt="">' if ext["thumb"] else ""
    domain = f'<div class="lcdomain">{esc(_domain(ext["uri"]))}</div>'
    title = f'<div class="lctitle">{esc(ext["title"])}</div>' if ext["title"] else ""
    desc = f'<div class="lcdesc">{esc(ext["description"])}</div>' if ext["description"] else ""
    return (f'<div class="linkcard">{thumb}'
            f'<div class="lcmeta">{domain}{title}{desc}</div></div>')


def _mention_facets(record):
    """(byteStart, byteEnd, did) for each mention facet in a post record."""
    out = []
    for f in record.get("facets") or []:
        idx = f.get("index") or {}
        bs, be = idx.get("byteStart"), idx.get("byteEnd")
        if bs is None or be is None:
            continue
        for feat in f.get("features") or []:
            if feat.get("$type", "").endswith("facet#mention") and feat.get("did"):
                out.append((bs, be, feat["did"]))
    return sorted(out)


def mention_dids(posts):
    """All DIDs mentioned across the thread's posts (for batch profile lookup)."""
    dids = set()
    for p in posts:
        for _, _, did in _mention_facets(p["record"]):
            dids.add(did)
    return dids


def render_text_html(record, esc, names=None):
    """Post text as safe HTML. Mention facets become a blue span showing the
    mentioned account's display name (from `names`: did -> displayName); when a
    did is unresolved, the handle text as written is kept. Facet byte offsets
    index the UTF-8 encoding, so we slice on bytes."""
    text = record.get("text", "") or ""
    spans = _mention_facets(record)
    if not spans:
        return esc(text)
    raw = text.encode("utf-8")
    names = names or {}
    out, pos = [], 0
    for bs, be, did in spans:
        if bs < pos:  # overlapping/out-of-order; skip
            continue
        out.append(esc(raw[pos:bs].decode("utf-8", "ignore")))
        name = names.get(did)
        label = name if name else raw[bs:be].decode("utf-8", "ignore")
        out.append(f'<span class="mention">{esc(label)}</span>')
        pos = be
    out.append(esc(raw[pos:].decode("utf-8", "ignore")))
    return "".join(out)


def canvas_bg_css(bgcolor):
    """Resolve the --bgcolor value to a CSS background for the canvas."""
    return "transparent" if bgcolor.strip().lower() in ("none", "transparent", "") else bgcolor


# Bluesky butterfly logo (official brand path), tinted via CSS `color`.
BSKY_SVG = (
    '<svg class="bsky" viewBox="0 0 568 501" xmlns="http://www.w3.org/2000/svg" '
    'aria-hidden="true"><path fill="currentColor" d="M123.121 33.6637C188.241 '
    '82.5526 258.281 181.681 284 234.873C309.719 181.681 379.759 82.5526 444.879 '
    '33.6637C491.866 -1.61183 568 -28.9064 568 57.9464C568 75.2916 558.055 203.659 '
    '552.222 224.501C531.947 296.954 458.067 315.434 392.347 304.249C507.222 323.8 '
    '536.444 388.56 473.333 453.32C353.473 576.312 301.061 422.461 287.631 '
    '383.039C285.169 375.812 284.017 372.431 284 375.306C283.983 372.431 282.831 '
    '375.812 280.369 383.039C266.939 422.461 214.527 576.312 94.6667 453.32C31.5556 '
    '388.56 60.7778 323.8 175.653 304.249C109.933 315.434 36.0535 296.954 15.7778 '
    '224.501C9.94525 203.659 0 75.2916 0 57.9464C0 -28.9064 76.1335 -1.61183 123.121 '
    '33.6637Z"/></svg>'
)


def _card_html(idx, post, total, esc, header=True, names=None):
    """One post card: author header, body (text, images, quote), and n/N footer.
    `header` can suppress the author row, but every card shows it by default.
    `names` labels in-text mentions. A Bluesky butterfly sits top-right."""
    text = render_text_html(post["record"], esc, names)
    imgs = "".join(
        f'<img class="media" src="{esc(u)}" alt="{esc(alt)}">'
        for u, alt in embed_images(post)
    )
    link = _external_html(embed_external(post), esc)
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
    return (f'<div class="card">{BSKY_SVG}{head}'
            f'<div class="body"><div class="text">{text}</div>{imgs}{link}{quote}</div>'
            f'<div class="foot">{idx}/{total}</div></div>')


def slide_group_html(group, total, dark, bgcolor=DEFAULT_BG, names=None):
    """A slide holding one or two posts. `group` is [(idx, post), ...]; each card
    shows the author header and its own n/N footer. Cards are stacked in a
    top-aligned .stack and float on the fixed {W}x{H} canvas. `names` labels
    in-text mentions (did -> display name)."""
    esc = html.escape
    bg, fg, sub = ("#161e27", "#f1f3f5", "#8b98a5") if dark else ("#ffffff", "#0b0f14", "#5b6b7b")
    canvas = canvas_bg_css(bgcolor)
    cards = "".join(
        _card_html(idx, post, total, esc, names=names)
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
.card{{width:100%;position:relative;background:{bg};border-radius:40px;overflow:hidden;
  display:flex;flex-direction:column;padding:46px 56px 52px}}
.bsky{{position:absolute;top:64px;right:56px;width:60px;height:auto;color:#1185fe}}
.head{{display:flex;align-items:center;gap:22px;margin-bottom:40px;padding-right:76px}}
.av{{width:88px;height:88px;border-radius:50%;background:{sub};object-fit:cover;flex:none}}
.name{{font-size:32px;font-weight:700}}
.handle{{font-size:26px;color:{sub}}}
.body{{flex:1;display:flex;flex-direction:column;gap:28px}}
.text{{font-size:48px;line-height:1.3;white-space:pre-wrap;word-wrap:break-word}}
.mention{{color:#1185fe}}
.media{{max-width:100%;max-height:520px;border-radius:20px;object-fit:contain;align-self:flex-start}}
.linkcard{{border:2px solid {sub};border-radius:20px;overflow:hidden;
  display:flex;flex-direction:column}}
.lcthumb{{width:100%;max-height:360px;object-fit:cover;display:block}}
.lcmeta{{padding:24px 30px;display:flex;flex-direction:column;gap:8px}}
.lcdomain{{font-size:24px;color:{sub}}}
.lctitle{{font-size:28px;font-weight:700;line-height:1.25}}
.lcdesc{{font-size:26px;color:{sub};line-height:1.3;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
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


def slide_html(post, idx, total, dark, bgcolor=DEFAULT_BG, names=None):
    """A single-post slide (thin wrapper over slide_group_html)."""
    return slide_group_html([(idx, post)], total, dark, bgcolor, names)


# Set the main text of every card to `uniformSize` (and the quote a bit smaller,
# so a quoted post never looks larger than the quoting one). Then, if the stack
# overflows CARD_MAX_H, compress each card's embeds first — quoted text, quoted
# image, link-card thumbnail — so the quoting post keeps its size, and only as a
# last resort shrink the main text of all cards together. Returns the main size
# it settled on (pass 1 uses this per single post to find the thread's minimum).
FIT_JS = """(uniformSize) => {
  const MAX_H = %d, MIN_MAIN = 20, MIN_QUOTE = 16, MIN_QIMG = 110, MIN_LCIMG = 160;
  const stack = document.querySelector('.stack');
  const cards = Array.from(document.querySelectorAll('.card'));
  const h = () => Math.ceil(stack.getBoundingClientRect().height);
  let s = uniformSize || 48;
  const setMain = px => cards.forEach(c => {
    const t = c.querySelector('.text'); if (t) t.style.fontSize = px + 'px';
  });
  // Quote text tracks the main size but stays smaller (and never below MIN_QUOTE).
  const qBase = Math.max(MIN_QUOTE, Math.min(30, s - 6));
  document.querySelectorAll('.qtext').forEach(q => q.style.fontSize = qBase + 'px');
  setMain(s);
  if (h() > MAX_H) {
    cards.forEach(c => {
      const q = c.querySelector('.qtext');
      if (q) { let qs = qBase; while (h() > MAX_H && qs > MIN_QUOTE) { qs -= 2; q.style.fontSize = qs + 'px'; } }
      const qm = c.querySelectorAll('.qmedia');
      if (qm.length) { let cap = 300; while (h() > MAX_H && cap > MIN_QIMG) { cap -= 20; qm.forEach(m => m.style.maxHeight = cap + 'px'); } }
      const lc = c.querySelectorAll('.lcthumb');
      if (lc.length) { let cap = 360; while (h() > MAX_H && cap > MIN_LCIMG) { cap -= 20; lc.forEach(m => m.style.maxHeight = cap + 'px'); } }
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
        ext = embed_external(post)
        if ext:
            lines.append("")
            lines.append(f"- link: {ext['title'] or _domain(ext['uri'])} — {ext['uri']}")
            if ext["description"]:
                lines.append(f"  {ext['description']}")
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
    names = resolve_profiles(mention_dids(posts))  # label in-text mentions

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
            page.set_content(slide_group_html(group, n, args.dark, args.bgcolor, names),
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
