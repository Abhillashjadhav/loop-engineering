---
name: resume-craft
description: The complete quality standard for every resume this agent produces — all known failure modes (mined from the full session history at token level) and what "upload-ready, no rechecking needed" means, plus the pre-share checklist. Use this skill BEFORE generating, rendering, re-rendering, reviewing, or sharing ANY resume, and whenever the user points out a resume problem. It covers JD-domain tailoring (project selection, per-domain bullet ordering, track-record swap), job relevancy, the payments/fintech variant, sections (one of Core Skills vs Core Competencies — we keep Core Skills + Executive Summary), professional formatting (no markup artifacts, 2 pages, full contact header with LinkedIn + GitHub), load-bearing bolding, ATS keyword integrity, and the "zero warnings / 80+ high confidence / perfect fit" bar. The hard honesty/title GATE lives in the separate `resume-integrity` skill (run its checker too). The user cannot easily recheck resumes, so a resume ships only when it clears every item here. Skip only for tasks with no resume surface.
---

# Resume Craft — every failure mode, accounted for

The user's hardest, least-recoverable review is the resume itself. A resume
ships **only** when it is good enough to upload without rechecking. The list
below is the full set of resume failure modes we have actually hit across
sessions, mined from the transcript at token level — **34 modes in 8 groups.**
Each is a thing that went wrong and the rule that prevents it. Don't ship a
resume until every applicable one is satisfied.

The honesty/title hard gate is the separate **`resume-integrity`** skill — run
`python agent/check_resume_integrity.py` (must exit 0) **in addition** to this.

---

## A. Titles, identity & honesty
1. **Pre-Amazon titles are literal — never append "Product"/"Product Management."**
   PayTM=**AVP**, IndiaMart=**Vice President**, LeEco=**Senior Manager**,
   Flipkart=**Senior Manager**, Marico=**Area Sales Manager**, AgroTech=**Area
   Sales Manager**. (Most-repeated correction in the whole project.)
2. **Exact titles:** PayTM = `AVP`; RADAR by AIMleap = `Product Advisor (Pro Bono)`.
3. **`NEVER_INCLUDE_COMPANIES` must contain `MJ Internet Pvt Ltd`** — never rendered.
4. **Years are consistent and correct:** headline / `experience_years_total` /
   executive-summary opener all say **"15+ years"** total (not 16+), framed as
   "11+ years of at-scale product management experience including enterprise
   SaaS platform products" — never "11+ years driving enterprise SaaS".
5. **No fabrication; no over-claiming.** Every metric/scope/date traces to
   `master_profile.json`. E.g. say "$300M business impact", not "$300M
   annualised impact" unless the profile says annualised. `output_audit.py`
   quarantines fabricated bullets — a quarantined resume must not ship.
6. **Load-bearing bold only.** Only bold a keyword that has real backing in
   `ADJACENCY_EVIDENCE` — bolding a term the profile can't support is a mild
   fabrication (recruiters read bold as a load-bearing claim).

## B. Sections & structure
7. **Pick ONE of Core Skills vs Core Competencies — keep Core Skills, DROP Core
   Competencies.** Both used to render (deterministic *and* LLM-draft paths);
   the standard is **Core Skills + Executive Summary only**. Do not reintroduce
   a "Core Competencies" section.
8. **Executive Summary present and domain-tailored** (see group D) — generic
   summary is a defect.
9. **Section order:** header → Core Skills → divider → Executive Summary →
   Professional Experience → (Selected Project, when relevant). No Core Competencies.

## C. Projects (must be present, and the RIGHT one)
10. **Projects must be mentioned.** Earlier resumes omitted projects entirely —
    that's a defect. Source: `selected_projects` in `master_profile.json`
    (currently: AI Career Counseling Agent, RAG Eval Harness, Indian Stocks
    Deep-Dive & Trading Agents).
11. **Pick the project that matches the JD domain** (not a fixed one):
    knowledge_ai → **RAG Eval Harness**; agentic_ai → **AI Career Counseling
    Agent**; b2b_enterprise → **Indian Stocks Deep-Dive & Trading Agents**.
12. **Show the project only when the JD aligns** (AI / agentic / GenAI / platform
    / PM). Don't bolt an AI project onto an unrelated role.

## D. JD-domain tailoring engine (the resume is built FROM the JD)
13. **Read the actual JD body first.** If there's no real JD body, say so
    (lower confidence) — never fake tailoring. Use the full ~1500-char excerpt
    (group F.27), not the truncated 90-char one.
14. **Classify the JD into a domain** via `classify_jd_domain()` — one of
    knowledge_ai, genai_platform, agentic_ai, b2b_enterprise, consumer_ai,
    developer_platform. This drives project, bullet order, and track record.
15. **Per-domain Wayfair bullet ordering** (`_WAYFAIR_BULLET_ORDER`, 4-bullet
    Wayfair block): lead with the most JD-relevant bullet — e.g. knowledge_ai
    leads with the RAG/knowledge bullet, genai_platform leads with platform
    overview, agentic_ai leads with the eval/agentic bullet.
16. **Per-domain executive-summary track record** (`_TRACK_RECORD_BY_DOMAIN`):
    swap the generic track-record line for the domain-relevant one.
17. **IC vs people-manager framing** via `detect_role_mode()` — for IC roles,
    `scrub_cross_company_terms` trims org-leadership phrasing; for manager roles
    lead with scope/leadership. Match the seniority the JD implies.
18. **Mirror the JD's vocabulary** via `jd_keywords_for()` — bold the keywords
    the JD actually uses (subject to load-bearing rule A.6).

## E. Length & formatting (professional, no artifacts)
19. **Exactly 2 pages.** Page-2 body ~3,400–4,200 chars. Not 1, not 3.
20. **Per-company bullet budgets keep it to 2 pages:** Marico/AgroTech/LeEco →
    1 bullet; Flipkart/PayTM/IndiaMart/RADAR → 2 bullets; Wayfair/Amazon/CTL get
    the fuller treatment. Trim to fit without dropping relevance.
21. **Marico + AgroTech are ONE consolidated entry** ("Area Sales Manager, FMCG").
22. **`KeepTogether` per role** — a role block must not split across a page; the
    Amazon header must not trail at the bottom of page 1.
23. **Bolding via span-based `render_bullet()` — never the old two-pass.** This
    structurally prevents the artifacts that actually shipped:
    no leaked markup (`<b>`), no compound-phrase split ("Customer Data —
    Platform"), no em-dash injected mid-phrase ("Rs. — 78", "microservices —
    platform"), no ransom-note over-bolding (< 45% of glyphs bold).
24. **No duplicate adjacent words** ("Improved improved") and no `a→an` scrubber
    misfire ("an unified"). `_check_formatting()` hard-FAILs these — but write
    clean first.
25. **A4, margins 0.58" L/R / 0.48" T/B, embedded fonts; ~48–50 KB** (8–12 KB =
    fonts didn't embed → regenerate).
26. **Complete contact header:** phone, email, **LinkedIn URL, GitHub URL** (full
    strings: `linkedin.com/in/abhillashjadhav`, `github.com/Abhillashjadhav`).
    A resume missing these does not ship.

## F. ATS & keyword integrity
27. **Use the full JD, not the truncated one.** `_scored_candidates.json`
    truncates `description_excerpt` to ~90 chars; pull the full ~1500-char text
    from `_raw_candidates.jsonl` / URL enrichment so tailoring sees real asks.
28. **Isolate the requirements section.** LinkedIn excerpts often open with 80%+
    company/culture boilerplate; `_extract_requirements_section()` isolates the
    real requirements so scoring/keywords aren't polluted.
29. **Don't contaminate the keyword set with meta-commentary.** `why_fit` bullets
    contain agent phrases ("maps perfectly", "scope sweet spot") that are NOT in
    any resume — exclude them from JD keyword extraction or ATS coverage reads
    falsely low.
30. **`scrub_fluff`:** strip hype adjectives; "world-class" stays only when
    quantified, never as a self-applied compliment.
31. **ATS singular/plural stemming** (models↔model, agents↔agent) — avoids false
    "missing keyword" gaps on a trailing `s`.
32. **Reviewer matches per-PDF by role-slug** — multi-role companies (e.g. FICO)
    must be scored against *their own* JD, not another role's.
33. **ATS targets:** parseability ≥ 85, keyword coverage ≥ 70. Adyen once landed
    at 55–56% → WARN. Regenerate (max 2 retries), authentically adding JD
    keywords real experience supports.

## G. Payments / fintech variant
34. **`is_payments_role()` gate.** Apply payments-forward framing **only** to
    genuine payments/fintech roles: Amazon "Promotions and Payments (merchant)
    Platform", PayTM "B2B business and Payment Product", CTL "eCommerce (Payments
    and Orders)". Payments/transaction language must show prominently in the CTL
    and Amazon sections for these roles — and must NOT bleed into unrelated roles.

## H. The bar (ship/no-ship)
- Fit is **real and ≥80** (original or genuinely bumped) with high confidence.
- `resume_reviewer.review_resume()` → **PASS, 0 FAIL, 0 WARN**, formatting issues
  empty. A WARN is a real gap: fix by authentic reframing, or it isn't an 80.
- All of A–G satisfied for the role's domain.

---

## Pre-share checklist (run before committing/sharing any resume)
1. `python agent/check_resume_integrity.py` → **exit 0** (titles / exact-titles /
   forbidden strings) — the `resume-integrity` gate.
2. JD body read; domain classified; **right project** shown; Wayfair bullets and
   exec-summary track record ordered for that domain.
3. Payments framing applied **iff** `is_payments_role()` is true.
4. Sections = Core Skills + Executive Summary (NO Core Competencies); projects present.
5. `agent/resume_reviewer.py` → **PASS, 0 FAIL, 0 WARN**; no leaked markup,
   duplicates, or over-bolding.
6. `agent/ats_report.py` → parseability ≥ 85, coverage ≥ 70 (keyword set not
   contaminated by `why_fit` meta-text).
7. PDF is **2 pages**, ~48–50 KB, header has email/phone/location + LinkedIn +
   GitHub URLs; years say 15+; bolded terms are load-bearing.
8. PDF committed under `outputs/{date}/resumes/` (date-stamped filename).

If any item fails, fix the **source** (profile / JD parse / draft / renderer)
and regenerate — never hand-patch the PDF. A resume that can't clear all of
A–H isn't ready, and we say so rather than shipping a flawed one.

## Maintenance
When the user flags a new resume problem, add it as a numbered failure mode here
and, if mechanically checkable, wire it into `check_resume_integrity.py` or
`resume_reviewer._check_formatting()` — so the next resume can't repeat it.
