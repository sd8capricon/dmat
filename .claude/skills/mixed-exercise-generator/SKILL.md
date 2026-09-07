---
name: mixed-exercise-generator
description: Generate a mixed dMAT practice set combining Figure Sequences, Latin Squares, and/or Mathematical Equations questions in one self-contained HTML file, grouped into per-type sections with continuous numbering. Use when the user asks for a combined/mixed practice set spanning more than one dMAT question type, specifying which types to include, how many questions per type, and either a mixed difficulty spread or an exact difficulty per type.
---

# Mixed Exercise Generator

## Why this exists

This skill never generates a question itself. Figure sequences, Latin
squares, and mathematical-equation systems are each hard enough to get
subtly wrong that they already have dedicated, self-verifying generator
skills (`figure-sequence-generator`, `latin-square-generator`,
`math-equation-generator`) — re-deriving any of that logic here would
reopen exactly the bugs those skills exist to prevent (non-unique answers,
overlapping figures, unsolvable-by-the-allowed-method puzzles).

Instead, `scripts/generate_mixed.py` loads all three sibling scripts as
plain Python modules (by file path — their directory names contain
hyphens, so a normal `import` can't reach them) and calls their own
`build_item`/`build_random_item` + `render_item` functions directly. It
then wraps the returned item fragments in one shared page shell: the three
sibling stylesheets are concatenated verbatim (they share the same
`:root` palette and core classes, and only *add* selectors relative to
each other — see Constraints below), one shared answer-check JS snippet
(already byte-identical across all three siblings) is included once, and
questions are numbered continuously across the whole file instead of each
type restarting at 1. A clean run with no traceback means every item is as
sound as it would be in that type's own standalone file, because it *is*
that type's own code running unmodified.

## When to use this skill

Trigger when the user asks for a combined / mixed practice set spanning
**more than one** of the three dMAT question types in a single HTML file.
If the user only wants one question type, use that type's own skill
instead — don't route a single-type request through this one.

## Step 1 — Gather inputs

You need, for **each question type the user wants included**:
- **Total number of questions** for that type.
- **Difficulty**: either an exact per-tier split ("10 easy, 5 medium, 5
  hard"), a single specified tier applied to the whole type's count ("15
  Latin Squares, all hard"), or "mixed" (split as evenly as possible across
  all three tiers, remainder on the hardest tier — same rule the sibling
  skills use for a bare total).

A question type is included in the output only if the user asked for it;
omit its flags entirely rather than passing zeros for tiers they didn't
ask about. If the user gives a total with no tier/type breakdown at all
("give me 30 mixed questions"), ask (via AskUserQuestion) which types to
include and how to split both the per-type totals and each type's
difficulty, defaulting the recommended option to an even split across all
three types and an even mixed-difficulty spread within each.

## Step 2 — Compute the output filename

Format: **`Mixed-<yymmdd>-<total-questions>.html`** (e.g.
`Mixed-260906-25.html`), using **today's date** and the combined total
across all included types. Saved in the project root unless the user
specifies otherwise.

**Unlike the three single-type skills, do not compute or check this
filename by hand — omit `--out` entirely and let the script do it.**
A plain `Mixed-<yymmdd>-<total>.html` name only encodes the date and the
total question count, not the type/tier composition, so two *different*
mixed sets requested on the same day (e.g. successive practice-coach
rounds that happen to reuse the same round size) routinely collide on that
name — this is a routine case here, not the rare edge case it is for the
single-type skills. `generate_mixed.py` handles this itself: when `--out`
is omitted it auto-detects an existing same-name file and appends `-2`,
`-3`, etc. until it finds a free name (see Step 3). Only pass an explicit
`--out` if the user names a specific file themselves — and even then, the
script refuses to silently overwrite an existing file unless `--force` is
also passed (see Step 3), so it's safe to just let it run rather than
`ls`-checking first.

## Step 3 — Run the generator

```
python3 .claude/skills/mixed-exercise-generator/scripts/generate_mixed.py \
  --fs-easy <N> --fs-medium <N> --fs-hard <N> \
  --ls-easy <N> --ls-medium <N> --ls-hard <N> \
  --me-easy <N> --me-medium <N> --me-hard <N>
```

Omit every `--<type>-<tier>` flag that would be 0 — omitting all three
tiers for a type excludes that type's section entirely. Add `--seed <int>`
only if the user explicitly wants reproducible output; otherwise leave it
unset. Generation cost is just the sum of the three sibling engines' own
cost, so a few dozen total questions should finish in seconds; if it hangs,
the problem is in whichever sibling skill owns that type, not in this one.

Leave `--out` unset per Step 2 unless the user named a specific file. If
you do pass an explicit `--out` and the script refuses because that path
already exists, that is the intended safety behavior — either drop `--out`
(let it auto-name/auto-suffix instead) or add `--force` if the user
specifically confirmed they want that exact file overwritten.

Sanity-check the printed summary line's per-type, per-tier breakdown
matches what was requested.

## Step 4 — Verify before reporting done

Because every item is produced by the sibling engine that already
self-verifies it, this step is about confirming the **combination** was
assembled correctly (global numbering, no cross-type leakage, sections
present/absent as requested) — plus re-running each sibling's own Step 4
check, scoped to that type's section:

```python
import re, itertools

html = open('<filename>.html').read()

# Global item ids are contiguous starting at 1 (catches numbering bugs from
# the section-building loop).
ids = [int(i) for i in re.findall(r'<section class="item" id="item-(\d+)"', html)]
assert ids == list(range(1, len(ids) + 1)), ids

# Split into per-type sections in document order.
sections = re.findall(
    r'<section class="type-section">(.*?)</section>\s*(?=(?:<section class="type-section">|</main>))',
    html, re.S)
def items_in(block):
    return re.findall(r'<section class="item".*?</section>', block, re.S)

for block in sections:
    items = items_in(block)
    if 'matrix-block' in block:            # Figure Sequences section
        for it in items:
            assert len(re.findall(r'matrix-block', it)) == 4
            assert len(re.findall(r'options-row', it)) == 2
    elif 'lcell qmark' in block:            # Latin Squares section
        for it in items:
            assert len(re.findall(r'lcell qmark', it)) == 1
            assert len(re.findall(r'data-correct="true"', it)) == 1
            assert len(re.findall(r'option-letter-big', it)) == 5
    elif 'eqn-chip' in block:               # Mathematical Equations section
        def split_eq(t):
            l, r = t.split('=')
            return l.replace('×','*').replace('÷','/').strip(), r.replace('×','*').replace('÷','/').strip()
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
            assert len(sols) == 1, f"item {i}: not unique ({len(sols)})"
            assert sols[0][letters.index(prompt)] == correct
print("ok", len(ids), "items across", len(sections), "sections")
```

Then open the file (or spot-check the raw HTML) and confirm: the section(s)
for every requested type are present and only those, each section's own
"Show answer" panels expand independently (native `<details>`, no extra JS
needed), and — for any Figure Sequence section — a visual spot-check that
figures don't overlap in any matrix, matching that sibling skill's own
Step 4. Also confirm the single, file-wide pacing timer's
`data-total-seconds` attribute equals `<total items across all sections>
&times; 75` (e.g. `grep -o 'data-total-seconds="[0-9]*"' <filename>.html`)
— there is exactly one timer bar for the whole file, not one per section.

Report the final file path and the per-type, per-tier question-count
breakdown to the user.

## Constraints and pitfalls learned building this (do not relitigate)

- **Filename collision avoidance is enforced in the script, not left as an
  agent-remembered step.** The sibling single-type skills document "append
  `-2`, `-3`, etc." as something the invoking agent should check for by
  hand, which is fine when it's a rare edge case. It is not rare here: a
  `Mixed-<yymmdd>-<total>.html` name only encodes the date and the total
  question count, so two different type/tier compositions can easily
  produce the identical default filename on the same day (this is the
  normal case for a multi-round `practice-coach` session that reuses the
  same round size). `next_available_path()` in `generate_mixed.py` auto-
  suffixes (`-2`, `-3`, ...) whenever `--out` is omitted, and a separate
  guard refuses to silently overwrite an explicit `--out` path unless
  `--force` is passed. Do not move this check back into "the agent should
  remember to `ls` first" — that's exactly the failure mode this fixes.
- **Never hand-generate a question here, in any type.** This skill's only
  job is orchestration (which types, how many, what tier, what order) —
  the second any question-construction logic gets copied inline instead of
  called through the sibling module, this skill inherits every correctness
  bug those skills were built to eliminate. If a new requirement needs new
  generation logic, it belongs in the relevant sibling's `generate_*.py`,
  not here.
- **Sibling scripts are loaded by file path via `importlib`, not imported
  as packages.** Their directory names (`figure-sequence-generator`, etc.)
  contain hyphens, which are not valid in a Python dotted import path. Do
  not try to convert the skills directory into a package (`__init__.py` +
  dotted imports) just to make imports look more conventional — the
  sibling skills are independently invoked elsewhere (their own
  `SKILL.md`s run them directly as scripts) and must keep working
  standalone; this file-path loading approach is what leaves them
  completely untouched.
- **Concatenating the three CSS blocks verbatim is *not* fully safe — this
  was wrong and caused a real bug.** The original assumption here was that
  repeated selectors across the three sibling stylesheets are
  byte-identical restatements. That's false for `.option`, `.options-row`,
  and `.prompt`: FS leaves `.option` auto-width (it holds a 176px 4×4 shape
  grid) while LS/ME fix it to a small `48px`/`56px` text-button width, and
  since concatenation order is `fs.CSS + ls.CSS + me.CSS`, ME's rule (last)
  won that property for *every* section — squeezing FS's option grids into
  a 56px box so figures visually spilled into the next option card. The fix
  (already applied in `generate_mixed.py`) is scoped override CSS: each
  section's wrapper carries a `type-section-<key>` class (e.g.
  `type-section-fs`), and `EXTRA_CSS` re-asserts each type's own
  `.option`/`.options-row`/`.prompt` values under `.type-section-<key> ...`
  — higher specificity than the bare sibling selectors, so section order
  can no longer matter. `:root` and `.item`/`.badge`/`.solution` genuinely
  are identical (or additive, e.g. LS's `--mark`) across all three and are
  still safe to concatenate verbatim. If a sibling's CSS changes again,
  re-diff all three stylesheets for selectors with matching names but
  different bodies (not just eyeballing it) before assuming a new addition
  is conflict-free — do not restore the "verbatim concatenation is always
  safe" assumption this replaced. Do not hand-merge everything into one
  deduplicated stylesheet either — that reintroduces the parallel-logic
  drift risk this skill's design otherwise avoids: this skill's output
  should stay correct automatically because it re-reads each sibling's
  `CSS` constant at generation time, only patching the specific selectors
  known to conflict.
- **The shared JS is taken from one sibling (`fs.JS`), not all three.**
  Unlike CSS, running the same `document.querySelectorAll(".options-row")`
  click-handler setup three times would attach three listeners per row.
  This happens to be harmless today (the `row.classList.contains("answered")`
  guard makes the 2nd/3rd listener no-ops on the same click), but it is
  incidental, not a property to depend on. If the three sibling JS
  snippets ever diverge, revisit this — do not just keep concatenating.
- **Sections are grouped by type (FS, then LS, then ME), not interleaved**,
  each internally ordered easiest-to-hardest tier, matching every sibling
  skill's own within-file ordering. If the user asks for interleaved /
  shuffled ordering instead, that's a real, deliberate feature change —
  ask for confirmation before extending `build_html`'s section loop into a
  randomized interleave, since it changes what "Question N" means relative
  to the sections a user might reference.
- **Global numbering, not per-type numbering.** Each sibling module's
  `render_item` takes an explicit `idx` argument (never generates its own),
  so `generate_mixed.py` threads a single running counter across all three
  builder calls in section order. Do not call any sibling's own
  `build_html`/`main` (which would restart numbering at 1 and also
  duplicate the page shell) — always call `build_item`/`build_random_item`
  + `render_item` directly, as the current script does.
- **Rules text per section is copied verbatim from each sibling's own
  instructions block**, not paraphrased. If a sibling skill's rules wording
  changes (e.g. a new constraint is added to the closed rule grammar), copy
  the updated text into this skill's `TYPE_META[...]['rules']` — do not let
  it drift out of sync, since a mismatched rules block would describe a
  different rule set than the one that actually generated the questions in
  that section.
- **One cumulative pacing timer for the whole file, not one per section.**
  The budget is 75s per question, counted across *all* sections combined
  (e.g. 5 FS + 5 LS + 5 ME = 15 questions &rarr; 18:45 total, not three
  separate 6:15 timers) — this mirrors what a real proctored session would
  time. `generate_mixed.py` calls `fs.render_timer_bar(total)` once (with
  the file's grand total, computed the same way `type_comp` already is) and
  pulls in `fs.TIMER_CSS`/`fs.TIMER_JS` alongside the three sibling
  stylesheets — it does not call each sibling's own `render_timer_bar`. If a
  new type is ever added to this skill, it only needs to contribute to that
  one shared total, not bring its own timer bar.

## Files

- `scripts/generate_mixed.py` — the orchestration script (sibling-module
  loading, per-type item building, merged page-shell rendering, CLI).
  Treat this as the source of truth for *how sections are combined*; treat
  each sibling's own `generate_*.py` as the source of truth for *how a
  question of that type is built* — extend the right one for the kind of
  change being requested.
