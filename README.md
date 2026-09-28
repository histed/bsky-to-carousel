# bsky-to-carousel

Turn a public Bluesky self-thread into one 1080×1350 (Instagram 4:5) PNG per post.
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

# Text-only preview of the collected thread — no browser needed
pixi run preview https://bsky.app/profile/HANDLE/post/RKEY --markdown preview.md
```

The tool walks up to the thread root and follows the author's own replies down,
ignoring other people's replies.

## Output

Each post becomes one `NN.png` in the output directory (`-o`, default
`bsky_slides/`), numbered `01.png`, `02.png`, … in thread order (root first).
Each slide shows the author's avatar, display name, `@handle`, the post text,
any embedded images, a quoted post (if any) as a smaller nested card, and an
`n/N` position footer.

**Size:** every image is **1080px wide**. Height is content-driven up to a
**1350px** cap (Instagram 4:5): a post longer than that has its text
auto-shrunk to fit 1350px, while a shorter post produces a shorter image
cropped to its content instead of being padded with empty space.

### Themes

**Light is the default; pass `--dark` for the dark theme.**

| Role | Light (default) | Dark (`--dark`) |
| --- | --- | --- |
| Background | `#ffffff` | `#161e27` |
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
