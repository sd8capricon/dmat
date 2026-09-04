# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A dMAT (a standardized reasoning admissions test) exam-prep project. There is no
application code here — the repository consists entirely of three Claude Code
skills (`.claude/skills/*`) that procedurally generate self-contained HTML
practice-question files for three dMAT question types:

- **figure-sequence-generator** → `FS-<yymmdd>-<total>.html` — 4×4 matrices of
  shapes that move/rotate/change colour across a sequence.
- **latin-square-generator** → `LS-<yymmdd>-<total>.html` — 5×5 grids (letters
  A–E) with one marked cell to deduce.
- **math-equation-generator** → `ME-<yymmdd>-<total>.html` — systems of 2–4
  equations in unknowns A–D.

Generated `.html` files are saved to the project root and are the actual
deliverable the user asks for — there is no build/lint/test pipeline in the
usual sense; "correctness" is enforced by each generator script itself
(bounds/overlap checks, a naked-single solver, or brute-force uniqueness
search — see each skill for details).

## Working in this repo

- Each question type is driven by its skill (invoke via `/figure-sequence-generator`,
  `/latin-square-generator`, `/math-equation-generator`, or let it trigger
  automatically when the user asks for practice questions). **Read the
  relevant `SKILL.md` before generating anything** — each one documents exact
  inputs to gather, the output filename convention, the CLI invocation, and a
  mandatory post-generation verification step.
- **Never hand-author a question in the conversation.** All three skills exist
  specifically because freehand-authored figure sequences / Latin squares /
  equation systems are extremely easy to get subtly wrong (non-unique
  answers, overlapping figures, unsolvable-by-the-allowed-method puzzles).
  Every generator is self-verifying (retry-until-valid, brute-force checks,
  or `assert`-verified solver chains) — a clean run with no traceback is
  itself evidence of correctness. Extend the relevant `scripts/generate_*.py`
  in place for new requirements instead of writing parallel logic by hand.
- Run generators with `python3` (no dependencies beyond the standard
  library), e.g.:
  ```
  python3 .claude/skills/figure-sequence-generator/scripts/generate_fs.py --easy 5 --medium 5 --hard 5 --out FS-260902-15.html
  python3 .claude/skills/latin-square-generator/scripts/generate_ls.py --easy 5 --medium 5 --hard 5 --out LS-260902-15.html
  python3 .claude/skills/math-equation-generator/scripts/generate_me.py --easy 5 --medium 5 --hard 5 --out ME-260902-15.html
  ```
  Omit any `--easy/--medium/--hard` flag that would be 0. Only pass `--seed`
  when the user explicitly wants reproducible output.
- Each skill's "Constraints and pitfalls learned building this" section
  records hard-won decisions (grid size, allowed rule grammar, difficulty
  measure, colour palette, distractor-construction method, etc.) — treat
  these as settled unless the user explicitly asks to revisit them.
- Difficulty tiers are configured in each script's `TIERS` dict (and related
  sampling logic) — adjust there rather than hand-tuning generated output.
- After generation, always run the skill's Step 4 verification (visual
  spot-check for figure sequences; a structural regex audit for Latin
  squares; an independent brute-force re-derivation from the rendered HTML
  for math equations) before reporting the file as done.
