# xivLab Loop Status

**Last updated**: 2026-05-05T18:20:00+08:00
**Last completed Task**: T14 (Email Rendering + Send Digest)
**Next Task**: T15 (send_digests Cron Job)
**Test suite**: green (118 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- `templates/emails/digest.html` and `templates/emails/digest.txt` — Jinja templates for the daily digest email. HTML uses inline styles only (mailbox-friendly, no external CSS). Both render task name + today's ISO date in the header, paginate through papers showing title (linked to `arxiv.org/abs/<id>`), top-3 authors with " et al." truncation, primary_category, abstract truncated at 600 chars with `…`, and a PDF link (uses `paper.pdf_url` if set, else `arxiv.org/pdf/<id>` fallback). Footer has a manage-subscription link to `<app_base_url>/dashboard/tasks/<task_id>`.
- `app/services/digest.render_digest(task, papers, unsubscribe_url) -> tuple[html, text]` — pure renderer with Jinja autoescape on for `.html` (so a paper title containing `<script>` becomes `&lt;script&gt;`).
- `app/services/digest.deliver_email(s, user, task, papers)` — sends one email via `send_email` (mock backend in tests/dev, Resend in prod) and writes one `Delivery` row per paper with `channel='email'`. Empty `papers` short-circuits — no send, no rows. Subject is `🧪 <task.name> · <N> papers · <today>`.
- 14 tests in `tests/unit/test_digest_rendering.py`: 11 rendering (HTML+text return, title/abstract presence in both, `et al.` truncation above 3 authors and absent at ≤3, abs+pdf links, custom pdf_url override, today/count/task-name in body, unsubscribe URL embedded, abstract truncation `…`, `<script>` autoescape, empty-papers no-crash); 3 delivery (one mock send + N Delivery rows, no-papers no-op, the (task_id,paper_id,channel) unique-constraint actually fires on duplicate paper).

## Plan deviations / fixes

- The plan loaded Jinja with bare `Environment(loader=FileSystemLoader(...))` — autoescape was OFF, meaning a paper title containing `<script>` would be injected verbatim into the email HTML. Fixed: `select_autoescape(["html"])` so `.html` autoescapes and `.txt` stays raw. Added an explicit test for the escape behavior.
- The plan inlined `from app.config import get_settings` inside `deliver_email` to dodge a circular-import worry. There's no actual cycle (`app.config` doesn't import from `app.services`), so I moved it to the top.
- The plan's single test asserted "title appears in HTML" only. Wrote 11 rendering tests covering each branch of the templates (author truncation both directions, abstract truncation, custom pdf_url override, autoescape, empty list) so future template edits get caught by the test suite.
- The plan's `deliver_email` signature was `user` (untyped). Typed it as `User` so pyright catches argument-shape errors and call-sites get the right autocomplete.
- Subject line: kept the plan's `🧪 <name> · <N> papers · <date>` format. The test asserts task name + paper count appear; the exact format is not load-bearing.

## Open issues / TODOs

- `socksio==1.0.0` transitive dep — fine.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 443 warnings (up from 424; rendering tests instantiate Paper rows). Sweep around T15.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- Real arXiv API + real OpenAI embeddings still never hit by tests; the send-digest cron (T15) wires `select_papers_for_task` + `deliver_email` together but still mocks externals.
- The `xivLab · manage subscription` footer text isn't translatable. Fine for MVP — i18n is post-1.0.
- Email `From:` header currently hardcoded to `noreply@xivlab.local` via `settings.resend_from_email`. Real domain swap happens at deploy.

## What's next (T15 high-level reminder)

T15 is the send_digests cron job:
- `app/jobs/send_digests.py` — iterates enabled tasks whose owner has `email_verified=True`, calls `select_papers_for_task` + `deliver_email`. Wraps the full run in `cron_run("send_digests")` (T12's helper) so success/failure + per-run metrics (`tasks_processed`, `emails_sent`, `papers_delivered`) land in `cron_runs.job_metadata`.
- Per-task failures should NOT abort the whole job — log the error, mark just that task's metrics, continue. The cron-runs row stays `success` if at least one task delivered. (Or maybe `success_with_partial_failures` — TBD by the plan text.)
- `tests/integration/test_send_digests_job.py` — autouse `_reset_db`, seed two users with two tasks each, mock arxiv to populate papers, run the job, assert MockEmailBackend.sent has the right count and the per-task Delivery rows exist.
- T15 closes the loop: T11 (embed) → T12 (fetch+vectors) → T13 (filter) → T14 (render+deliver) → T15 (schedule). After T15, the daily digest pipeline is end-to-end functional minus the APScheduler wiring (T22).
