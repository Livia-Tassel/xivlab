# xivLab `/loop` Runner Manual

> **Read this first** if you've been triggered as part of a `/loop` autonomous development session.
> 
> **You are**: A coding agent dispatched (perhaps repeatedly) to advance the xivLab MVP towards a runnable state. You may have NO memory of previous iterations. The state is in the filesystem and git history.

---

## 0. Mental Model

You're an iteration in a loop. Each iteration:

1. **Orient** — figure out where the project is.
2. **Pick** — choose the next Task from the implementation plan.
3. **Execute** — perform that Task end-to-end (code + tests + commit).
4. **Verify** — run the universal acceptance commands.
5. **Report** — write a short status note for the next iteration.

You do **one** Task per iteration. Don't try to do two even if you have time. Stopping cleanly at a known-good state is more valuable than rushing.

---

## 1. Pre-flight (always)

Before doing anything else, read these files in order:

```
docs/superpowers/specs/2026-05-04-xivlab-design.md          # the design (what)
docs/superpowers/plans/2026-05-04-xivlab-implementation.md   # the plan (sequence)
docs/DEVELOPMENT_GUIDE.md                                    # the conventions (how)
docs/LOOP_RUNNER.md                                          # this file
docs/LOOP_STATUS.md                                          # current state (auto-written by loop)
```

If `docs/LOOP_STATUS.md` doesn't exist, you're the first iteration. **Create it** at the end of your run (Section 5).

---

## 2. Orient: Discover Current State

### 2.1 Read git log

```bash
git log --oneline -30
```

Each Task's final commit ends with the Task's purpose, e.g. `feat: auth: add register endpoint with bcrypt password hashing` corresponds to Task 03.

### 2.2 Read the plan's checkboxes

Open `docs/superpowers/plans/2026-05-04-xivlab-implementation.md` and find the first Task whose steps are not all checked off (`- [ ]`).

If LOOP_STATUS.md exists, it points to the current task. **Trust it but verify** — if git log doesn't match its claim, prefer git history.

### 2.3 Run the test suite

```bash
uv run pytest -q
```

If it's failing on `main`, **STOP** and report (Section 6.2). Don't start a new Task on a broken base.

---

## 3. Pick: The Next Task

The next Task is the lowest-numbered Task whose checkboxes are not yet all complete in the plan document. If the previous Task's last commit says "Task NN done" or its commit message matches the Task description, that Task is done.

**Do not skip Tasks.** They have dependencies. If Task NN looks blocked or unclear, see Section 6.1 (handling blocks).

---

## 4. Execute One Task

### 4.1 Tight loop per step

Each Task in the plan has numbered Steps with checkboxes (`- [ ]`). Work through them **in order, one at a time**:

1. Read the Step.
2. Do exactly what it says — write the file, run the command, etc.
3. Mentally tick the box (you'll commit the actual checkbox tick at the end).

When the Step says "Run tests and verify they fail / pass", **actually run them and read the output**. Don't proceed if reality doesn't match expectation.

### 4.2 The TDD steps are not optional

Most Tasks are TDD-shaped: write failing test → run → implement → run → commit. Honor that. If you write the implementation first and the test passes immediately, you wrote a tautological test — go back and make it actually test the behavior.

### 4.3 If a Step's code snippet is incomplete

The plan sometimes says things like "(rest of CRUD pattern from earlier tasks)" or "(similar to Task 06)". This is intentional — you have judgment. Mirror the prior pattern, follow `DEVELOPMENT_GUIDE.md`, and produce the code.

### 4.4 If a Step is wrong

If you discover an error in the plan (e.g. a column type that won't migrate, an import that doesn't exist) — **fix it as part of your Task**. Update the plan in the same commit. Note the fix in your status report.

---

## 5. Verify + Tick + Commit + Update Status

### 5.1 Universal acceptance check

Before commit, run all four:

```bash
uv run pytest -q                         # all tests pass
uv run ruff check app/ tests/            # no lint errors
uv run ruff format --check app/ tests/   # formatted
uv run pyright app/                      # type-check clean
```

If any fail: fix, then re-run. **Never commit broken state.**

### 5.2 Tick the boxes in the plan

In `docs/superpowers/plans/2026-05-04-xivlab-implementation.md`, find the Steps you just completed and change `- [ ]` → `- [x]`. Stage this file as part of your commit.

### 5.3 Commit

Per `DEVELOPMENT_GUIDE.md` §7, commit format:

```
<type>: <component>: <what>

<optional body summarizing the Task>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Stage explicit files with `git add path/to/file`. Avoid `git add -A`.

### 5.4 Update `docs/LOOP_STATUS.md`

This file is the loop's "session state". Overwrite it with:

```markdown
# xivLab Loop Status

**Last updated**: <ISO timestamp>
**Last completed Task**: T<NN> (<short description>)
**Next Task**: T<NN+1> (<short description>)
**Test suite**: <green | red — describe failure>
**Last commit**: <git short hash + message>

## Notes for next iteration

- <anything the next iteration needs to know>
- <e.g. "I had to fix a typo in the migration; double-check Task 02 alembic file">
- <e.g. "Mock embedding now returns L2-normalized vectors; tests adjusted accordingly">

## Open issues / TODOs surfaced this iteration

- <if any>
```

Commit this update with the rest of your work — same commit, OR a follow-up `chore: update loop status` commit if your main commit is already created.

---

## 6. When to Stop / Escalate

### 6.1 Blocked on a Task

If you genuinely can't make a Task pass (e.g. an external dependency failing, a tool not installed, a fundamental ambiguity in the spec):

1. **Don't fake it**. Don't commit broken tests, don't commit "TODO" stubs that pretend to work.
2. **Document the block** in `docs/LOOP_STATUS.md` under "Open issues" with as much detail as you'd want from a coworker.
3. **Stop your iteration cleanly**. Don't move on to a later Task — they likely depend on the blocked one.
4. The next loop iteration (or the human) can pick up from your notes.

### 6.2 Test suite is red on `main` from the start

This means a previous iteration committed broken state (shouldn't happen, but…). **DO NOT** start a new Task. Instead:

1. Read recent commits to find what broke.
2. Either fix the breakage (single commit, type=`fix`) or revert the offending commit.
3. Update `LOOP_STATUS.md` to describe what happened.
4. Stop. Let the next iteration resume.

### 6.3 All Tasks done

When you complete Task 28 (the last):

1. Run a final full validation: `uv run pytest -q && uv run ruff check && uv run pyright`
2. Tag the release: `git tag -a v0.1.0 -m "MVP release"`
3. Update `LOOP_STATUS.md` with `**All tasks complete**. Project at v0.1.0.`
4. Stop.

### 6.4 Time budget

You're an iteration; you're not the marathon. If you've been working for >20 minutes on a single Step and not making progress, **stop and document the block** (Section 6.1). The next iteration may have a fresh angle.

---

## 7. Things You Are Allowed To Do

- Refactor for clarity if a file you're touching has grown unwieldy. Keep the refactor scope-minimal — don't tour the codebase.
- Fix typos / small bugs in earlier Tasks if you find them while working on a current Task. Note in commit body.
- Improve test coverage of an area you're already touching.
- Add helper utilities (e.g. test factories) when you find yourself duplicating patterns.
- **Push to `origin main` at the end of every iteration** so progress is durable. The remote is `git@github.com:Livia-Tassel/xivlab.git` (already configured).
- Choose your own development environment: write code locally then push, or SSH to Sacurajima and write directly there. Both work — pick what's faster.
- Decide deployment cadence: deploy after every Task, after each phase, or only at the end (T28). Just keep it tested.

## 8. Things You Are NOT Allowed To Do

- ❌ Skip Tasks or reorder them — the plan has dependencies
- ❌ Commit broken tests
- ❌ Commit `# TODO` stubs that pretend to be done
- ❌ Modify `docs/superpowers/specs/` (the spec is source of truth; if you spot a real issue, document in LOOP_STATUS)
- ❌ Run real external API calls in tests (always mocked)
- ❌ Force-push or rewrite history on `main`
- ❌ Delete data, drop tables, or run destructive `git` commands without strong reason + clear undo path
- ❌ Bump major dependency versions (Python, FastAPI, SQLAlchemy) without an explicit Task for it
- ❌ Change the deployment target (Sacurajima) or the memory budget (<500MB)
- ❌ Commit `.env` or any file containing real secrets

---

## 9. The First Iteration's Special Steps

If you're the FIRST iteration (no `docs/LOOP_STATUS.md`, no app code, just docs):

1. Confirm the only commits in `git log` are the docs commits + `chore: bootstrap` (none of the latter yet).
2. Begin Task 01 from the plan.
3. At the end, create `docs/LOOP_STATUS.md` with the format from §5.4.

---

## 10. The Last Iteration's Special Steps

If `docs/LOOP_STATUS.md` says "All tasks complete":

1. Don't pick a new Task.
2. Run the smoke test script: `uv run python scripts/check_health.py http://localhost:8001`
3. Print a short summary of what was built and any operational follow-ups (e.g. "User still needs to: register Resend, point DNS, run deploy.sh on Sacurajima").
4. Stop.

---

## 11. Communication Style

When the loop reports back to the user (the human watching), use this template:

```
✅ Iteration N — Task TXX done
Commit: <hash> "<commit message>"
Tests: <pass count>/<total>
Next: TYY <description>
Notes: <one-line summary if anything noteworthy>
```

If blocked:

```
⚠️ Iteration N — BLOCKED on Task TXX, Step Z
Reason: <one paragraph>
Last good commit: <hash>
See LOOP_STATUS.md for details.
```

Keep it terse. The user is reading 20 of these.

---

## 12. Sanity Checklist (review before every commit)

- [ ] Tests pass (`uv run pytest`)
- [ ] Lint clean (`uv run ruff check`)
- [ ] Format clean (`uv run ruff format --check`)
- [ ] Type-check clean (`uv run pyright app/`)
- [ ] No secrets in committed files (`grep -r "api_key\|password" app/ | grep -v test`)
- [ ] No `print()` left in app code (logs only)
- [ ] No `data/app.db`, `.env`, or other gitignored files staged
- [ ] Plan checkboxes ticked
- [ ] LOOP_STATUS updated
- [ ] Commit message follows convention

If all 9 are checked, commit. Otherwise, fix.
