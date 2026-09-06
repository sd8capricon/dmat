# CLAUDE.md / AGENTS.md

These files provide guidance to coding agents when working in this repository. `CLAUDE.md` and
`AGENTS.md` are intentionally identical mirrors: read either one as the complete project
instructions, and update both together whenever these instructions change. Never make a
repository-instruction change in only one of the two files. Before finishing an instruction
change, verify that the two files remain byte-for-byte identical.

## What this repository is

A dMAT (a standardized reasoning admissions test) exam-prep project. There is no
application code here — the repository consists of Claude Code skills
(`.claude/skills/*`) that procedurally generate self-contained HTML
practice-question files for three dMAT question types, plus a combining skill
and a conversational coaching agent on top of them:

- **figure-sequence-generator** (skill) → `FS-<yymmdd>-<total>.html` — 4×4
  matrices of shapes that move/rotate/change colour across a sequence.
- **latin-square-generator** (skill) → `LS-<yymmdd>-<total>.html` — 5×5
  grids (letters A–E) with one marked cell to deduce.
- **math-equation-generator** (skill) → `ME-<yymmdd>-<total>.html` — systems
  of 2–4 equations in unknowns A–D.
- **mixed-exercise-generator** (skill) → `Mixed-<yymmdd>-<total>.html` —
  combines two or more of the above question types into one HTML file
  (per-type sections, continuous numbering), by calling the three generators'
  own functions directly rather than reimplementing anything.
- **practice-coach** (`.claude/agents/practice-coach.md`, an **agent**, not a
  skill) — conversational, session-only study coach. Talks with the user
  about goals/level/weak areas, turns that into a concrete type/tier/count
  plan, delegates all actual generation to the four skills above, and adapts
  later rounds from the user's self-reported results. It is an agent (not a
  skill) specifically so it can hold a genuine multi-turn conversation with
  `AskUserQuestion`; a Task-tool subagent can't do that (no `AskUserQuestion`,
  no live conversation visibility), so treat this one as invoked directly
  (addressed by name / as the active agent), not spawned as a background
  worker — see the file's own "note on how you might be invoked" for the
  degraded fallback if that ever happens anyway.

Generated `.html` files are saved to the project root and are the actual
deliverable the user asks for — there is no build/lint/test pipeline in the
usual sense; "correctness" is enforced by each generator script itself
(bounds/overlap checks, a naked-single solver, or brute-force uniqueness
search — see each skill for details). `practice-coach` adds no new
correctness surface of its own since it never generates a question directly.

## Working in this repo

- Each question type is driven by its skill (invoke via `/figure-sequence-generator`,
  `/latin-square-generator`, `/math-equation-generator`, `/mixed-exercise-generator`,
  or let one trigger automatically when the user asks for practice questions).
  Reach for the `practice-coach` agent instead when the user wants help
  deciding what to practice or wants an adaptive, multi-round session rather
  than a specific exact count/tier/type. **Read the relevant `SKILL.md`
  before generating anything** — each one documents exact inputs to gather,
  the output filename convention, the CLI invocation, and a mandatory
  post-generation verification step.
- **Never hand-author a question in the conversation.** All four generator
  skills exist specifically because freehand-authored figure sequences /
  Latin squares / equation systems are extremely easy to get subtly wrong
  (non-unique answers, overlapping figures, unsolvable-by-the-allowed-method
  puzzles). Every generator is self-verifying (retry-until-valid, brute-force
  checks, or `assert`-verified solver chains) — a clean run with no traceback
  is itself evidence of correctness. Extend the relevant `scripts/generate_*.py`
  in place for new requirements instead of writing parallel logic by hand.
  `mixed-exercise-generator` in particular must keep calling straight into
  the three single-type scripts' own functions rather than re-deriving any
  generation logic — see its own SKILL.md.
- Run generators with `python3` (no dependencies beyond the standard
  library), e.g.:
  ```
  python3 .claude/skills/figure-sequence-generator/scripts/generate_fs.py --easy 5 --medium 5 --hard 5 --out FS-260902-15.html
  python3 .claude/skills/latin-square-generator/scripts/generate_ls.py --easy 5 --medium 5 --hard 5 --out LS-260902-15.html
  python3 .claude/skills/math-equation-generator/scripts/generate_me.py --easy 5 --medium 5 --hard 5 --out ME-260902-15.html
  python3 .claude/skills/mixed-exercise-generator/scripts/generate_mixed.py --fs-easy 5 --ls-medium 5 --me-hard 5
  ```
  Omit any `--easy/--medium/--hard` (or, for the mixed generator,
  `--<type>-<tier>`) flag that would be 0. Only pass `--seed` when the user
  explicitly wants reproducible output. All four scripts refuse to silently
  overwrite an existing file at whatever `--out` path they're given (pass
  `--force` only once the user has confirmed they want that exact file
  replaced); when `--out` is omitted, they auto-suffix (`-2`, `-3`, ...)
  instead of colliding — the mixed generator's own `SKILL.md` recommends
  always omitting `--out` for exactly this reason (its filename only encodes
  date + total, so same-day collisions across different mixes are routine),
  while the three single-type skills still compute and pass an explicit
  `--out` per their own Step 2, with the auto-suffix behavior only as a
  fallback for a manually-run, `--out`-less invocation.
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
