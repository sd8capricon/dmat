---
name: math-equation-generator
description: Generate dMAT-style "Mathematical Equations" reasoning practice questions (systems of 2-4 equations in unknowns A-D, solved by the read-off/anchor chain method) as a self-contained HTML file with expandable per-question solutions. Use when the user asks to create, generate, or add more Mathematical Equations / equation-system practice questions/quiz for dMAT prep in this project, specifying a question count and one or more difficulty levels (easy/medium/hard).
---

# Mathematical Equations Question Generator

## Why this exists

A Mathematical Equations item looks trivial to hand-author (just write a few
equations with capital letters) but it is very easy to get subtly wrong: an
LLM freehand-writing a system has no guarantee it has *exactly one* integer
solution in range, that a "hard" item is hard for the right reason (a real
anchor-and-collapse derivation) rather than just having more letters, or that
the four multiple-choice options don't accidentally contain two numbers that
are both defensible.

The fix, mirroring the sibling `figure-sequence-generator` and
`latin-square-generator` skills, is **never hand-write a system** — always
generate it procedurally:

1. Pick n distinct target integers in [1, 20], one per unknown.
2. Build n equations from those targets using one of two constructions that
   are correct *by construction* (see "Difficulty tiers" below): a
   **chain** (one equation reads off a single unknown, every other equation
   links a new unknown to one already known) or an **anchor** (every other
   unknown is an exact integer-affine function of one anchor unknown, and a
   final weighted-sum equation collapses everything into the anchor alone).
3. Independently re-verify every system by **brute-force search** over the
   full `[1, 20]^n` integer grid (n <= 4, so at most 160,000 combinations —
   cheap to check directly instead of trusting the algebra): reject and
   retry unless exactly one assignment satisfies every equation, and it is
   the assignment the system was built from.
4. Build wrong-answer options by reusing a sibling unknown's true value or
   nudging the correct value by a small offset — never an arbitrary
   freehand number — so distractors are plausible slips, not noise.

All of this is already implemented in `scripts/generate_me.py`. Do not
re-derive equation forms or hand-write a system in the conversation — a
clean run with no traceback, on top of the brute-force check baked into
`validate_unique`, is itself strong evidence of correctness (see Step 4 for
an extra independent audit you should still run).

## When to use this skill

Trigger when the user asks for new Mathematical Equations / equation-system
practice questions for dMAT in this project, specifying (or implying) a
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

Format: **`ME-<yymmdd>-<total-questions>.html`** (e.g. `ME-260902-20.html`),
using **today's date**. Save it in the project root (the directory the user
is working in) unless they specify otherwise. Do not overwrite an existing
file with the same name from the same day without confirming — append `-2`,
`-3`, etc. if needed. As a safety net (not a substitute for that check),
the script itself now also refuses to overwrite whatever `--out` path you
give it if that file already exists — pass `--force` only after the user
has actually confirmed they want that exact file replaced.

## Step 3 — Run the generator

```
python3 .claude/skills/math-equation-generator/scripts/generate_me.py \
  --easy <N> --medium <N> --hard <N> --out <filename>.html
```

Omit any of `--easy/--medium/--hard` that are 0. Add `--seed <int>` only if
the user explicitly wants reproducible output across runs; otherwise leave
it unset so repeated invocations produce fresh variety.

The script's `validate_unique()` brute-forces the full `[1,20]^n` grid per
item and retries (up to 200 attempts per item, and up to 60 nested attempts
for a non-degenerate anchor collapse) until every item is provably correct.
A successful run with no traceback means every item is structurally valid.
Sanity-check the printed summary line matches the requested per-tier counts.
Generation is fast even at the hardest tier (~0.1s/item for 4 unknowns on a
normal laptop) — a request for a few dozen questions should finish in
seconds, not minutes; if it hangs, something is wrong (see Constraints).

## Step 4 — Verify before reporting done

The script's own brute-force check is strong, but re-derive independently
from the *rendered HTML text* as a second, fully separate check — this
catches bugs in the narrative/rendering code that wouldn't show up in the
generator's internal check:

```python
import re, itertools

html = open('<filename>.html').read()
items = re.findall(r'<section class="item".*?</section>', html, re.S)

def split_eq(text):
    lhs, rhs = text.split('=')
    return lhs.replace('×', '*').replace('÷', '/').strip(), rhs.replace('×', '*').replace('÷', '/').strip()

for i, it in enumerate(items, 1):
    eqns = re.findall(r'<div class="eqn-chip">(.*?)</div>', it)
    letters = sorted(set(re.findall(r'\b([A-D])\b', ' '.join(eqns))))
    prompt = re.search(r'What is the value of ([A-D])\?', it).group(1)
    opts = re.findall(r'data-correct="(true|false)"[^>]*><div class="option-letter-big">(-?\d+)</div>', it)
    assert len(opts) == 4 and sum(c == 'true' for c, _ in opts) == 1
    correct = int([v for c, v in opts if c == 'true'][0])
    parsed = [split_eq(e) for e in eqns]
    sols = [c for c in itertools.product(range(1, 21), repeat=len(letters))
            if all(abs(eval(l, {}, dict(zip(letters, c))) - eval(r, {}, dict(zip(letters, c)))) < 1e-9
                   for l, r in parsed)]
    assert len(sols) == 1, f"item {i}: not unique ({len(sols)} solutions)"
    assert sols[0][letters.index(prompt)] == correct, f"item {i}: option doesn't match derived answer"
print("ok", len(items))
```

Then open the file (or spot-check the raw HTML) and confirm at least one
"Show answer & reasoning" panel expands independently of the others (native
`<details>` — no extra JS needed for that part) and that the reasoning text
reads coherently against the equations shown.

Report the final file path and question-count breakdown to the user.

## Difficulty tiers (already encoded in `TIERS` in the script)

| Tier   | Unknowns | Chain probability | What it matches in the reference materials |
|--------|----------|--------------------|-----------------------------------------------|
| Easy   | 2 | 0.65 | dMAT prep materials Exercises 1/2 ("low"); Nbyula ME-LOW-* |
| Medium | 3 | 0.50 | dMAT prep materials Exercise 3/4 ("medium"); Nbyula ME-MEDIUM-* |
| Hard   | 4 | 0.0 (always anchor) | dMAT prep materials Exercises 5/6 ("high"); Nbyula ME-HIGH-* |

`n_unknowns` is the exam's own ladder (verified against
`260716_dMAT_General-Academic-Module_Preparatoy-Materials_EN.pdf` pages
19-23, which states "2 equations in 2 unknowns, then 3 in 3, then 4 in 4",
and `Nbyula-dMAT-Guide.pdf` pages 19-23/42-82, which shows the same ladder
across a 40-item bank). `chain_prob` is the probability an item is built by
"chain" (one free read-off equation, then pure forward substitution) instead
of "anchor" (no free read-off; must anchor on the most-referenced letter).
Every one of the seven worked hard/high-tier examples sampled from the guide
(ME-HIGH-02/03/05/06/08/09/10, pages 69-75) opens with "no equation gives you
a number on its own" — hard items never offer a free read-off, hence
`chain_prob = 0` for hard. Low/medium items are a genuine mix of both in the
source material, hence the ~50/50 and ~65/35 splits.

If asked to adjust difficulty balance, edit `TIERS` in `generate_me.py`
rather than hand-writing new question logic in the conversation.

## Constraints and pitfalls learned building this (do not relitigate)

- **Never more than 4 letters (A-D), regardless of tier.** This matches the
  real exam exactly — even the hardest tier tops out at 4 unknowns, it never
  scales further. `LETTERS_POOL` is fixed at exactly `['A','B','C','D']`;
  don't extend it for a "harder than hard" request — instead say the real
  exam doesn't go beyond 4-in-4 and offer more *items* at hard instead.
- **Target values are always distinct integers in [1, 20]**, drawn via
  `rng.sample` (sampling without replacement). This matches every worked
  example in both reference PDFs — no worked item ever repeats a value
  across two different letters. Do not switch to `rng.randint` with
  replacement; besides being unfaithful to the source, it also makes
  distractor construction (which reuses sibling values) degenerate when two
  letters share a value.
- **Anchor mode's "express" equations are restricted to integer-affine
  forms** (`new_var = m * anchor + b`, integer `m` and `b`) even though
  `pairwise_link_equation` (used only in chain mode) is allowed much richer
  forms including opportunistic division. This is a deliberate,
  intentional trade: anchor mode needs to track a symbolic `(m, b)` pair
  per expressed letter so the final collapse ("tidies to `K × anchor + B =
  total`") can be computed and displayed exactly. A fractional coefficient
  here would make that line either wrong or unexplainably hand-wavy. This
  costs some of the division-flavoured equations the real material shows in
  its anchor-style items, in exchange for a narrative that is *always*
  exactly correct. If asked to add division to anchor-mode express
  equations, you would need to switch the whole `(m, b)` tracking to
  `fractions.Fraction` and update the collapse narrative accordingly — do
  not just bolt a `÷` form onto the existing integer-only code path, it will
  silently produce wrong "tidies to" lines.
- **The brute-force uniqueness check (`validate_unique`) is the actual
  correctness guarantee, not the hand-derived algebra.** Every equation
  form was designed to be correct by construction, but `validate_unique`
  re-derives the answer from scratch over the full `[1,20]^n` grid and
  rejects (triggering a full regenerate-and-retry, not a patch) anything
  that isn't provably unique and matching. If you ever add a new equation
  template, you do not need to hand-prove it is sound — just make sure it
  still routes through `validate_unique` before being accepted, exactly
  like every existing template does.
- **Hard items always use anchor mode, never chain** (`chain_prob = 0`).
  Do not "simplify" a hard item by giving it a free read-off equation — that
  silently turns it into a medium-difficulty item wearing a hard badge,
  which is exactly the kind of mismatch this skill exists to prevent (see
  the sibling `latin-square-generator`'s note on `chain_len` being the real
  difficulty signal, not a superficial one).
- **Collapse equation weights are mostly 1, occasionally one letter gets
  weight 2** (`collapse_equation`, ~30% chance). This mirrors the mix seen
  in the reference bank between plain-sum collapses (`A + B + C + D = 41`)
  and weighted ones (`5 × B + A + C = 54`). Do not make every collapse a
  plain sum — that under-represents the coefficient-carrying items the
  guide actually contains; and do not make weights routinely larger than 2
  — real examples keep this term small so the mental arithmetic stays
  three-digit at most.
- **Distractor construction, not freehand numbers**: `build_distractors`
  first reuses other letters' true values in the same system (the most
  common real trap — grabbing the wrong letter's answer), then fills any
  remaining slots with the correct value ± a small offset. Always
  de-duplicate against the correct value and against each other.
- **Per-question solution must be independent and collapsed by default**:
  use a native `<details>`/`<summary>` element per question — this gets
  "collapsed by default, expand one without affecting others" for free with
  no JS, matching what `figure-sequence-generator` and
  `latin-square-generator` already do.
- **Click-to-check options mirror both sibling skills' UX**
  (`selected-correct` / `selected-wrong` / `reveal-correct` classes, same
  click-once-per-group JS snippet, same CSS variable palette and
  `badge-easy/medium/hard` colours) for visual/interaction consistency
  across every generated practice file in this project. Keep it unless the
  user asks for plain static output.

## Files

- `scripts/generate_me.py` — the full engine (equation construction for
  both chain and anchor modes, brute-force uniqueness verification,
  distractor construction, narrative generation, HTML/CSS/JS rendering,
  CLI). Treat this as the source of truth; extend it in place for new
  requirements (e.g. a 5th letter, a new tier, a different collapse style)
  rather than writing a parallel implementation in the conversation.
