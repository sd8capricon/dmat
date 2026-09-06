#!/usr/bin/env python3
"""
Generate dMAT-style "Mathematical Equations" reasoning questions as a
self-contained HTML file.

Core idea, mirroring the sibling figure-sequence-generator /
latin-square-generator skills: NEVER hand-write a system of equations and
hope it has a unique answer. Instead:

  1. Pick n distinct target integer values in [1, 20], one per unknown
     (A, B, C, ... up to D -- the real exam never uses more than 4 letters).
  2. Build n equations from those targets using one of two constructions
     that are correct *by construction*:
       - "chain": one equation isolates a single unknown; every other
         equation links a new unknown to one already known, so the whole
         system can be solved by pure forward substitution (no algebra
         held in your head at once).
       - "anchor": no equation isolates a single unknown. Every other
         unknown is expressed as an exact integer-affine function of one
         "anchor" unknown, and a final weighted-sum equation collapses
         everything into one equation in the anchor alone.
  3. Independently VERIFY every generated system by brute-force search over
     the full [1, 20]^n integer grid: reject and retry unless exactly one
     assignment satisfies every equation, and that assignment is the target
     we built it from. This is the same "simulate, then reject and retry if
     invalid" discipline the sibling skills use for grids/matrices, applied
     here to a search space small enough (<=20^4) to brute force directly
     instead of trusting the algebra.
  4. Distractors are built by reusing a sibling unknown's true value, or by
     nudging the correct value by a small offset -- never an arbitrary
     freehand number -- so wrong options are plausible slips, not noise.

Usage:
  python3 generate_me.py --easy 5 --medium 10 --hard 5 [--out ME-20-260902.html] [--seed 42]

If --out is omitted, the file is named ME-<total>-<yymmdd>.html in the
current directory.
"""
import argparse
import datetime
import itertools
import random
from pathlib import Path

LETTERS_POOL = ['A', 'B', 'C', 'D']

# ---------------------------------------------------------------------------
# Difficulty tiers
# ---------------------------------------------------------------------------
# n_unknowns   -> the real exam's own ladder: 2-in-2, then 3-in-3, then 4-in-4.
# chain_prob   -> probability the item uses the easier "chain" (read-off then
#                 substitute-forward) construction instead of "anchor"
#                 (express everything in one unknown, then collapse). Every
#                 worked hard/high-tier example in the reference guide
#                 (Nbyula-dMAT-Guide.pdf pages 69-75, ME-HIGH-02/03/05/06/08/
#                 09/10) opens with "no equation gives you a number on its
#                 own" -- i.e. hard items never offer a free read-off, so
#                 hard uses chain_prob = 0.
TIERS = {
    'easy':   dict(n_unknowns=2, chain_prob=0.65),
    'medium': dict(n_unknowns=3, chain_prob=0.50),
    'hard':   dict(n_unknowns=4, chain_prob=0.0),
}

DIFF_LABEL = {'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'}


# ---------------------------------------------------------------------------
# Equation construction
# ---------------------------------------------------------------------------
# Every equation is represented as a dict: {'text': str, 'vars': set(str),
# 'check': callable(values_dict) -> bool}. 'check' is the only thing that
# matters for correctness -- 'text' is purely for display, and every branch
# below builds both from the *same* numbers so they can never drift apart.


def single_var_equation(v, t, rng):
    """One equation, one unknown v, with true value t. Used for chain mode's
    read-off step. Division forms are only offered when they divide evenly."""
    forms = []

    k = rng.randint(1, 15)
    c = t + k
    forms.append((f"{v} + {k} = {c}", lambda val, v=v, k=k, c=c: val[v] + k == c))

    k = rng.randint(1, 15)
    c = t + k
    forms.append((f"{k} + {v} = {c}", lambda val, v=v, k=k, c=c: k + val[v] == c))

    if t > 1:
        k = rng.randint(1, min(15, t - 1))
        c = t - k
        forms.append((f"{v} - {k} = {c}", lambda val, v=v, k=k, c=c: val[v] - k == c))

    c = rng.randint(1, 15)
    k = t + c
    forms.append((f"{k} - {v} = {c}", lambda val, v=v, k=k, c=c: k - val[v] == c))

    m = rng.choice([2, 3, 4, 5])
    c = m * t
    forms.append((f"{m} × {v} = {c}", lambda val, v=v, m=m, c=c: m * val[v] == c))
    m = rng.choice([2, 3, 4, 5])
    c = m * t
    forms.append((f"{v} × {m} = {c}", lambda val, v=v, m=m, c=c: val[v] * m == c))

    for k in (2, 3, 4):
        if t % k == 0:
            c = t // k
            forms.append((f"{v} ÷ {k} = {c}",
                          lambda val, v=v, k=k, c=c: val[v] % k == 0 and val[v] // k == c))
    for m in (2, 3, 4, 5):
        k = m * t
        if k <= 200:
            forms.append((f"{k} ÷ {v} = {m}",
                          lambda val, v=v, k=k, m=m: val[v] != 0 and k % val[v] == 0 and k // val[v] == m))

    text, check = rng.choice(forms)
    return {'text': text, 'vars': {v}, 'check': check}


def pairwise_link_equation(new_v, ref_v, t_new, t_ref, rng):
    """One equation linking two unknowns, used for chain mode's substitute-
    forward steps. ref_v's value is already known when this is solved, so
    there is no need to track a symbolic (m, b) pair here -- any form that
    is true for (t_new, t_ref) is fair game, including opportunistic
    division when it happens to divide evenly."""
    forms = []
    d = t_ref - t_new
    if d > 0:
        forms.append((f"{new_v} + {d} = {ref_v}", lambda val, a=new_v, b=ref_v, d=d: val[a] + d == val[b]))
        forms.append((f"{ref_v} - {d} = {new_v}", lambda val, a=new_v, b=ref_v, d=d: val[b] - d == val[a]))
    elif d < 0:
        forms.append((f"{ref_v} + {-d} = {new_v}", lambda val, a=new_v, b=ref_v, d=-d: val[b] + d == val[a]))
        forms.append((f"{new_v} - {-d} = {ref_v}", lambda val, a=new_v, b=ref_v, d=-d: val[a] - d == val[b]))

    for m in (2, 3):
        b = t_ref - m * t_new
        forms.append((f"{m} × {new_v} {'+' if b >= 0 else '-'} {abs(b)} = {ref_v}" if b != 0
                      else f"{m} × {new_v} = {ref_v}",
                      lambda val, a=new_v, b_=ref_v, m=m, c=b: m * val[a] + c == val[b_]))
        b2 = t_new - m * t_ref
        forms.append((f"{m} × {ref_v} {'+' if b2 >= 0 else '-'} {abs(b2)} = {new_v}" if b2 != 0
                      else f"{m} × {ref_v} = {new_v}",
                      lambda val, a=new_v, b_=ref_v, m=m, c=b2: m * val[b_] + c == val[a]))

    for k in (2, 3, 4):
        if t_ref % k == 0 and t_ref // k == t_new:
            forms.append((f"{ref_v} ÷ {k} = {new_v}",
                          lambda val, a=new_v, b_=ref_v, k=k: val[b_] % k == 0 and val[b_] // k == val[a]))
        if t_new % k == 0 and t_new // k == t_ref:
            forms.append((f"{new_v} ÷ {k} = {ref_v}",
                          lambda val, a=new_v, b_=ref_v, k=k: val[a] % k == 0 and val[a] // k == val[b_]))

    text, check = rng.choice(forms)
    return {'text': text, 'vars': {new_v, ref_v}, 'check': check}


def pairwise_express_equation(new_v, anchor_v, t_new, t_anchor, rng):
    """One equation expressing new_v as an exact integer-affine function of
    anchor_v: new_v = m * anchor_v + b. Used for anchor mode. Restricted to
    integer (m, b) -- unlike pairwise_link_equation above, this value feeds
    into a symbolic collapse later, so a fractional coefficient here would
    make that collapse messy/unverifiable by hand. This is a deliberate,
    documented simplification (see SKILL.md); it costs some of the
    division-flavoured equations real items show, in exchange for a
    guaranteed-clean "tidies to K x anchor + B = total" narrative line."""
    m = rng.choice([2, 3]) if rng.random() < 0.35 else 1
    b = t_new - m * t_anchor
    if m == 1:
        if b > 0:
            text = f"{anchor_v} + {b} = {new_v}"
        elif b < 0:
            text = f"{new_v} + {-b} = {anchor_v}"
        else:
            text = f"{anchor_v} = {new_v}"
    else:
        if b > 0:
            text = f"{m} × {anchor_v} + {b} = {new_v}"
        elif b < 0:
            text = f"{m} × {anchor_v} - {-b} = {new_v}"
        else:
            text = f"{m} × {anchor_v} = {new_v}"
    check = (lambda val, a=new_v, b_=anchor_v, m=m, c=b: m * val[b_] + c == val[a])
    return {'text': text, 'vars': {new_v, anchor_v}, 'check': check}, m, b


def collapse_equation(letters, targets, rng):
    """Final anchor-mode equation: a small-integer weighted sum of every
    unknown equal to a constant. Mirrors the near-universal pattern in every
    worked hard/high-tier reference example (e.g. 'A + B + C + D = 41')."""
    weights = {l: 1 for l in letters}
    if rng.random() < 0.3:
        weights[rng.choice(letters)] = 2
    total = sum(weights[l] * targets[l] for l in letters)
    terms = [(f"{weights[l]} × {l}" if weights[l] != 1 else l) for l in letters]
    text = " + ".join(terms) + f" = {total}"
    check = lambda val, weights=weights, total=total: sum(weights[l] * val[l] for l in letters) == total
    return {'text': text, 'vars': set(letters), 'check': check}, weights, total


# ---------------------------------------------------------------------------
# Item (system) construction
# ---------------------------------------------------------------------------
def validate_unique(letters, equations, targets, lo=1, hi=20):
    """Brute-force ground truth: exactly one assignment in [lo, hi]^n may
    satisfy every equation, and it must be the assignment we built from."""
    n = len(letters)
    found = 0
    for combo in itertools.product(range(lo, hi + 1), repeat=n):
        val = dict(zip(letters, combo))
        if all(eq['check'](val) for eq in equations):
            found += 1
            if found == 1:
                match = combo
            if found > 1:
                return False
    if found != 1:
        return False
    return match == tuple(targets[l] for l in letters)


def build_chain_system(letters, targets, rng):
    order = letters[:]
    rng.shuffle(order)
    equations = [single_var_equation(order[0], targets[order[0]], rng)]
    steps = [{'kind': 'readoff', 'var': order[0], 'eq_text': equations[0]['text'],
              'value': targets[order[0]]}]
    for i in range(1, len(order)):
        new_v, ref_v = order[i], order[i - 1]
        eq = pairwise_link_equation(new_v, ref_v, targets[new_v], targets[ref_v], rng)
        equations.append(eq)
        steps.append({'kind': 'link', 'var': new_v, 'ref': ref_v, 'eq_text': eq['text'],
                      'ref_value': targets[ref_v], 'value': targets[new_v]})
    rng.shuffle(equations)
    return equations, {'mode': 'chain', 'steps': steps}


def build_anchor_system(letters, targets, rng, max_attempts=60):
    for _ in range(max_attempts):
        anchor = rng.choice(letters)
        others = [l for l in letters if l != anchor]
        equations = []
        express = []  # (var, m, b, eq)
        ok = True
        for v in others:
            eq, m, b = pairwise_express_equation(v, anchor, targets[v], targets[anchor], rng)
            equations.append(eq)
            express.append((v, m, b, eq))
        coll_eq, weights, total = collapse_equation(letters, targets, rng)
        K = weights[anchor] + sum(weights[v] * m for (v, m, b, _e) in express)
        B = sum(weights[v] * b for (v, m, b, _e) in express)
        if K == 0:
            ok = False
        equations.append(coll_eq)
        if not ok:
            continue
        rng.shuffle(equations)
        steps = {
            'mode': 'anchor', 'anchor': anchor, 'express': express,
            'collapse_text': coll_eq['text'], 'K': K, 'B': B, 'total': total,
        }
        return equations, steps
    raise RuntimeError("Could not build a non-degenerate anchor system")


def build_item(tier, rng, max_attempts=200):
    cfg = TIERS[tier]
    n = cfg['n_unknowns']
    letters = LETTERS_POOL[:n]
    for _ in range(max_attempts):
        targets = dict(zip(letters, rng.sample(range(1, 21), n)))
        use_chain = rng.random() < cfg['chain_prob']
        try:
            if use_chain:
                equations, narrative = build_chain_system(letters, targets, rng)
            else:
                equations, narrative = build_anchor_system(letters, targets, rng)
        except RuntimeError:
            continue
        if validate_unique(letters, equations, targets):
            return letters, targets, equations, narrative
    raise RuntimeError(f"Could not build a valid '{tier}' item after {max_attempts} attempts")


# ---------------------------------------------------------------------------
# Distractors: reuse a sibling unknown's true value, or nudge by a small
# offset -- never an arbitrary freehand number.
# ---------------------------------------------------------------------------
def build_distractors(correct, targets, letters, asked, rng, n=3):
    pool = [targets[l] for l in letters if l != asked and targets[l] != correct]
    rng.shuffle(pool)
    offsets = [1, -1, 2, -2, 3, -3, 4, -4, 5, -5]
    rng.shuffle(offsets)
    out, seen = [], {correct}
    for v in pool:
        if v not in seen:
            out.append(v)
            seen.add(v)
        if len(out) == n:
            break
    for off in offsets:
        if len(out) == n:
            break
        cand = correct + off
        if cand >= 1 and cand not in seen:
            out.append(cand)
            seen.add(cand)
    return out[:n]


# ---------------------------------------------------------------------------
# Narrative (the "Show answer & reasoning" text)
# ---------------------------------------------------------------------------
def render_narrative(letters, targets, narrative, asked):
    solved_line = ", ".join(f"{l} = {targets[l]}" for l in letters)
    paras = [f"<p><strong>Answer: {asked} = {targets[asked]}</strong> ({solved_line})</p>"]

    if narrative['mode'] == 'chain':
        steps = narrative['steps']
        first = steps[0]
        paras.append(
            f"<p>Read <code>{first['eq_text']}</code> first &mdash; it is the only equation with a "
            f"single unknown. That hands you {first['var']} = {first['value']} directly.</p>"
        )
        for st in steps[1:]:
            paras.append(
                f"<p>Now take <code>{st['eq_text']}</code>. Since {st['ref']} = {st['ref_value']}, "
                f"this gives {st['var']} = {st['value']}.</p>"
            )
    else:
        anchor = narrative['anchor']
        n_eqs = len(narrative['express']) + 1
        paras.append(
            f"<p>No equation has a single unknown. {anchor} appears in every equation that matters here, "
            f"so anchor on {anchor}.</p>"
        )
        for (v, m, b, eq) in narrative['express']:
            expr = (f"{anchor}" if (m == 1 and b == 0) else
                    f"{m} × {anchor}" if b == 0 else
                    f"{anchor} + {b}" if m == 1 and b > 0 else
                    f"{anchor} - {-b}" if m == 1 and b < 0 else
                    f"{m} × {anchor} + {b}" if b > 0 else
                    f"{m} × {anchor} - {-b}")
            paras.append(f"<p>From <code>{eq['text']}</code>: {v} = {expr}. Nothing to compute yet &mdash; just carry it.</p>")
        K, B, total = narrative['K'], narrative['B'], narrative['total']
        rhs = total - B
        tidy = f"{K} × {anchor}" + (f" + {B}" if B > 0 else f" - {-B}" if B < 0 else "") + f" = {total}"
        paras.append(
            f"<p>Substitute every expression into <code>{narrative['collapse_text']}</code>, which tidies to "
            f"<code>{tidy}</code>. That pins it: {anchor} = {rhs} / {K} = {targets[anchor]}.</p>"
        )
        unwinds = []
        for (v, m, b, eq) in narrative['express']:
            unwinds.append(f"{v} = {targets[v]}")
        if unwinds:
            paras.append(f"<p>Unwind: {', '.join(unwinds)}.</p>")

    return "\n    ".join(paras)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
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
.eqn-row{ display:flex; flex-wrap:wrap; gap:12px; margin-bottom:18px; }
.eqn-chip{ background:var(--panel2); border:1px solid var(--line); border-radius:8px;
  padding:10px 16px; font-family:"SF Mono",Menlo,Consolas,monospace; font-size:1.02rem;
  color:var(--text); box-shadow:0 1px 2px rgba(20,25,40,.05); white-space:nowrap; }
.prompt{ font-weight:600; margin:0 0 10px; color:var(--text); }
.options-row{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:6px; }
.option{ background:var(--panel); border:2px solid var(--line); border-radius:10px; padding:10px 0;
  width:56px; cursor:pointer; text-align:center; color:var(--text); transition:border-color .15s, background .15s;
  box-shadow:0 1px 3px rgba(20,25,40,.05); }
.option:hover{ border-color:var(--accent); }
.option-letter-big{ font-size:1.15rem; font-weight:700; }
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
.solution code{ background:rgba(51,85,204,.08); padding:1px 5px; border-radius:4px; color:var(--text); }
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


def render_item(idx, tier, letters, targets, equations, narrative, rng):
    n = len(letters)
    asked = rng.choice(letters)
    correct = targets[asked]
    distractors = build_distractors(correct, targets, letters, asked, rng)
    choices = [correct] + distractors
    rng.shuffle(choices)

    eqn_html = "".join(f'<div class="eqn-chip">{eq["text"]}</div>' for eq in equations)
    gname = f"item{idx}"
    opts_html = "".join(
        f'<button type="button" class="option" data-correct="{str(v == correct).lower()}" '
        f'data-group="{gname}"><div class="option-letter-big">{v}</div></button>'
        for v in choices
    )
    solution_html = render_narrative(letters, targets, narrative, asked)

    return f'''
<section class="item" id="item-{idx}">
  <div class="item-header">
    <h2>Question {idx} <span class="badge badge-{tier}">{DIFF_LABEL[tier]} &middot; {n} unknown{'s' if n != 1 else ''}</span></h2>
  </div>
  <div class="eqn-row">{eqn_html}</div>
  <div class="prompt">What is the value of {asked}?</div>
  <div class="options-row" data-group="{gname}">{opts_html}</div>
  <details class="solution">
    <summary>Show answer &amp; reasoning</summary>
    {solution_html}
  </details>
</section>
'''


def build_html(items_by_tier_order, counts):
    total = sum(counts.values())
    comp = ", ".join(f"{counts[t]} {DIFF_LABEL[t]}" for t in ('easy', 'medium', 'hard') if counts.get(t))
    items_html = "".join(html for html in items_by_tier_order)
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>dMAT Mathematical Equations &mdash; {total} Questions</title>
<style>{CSS}</style>
</head>
<body>
<header class="page-header">
  <h1>Mathematical Equations Practice Set</h1>
  <p>{total} items ({comp}), in the dMAT Core Module format. Each item is a system of equations (2 unknowns for Easy, 3 for Medium, 4 for Hard) using the letters A&ndash;D.</p>
  <div class="instructions">
    <strong>Rules:</strong>
    <ul>
      <li>Each letter is a whole number between 1 and 20, and every system has exactly one solution.</li>
      <li>Operators are +, &minus;, &times; and &divide;. Work entirely in your head &mdash; no calculator, no notes.</li>
      <li>If one equation has only a single unknown, read it off first and substitute forward.</li>
      <li>If no equation offers a single unknown, pick the letter that appears in the most equations as your anchor, write every other letter as an expression in that anchor, then solve the one equation that collapses to the anchor alone.</li>
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
    """base_name has no extension, e.g. 'ME-15-260906'. Returns the first of
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

    rng = random.Random(args.seed)

    items_html = []
    idx = 0
    for tier in ('easy', 'medium', 'hard'):
        for _ in range(counts[tier]):
            idx += 1
            letters, targets, equations, narrative = build_item(tier, rng)
            items_html.append(render_item(idx, tier, letters, targets, equations, narrative, rng))

    html = build_html(items_html, counts)

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
        out_path = next_available_path(f"ME-{total}-{yymmdd}")

    with open(out_path, 'w') as f:
        f.write(html)
    print(f"Wrote {out_path} ({total} questions: "
          f"{counts['easy']} easy, {counts['medium']} medium, {counts['hard']} hard)")


if __name__ == '__main__':
    main()
