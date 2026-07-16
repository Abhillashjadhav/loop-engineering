# Live audit status: BLOCKED on access — no conclusions invented

> **Update 2026-07-16 (attempt executed):** a full live attempt was made per
> operator instruction — every access channel (REST user + repo endpoints,
> HTML, tarball, clone, add_repo, general web egress) is blocked in this
> environment except `raw.githubusercontent.com` file content and web search.
> Identity linkage for both subjects WAS verified and recorded, and
> `examples/subjects.yaml` now carries the verified attributes. The complete
> command-by-command access matrix, the exact `--live` blocking report, and
> the unblock options live in `audits/2026-07-16-live-audit/ACCESS-BLOCKED.md`
> and `audits/2026-07-16-live-audit/identity-evidence.md`. Repository
> analysis remains not executed; both subjects remain INSUFFICIENT_EVIDENCE.

**Subjects:** Aakash Gupta (candidate login `aakashg`), Shubham Saboo
(candidate login `Shubhamsaboo`) — spec §10.

**Status:** the live audit has **not** been executed. Per spec §16 and Hard
Rule "honesty over helpfulness", the working system ships with this explicit
gap report instead of invented results. Nothing in this repository states any
finding, score, classification, or verdict about either subject.

## Why it is blocked

GitHub access in the build environment is scoped to
`Abhillashjadhav/loop-engineering` only. Reading any other repository —
including the subjects' public repositories, via any tool — is outside the
session's authorized access. This is the circuit-breaker condition
"required public source inaccessible" (spec §8), reported here rather than
silently skipped.

## Exactly what evidence is missing

Per subject, the audit requires (and currently has none of):

1. **Identity corroboration** — the candidate profile snapshot plus at least
   two independent public attributes linking the person to the login (e.g.
   their own site/newsletter/X/LinkedIn linking to the GitHub account).
   `examples/subjects.yaml` deliberately ships with only `name` +
   `bio_keywords` placeholders; a URL alone proves nothing, and analysis
   blocks until two attributes corroborate.
2. **Complete repository inventory** — every page of the subject's public
   repository listing (originals, forks, archived, mirrors, empty),
   with retrieval timestamps.
3. **Per-repository inspection signals** — for each authored repository, the
   observable signals the rubric consumes (README claims vs code backing,
   template similarity, tests/CI, commit-day distribution, runnable setup,
   etc.), each backed by raw snapshots (source files, commit logs, file
   listings) preserved under `evidence/` with URLs, retrieval dates, and
   content hashes.
4. **Counter-evidence review** for any repository that would otherwise be
   classified shallow/templated.

## How to unblock (any one of these)

- **Run it yourself** from any machine with normal GitHub access:
  `pip install -e . && loop-engineering audit-github --subjects examples/subjects.yaml --live`
  (after filling the second expected attribute per subject in
  `examples/subjects.yaml`), or pre-fetch snapshots and pass `--fixtures`.
- **Claude Code session with public GitHub/web access permitted:** invoke
  `/loop-engineer use-case github-authority-audit` — the skill fetches public
  snapshots into the FixtureDataSource layout and runs the audit offline
  against them.
- **This environment:** grant the session access to the subjects' public
  repositories (repo scoping is controlled by the workspace's GitHub
  integration settings), then re-run.

When unblocked, the run will produce the full Accuracy Evidence Pack under
`outputs/github-authority-audit-live/`, including the six-run stability
comparison and the claim-evidence matrix. Until then, the only honest answer
for both subjects is: **INSUFFICIENT_EVIDENCE — not analysed**.
