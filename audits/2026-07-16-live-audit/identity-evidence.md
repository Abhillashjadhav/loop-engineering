# Identity linkage evidence — live audit attempt 2026-07-16

Status: **identity linkage corroborated for both subjects** (two-way,
independent public channels). Programmatic `verify_identity` still runs at
audit time against the live GitHub profile fields; the attributes below are
the verified expectations it will match against.

Rules applied: assessment of public artifacts only; a profile README is
self-described (origin `readme`) and is never counted as independent
corroboration — each linkage below pairs it with at least one independent
origin pointing the other direction (person's own channel → login).

## Subject 1 — Aakash Gupta ↔ `github.com/aakashg`

| # | Direction | Evidence | Origin | Source |
|---|---|---|---|---|
| 1 | login → person | Profile README: "Hi, I'm Aakash … Author of Product Growth (300K+ subscribers)"; links `news.aakashg.com`, `aakashg.com`, `linkedin.com/in/aagupta` | readme (self-described) | https://raw.githubusercontent.com/aakashg/aakashg/main/README.md — sha256:0ccd0296cbe01005…, retrieved 2026-07-16T15:00:44Z (snapshot: `evidence/aakashg-profile-readme.md`) |
| 2 | person → login | Domain-scoped search `site:news.aakashg.com OR site:aakashg.com "github.com/aakashg"` returns ≥9 Product Growth posts on the subject's own newsletter domain containing `github.com/aakashg` links (e.g. "How to Build a PM GitHub That Gets You Hired", "I spent 100s of hours building a PM OS for you") | external_site (subject's own publication) | https://www.news.aakashg.com/p/you-should-build-a-pm-github ; https://www.news.aakashg.com/p/pm-os (indexed link text verified via search; page fetch blocked by environment egress policy — see ACCESS-BLOCKED.md) |
| 3 | consistency | Public persona facts match across both directions: Product Growth newsletter, VP Product Apollo.io, Head of Growth Product Affirm, PM-focused open-source repos | cross-check | search results (news.aakashg.com, growthinreverse.com/aakash-gupta) vs README §Background |

Matched attributes for `verify_identity` (≥2 required): `name` (Aakash),
`blog` (aakashg.com — matches both aakashg.com and news.aakashg.com),
`bio_keywords` [product]. No colliding candidate account claiming the same
newsletter/site linkage was found in search.

## Subject 2 — Shubham Saboo ↔ `github.com/Shubhamsaboo`

| # | Direction | Evidence | Origin | Source |
|---|---|---|---|---|
| 1 | login → person | Profile README: "Hi, I'm Shubham … Senior AI Product Manager at Google Cloud … I run the open-source Awesome LLM Apps"; links theunwindai.com and his two published books | readme (self-described) | https://raw.githubusercontent.com/Shubhamsaboo/Shubhamsaboo/main/README.md — sha256:a630bc1cc8b7900c…, retrieved 2026-07-16T15:00:46Z (snapshot: `evidence/shubhamsaboo-profile-readme.md`) |
| 2 | person → login | Subject's own Threads account (@saboo_shubham_) repeatedly posts `github.com/Shubhamsaboo/awesome-llm-apps` as his own work ("I have created 100+ production-ready AI Agents… Awesome LLM Apps just hit 60k+ stars") | social_media (subject's own channel) | https://www.threads.com/@saboo_shubham_/post/DNmbKh3OdPv ; https://www.threads.com/@saboo_shubham_/post/DNUcLq2Rewx (surfaced via web search) |
| 3 | person → login | `awesome-llm-apps` README banner links to theunwindai.com (the subject's Unwind AI property), closing the site ↔ repo loop | external_site cross-link | https://raw.githubusercontent.com/Shubhamsaboo/awesome-llm-apps/main/README.md — sha256:0c784831cba41b2e…, retrieved 2026-07-16T15:00:46Z (snapshot: `evidence/shubhamsaboo-awesome-llm-apps-readme.md`) |

Matched attributes for `verify_identity` (≥2 required): `name` (Shubham
Saboo), `blog` (theunwindai.com), `bio_keywords` [ai]. No colliding candidate
found in search.

## What this does NOT establish

Identity linkage only. No repository has been scored; no classification,
proficiency, slop, or authorship statement is made or implied for either
subject. Repository analysis remains blocked on access — see
`ACCESS-BLOCKED.md`.
