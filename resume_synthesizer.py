#!/usr/bin/env python3
"""
Synthetic resume generator and database loader.

Usage:
    python resume_synthesizer.py             # generate + store in DB
    python resume_synthesizer.py --dry-run   # generate only, save to resumes.json

Steps:
  1. Use Claude Sonnet to generate batches of realistic synthetic resumes
  2. Embed each experience chunk locally with SentenceTransformer
  3. Bulk-store profiles in `resumes` and embeddings in `experience_chunks`
"""

import argparse
import json
import os
import random
import re
import time
import uuid

import anthropic
import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv()

GEN_MODEL = "claude-sonnet-4-6"
EMBED_MODEL = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Batch definitions  (name, resumes_per_call, distribution_instructions)
# ---------------------------------------------------------------------------

BATCHES = [
    ("junior", 5, """
200 junior engineers, 1-3 years total experience, seniority=junior.
Tech mix: 30% Python/backend, 25% JS/React, 20% Java, 15% mobile (iOS/Android), 10% mixed.
First or second job. Realistic junior wins — not saving the company.
5 per batch should be strong juniors clearly punching above their level.
open_to_remote: mix of true and false.
"""),
    ("mid", 5, """
Mid-level engineers, 3-6 years total experience, seniority=mid.
Wide variety: backend, fullstack, data engineering, DevOps, ML infra.
Some have switched stacks once. Some have led small projects.
20% have a brief gap or non-linear path. Mix of remote and in-office preferences.
"""),
    ("senior", 5, """
Senior engineers, 6-12 years total experience, seniority=senior.
Strong technical depth. Owned systems, mentored juniors, drove architecture decisions.
Domains: distributed systems, platform engineering, ML/data, fintech, infra.
15% have a visible transition (IC to manager to IC, or startup to big co).
"""),
    ("staff", 5, """
Staff and principal engineers, 10+ years, seniority=staff.
Cross-team technical leadership. Designed org-wide systems. Drove large migrations.
Mix of generalists and deep specialists. Some have published or spoken publicly.
Fewer roles per resume (tenures are longer). High impact per description.
"""),
    ("weak", 5, """
Weaker or inconsistent profiles, seniority=junior or mid.
Visible issues: vague impact, short tenures, unexplained gaps, skills mismatched to title.
Some are real candidates who just write poor resumes. Not fictional caricatures.
Mix of honest-but-weak and slightly padded. Keep them plausible.
"""),
]

PROMPT = """\
Generate {n} realistic software engineer resumes as a JSON array.

CRITICAL RULE — experience descriptions:
Every work experience must have 4-6 sentences of specific achievement narrative.
Real scale, real impact, real problems solved.

BAD:  "Worked on backend systems using Python and Kafka"
GOOD: "Redesigned the order processing service to handle peak traffic by replacing
       a synchronous monolith with Kafka-based event streaming. The system went from
       40,000 to 180,000 orders per hour with zero downtime during the migration."

JSON schema — follow exactly:
[{{
  "name": "Full Name",
  "email": "firstname.lastname@email.com",
  "phone": "+1-555-xxx-xxxx",
  "location": "City, State",
  "open_to_remote": true,
  "total_years": 4,
  "seniority": "junior|mid|senior|staff",
  "summary": "3-4 sentence narrative — who they are, what they excel at, what problems they solve.",
  "experience": [{{
    "company": "Company Name",
    "title": "Job Title",
    "duration": "Mon YYYY - Mon YYYY",
    "description": "4-6 sentence achievement narrative.",
    "skills_demonstrated": ["skill1", "skill2"]
  }}],
  "education": {{
    "degree": "Degree Name",
    "institution": "University Name",
    "year": 2018
  }},
  "key_topics": ["8-12 items — domains and capabilities, not just tool names"]
}}]

BATCH PROFILE:
{distribution}

VARIETY RULES:
- Companies: mix of startups, mid-size, FAANG-adjacent — fictional but believable names
- Locations: SF, NYC, Seattle, Austin, Chicago, Boston — mixed; ~20% fully remote
- Education: top universities, state schools, bootcamp grads, self-taught — mixed
- open_to_remote: mix of true and false across the batch

Return only valid JSON. No markdown fences. No explanation."""


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_batch(client: anthropic.Anthropic, name: str, n: int, distribution: str) -> list[dict]:
    print(f"  [{name}] Calling Claude Sonnet for {n} resumes...")
    max_retries = 8
    response = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=GEN_MODEL,
                max_tokens=16000,
                messages=[{
                    "role": "user",
                    "content": PROMPT.format(n=n, distribution=distribution.strip()),
                }],
            )
            break
        except anthropic.OverloadedError:
            if attempt == max_retries - 1:
                raise
            wait = 10 * (2 ** attempt) + random.uniform(0, 3)  # 10, 20, 40, 80 … seconds + jitter
            print(f"  [{name}] API overloaded — waiting {wait:.0f}s before retry {attempt + 2}/{max_retries}...")
            time.sleep(wait)
    text = response.content[0].text.strip()
    # Strip accidental markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    conn = psycopg2.connect(url)
    register_vector(conn)
    return conn


def _build_raw_text(r: dict) -> str:
    """Reconstruct a plain-text version of the resume for the raw_text column."""
    lines = [r.get("name", ""), r.get("summary", "")]
    for exp in r.get("experience", []):
        lines.append(
            f"{exp.get('title', '')} at {exp.get('company', '')} ({exp.get('duration', '')})"
        )
        lines.append(exp.get("description", ""))
    edu = r.get("education")
    if edu:
        lines.append(f"{edu.get('degree', '')} — {edu.get('institution', '')} {edu.get('year', '')}")
    return "\n".join(filter(None, lines))


def _store_resume(cur, resume_id: str, r: dict) -> None:
    cur.execute(
        """
        INSERT INTO resumes
            (id, name, email, seniority, total_years, location,
             open_to_remote, employment_type, summary, key_topics, raw_text)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            resume_id,
            r.get("name"),
            r.get("email"),
            r.get("seniority"),
            r.get("total_years"),
            r.get("location"),
            r.get("open_to_remote"),
            "full-time",            # synthetic resumes default to full-time
            r.get("summary"),
            r.get("key_topics", []),
            _build_raw_text(r),
        ),
    )


def _store_experiences(
    cur,
    embedder: SentenceTransformer,
    resume_id: str,
    experiences: list[dict],
    seniority: str = "",
    total_years: int = 0,
) -> None:
    for i, exp in enumerate(experiences):
        # Enhanced chunk with seniority context (but not too verbose)
        # Helps vector search understand depth without overwhelming embedding
        chunk = (
            f"Seniority: {seniority} ({total_years} yrs)\n"
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


def bulk_store(resumes: list[dict], embedder: SentenceTransformer) -> None:
    conn = get_conn()
    stored = 0
    try:
        with conn.cursor() as cur:
            for r in resumes:
                resume_id = str(uuid.uuid4())
                _store_resume(cur, resume_id, r)
                _store_experiences(
                    cur, embedder, resume_id, r.get("experience", []),
                    seniority=r.get("seniority", ""),
                    total_years=r.get("total_years", 0),
                )
                stored += 1
                if stored % 10 == 0:
                    print(f"  {stored}/{len(resumes)} stored...")
        conn.commit()
    finally:
        conn.close()
    print(f"  Stored {stored} resumes in database.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and ingest synthetic resumes.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate only; skip DB write. Saves output to --out.",
    )
    parser.add_argument(
        "--out", default="resumes.json",
        help="Output file path for dry-run (default: resumes.json).",
    )
    args = parser.parse_args()

    print(f"Loading embedding model ({EMBED_MODEL})...")
    embedder = SentenceTransformer(EMBED_MODEL)

    client = anthropic.Anthropic()
    all_resumes: list[dict] = []

    print("\nGenerating synthetic resumes...\n")
    for batch_name, n, distribution in BATCHES:
        batch = generate_batch(client, batch_name, n, distribution)
        all_resumes.extend(batch)
        print(f"  Got {len(batch)} — running total: {len(all_resumes)}\n")

    print(f"Total generated: {len(all_resumes)} resumes")

    if args.dry_run:
        with open(args.out, "w") as f:
            json.dump(all_resumes, f, indent=2)
        print(f"Dry run — saved to {args.out}. No DB writes.")
        return

    print("\nEmbedding and storing in database...")
    bulk_store(all_resumes, embedder)
    print("\nDone.")


if __name__ == "__main__":
    main()
