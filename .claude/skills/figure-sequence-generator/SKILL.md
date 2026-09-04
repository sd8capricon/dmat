---
name: figure-sequence-generator
description: Generate dMAT-style "Figure Sequence" reasoning practice questions (matrices of shapes that move/rotate/change colour across a sequence) as a self-contained HTML file with expandable per-question solutions. Use when the user asks to create, generate, or add more figure-sequence / matrix-sequence practice questions, at one or more difficulty levels (easy/medium/hard), for dMAT prep in this project.
---

# Figure Sequence Question Generator

## Why this exists

Figure-sequence items look easy to hand-author but are extremely easy to get
subtly wrong: an LLM freehand-drawing "Matrix 5" and four answer options has
no guarantee that exactly one option is correct, that figures don't overlap
or leave the grid, or that a "wrong" option isn't accidentally identical to
the right one. The fix used here is **never author a sequence by hand** —
always generate it procedurally:

1. Randomly sample a rule (position / orientation / colour) per figure.
2. Simulate matrices 1–6 deterministically from that rule.
3. Reject and retry if any matrix has an out-of-bounds or overlapping figure.
4. Build wrong-answer options by deliberately mutating exactly one channel of
   one figure away from the simulated truth (never a fresh redraw).

This guarantees, by construction, a unique determinable answer per
sub-question — which is exactly what the task requires. All of this logic is
already implemented in `scripts/generate_fs.py`; do not re-derive it by hand
in the conversation.

## When to use this skill

Trigger when the user asks for new figure-sequence / matrix-sequence
practice questions for dMAT, in this project, specifying (or implying) a
question count and one or more difficulty levels.

## Step 1 — Gather inputs

You need, at minimum:
- **Total number of questions**.
- **Difficulty level(s)**: easy, medium, hard, or a mix.

If the user gives an exact per-tier split ("10 easy, 5 medium, 5 hard"), use
it directly. If they give only a total and a set of tiers ("20 questions,
mix of medium and hard"), split as evenly as possible across the requested
tiers, putting any remainder on the hardest requested tier. If the user gives
only a total with no tier info, ask (via AskUserQuestion) which tier(s) they
want, defaulting the recommended option to an even split across all three
tiers.

## Step 2 — Compute the output filename

Format: `FS-<yymmdd>-<total-questions>.html` (e.g. `FS-260902-20.html`),
using **today's date**. Save it in the project root (the directory the user
is working in) unless they specify otherwise. Do not overwrite an existing
file with the same name from the same day without confirming — append `-2`,
`-3`, etc. if needed.

## Step 3 — Run the generator

```
python3 .claude/skills/figure-sequence-generator/scripts/generate_fs.py \
  --easy <N> --medium <N> --hard <N> --out <filename>.html
```

Omit any of `--easy/--medium/--hard` that are 0. Add `--seed <int>` only if
the user explicitly wants reproducible output across runs; otherwise leave
it unset so repeated invocations produce fresh variety.

The script is self-verifying (bounds + overlap checks with automatic retry,
and exactly-one-correct-option construction for every sub-question) — a
successful run with no traceback means the output is structurally valid.
Sanity-check the printed summary line matches the requested counts.

## Step 4 — Verify visually before reporting done

Render the HTML (e.g. headless-screenshot it, or open it) and spot-check:
- Shapes are visually distinct within each question (they will be, since the
  script only draws from a pool of rotation-asymmetric shapes and samples
  without replacement — see Constraints below).
- Figures don't visually overlap in any matrix.
- At least one "Show answer & reasoning" panel expands to readable,
  per-figure position/orientation/colour rule text, independently of the
  others (native `<details>` — no extra JS needed for that part).

Report the final file path and question-count breakdown to the user.

## Difficulty tiers (already encoded in `TIERS` in the script)

| Tier   | Figures | x+1 budget | Diagonal movers | Colour cycle length |
|--------|---------|-----------|------------------|----------------------|
| Easy   | 1       | 0 (constant steps only) | no  | 1–2 |
| Medium | 2       | 1 slot across the item  | yes | 1–3 |
| Hard   | 3–4     | 3 slots across the item | yes | 2–3 |

"x+1 budget" = how many (figure, channel) slots in that item may use the
x+1 stepping rule (step 1, then 2, then 3, then 4, then 5 — the thing that
actually makes a sequence hard, since you must convert positions to
path-length-travelled to detect it instead of reading raw coordinates).
More figures and more x+1 usage is what separates hard from easy — not
cosmetic changes.

If asked to adjust difficulty balance or add a new tier, edit `TIERS` and
the sampling weights in `random_figure()` inside `generate_fs.py` rather
than hand-writing new question logic in the conversation.

## Constraints and pitfalls learned building this (do not relitigate)

- **Grid is 4×4** (row 1 = top, column 1 = left). This is a deliberate
  simplification of the real exam's grammar (verified against
  `260716_dMAT_General-Academic-Module_Preparatoy-Materials_EN.pdf` pages
  7–15 and `Nbyula-dMAT-Guide.pdf` pages 14–18 and 116–143, which describe a
  4×4 grid explicitly and show worked items). If a wider grid is ever
  needed, `GRID_R`/`GRID_C` and `RING_CW` (the 12-cell border ring) must be
  updated together and every simulation function re-verified.
- **The rule grammar is closed** — only these things may ever happen to a
  figure: change colour, rotate around its own axis, move vertically/
  horizontally/diagonally (a diagonal mover can never switch to another
  movement type), and any of position/orientation/colour may advance by a
  constant amount or by x+1. Figures never disappear, never overlap, never
  leave the matrix; on hitting the outer wall they either bounce off or
  travel along the border. Do not invent rule types outside this list.
- **Diagonal bounce**: only the axis component that hits the wall reverses;
  at a corner both components reverse. The mover stays diagonal afterwards.
- **Shape choice is rotation-sensitivity-constrained**: only use shapes
  whose 4 possible 90° rotations (0/90/180/270) are all visually distinct.
  The current pool (`house`, `pin`, `arrow`, `chevron`, `flag`) is verified
  by eye. A circle, plain square, or regular hexagon must **not** be added
  with a rotating orientation channel — their rotations look identical or
  ambiguous, which breaks "exactly one determinable answer" (two options
  could render pixel-identical despite differing internally). If a
  symmetric shape is ever wanted, force `orient_mode='fixed'` for it.
- **Distinct shapes per item**: figures within one question always use
  distinct shapes (sampled without replacement) so a solver is never stuck
  disambiguating "which figure is which" by colour alone.
- **Colour must contrast the page background.** The palette
  (`charcoal #37474F, orange #FB8C00, blue #1E88E5, yellow #FDD835`) was
  chosen to read clearly on a **light** page background, matching the real
  material's own look. Do not port this onto a dark theme — a first attempt
  at this made `charcoal` figures nearly invisible against a dark panel
  colour. If the page theme ever changes, re-check contrast for every
  colour in the palette against the new background.
- **Distractor construction, not redraws**: every wrong option is generated
  by taking the correct combo and mutating exactly one figure's one channel
  (position → previous matrix's position, or a one-cell nudge if the figure
  didn't move that step; orientation → previous matrix's degree, or +90° if
  it doesn't rotate; colour → previous matrix's colour, or a different
  palette colour if it doesn't cycle). This mirrors the single most common
  real trap ("correct movement, colour one step out of phase") instead of
  generating arbitrary wrong pictures that could accidentally look more
  "right" than the real answer. Always de-duplicate against the correct
  combo and against each other, and reject any option whose figures overlap.
- **Two-part answer, always**: every item asks for both Matrix 5 and Matrix
  6 (never just "what comes next"), matching the authentic dMAT format
  ("every item has two answers" — Nbyula guide, p.14).
- **Per-question solution must be independent and collapsed by default**:
  use a native `<details>`/`<summary>` element per question — this gets
  "collapsed by default, expand one without affecting others" for free with
  no JS, and is what the script already does.

## Files

- `scripts/generate_fs.py` — the full engine (simulation, retry-until-valid
  generation, distractor construction, HTML/CSS/JS rendering, CLI). Treat
  this as the source of truth; extend it in place for new requirements
  (e.g. a new shape, a new tier, a 5-option format) rather than writing a
  parallel implementation in the conversation.
