# Identity linkage evidence — cohort audit 2026-07-17

Goal: `github-authority-audit-cohort-2026-07`. Rules applied: identity is
never assumed from the operator's instruction or a URL; a GitHub profile /
repo README is self-described (origin `readme`) and never counts as
independent corroboration on its own — each confirmed linkage pairs it with
at least one channel owned by the person pointing the other direction
(person → login). Raw profile-README snapshots with sha256 hashes are in
`evidence/` (retrieved 2026-07-17T03:44:26Z via raw.githubusercontent.com,
the only direct-content channel available in this environment; external
sites are corroborated via indexed web search because direct fetch is
blocked by egress policy — same constraint as the 2026-07-16 audit).

## Confirmed two-way linkages

| Subject | Login | login → person (self-described) | person → login (independent) |
|---|---|---|---|
| Paweł Huryn | `phuryn` | Profile README "Hi, I'm Paweł Huryn … Creator of The Product Compass Newsletter", links productcompass.pm (`evidence/phuryn-profile-readme.md`, sha256:b6cc0f597f62f00e…) | His own newsletter domain productcompass.pm publishes posts presenting github.com/phuryn/pm-skills and github.com/phuryn/pm-brain as his work (e.g. productcompass.pm/p/pm-skills-2-red-team-ship, /p/pm-brain-os, /p/pm-skills-marketplace-claude) |
| Hamel Husain | `hamelsmu` | Profile README "Hi, I'm Hamel … Parlance Labs … I write at hamel.dev" (`evidence/hamelsmu-profile-readme.md`, sha256:e13d660180c312b6…) | His own blog hamel.dev links github.com/hamelsmu repositories as his (hamel.dev/blog/posts/evals-skills/ → github.com/hamelsmu/evals-skills; hamel.dev/notes/linux/cookbook.html → github.com/hamelsmu/…) |
| Eugene Yan | `eugeneyan` | Profile README "Hi, I'm Eugene Yan … Principal Applied Scientist at Amazon", links eugeneyan.com (`evidence/eugeneyan-profile-readme.md`, sha256:e932f254d56b6ceb…) | His own site eugeneyan.com links github.com/eugeneyan repos as his projects (eugeneyan.com/writing/obsidian-copilot/, /writing/testing-ml/, /writing/news-agents/, /prototyping/) |
| Shreya Shankar | `shreyashankar` | Profile README "incoming Assistant Professor at CMU … PhD from UC Berkeley, built DocETL … essays at sh-reya.com, Twitter @sh_reya" (`evidence/shreyashankar-profile-readme.md`, sha256:68f7a915af1657d2…) | Her own site's CV (sh-reya.com/SS_CV.pdf, "Shreya Shankar shreyashankar@berkeley.edu | sh-reya.com") and her own X account @sh_reya (which sh-reya.com links) promote her GitHub work; GitHub profile fields (name, blog sh-reya.com, twitter sh_reya, Berkeley CA) match her site |
| Chip Huyen | `chiphuyen` | Profile README "Hi, I'm Chip … author of AI Engineering and Designing Machine Learning Systems", links huyenchip.com properties (`evidence/chiphuyen-profile-readme.md`, sha256:c3ccb893f056979a…) | Her own site huyenchip.com links github.com/chiphuyen repositories as hers (huyenchip.com/ml-interviews-book/…/chapter-6 → github.com/chiphuyen/coding-exercises; the site's open-sourced books correspond to chiphuyen repos named in the README) |
| Aakash Gupta | `aakashg` | Reused from completed audit (2026-07-16), unchanged | Reused: news.aakashg.com posts linking github.com/aakashg (see audits/2026-07-16-live-audit/identity-evidence.md) |
| Shubham Saboo | `Shubhamsaboo` | Reused from completed audit (2026-07-16), unchanged | Reused: @saboo_shubham_ Threads posts + theunwindai.com cross-link (see audits/2026-07-16-live-audit/identity-evidence.md) |

## Abhillash Jadhav ↔ `Abhillashjadhav` — PARTIALLY VERIFIED (second attribute pending)

- login → person: PUBLIC repo READMEs self-describe the author —
  `PM-agent-OS` footer: "*Built by [Abhillash Jadhav](github.com/Abhillashjadhav) — GenAI PM.
  Evals, context engineering, agentic reliability.*"
  (`evidence/PM-agent-OS-readme.md`, sha256:0b6238ed4b1042f7…, retrieved
  2026-07-17T03:47:48Z; also `pm-evals-readme.md` sha256:d31c6ecd385460c3…,
  `rag-eval-harness-readme.md` sha256:4e5b019318137aaf…).
- The account has **no profile README** (raw.githubusercontent.com
  Abhillashjadhav/Abhillashjadhav → 404 on main and master).
- person → login: **no independent public channel found linking to
  github.com/Abhillashjadhav.** Searched 2026-07-17: `"github.com/Abhillashjadhav"`
  (zero true hits) and `"Abhillash" linkedin.com "github" …` (zero). A public
  LinkedIn profile "Abhillash Jadhav" exists
  (in.linkedin.com/in/abhillash-jadhav-350525b, Wayfair, product posts) with
  the same distinctive spelling, but no indexed content of that profile links
  the GitHub account, and LinkedIn cannot be fetched from this environment.
- Engine expectation recorded in `examples/subjects.cohort.yaml`:
  `name: Abhillash Jadhav` + `linkedin: abhillash-jadhav`. The identity gate
  will pass only if the harvested GitHub profile carries both (name field and
  a linkedin URL containing the slug). **Unblock options (either):**
  1. add the GitHub URL to a channel he publicly controls (LinkedIn contact
     info / a post / a personal site) — creates the person → login origin; or
  2. set the GitHub profile's name and a public link binding the two (still
     self-described — Loop 3 will then hold the identity claim at one
     independent origin and say so honestly).

## Aishwarya Srinivasan — IDENTITY_UNRESOLVED_FOR_GITHUB_AUDIT

No GitHub account is linkable to her by two independent public attributes.
She is therefore **not a subject in `subjects.cohort.yaml`**, and per the
goal contract no technical inference of any kind is drawn from the absence
of a verified account.

Recorded search coverage (all 2026-07-17, indexed web search):

| # | Query / probe | Result |
|---|---|---|
| 1 | `"Aishwarya Srinivasan" AI "github.com" profile OR repository` | ≥5 same-named or near-named candidate accounts (`eaishwa` "Aishwarya V Srinivasan" Columbia, `AiswaryaSrinivas`, `ash-srini` Toronto, `aish-blr`, `aishusreeni`, `ayshwaryasrinivasan.github.io`) — a collision-rich field; none self-linked by her |
| 2 | `"Aishwarya Srinivasan" "AI advisor" OR "Fireworks" OR … "github"` | Her own properties surfaced (aishwarya.ai, Substack "AI with Aish", linkedin.com/in/aishwarya-srinivasan, YouTube) — none of the indexed results show a personal GitHub link |
| 3 | `site:aishwarya.ai OR site:aishwaryasrinivasan.substack.com "github.com"` | Only two Substack posts referencing **other people's** repositories (github.com/san-s1819/GenAI-news-curator, github.com/pytorch/pytorch) — no personal account |
| 4 | Candidate cross-check | `eaishwa` (Columbia) is superficially compatible with her Columbia degree but carries a different name form ("Aishwarya V Srinivasan"), no link to aishwarya.ai/Substack/LinkedIn, and multiple rival candidates exist — assigning it would violate the two-attribute rule and the collision rule |

Classification: **IDENTITY_UNRESOLVED_FOR_GITHUB_AUDIT** (as the goal
contract requires). Reversal condition: any channel she publicly controls
(aishwarya.ai, the Substack, her LinkedIn, a conference bio she authored)
naming a specific GitHub account, plus one further matching public attribute.

## Environment/visibility findings material to the audit

- `Abhillashjadhav/PM-agent-OS`, `pm-evals`, `rag-eval-harness` are **public**
  (READMEs fetch unauthenticated, hashes above).
- `Abhillashjadhav/loop-engineering` and `Abhillashjadhav/production-engineering-os`
  are **not publicly visible** (unauthenticated README fetch → 404 on
  main/master; loop-engineering is known to have a README on main, so the 404
  means auth-gated). Under the locked exclusions (public artifacts only)
  they are invisible to this audit and cannot be counted for or against any
  subject — including in the product-level flagship comparison — unless made
  public before the harvest.

## Post-harvest identity-gate results (2026-07-17, snapshots @ df5145b)

All eight subjects pass `verify_identity` against the harvested profiles:
pawel-huryn (name+blog, 80), aakash-gupta (name+blog+bio, 100),
shubham-saboo (name+blog+bio, 100), hamel-husain (name+blog, 80),
eugene-yan (name+blog, 80), shreya-shankar (name+blog+twitter, 100),
chip-huyen (name+blog, 80), abhillash-jadhav (name+bio_keywords, 80 — see
below).

**abhillash-jadhav amendment:** the harvested profile has an empty blog
field and no linkedin/twitter, so the originally-expected `linkedin`
attribute could not match. Expected attributes were amended to
`name` + `bio_keywords: [genai]`, both grounded in already-hashed public
artifacts (PM-agent-OS README "Built by Abhillash Jadhav — GenAI PM",
sha256:0b6238ed4b1042f7…; harvested profile bio "GenAI Product Manager
building AI agents…"). Candidate field: exactly one account, zero
collisions; a fresh indexed search for "github.com/Abhillashjadhav"
(2026-07-17) still returns no independent person→login channel. CAVEAT
carried into the final report: both matched attributes are self-described,
so the Loop 3 identity claim for this subject rests on one independent
origin and is reported as such. Unblock unchanged: any publicly-controlled
channel (LinkedIn, personal site) linking to github.com/Abhillashjadhav.
