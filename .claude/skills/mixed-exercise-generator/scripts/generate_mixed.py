#!/usr/bin/env python3
"""
Generate a mixed dMAT practice set (Figure Sequences + Latin Squares +
Mathematical Equations) as a single self-contained HTML file.

Core idea: this script never re-implements question generation. It loads the
three sibling generator scripts --
  ../../figure-sequence-generator/scripts/generate_fs.py
  ../../latin-square-generator/scripts/generate_ls.py
  ../../math-equation-generator/scripts/generate_me.py
-- as plain Python modules and calls their own build_item/render_item
functions directly, then wraps the resulting item sections in one shared
page shell: merged CSS (the three sibling stylesheets are additive, not
conflicting -- see SKILL.md), one shared answer-check JS snippet (already
byte-identical across all three), and continuous question numbering across
the whole file. Each question type still gets its own labelled section with
its own rules/instructions block, copied verbatim from the sibling script
that owns that question type.

Usage:
  python3 generate_mixed.py \\
    --fs-easy 5 --fs-medium 5 --fs-hard 0 \\
    --ls-easy 0 --ls-medium 5 --ls-hard 5 \\
    --me-easy 5 --me-medium 0 --me-hard 0 \\
    --out Mixed-260906-25.html [--seed 42]

Omit any --<type>-<tier> flag that would be 0. A question type is included
in the output only if at least one of its three tier counts is > 0.
If --out is omitted, the file is named Mixed-<yymmdd>-<total>.html in the
current directory.
"""
import argparse
import datetime
import importlib.util
import random
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2]  # .../.claude/skills


def load_sibling(rel_path, module_name):
    """Load a sibling generator script as a module by file path (their
    directory names contain hyphens, so a normal dotted import can't reach
    them). Their own main()/argparse/CLI blocks are guarded by
    `if __name__ == '__main__'`, so importing them this way never runs their
    CLI or writes any file -- only their functions/constants become
    available."""
    path = SKILLS_DIR / rel_path
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


fs = load_sibling('figure-sequence-generator/scripts/generate_fs.py', 'dmat_gen_fs')
ls = load_sibling('latin-square-generator/scripts/generate_ls.py', 'dmat_gen_ls')
me = load_sibling('math-equation-generator/scripts/generate_me.py', 'dmat_gen_me')

TIERS = ('easy', 'medium', 'hard')
DIFF_LABEL = {'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'}

# Section metadata + rules text copied VERBATIM from each sibling script's own
# build_html() instructions block -- never hand-authored here, so the rules
# shown to the solver always match the engine that actually built the item.
TYPE_META = {
    'fs': {
        'code': 'FS',
        'title': 'Figure Sequences',
        'lead': 'Each item shows Matrix 1&ndash;4; you pick <strong>both</strong> Matrix 5 and Matrix 6.',
        'rules': '''
      <li>Figures can change colour, and can rotate around their own axis.</li>
      <li>Figures move vertically, horizontally, or diagonally. A figure moving diagonally cannot switch to another movement type.</li>
      <li>Movement, rotation, or colour can advance by a constant amount, or by x+1 (step 1, then 2, then 3, then 4, then 5).</li>
      <li>Figures cannot disappear, overlap, or leave the matrix &mdash; on hitting the outer wall they either bounce off or travel along the border.</li>
      <li>Read each figure's three channels (position, orientation, colour) separately across all four matrices before combining them.</li>
        ''',
    },
    'ls': {
        'code': 'LS',
        'title': 'Latin Squares',
        'lead': 'Each item is a 5&times;5 grid using the letters A&ndash;E.',
        'rules': '''
      <li>Each letter (A&ndash;E) appears exactly once in every row and exactly once in every column.</li>
      <li>Some cells are already filled in. Only the letters A&ndash;E may be used &mdash; no other symbols.</li>
      <li>Exactly one cell is marked with a red <strong>?</strong>. Work out which letter belongs there and click it below the grid.</li>
      <li>Sometimes you need to work out one or more other cells first before the marked cell becomes forced &mdash; that chain of deductions is what separates easy, medium and hard items.</li>
      <li>Only the marked cell's own row and own column can ever change its answer, but a stepping-stone cell elsewhere in the grid may need its own row/column solved first.</li>
        ''',
    },
    'me': {
        'code': 'ME',
        'title': 'Mathematical Equations',
        'lead': 'Each item is a system of equations (2 unknowns for Easy, 3 for Medium, 4 for Hard) using the letters A&ndash;D.',
        'rules': '''
      <li>Each letter is a whole number between 1 and 20, and every system has exactly one solution.</li>
      <li>Operators are +, &minus;, &times; and &divide;. Work entirely in your head &mdash; no calculator, no notes.</li>
      <li>If one equation has only a single unknown, read it off first and substitute forward.</li>
      <li>If no equation offers a single unknown, pick the letter that appears in the most equations as your anchor, write every other letter as an expression in that anchor, then solve the one equation that collapses to the anchor alone.</li>
        ''',
    },
}


# ---------------------------------------------------------------------------
# Per-type item building -- each one calls straight into the sibling module's
# own build_item/build_random_item + render_item, only supplying a continuous
# global index instead of that module's own per-file numbering.
# ---------------------------------------------------------------------------
def build_one_fs(rng_module, tier, idx):
    figs, states = fs.build_random_item(tier, rng_module)
    return fs.render_item(idx, tier, figs, states)


def build_one_ls(rng, tier, idx, seen_signatures):
    d = ls.build_item(rng, tier, seen_signatures)
    return ls.render_item(idx, d)


def build_one_me(rng, tier, idx):
    letters, targets, equations, narrative = me.build_item(tier, rng)
    return me.render_item(idx, tier, letters, targets, equations, narrative, rng)


def build_items_for_tier(key, tier, count, rng_arg, start_idx, seen_signatures=None):
    """Build `count` items of a single (type, tier) pair, threading a
    continuous idx. Shared by both the default grouped-by-type-only ordering
    (looped once per tier inside build_fs_items/etc.) and the exam-ladder
    ordering (called once per (tier, type) block in tier-major order)."""
    idx = start_idx
    items = []
    for _ in range(count):
        if key == 'fs':
            items.append(build_one_fs(rng_arg, tier, idx))
        elif key == 'ls':
            items.append(build_one_ls(rng_arg, tier, idx, seen_signatures))
        elif key == 'me':
            items.append(build_one_me(rng_arg, tier, idx))
        idx += 1
    return items, idx


def build_fs_items(counts, rng_module, start_idx):
    items_html = []
    idx = start_idx
    for tier in TIERS:
        new_items, idx = build_items_for_tier('fs', tier, counts[tier], rng_module, idx)
        items_html.extend(new_items)
    return items_html, idx


def build_ls_items(counts, rng, start_idx):
    items_html = []
    idx = start_idx
    seen_signatures = set()
    for tier in TIERS:
        new_items, idx = build_items_for_tier('ls', tier, counts[tier], rng, idx, seen_signatures)
        items_html.extend(new_items)
    return items_html, idx


def build_me_items(counts, rng, start_idx):
    items_html = []
    idx = start_idx
    for tier in TIERS:
        new_items, idx = build_items_for_tier('me', tier, counts[tier], rng, idx)
        items_html.extend(new_items)
    return items_html, idx


BUILDERS = {'fs': build_fs_items, 'ls': build_ls_items, 'me': build_me_items}


def next_available_path(base_name):
    """base_name has no extension, e.g. 'Mixed-260906-15'. Different type/tier
    compositions on the same day can land on the same auto-generated name
    (the name only encodes the date and the total, not the mix) -- so unlike
    the sibling single-type scripts, a plain total-based name collision here
    is routine, not a rare edge case (e.g. a practice-coach session reusing
    the same round size every round). Returns the first of base_name.html,
    base_name-2.html, base_name-3.html, ... that doesn't already exist,
    matching the '-2, -3, etc.' suffix convention already documented in this
    skill's SKILL.md."""
    path = Path(f"{base_name}.html")
    n = 2
    while path.exists():
        path = Path(f"{base_name}-{n}.html")
        n += 1
    return str(path)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
# The three sibling stylesheets share the same :root palette and most of the
# core .item/.badge/.solution rules byte-for-byte, but NOT .option/.options-row
# /.prompt: LS/ME size .option as a small fixed-width text button (48px/56px)
# while FS leaves it auto-width to hold a 176px shape grid. Concatenating
# verbatim lets whichever sibling loads last (ME) win that width for every
# section, squeezing FS's grids into a 56px box so figures spill into the
# next option card. The scoped overrides below re-assert each type's own
# values at higher specificity so section order can't matter. JS is still a
# safe verbatim share -- the three click-to-check snippets are byte-identical.
EXTRA_CSS = '''
.type-section + .type-section{ border-top:2px solid var(--line); margin-top:40px; padding-top:8px; }
.type-section-header h2{ margin:0 0 4px; font-size:1.4rem; }
.type-section-header > p{ color:var(--text-dim); margin:4px 0 0; }
.type-section-fs .option{ width:auto; padding:8px; }
.type-section-fs .options-row{ gap:14px; }
.type-section-fs .prompt{ margin:18px 0 10px; }
.type-section-ls .option{ width:48px; padding:10px 0; }
.type-section-ls .options-row{ gap:10px; }
.type-section-ls .prompt{ margin:0 0 10px; }
.type-section-me .option{ width:56px; padding:10px 0; }
.type-section-me .options-row{ gap:10px; }
.type-section-me .prompt{ margin:0 0 10px; }
'''

JS = fs.JS + fs.TIMER_JS


def render_section(key, counts, items_html, tier_label=None):
    """tier_label is None for the default grouped-by-type-only ordering
    (section spans every tier of that type). In exam-ladder mode, each
    (tier, type) pair gets its own block, so tier_label names that one tier
    and `counts` only holds that single tier's count -- the rules/lead text
    is still copied in full each time, matching this skill's "never
    paraphrase a sibling's rules" rule regardless of how blocks are sliced."""
    meta = TYPE_META[key]
    comp = ", ".join(f"{counts[t]} {DIFF_LABEL[t]}" for t in TIERS if counts.get(t))
    title = meta['title'] if tier_label is None else f"{meta['title']} &mdash; {DIFF_LABEL[tier_label]}"
    return f'''
<section class="type-section type-section-{key}">
  <div class="type-section-header">
    <h2>{title}</h2>
    <p>{sum(counts.values())} items ({comp}). {meta['lead']}</p>
    <div class="instructions">
      <strong>Rules:</strong>
      <ul>{meta['rules']}</ul>
    </div>
  </div>
  {"".join(items_html)}
</section>
'''


def build_html(blocks, type_counts, ladder=False):
    """`blocks` is an ordered list of (key, tier_label_or_None, counts, items_html)
    tuples, already in the exact document order to render -- grouped-by-type
    order for the default mode, tier-major/type-minor order for ladder mode."""
    total = sum(sum(c.values()) for c in type_counts.values())
    type_comp = ", ".join(
        f"{sum(type_counts[k].values())} {TYPE_META[k]['title']}"
        for k in ('fs', 'ls', 'me') if k in type_counts and sum(type_counts[k].values())
    )
    css = fs.CSS + ls.CSS + me.CSS + EXTRA_CSS + fs.TIMER_CSS
    symbols = fs.SYMBOLS if 'fs' in type_counts and sum(type_counts['fs'].values()) else ''
    body = "".join(
        render_section(key, counts, items_html, tier_label)
        for key, tier_label, counts, items_html in blocks
    )
    if ladder:
        order_note = ("Questions run as an exam ladder: easiest tier first, hardest tier "
                       "last across the whole set; within each tier, questions are grouped "
                       "by question type.")
    else:
        order_note = "Sections are grouped by question type; within each section, questions run easiest to hardest."
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>dMAT Mixed Practice &mdash; {total} Questions</title>
<style>{css}</style>
</head>
<body>
{symbols}
{fs.render_timer_bar(total)}
<header class="page-header">
  <h1>Mixed Practice Set</h1>
  <p>{total} items ({type_comp}), in the dMAT Core Module format. {order_note}</p>
  <div class="instructions">
    <strong>Timer:</strong>
    <ul>
      <li>Timer budget: {fs.SECONDS_PER_QUESTION}s per question ({fs.format_mmss(total * fs.SECONDS_PER_QUESTION)} total for this set), shown at the top of the page. Press <strong>Start</strong> when you begin, <strong>Lap</strong> after each question to log your split, <strong>Pause</strong> to hold, and <strong>Reset</strong> to start over &mdash; it's a pacing guide only and won't lock you out at zero.</li>
    </ul>
  </div>
</header>
<main>
{body}
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for t in ('fs', 'ls', 'me'):
        ap.add_argument(f'--{t}-easy', type=int, default=0)
        ap.add_argument(f'--{t}-medium', type=int, default=0)
        ap.add_argument(f'--{t}-hard', type=int, default=0)
    ap.add_argument('--out', type=str, default=None)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--force', action='store_true',
                     help='Overwrite --out if it already exists instead of refusing.')
    ap.add_argument('--ladder', action='store_true',
                     help='Order the whole file tier-major (all Easy across every type, '
                          'then all Medium, then all Hard) instead of the default '
                          'type-major grouping. Within each tier, questions are grouped '
                          'by type in fs/ls/me order.')
    args = ap.parse_args()

    type_counts = {
        'fs': {'easy': args.fs_easy, 'medium': args.fs_medium, 'hard': args.fs_hard},
        'ls': {'easy': args.ls_easy, 'medium': args.ls_medium, 'hard': args.ls_hard},
        'me': {'easy': args.me_easy, 'medium': args.me_medium, 'hard': args.me_hard},
    }
    total = sum(sum(c.values()) for c in type_counts.values())
    if total <= 0:
        raise SystemExit("Specify at least one --<type>-<tier> count > 0 (types: fs, ls, me)")

    # FS's own build_random_item()/render_item() draw from the global `random`
    # module (mirroring generate_fs.py's own main()); LS and ME take an
    # explicit random.Random instance. Seeding both with the same value keeps
    # the whole mixed run reproducible under --seed even though the two RNG
    # streams are independent.
    if args.seed is not None:
        random.seed(args.seed)
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    idx = 1
    blocks = []
    seen_signatures = set()  # LS dedup state must persist across tiers in ladder mode too
    if args.ladder:
        for tier in TIERS:
            for key in ('fs', 'ls', 'me'):
                count = type_counts[key][tier]
                if count <= 0:
                    continue
                rng_arg = random if key == 'fs' else rng
                items_html, idx = build_items_for_tier(key, tier, count, rng_arg, idx, seen_signatures)
                blocks.append((key, tier, {tier: count}, items_html))
    else:
        for key in ('fs', 'ls', 'me'):
            counts = type_counts[key]
            if sum(counts.values()) <= 0:
                continue
            rng_arg = random if key == 'fs' else rng
            items_html, idx = BUILDERS[key](counts, rng_arg, idx)
            blocks.append((key, None, counts, items_html))

    sections = {k: True for k, _, _, _ in blocks}
    html = build_html(blocks, type_counts, ladder=args.ladder)

    if args.out:
        out_path = args.out
        if Path(out_path).exists() and not args.force:
            raise SystemExit(
                f"{out_path} already exists. Pass --force to overwrite it "
                f"intentionally, or drop --out (or pick a different name) to "
                f"keep both files."
            )
    else:
        yymmdd = datetime.date.today().strftime('%y%m%d')
        out_path = next_available_path(f"Mixed-{yymmdd}-{total}")

    with open(out_path, 'w') as f:
        f.write(html)

    breakdown = "; ".join(
        f"{TYPE_META[k]['code']} {sum(type_counts[k].values())} ("
        + ", ".join(f"{type_counts[k][t]} {t}" for t in TIERS if type_counts[k][t])
        + ")"
        for k in ('fs', 'ls', 'me') if k in sections
    )
    print(f"Wrote {out_path} ({total} questions: {breakdown})")


if __name__ == '__main__':
    main()
