# Plan

Roadmap and pending decisions for bsky-to-carousel. Design rationale lives in
[`docs/bsky_thread_to_png.md`](docs/bsky_thread_to_png.md); usage in
[`README.md`](README.md).

## Done

- Extract script from design doc; verify Bluesky API field names against the live API.
- pixi-managed env; offline unit tests + opt-in live API tests.
- `--markdown` browser-free thread preview.
- Variable slide height: short posts crop to content, long posts fill 1350px with font auto-shrink.
- Render quoted posts as a smaller nested card (avatar, name, @handle, text, quoted image).

## Next

- **Uniform slide size + pack two posts when there's room.** Revisit the current
  content-driven height: instead go back to a **fixed, always-identical PNG
  size** (1080×1350) for every slide, but when a post leaves lots of empty space
  at the bottom, fit the *next* post onto the same slide (with a divider)
  instead of padding. Effectively a bin-packing pass over the thread: fill each
  fixed-size slide with one or more consecutive posts. Supersedes the shipped
  variable-height behavior.
  - Open questions: min gap before packing a second post; never split a single
    post across slides; how `n/N` numbering works when a slide holds >1 post.
- **Quote sizing: keep the quoting post at normal text size.** When a slide has
  a quote and overflows, the fit step currently shrinks the *main* post text
  while the quote card stays large (backwards). The quoting post should render
  at normal size (as if there were no quote), and the *quoted* post should be
  the smaller, compressible part.
- **Expand quoted user handles to display names.** Show the quoted account as
  `@"First Last"` (its `displayName`) rather than the raw
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
