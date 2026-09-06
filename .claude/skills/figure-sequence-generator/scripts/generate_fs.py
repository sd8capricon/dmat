#!/usr/bin/env python3
"""
Generate dMAT-style "Figure Sequence" reasoning questions as a self-contained HTML file.

Core idea: NEVER hand-draw a sequence and hope it's logically consistent. Instead:
  1. Randomly sample a rule set per figure (position / orientation / colour channels).
  2. Simulate all 6 matrices deterministically from those rules.
  3. Verify the result never overlaps figures or leaves the 4x4 grid; retry if it does.
  4. Derive wrong-answer options by mutating exactly one channel of one figure away
     from the simulated truth (the "one channel out of phase" trap style used by the
     real exam), so there is provably exactly one correct option per sub-question.

Usage:
  python3 generate_fs.py --easy 5 --medium 10 --hard 5 [--out FS-20-260902.html] [--seed 42]

If --out is omitted, the file is named FS-<total>-<yymmdd>.html in the current directory.
"""
import argparse
import copy
import datetime
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Grid & simulation engine
# ---------------------------------------------------------------------------
# Grid is modelled as 4 rows x 4 columns (row 1 = top, column 1 = left), matching
# the dMAT guide's own explanatory example ("on a 4x4 grid the ring is twelve
# cells"). The real exam sometimes renders a wider (e.g. 4x5) grid, but 4x4 is a
# faithful, fully-verified simplification -- change GRID_R/GRID_C together with
# RING_CW below if a non-square grid is ever required.
GRID_R, GRID_C = 4, 4

RING_CW = [(1, 1), (1, 2), (1, 3), (1, 4), (2, 4), (3, 4), (4, 4),
           (4, 3), (4, 2), (4, 1), (3, 1), (2, 1)]

COLOR_HEX = {'charcoal': '#37474F', 'orange': '#FB8C00', 'blue': '#1E88E5', 'yellow': '#FDD835'}
COLORS = list(COLOR_HEX.keys())
HEADING = {0: 'up', 90: 'right', 180: 'down', 270: 'left'}

# Only rotation-ASYMMETRIC shapes belong here: every 90-degree step (0/90/180/270)
# must render as a visually distinct silhouette. A circle, square or regular
# hexagon looks the same (or ambiguous) after some 90-degree rotations, which
# would make the "orientation" channel untestable / create false-duplicate
# answer options. If a new shape is added, sanity-check all 4 rotations by eye
# before trusting it here.
SHAPES = ['house', 'pin', 'arrow', 'chevron', 'flag']


def ring_index(pos):
    return RING_CW.index(pos)


def border_move(start, k, clockwise=True):
    n = len(RING_CW)
    idx = ring_index(start)
    return RING_CW[(idx + k) % n] if clockwise else RING_CW[(idx - k) % n]


def bounce_1d(pos, direction, steps, lo=1, hi=4):
    for _ in range(steps):
        nxt = pos + direction
        if nxt < lo or nxt > hi:
            direction = -direction
            nxt = pos + direction
        pos = nxt
    return pos, direction


def diagonal_move(r, c, dr, dc, steps, lo=1, hi=4):
    for _ in range(steps):
        nr, nc = r + dr, c + dc
        if nr < lo or nr > hi:
            dr = -dr
            nr = r + dr
        if nc < lo or nc > hi:
            dc = -dc
            nc = c + dc
        r, c = nr, nc
    return r, c, dr, dc


def simulate_figure(fig, n_transitions=5):
    """Simulate a figure across matrices 1..6 (index 0..5) from its rule dict."""
    r, c = fig['pos_start']
    deg = fig['orient_start'] % 360
    cycle = fig['colour_cycle']
    cidx = fig['colour_start_idx']
    dr, dc = fig.get('dr', 0), fig.get('dc', 0)
    clockwise = fig.get('clockwise', True)

    states = [{'pos': (r, c), 'deg': deg, 'colour': cycle[cidx % len(cycle)]}]
    for t in range(1, n_transitions + 1):
        if fig['pos_type'] == 'through':
            step = t if fig['step_mode'] == 'x+1' else fig['step_val']
            if dr != 0 and dc != 0:
                for _ in range(step):
                    r, c, dr, dc = diagonal_move(r, c, dr, dc, 1)
            else:
                if dr != 0:
                    r, dr = bounce_1d(r, dr, step)
                if dc != 0:
                    c, dc = bounce_1d(c, dc, step)
        elif fig['pos_type'] == 'border':
            step = t if fig['step_mode'] == 'x+1' else fig['step_val']
            r, c = border_move((r, c), step, clockwise)
        # else 'fixed': position unchanged

        if fig['orient_mode'] == 'const':
            deg = (deg + fig['orient_val']) % 360
        elif fig['orient_mode'] == 'x+1':
            deg = (deg + 90 * t) % 360
        # else 'fixed': unchanged

        if fig['colour_mode'] == 'const':
            cidx = (cidx + fig['colour_val']) % len(cycle)
        elif fig['colour_mode'] == 'x+1':
            cidx = (cidx + t) % len(cycle)
        # else 'fixed': unchanged

        states.append({'pos': (r, c), 'deg': deg % 360, 'colour': cycle[cidx % len(cycle)]})
    return states


def combo_at(all_states, idx):
    return [fs[idx] for fs in all_states]


def combo_key(combo):
    return tuple((s['pos'], s['deg'], s['colour']) for s in combo)


def has_overlap(combo):
    cells = [s['pos'] for s in combo]
    return len(cells) != len(set(cells))


def in_bounds(all_states):
    return all(1 <= s['pos'][0] <= GRID_R and 1 <= s['pos'][1] <= GRID_C
               for fs in all_states for s in fs)


# ---------------------------------------------------------------------------
# Difficulty tiers
# ---------------------------------------------------------------------------
# n_figures            -> reasoning load (how many independent objects to track)
# x_plus_1_budget      -> how many (figure, channel) slots may use x+1 stepping;
#                         x+1 is what turns a "spot the constant rule" item into
#                         a genuine hard item (per the guide: you must convert
#                         position to path-length-travelled to detect it).
# allow_diagonal       -> diagonal bouncers are harder to track (direction flips
#                         on both axes at a corner) so reserve for medium/hard.
# colour_cycle_lengths -> length-3 cycles are the main "colour phase" trap source.
TIERS = {
    'easy': dict(n_figures=(1, 1), x_plus_1_budget=0, allow_diagonal=False,
                 colour_cycle_lengths=(1, 2), step_vals=(1, 2)),
    'medium': dict(n_figures=(2, 2), x_plus_1_budget=1, allow_diagonal=True,
                   colour_cycle_lengths=(1, 2, 3), step_vals=(1, 2)),
    'hard': dict(n_figures=(3, 4), x_plus_1_budget=3, allow_diagonal=True,
                 colour_cycle_lengths=(2, 3), step_vals=(1, 2, 3)),
}


def random_figure(tier_cfg, shape, rng, x_budget_left):
    """Build one figure's rule dict. Returns (fig, x_plus_1_used_count)."""
    x_used = 0
    pos_type = rng.choice(['through', 'through', 'border', 'fixed'])
    fig = {'shape': shape}

    if pos_type == 'fixed':
        fig.update(pos_type='fixed', pos_start=(rng.randint(1, GRID_R), rng.randint(1, GRID_C)))
    elif pos_type == 'border':
        start = rng.choice(RING_CW)
        use_xp1 = x_budget_left > 0 and rng.random() < 0.5
        fig.update(pos_type='border', pos_start=start, clockwise=rng.choice([True, False]),
                   step_mode='x+1' if use_xp1 else 'const',
                   step_val=rng.choice(tier_cfg['step_vals']))
        if use_xp1:
            x_used += 1
    else:  # through
        diag_ok = tier_cfg['allow_diagonal']
        kind = rng.choice(['h', 'v', 'diag'] if diag_ok else ['h', 'v'])
        dr, dc = {'h': (0, rng.choice([1, -1])),
                   'v': (rng.choice([1, -1]), 0),
                   'diag': (rng.choice([1, -1]), rng.choice([1, -1]))}[kind]
        use_xp1 = x_budget_left > 0 and rng.random() < 0.5
        fig.update(pos_type='through', dr=dr, dc=dc,
                   pos_start=(rng.randint(1, GRID_R), rng.randint(1, GRID_C)),
                   step_mode='x+1' if use_xp1 else 'const',
                   step_val=rng.choice(tier_cfg['step_vals']))
        if use_xp1:
            x_used += 1

    # Orientation
    orient_mode = rng.choice(['fixed', 'const', 'const', 'x+1' if x_budget_left - x_used > 0 else 'const'])
    fig['orient_start'] = rng.choice([0, 90, 180, 270])
    if orient_mode == 'x+1':
        x_used += 1
    fig['orient_mode'] = orient_mode
    if orient_mode == 'const':
        fig['orient_val'] = rng.choice([90, 180, 270])

    # Colour
    cyc_len = rng.choice(tier_cfg['colour_cycle_lengths'])
    fig['colour_cycle'] = rng.sample(COLORS, cyc_len)
    fig['colour_start_idx'] = 0
    if cyc_len == 1:
        fig['colour_mode'] = 'fixed'
    else:
        use_xp1 = x_budget_left - x_used > 0 and rng.random() < 0.4
        fig['colour_mode'] = 'x+1' if use_xp1 else 'const'
        if use_xp1:
            x_used += 1
        else:
            fig['colour_val'] = 1

    return fig, x_used


def build_random_item(tier, rng, max_attempts=400):
    cfg = TIERS[tier]
    n_figs = rng.randint(*cfg['n_figures'])
    for _ in range(max_attempts):
        shapes = rng.sample(SHAPES, n_figs)
        figs = []
        x_left = cfg['x_plus_1_budget']
        for shape in shapes:
            fig, used = random_figure(cfg, shape, rng, x_left)
            x_left = max(0, x_left - used)
            figs.append(fig)
        all_states = [simulate_figure(f) for f in figs]
        if not in_bounds(all_states):
            continue
        if any(has_overlap(combo_at(all_states, m)) for m in range(6)):
            continue
        return figs, all_states
    raise RuntimeError(f"Could not build a valid '{tier}' item after {max_attempts} attempts")


# ---------------------------------------------------------------------------
# Distractor generation: always a genuine single-channel error, never a
# cosmetic redraw. This is what guarantees a unique correct answer per option
# set instead of an ambiguous "which one looks right" guess.
# ---------------------------------------------------------------------------
def mutate_pos(fig, states, target_idx, rng):
    prev = states[target_idx - 1]['pos']
    cur = states[target_idx]['pos']
    if prev != cur:
        return prev  # "forgot to advance" trap
    # Figure didn't move this step -- nudge it to a neighbouring in-bounds cell.
    r, c = cur
    candidates = [(r + dr, c + dc) for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]
                  if 1 <= r + dr <= GRID_R and 1 <= c + dc <= GRID_C]
    return rng.choice(candidates)


def mutate_orient(fig, states, target_idx, rng):
    prev = states[target_idx - 1]['deg']
    cur = states[target_idx]['deg']
    if prev != cur:
        return prev  # "forgot to rotate" trap
    return (cur + 90) % 360  # fake rotation on a fixed figure


def mutate_colour(fig, states, target_idx, rng, others):
    prev = states[target_idx - 1]['colour']
    cur = states[target_idx]['colour']
    if prev != cur:
        return prev  # classic "colour one step out of phase" trap
    choices = [c for c in COLORS if c != cur]
    return rng.choice(choices)


def gen_distractors(figs, all_states, target_idx, rng, n=3):
    correct = combo_at(all_states, target_idx)
    seen = {combo_key(correct)}
    out = []
    channels = ['pos', 'orient', 'colour']
    fig_order = list(range(len(figs)))
    attempts = 0
    ci = 0
    while len(out) < n and attempts < 60:
        attempts += 1
        fig_i = fig_order[attempts % len(fig_order)]
        channel = channels[ci % len(channels)]
        if attempts % len(fig_order) == 0:
            ci += 1
        cand = copy.deepcopy(correct)
        if channel == 'pos':
            cand[fig_i]['pos'] = mutate_pos(figs[fig_i], all_states[fig_i], target_idx, rng)
        elif channel == 'orient':
            cand[fig_i]['deg'] = mutate_orient(figs[fig_i], all_states[fig_i], target_idx, rng)
        else:
            cand[fig_i]['colour'] = mutate_colour(figs[fig_i], all_states[fig_i], target_idx, rng, cand)
        key = combo_key(cand)
        if key in seen or has_overlap(cand):
            continue
        seen.add(key)
        out.append(cand)
    if len(out) < n:
        raise RuntimeError("Could not generate enough distinct distractors; regenerate item")
    return out


def build_options(figs, all_states, target_idx, rng):
    correct = combo_at(all_states, target_idx)
    distractors = gen_distractors(figs, all_states, target_idx, rng)
    combos = [('correct', correct)] + [('wrong', d) for d in distractors]
    rng.shuffle(combos)
    letters = ['A', 'B', 'C', 'D']
    options = []
    correct_letter = None
    for letter, (tag, combo) in zip(letters, combos):
        options.append({'letter': letter, 'state': combo})
        if tag == 'correct':
            correct_letter = letter
    return {'options': options, 'correct': correct_letter}


# ---------------------------------------------------------------------------
# Rule -> plain-English description (mirrors the official solution-key style)
# ---------------------------------------------------------------------------
def describe_position(fig):
    if fig['pos_type'] == 'fixed':
        return "Does not move."
    if fig['pos_type'] == 'through':
        dr, dc = fig['dr'], fig['dc']
        if dr != 0 and dc != 0:
            vert = 'down' if dr > 0 else 'up'
            horiz = 'right' if dc > 0 else 'left'
            direction = f"{vert}-{horiz} (diagonally &mdash; stays diagonal after any bounce)"
        elif dr != 0:
            direction = 'down' if dr > 0 else 'up'
        else:
            direction = 'right' if dc > 0 else 'left'
        step_txt = ("by x+1 cells each matrix (1, then 2, then 3, then 4, then 5)"
                    if fig['step_mode'] == 'x+1'
                    else f"by {fig['step_val']} cell{'s' if fig['step_val'] != 1 else ''} each matrix")
        return f"Moves {direction}, {step_txt}, bouncing off the outer wall."
    dirw = 'clockwise' if fig['clockwise'] else 'anticlockwise'
    step_txt = ("by x+1 cells each matrix (1, then 2, then 3, then 4, then 5)"
                if fig['step_mode'] == 'x+1'
                else f"by {fig['step_val']} cell{'s' if fig['step_val'] != 1 else ''} each matrix")
    return f"Moves along the outer border {dirw}, {step_txt}."


def describe_orientation(fig):
    if fig['orient_mode'] == 'fixed':
        return "Does not rotate."
    if fig['orient_mode'] == 'const':
        return f"Rotates {fig['orient_val']}&deg; clockwise each matrix."
    return ("Rotates by x+1 steps of 90&deg; clockwise each matrix "
            "(90, then 180, then 270, then 360&equiv;0, then 450&equiv;90).")


def describe_colour(fig):
    cyc = fig['colour_cycle']
    if fig['colour_mode'] == 'fixed' or len(cyc) == 1:
        return f"Stays {cyc[0]}."
    cyc_txt = ' &rarr; '.join(cyc) + ' &rarr; (repeat)'
    if fig['colour_mode'] == 'const':
        adv = fig['colour_val']
        return f"Steps through the colour cycle {cyc_txt}, advancing {adv} place{'s' if adv != 1 else ''} each matrix."
    return f"Steps through the colour cycle {cyc_txt}, advancing by x+1 places each matrix (1, then 2, then 3, ...)."


def fig_rule_html(fig, start_state):
    r, c = start_state['pos']
    heading = HEADING[start_state['deg']]
    colour = start_state['colour']
    shape_name = fig['shape'].capitalize()
    return (f"<p><strong>{shape_name}</strong> &mdash; starts at row {r}, column {c}, "
            f"heading {heading}, {colour}."
            f"<br>&nbsp;&nbsp;Position: {describe_position(fig)}"
            f"<br>&nbsp;&nbsp;Orientation: {describe_orientation(fig)}"
            f"<br>&nbsp;&nbsp;Colour: {describe_colour(fig)}</p>")


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
SYMBOLS = '''
<svg width="0" height="0" style="position:absolute">
<defs>
<symbol id="shape-house" viewBox="0 0 100 100"><path d="M50 6 L94 45 L94 94 L6 94 L6 45 Z"/></symbol>
<symbol id="shape-pin" viewBox="0 0 100 100"><path d="M50 5 C63 28 85 52 85 70 A35 35 0 1 1 15 70 C15 52 37 28 50 5 Z"/></symbol>
<symbol id="shape-arrow" viewBox="0 0 100 100"><path d="M50 4 L82 42 L64 42 L64 96 L36 96 L36 42 L18 42 Z"/></symbol>
<symbol id="shape-chevron" viewBox="0 0 100 100"><path d="M50 12 L88 82 L12 82 Z"/></symbol>
<symbol id="shape-flag" viewBox="0 0 100 100"><path d="M44 6 H56 V94 H44 Z"/><path d="M56 12 L90 30 L56 48 Z"/></symbol>
</defs>
</svg>
'''


def svg_figure(shape, deg, colour, size=34):
    hexc = COLOR_HEX[colour]
    return (f'<svg class="fig" width="{size}" height="{size}" viewBox="0 0 100 100">'
            f'<use href="#shape-{shape}" transform="rotate({deg} 50 50)" fill="{hexc}"/></svg>')


def render_grid(shapes, states, cell=44):
    size = cell * GRID_C
    occ = {tuple(s['pos']): (shape, s) for s, shape in zip(states, shapes)}
    cells_html = []
    for r in range(1, GRID_R + 1):
        for c in range(1, GRID_C + 1):
            content = ""
            if (r, c) in occ:
                shape, st = occ[(r, c)]
                content = svg_figure(shape, st['deg'], st['colour'])
            cells_html.append(f'<div class="cell">{content}</div>')
    return f'<div class="grid" style="width:{size}px;height:{size}px;">{"".join(cells_html)}</div>'


def render_matrix_block(label, shapes, states):
    return f'<div class="matrix-block"><div class="matrix-label">{label}</div>{render_grid(shapes, states)}</div>'


def render_option(shapes, opt, group_name, correct_letter):
    is_correct = (opt['letter'] == correct_letter)
    grid = render_grid(shapes, opt['state'])
    return (f'<button type="button" class="option" data-correct="{str(is_correct).lower()}" '
            f'data-group="{group_name}"><div class="option-letter">{opt["letter"]}</div>{grid}</button>')


DIFF_LABEL = {'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'}


def render_item(idx, tier, figs, all_states):
    shapes = [f['shape'] for f in figs]
    m1234 = [combo_at(all_states, m) for m in range(4)]
    matrices_html = "".join(render_matrix_block(f"Matrix {i + 1}", shapes, m1234[i]) for i in range(4))

    m5 = build_options(figs, all_states, 4, random)
    m6 = build_options(figs, all_states, 5, random)
    gname5, gname6 = f"item{idx}-m5", f"item{idx}-m6"
    opts5 = "".join(render_option(shapes, o, gname5, m5['correct']) for o in m5['options'])
    opts6 = "".join(render_option(shapes, o, gname6, m6['correct']) for o in m6['options'])
    rules_html = "".join(fig_rule_html(fig, m1234[0][i]) for i, fig in enumerate(figs))

    return f'''
<section class="item" id="item-{idx}">
  <div class="item-header">
    <h2>Question {idx} <span class="badge badge-{tier}">{DIFF_LABEL[tier]} &middot; {len(figs)} figure{'s' if len(figs) != 1 else ''}</span></h2>
  </div>
  <div class="sequence-row">{matrices_html}</div>

  <div class="prompt">Which is Matrix 5?</div>
  <div class="options-row" data-group="{gname5}">{opts5}</div>

  <div class="prompt">Which is Matrix 6?</div>
  <div class="options-row" data-group="{gname6}">{opts6}</div>

  <details class="solution">
    <summary>Show answer &amp; reasoning</summary>
    <p><strong>Matrix 5: {m5['correct']}</strong> &nbsp;&nbsp; <strong>Matrix 6: {m6['correct']}</strong></p>
    {rules_html}
  </details>
</section>
'''


CSS = '''
:root{
  --bg:#f4f5f8; --panel:#ffffff; --panel2:#fbfbfd; --line:#d7dbe4;
  --text:#1c2233; --text-dim:#5b6478; --accent:#3355cc;
  --good:#1f9d55; --bad:#d13b34;
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
.sequence-row{ display:flex; flex-wrap:wrap; gap:16px; align-items:flex-end; margin-bottom:18px; }
.matrix-block{ text-align:center; }
.matrix-label{ font-size:.75rem; color:var(--text-dim); margin-bottom:6px; font-weight:600; }
.grid{ display:grid; grid-template-columns:repeat(4,1fr); grid-template-rows:repeat(4,1fr);
  background:var(--panel2); border:1.5px solid var(--line); border-radius:6px; overflow:hidden;
  box-shadow:0 1px 2px rgba(20,25,40,.06); }
.cell{ border:.5px solid var(--line); display:flex; align-items:center; justify-content:center; }
.fig{ display:block; }
.prompt{ font-weight:600; margin:18px 0 10px; color:var(--text); }
.options-row{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:6px; }
.option{ background:var(--panel); border:2px solid var(--line); border-radius:10px; padding:8px;
  cursor:pointer; text-align:center; color:var(--text); transition:border-color .15s, background .15s;
  box-shadow:0 1px 3px rgba(20,25,40,.05); }
.option:hover{ border-color:var(--accent); }
.option-letter{ font-size:.75rem; font-weight:700; color:var(--text-dim); margin-bottom:6px; }
.option.selected-correct{ border-color:var(--good); background:rgba(31,157,85,.10); }
.option.selected-wrong{ border-color:var(--bad); background:rgba(209,59,52,.10); }
.option.reveal-correct{ border-color:var(--good); }
.options-row.answered .option{ cursor:default; }
.options-row.answered .option:hover{ border-color:var(--line); }
.options-row.answered .option.reveal-correct:hover{ border-color:var(--good); }
.solution{ margin-top:16px; background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:10px 16px; }
.solution summary{ cursor:pointer; font-weight:600; color:var(--accent); }
.solution p{ margin:10px 0; font-size:.92rem; color:var(--text-dim); }
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


def build_html(items_by_tier_order, counts):
    total = sum(counts.values())
    comp = ", ".join(f"{counts[t]} {DIFF_LABEL[t]}" for t in ('easy', 'medium', 'hard') if counts.get(t))
    items_html = "".join(
        render_item(i + 1, tier, figs, states)
        for i, (tier, figs, states) in enumerate(items_by_tier_order)
    )
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>dMAT Figure Sequences &mdash; {total} Questions</title>
<style>{CSS}</style>
</head>
<body>
{SYMBOLS}
<header class="page-header">
  <h1>Figure Sequences Practice Set</h1>
  <p>{total} items ({comp}), in the dMAT Core Module format. Each item shows Matrix 1&ndash;4; you pick <strong>both</strong> Matrix 5 and Matrix 6.</p>
  <div class="instructions">
    <strong>Reminders (the closed rule set):</strong>
    <ul>
      <li>Figures can change colour, and can rotate around their own axis.</li>
      <li>Figures move vertically, horizontally, or diagonally. A figure moving diagonally cannot switch to another movement type.</li>
      <li>Movement, rotation, or colour can advance by a constant amount, or by x+1 (step 1, then 2, then 3, then 4, then 5).</li>
      <li>Figures cannot disappear, overlap, or leave the matrix &mdash; on hitting the outer wall they either bounce off or travel along the border.</li>
      <li>Read each figure's three channels (position, orientation, colour) separately across all four matrices before combining them.</li>
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
def next_available_path(base_name):
    """base_name has no extension, e.g. 'FS-15-260906'. Returns the first of
    base_name.html, base_name-2.html, base_name-3.html, ... that doesn't
    already exist, so a second same-day request with the same total never
    silently clobbers an earlier file."""
    path = Path(f"{base_name}.html")
    n = 2
    while path.exists():
        path = Path(f"{base_name}-{n}.html")
        n += 1
    return str(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--easy', type=int, default=0)
    ap.add_argument('--medium', type=int, default=0)
    ap.add_argument('--hard', type=int, default=0)
    ap.add_argument('--out', type=str, default=None)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--force', action='store_true',
                     help='Overwrite --out if it already exists instead of refusing.')
    args = ap.parse_args()

    counts = {'easy': args.easy, 'medium': args.medium, 'hard': args.hard}
    total = sum(counts.values())
    if total <= 0:
        raise SystemExit("Specify at least one of --easy/--medium/--hard with a count > 0")

    if args.seed is not None:
        random.seed(args.seed)

    items = []
    for tier in ('easy', 'medium', 'hard'):
        for _ in range(counts[tier]):
            figs, states = build_random_item(tier, random)
            items.append((tier, figs, states))

    html = build_html(items, counts)

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
        out_path = next_available_path(f"FS-{total}-{yymmdd}")

    with open(out_path, 'w') as f:
        f.write(html)
    print(f"Wrote {out_path} ({total} questions: "
          f"{counts['easy']} easy, {counts['medium']} medium, {counts['hard']} hard)")


if __name__ == '__main__':
    main()
