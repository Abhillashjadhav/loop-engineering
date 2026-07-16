---
name: resume-integrity
description: Hard gate for the Dreamjob job-search agent's resume rules — the standing instructions Abhillash has had to repeat by hand. Use this skill BEFORE generating, rendering, editing, re-rendering, or sharing ANY resume (PDF or draft), BEFORE editing profile/master_profile.json or agent/resume_pipeline.py (especially TITLE_OVERRIDES), and BEFORE committing changes under outputs/*/resumes/. Also use whenever the user points out a resume mistake. The skill runs agent/check_resume_integrity.py as a pass/fail gate and lists the rules so they are enforced programmatically, not from memory. Do NOT skip because a change "looks small" — the title bug recurred exactly that way. Skip only for tasks with no resume/profile surface at all.
---

# Resume Integrity Gate

Abhillash has repeated the same resume corrections multiple times — most painfully **"don't add 'Product' to pre-Amazon titles."** It kept recurring because the rule lived only in chat, while a hardcoded `TITLE_OVERRIDES` table silently re-broke it on every render. This skill makes the rules a **programmatic gate** so they cannot be forgotten.

## The hard rule

**No resume ships until `agent/check_resume_integrity.py` exits 0.** Run it before generating, rendering, or sharing any resume:

```bash
python agent/check_resume_integrity.py                 # validates master_profile (post-render-patch)
python agent/check_resume_integrity.py --draft <file>  # validates an LLM draft JSON
```

If it fails, fix the **source** (`TITLE_OVERRIDES` in `agent/resume_pipeline.py`, the profile, or the draft) — never the symptom — then re-run until clean. This is non-negotiable.

## The rules it enforces (and why)

1. **Pre-Amazon titles are literal — never append "Product"/"Product Management".**
   Roles before Amazon (May 2019): PayTM=**AVP**, IndiaMart=**Vice President**, LeEco=**Senior Manager**, Flipkart=**Senior Manager**, Marico=**Area Sales Manager**, AgroTech=**Area Sales Manager**. Amazon and later keep their product titles. The fix lives at one chokepoint — `patch_profile_for_skill_md` strips any "Product" qualifier for `PRE_AMAZON_COMPANIES` — so a bad `TITLE_OVERRIDES` edit or LLM draft can't reintroduce it. The validator checks the **patched** titles (what the PDF actually shows).
2. **Exact-title hard rules:** PayTM = `AVP`, RADAR = `Product Advisor (Pro Bono)`.
3. **Never include forbidden companies** (e.g. `MJ Internet Pvt Ltd`) in any rendered content.
4. **Honesty (CLAUDE.md §2):** reframing into JD vocabulary is fine; inventing titles, metrics, dates, scope, headcount, or budget is not. Every number must trace to `master_profile.json`.

## When you change the rules

If Abhillash gives a new standing resume instruction, encode it in **both** places so it's enforced next time, not just remembered:
- the check in `agent/check_resume_integrity.py` (and a `constraints.*` entry in `profile/master_profile.json`), and
- this skill's rule list above.

## Working agreements (other repeat-mistakes from past sessions)

These aren't resume-specific but caused rework; keep them in mind on this repo:
- **Don't re-ask a decided question.** If the user already answered (e.g. "open the PR"), act — don't re-confirm.
- **Prefer the aggregator, not per-portal connectors.** For job coverage the user's leverage is the paid LinkedIn/Indeed actors pulling everything; enumerating per-company ATS sites is tech debt. Confirm the strategic approach before building a new source.
- **When "completeness" is the goal, verify the actual ceiling** — per-query `limit`, pagination depth, budget caps — not just that the fetch ran without error. A capped sweep looks successful while silently under-sampling.
