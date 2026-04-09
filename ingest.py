#!/usr/bin/env python3
"""
Resume ingestion + JD matching FastAPI service.

Usage:
    uvicorn ingest:app --reload

Endpoints:
    GET  /          — resume upload UI
    POST /ingest    — multipart PDF upload; returns resume_id + profile JSON
    GET  /search    — JD matching UI
    POST /search    — {job_description: str} → top-10 ranked candidates
"""

import io
import json
import os
import re
import time
import uuid
from collections import defaultdict
from pathlib import Path

import anthropic
import numpy as np
import pdfplumber
import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pgvector.psycopg2 import register_vector
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()

MODEL = "claude-haiku-4-5"
EMBED_MODEL = "all-MiniLM-L6-v2"

MAX_FILE_BYTES = 150 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf"}
PDF_MAGIC = b"%PDF-"

RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60
_rate_store: dict[str, list[float]] = defaultdict(list)

STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

embedder = SentenceTransformer(EMBED_MODEL)
claude = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PROFILE_PROMPT = """\
You are a resume parser. Extract information from the resume below and return \
ONLY valid JSON — no markdown, no code fences, no explanation.

Schema:
{{
  "name": "Full name of the candidate",
  "email": "candidate email address or null if not found",
  "seniority": "one of: junior, mid, senior, staff, principal, executive",
  "total_years": <integer — total years of work experience>,
  "location": "City, State  or  City, Country",
  "open_to_remote": <true | false>,
  "employment_type": "one of: full-time, part-time, contract, freelance",
  "summary": "2-3 sentence summary of the candidate's background and strengths",
  "key_topics": ["skill1", "technology2", "domain3", ...]
}}

Resume:
{text}"""

EXPERIENCE_PROMPT = """\
Extract every work experience entry from the resume below.
Return ONLY valid JSON — no markdown, no code fences, no explanation.

Schema:
{{
  "experiences": [
    {{
      "company": "Company Name",
      "title": "Job Title",
      "duration": "e.g. Jan 2020 - Dec 2022  or  2019 - Present",
      "description": "Full text of this role including all bullet points and responsibilities"
    }}
  ]
}}

Resume:
{text}"""

RANKING_PROMPT = """\
You are a technical recruiter. Rank candidates for the job description below.

Job Description:
{job_description}

Candidates:
{candidates}

═════════════════════════════════════════════════════════════════════════════
STEP 1: ASSESS JD CLARITY
═════════════════════════════════════════════════════════════════════════════
Check if the JD is VAGUE. Red flags for vague JDs:
- Buzzwords without specifics: "strong engineer", "interesting challenges", "smart people"
- No explicit requirements: no years, no specific skills, no domain
- Soft language: "passion", "curiosity", "ability to learn"
- Generic: "growing team", "technical challenges"

If the JD shows 3+ vague signals → MAX confidence is "medium" (never "high")

═════════════════════════════════════════════════════════════════════════════
STEP 2: CHECK SENIORITY FIT & FLAG OVERQUALIFICATION
═════════════════════════════════════════════════════════════════════════════
MANDATORY: Check every candidate's seniority against the JD:

Role is "mid-level" (3-4 years)?
  ✓ Candidate is mid (3-6 years) → OK
  ✗ Candidate is senior (6-12 years) → FLAG "overqualified" (exceeds by 1 level)
  ✗ Candidate is staff (10+ years) → FLAG "overqualified" (exceeds by 2+ levels)

Role is "mid-level backend"?
  ✗ Staff engineer with 15 years → "overqualified" MUST be in flags
  ✗ Principal engineer → "overqualified" MUST be in flags

DO NOT skip this check. DO NOT assume overqualification only matters for very senior roles.

═════════════════════════════════════════════════════════════════════════════
STEP 3: RANK & ASSIGN CONFIDENCE
═════════════════════════════════════════════════════════════════════════════
Rank the top {n} candidates by fit: skills, seniority, depth, recency.

Confidence — STRICT AND SPECIFIC:
  "high"   — ONLY if ALL of:
             (1) JD has specific requirements (tech stack, years, domain)
             (2) Candidate clearly meets requirements
             (3) Descriptions show substantive, relevant depth
             (4) Seniority is appropriate (not overqualified, not underqualified)
             Example: JD asks for "5+ years Kafka, Python", candidate has 7 years doing exactly that.

  "medium" — ANY of:
             - JD has specific requirements but candidate has gaps (missing one skill, seniority slightly high)
             - JD is somewhat vague but candidate profile suggests capability
             - Candidate technically capable but minor misalignment
             Example: JD asks for senior Kafka engineer, candidate is mid-level but deep Kafka expertise.

  "low"    — ANY of:
             - JD is vague (no specific requirements) → automatically low/medium max
             - Candidate barely matches (keywords only, no depth)
             - Significant seniority/skill misalignment
             Example: Vague "passionate engineer wanted" gets low/medium confidence even with good candidate.

RULE: Vague JDs produce NO "high" confidence results. Ever.

═════════════════════════════════════════════════════════════════════════════
STEP 4: FLAGS — MANDATORY CHECK
═════════════════════════════════════════════════════════════════════════════
Flags — ALWAYS check and include if ANY condition is met:
  "overqualified"       — seniority exceeds role level (staff for mid-level, senior for junior, etc.)
  "stale_expertise"     — relevant skills not used in 4+ years
  "domain_mismatch"     — right tools but wrong industry/domain
  "insufficient_depth"  — keywords present but descriptions show surface-level only
  "keyword_match_only"  — title/skills match but work descriptions show no real fit
  "seniority_mismatch"  — experience level misaligned (too junior or too senior for role)

EXAMPLE: Mid-level role, staff engineer candidate → MUST include "overqualified" in flags.

═════════════════════════════════════════════════════════════════════════════
RETURN FORMAT
═════════════════════════════════════════════════════════════════════════════
Return ONLY valid JSON array. No markdown, no explanation, only JSON.

[{{
  "rank": 1,
  "name": "candidate full name",
  "email": "candidate email or null",
  "summary": "their profile summary verbatim",
  "reason": "1-2 crisp sentences: why this rank, any red flags or concerns",
  "confidence": "high|medium|low",
  "flags": []
}}]"""


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW
    _rate_store[ip] = [t for t in _rate_store[ip] if t > window_start]
    if len(_rate_store[ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before trying again.",
        )
    _rate_store[ip].append(now)


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------

def validate_upload(content: bytes, content_type: str | None) -> None:
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_FILE_BYTES:
        kb = len(content) / 1024
        raise HTTPException(status_code=413, detail=f"File is {kb:.1f} KB — must be under 150 KB.")
    if content_type and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")
    if not content.startswith(PDF_MAGIC):
        raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF.")


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def parse_pdf_bytes(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()


# ---------------------------------------------------------------------------
# Claude helpers
# ---------------------------------------------------------------------------

def _call_haiku(prompt: str, max_tokens: int = 2048) -> str:
    response = claude.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _parse_json(raw: str) -> dict | list:
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*|```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to salvage a truncated JSON array by trimming to the last complete object
        last_close = cleaned.rfind("},")
        if last_close != -1:
            try:
                # Find the opening bracket and reconstruct valid JSON
                start = cleaned.index("[")
                return json.loads(cleaned[start: last_close + 1] + "]")
            except (json.JSONDecodeError, ValueError):
                pass
        raise


def extract_profile(text: str) -> dict:
    raw = _call_haiku(PROFILE_PROMPT.format(text=text))
    return _parse_json(raw)


def extract_experiences(text: str) -> list[dict]:
    raw = _call_haiku(EXPERIENCE_PROMPT.format(text=text))
    data = _parse_json(raw)
    return data.get("experiences", []) if isinstance(data, dict) else []


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured.")
    conn = psycopg2.connect(url)
    register_vector(conn)
    return conn


def store(conn, resume_id: str, profile: dict, text: str, experiences: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO resumes
                (id, name, email, seniority, total_years, location,
                 open_to_remote, employment_type, summary, key_topics, raw_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resume_id,
                profile.get("name"),
                profile.get("email"),
                profile.get("seniority"),
                profile.get("total_years"),
                profile.get("location"),
                profile.get("open_to_remote"),
                profile.get("employment_type"),
                profile.get("summary"),
                profile.get("key_topics", []),
                text,
            ),
        )

        for i, exp in enumerate(experiences):
            # Enhanced chunk with seniority context (but not too verbose)
            # Helps vector search understand depth without overwhelming embedding
            seniority = profile.get("seniority", "unknown")
            years = profile.get("total_years", 0)

            chunk = (
                f"Seniority: {seniority} ({years} yrs)\n"
                f"{exp.get('title', '')} at {exp.get('company', '')} "
                f"({exp.get('duration', '')})\n{exp.get('description', '')}"
            ).strip()
            embedding = embedder.encode(chunk)

            cur.execute(
                """
                INSERT INTO experience_chunks
                    (id, resume_id, company, title, duration, chunk_text, embedding, position)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    resume_id,
                    exp.get("company"),
                    exp.get("title"),
                    exp.get("duration"),
                    chunk,
                    embedding,
                    i,
                ),
            )

    conn.commit()


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------

def vector_search(conn, query_embedding: np.ndarray, limit: int = 20) -> list[dict]:
    """
    Return the top `limit` resumes ranked by their best-matching experience chunk.
    Uses cosine distance (<=>); lower = more similar.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                r.id,
                r.name,
                r.email,
                r.summary,
                r.seniority,
                r.total_years,
                r.key_topics,
                MIN(ec.embedding <=> %s) AS best_distance,
                (array_agg(ec.chunk_text ORDER BY ec.embedding <=> %s))[1] AS best_chunk
            FROM experience_chunks ec
            JOIN resumes r ON r.id = ec.resume_id
            GROUP BY r.id, r.name, r.email, r.summary, r.seniority, r.total_years, r.key_topics
            ORDER BY best_distance ASC
            LIMIT %s
            """,
            (query_embedding, query_embedding, limit),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _infer_jd_seniority(job_description: str) -> str | None:
    """Extract implied seniority level from JD text."""
    jd_lower = job_description.lower()

    # Check for explicit seniority keywords
    if any(word in jd_lower for word in ["principal", "principal engineer"]):
        return "principal"
    if any(word in jd_lower for word in ["staff engineer", "staff-level"]):
        return "staff"
    if any(word in jd_lower for word in ["senior ", "7+", "8+", "9+", "10+"]):
        return "senior"
    if any(word in jd_lower for word in ["mid-level", "mid level", "3-4", "3-6", "4-5", "4-6"]):
        return "mid"
    if any(word in jd_lower for word in ["junior", "entry-level", "entry level", "0-2", "1-3"]):
        return "junior"

    return None


def _apply_overqualification_flags(ranked: list[dict], job_description: str, candidates_by_name: dict) -> list[dict]:
    """Post-process Claude's ranking to add overqualified flags where warranted."""
    jd_seniority = _infer_jd_seniority(job_description)
    if not jd_seniority:
        return ranked

    seniority_levels = {"junior": 0, "mid": 1, "senior": 2, "staff": 3, "principal": 4}
    jd_level = seniority_levels.get(jd_seniority, 0)

    for r in ranked:
        candidate_name = r.get("name")
        if candidate_name in candidates_by_name:
            cand_seniority = candidates_by_name[candidate_name].get("seniority", "").lower()
            cand_level = seniority_levels.get(cand_seniority, 0)

            # If candidate seniority exceeds JD seniority, flag as overqualified
            if cand_level > jd_level:
                if "flags" not in r or r["flags"] is None:
                    r["flags"] = []
                if "overqualified" not in r["flags"]:
                    r["flags"].append("overqualified")

    return ranked


def rank_candidates(candidates: list[dict], job_description: str, top_n: int = 10) -> list[dict]:
    """Feed top vector-search hits to Claude Haiku for intelligent ranking."""
    candidate_text = ""
    candidates_by_name = {}

    for i, c in enumerate(candidates, 1):
        candidates_by_name[c['name']] = c
        topics = ", ".join(c.get("key_topics") or [])
        candidate_text += (
            f"--- Candidate {i} ---\n"
            f"Name: {c['name']}\n"
            f"Email: {c.get('email') or 'not provided'}\n"
            f"Seniority: {c.get('seniority')} | {c.get('total_years')} yrs experience\n"
            f"Summary: {c.get('summary')}\n"
            f"Key Skills: {topics}\n"
            f"Most Relevant Experience: {c.get('best_chunk', '')}\n\n"
        )

    prompt = RANKING_PROMPT.format(
        job_description=job_description,
        candidates=candidate_text.strip(),
        n=min(top_n, len(candidates)),
    )
    raw = _call_haiku(prompt, max_tokens=4096)
    result = _parse_json(raw)
    ranked = result if isinstance(result, list) else []

    # Apply overqualification flags post-hoc
    ranked = _apply_overqualification_flags(ranked, job_description, candidates_by_name)

    return ranked


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    job_description: str = Field(..., min_length=10)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def serve_ingest_ui():
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/search", include_in_schema=False)
async def serve_search_ui():
    return FileResponse(STATIC_DIR / "search.html", media_type="text/html")


@app.post("/ingest")
async def ingest(request: Request, file: UploadFile = File(...)):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    content = await file.read()
    validate_upload(content, file.content_type)

    text = parse_pdf_bytes(content)
    if not text:
        raise HTTPException(status_code=422, detail="No text could be extracted from the PDF.")

    profile = extract_profile(text)
    experiences = extract_experiences(text)
    resume_id = str(uuid.uuid4())

    conn = get_conn()
    try:
        store(conn, resume_id, profile, text, experiences)
    finally:
        conn.close()

    return {
        "resume_id": resume_id,
        "name": profile.get("name"),
        "email": profile.get("email"),
        "seniority": profile.get("seniority"),
        "total_years": profile.get("total_years"),
        "location": profile.get("location"),
        "open_to_remote": profile.get("open_to_remote"),
        "employment_type": profile.get("employment_type"),
        "key_topics": profile.get("key_topics", []),
        "summary": profile.get("summary"),
        "experience_chunks_stored": len(experiences),
    }


@app.post("/search")
async def search(request: Request, body: SearchRequest):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    # Embed the job description
    jd_embedding = embedder.encode(body.job_description)

    conn = get_conn()
    try:
        candidates = vector_search(conn, jd_embedding, limit=20)
    finally:
        conn.close()

    if not candidates:
        return {"results": []}

    ranked = rank_candidates(candidates, body.job_description, top_n=10)

    return {"results": ranked}
