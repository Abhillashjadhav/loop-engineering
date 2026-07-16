"""
Inline ReportLab resume builder.

Reads the run's _scored_candidates.json and profile/master_profile.json, emits
one date-stamped PDF per >=80 fit (original or bumped) to
outputs/{date}/resumes/.

Usage:
    python agent/resume_pipeline.py --date 2026-05-03

Layout / framing:
  * Resume content is sourced from profile/master_profile.json.
  * A4 page size, margins 0.58"L/R / 0.48"T/B.
  * Embeds Liberation Sans (Helvetica equivalent) + Liberation Serif TTF so
    ATS / Workday parsers see embedded glyph data (file size ~48-50 KB).
  * Detects people-manager vs IC roles by title and applies per-mode framing.
  * Honors the EXACT TITLES table (overrides master_profile where they differ).
  * Honors verified factual anchors (PayTM 8 PMs / 30% adoption,
    Wayfair "enabling SDLC velocity", IndiaMART catalog/listing quality,
    Flipkart "seller acquisition workflow efficiency").
  * Enforces content exclusivity (Amazon-only / Wayfair-only keywords).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable


# Color palette per the layout spec FORMATTING > "Color palette".
BLUE = HexColor("#1F4E8C")
BODY = HexColor("#1a1a1a")
GREY = HexColor("#333333")


LIB_TTF_DIR = Path("/usr/share/fonts/truetype/liberation")


# ---------- Font registration ------------------------------------------------

# We register Liberation Sans as the visual "Helvetica" body / header font so
# embedded glyph data lands in the PDF (8-12 KB output = unembedded built-in
# Helvetica per the embedded-fonts note; 48-50 KB = correctly embedded).
BASE_FONT = "LibSans"
BOLD_FONT = "LibSans-Bold"
ITALIC_FONT = "LibSans-Italic"
BOLD_ITALIC_FONT = "LibSans-BoldItalic"
SERIF_FONT = "LibSerif"


def _register_fonts() -> None:
    sans_dir = Path("/usr/share/fonts/truetype/liberation")
    pdfmetrics.registerFont(TTFont(BASE_FONT, str(sans_dir / "LiberationSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD_FONT, str(sans_dir / "LiberationSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(ITALIC_FONT, str(sans_dir / "LiberationSans-Italic.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD_ITALIC_FONT, str(sans_dir / "LiberationSans-BoldItalic.ttf")))
    # Tell ReportLab how the bold/italic variants relate so <b>/<i> tags work.
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily(
        BASE_FONT,
        normal=BASE_FONT, bold=BOLD_FONT,
        italic=ITALIC_FONT, boldItalic=BOLD_ITALIC_FONT,
    )


# ---------- Layout spec constants -------------------------------------------

# Override profile titles to match the EXACT TITLES table in the layout spec.
# HARD RULE (do not re-violate): roles BEFORE Amazon (May 2019) use their
# literal title — NEVER append "Product"/"Product Management". This was
# repeatedly broken by embellishing IndiaMart/Flipkart/LeEco here; the values
# below now match the profile verbatim AND the PRE_AMAZON_COMPANIES guard in
# patch_profile_for_skill_md strips any "Product" qualifier that slips back in.
TITLE_OVERRIDES = {
    # Amazon and later — product titles are legitimate and kept.
    "Wayfair":          "Senior Manager, GenAI Product Management",
    "RADAR by AIMleap": "Product Advisor (Pro Bono)",
    "CTL":              "Director, Product Management",
    "Amazon":           "Product Head (Senior PM)",
    # Pre-Amazon — literal titles, no "Product" added.
    "PayTM":            "AVP",
    "IndiaMart":        "Vice President",
    "LeEco":            "Senior Manager",
    "Flipkart":         "Senior Manager",
    "Marico Industries":   "Area Sales Manager",
    "AgroTech Foods Ltd":  "Area Sales Manager",
}

# Roles chronologically before Amazon (start < May 2019). Their titles are used
# verbatim and may never carry an added "Product"/"Product Management" suffix.
PRE_AMAZON_COMPANIES = {
    "PayTM", "IndiaMart", "LeEco", "Flipkart",
    "Marico Industries", "AgroTech Foods Ltd",
}


def _strip_added_product_qualifier(title: str) -> str:
    """Remove an appended 'Product'/'Product Management' qualifier from a
    pre-Amazon title and tidy leftover punctuation. No-op when the title is
    already clean. This is the durable backstop that prevents the
    'Senior Manager, Product' / 'Vice President, Product' class of regression,
    regardless of what TITLE_OVERRIDES or an LLM draft produced."""
    cleaned = re.sub(r"[,\-–]?\s*\bProduct(\s+Management)?\b", "",
                     title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,-–")
    return cleaned or title

# Hard exclusion per the layout spec.
NEVER_INCLUDE_COMPANIES = {"MJ Internet Pvt Ltd"}

CORE_SKILLS_LINE = (
    "GenAI/LLM Platforms · Agentic AI · AI Agents · Autonomous Agents · RAG · "
    "Knowledge Management & Retrieval · Vector Search & Embeddings · "
    "LLM Orchestration · Responsible AI · Model Governance · "
    "Recommendation Systems · Personalization · Search & Discovery · "
    "Developer Tooling · Developer Productivity · API Platform · SDKs · "
    "Cloud Infrastructure (AWS EC2/ECS) · Cloud Compute & Workloads · "
    "Microservices · Distributed Systems · Deployment · DevOps & CI/CD · "
    "Monitoring & Observability · Scalability · Optimization · Reliability · "
    "Automation · "
    "A/B Testing & Experimentation · Product Strategy · Stakeholder Alignment · "
    "Enablement · Cross-functional Leadership · Enterprise SaaS · B2B Platforms"
)

EDUCATION_LINE = "B.E., M.Tech, MBA (Marketing — JBIMS)"

# Decline-list (case-insensitive substring) per the layout spec. Resume generation
# is skipped entirely if the candidate company matches.
DECLINE_LIST = [
    # Amazon umbrella
    "Amazon", "AWS", "Twitch", "IMDb", "Whole Foods", "Audible", "Ring",
    "Zappos", "MGM Studios", "Goodreads", "Kuiper", "A9", "Alexa", "Lab126",
    # Cimpress umbrella
    "Cimpress", "CTL", "Vista", "Vistaprint", "Pixartprinting", "Drukwerkdeal",
    "BuildASign", "Printi", "WIRmachenDRUCK", "Tradeprint", "National Pen",
    "Easyflyer", "Exaprint", "Druck.at", "VistaCreate",
]

# CONTENT EXCLUSIVITY — keywords that must only appear under their owning
# company's bullets. Used to scrub bullets when reframing.
AMAZON_ONLY_TERMS = (
    "RFM", "AARRR", "CDP", "Customer Data Platform",
    "collaborative filtering", "content-based filtering", "matrix factorisation",
    "matrix factorization",
)
WAYFAIR_ONLY_TERMS = (
    "agentic coding assistant", "RAG-powered PR evaluation", "Model Proxy",
    "Advisory Committee", "Champions Group", "Cursor", "Copilot",
)


# ---------- People-manager vs IC detection (the layout spec section) ---------------

PEOPLE_MGR_TITLE_RE = re.compile(
    r"\b(director|sr\.?\s*director|senior\s+director|vp|vice\s+president|"
    r"head\s+of\s+product|group\s+product|gpm)\b",
    re.IGNORECASE,
)
IC_TITLE_RE = re.compile(
    r"\b(principal|staff|lead)\s+pm\b|"
    r"\bprincipal\s+product\s+manager\b|"
    r"\bstaff\s+product\s+manager\b|"
    r"\bsenior\s+product\s+manager\b",
    re.IGNORECASE,
)


def detect_role_mode(candidate: dict) -> str:
    """Return 'people_manager' or 'ic' based on candidate title.

    Per the layout spec: when ambiguous (e.g. 'Principal Group PM'), default to IC.
    Director / Senior Director / VP / Head / GPM strictly imply people manager.
    """
    title = (candidate.get("title") or candidate.get("role") or "").lower()
    # IC takes priority when 'principal' is in the title — even for
    # 'Principal Group PM' the layout-spec default is IC.
    if "principal" in title or "staff product" in title:
        return "ic"
    if PEOPLE_MGR_TITLE_RE.search(title):
        return "people_manager"
    if "senior product manager" in title or "lead product manager" in title:
        return "ic"
    return "ic"  # safe default per the layout spec ambiguity rule


# ── Domain classification ─────────────────────────────────────────────────────
_DOMAIN_SIGNALS: dict[str, list[str]] = {
    "knowledge_ai": [
        "knowledge platform", "knowledge base", "knowledge graph", "retrieval",
        "semantic search", "knowledge layer", "enterprise search", "knowledge management",
    ],
    "agentic_ai": [
        "agentic", "agents", "multi-step", "multi-agent", "autonomous", "orchestration",
        "reasoning", "tool-calling", "copilot", "assistant", "workflow automation",
    ],
    "genai_platform": [
        "genai platform", "ai platform", "llm platform", "model platform", "model serving",
        "mlops", "eval framework", "foundation model", "model governance", "ai infrastructure",
        "ai/ml platform", "llm", "large language", "foundry",
    ],
    "b2b_enterprise": [
        "enterprise saas", "b2b", "marketplace", "payments", "fintech", "subscriptions",
        "billing", "api platform", "multi-tenant", "partner", "channel", "saas platform",
        "payment", "transaction", "checkout", "revenue platform",
    ],
    "consumer_ai": [
        "recommendation", "personalisation", "personalization", "discovery",
        "consumer", "growth", "user engagement", "lifecycle", "retention",
        "ads", "monetization", "audience", "targeting",
    ],
    "developer_platform": [
        "developer productivity", "developer experience", "devex", "internal developer portal",
        "idp", "platform engineering", "api platform", "appsec", "devsecops",
        "developer tooling", "ci/cd", "sdlc",
    ],
}

def classify_jd_domain(candidate: dict) -> str:
    """Classify a JD into one of 6 tailoring domains based on keyword signals."""
    blob = " ".join([
        (candidate.get("title") or ""),
        (candidate.get("company") or ""),
        " ".join(candidate.get("why_fit") or []),
        (candidate.get("description_excerpt") or ""),
    ]).lower()

    scores: dict[str, int] = {}
    for domain, signals in _DOMAIN_SIGNALS.items():
        scores[domain] = sum(1 for s in signals if s in blob)

    if not any(scores.values()):
        return "genai_platform"  # default for AI-heavy roles
    return max(scores, key=lambda d: scores[d])


# Payments / fintech roles get a dedicated reframe layer: the same verified
# facts, but surfaced with the merchant-payments / B2B-payments framing from
# Abhillash's own payments-oriented résumé. Gated tightly so only genuine
# payments/fintech roles trigger it (a stray "payment" in a consumer-growth JD
# — e.g. Google One subscription billing — must NOT flip the whole resume).
_PAYMENTS_TITLE_RE = re.compile(
    r"\b(payment|payments|fintech|lending|bnpl|merchant\s+acquir|"
    r"acquiring|wallet|remittance|payout|card\s+issu)\w*", re.IGNORECASE,
)
_PAYMENTS_BODY_RE = re.compile(
    r"\b(fintech|lending|bnpl|merchant|acquir|remittance|payout|"
    r"card\s+issu|payment\s+(?:platform|rail|gateway|processing|orchestrat))\w*",
    re.IGNORECASE,
)


def is_payments_role(candidate: dict) -> bool:
    """True for genuine payments/fintech roles.

    Trigger on a payments signal in the TITLE, or a payments-platform signal
    (fintech/lending/merchant/acquiring/…) in the JD body. A bare 'payments'
    mention in the body alone (common in consumer-subscription JDs) does not
    qualify — that keeps Google One Growth and similar out of this path.
    """
    title = candidate.get("title") or candidate.get("role") or ""
    if _PAYMENTS_TITLE_RE.search(title):
        return True
    body = " ".join([
        " ".join(candidate.get("why_fit") or []),
        candidate.get("description_excerpt") or "",
    ])
    return bool(_PAYMENTS_BODY_RE.search(body))


# Wayfair bullet indices by domain (indexes into the 4-bullet achievements list):
# 0=platform-overview, 1=engineering-SDLC, 2=catalog-autofill+consumer-roadmap, 3=investment+community
_WAYFAIR_BULLET_ORDER: dict[str, list[int]] = {
    "knowledge_ai":       [1, 0, 3, 2],  # RAG/knowledge layer leads
    "genai_platform":     [0, 1, 2, 3],  # platform overview leads
    "agentic_ai":         [1, 0, 2, 3],  # agentic/eval framework leads
    "b2b_enterprise":     [0, 3, 2, 1],  # platform+investment leads (supplier/payments angle)
    "consumer_ai":        [0, 2, 1, 3],  # platform + consumer roadmap leads
    "developer_platform": [1, 0, 3, 2],  # engineering SDLC leads
}

# Amazon bullet indices by domain (indexes into the 4-bullet Amazon list built at render time):
# 0=AI-engine, 1=CDP-scope, 2=microservices-arch, 3=engagement-UX
_AMAZON_BULLET_ORDER: dict[str, list[int]] = {
    "knowledge_ai":       [0, 1, 2, 3],
    "genai_platform":     [0, 1, 2, 3],
    "agentic_ai":         [0, 1, 3, 2],
    "b2b_enterprise":     [1, 2, 3, 0],  # CDP/data-platform scope leads; transactions prominent
    "consumer_ai":        [0, 3, 1, 2],  # AI engine + UX outcomes lead
    "developer_platform": [2, 1, 0, 3],  # arch leads
}

_TRACK_RECORD_BY_DOMAIN: dict[str, str] = {
    "knowledge_ai":
        "Track record in enterprise knowledge platforms, AI/ML retrieval, RAG systems, "
        "semantic search, knowledge management, eval frameworks, and GenAI at scale; "
        "cloud infrastructure deployment across distributed systems; "
        "data-driven roadmap delivery with clear OKRs and stakeholder alignment.",
    "genai_platform":
        "Track record in AI platform strategy, LLM/RAG systems, eval frameworks, "
        "responsible AI, model governance, agentic AI agents, and enterprise AI adoption; "
        "cloud infrastructure deployment and scalability at scale; "
        "cross-functional leadership and stakeholder alignment driving product vision to delivery.",
    "agentic_ai":
        "Track record in agentic AI agents, multi-agent orchestration, automation, "
        "multi-step reasoning, RAG pipelines, eval frameworks, and enterprise AI platform strategy; "
        "responsible AI deployment, cloud infrastructure, and distributed systems; "
        "data-driven, agile delivery with measurable business impact.",
    "b2b_enterprise":
        "Track record in B2B SaaS platform strategy, API platform development, cloud infrastructure, "
        "marketplace, payments, fintech, subscriptions, and enterprise data platforms; "
        "scalable deployment, infrastructure reliability, and stakeholder alignment; "
        "go-to-market execution, enablement, and P&amp;L ownership.",
    "consumer_ai":
        "Track record in AI/ML recommendations engines, semantic search & discovery, "
        "personalisation, B2B marketplace, monetization, lifecycle targeting, and conversion; "
        "cloud deployment and scalability; "
        "customer research, A/B experimentation, and OKR-driven growth.",
    "developer_platform":
        "Track record in developer productivity platforms, GenAI tooling, automation, "
        "API platform development, SDKs, CI/CD, cloud infrastructure, and enterprise AI adoption; "
        "responsible AI deployment, reliability, scalability; "
        "agile delivery with stakeholder alignment across engineering and leadership.",
}

_PROJECT_BY_DOMAIN: dict[str, str] = {
    "knowledge_ai":       "RAG Eval Harness",
    "genai_platform":     "AI Career Counseling Agent",
    "agentic_ai":         "AI Career Counseling Agent",
    "b2b_enterprise":     "Indian Stocks Deep-Dive & Trading Agents",
    "consumer_ai":        "AI Career Counseling Agent",
    "developer_platform": "RAG Eval Harness",
}


# ---------- Helpers ----------------------------------------------------------

def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
    return s


def is_declined(company: str) -> bool:
    co = (company or "").lower()
    return any(d.lower() in co for d in DECLINE_LIST)


def jd_keywords_for(candidate: dict) -> list[str]:
    """Pick keywords from Abhillash's catalog that overlap the JD.

    The pool is intentionally per-JD: it pulls from title + company + why_fit +
    the JD body itself (description / description_excerpt) so a Stripe Principal
    PM brief and a Wayfair Director PM brief surface different bolded phrases.
    """
    pool = set()
    blob = " ".join([
        (candidate.get("title") or "").lower(),
        (candidate.get("company") or "").lower(),
        " ".join(candidate.get("why_fit") or []).lower(),
        (candidate.get("description_excerpt") or "").lower(),
        (candidate.get("description") or "").lower(),
    ])
    catalog = [
        "Model Proxy", "agentic", "RAG", "LangChain", "LangGraph",
        "developer velocity", "$300M business impact", "2,800+ engineers",
        "AI/ML", "GenAI", "LLM", "platform", "recommendation",
        "personalisation", "subscriptions", "B2B", "marketplace", "0-to-1",
        "multi-tenant", "microservices", "AWS", "eval framework",
        "governance", "developer tooling", "$3.2B GMV", "$1.2B AI/ML growth",
        "$4B GMV", "Customer Data Platform",
        # Stretch-mode adjacencies — bolded when the JD calls for them.
        "API", "SDK", "developer platform", "observability",
        "payments", "fintech", "BNPL", "fraud", "risk",
        "search", "ranking", "discovery", "personalization",
        "trust and safety", "compliance", "data platform",
        "pricing", "billing", "checkout", "growth",
        "experimentation", "A/B testing", "PLG", "self-serve",
        "enterprise SaaS", "0-to-1", "scale", "roadmap",
        # Additional authentic keywords — all trace to master_profile.json
        "stakeholder management", "product strategy", "product vision",
        "product roadmap", "OKRs", "KPIs", "data-driven",
        "agile", "scrum", "go-to-market", "GTM",
        "customer research", "user research", "voice of the customer",
        "API platform", "API design", "developer experience",
        "multi-agent", "multi-LLM", "orchestration",
        "model governance", "safety guardrails", "responsible AI",
        "embedding", "vector search", "semantic search",
        "platform strategy", "0-to-1 product", "cross-functional",
        "monetisation", "monetization", "revenue", "retention",
        "NPS", "CSAT", "cohort analysis", "funnel",
        "enterprise search", "knowledge management",
        "CI/CD", "SDLC", "developer productivity",
        "cloud infrastructure", "cloud native",
        "security", "privacy", "compliance framework",
        "technical product management", "engineering partnership",
    ]
    for term in catalog:
        if term.lower() in blob or any(
            tok in blob for tok in term.lower().replace("/", " ").split()
            if len(tok) > 4
        ):
            pool.add(term)
    # Anchor terms — always bold these, they identify Abhillash's signature work.
    pool.update({"$300M business impact", "2,800+ engineers", "Model Proxy"})
    return list(pool)


# Adjacency map: every JD keyword we are willing to bold must trace back to
# documented evidence in master_profile.json. Bolding a keyword the user has
# no proven experience for is a mild form of fabrication — recruiters expect
# bolded phrases to be load-bearing.
ADJACENCY_EVIDENCE = {
    # AI / ML / GenAI — Wayfair Model Proxy, Amazon AI/ML reco
    "agentic": "Wayfair Model Proxy",
    "genai": "Wayfair Model Proxy",
    "rag": "Wayfair Model Proxy",
    "llm": "Wayfair Model Proxy",
    "langchain": "Wayfair Model Proxy",
    "langgraph": "Wayfair Model Proxy",
    "ai/ml": "Amazon AI/ML recommendation engine",
    "model proxy": "Wayfair Model Proxy",
    "multi-llm": "Wayfair Model Proxy",
    "multi-agent": "Wayfair Model Proxy",
    "orchestration": "Wayfair Model Proxy",
    "model governance": "Wayfair Model Proxy governance",
    "safety guardrails": "Wayfair Model Proxy",
    "responsible ai": "Wayfair Model Proxy governance",
    "embedding": "Amazon AI/ML reco + Wayfair RAG",
    "vector search": "Wayfair RAG pipeline",
    "semantic search": "Wayfair RAG pipeline",
    "enterprise search": "Wayfair catalog search",
    "knowledge management": "Wayfair knowledge layer",
    # Platform / DevTools — Wayfair GenAI dev platform
    "platform": "Wayfair GenAI dev platform",
    "developer velocity": "Wayfair GenAI dev platform",
    "developer platform": "Wayfair GenAI dev platform",
    "developer tooling": "Wayfair GenAI dev platform",
    "developer productivity": "Wayfair GenAI dev platform",
    "developer experience": "Wayfair GenAI dev platform",
    "eval framework": "Wayfair Model Proxy evals",
    "observability": "Wayfair Model Proxy",
    "api platform": "Wayfair Model Proxy API",
    "api design": "Wayfair Model Proxy API",
    "ci/cd": "Wayfair engineering velocity",
    "sdlc": "Wayfair engineering velocity",
    "cloud infrastructure": "Wayfair AWS EC2/ECS",
    "cloud native": "Wayfair AWS EC2/ECS",
    # Reco / Personalization — Amazon + CTL
    "recommendation": "Amazon AI/ML reco $1.2B",
    "personalization": "CTL personalization $3.2B GMV",
    "personalisation": "CTL personalization $3.2B GMV",
    "search": "Amazon Promotions Platform",
    "ranking": "Amazon AI/ML reco",
    "monetisation": "Amazon/IndiaMART revenue platforms",
    "monetization": "Amazon/IndiaMART revenue platforms",
    "retention": "CTL lifecycle targeting",
    "nps": "Wayfair +400 bps satisfaction",
    "csat": "Wayfair customer satisfaction",
    "funnel": "Amazon Promotions Platform",
    "cohort analysis": "Amazon CDP cohort analysis",
    # B2B / Subscriptions / Marketplace — PayTM, IndiaMART
    "b2b": "PayTM B2B Payments founding PM",
    "marketplace": "PayTM B2B + IndiaMART Big Brands",
    "subscriptions": "IndiaMART subscriptions ₹30 Cr ARR",
    "multi-tenant": "PayTM B2B Payments",
    # Payments / Fintech — PayTM + IndiaMart + Amazon
    "payments": "PayTM B2B Payments founding PM",
    "fintech": "PayTM B2B Payments founding PM",
    "bnpl": "PayTM B2B Payments",
    "checkout": "Amazon Promotions Platform checkout flows",
    "billing": "IndiaMART subscriptions billing",
    "pricing": "PayTM + IndiaMART pricing strategy",
    "revenue": "Amazon $4B / IndiaMART ₹30 Cr ARR",
    # Infra / API
    "api": "Wayfair Model Proxy API",
    "sdk": "Wayfair Model Proxy SDK",
    "microservices": "Wayfair Model Proxy",
    "aws": "Wayfair Model Proxy",
    # Governance / Trust / Security / Compliance
    "governance": "Wayfair Model Proxy governance layer",
    "trust and safety": "Wayfair Model Proxy governance",
    "compliance": "Wayfair Model Proxy governance",
    "security": "Wayfair Model Proxy governance",
    "privacy": "Wayfair Model Proxy governance",
    # Product craft — always authentic
    "product strategy": "11+ years product management",
    "product vision": "11+ years product management",
    "product roadmap": "11+ years product management",
    "stakeholder management": "cross-functional leadership",
    "okrs": "Wayfair / IndiaMART goal-setting",
    "kpis": "11+ years metrics-driven PM",
    "data-driven": "Amazon CDP + Wayfair evals",
    "agile": "Wayfair / CTL agile delivery",
    "scrum": "Wayfair / CTL agile delivery",
    "go-to-market": "IndiaMart + Amazon GTM",
    "gtm": "IndiaMart + Amazon GTM",
    "customer research": "Amazon / Wayfair customer discovery",
    "user research": "Amazon / Wayfair user research",
    "voice of the customer": "Wayfair 500-adopter beta VOC",
    "cross-functional": "cross-functional team leadership",
    "platform strategy": "Wayfair GenAI platform strategy",
    "technical product management": "Wayfair / CTL technical PM",
    "engineering partnership": "Wayfair / CTL engineering partnership",
    # Scale / 0-to-1
    "0-to-1": "PayTM B2B Payments founding PM",
    "0-to-1 product": "PayTM B2B Payments founding PM",
    "scale": "Amazon Promotions Platform $4B GMV",
    # Anchors — always allowed
    "$300m business impact": "Wayfair $300M",
    "2,800+ engineers": "Wayfair 2,800+ engineers",
    "$3.2b gmv": "CTL personalization",
    "$1.2b ai/ml growth": "Amazon AI/ML reco",
    "$4b gmv": "Amazon Promotions Platform",
    "customer data platform": "Amazon CDP",
    "enterprise saas": "Wayfair / CTL / IndiaMART",
}


def _has_adjacency_evidence(kw: str) -> bool:
    """Return True iff `kw` maps to a documented experience bullet."""
    return kw.lower().strip() in ADJACENCY_EVIDENCE


def bold_keywords(text: str, keywords: list[str]) -> str:
    """Bold JD keywords ONLY when they map to documented evidence.

    Adjacency check (ADJACENCY_EVIDENCE) prevents implying fluency we can't
    substantiate. An unmapped keyword silently passes through unbolded — it's
    fine if the keyword happens to appear in the bullet (it's the user's own
    text), we just don't draw the recruiter's eye to it as a claim.
    """
    if not text:
        return ""
    out = text
    for kw in sorted(set(keywords), key=len, reverse=True):
        if not kw:
            continue
        if not _has_adjacency_evidence(kw):
            continue
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        m = pattern.search(out)
        if not m:
            continue
        s, e = m.span()
        before = out[:s]
        if before.rfind("<b>") > before.rfind("</b>"):
            continue
        out = out[:s] + "<b>" + out[s:e] + "</b>" + out[e:]
    return out


def scrub_cross_company_terms(text: str, owning_company: str) -> str:
    """Remove cross-company terms per CONTENT EXCLUSIVITY in the layout spec.

    e.g. 'RFM' / 'AARRR' / 'CDP' must only appear under Amazon bullets;
    'Model Proxy' / 'agentic coding assistant' only under Wayfair.
    """
    co = (owning_company or "").lower()
    out = text
    if "amazon" not in co:
        for term in AMAZON_ONLY_TERMS:
            out = re.sub(re.escape(term), "", out, flags=re.IGNORECASE)
    if "wayfair" not in co:
        for term in WAYFAIR_ONLY_TERMS:
            out = re.sub(re.escape(term), "", out, flags=re.IGNORECASE)
    # Tidy any double-spaces / hanging punctuation we just introduced.
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\(\s*[,;]\s*", "(", out)
    out = re.sub(r"\s*[,;]\s*\)", ")", out)
    return out


# ---------------- Integrity guardrails (no fluff, no fabrication) -----------
#
# Hard rules baked into every bullet/summary before it lands in the PDF:
#
# 1. NO FLUFF — banned superlatives/marketing adjectives that don't carry
#    information. Recruiters discount them; ATS systems don't weight them.
#    The list below is curated to remove the dross without breaking phrases
#    where the word is load-bearing (e.g. "world-class" stays only when
#    quantified, never as a self-applied compliment).
#
# 2. NO FABRICATION — we only retain the metrics/scope/dates documented in
#    profile/master_profile.json. The reframe path is allowed to use JD
#    language for the same documented achievement, but cannot invent new
#    numbers, titles, or scope. Fabrication detection runs on every bullet
#    that mentions a $-figure or %-figure not in the profile catalog.
#
# 3. ADJACENT SKILLS ONLY — JD-keyword bolding is restricted to phrases that
#    map to a documented experience bullet OR an adjacency the user has
#    explicit evidence for (e.g. "payments" maps to PayTM; "agentic AI" to
#    Wayfair Model Proxy). Unmapped JD keywords are NOT bolded — they would
#    imply fluency we can't substantiate.

FLUFF_WORDS = [
    # Self-applied superlatives — never substantiated
    "best-in-class", "best in class", "world-class", "world class",
    "industry-leading", "industry leading", "cutting-edge", "cutting edge",
    "state-of-the-art", "state of the art", "next-generation", "next generation",
    "next-gen", "best-of-breed", "best of breed",
    # Hype adjectives
    "amazing", "incredible", "phenomenal", "unparalleled", "unmatched",
    "extraordinary", "exceptional", "remarkable", "outstanding",
    "groundbreaking", "ground-breaking", "revolutionary", "disruptive",
    "transformative", "game-changing", "game changing", "innovative",
    "innovating", "pioneering",
    # Filler
    "brand new", "brand-new", "robust", "synergistic", "holistic",
    "seamless", "seamlessly", "leverage", "leveraging", "leveraged",
    "passionate", "passionately", "drove transformation", "thought leader",
    "thought-leader", "rockstar", "ninja", "guru",
    # Empty modifiers
    "very ", "extremely ", "highly ", "deeply ", "truly ",
    "successfully ", "effectively ", "efficiently ",
    # Self-praise framings
    "spearheaded the", "championed the", "orchestrated the",
]

# Documented numeric anchors derived dynamically from the master profile.
# `load_approved_metrics()` scans every numeric/scope token in the profile
# (executive_summary, every experience bullet, every metric/scope field) and
# returns the set of strings that the fabrication guard treats as "documented."
# Hard-coding this list is fragile — the profile is the source of truth.
APPROVED_METRICS_STATIC_FALLBACK = [
    "$300M", "$15M", "$3.2B", "$4B", "$1.2B", "$1B", "$500M",
    "800M+", "10M+", "2,800+", "15,000+", "13 brands", "11+ years",
    "15+ years", "₹30 Cr", "Rs 30 Cr", "₹78 Cr", "Rs 78 Cr",
    "0-to-1", "0 to 1", "0→1",
]

_APPROVED_METRICS_CACHE: set[str] | None = None


def load_approved_metrics(profile: dict | None = None) -> set[str]:
    """Extract every numeric/$-figure token from the master profile.

    Returns a set of normalised strings. Cached after first call; pass
    `profile=None` (default) to use the cached set on subsequent calls.

    Tokens captured:
      - Dollar / ₹ / Rs amounts:        $300M, $4B, $1.2B, ₹30 Cr
      - Suffix-K/M/B with optional +:    800M+, 10M+, 2,800+, 15,000+
      - Year ranges:                     11+ years, 16+ years
      - Counts with + suffix:            20+ marketplaces, 8 countries
      - Phrases the profile uses verbatim: 0-to-1, 13 brands
    """
    global _APPROVED_METRICS_CACHE
    if profile is None and _APPROVED_METRICS_CACHE is not None:
        return _APPROVED_METRICS_CACHE
    if profile is None:
        return set(APPROVED_METRICS_STATIC_FALLBACK)

    blob_parts = [profile.get("executive_summary", "")]
    for role in profile.get("experience", []):
        blob_parts.extend(role.get("achievements", []) or [])
        if role.get("scope"):
            blob_parts.append(role["scope"])
        if role.get("metrics"):
            blob_parts.extend(role["metrics"])
        blob_parts.append(role.get("title", ""))
    blob = "\n".join(blob_parts)

    metrics: set[str] = set()
    # $ and ₹ amounts
    for m in re.finditer(r"\$[\d.,]+\s*[BMKbmk]?", blob):
        metrics.add(m.group().strip())
    for m in re.finditer(r"₹[\d.,]+\s*Cr?", blob):
        metrics.add(m.group().strip())
    for m in re.finditer(r"Rs\.?\s*[\d.,]+\s*Cr?", blob):
        metrics.add(m.group().strip())
    # Suffix-K/M/B with optional + (e.g. 800M+, 10M+, 2,800+, 15,000+)
    for m in re.finditer(r"\b\d+(?:,\d{3})*\+?\s*[BMKbmk]?\+?\b", blob):
        tok = m.group().strip()
        # Skip standalone tiny integers (3, 6, 8 etc) — too noisy.
        if re.fullmatch(r"\d{1,2}", tok):
            continue
        metrics.add(tok)
    # Year phrases
    for m in re.finditer(r"\b\d+\+?\s*years?\b", blob, re.IGNORECASE):
        metrics.add(m.group().strip())
    # Always-allowed anchor phrases
    metrics.update({"0-to-1", "0 to 1", "0→1"})

    _APPROVED_METRICS_CACHE = metrics
    return metrics


def detect_fabricated_metrics(text: str, profile: dict | None = None) -> list[str]:
    """Return any $-figure or %-figure in the text NOT documented in profile.

    The "documented" set comes from `load_approved_metrics(profile)` which
    scans master_profile.json for every numeric token. A non-empty return
    means a bullet contains a number we have no source for — that bullet
    should be dropped, not coerced.
    """
    if not text:
        return []
    approved = load_approved_metrics(profile)
    approved_lower = {m.lower() for m in approved}
    numeric_re = re.compile(
        r"(\$[\d.,]+\s*[BMK]?|₹[\d.,]+\s*Cr?|Rs\.?\s*[\d.,]+\s*Cr?|"
        r"\b\d+(?:,\d{3})*\+?\s*(?:M|B|K)?\+?\b(?!\s*(?:years|year|months|weeks|days|bps|%)))",
        re.IGNORECASE,
    )
    found = numeric_re.findall(text)
    suspect = []
    for f in found:
        f_clean = f.strip().lower()
        # Plain small integers are typically counts, not metrics.
        if re.fullmatch(r"\d{1,2}\+?", f_clean):
            continue
        if any(f_clean in a or a in f_clean for a in approved_lower):
            continue
        suspect.append(f.strip())
    return suspect


def scrub_fluff(text: str) -> str:
    """Remove fluff words / hype adjectives from a bullet.

    Operates on a copy. The matches are case-insensitive and we preserve
    surrounding punctuation. Multiple whitespace collapsed at the end.
    """
    if not text:
        return ""
    out = text
    for word in FLUFF_WORDS:
        # Word-boundary match for multi-word phrases; trailing space tokens
        # ("very ", "highly ") match anywhere.
        if word.endswith(" "):
            # Negative lookbehind prevents matching inside longer words
            # e.g. "very " must not match inside "discovery "
            pattern = re.compile(rf"(?<!\w){re.escape(word)}", re.IGNORECASE)
        else:
            pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        out = pattern.sub("", out)
    # Tidy up: collapse whitespace, fix orphaned punctuation/articles.
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r"\s+\.", ".", out)
    out = re.sub(r"\(\s+", "(", out)
    out = re.sub(r"\s+\)", ")", out)
    out = re.sub(r"\s{2,}", " ", out)
    # Article cleanup: "a/an/the X" where X starts with a vowel sometimes
    # breaks after we delete "innovative" etc. Fix the obvious ones.
    out = re.sub(r"\ban\s+([bcdfghjklmnpqrstvwxyz])", r"a \1", out, flags=re.IGNORECASE)
    # Convert "a" → "an" only before a/e/i/o. Deliberately exclude "u": resume
    # u-words (unified, unique, user, universal) are pronounced with a 'y' glide
    # and take "a", so "a unified platform" must NOT become "an unified platform".
    out = re.sub(r"\ba\s+([aeio])", r"an \1", out, flags=re.IGNORECASE)
    # Strip orphan leading punctuation/whitespace that fluff removal can create.
    out = re.sub(r"^[\s,;:.\-—]+", "", out)
    # Capitalize first letter if it got de-cased by removal of leading verb.
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out.strip()


def reframe_for_mode(achievement: str, company: str, mode: str) -> str | None:
    """Apply IC- vs people-manager framing per the layout spec.

    Returns None if the bullet should be dropped entirely in this mode
    (e.g. people-management bullets in IC mode that have no technical content).
    """
    text = achievement
    if mode == "ic":
        # Strip common team-size constructions for IC roles.
        text = re.sub(
            r"(with )?a (cross-functional )?team of \d+( \([^)]+\))?",
            "", text, flags=re.IGNORECASE,
        )
        text = re.sub(r"\bgrew (the )?PM org \d+\s*(?:to|->|→)\s*\d+\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+\s+Senior PM promotions\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r";?\s*Mentor \d+ PMs[^.]*\.?", "", text, flags=re.IGNORECASE)
        # Clean punctuation orphaned by the strips above: a clause removed after
        # a comma/semicolon would otherwise leave ", ." or "; ." or "  ,".
        text = re.sub(r"\s*[,;]\s*\.", ".", text)   # "US/EU/NA, ." -> "US/EU/NA."
        text = re.sub(r"\s+([.,;])", r"\1", text)    # space before punctuation
        text = re.sub(r"[,;]\s*([,;])", r"\1", text)  # doubled separators
        text = re.sub(r"\s{2,}", " ", text).strip(" ;,—-")
        if not text or len(text) < 40:
            return None
    return text


# ---------- Profile patches per the layout spec anchors ----------------------------

def patch_profile_for_skill_md(profile: dict) -> dict:
    """Apply EXACT TITLES + VERIFIED FACTUAL ANCHORS overrides at runtime.

    The on-disk master_profile.json is the canonical content source but
    the layout spec prescribes specific titles / metrics that override it. We
    don't mutate the file; we patch the in-memory copy used for this build.
    """
    p = json.loads(json.dumps(profile))  # deep copy

    for role in p.get("experience", []):
        co = role.get("company", "")
        # EXACT TITLES override
        if co in TITLE_OVERRIDES:
            role["title"] = TITLE_OVERRIDES[co]
        # HARD GUARD: pre-Amazon roles never carry an added "Product" qualifier.
        # Enforced here (the single chokepoint both render paths read titles
        # from) so the rule cannot be re-broken by a bad override or LLM draft.
        if co in PRE_AMAZON_COMPANIES:
            role["title"] = _strip_added_product_qualifier(role.get("title", ""))
        # PayTM: 8 PMs (NOT 16); 30% adoption (NOT 40%)
        if co == "PayTM":
            new_achievements = []
            for ach in role.get("achievements", []):
                ach = re.sub(r"team of 16", "team of 8", ach)
                ach = re.sub(r"40% adoption", "30% adoption", ach)
                new_achievements.append(ach)
            role["achievements"] = new_achievements
        # Wayfair: enforce "enabling SDLC velocity" framing language;
        # ensure no "developer productivity L&D charter" wording leaks.
        if co == "Wayfair":
            new_achievements = []
            for ach in role.get("achievements", []):
                ach = ach.replace(
                    "developer productivity L&D charter",
                    "enabling SDLC velocity",
                )
                ach = ach.replace(
                    "$300M annualised impact",
                    "$300M business impact",
                )
                new_achievements.append(ach)
            role["achievements"] = new_achievements
        # IndiaMart: scope = B2B catalog/listing quality (NOT enrichment pipelines)
        if co == "IndiaMart":
            new_achievements = []
            for ach in role.get("achievements", []):
                ach = ach.replace("enrichment pipelines", "B2B catalog/listing quality")
                new_achievements.append(ach)
            role["achievements"] = new_achievements
        # Flipkart: NEVER "field operations efficiency"
        if co == "Flipkart":
            new_achievements = []
            for ach in role.get("achievements", []):
                ach = ach.replace(
                    "field operations efficiency",
                    "seller acquisition workflow efficiency",
                )
                new_achievements.append(ach)
            role["achievements"] = new_achievements

    # Fix years of experience: career started Jun 2011, current year 2026 = 15 years
    p["executive_summary"] = p.get("executive_summary", "").replace("16+ years", "15+ years")

    # Education line
    p["_education_line"] = EDUCATION_LINE
    return p


# ---------- Style sheet ------------------------------------------------------

def build_styles() -> dict:
    """Style sheet built per the layout spec FORMATTING > Color palette / Header treatment."""
    name = ParagraphStyle(
        "Name", fontName=BOLD_FONT, fontSize=15, leading=17, spaceAfter=1,
        textColor=BLUE,
    )
    contact = ParagraphStyle(
        "Contact", fontName=BASE_FONT, fontSize=9, leading=10.5, spaceAfter=0,
        textColor=GREY,
    )
    headline = ParagraphStyle(
        "Headline", fontName=ITALIC_FONT, fontSize=9, leading=11, spaceAfter=4,
        textColor=GREY,
    )
    skills = ParagraphStyle(
        "Skills", fontName=BASE_FONT, fontSize=9, leading=10.5, spaceAfter=2,
        textColor=BODY,
    )
    section = ParagraphStyle(
        "Section", fontName=BOLD_FONT, fontSize=10.5, leading=12,
        spaceBefore=5, spaceAfter=1, textColor=BLUE,
    )
    role = ParagraphStyle(
        "Role", fontName=BOLD_FONT, fontSize=10.5, leading=12.5, spaceAfter=0,
        textColor=BODY,
    )
    role_dates = ParagraphStyle(
        "RoleDates", fontName=BASE_FONT, fontSize=9.5, leading=12.5, spaceAfter=0,
        textColor=GREY,
    )
    role_company = ParagraphStyle(
        "RoleCompany", fontName=ITALIC_FONT, fontSize=9.5, leading=11,
        spaceAfter=2, textColor=GREY,
    )
    body = ParagraphStyle(
        "Body", fontName=BASE_FONT, fontSize=9.5, leading=11.5, spaceAfter=2,
        textColor=BODY,
    )
    bullet = ParagraphStyle(
        "Bullet", fontName=BASE_FONT, fontSize=9.5, leading=11.5,
        leftIndent=12, bulletIndent=0, firstLineIndent=0, spaceAfter=2,
        textColor=BODY,
    )
    summary = ParagraphStyle(
        "Summary", fontName=BASE_FONT, fontSize=9.5, leading=11.5, spaceAfter=4,
        textColor=BODY,
    )
    return {
        "name": name, "contact": contact, "headline": headline,
        "skills": skills, "section": section, "role": role,
        "role_dates": role_dates, "role_company": role_company,
        "body": body, "bullet": bullet, "summary": summary,
    }


def hr_divider(width: float, color=BLUE, thickness: float = 0.6) -> HRFlowable:
    """Layout spec: HRFlowable thickness 0.6pt, color #1F4E8C."""
    return HRFlowable(
        width=width, thickness=thickness, color=color,
        spaceBefore=2, spaceAfter=3, hAlign="LEFT",
    )


def section_header(title: str, styles: dict, doc_width: float) -> list:
    """Section header in BLUE with HRFlowable underneath."""
    return [
        Paragraph(title.upper(), styles["section"]),
        hr_divider(doc_width),
    ]


def role_header(title: str, company: str, dates: str,
                styles: dict, doc_width: float) -> list:
    """Role header per the layout spec: bold title in BODY, dates flush-right in GREY,
    company as italic sub-line in GREY (sub-line, not adjacent to title)."""
    left = Paragraph(f"<b>{title}</b>", styles["role"])
    right = Paragraph(
        f'<para align="right">{dates}</para>', styles["role_dates"],
    )
    t = Table(
        [[left, right]],
        colWidths=[doc_width * 0.74, doc_width * 0.26],
        style=TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]),
    )
    company_line = Paragraph(f"<i>{company}</i>", styles["role_company"])
    return [t, company_line]


def bullet_para(text: str, styles: dict) -> Paragraph:
    return Paragraph(text, styles["bullet"], bulletText="•")


_EM = "—"  # —

# Words a bold lead-in phrase must never END on (prepositions / conjunctions /
# articles) and currency tokens that must stay glued to their following number.
_LEADIN_STOP = {
    'of', 'for', 'in', 'with', 'to', 'or', 'from', 'by', 'at', 'and', 'the',
    'a', 'an', 'on', 'as', 'into', 'across', 'via', 'per', '&', 'that', 'which',
}
_CURRENCY_TOK = {'rs.', 'rs', '$', '₹', 'inr', 'usd'}


def _xml_escape(s: str) -> str:
    """Escape a PLAIN-text segment for ReportLab's mini-XML. Applied per segment
    BEFORE we wrap our own <b> tags around it, so the markup we emit is the only
    markup present — no pre-existing tags to double-escape or nest."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _leadin_span(plain: str) -> tuple[int, int]:
    """Return (0, end) char span to bold as the bullet's headline lead-in.

    Two cases, both computed on PLAIN text (no HTML yet):
      1. A natural em-dash within the first ~95 chars (the X-Y-Z bullets are
         authored this way) → bold everything before it. We do NOT insert a
         dash; the dash already in the text becomes the separator.
      2. No early dash → bold the opening verb phrase (~6 words), trimmed so it
         never ends on a preposition/conjunction/comma or a bare currency token
         ("Rs."). This is what kills "Rs. — 78" and "microservices — platform".
    """
    if not plain:
        return (0, 0)
    dash = plain.find("—")
    if 0 < dash <= 95:
        head = plain[:dash].rstrip()
        if 1 <= len(head.split()) <= 11:
            return (0, len(head))
    toks = list(re.finditer(r"\S+", plain))
    if len(toks) <= 4:
        return (0, len(plain))
    n = min(6, len(toks))

    def _bad_end(tok: str) -> bool:
        wl = tok.rstrip(".,;:").lower()
        return (
            wl in _LEADIN_STOP
            or tok.endswith(",") or tok.endswith(";")
            or wl in _CURRENCY_TOK
        )

    while n > 2 and _bad_end(toks[n - 1].group()):
        n -= 1
    return (0, toks[n - 1].end())


def _keyword_spans(plain: str, keywords: list[str]) -> list[tuple[int, int]]:
    """First non-overlapping char span for each adjacency-backed keyword, longest
    phrases first so 'Customer Data Platform' wins over 'Platform'."""
    spans: list[tuple[int, int]] = []
    for kw in sorted({k for k in keywords if k}, key=len, reverse=True):
        if not _has_adjacency_evidence(kw):
            continue
        pat = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        for m in pat.finditer(plain):
            s, e = m.span()
            if any(s < es and e > ss for ss, es in spans):
                continue  # overlaps a longer phrase already claimed
            spans.append((s, e))
            break  # one emphasis per keyword is enough
    return spans


def _merge_spans(spans: list[tuple[int, int]], plain: str) -> list[tuple[int, int]]:
    """Merge overlapping spans AND coalesce spans separated only by whitespace,
    so adjacent keyword hits ('B2B Payments marketplace') render as one bold run
    instead of a ransom-note. Guarantees no nested <b>."""
    if not spans:
        return []
    spans = sorted(spans)
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        last = merged[-1]
        gap = plain[last[1]:s]
        if s <= last[1] or gap.strip() == "":
            last[1] = max(last[1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def render_bullet(plain: str, keywords: list[str]) -> str:
    """Turn a plain-text bullet into bolded ReportLab markup.

    All emphasis (headline lead-in + JD keywords) is computed as char spans on
    the PLAIN text, merged, then rendered in a single pass. Because the spans
    are merged before any tag is written, nesting ('<b>..<b>..</b></b>') is
    structurally impossible and compound phrases are never split by a dash.
    """
    if not plain:
        return ""
    plain = plain.strip()
    spans = [_leadin_span(plain)] + _keyword_spans(plain, keywords)
    spans = [(s, e) for s, e in spans if e > s]
    merged = _merge_spans(spans, plain)

    # Anti-ransom-note cap: if >55% of the bullet would be bold, keep the
    # lead-in and drop the smallest keyword spans until under the cap.
    def _bold_chars(ms):
        return sum(e - s for s, e in ms)
    if merged and _bold_chars(merged) > 0.55 * len(plain):
        lead = merged[0]
        rest = sorted(merged[1:], key=lambda x: x[1] - x[0], reverse=True)
        kept = [lead]
        for sp in rest:
            if _bold_chars(kept) + (sp[1] - sp[0]) > 0.55 * len(plain):
                continue
            kept.append(sp)
        merged = sorted(kept)

    out, cursor = [], 0
    for s, e in merged:
        if s > cursor:
            out.append(_xml_escape(plain[cursor:s]))
        out.append("<b>" + _xml_escape(plain[s:e]) + "</b>")
        cursor = e
    if cursor < len(plain):
        out.append(_xml_escape(plain[cursor:]))
    return "".join(out)


def add_bold_lead_in(text: str) -> str:
    """Backward-compatible shim. The bullet path now uses render_bullet() which
    computes lead-in + keyword spans together on plain text. Retained only for
    any external caller; bolds the opening phrase with no dash injection."""
    if not text or text.lstrip().startswith("<b>"):
        return text
    s, e = _leadin_span(text)
    if e <= s:
        return _xml_escape(text)
    return (
        _xml_escape(text[:s]) + "<b>" + _xml_escape(text[s:e]) + "</b>"
        + _xml_escape(text[e:])
    )


# ---------- Main builder -----------------------------------------------------

def build_pdf(out_path: Path, candidate: dict, profile: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    company = candidate.get("company") or "Unknown"
    if is_declined(company):
        # Per the layout spec: skip entirely.
        return

    mode = detect_role_mode(candidate)
    domain = classify_jd_domain(candidate)
    payments = is_payments_role(candidate)
    keywords = jd_keywords_for(candidate)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=0.58 * inch,
        rightMargin=0.58 * inch,
        topMargin=0.48 * inch,
        bottomMargin=0.48 * inch,
        title=f"Abhillash Jadhav — Resume — {company}",
        author="Abhillash Jadhav",
    )
    styles = build_styles()
    doc_width = A4[0] - doc.leftMargin - doc.rightMargin
    story = []

    # Header sequence per the layout spec:
    # Name (15pt blue bold) -> contact line (· separators) -> HRFlowable
    # -> Core Skills -> HRFlowable -> Executive Summary
    p = profile["personal"]
    contact_line = (
        f'{p["phone_primary"]} &nbsp;&middot;&nbsp; '
        f'<a href="mailto:{p["email"]}" color="#1F4E8C">{p["email"]}</a> &nbsp;&middot;&nbsp; '
        f'<a href="{p["linkedin"]}" color="#1F4E8C">linkedin.com/in/abhillashjadhav</a> &nbsp;&middot;&nbsp; '
        f'<a href="{p["github"]}" color="#1F4E8C">github.com/Abhillashjadhav</a>'
    )
    story.append(Paragraph(p["name"], styles["name"]))
    story.append(Paragraph(contact_line, styles["contact"]))
    story.append(hr_divider(doc_width))

    # Core Skills line — required by the layout spec "Both modes" section.
    story.append(Paragraph(
        f'<b>Core Skills:</b> {CORE_SKILLS_LINE}',
        styles["skills"],
    ))
    story.append(hr_divider(doc_width))

    # EXECUTIVE SUMMARY — same content but with Wayfair anchor patched.
    story.extend(section_header("Executive Summary", styles, doc_width))
    summary = profile["executive_summary"].replace(
        "$300M annualised impact", "$300M business impact",
    )
    # Swap the generic track-record line for the domain-specific one.
    generic_track = "Track record spans Search & Discovery, Personalisation, Recommendations, Subscriptions, B2B Marketplaces, and Payments."
    domain_track = _TRACK_RECORD_BY_DOMAIN.get(domain, generic_track)
    summary = summary.replace(generic_track, domain_track)
    summary = scrub_cross_company_terms(summary, "Wayfair") if mode == "ic" else summary
    summary = scrub_fluff(summary)  # integrity: strip hype adjectives
    story.append(Paragraph(bold_keywords(summary, keywords), styles["summary"]))

    # PROFESSIONAL EXPERIENCE
    story.extend(section_header("Professional Experience", styles, doc_width))
    fmcg_rendered = False
    for role in profile["experience"]:
        if role["company"] in NEVER_INCLUDE_COMPANIES:
            continue
        # Consolidate Marico + AgroTech into a single FMCG entry under Marico header.
        if role["company"] == "AgroTech Foods Ltd":
            continue  # folded into the Marico block below
        block = []
        if role["company"] == "Marico Industries":
            block.extend(role_header(
                "Area Sales Manager, FMCG",
                "Marico Industries / AgroTech Foods Ltd",
                "Jun 2011 – Jun 2014",
                styles, doc_width,
            ))
        else:
            block.extend(role_header(
                role["title"], role["company"],
                f'{role["start"]} – {role["end"]}',
                styles, doc_width,
            ))
        achievements = list(role["achievements"])
        if role["company"] == "Wayfair":
            # Domain-based bullet reordering: pick the 4 bullets in the JD-optimal order.
            order = _WAYFAIR_BULLET_ORDER.get(domain, [0, 1, 2, 3])
            achievements = [achievements[i] for i in order if i < len(achievements)]
        elif role["company"] == "Amazon":
            # Split the 3 profile bullets into 4 logical bullets, then reorder.
            raw = list(role["achievements"])
            # Build a 4-item list: [AI-engine, CDP-scope, microservices-arch, engagement-UX]
            # Raw[0] = CDP-scope (bullet 1), Raw[1] = AI-engine (bullet 2), Raw[2] = arch+UX (bullet 3)
            # Split Raw[2] into arch (microservices) and UX/engagement halves.
            raw2 = raw[2] if len(raw) > 2 else ""
            # Split on "; improved" or "improved" to separate the two halves of bullet 3.
            import re as _re
            split_pat = _re.compile(r'; (?=improved)', _re.IGNORECASE)
            parts = split_pat.split(raw2, maxsplit=1)
            arch_bullet = parts[0].strip() if parts else raw2
            # parts[1] already begins "improved …" — capitalise it rather than
            # prepending "Improved " (which produced "Improved improved …").
            if len(parts) > 1:
                tail = parts[1].strip()
                ux_bullet = tail[:1].upper() + tail[1:] if tail else ""
            else:
                ux_bullet = ""
            four_bullets = [
                raw[1] if len(raw) > 1 else "",   # 0 = AI-engine
                raw[0] if len(raw) > 0 else "",   # 1 = CDP-scope
                arch_bullet,                        # 2 = microservices-arch
                ux_bullet,                          # 3 = engagement-UX
            ]
            # For b2b_enterprise (payments) domain: reframe CDP bullet to lead with transactions
            if domain == "b2b_enterprise":
                # Surface factual payments ownership within Promotions Platform (user-verified)
                four_bullets[1] = four_bullets[1].replace(
                    "Led Promotions Platform and Customer Data Platform (CDP) for Amazon Global",
                    "Led Promotions Platform (including checkout and payment flows) and"
                    " Customer Data Platform for Amazon Global",
                )
            if payments:
                # Payments-role framing from Abhillash's own payments résumé: the
                # "Promotions and Payments (merchant) Platform" scope + the unified
                # promotions/payments microservices integration (launch time -45%).
                achievements = [
                    "Led Promotions and Payments (merchant) Platform for Amazon's"
                    " worldwide promotions business with a team of 6 (Product Managers)"
                    " — Payments, Promotions, and Analytics products spanning 20+"
                    " international marketplaces, 800M+ customers, 10M+ sellers, and"
                    " $4B annual GMV.",
                    "Integrated Promotions and Payments onto a single microservices"
                    " platform on AWS EC2/ECS with RESTful APIs handling 10M+ daily"
                    " transactions — achieving parity across promotion types, faster"
                    " time-to-value, and a uniform merchant/customer experience while"
                    " cutting new-promotion launch time 45%.",
                    "Shipped the industry-first AI/ML recommendation engine serving"
                    " 800M+ consumers — combining collaborative filtering,"
                    " content-based filtering, and matrix factorisation — driving 40%"
                    " business growth ($1.2B annualised).",
                ]
            else:
                order = _AMAZON_BULLET_ORDER.get(domain, [0, 1, 2, 3])
                achievements = [four_bullets[i] for i in order if four_bullets[i]]
        elif role["company"] == "Marico Industries":
            achievements = achievements[:1]
        elif role["company"] == "LeEco":
            achievements = achievements[:1]
        elif role["company"] == "IndiaMart":
            # b2b_enterprise gets 3 bullets to surface subscriptions depth; others get 2
            cap = 3 if domain == "b2b_enterprise" else 2
            achievements = achievements[:cap]
            if domain == "b2b_enterprise" and len(achievements) >= 2:
                # Lead with EasyPay payments bullet for payments/b2b domain
                achievements = [achievements[1], achievements[0]]
        elif role["company"] == "PayTM":
            if payments:
                # Payments-role framing from Abhillash's payments résumé: B2B
                # Payment Product scope + the lending/bulk-buying/dynamic-catalog
                # launches with their conversion/acquisition outcomes.
                achievements = [
                    "Founding team member of PayTM's B2B business and Payment Product"
                    " (PM Managers, UX, Product Operations) — owned Payments, Product"
                    " Catalog, Order Management, and Customer Communications; defined"
                    " product vision, strategy, roadmap, and pricing for launch and"
                    " scale.",
                    "Launched 3 zero-to-one products (lending, bulk-buying, dynamic"
                    " catalog) — 30% adoption in the first 3 months and +Rs 25 Cr/annum"
                    " incremental GMS; lifted seller conversion +15% and new-customer"
                    " acquisition +20% via a streamlined, redesigned promotion-management"
                    " experience (seller NPS +400 bps).",
                ]
            else:
                achievements = achievements[:2]
        elif role["company"] in {"Flipkart", "RADAR by AIMleap"}:
            achievements = achievements[:2]
        elif role["company"] == "CTL":
            achievements = achievements[:2]
            if payments:
                # Payments-role framing: surface the eCommerce Payments & Orders scope.
                achievements[0] = (
                    "Led Data, eCommerce (Payments and Orders), and Access platforms"
                    " for CTL's 13-brand portfolio (Vistaprint, Pixartprinting and"
                    " others) — all eCommerce workflows including Payments, Order"
                    " Management, and Access products — $3.2B annual GMV across"
                    " US/EU/NA, with a cross-functional team of 21 (PM Managers, UX"
                    " Leads, Data Leads)."
                )
            elif domain == "b2b_enterprise" and achievements:
                # Surface ecommerce + payments platform ownership (user-verified scope)
                achievements[0] = (
                    "Owned end-to-end ecommerce platform (personalisation, checkout, and payments)"
                    " for CTL's 13-brand portfolio (Vistaprint, Pixartprinting and others)"
                    " — $3.2B annual GMV across US/EU/NA; led cross-functional team of 21"
                    " (PM Managers, UX Leads, Data Leads) with 4 hires, 2 internal promotions,"
                    " and 95% engagement."
                )

        rendered_bullets = 0
        for ach in achievements:
            framed = reframe_for_mode(ach, role["company"], mode)
            if not framed:
                continue
            framed = scrub_cross_company_terms(framed, role["company"])
            framed = scrub_fluff(framed)  # integrity: strip hype adjectives
            # Integrity check: if the bullet contains a $/%/₹ figure that's
            # not in APPROVED_METRICS, drop the bullet entirely rather than
            # let a fabricated number through. See detect_fabricated_metrics.
            suspect = detect_fabricated_metrics(framed, profile)
            if suspect:
                # Drop silently; the trajectory logger upstream can audit if needed.
                # Honesty over output (CLAUDE.md rule 2).
                continue
            if len(framed) < 40:  # bullet became too short after scrubbing
                continue
            # Span-based render: lead-in + keyword emphasis merged on plain text
            # in one pass (no nesting, no compound-phrase splits, no injected dash).
            display = render_bullet(framed, keywords)
            block.append(bullet_para(display, styles))
            rendered_bullets += 1
        # Don't emit an orphan role header if every bullet got dropped.
        if rendered_bullets == 0:
            continue
        block.append(Spacer(1, 4))
        # KeepTogether per role: PayTM block must never split, Amazon header
        # must never trail at end of page 1 (KeepTogether handles both: if
        # the entire block can't fit before a page break, it moves whole).
        story.append(KeepTogether(block))

    # SELECTED PROJECT — shown for AI/GenAI/platform/agentic roles; domain-selected.
    title_lower = (candidate.get("title") or candidate.get("role") or "").lower()
    show_project = any(t in title_lower for t in (
        "ai", "genai", "agentic", "llm", "gen ai", "platform", "product manager"
    ))
    if show_project:
        preferred_project = _PROJECT_BY_DOMAIN.get(domain)
        projects = profile.get("selected_projects", [])
        if preferred_project:
            # Show domain-preferred project first, then others if space permits
            ordered = [p for p in projects if p.get("name") == preferred_project]
            ordered += [p for p in projects if p.get("name") != preferred_project]
            projects = ordered[:1]  # one project per resume keeps it tight
        else:
            projects = projects[:1]
        if projects:
            story.extend(section_header("Selected Project", styles, doc_width))
        for proj in projects:
            block = [
                Paragraph(
                    f'<b>{proj["name"]}</b> &mdash; {proj["role"]} &nbsp;'
                    f'<i>({proj["date"]})</i>', styles["role"],
                ),
                Paragraph(bold_keywords(proj["description"], keywords), styles["body"]),
                Spacer(1, 4),
            ]
            story.append(KeepTogether(block))

    # EDUCATION
    story.extend(section_header("Education", styles, doc_width))
    story.append(Paragraph(EDUCATION_LINE, styles["body"]))

    doc.build(story)


# ---------- LLM-draft renderer ----------------------------------------------

def build_pdf_from_draft(out_path: Path, draft: dict, profile: dict,
                         candidate: dict) -> None:
    """Render a PDF from an LLM-generated draft (agent/llm_resume_generator).

    Unlike build_pdf — which reframes master_profile content deterministically
    — this renders bullet text the generator already finalized and the critic
    already vetted. It reuses every layout primitive (fonts, styles, geometry,
    headers) so the visual spec is unchanged; only the content source differs.

    `draft` shape: {executive_summary, core_skills:[...],
    roles:[{company, bullets:[...]}], core_competencies:[[label, kw], ...]}.
    Role titles and dates come from profile["experience"] (verified facts);
    only prose comes from the draft.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    company = candidate.get("company") or "Unknown"
    if is_declined(company):
        return

    keywords = jd_keywords_for(candidate)
    draft_roles = {
        (r.get("company") or "").strip().lower(): (r.get("bullets") or [])
        for r in draft.get("roles", [])
    }

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=0.58 * inch,
        rightMargin=0.58 * inch,
        topMargin=0.48 * inch,
        bottomMargin=0.48 * inch,
        title=f"Abhillash Jadhav — Resume — {company}",
        author="Abhillash Jadhav",
    )
    styles = build_styles()
    doc_width = A4[0] - doc.leftMargin - doc.rightMargin
    story = []

    # Header — name, contact, divider.
    p = profile["personal"]
    contact_line = (
        f'{p["phone_primary"]} &nbsp;&middot;&nbsp; '
        f'<a href="mailto:{p["email"]}" color="#1F4E8C">{p["email"]}</a> &nbsp;&middot;&nbsp; '
        f'<a href="{p["linkedin"]}" color="#1F4E8C">linkedin.com/in/abhillashjadhav</a> &nbsp;&middot;&nbsp; '
        f'<a href="{p["github"]}" color="#1F4E8C">github.com/Abhillashjadhav</a>'
    )
    story.append(Paragraph(p["name"], styles["name"]))
    story.append(Paragraph(contact_line, styles["contact"]))
    story.append(hr_divider(doc_width))

    # Core Skills — from the draft, falling back to the static line.
    skills = draft.get("core_skills") or []
    skills_line = " · ".join(str(s) for s in skills) if skills else CORE_SKILLS_LINE
    story.append(Paragraph(f"<b>Core Skills:</b> {skills_line}", styles["skills"]))
    story.append(hr_divider(doc_width))

    # Executive Summary — from the draft.
    story.extend(section_header("Executive Summary", styles, doc_width))
    summary = scrub_fluff(draft.get("executive_summary", "")
                          or profile.get("executive_summary", ""))
    story.append(Paragraph(bold_keywords(summary, keywords), styles["summary"]))

    # Professional Experience — profile order; bullets from the draft.
    story.extend(section_header("Professional Experience", styles, doc_width))
    for role in profile["experience"]:
        if role["company"] in NEVER_INCLUDE_COMPANIES:
            continue
        bullets = draft_roles.get(role["company"].strip().lower(), [])
        if not bullets:
            continue
        block = []
        block.extend(role_header(
            role["title"], role["company"],
            f'{role["start"]} – {role["end"]}',
            styles, doc_width,
        ))
        rendered = 0
        for b in bullets:
            text = scrub_fluff(str(b))  # cheap hype backstop on top of the critic
            if len(text) < 30:
                continue
            display = bold_keywords(add_bold_lead_in(text), keywords)
            block.append(bullet_para(display, styles))
            rendered += 1
        if rendered == 0:
            continue
        block.append(Spacer(1, 4))
        story.append(KeepTogether(block))

    # Selected Project — verified content, surfaced on AI-flavoured JDs.
    title_lower = (candidate.get("title") or candidate.get("role") or "").lower()
    if any(t in title_lower for t in ("ai", "genai", "agentic", "llm", "gen ai")):
        projects = profile.get("selected_projects", [])
        if projects:
            story.extend(section_header("Selected Project", styles, doc_width))
            for proj in projects:
                block = [
                    Paragraph(
                        f'<b>{proj["name"]}</b> &mdash; {proj["role"]} &nbsp;'
                        f'<i>({proj["date"]})</i>', styles["role"],
                    ),
                    Paragraph(bold_keywords(proj["description"], keywords),
                              styles["body"]),
                    Spacer(1, 4),
                ]
                story.append(KeepTogether(block))

    # Education
    story.extend(section_header("Education", styles, doc_width))
    story.append(Paragraph(EDUCATION_LINE, styles["body"]))

    doc.build(story)


# ---------- Driver ----------------------------------------------------------

def select_fits(scored: list[dict]) -> list[dict]:
    fits = []
    for c in scored:
        original = c.get("original_score") or c.get("score") or 0
        bumped = c.get("bumped_score") or original
        if bumped >= 80 or original >= 80:
            fits.append(c)
    return fits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    root = Path(args.root)

    _register_fonts()

    profile_raw = json.loads((root / "profile/master_profile.json").read_text())
    profile = patch_profile_for_skill_md(profile_raw)
    scored = json.loads(
        (root / f"outputs/{args.date}/_scored_candidates.json").read_text()
    )
    fits = select_fits(scored)
    out_dir = root / f"outputs/{args.date}/resumes"
    out_dir.mkdir(parents=True, exist_ok=True)

    log = []
    for c in fits:
        company = (c.get("company") or "Unknown")
        if is_declined(company):
            log.append({
                "company": company, "title": c.get("title"),
                "status": "skipped_decline_list",
            })
            continue
        company_safe = re.sub(r"[^A-Za-z0-9]+", "_", company).strip("_") or "Unknown"
        title = c.get("title") or c.get("role") or "role"
        slug = slugify(title)
        fname = f"{args.date}_{company_safe}_{slug}.pdf"
        path = out_dir / fname
        build_pdf(path, c, profile)
        if not path.exists():
            log.append({"company": company, "title": title, "status": "failed_no_output"})
            continue
        size = path.stat().st_size
        mode = detect_role_mode(c)
        log.append({
            "company": company,
            "title": title,
            "pdf": str(path.relative_to(root)),
            "size_kb": round(size / 1024, 1),
            "mode": mode,
            "status": "fit" if (c.get("original_score") or 0) >= 80 else "bumped_fit",
        })
        print(f"  [{mode:14}]  {fname}  ({size/1024:.1f} KB)")

    summary_path = root / f"outputs/{args.date}/_resume_generation.json"
    summary_path.write_text(json.dumps(log, indent=2))
    sizes = [e["size_kb"] for e in log if "size_kb" in e]
    if sizes:
        print(
            f"\ngenerated {len(sizes)} resumes -> {out_dir}\n"
            f"size range: {min(sizes):.1f}-{max(sizes):.1f} KB "
            f"(layout spec target: 48-50 KB)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
