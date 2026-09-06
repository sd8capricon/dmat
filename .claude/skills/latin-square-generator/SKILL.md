---
name: latin-square-generator
description: Generate dMAT-style "Latin Squares" reasoning practice questions (5x5 grid, letters A-E, one marked cell) as a self-contained HTML file with expandable per-question solutions. Use when the user asks to create, generate, or add more Latin Square practice questions/quiz for dMAT prep in this project, specifying a question count and one or more difficulty levels (easy/medium/hard).
---

# Latin Square Question Generator

## Why this exists

A Latin Square item looks trivial to hand-author (just scatter some letters in
a 5x5 grid) but it is very easy to get subtly wrong: an LLM freehand-placing
letters has no guarantee the marked cell has a *unique* answer, that the
"reasoning" needed to reach it is the reasoning a human solver is actually
allowed to use on this task, or that "hard" grids are hard for the right
reason (a real deduction chain) instead of just being sparse-looking but
trivially forced.

The fix, mirroring the sibling `figure-sequence-generator` skill, is **never
author a grid by hand** — always generate it procedurally:

1. Build a genuine random 5x5 Latin square (every row and every column is a
   permutation of A-E).
2. Pick a target ("marked") cell and reveal a subset of the other 24 cells.
3. Run a round-based **naked-single solver** over the revealed grid — the
   only logic a human is allowed to use here: *"a cell must be the one
   letter missing from the union of its row and its column."* No guessing,
   no backtracking. If this solver eventually forces the target cell to a
   single letter, the puzzle has a provably unique, human-findable answer.
   If it doesn't, discard the attempt and retry with a different reveal.
4. The number of solver rounds needed before the target resolves **is** the
   difficulty: 0 stepping stones = easy, 1 = medium, 2-3 = hard.

All of this is already implemented in `scripts/generate_ls.py`. Do not
re-derive the solver or hand-place letters in the conversation — every
puzzle it emits is `assert`-verified sound while it builds the solution
text, so a clean run with no traceback is itself evidence of correctness.

## When to use this skill

Trigger when the user asks for new Latin Square practice questions for dMAT
in this project, specifying (or implying) a question count and one or more
difficulty levels.

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

Format: **`LS-<yymmdd>-<total-questions>.html`** (e.g. `LS-260902-20.html`),
using **today's date**. Save it in the project root (the directory the user
is working in) unless they specify otherwise. Do not overwrite an existing
file with the same name from the same day without confirming — append `-2`,
`-3`, etc. if needed. As a safety net (not a substitute for that check),
the script itself now also refuses to overwrite whatever `--out` path you
give it if that file already exists — pass `--force` only after the user
has actually confirmed they want that exact file replaced.

## Step 3 — Run the generator

```
python3 .claude/skills/latin-square-generator/scripts/generate_ls.py \
  --easy <N> --medium <N> --hard <N> --out <filename>.html
```

Omit any of `--easy/--medium/--hard` that are 0. Add `--seed <int>` only if
the user explicitly wants reproducible output across runs; otherwise leave
it unset so repeated invocations produce fresh variety.

The script retries internally (per item, up to 4000 attempts) until it finds
a sound puzzle matching the requested tier, and de-duplicates against every
grid/target pair already used in the same file. A successful run with no
traceback means every item is structurally valid and logically sound — the
printed summary line will echo the requested per-tier counts back to you;
sanity-check it matches.

## Step 4 — Verify before reporting done

Run a quick structural audit (regex over the output is enough, no browser
needed) confirming for every item: 25 grid cells, exactly one `qmark` cell,
exactly 5 answer options with exactly one `data-correct="true"`, and a
non-empty `<details class="solution">` block. Example one-liner:

```
python3 -c "
import re
html = open('<filename>.html').read()
items = re.findall(r'<section class=\"item\".*?</section>', html, re.S)
assert len(items) == <total>
for it in items:
    assert len(re.findall(r'lcell qmark', it)) == 1
    assert len(re.findall(r'data-correct=\"true\"', it)) == 1
    assert len(re.findall(r'option-letter-big', it)) == 5
print('ok', len(items))
"
```

Then open the file (or spot-check the raw HTML) and confirm at least one
"Show answer & solution" panel expands independently of the others (native
`<details>` — no extra JS needed for that part) and that the reasoning text
reads coherently against the rendered grid.

Report the final file path and question-count breakdown to the user.

## Difficulty tiers (already encoded in `TIERS` in the script)

| Tier   | Stepping stones (`chain_len`) | Given-cell count (of 24) | What it matches in the reference materials |
|--------|-------------------------------|---------------------------|---------------------------------------------|
| Easy   | 0 | 13–17 (dense)  | dMAT prep materials Exercise 1/2 ("low"); Nbyula's "one-step read" (LS-001) |
| Medium | 1 | 9–13 (moderate) | dMAT prep materials Exercise 3/4 ("medium"); Nbyula's "two candidates, one deduction" (LS-025) |
| Hard   | 2–3 | 7–11 (sparse) | dMAT prep materials Exercise 5/6 ("high"); Nbyula's "chain of three, sparse grid" (LS-050) |

`chain_len` is the number of *other* cells that must be resolved by pure
row/column elimination before the marked cell itself becomes forced — this
is the actual difficulty signal (verified against both reference PDFs while
building this skill: `260716_dMAT_General-Academic-Module_..._EN.pdf` pages
22–33, `Nbyula-dMAT-Guide.pdf` pages 24–28). Given-cell count is a
*secondary*, purely visual signal (how "sparse" the grid looks) and is
enforced independently — do not conflate the two when tuning tiers.

If asked to adjust difficulty balance, edit the `chain_lens` / `given_range`
tuples in `TIERS` inside `generate_ls.py` rather than hand-writing new
question logic in the conversation.

## Constraints and pitfalls learned building this (do not relitigate)

- **Grid is 5x5, letters A–E** (row 1 = top, column 1 = left). This is fixed
  by the real exam's format (verified against both reference PDFs) — do not
  change `N`/`LETTERS` without re-verifying every rendering and solver
  function.
- **The solver must only use row/column naked-single elimination** — never
  full backtracking/constraint search. Backtracking can "solve" a puzzle a
  human couldn't, which would silently ship an unfair item. `propagate_rounds`
  in the script is the one and only source of truth for what counts as a
  legitimate deduction; do not add smarter solving logic to it.
- **"Fully solvable" is the wrong acceptance criterion — do not resurrect
  it.** An earlier version of this generator required the *entire* grid to
  become forced via elimination before accepting a puzzle. That produced
  puzzles where the marked cell needed 6+ chained deductions even at
  moderate sparsity, because minimizing for "whole grid solvable" strips
  every cell not needed for *some* eventual full solve, not just the ones
  needed for the marked cell. The fix (already in the script) is
  `target_forced()`: only require that the *marked cell* eventually gets
  forced. Many other cells are allowed to stay permanently ambiguous/blank —
  this is also what the real dMAT solution keys look like (see Exercise 6's
  worked solution: most of the grid is still blank after solving).
- **`chain_len` (from `chain_bullets`) is the real difficulty measure, not
  the raw round number.** `propagate_rounds` assigns a round to *every*
  forceable cell in the whole grid, including ones unrelated to the marked
  cell that happen to resolve incidentally. `chain_bullets` filters this
  down to only the cells that were actually forced *before* the target, in
  dependency order, and re-derives + `assert`s each one against the true
  solution. Always compute difficulty from `len(chain_bullets(...)) - 1`,
  never from a raw round count.
- **Stepping stones are not restricted to the marked cell's own row/column.**
  The instructions correctly say only the marked cell's own row/column can
  change *its* answer directly, but a stepping-stone cell's own crossing
  line can pull from a given anywhere else in the grid (verified against
  dMAT Exercise 3's worked solution, which uses a row-3 given to resolve a
  stepping stone in a different row/column entirely). Do not add a filter
  that restricts revealed/stepping-stone cells to the target's row/column —
  it would make hard puzzles unrepresentative of the real exam.
- **Easy/medium must use random reveal, not minimization.** `minimize_for_chain`
  (strip givens while the target stays forceable *at all*) always biases
  toward the sparsest possible support, which tends to produce *longer*
  chains, not shorter ones — it is only appropriate for the `hard` tier.
  Easy/medium instead pick a random subset of a given size directly
  (`random_reveal`) and reject the attempt if the resulting `chain_len`
  doesn't match the tier; this is what keeps easy grids looking dense and
  medium grids looking moderately filled, matching the official materials'
  visual style at each tier.
- **Soundness is automatic, not something to double-check separately.**
  Because every reveal is a genuine subset of an actual solved Latin square,
  any letter that elimination narrows down to a single candidate *must* be
  the true value (removing letters that are already used elsewhere in the
  row/column can never eliminate the correct answer). The `assert` calls in
  `chain_bullets` exist to catch *implementation* bugs (e.g. replaying
  same-round deductions in a bad order), not to check puzzle correctness —
  if a run raises `AssertionError`, that attempt is simply skipped and
  retried, it does not mean the underlying math needs re-justifying.
- **De-duplicate within a file.** Track `(given-grid, target)` signatures
  already used and reject repeats (`seen_signatures` in `build_item`) so a
  large request (e.g. 30 questions) doesn't silently repeat a puzzle.
- **Per-question solution must be independent and collapsed by default**:
  use a native `<details>`/`<summary>` element per question — this gets
  "collapsed by default, expand one without affecting others" for free with
  no JS, matching what `figure-sequence-generator` already does.
- **Click-to-check options mirror the sibling skill's UX** (`selected-correct`
  / `selected-wrong` / `reveal-correct` classes, same click-once-per-group JS
  snippet) for visual/interaction consistency across every generated
  practice file in this project. Keep it unless the user asks for plain
  static output.

## Files

- `scripts/generate_ls.py` — the full engine (Latin square generation, the
  naked-single solver, tiered reveal/minimization, chain verification,
  HTML/CSS/JS rendering, CLI). Treat this as the source of truth; extend it
  in place for new requirements (e.g. a 6x6 variant, a new tier, per-question
  timing hints) rather than writing a parallel implementation in the
  conversation.
