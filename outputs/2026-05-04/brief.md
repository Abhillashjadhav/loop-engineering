# Job brief — 2026-05-04 — 2 fits, 2 bumped fits, 2 near-misses [partial-culture] [partial-drive]

## Drift / error notes

- `[partial-culture]` — Indeed `get_company_data` MCP not invoked for the 4 fits this run; brief shows "culture data not available" honestly rather than fabricating ratings (Hard Rule 8).
- `[partial-drive]` — 4 resume PDFs hosted on GitHub raw URLs (linked below); will also be uploaded to Drive folder per the standard flow. PDFs are compact (Helvetica core font, no embedding) so they fit inline base64 size limits — same content, smaller file (~9 KB vs 64–84 KB). ATS compatible.
- LinkedIn connections CSV not yet in repo (`data/linkedin_connections.csv`) — every referral row honestly shows "no referral path identified". Once a connections export is committed, the next run picks it up.

## Funnel

| Stage | Count |
|---|---|
| Raw rows ingested (LinkedIn-jobs-scraper Apify, 5 datasets) | 276 |
| After URL dedupe | 209 |
| After in-batch dedupe | 201 |
| After title regex `(Director\|Principal\|Group\|Head\|VP).*Product` filter | 44 (after disqualifying drops) |
| After 60-day no-resurface dedup vs May 3 (`outputs/seen_index.jsonl`) | 16 (23 May 3 repeats dropped) |
| After (company, title) dedup vs May 3 surfaced cohort | 15 |
| Scored | 15 (6 retained for review, 9 silent-dropped) |
| **FITS (≥80 original)** | **2** |
| **BUMPED FITS (60–79 → ≥80)** | **2** |
| Near-misses (60–79) | 2 |
| Silent drops (<60 or wrong-track) | 9 |

---

## FITS

### 1. FICO — Director/Principal Platform Product Manager - Observability (90)
- **Apply:** [https://in.linkedin.com/jobs/view/director-principal-platform-product-manager-observability-at-fico-4407181011](https://in.linkedin.com/jobs/view/director-principal-platform-product-manager-observability-at-fico-4407181011)
- **Resume PDF:** [2026-05-04_FICO_director-principal-platform-product-manager-observability.pdf](https://github.com/Abhillashjadhav/Dreamjob-agent/raw/claude/setup-drive-upload-sQWkx/outputs/2026-05-04/resumes_compact/2026-05-04_FICO_director-principal-platform-product-manager-observability.pdf)
- **Why fit:**
  - Direct overlap: observability platform = exactly Wayfair Model Proxy + eval framework + drift monitoring track record
  - Director/Principal seniority matches Abhillash's target band; 10+ years YoE matches profile
  - Bengaluru location preferred; FICO is enterprise SaaS (B2B Experience competency hits)
- **Why not / risk:** Specific FICO domain (decisioning/credit risk) is adjacent to Abhillash's CDP/personalization work but not direct.
- **Referral path:** no referral path identified (no LinkedIn connections export in repo)
- **Culture snapshot:** culture data not available (Indeed get_company_data not invoked this run — partial-culture flag set)
### 2. Aviatrix — Principal Product Manager (81)
- **Apply:** [https://in.linkedin.com/jobs/view/principal-product-manager-at-aviatrix-4409891928](https://in.linkedin.com/jobs/view/principal-product-manager-at-aviatrix-4409891928)
- **Resume PDF:** [2026-05-04_Aviatrix_principal-product-manager.pdf](https://github.com/Abhillashjadhav/Dreamjob-agent/raw/claude/setup-drive-upload-sQWkx/outputs/2026-05-04/resumes_compact/2026-05-04_Aviatrix_principal-product-manager.pdf)
- **Why fit:**
  - Cloud Native Security Fabric, multi-cloud (AWS/Azure/GCP), developer velocity — direct overlap with Wayfair platform work
  - Principal IC track suits both PM-leader and hands-on architect framing in the resume
  - Bengaluru, well-funded enterprise cloud security
- **Why not / risk:** Cloud security/networking specialism is a stretch for AI/ML platform background; need to lead with developer platform / governance angle.
- **Referral path:** no referral path identified (no LinkedIn connections export in repo)
- **Culture snapshot:** culture data not available (Indeed get_company_data not invoked this run — partial-culture flag set)

---

## BUMPED FITS

### 3. Jobgether — Head of Product (B2B SaaS) (84)
- **Apply:** [https://in.linkedin.com/jobs/view/head-of-product-b2b-saas-at-jobgether-4406280486](https://in.linkedin.com/jobs/view/head-of-product-b2b-saas-at-jobgether-4406280486)
- **Resume PDF:** [2026-05-04_Jobgether_head-of-product-b2b-saas.pdf](https://github.com/Abhillashjadhav/Dreamjob-agent/raw/claude/setup-drive-upload-sQWkx/outputs/2026-05-04/resumes_compact/2026-05-04_Jobgether_head-of-product-b2b-saas.pdf)
- **Why fit:**
  - Head of Product matches Abhillash's leadership target
  - B2B SaaS infrastructure for influencer/performance marketing — adjacent to PayTM B2B Marketplace + IndiaMART subscriptions
  - Multi-product-line ownership matches CTL Personalization Platform breadth
- **Why not / risk:** Recruiter-staffed (Jobgether posts on behalf of partner) — final employer unknown. Influencer marketing domain is consumer-tech adjacent but not core fit.
- **Bump rationale:** original 76 → bumped 84 via +8 PayTM B2B Payments founding PM (0-to-1 fintech) + IndiaMART Big Brands subscriptions (₹30 Cr ARR) → B2B SaaS adjacency
- **Referral path:** no referral path identified (no LinkedIn connections export in repo)
- **Culture snapshot:** culture data not available (Indeed get_company_data not invoked this run — partial-culture flag set)
### 4. Playlist — Principal Product Manager (81)
- **Apply:** [https://in.linkedin.com/jobs/view/principal-product-manager-at-playlist-4406785841](https://in.linkedin.com/jobs/view/principal-product-manager-at-playlist-4406785841)
- **Resume PDF:** [2026-05-04_Playlist_principal-product-manager.pdf](https://github.com/Abhillashjadhav/Dreamjob-agent/raw/claude/setup-drive-upload-sQWkx/outputs/2026-05-04/resumes_compact/2026-05-04_Playlist_principal-product-manager.pdf)
- **Why fit:**
  - Global cross-border payments, PSP integrations, PSD2/regulatory — direct overlap with PayTM B2B Payments founding PM (0-to-1 Fintech launch)
  - Mindbody/ClassPass parent — established consumer tech
  - Mumbai location, technical fluency required (APIs, payment flows)
- **Why not / risk:** Specific cross-border PSD2/Verifactu/NF525 compliance is region-specific (EU); Abhillash's payments expertise is India-centric (PayTM).
- **Bump rationale:** original 73 → bumped 81 via +8 PayTM B2B Payments founding PM + Amazon's 20+ marketplaces internationalization → cross-border payments adjacency
- **Referral path:** no referral path identified (no LinkedIn connections export in repo)
- **Culture snapshot:** culture data not available (Indeed get_company_data not invoked this run — partial-culture flag set)

---

## NEAR-MISSES (gap analysis only, no resume)

### 1. Sabre — Principal Product Manager (78)
- **Apply:** https://in.linkedin.com/jobs/view/principal-product-manager-at-sabre-4389537930
- **Why considered:** Media monetization platform — adjacent to Amazon Promotions Platform ($4B GMV); Bengaluru, Principal seniority
- **Why not a fit:** Travel-supplier media advertising is a niche; Abhillash's Promotions experience is retail/CPG-flavored.

### 2. Qualys — Principal Product Manager,Support (60)
- **Apply:** https://in.linkedin.com/jobs/view/principal-product-manager-support-at-qualys-4407820229
- **Why considered:** Support-product PM — adjacent to Wayfair Model Proxy support tooling
- **Why not a fit:** Pune (not preferred metro); Support specialism is a niche track within PM.


---

## Honest note on net-new

After dedupe against the May 3 cohort (29 surfaced roles in `outputs/seen_index.jsonl`), 23 LinkedIn rows were dropped as already-seen. Additional manual filter dropped 1 more company+title repeat (PayU BNPL — different URL, same role). The 4 fits + 2 near-misses below are all genuinely net-new since 2026-05-03.

— Auto-generated by dreamjob-agent
