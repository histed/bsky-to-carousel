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

## Next

- **Expand quoted user handles to display names.** Show the quoted account as
  `@First Last` (its `displayName`, no quotes) rather than the raw
  `@handle.bsky.social`. (Same idea may apply to in-text `@mentions` via
  facets.)
- **Link cards styled like Bluesky.** Pasted links / external embeds
  (`app.bsky.embed.external`) should render as Bluesky-style preview cards
  (chips/link-preview boxes: thumbnail, title, description, domain) instead of
  the current thumbnail-only / plain-truncated-URL treatment. Match Bluesky's
  visual layout as closely as practical.
  - Source fields: `embed.external.{uri, title, description, thumb}`.
  - Also revisit facets so in-text links render as links rather than the
    truncated `www.exa…` plain text currently shown.

## Known limitations (from the design doc)

- Facets (links/mentions) render as plain text.
- Video embeds not handled.
- Alt text not surfaced in the rendered image (only in `--markdown`).
