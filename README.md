# bsky-to-carousel

Turn a public Bluesky self-thread into one 1080×1350 (Instagram 4:5) PNG per
post, each a rounded post card floating on a colored (or transparent) canvas.
Design notes and rationale: [`docs/bsky_thread_to_png.md`](docs/bsky_thread_to_png.md).

## Setup

Managed with [pixi](https://pixi.sh):

```
pixi install                 # create the env (python, requests, playwright, pytest)
pixi run playwright install chromium   # one-time: browser for PNG rendering
```

## Usage

```
# Render PNGs, light theme (default) — needs chromium, see above
pixi run python bsky_thread_to_png.py https://bsky.app/profile/HANDLE/post/RKEY -o slides

# Same, dark theme
pixi run python bsky_thread_to_png.py https://bsky.app/profile/HANDLE/post/RKEY -o slides --dark

# Custom canvas color, or a transparent canvas for compositing later
pixi run python bsky_thread_to_png.py https://bsky.app/profile/HANDLE/post/RKEY -o slides --bgcolor "#ffd6e7"
pixi run python bsky_thread_to_png.py https://bsky.app/profile/HANDLE/post/RKEY -o slides --bgcolor none

# One post per slide (disable two-post packing)
pixi run python bsky_thread_to_png.py https://bsky.app/profile/HANDLE/post/RKEY -o slides --no-pack

# Text-only preview of the collected thread — no browser needed
pixi run preview https://bsky.app/profile/HANDLE/post/RKEY --markdown preview.md
```

The tool walks up to the thread root and follows the author's own replies down,
ignoring other people's replies.

## Output

Slides are written as `NN.png` in the output directory (`-o`, default
`bsky_slides/`), numbered `01.png`, `02.png`, … in thread order (root first).
Each card shows the author's avatar, display name, `@handle`, the post text,
any embedded images, a quoted post (if any) as a smaller nested card, and an
`n/N` footer (the post's position in the thread).

**Canvas:** every PNG is the same **1080×1350** (Instagram 4:5). A post renders
as a rounded card ~800px wide, centered with a transparent gutter each side and
top-aligned, so card height varies with content while the image size never
does. A card too tall for the canvas is auto-shrunk to fit (the quoted card
compresses first, the main text only as a last resort).

**Uniform text:** the whole carousel shares one main-text size — the smallest
any single post needs — so type is consistent slide to slide (one very long
post pulls every slide down to its size).

**Two-up packing:** by default, two consecutive posts share a slide when both
fit at that size, so the slide count can be less than the post count. Each card
keeps its own author header and `n/N` footer. Pass `--no-pack` for strictly one
post per slide.

**Background:** `--bgcolor HEX` fills the canvas behind the card (default
`#bde0fe`, a light sky blue). `--bgcolor none` makes the canvas transparent and
writes RGBA PNGs, so you can drop in your own background afterward.

### Posting to Instagram

The PNGs are 1080×1350 (4:5 portrait), the tallest size Instagram shows in-feed.
When you add them in the Instagram composer, **tap the crop/aspect icon** (the
`⤢` two-arrows button at the bottom-left of the preview) and choose **4:5 /
original** — otherwise Instagram defaults to a square (1:1) crop and cuts off
the top and bottom of each card. For a carousel, set it on the first image and
Instagram applies that ratio to all of them. (Instagram carousels hold up to 20
images.)

### Themes

**Light is the default; pass `--dark` for the dark theme.**

| Role | Light (default) | Dark (`--dark`) |
| --- | --- | --- |
| Card background | `#ffffff` | `#161e27` |
| Text | `#0b0f14` | `#f1f3f5` |
| Secondary (handle, footer, avatar placeholder) | `#5b6b7b` | `#8b98a5` |

## Tasks

| Task | Command | What it does |
| --- | --- | --- |
| `pixi run test` | `pytest -q` | Offline unit-test suite (no network). |
| `pixi run preview <url> --markdown FILE` | script | Fetch a real thread and write a readable Markdown dump to `FILE`. |

## Tests

- **Default suite is offline** — pure functions (`parse_url`, `embed_images`,
  `collect_self_thread`, `slide_html`, `thread_markdown`) tested against
  hand-built fixtures. Run with `pixi run test`.
- **Live API tests are opt-in** (guard against Bluesky API drift), skipped
  unless `LIVE_TESTS=1`:

  ```
  LIVE_TESTS=1 pixi run pytest tests/test_live_api.py -q
  ```
