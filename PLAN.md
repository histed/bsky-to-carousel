# Plan

Roadmap and pending decisions for bsky-to-carousel. Design rationale lives in
[`docs/bsky_thread_to_png.md`](docs/bsky_thread_to_png.md); usage in
[`README.md`](README.md).

## Done

- Extract script from design doc; verify Bluesky API field names against the live API.
- pixi-managed env; offline unit tests + opt-in live API tests.
- `--markdown` browser-free thread preview.
- Render quoted posts as a smaller nested card (avatar, name, @handle, text, quoted image).
- **Fixed canvas, floating variable-height card.** Every PNG is an identical
  1080×1350 (4:5) canvas; the post renders as a rounded card ~800px wide,
  centered with a transparent gutter each side and top-aligned, whose height
  follows its content. The card shrinks to fit when it would overflow.
- **Canvas background.** `--bgcolor HEX` fills the canvas (default `#bde0fe`, a
  light sky blue); `--bgcolor none` leaves it transparent (RGBA output) for
  compositing a background later.
- **Quote sizing: keep the quoting post at normal text size.** On overflow the
  fit step compresses the *quoted* card (quote text, then quoted image) and only
  shrinks the main post text as a last resort, so the quoting post reads as if
  there were no quote.
- **Uniform text size across the carousel.** A two-pass render finds the
  smallest main-text size any single post needs and pins every slide to it, so
  type is consistent across all slides rather than varying per post.
- **Pack two posts per slide.** Two consecutive posts share one slide when both
  fit at the uniform size (greedy, max two per slide); `--no-pack` keeps one per
  slide. Each card keeps its own author header and `n/N` footer. PNGs are
  numbered by slide; footers stay by post position.
- **Bluesky-style link cards.** External embeds (`app.bsky.embed.external`, and
  the media half of `recordWithMedia`) render as a preview card: thumbnail on
  top, then domain, title, and a clamped description. Replaces the old
  thumbnail-only treatment. In-text link facets are still plain text (see Next).

- **Bluesky butterfly watermark.** The Bluesky butterfly (inline SVG, Bluesky
  blue) sits in the top-right of every card, vertically aligned with the avatar.
- **In-text mentions as blue display names.** Mention facets in the body render
  as a blue span showing the mentioned account's display name with no `@` (e.g.
  `Brian Beutler` instead of `@brianbeutler.bsky.social`). DIDs are resolved
  once per run via `getProfiles`; an unresolved mention keeps the handle text.
- **Quoted account shown by display name.** The nested quote card shows the
  quoted account's display name (bold) with its `@handle` beneath. (Mentions in
  the quoted post's body are not expanded — only the quoting post's text is.)

## Next

_Nothing planned right now._

## Known limitations (from the design doc)

- In-text link facets stay as plain (often truncated) text — intentionally not
  linkified (the link card already shows the destination).
- Video embeds not handled.
- Alt text not surfaced in the rendered image (only in `--markdown`).
