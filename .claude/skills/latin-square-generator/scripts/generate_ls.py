#!/usr/bin/env python3
"""
Generate dMAT-style "Latin Squares" reasoning questions as a self-contained HTML file.

Core idea: NEVER hand-place letters in a 5x5 grid and hope the marked cell has a
unique, findable answer. Instead:
  1. Build a genuine random 5x5 Latin square (rows and columns are permutations of A-E).
  2. Pick a target ("marked") cell and reveal a subset of the other 24 cells as givens.
  3. Run a round-based naked-single solver (the ONLY logic a human is allowed to use on
     this task: "a cell must be the one letter missing from its row and column") over the
     revealed grid. If that solver eventually forces the target cell to a single letter,
     the puzzle is sound and has a provably unique, human-findable answer -- no guessing
     or backtracking ever required. If it doesn't, discard the attempt and try again.
  4. The number of solver rounds needed before the target resolves *is* the difficulty:
     0 stepping stones = easy, 1 = medium, 2-3 = hard.

This mirrors the sibling `figure-sequence-generator` skill's philosophy: never author
by hand, always simulate + verify + retry. All of this logic lives in this script;
do not re-derive it by hand in the conversation.

Usage:
  python3 generate_ls.py --easy 5 --medium 10 --hard 5 [--out LS-20-260902.html] [--seed 42]

If --out is omitted, the file is named LS-<total>-<yymmdd>.html in the current directory.
"""
import argparse
import datetime
import random

N = 5
LETTERS = "ABCDE"

# ---------------------------------------------------------------------------
# Latin square engine
# ---------------------------------------------------------------------------

def random_latin_square(rng):
    """A uniform-ish random 5x5 Latin square: start from a cyclic square, then
    shuffle rows, shuffle columns, and relabel symbols. This fully decorrelates
    the result from the obvious cyclic pattern."""
    base = list(range(N))
    rng.shuffle(base)
    grid = [[base[(i + j) % N] for j in range(N)] for i in range(N)]
    row_order = list(range(N)); rng.shuffle(row_order)
    col_order = list(range(N)); rng.shuffle(col_order)
    grid = [[grid[r][c] for c in col_order] for r in row_order]
    relabel = list(range(N)); rng.shuffle(relabel)
    return [[relabel[v] for v in row] for row in grid]


def candidates(grid, r, c):
    """Letters not yet used in row r or column c. grid[r][c] itself is ignored
    (candidates() is only ever called on cells being considered for a value)."""
    used = set()
    for cc in range(N):
        if grid[r][cc] is not None:
            used.add(grid[r][cc])
    for rr in range(N):
        if grid[rr][c] is not None:
            used.add(grid[rr][c])
    return set(range(N)) - used


def propagate_rounds(given):
    """Round-based naked-single propagation over the WHOLE grid (every cell,
    not just the target's row/column -- a stepping stone's own crossing line
    can depend on givens anywhere in the grid, e.g. dMAT Exercise 3's use of a
    row-3 given to resolve a row-1/column-5 stepping stone).

    Returns (grid_after, round_filled). round_filled[r][c]:
      0    -> was a given clue
      >0   -> the round number it got forced (rounds start at 1)
      None -> never resolved by pure elimination (this given set is a dead end)
    """
    grid = [row[:] for row in given]
    round_filled = [[0 if given[r][c] is not None else None for c in range(N)] for r in range(N)]
    rnd = 0
    while True:
        rnd += 1
        to_fill = []
        for r in range(N):
            for c in range(N):
                if grid[r][c] is None:
                    cand = candidates(grid, r, c)
                    if len(cand) == 1:
                        to_fill.append((r, c, next(iter(cand))))
        if not to_fill:
            break
        for r, c, v in to_fill:
            if grid[r][c] is None:
                grid[r][c] = v
                round_filled[r][c] = rnd
    return grid, round_filled


def target_forced(given, target):
    grid, round_filled = propagate_rounds(given)
    r0, c0 = target
    return grid[r0][c0] is not None, round_filled


def chain_bullets(full, given, target, round_filled):
    """Replay the actual dependency chain in round order and return, for each
    step, (r, c, letter, candidates_at_that_moment). The last entry is always
    the target itself. Every step is re-verified (assert) against the real
    solution so a bug here can never silently ship an unsound puzzle."""
    r0, c0 = target
    stones = []
    for r in range(N):
        for c in range(N):
            if (r, c) != target and round_filled[r][c] is not None and round_filled[r][c] > 0:
                stones.append((round_filled[r][c], r, c))
    stones.sort()
    grid = [row[:] for row in given]
    bullets = []
    for rnd, r, c in stones:
        cand = candidates(grid, r, c)
        v = full[r][c]
        assert cand == {v}, "unsound deduction while replaying chain"
        bullets.append((r, c, LETTERS[v], sorted(LETTERS[x] for x in cand)))
        grid[r][c] = v
    cand = candidates(grid, r0, c0)
    v = full[r0][c0]
    assert cand == {v}, "unsound deduction at target cell"
    bullets.append((r0, c0, LETTERS[v], sorted(LETTERS[x] for x in cand)))
    return bullets


def minimize_for_chain(given, rng, target):
    """Greedily strip givens (one at a time, random order) while the target
    remains forceable *at all*. This finds a minimal-support sparse puzzle,
    which is what naturally produces the longer 2-3 step chains real hard
    items use (dMAT Exercise 5/6, Nbyula's LS-050). Do NOT use this for
    easy/medium -- it biases hard toward long chains, not toward the dense,
    single-step look those tiers need."""
    cells = [(r, c) for r in range(N) for c in range(N) if given[r][c] is not None and (r, c) != target]
    rng.shuffle(cells)
    given = [row[:] for row in given]
    for (r, c) in cells:
        val = given[r][c]
        given[r][c] = None
        ok, _ = target_forced(given, target)
        if not ok:
            given[r][c] = val
    return given


def random_reveal(full, rng, target, k):
    """Reveal exactly k of the 24 non-target cells as givens."""
    r0, c0 = target
    cells = [(r, c) for r in range(N) for c in range(N) if (r, c) != target]
    rng.shuffle(cells)
    chosen = set(cells[:k])
    return [[full[r][c] if (r, c) in chosen else None for c in range(N)] for r in range(N)]


# ---------------------------------------------------------------------------
# Difficulty tiers
# ---------------------------------------------------------------------------
# chain_len = number of stepping-stone cells that must be resolved (via pure
# row/column elimination) before the marked cell itself becomes forced.
#   easy   -> 0: the marked row/column alone already rules out every letter
#             but one (dMAT's "one-step read"; Exercise 1/2 style).
#   medium -> 1: exactly one other cell must be resolved first ("two
#             candidates, one deduction"; Exercise 3/4, Nbyula LS-025 style).
#   hard   -> 2 or 3: a genuine multi-step chain (Exercise 5/6, Nbyula
#             LS-050 "chain of three" style).
# given_range is the *displayed* clue count and is what actually produces the
# tier's look: easy grids read as "mostly filled in", hard grids read as
# sparse. It is a visual/difficulty signal independent of chain_len.
TIERS = {
    'easy':   dict(chain_lens={0}, given_range=(13, 17), use_minimize=False),
    'medium': dict(chain_lens={1}, given_range=(9, 13),  use_minimize=False),
    'hard':   dict(chain_lens={2, 3}, given_range=(7, 11), use_minimize=True),
}


def try_generate_tier(rng, tier, max_targets=25):
    cfg = TIERS[tier]
    full = random_latin_square(rng)
    targets = [(r, c) for r in range(N) for c in range(N)]
    rng.shuffle(targets)
    for target in targets[:max_targets]:
        r0, c0 = target
        if cfg['use_minimize']:
            given = [[full[r][c] for c in range(N)] for r in range(N)]
            given[r0][c0] = None
            given = minimize_for_chain(given, rng, target)
        else:
            lo, hi = cfg['given_range']
            k = rng.randint(lo, hi)
            given = random_reveal(full, rng, target, k)
        ok, round_filled = target_forced(given, target)
        if not ok:
            continue
        try:
            bullets = chain_bullets(full, given, target, round_filled)
        except AssertionError:
            continue
        chain_len = len(bullets) - 1
        n_given = sum(1 for r in range(N) for c in range(N) if given[r][c] is not None)
        lo, hi = cfg['given_range']
        if chain_len in cfg['chain_lens'] and lo <= n_given <= hi:
            return {
                'tier': tier, 'full': full, 'given': given, 'target': target,
                'chain_len': chain_len, 'n_given': n_given,
                'answer': LETTERS[full[r0][c0]], 'bullets': bullets,
            }
    return None


def build_item(rng, tier, seen_signatures, max_attempts=4000):
    for _ in range(max_attempts):
        out = try_generate_tier(rng, tier)
        if out is None:
            continue
        sig = (tuple(tuple(row) for row in out['given']), out['target'])
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        return out
    raise RuntimeError(f"Could not build a valid '{tier}' item after {max_attempts} attempts")


# ---------------------------------------------------------------------------
# Plain-English reasoning (mirrors the official "Solution path" bullet style)
# ---------------------------------------------------------------------------

def row_used_letters(grid, r):
    return sorted(LETTERS[v] for v in grid[r] if v is not None)


def col_used_letters(grid, c):
    return sorted(LETTERS[grid[rr][c]] for rr in range(N) if grid[rr][c] is not None)


def build_reasoning_html(d):
    given = d['given']; target = tuple(d['target'])
    grid = [row[:] for row in given]
    lines = []
    for (r, c, letter, _cand) in d['bullets']:
        ru = row_used_letters(grid, r)
        cu = col_used_letters(grid, c)
        is_target = (r, c) == target
        loc = f"the marked cell (row {r + 1}, column {c + 1})" if is_target else f"row {r + 1}, column {c + 1}"
        ru_txt = ", ".join(ru) if ru else "no letters yet"
        cu_txt = ", ".join(cu) if cu else "no letters yet"
        verb = "the answer is" if is_target else f"row {r + 1}, column {c + 1} ="
        lines.append(
            f"<p>At {loc}: row {r + 1} already has {ru_txt}; column {c + 1} already has {cu_txt}. "
            f"That leaves only <strong>{letter}</strong>, so {verb} <strong>{letter}</strong>.</p>"
        )
        grid[r][c] = LETTERS.index(letter)
    return "".join(lines)


PATTERN_SUMMARY = {
    0: "Direct elimination: the marked row and column together already rule out every letter but one. No other cell needs to be solved first.",
    1: "One-step chain: exactly one stepping-stone cell must be resolved first (using its own row/column), and that single fact forces the marked cell.",
}


def pattern_summary(chain_len):
    if chain_len in PATTERN_SUMMARY:
        return PATTERN_SUMMARY[chain_len]
    return (f"Multi-step chain ({chain_len} stepping stones): resolve the stepping-stone cells in "
            f"order, each one removing another letter from the marked cell's candidates, until only "
            f"one letter remains.")


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_grid_html(given, target):
    r0, c0 = target
    cells = []
    for r in range(N):
        for c in range(N):
            if (r, c) == (r0, c0):
                cells.append('<div class="lcell qmark">?</div>')
            elif given[r][c] is not None:
                cells.append(f'<div class="lcell">{LETTERS[given[r][c]]}</div>')
            else:
                cells.append('<div class="lcell"></div>')
    return '<div class="lgrid">' + "".join(cells) + "</div>"


DIFF_LABEL = {'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'}


def render_item(idx, d):
    given = d['given']; target = tuple(d['target']); answer = d['answer']; tier = d['tier']
    grid_html = render_grid_html(given, target)
    group = f"item{idx}"
    options_html = "".join(
        f'<button type="button" class="option" data-correct="{"true" if letter == answer else "false"}" '
        f'data-group="{group}"><div class="option-letter-big">{letter}</div></button>'
        for letter in LETTERS
    )
    reasoning_html = build_reasoning_html(d)
    summary_txt = pattern_summary(d['chain_len'])
    return f'''
<section class="item" id="item-{idx}">
  <div class="item-header">
    <h2>Question {idx} <span class="badge badge-{tier}">{DIFF_LABEL[tier]}</span></h2>
  </div>
  <div class="puzzle-row">
    {grid_html}
    <div class="options-col">
      <div class="prompt">Which letter replaces the question mark?</div>
      <div class="options-row" data-group="{group}">{options_html}</div>
    </div>
  </div>
  <details class="solution">
    <summary>Show answer &amp; solution</summary>
    <p><strong>Answer: {answer}</strong></p>
    <p class="pattern">{summary_txt}</p>
    {reasoning_html}
  </details>
</section>
'''


CSS = '''
:root{
  --bg:#f4f5f8; --panel:#ffffff; --panel2:#fbfbfd; --line:#d7dbe4;
  --text:#1c2233; --text-dim:#5b6478; --accent:#3355cc;
  --good:#1f9d55; --bad:#d13b34; --mark:#d13b34;
  --easy:#1f9d55; --medium:#c47f17; --hard:#c0392b;
}
*{box-sizing:border-box;}
body{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:var(--bg); color:var(--text); line-height:1.5; }
header.page-header{ padding:32px 24px 16px; max-width:960px; margin:0 auto; }
header.page-header h1{ margin:0 0 6px; font-size:1.6rem; }
header.page-header p{ color:var(--text-dim); margin:4px 0; }
.instructions{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px 20px; margin-top:16px; }
.instructions ul{ margin:8px 0 0; padding-left:20px; }
.instructions li{ margin:4px 0; color:var(--text-dim); }
main{ max-width:960px; margin:0 auto; padding:8px 24px 64px; }
.item{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
  padding:20px 22px; margin:28px 0; box-shadow:0 1px 3px rgba(20,25,40,.05); }
.item-header h2{ margin:0 0 14px; font-size:1.15rem; display:flex; align-items:center; gap:10px; }
.badge{ font-size:.72rem; font-weight:600; padding:3px 9px; border-radius:999px; letter-spacing:.02em; border:1px solid; }
.badge-easy{ color:var(--easy); background:rgba(31,157,85,.08); border-color:rgba(31,157,85,.35); }
.badge-medium{ color:var(--medium); background:rgba(196,127,23,.08); border-color:rgba(196,127,23,.35); }
.badge-hard{ color:var(--hard); background:rgba(192,57,43,.08); border-color:rgba(192,57,43,.35); }
.puzzle-row{ display:flex; flex-wrap:wrap; gap:32px; align-items:flex-start; margin-bottom:8px; }
.lgrid{ display:grid; grid-template-columns:repeat(5,56px); grid-template-rows:repeat(5,56px);
  background:var(--panel2); border:2px solid var(--line); border-radius:6px; overflow:hidden;
  box-shadow:0 1px 2px rgba(20,25,40,.06); flex:0 0 auto; }
.lcell{ border:.5px solid var(--line); display:flex; align-items:center; justify-content:center;
  font-size:1.3rem; font-weight:600; color:var(--text); background:var(--panel); }
.lcell.qmark{ color:var(--mark); border:2px solid var(--mark); font-weight:700; }
.options-col{ flex:1 1 220px; min-width:220px; }
.prompt{ font-weight:600; margin:0 0 10px; color:var(--text); }
.options-row{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:6px; }
.option{ background:var(--panel); border:2px solid var(--line); border-radius:10px; padding:10px 0;
  width:48px; cursor:pointer; text-align:center; color:var(--text); transition:border-color .15s, background .15s;
  box-shadow:0 1px 3px rgba(20,25,40,.05); }
.option-letter-big{ font-size:1.15rem; font-weight:700; }
.option:hover{ border-color:var(--accent); }
.option.selected-correct{ border-color:var(--good); background:rgba(31,157,85,.10); }
.option.selected-wrong{ border-color:var(--bad); background:rgba(209,59,52,.10); }
.option.reveal-correct{ border-color:var(--good); }
.options-row.answered .option{ cursor:default; }
.options-row.answered .option:hover{ border-color:var(--line); }
.options-row.answered .option.reveal-correct:hover{ border-color:var(--good); }
.solution{ margin-top:16px; background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:10px 16px; }
.solution summary{ cursor:pointer; font-weight:600; color:var(--accent); }
.solution p{ margin:10px 0; font-size:.92rem; color:var(--text-dim); }
.solution p.pattern{ font-style:italic; }
.solution strong{ color:var(--text); }
footer{ text-align:center; color:var(--text-dim); font-size:.8rem; padding:24px; }
'''

JS = '''
document.querySelectorAll(".options-row").forEach(function(row){
  row.addEventListener("click", function(e){
    var btn = e.target.closest(".option");
    if(!btn || row.classList.contains("answered")) return;
    row.classList.add("answered");
    var correct = btn.dataset.correct === "true";
    btn.classList.add(correct ? "selected-correct" : "selected-wrong");
    if(!correct){
      row.querySelectorAll(".option").forEach(function(o){
        if(o.dataset.correct === "true") o.classList.add("reveal-correct");
      });
    }
  });
});
'''


def build_html(items, counts):
    total = sum(counts.values())
    comp = ", ".join(f"{counts[t]} {DIFF_LABEL[t]}" for t in ('easy', 'medium', 'hard') if counts.get(t))
    items_html = "".join(render_item(i + 1, d) for i, d in enumerate(items))
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>dMAT Latin Squares &mdash; {total} Questions</title>
<style>{CSS}</style>
</head>
<body>
<header class="page-header">
  <h1>Latin Squares Practice Set</h1>
  <p>{total} items ({comp}), in the dMAT Core Module format. Each item is a 5&times;5 grid using the letters A&ndash;E.</p>
  <div class="instructions">
    <strong>Rules:</strong>
    <ul>
      <li>Each letter (A&ndash;E) appears exactly once in every row and exactly once in every column.</li>
      <li>Some cells are already filled in. Only the letters A&ndash;E may be used &mdash; no other symbols.</li>
      <li>Exactly one cell is marked with a red <strong>?</strong>. Work out which letter belongs there and click it below the grid.</li>
      <li>Sometimes you need to work out one or more other cells first before the marked cell becomes forced &mdash; that chain of deductions is what separates easy, medium and hard items.</li>
      <li>Only the marked cell's own row and own column can ever change its answer, but a stepping-stone cell elsewhere in the grid may need its own row/column solved first.</li>
    </ul>
  </div>
</header>
<main>
{items_html}
</main>
<footer>Generated practice material &mdash; not official dMAT content. Verify against the official prep materials before relying on it.</footer>
<script>{JS}</script>
</body>
</html>
'''


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--easy', type=int, default=0)
    ap.add_argument('--medium', type=int, default=0)
    ap.add_argument('--hard', type=int, default=0)
    ap.add_argument('--out', type=str, default=None)
    ap.add_argument('--seed', type=int, default=None)
    args = ap.parse_args()

    counts = {'easy': args.easy, 'medium': args.medium, 'hard': args.hard}
    total = sum(counts.values())
    if total <= 0:
        raise SystemExit("Specify at least one of --easy/--medium/--hard with a count > 0")

    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    seen_signatures = set()
    items = []
    for tier in ('easy', 'medium', 'hard'):
        for _ in range(counts[tier]):
            items.append(build_item(rng, tier, seen_signatures))

    html = build_html(items, counts)

    out_path = args.out
    if not out_path:
        yymmdd = datetime.date.today().strftime('%y%m%d')
        out_path = f"LS-{total}-{yymmdd}.html"

    with open(out_path, 'w') as f:
        f.write(html)
    print(f"Wrote {out_path} ({total} questions: "
          f"{counts['easy']} easy, {counts['medium']} medium, {counts['hard']} hard)")


if __name__ == '__main__':
    main()
