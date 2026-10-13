# Handoff: Uniform type + two-post packing (unverified, uncommitted)

**Created:** 2026-10-12 00:28
**Branch:** main (nothing pushed)
**Session Duration:** ~1 hr

---

## Summary

Shipped and committed (`d20d93a`) the fixed 1080×1350 canvas with a floating, variable-height rounded card and a `--bgcolor` flag. After that commit, two more features were written but are **uncommitted and untested**: uniform main-text size across all slides (two-pass), and packing two consecutive posts onto one slide. The code byte-compiles. `pixi run test` and a real render have **not** been run since the packing change.

---

## Work Completed

### Committed (`d20d93a`)
- [x] Fixed canvas: every PNG is 1080×1350. The post is a rounded card 800px wide (`CARD_W`), centered, top-aligned, with a 70px margin (`CARD_TOP`) and a height cap `CARD_MAX_H=1210`.
- [x] `--bgcolor HEX`, default `#bde0fe` (light sky blue). `--bgcolor none` gives a transparent RGBA canvas. Both were checked at the pixel level.
- [x] Quote-first shrink order: quote text, then quote image, with main text last. This was the previous handoff's in-progress work.
- [x] Type scaled about 0.75 for the 800px card: main text 48px, quote text 30px, name 36px.
- [x] PLAN.md: quote sizing and fixed canvas moved to Done. Removed the outdated "uniform slide + bin-packing supersedes variable height" item. README documents the canvas, card, and `--bgcolor`.

### Uncommitted (user said "no commits for now")
- [ ] **Uniform type (two-pass).** Pass 1 renders each post alone and runs `FIT_JS(48)`. `FIT_JS` returns the main size the post settled on, and the run takes the minimum of those as `uniform`. Pass 2 renders every slide at `uniform`. Before packing was added, this was verified with all 11 slides at 38px.
- [ ] **Two-post packing (on by default, `--no-pack` turns it off).** Posts are paired greedily in order. If two consecutive posts fit together at `uniform` (`MEASURE_JS` stack height ≤ `CARD_MAX_H`, measured with no compression), they share a slide. A slide holds at most 2 posts.
- [ ] On a packed slide, the second card **omits the author header** (avatar, name, handle) but **keeps its `n/N` footer**.
- [ ] Two new tests: `test_slide_group_two_cards_and_one_header` and `test_slide_group_single_matches_slide_html`.

### Key Decisions

| Decision | Rationale | Alternatives |
| --- | --- | --- |
| Fixed canvas, variable-height card | User wants every image the same size and every card a different height | Crop each PNG to its content (old behavior) |
| Card 800 wide, top-aligned, gutter on all sides | User will put a colored background behind it | Full width, or vertically centered |
| Uniform font = smallest any post needs (no floor) | User chose consistent type across the carousel | A floor size, or sizing each slide separately |
| Two **separate stacked cards** with a 32px gap (`CARD_GAP`) | User's choice; matches the single-card look | One card with a divider |
| Pack by default, `--no-pack` to disable | User's choice | Off by default with `--pack` |
| Footer stays per post (`idx/total_posts`). PNG filenames are numbered per slide | Avoids ambiguous numbering on packed slides | Number by slide |
| `uniform` is computed from single posts, and pairs are packed only if they fit at `uniform` | No circular dependency: every single post fits at `uniform`, and a pair is packed only when it fits | A joint optimization |

---

## Files Affected

### Modified (uncommitted)
- `bsky_thread_to_png.py`
  - New constant `CARD_GAP = 32`
  - `_card_html(idx, post, total, esc, header=True)`: a new helper that builds one card
  - `slide_group_html(group, total, dark, bgcolor)`: new. `group` is `[(idx, post), ...]`. The cards sit inside `.canvas > .stack`
  - `slide_html(post, idx, total, dark, bgcolor)`: now a thin wrapper, so the existing tests are unchanged
  - CSS: `#body`/`#text` became the **classes** `.body`/`.text`, because two cards would otherwise duplicate the IDs. Added `.stack`. `.card` is now `width:100%`
  - `FIT_JS(uniformSize)`: iterates over all `.card`s and measures `.stack`. It compresses quotes per card, then shrinks every card's main text together. It returns the settled size
  - `MEASURE_JS(uniformSize)`: new. It sets the text size and returns the stack height without compressing anything
  - `main()`: `--no-pack` arg, then pass 1 → grouping → pass 2
- `tests/test_bsky_thread_to_png.py`: two packing tests added at the end

### Untracked, not created this session
- `slides/` and `.DS_Store` at the repo root. Ask the user before deleting or ignoring them.

---

## Technical Context

- `FIT_JS` and `MEASURE_JS` run in the browser and are **not** covered by the offline suite. Verify them by rendering.
- Pass 1 uses `FIT_JS`, which compresses as needed. The packing check uses `MEASURE_JS`, which never compresses. That way a pair is never packed because compression squeezed it to fit.
- Scratch helpers live in the session scratchpad and are not in the repo. To measure font sizes, render with `page.evaluate(FIT_JS, uniform)` and then read `getComputedStyle(.text).fontSize`.

---

## Things to Know

### Gotchas
- The conda-forge `playwright` is the Node CLI. Use `pixi add --pypi playwright`.
- Inline `python -c` with multiple lines gets mangled. Use heredoc files in the scratchpad.
- Scratch scripts that import the module need `PYTHONPATH=<repo>`.
- The old `measure_fonts.py` scratch script calls `FIT_JS` without the uniform argument, so it reports per-slide sizes instead of the uniform size. Don't trust it for checking uniformity.

### Known Issues
- **Live test failing:** `tests/test_live_api.py::test_get_thread_and_collect_shapes` gets HTTP 400 from `getPostThread`. The post it discovers is `at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.post/3mxk7gsrfxs2w`, with `depth=1000&parentHeight=1000`. This failure predates the current work. Investigate how the test chooses its input.
- Because type is uniform, one very long post pulls the whole carousel down to its size. That is the accepted tradeoff, and a floor option remains possible.
- Quote text size can still differ between slides, because quotes compress only when their own slide needs it.

---

## Current State

### Tests
- [x] Committed state: 40 passed, 2 skipped (offline)
- [ ] **Uncommitted packing code: `pixi run test` NOT run** (it byte-compiles)
- [ ] Packed render: NOT done
- [x] Uniform type before packing: rendered and measured, all slides at 38px

---

## Next Steps

### Immediate (Start Here)
1. `pixi run test` should give 42 passed, 2 skipped. Fix any failures.
2. Render the test thread and check it:
   ```bash
   rm -rf bsky_slides/markhisted-thread   # stale 11-slide output would mix with fewer slides
   pixi run python bsky_thread_to_png.py https://bsky.app/profile/markhisted.org/post/3mwhjmmcnsk2j -o bsky_slides/markhisted-thread
   ```
   Expect fewer than 11 PNGs. On packed slides the second card should have no header but should keep its `n/N`. All cards should be the same text size and no stack should overflow. Also run once with `--no-pack` to confirm 11 slides.
3. Update the README (uniform type, packing, `--no-pack`, PNG count ≠ post count) and PLAN.md (move both to Done). Commit when the user allows it. Commits were paused this session at the user's request, so ask first.

### Subsequent (PLAN.md "Next")
- Fix the failing live test (HTTP 400)
- Expand quoted handles to `@Display Name` (no quotes)
- Bluesky-style link cards (`embed.external.{uri,title,description,thumb}`) and facets
- Housekeeping: `slides/` and `.DS_Store`, and mark the old handoff `HANDOFF_QUOTE_SIZING_09_27_23_40.md` as superseded

---

## Commands

```bash
pixi run test                                                # offline suite
LIVE_TESTS=1 pixi run pytest tests/test_live_api.py -q       # live API (1 currently failing)
pixi run python bsky_thread_to_png.py <url> -o DIR [--dark] [--bgcolor HEX|none] [--no-pack]
```

---

## User Preferences (this session)
- Keep responses short. The user is token-conscious and asked to stop at clean boundaries.
- **Commits paused** at the user's request ("move on from any commits"). Ask before committing. Never push.
- Ask about real design branches before building. Otherwise pick a sensible default and say which one.

---

_This handoff was generated to checkpoint work. Start a new session and use this document as your initial context._
