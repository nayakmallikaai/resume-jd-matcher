#!/usr/bin/env python3
"""
Evaluation suite for the resume-JD matching system.

Section A — Standard retrieval + ranking metrics (4 JD categories):
  Precision@K, Recall@K, NDCG@K, MRR at both vector-search and Claude-ranked layers.

Section B — Behavioral tests (8 failure-mode scenarios):
  ┌─────────────────────────────────┬─────────────────────────────────────────────┐
  │ Test                            │ Assertion                                   │
  ├─────────────────────────────────┼─────────────────────────────────────────────┤
  │ 1. Keyword present, wrong ctx   │ ADV candidates rank low despite keyword hit │
  │ 2. Right experience, no kws     │ Synonym candidate still ranks in top-3      │
  │ 3. Seniority confusion          │ Humble senior ranks above verbose junior    │
  │ 4. Stale expertise              │ Stale candidate is absent/low + flagged     │
  │ 5. Vague JD                     │ No result has confidence="high"             │
  │ 6. Overqualification            │ OQ candidate has "overqualified" flag       │
  │ 7. Chunk boundary               │ Split-project candidate still ranks top-5   │
  │ 8. Aggregation                  │ Distributed-skills candidate ranks top-5    │
  └─────────────────────────────────┴─────────────────────────────────────────────┘

Usage:
    python eval.py                        # full eval
    python eval.py --section a            # only Section A (standard metrics)
    python eval.py --section b            # only Section B (behavioral)
    python eval.py --no-teardown          # keep seed data in DB
    python eval.py --k 5                  # evaluate at top-5 (default: 10)
"""

import argparse
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv

from ingest import embedder, get_conn, rank_candidates, vector_search
from resume_synthesizer import _store_experiences, _store_resume

load_dotenv()

# =============================================================================
# SECTION A — Positive (seed) resumes for standard metric test cases
# =============================================================================

# ── TC1: Senior Backend Engineer ─────────────────────────────────────────────
TC1_POSITIVES = [
    {
        "_id": str(uuid.uuid4()),
        "name": "Jordan Kim",
        "email": "jordan.kim@example.com",
        "seniority": "senior", "total_years": 9,
        "location": "Seattle, WA", "open_to_remote": True,
        "summary": (
            "Senior backend engineer with 9 years building distributed systems at scale. "
            "Deep expertise in event-driven architecture, Kafka, and Kubernetes. "
            "Led 6-engineer teams through full infrastructure migrations with zero downtime."
        ),
        "key_topics": ["distributed systems", "Kafka", "Kubernetes", "Python", "Go",
                       "microservices", "high-throughput systems", "reliability engineering"],
        "experience": [{
            "company": "StreamlineOps", "title": "Senior Backend Engineer",
            "duration": "Mar 2019 - Present",
            "description": (
                "Owned the event-processing backbone serving 200k events/sec across 40 microservices. "
                "Migrated a legacy monolith to Kafka-based event streaming, reducing P99 latency from "
                "1.8s to 120ms. Designed the sharding strategy that scaled the order service from "
                "10k to 500k daily transactions. Led a 6-engineer team, drove MTTR from 45 min to 8 min."
            ),
            "skills_demonstrated": ["Kafka", "Python", "Kubernetes"],
        }],
    },
    {
        "_id": str(uuid.uuid4()),
        "name": "Elena Vasquez",
        "email": "elena.vasquez@example.com",
        "seniority": "staff", "total_years": 12,
        "location": "San Francisco, CA", "open_to_remote": False,
        "summary": (
            "Staff engineer with 12 years owning platform reliability for systems processing "
            "1M+ requests/sec. Expert in distributed consensus, event sourcing, and Kubernetes."
        ),
        "key_topics": ["distributed consensus", "event sourcing", "Kubernetes", "Kafka",
                       "Python", "platform engineering", "reliability"],
        "experience": [{
            "company": "NovaPlatform", "title": "Staff Engineer — Platform",
            "duration": "Jun 2018 - Present",
            "description": (
                "Designed the event-sourcing layer processing 1.2M events/sec with 99.99% durability. "
                "Re-architected Kubernetes multi-cluster federation used by 20 product teams, cutting "
                "deploy time 70%. Drove distributed tracing adoption company-wide."
            ),
            "skills_demonstrated": ["Kafka", "Kubernetes", "Python"],
        }],
    },
    {
        "_id": str(uuid.uuid4()),
        "name": "Marcus Osei",
        "email": "marcus.osei@example.com",
        "seniority": "senior", "total_years": 7,
        "location": "Austin, TX", "open_to_remote": True,
        "summary": (
            "Senior backend engineer specialising in event-driven microservices and "
            "Kubernetes-native systems. Built real-time pipelines handling 150k messages/sec."
        ),
        "key_topics": ["microservices", "Kafka", "Kubernetes", "Python",
                       "event-driven architecture", "observability", "Go"],
        "experience": [{
            "company": "RapidEdge Labs", "title": "Senior Backend Engineer",
            "duration": "Aug 2020 - Present",
            "description": (
                "Rebuilt the notification pipeline from polling to Kafka pub/sub, cutting delivery "
                "latency from 4s to 40ms at 150k msg/sec. Designed the Kubernetes-native deployment "
                "framework adopted across 12 services. Reduced infrastructure cost 35% through right-sizing."
            ),
            "skills_demonstrated": ["Kafka", "Kubernetes", "Python"],
        }],
    },
]

# ── TC2: ML Engineer ─────────────────────────────────────────────────────────
TC2_POSITIVES = [
    {
        "_id": str(uuid.uuid4()),
        "name": "Aria Zhang",
        "email": "aria.zhang@example.com",
        "seniority": "senior", "total_years": 6,
        "location": "New York, NY", "open_to_remote": True,
        "summary": (
            "ML Engineer with 6 years building production ML systems end-to-end. "
            "Deep PyTorch expertise, feature engineering at scale, and model lifecycle management."
        ),
        "key_topics": ["PyTorch", "machine learning", "feature engineering", "MLflow",
                       "model training", "A/B testing", "recommendation systems"],
        "experience": [{
            "company": "Meridian Commerce", "title": "Senior ML Engineer",
            "duration": "Sep 2021 - Present",
            "description": (
                "Designed and trained a two-tower retrieval model in PyTorch that improved "
                "recommendation CTR 28%, attributing to $12M ARR lift. Built a feature store "
                "serving 400+ features with sub-5ms p99. Established the MLflow model registry, "
                "halving time-to-production. Ran 30+ A/B tests."
            ),
            "skills_demonstrated": ["PyTorch", "feature engineering", "MLflow"],
        }],
    },
    {
        "_id": str(uuid.uuid4()),
        "name": "Omar Hassan",
        "email": "omar.hassan@example.com",
        "seniority": "senior", "total_years": 7,
        "location": "Chicago, IL", "open_to_remote": False,
        "summary": (
            "ML Engineer with 7 years focused on training and deploying deep learning models "
            "for NLP and computer vision at scale."
        ),
        "key_topics": ["PyTorch", "deep learning", "NLP", "model compression",
                       "ML pipelines", "model serving", "feature engineering"],
        "experience": [{
            "company": "Synthos AI", "title": "ML Engineer",
            "duration": "Jan 2020 - Present",
            "description": (
                "Trained BERT-based document classifiers achieving 94% F1 on a 50-class taxonomy. "
                "Built distributed PyTorch training on Kubernetes, reducing training time from 18h "
                "to 2.5h for 1B-parameter models. Applied knowledge distillation to cut model size "
                "4x with <1% accuracy drop."
            ),
            "skills_demonstrated": ["PyTorch", "NLP", "Kubernetes"],
        }],
    },
    {
        "_id": str(uuid.uuid4()),
        "name": "Nina Rodriguez",
        "email": "nina.rodriguez@example.com",
        "seniority": "mid", "total_years": 4,
        "location": "Boston, MA", "open_to_remote": True,
        "summary": (
            "ML Engineer with 4 years training supervised and self-supervised models for "
            "tabular and time-series data. Strong in scikit-learn, PyTorch, and experiment tracking."
        ),
        "key_topics": ["PyTorch", "scikit-learn", "feature engineering", "MLflow",
                       "time-series forecasting", "model evaluation", "A/B testing"],
        "experience": [{
            "company": "Forecast Systems", "title": "ML Engineer",
            "duration": "Mar 2022 - Present",
            "description": (
                "Built a gradient-boosted demand forecasting model that reduced inventory overstock "
                "22%, saving $3M annually. Engineered 80+ features from raw transaction logs. "
                "Migrated experiment tracking to MLflow. Designed the offline evaluation harness "
                "that gates all models before shadow deployment."
            ),
            "skills_demonstrated": ["PyTorch", "scikit-learn", "feature engineering"],
        }],
    },
]

# ── TC3: Product Manager ──────────────────────────────────────────────────────
TC3_POSITIVES = [
    {
        "_id": str(uuid.uuid4()),
        "name": "Rachel Kim",
        "email": "rachel.kim@example.com",
        "seniority": "senior", "total_years": 8,
        "location": "San Francisco, CA", "open_to_remote": True,
        "summary": (
            "Senior PM with 8 years driving B2B SaaS roadmaps. Expert in stakeholder alignment, "
            "OKR-setting, and GTM strategy. Led launches that grew ARR by $18M."
        ),
        "key_topics": ["product roadmap", "stakeholder management", "GTM strategy", "OKRs",
                       "B2B SaaS", "enterprise product", "pricing strategy"],
        "experience": [{
            "company": "Clarifio", "title": "Senior Product Manager",
            "duration": "Feb 2019 - Present",
            "description": (
                "Owned the enterprise workflow product from roadmap through GA, growing it to "
                "$18M ARR in 24 months. Defined pricing and packaging that increased ACV 40%. "
                "Led cross-functional squads of 12 (eng, design, data, sales). "
                "Ran 60+ customer discovery interviews that reshaped the 3-year product strategy."
            ),
            "skills_demonstrated": ["roadmap", "GTM", "stakeholder management"],
        }],
    },
    {
        "_id": str(uuid.uuid4()),
        "name": "James Chen",
        "email": "james.chen@example.com",
        "seniority": "mid", "total_years": 5,
        "location": "New York, NY", "open_to_remote": False,
        "summary": (
            "Product Manager with 5 years in B2B SaaS. Bridges technical and business stakeholders. "
            "Managed roadmaps for teams of 8-15 engineers."
        ),
        "key_topics": ["product roadmap", "PRD writing", "stakeholder management",
                       "B2B SaaS", "discovery", "OKRs", "product strategy"],
        "experience": [{
            "company": "WorkBridge", "title": "Product Manager",
            "duration": "Jun 2021 - Present",
            "description": (
                "Drove the launch of an integration marketplace to 200 active integrations in 18 months, "
                "contributing to 15% higher retention. Partnered with sales and CS to translate 120+ "
                "support tickets into a prioritised roadmap that reduced churn 8 points."
            ),
            "skills_demonstrated": ["roadmap", "stakeholder management", "discovery"],
        }],
    },
]

# ── TC4: AI Engineer (LLM fine-tuning) ───────────────────────────────────────
TC4_POSITIVES = [
    {
        "_id": str(uuid.uuid4()),
        "name": "Yuki Tanaka",
        "email": "yuki.tanaka@example.com",
        "seniority": "senior", "total_years": 5,
        "location": "Seattle, WA", "open_to_remote": True,
        "summary": (
            "AI Engineer with 5 years specialising in LLM fine-tuning and alignment. "
            "Hands-on with LoRA, QLoRA, and RLHF on models up to 70B parameters."
        ),
        "key_topics": ["LLM fine-tuning", "LoRA", "QLoRA", "RLHF", "Hugging Face",
                       "model evaluation", "PEFT", "transformer architecture"],
        "experience": [{
            "company": "FoundationAI", "title": "AI Engineer — Fine-tuning",
            "duration": "Jan 2022 - Present",
            "description": (
                "Led fine-tuning of Llama-2-70B with QLoRA for legal document summarisation, "
                "achieving human-parity ROUGE at 1/10th GPT-4 cost. Built a reusable RLHF pipeline "
                "using TRL on 50k human preference pairs, improving win-rate from 52% to 71%. "
                "Designed the 8-benchmark evaluation harness that gates all fine-tuned models."
            ),
            "skills_demonstrated": ["QLoRA", "RLHF", "Hugging Face", "model evaluation"],
        }],
    },
    {
        "_id": str(uuid.uuid4()),
        "name": "Carlos Vega",
        "email": "carlos.vega@example.com",
        "seniority": "senior", "total_years": 6,
        "location": "Austin, TX", "open_to_remote": True,
        "summary": (
            "AI Engineer with 6 years training and adapting large language models for enterprise. "
            "Deep expertise in PEFT, DPO, and custom training loops."
        ),
        "key_topics": ["LLM fine-tuning", "RLHF", "DPO", "LoRA", "Hugging Face",
                       "custom training pipelines", "model alignment", "PyTorch"],
        "experience": [{
            "company": "AlignLabs", "title": "Senior AI Engineer",
            "duration": "May 2021 - Present",
            "description": (
                "Fine-tuned Mistral-7B with LoRA for domain-specific code generation, outperforming "
                "GPT-3.5 on internal benchmarks by 19 points. Implemented DPO from scratch, reducing "
                "training compute 60% with equivalent alignment quality. Built a custom training loop "
                "for models up to 34B on 4x A100 nodes."
            ),
            "skills_demonstrated": ["LoRA", "DPO", "PyTorch", "model evaluation"],
        }],
    },
]

# =============================================================================
# SECTION A — Adversarial resumes (original 4)
# =============================================================================

ADV_VERBOSE_JUNIOR = {
    "_id": str(uuid.uuid4()),
    "_label": "ADV-1: Verbose junior / Senior Backend JD",
    "_target_tc": "tc1",
    "name": "Tyler Brooks",
    "email": "tyler.brooks@example.com",
    "seniority": "junior", "total_years": 2,
    "location": "Remote", "open_to_remote": True,
    "summary": (
        "Passionate backend developer with exposure to Kafka, Kubernetes, distributed systems, "
        "microservices, Python, Go, gRPC, and event-driven architecture."
    ),
    "key_topics": ["Kafka", "Kubernetes", "distributed systems", "microservices",
                   "Python", "Go", "gRPC", "Docker"],
    "experience": [{
        "company": "TechStartup Co", "title": "Junior Backend Developer",
        "duration": "Jun 2023 - Present",
        "description": (
            "Worked on backend services using Python and helped integrate a Kafka consumer "
            "for processing user events. Assisted with Kubernetes deployments by writing YAML "
            "manifests under senior engineer guidance. Participated in a microservices refactoring "
            "project where I updated API endpoints and fixed bugs in the distributed cache integration."
        ),
        "skills_demonstrated": ["Python", "Kafka", "Kubernetes"],
    }],
}

ADV_DATA_ANALYST = {
    "_id": str(uuid.uuid4()),
    "_label": "ADV-2: Python data analyst / ML Engineer JD",
    "_target_tc": "tc2",
    "name": "Sarah Chen",
    "email": "sarah.chen@example.com",
    "seniority": "mid", "total_years": 5,
    "location": "Chicago, IL", "open_to_remote": False,
    "summary": (
        "Data analyst with 5 years using Python, SQL, and pandas to extract, clean, and "
        "visualise business data. Builds executive dashboards and automates monthly reporting."
    ),
    "key_topics": ["Python", "pandas", "SQL", "Tableau", "data visualisation",
                   "business reporting", "ETL", "Jupyter", "Excel"],
    "experience": [{
        "company": "RetailCo Analytics", "title": "Data Analyst",
        "duration": "Mar 2021 - Present",
        "description": (
            "Wrote Python scripts with pandas and openpyxl to automate 14 weekly reports, saving "
            "20 hours of manual work per week. Built Tableau dashboards for sales and operations "
            "tracking KPIs across 200 stores. Ran SQL queries against the data warehouse for ad-hoc "
            "business questions. Created Jupyter notebooks to explore purchase trends."
        ),
        "skills_demonstrated": ["Python", "pandas", "SQL", "Tableau"],
    }],
}

ADV_SWE_FOR_PM = {
    "_id": str(uuid.uuid4()),
    "_label": "ADV-3: Software Engineer / Product Manager JD",
    "_target_tc": "tc3",
    "name": "Marcus Johnson",
    "email": "marcus.johnson@example.com",
    "seniority": "mid", "total_years": 5,
    "location": "New York, NY", "open_to_remote": True,
    "summary": (
        "Full-stack software engineer with 5 years building web applications in React and Node.js. "
        "Ships clean, well-tested code and enjoys mentoring junior developers."
    ),
    "key_topics": ["React", "Node.js", "PostgreSQL", "REST APIs", "TypeScript",
                   "full-stack development", "testing", "CI/CD"],
    "experience": [{
        "company": "WebAgency Ltd", "title": "Software Engineer",
        "duration": "Jan 2021 - Present",
        "description": (
            "Built a customer portal in React and Node.js consolidating 6 legacy tools, reducing "
            "support tickets 30%. Designed PostgreSQL schemas for the subscription billing module. "
            "Wrote Playwright end-to-end tests. Mentored 2 junior engineers."
        ),
        "skills_demonstrated": ["React", "Node.js", "PostgreSQL"],
    }],
}

ADV_LLM_API_USER = {
    "_id": str(uuid.uuid4()),
    "_label": "ADV-4: SWE with light LLM API touch / AI Engineer fine-tuning JD",
    "_target_tc": "tc4",
    "name": "Priya Patel",
    "email": "priya.patel@example.com",
    "seniority": "mid", "total_years": 4,
    "location": "San Francisco, CA", "open_to_remote": True,
    "summary": (
        "Backend engineer with 4 years in Python and FastAPI. Built AI-powered product features "
        "by integrating OpenAI and Anthropic APIs via LangChain."
    ),
    "key_topics": ["Python", "FastAPI", "PostgreSQL", "OpenAI API", "LangChain",
                   "LLM integration", "RAG", "chatbots", "Docker"],
    "experience": [{
        "company": "ProductCo", "title": "Backend Engineer",
        "duration": "Feb 2022 - Present",
        "description": (
            "Integrated the OpenAI ChatGPT API into the support feature, with retrieval-augmented "
            "context built using LangChain and pgvector. Built the FastAPI service that proxies "
            "requests to the Anthropic API with rate limiting and caching. Set up a LangChain agent "
            "for customer queries. No model training or fine-tuning — all work used hosted API endpoints."
        ),
        "skills_demonstrated": ["Python", "FastAPI", "OpenAI API", "LangChain"],
    }],
}

SECTION_A_ADVERSARIAL = [ADV_VERBOSE_JUNIOR, ADV_DATA_ANALYST, ADV_SWE_FOR_PM, ADV_LLM_API_USER]

# =============================================================================
# SECTION B — Behavioral test resumes (8 scenarios)
# =============================================================================

# B1 — Keyword present, wrong context (same as ADV adversarials, covered above)

# B2 — Right experience, no keywords (uses synonyms / domain vocabulary)
BEH_NO_KEYWORDS = {
    "_id": str(uuid.uuid4()),
    "_label": "B2: Right experience, avoids JD keywords",
    "name": "Dmitri Volkov",
    "email": "dmitri.volkov@example.com",
    "seniority": "senior", "total_years": 8,
    "location": "Remote", "open_to_remote": True,
    "summary": (
        "Senior infrastructure engineer with 8 years designing fault-tolerant, high-throughput "
        "data pipelines and container-orchestrated service meshes. Led reliability overhauls "
        "for systems handling 300k concurrent connections."
    ),
    "key_topics": [
        "fault-tolerant pipelines", "container orchestration", "message brokers",
        "service mesh", "high-throughput infrastructure", "reliability engineering",
        "event streaming", "distributed coordination",
    ],
    "experience": [{
        "company": "ScaleCraft", "title": "Senior Infrastructure Engineer",
        "duration": "Apr 2018 - Present",
        "description": (
            "Replaced a polling-based integration layer with an event-streaming backbone using "
            "a distributed message broker, cutting end-to-end latency from 3s to 80ms at "
            "300k events/sec. Migrated 30 services to a container-orchestrated deployment model, "
            "reducing release cycle from 2 weeks to same-day. Designed the distributed coordination "
            "layer that enabled zero-downtime rolling deployments across 5 data centres. "
            "Led a 5-engineer platform team through an 18-month reliability roadmap that brought "
            "availability from 99.5% to 99.97%."
        ),
        "skills_demonstrated": ["event streaming", "container orchestration", "reliability"],
    }],
}

# B3 — Humble senior (accurate but understated) vs verbose junior (Tyler Brooks, already defined)
BEH_HUMBLE_SENIOR = {
    "_id": str(uuid.uuid4()),
    "_label": "B3: Humble senior — undersells real depth",
    "name": "Wei Liu",
    "email": "wei.liu@example.com",
    "seniority": "senior", "total_years": 9,
    "location": "Seattle, WA", "open_to_remote": True,
    "summary": (
        "Backend engineer. Worked on distributed infrastructure for about 9 years. "
        "Mostly Python and Go. Have done some Kafka and Kubernetes work."
    ),
    "key_topics": ["Python", "Go", "Kafka", "Kubernetes", "distributed systems",
                   "backend engineering", "infrastructure"],
    "experience": [{
        "company": "DataCore Systems", "title": "Backend Engineer",
        "duration": "Jan 2016 - Present",
        "description": (
            "Was part of the team that redesigned the event pipeline to use Kafka, which ended up "
            "handling around 180k events per second. Helped with the Kubernetes migration for the "
            "main service fleet. Worked on the sharding approach for the database layer that handled "
            "the 10x traffic growth during peak seasons. Also helped mentor a few junior engineers "
            "and was involved in some of the architecture review sessions."
        ),
        "skills_demonstrated": ["Python", "Go", "Kafka", "Kubernetes"],
    }],
}

# B4 — Stale expertise (was expert years ago, nothing recent)
BEH_STALE_EXPERT = {
    "_id": str(uuid.uuid4()),
    "_label": "B4: Stale expertise — Hadoop/MapReduce, last used 2016",
    "name": "Robert Miller",
    "email": "robert.miller@example.com",
    "seniority": "senior", "total_years": 16,
    "location": "Chicago, IL", "open_to_remote": False,
    "summary": (
        "Experienced data infrastructure engineer. Deep background in Hadoop MapReduce, "
        "Hive, and Java EE batch processing. Now focused on maintaining legacy pipelines "
        "and mentoring junior engineers."
    ),
    "key_topics": ["Hadoop", "MapReduce", "Hive", "Java EE", "batch processing",
                   "legacy systems", "data pipelines", "HDFS"],
    "experience": [
        {
            "company": "EnterpriseDataCo", "title": "Senior Data Engineer",
            "duration": "Jan 2017 - Present",
            "description": (
                "Maintains and supports the legacy Hadoop MapReduce batch processing system "
                "originally built in 2013. Handles incident response when Hive jobs fail and "
                "coordinates with the business on SLA impacts. Helps onboard new team members "
                "to the existing Java EE codebase. No new ML or streaming work in this role."
            ),
            "skills_demonstrated": ["Hadoop", "Hive", "Java EE"],
        },
        {
            "company": "BigDataStartup", "title": "Data Engineer",
            "duration": "Mar 2010 - Dec 2016",
            "description": (
                "Built MapReduce jobs in Java processing 5TB of daily clickstream data. "
                "Designed the Hive schema for the analytics data warehouse. Led migration "
                "from raw HDFS to a managed Hadoop cluster. Was considered a Hadoop expert "
                "internally; gave talks at two Hadoop World conferences in 2014 and 2015."
            ),
            "skills_demonstrated": ["Hadoop", "MapReduce", "HDFS", "Hive"],
        },
    ],
}

# B5 — Overqualified: staff engineer for a mid-level role
BEH_OVERQUALIFIED = {
    "_id": str(uuid.uuid4()),
    "_label": "B6: Overqualified — staff engineer for mid-level backend role",
    "name": "Alexandra Hunt",
    "email": "alexandra.hunt@example.com",
    "seniority": "staff", "total_years": 15,
    "location": "San Francisco, CA", "open_to_remote": True,
    "summary": (
        "Staff engineer with 15 years designing planet-scale distributed systems. "
        "Led org-wide technical strategy at two unicorn-stage companies. "
        "Defined the engineering standards adopted across 200-engineer organisations."
    ),
    "key_topics": ["distributed systems", "Kafka", "Kubernetes", "Python", "Go",
                   "technical strategy", "org-wide architecture", "engineering leadership",
                   "staff engineering", "systems design"],
    "experience": [{
        "company": "MegaScale Inc", "title": "Principal Engineer",
        "duration": "Jan 2018 - Present",
        "description": (
            "Architected the global event fabric processing 5M events/sec across 12 regions, "
            "used by all 40 product teams. Defined the distributed systems primitives that became "
            "the company's engineering standards. Led a 3-year technical roadmap with a $50M "
            "infrastructure budget. Mentored 15 senior and staff engineers. Published 4 internal "
            "papers on consensus algorithms and their production tradeoffs."
        ),
        "skills_demonstrated": ["Kafka", "Kubernetes", "distributed systems", "Python"],
    }],
}

# B7 — Chunk boundary: key achievement split across two roles
BEH_CHUNK_BOUNDARY = {
    "_id": str(uuid.uuid4()),
    "_label": "B7: Chunk boundary — migration started at co. A, finished at co. B",
    "name": "Kevin Park",
    "email": "kevin.park@example.com",
    "seniority": "senior", "total_years": 8,
    "location": "Austin, TX", "open_to_remote": True,
    "summary": (
        "Senior backend engineer who has owned end-to-end distributed systems migrations "
        "across company transitions. Strong in Kafka, Kubernetes, and Python event pipelines."
    ),
    "key_topics": ["Kafka", "Kubernetes", "Python", "distributed systems",
                   "event pipelines", "infrastructure migration", "backend engineering"],
    "experience": [
        {
            "company": "OldCo", "title": "Backend Engineer",
            "duration": "Feb 2019 - Aug 2021",
            "description": (
                "Designed and began the Kafka-based event pipeline migration, replacing a "
                "monolithic job queue that had become a reliability bottleneck at 40k events/sec. "
                "Completed the architecture design and delivered the first 8 of 20 service "
                "migrations before the company was acquired. The Kafka cluster was handling "
                "95k events/sec at handoff with full observability instrumented."
            ),
            "skills_demonstrated": ["Kafka", "Python", "distributed systems"],
        },
        {
            "company": "NewCo (acquirer)", "title": "Senior Backend Engineer",
            "duration": "Sep 2021 - Present",
            "description": (
                "Joined the acquiring company and immediately resumed the pipeline migration, "
                "completing the remaining 12 service migrations. The fully migrated system "
                "now processes 180k events/sec with 99.98% availability and zero data loss. "
                "Extended the system to support exactly-once delivery semantics for financial "
                "transactions. Led a Kubernetes rollout for the entire pipeline fleet."
            ),
            "skills_demonstrated": ["Kafka", "Kubernetes", "Python", "reliability"],
        },
    ],
}

# B8 — Aggregation: skills spread across 3 separate roles
BEH_AGGREGATION = {
    "_id": str(uuid.uuid4()),
    "_label": "B8: Aggregation — Python + Kafka + Kubernetes across 3 separate jobs",
    "name": "Isabella Torres",
    "email": "isabella.torres@example.com",
    "seniority": "senior", "total_years": 8,
    "location": "New York, NY", "open_to_remote": True,
    "summary": (
        "Backend engineer with 8 years across Python development, Kafka-based event streaming, "
        "and Kubernetes infrastructure. Each role added a distinct layer of distributed systems depth."
    ),
    "key_topics": ["Python", "Kafka", "Kubernetes", "backend engineering",
                   "event streaming", "distributed systems", "infrastructure"],
    "experience": [
        {
            "company": "PythonShop", "title": "Python Backend Engineer",
            "duration": "Jan 2017 - Dec 2019",
            "description": (
                "Built high-performance Python microservices handling 50k API requests/sec. "
                "Designed the async task processing layer using Celery and Redis. "
                "Implemented gRPC service interfaces for internal communication between 10 services. "
                "Reduced P99 API latency from 800ms to 95ms through profiling and async refactoring."
            ),
            "skills_demonstrated": ["Python", "microservices", "gRPC"],
        },
        {
            "company": "EventStreamCo", "title": "Data Engineer",
            "duration": "Jan 2020 - Dec 2021",
            "description": (
                "Designed and operated the Kafka event bus processing 120k messages/sec. "
                "Built consumer groups for 15 downstream services with guaranteed delivery semantics. "
                "Tuned Kafka producer and consumer configs to achieve 99.95% delivery reliability. "
                "Introduced schema registry to enforce event contracts across teams."
            ),
            "skills_demonstrated": ["Kafka", "event streaming", "reliability"],
        },
        {
            "company": "CloudInfra", "title": "Platform Engineer",
            "duration": "Jan 2022 - Present",
            "description": (
                "Owns the Kubernetes platform serving 40 engineering teams across 3 clusters. "
                "Designed the multi-cluster networking layer enabling cross-cluster service discovery. "
                "Reduced cluster infrastructure cost 28% through bin-packing and spot instance strategies. "
                "Implemented GitOps workflows adopted by all product teams."
            ),
            "skills_demonstrated": ["Kubernetes", "platform engineering", "infrastructure"],
        },
    ],
}

SECTION_B_RESUMES = [
    BEH_NO_KEYWORDS, BEH_HUMBLE_SENIOR, BEH_STALE_EXPERT,
    BEH_OVERQUALIFIED, BEH_CHUNK_BOUNDARY, BEH_AGGREGATION,
]

# JD for overqualification test (mid-level, explicitly scoped down)
OQ_JD = (
    "Mid-level Backend Engineer, 3-4 years experience. "
    "Build and maintain Python microservices with Kafka integration and Kubernetes deployments. "
    "Work within an established architecture — not a design/leadership role. "
    "Individual contributor focused on feature delivery and reliability."
)

VAGUE_JD = (
    "Looking for a strong engineer to join our growing team. "
    "You will work on interesting technical challenges and collaborate with smart people. "
    "We value passion, curiosity, and the ability to learn quickly."
)

SENIOR_BACKEND_JD = (
    "Senior Backend Engineer — 7+ years building distributed systems at scale. "
    "Deep expertise in event-driven architecture, Kafka, and Kubernetes. "
    "Led teams of 5+ engineers. Owned reliability for services processing 100k+ req/s. "
    "Python or Go required. Strong systems design fundamentals."
)

# All seed resumes combined (dedup by _id)
ALL_SEED_RESUMES = (
    TC1_POSITIVES + TC2_POSITIVES + TC3_POSITIVES + TC4_POSITIVES
    + SECTION_A_ADVERSARIAL + SECTION_B_RESUMES
)

# =============================================================================
# Test case data structures
# =============================================================================

@dataclass
class MetricTestCase:
    """Standard retrieval + ranking quality test."""
    id: str
    name: str
    job_description: str
    positive_ids: list
    adversarial_ids: list


@dataclass
class BehavioralTest:
    """Checks a specific system behavior rather than aggregate metrics."""
    id: str
    name: str
    description: str
    job_description: str
    check: Callable        # (ranked: list[dict], retrieval_ids: list[str]) -> (bool, str)
    expected: str          # human description of what "pass" looks like


METRIC_TEST_CASES = [
    MetricTestCase(
        id="tc1", name="Senior Backend Engineer",
        job_description=SENIOR_BACKEND_JD,
        positive_ids=[r["_id"] for r in TC1_POSITIVES],
        adversarial_ids=[ADV_VERBOSE_JUNIOR["_id"]],
    ),
    MetricTestCase(
        id="tc2", name="ML Engineer",
        job_description=(
            "ML Engineer for production ML systems. 4+ years training and deploying models. "
            "PyTorch required. Feature engineering, model evaluation, A/B testing. "
            "Build and maintain ML pipelines from data ingestion to model serving."
        ),
        positive_ids=[r["_id"] for r in TC2_POSITIVES],
        adversarial_ids=[ADV_DATA_ANALYST["_id"]],
    ),
    MetricTestCase(
        id="tc3", name="Product Manager",
        job_description=(
            "Product Manager for B2B SaaS. 5+ years PM experience. "
            "Drive product roadmap, stakeholder management, OKR setting, GTM strategy. "
            "Engineering background not required."
        ),
        positive_ids=[r["_id"] for r in TC3_POSITIVES],
        adversarial_ids=[ADV_SWE_FOR_PM["_id"]],
    ),
    MetricTestCase(
        id="tc4", name="AI Engineer (LLM fine-tuning)",
        job_description=(
            "AI Engineer — LLM fine-tuning specialist. 3+ years hands-on with LoRA, QLoRA, "
            "RLHF, and model evaluation. Hugging Face, custom training pipelines. "
            "This is not a role for API integrations or prompt engineering."
        ),
        positive_ids=[r["_id"] for r in TC4_POSITIVES],
        adversarial_ids=[ADV_LLM_API_USER["_id"]],
    ),
]


def _ranked_id(r: dict, raw_hits: list[dict]) -> Optional[str]:
    """Resolve a Claude-ranked entry back to a DB id via name match."""
    match = next((h for h in raw_hits if h["name"] == r.get("name")), None)
    return str(match["id"]) if match else None


def _rank_of(id_: str, ranked_ids: list[str]) -> Optional[int]:
    try:
        return ranked_ids.index(id_) + 1
    except ValueError:
        return None


def _flag_in(candidate_name: str, flag: str, ranked: list[dict]) -> bool:
    for r in ranked:
        if r.get("name") == candidate_name:
            return flag in (r.get("flags") or [])
    return False


def _confidence_of(candidate_name: str, ranked: list[dict]) -> Optional[str]:
    for r in ranked:
        if r.get("name") == candidate_name:
            return r.get("confidence")
    return None


BEHAVIORAL_TESTS = [
    BehavioralTest(
        id="b1", name="Keyword present, wrong context",
        description="Data analyst (Python/pandas/ETL) should not surface for ML Engineer JD.",
        job_description=(
            "ML Engineer for production ML systems. 4+ years training and deploying models. "
            "PyTorch required. Feature engineering, model evaluation, A/B testing."
        ),
        check=lambda ranked, ret_ids: (
            _rank_of(ADV_DATA_ANALYST["_id"], ret_ids) is None
            or (_rank_of(ADV_DATA_ANALYST["_id"], ret_ids) or 99) > 5,
            f"Data analyst rank in retrieval: {_rank_of(ADV_DATA_ANALYST['_id'], ret_ids) or 'absent'}",
        ),
        expected="ADV data analyst absent or ranked > 5 in retrieval",
    ),
    BehavioralTest(
        id="b2", name="Right experience, no keywords",
        description="Candidate using domain synonyms (no exact JD keywords) should still rank top-3.",
        job_description=SENIOR_BACKEND_JD,
        check=lambda ranked, ret_ids: (
            (_rank_of(BEH_NO_KEYWORDS["_id"], ret_ids) or 99) <= 5,
            f"Synonym candidate retrieval rank: {_rank_of(BEH_NO_KEYWORDS['_id'], ret_ids) or 'absent'}",
        ),
        expected="Dmitri Volkov (synonym vocabulary) retrieval rank ≤ 5",
    ),
    BehavioralTest(
        id="b3", name="Seniority confusion — humble senior > verbose junior",
        description="Wei Liu (understated 9-yr senior) should rank above Tyler Brooks (inflated junior).",
        job_description=SENIOR_BACKEND_JD,
        check=lambda ranked, ret_ids: (
            ((_rank_of(BEH_HUMBLE_SENIOR["_id"], ret_ids) or 99)
             < (_rank_of(ADV_VERBOSE_JUNIOR["_id"], ret_ids) or 0)),
            (f"Humble senior rank: {_rank_of(BEH_HUMBLE_SENIOR['_id'], ret_ids) or 'absent'} | "
             f"Verbose junior rank: {_rank_of(ADV_VERBOSE_JUNIOR['_id'], ret_ids) or 'absent'}"),
        ),
        expected="Humble senior retrieval rank < verbose junior retrieval rank",
    ),
    BehavioralTest(
        id="b4", name="Stale expertise",
        description="Hadoop/MapReduce expert (last used 2016) flagged for modern distributed systems JD.",
        job_description=SENIOR_BACKEND_JD,
        check=lambda ranked, ret_ids: (
            _flag_in(BEH_STALE_EXPERT["name"], "stale_expertise", ranked)
            or (_rank_of(BEH_STALE_EXPERT["_id"], ret_ids) or 99) > 8,
            (f"stale_expertise flag: {_flag_in(BEH_STALE_EXPERT['name'], 'stale_expertise', ranked)} | "
             f"retrieval rank: {_rank_of(BEH_STALE_EXPERT['_id'], ret_ids) or 'absent'}"),
        ),
        expected="Robert Miller flagged as stale_expertise OR ranked > 8 in retrieval",
    ),
    BehavioralTest(
        id="b5", name="Vague JD — no high-confidence results",
        description="A vague JD should not produce any high-confidence matches.",
        job_description=VAGUE_JD,
        check=lambda ranked, ret_ids: (
            all((r.get("confidence") or "low") != "high" for r in ranked),
            f"Confidence values: {[r.get('confidence') for r in ranked]}",
        ),
        expected="No ranked result has confidence='high' for a vague JD",
    ),
    BehavioralTest(
        id="b6", name="Overqualification flagged in reasoning",
        description="Staff engineer (Alexandra Hunt) for a mid-level role must carry 'overqualified' flag.",
        job_description=OQ_JD,
        check=lambda ranked, ret_ids: (
            _flag_in(BEH_OVERQUALIFIED["name"], "overqualified", ranked),
            f"overqualified flag present: {_flag_in(BEH_OVERQUALIFIED['name'], 'overqualified', ranked)}",
        ),
        expected="Alexandra Hunt has 'overqualified' in flags",
    ),
]

# =============================================================================
# DB seed / teardown
# =============================================================================

def seed_db(conn) -> list:
    inserted = []
    with conn.cursor() as cur:
        for r in ALL_SEED_RESUMES:
            rid = r["_id"]
            _store_resume(cur, rid, r)
            _store_experiences(
                cur, embedder, rid, r.get("experience", []),
                seniority=r.get("seniority", ""),
                total_years=r.get("total_years", 0),
            )
            inserted.append(rid)
    conn.commit()
    print(f"[setup] Seeded {len(inserted)} resumes.")
    return inserted


def teardown_db(conn, ids: list) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM resumes WHERE id = ANY(%s::uuid[])", (ids,))
    conn.commit()
    print(f"[teardown] Removed {len(ids)} seed resumes.")


# =============================================================================
# Metric functions — canonical signatures
# =============================================================================

def ndcg_score(ground_truth: list[str], retrieved: list[str]) -> float:
    """
    ground_truth : ordered list of relevant IDs (defines the ideal ranking)
    retrieved    : system-ranked list to score; k is implicit = len(retrieved)

    Uses binary relevance: every ID in ground_truth has gain = 1.
    IDCG places all relevant docs at the earliest positions.
    """
    relevant = set(ground_truth)
    rels = [1 if r in relevant else 0 for r in retrieved]
    dcg  = sum(rel / math.log2(i + 2) for i, rel in enumerate(rels))
    idcg = sum(1.0  / math.log2(i + 2) for i in range(min(len(relevant), len(retrieved))))
    return dcg / idcg if idcg else 0.0


def precision_at_k(retrieved: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """
    retrieved    : system-ranked list of IDs
    relevant_ids : set of known-relevant IDs
    k            : rank cutoff (default 5)
    """
    if k == 0:
        return 0.0
    return sum(1 for r in retrieved[:k] if r in relevant_ids) / k


def retrieval_recall(must_find: list[str], retrieved_ids: list[str]) -> float:
    """
    must_find     : IDs that must appear somewhere in retrieved_ids
    retrieved_ids : full retrieval result list — no k cutoff applied here;
                    pass retrieved_ids[:k] at the call site for recall@k.
    Returns the fraction of must_find items present in retrieved_ids.
    """
    if not must_find:
        return 1.0
    found = set(retrieved_ids)
    return sum(1 for m in must_find if m in found) / len(must_find)


def _mrr(ranked_ids: list[str], relevant_set: set[str]) -> float:
    for i, rid in enumerate(ranked_ids, 1):
        if rid in relevant_set:
            return 1.0 / i
    return 0.0

# =============================================================================
# Runners
# =============================================================================

def run_metric_test(tc: MetricTestCase, k: int) -> dict:
    jd_emb = embedder.encode(tc.job_description)
    conn = get_conn()
    try:
        raw_hits = vector_search(conn, jd_emb, limit=max(k * 2, 20))
    finally:
        conn.close()

    retrieval_ids = [str(h["id"]) for h in raw_hits]
    ranked        = rank_candidates(raw_hits, tc.job_description, top_n=k)
    ranking_ids   = [i for i in (_ranked_id(r, raw_hits) for r in ranked) if i]

    pos_set  = set(tc.positive_ids)
    pos_list = tc.positive_ids          # ordered ground truth for NDCG

    def _metrics(ids: list[str]) -> dict:
        return {
            "precision": precision_at_k(ids, pos_set, k=k),
            "recall":    retrieval_recall(pos_list, ids[:k]),   # recall@k
            "ndcg":      ndcg_score(pos_list, ids[:k]),
            "mrr":       _mrr(ids, pos_set),
        }

    return {
        "name":      tc.name,
        "k":         k,
        "retrieval": _metrics(retrieval_ids),
        "ranking":   _metrics(ranking_ids),
        "adversarial": [
            {
                "id":            aid,
                "retrieval_rank": _rank_of(aid, retrieval_ids),
                "ranking_rank":   _rank_of(aid, ranking_ids),
                "passed":         (_rank_of(aid, ranking_ids) is None
                                   or (_rank_of(aid, ranking_ids) or 99) > k // 2),
            }
            for aid in tc.adversarial_ids
        ],
    }


def run_behavioral_test(bt: BehavioralTest, k: int) -> dict:
    jd_emb = embedder.encode(bt.job_description)
    conn = get_conn()
    try:
        raw_hits = vector_search(conn, jd_emb, limit=max(k * 2, 20))
    finally:
        conn.close()

    retrieval_ids = [str(h["id"]) for h in raw_hits]
    ranked = rank_candidates(raw_hits, bt.job_description, top_n=k)

    passed, detail = bt.check(ranked, retrieval_ids)
    return {
        "id": bt.id,
        "name": bt.name,
        "description": bt.description,
        "expected": bt.expected,
        "passed": passed,
        "detail": detail,
    }


# =============================================================================
# Console report
# =============================================================================

def print_report(metric_results: list, behavioral_results: list) -> None:
    W = 70
    print(f"\n{'═' * W}")
    print("  EVAL REPORT — Resume-JD Matching System")
    print(f"{'═' * W}")

    if metric_results:
        print("\n  ── SECTION A: Standard Metrics ──\n")
        for res in metric_results:
            k = res["k"]
            print(f"  [{res['name']}]  (K={k})")
            print(f"  {'Metric':<22} {'Vector Search':>14} {'Claude Ranked':>14}")
            print(f"  {'─'*22} {'─'*14} {'─'*14}")
            labels = {
                "precision": f"precision_at_k(k={k})",
                "recall":    f"retrieval_recall@{k}",
                "ndcg":      f"ndcg_score@{k}",
                "mrr":       "mrr",
            }
            for m, label in labels.items():
                rv, rk = res["retrieval"][m], res["ranking"][m]
                print(f"  {label:<22} {rv:>14.3f} {rk:>14.3f}")
            for adv in res["adversarial"]:
                icon   = "✓" if adv["passed"] else "✗"
                status = "PASS" if adv["passed"] else "FAIL"
                rr = adv["retrieval_rank"] or "absent"
                fr = adv["ranking_rank"]   or "absent"
                print(f"  {icon} adversarial  retrieval={rr}  final={fr}  [{status}]")
            print()

    if behavioral_results:
        print("  ── SECTION B: Behavioral Tests ──\n")
        for res in behavioral_results:
            icon   = "✓" if res["passed"] else "✗"
            status = "PASS" if res["passed"] else "FAIL"
            print(f"  {icon} [{status}]  {res['id'].upper()}: {res['name']}")
            print(f"       expect : {res['expected']}")
            print(f"       detail : {res['detail']}")
        beh_pass = sum(1 for r in behavioral_results if r["passed"])
        print(f"\n  Behavioral: {beh_pass}/{len(behavioral_results)} passed\n")

    if metric_results:
        avgs    = {m: sum(r["ranking"][m] for r in metric_results) / len(metric_results)
                   for m in ("precision", "recall", "ndcg", "mrr")}
        adv_all = [a for r in metric_results for a in r["adversarial"]]
        adv_pass = sum(1 for a in adv_all if a["passed"])
        k = metric_results[0]["k"]
        print(f"  ── SECTION A AGGREGATE (Claude-ranked) ──")
        print(f"  precision_at_k({k}): {avgs['precision']:.3f}  "
              f"retrieval_recall: {avgs['recall']:.3f}  "
              f"ndcg_score: {avgs['ndcg']:.3f}  mrr: {avgs['mrr']:.3f}")
        print(f"  Adversarial: {adv_pass}/{len(adv_all)} passed")

    print(f"{'═' * W}\n")


# =============================================================================
# HTML report
# =============================================================================

def _metric_color(v: float) -> str:
    if v >= 0.6: return "#10b981"
    if v >= 0.35: return "#f59e0b"
    return "#ef4444"


def _bar(v: float) -> str:
    pct  = max(2, round(v * 100))
    col  = _metric_color(v)
    return (
        f'<div class="bar-wrap">'
        f'<div class="bar" style="width:{pct}%;background:{col}"></div>'
        f'<span class="bar-val">{v:.3f}</span>'
        f'</div>'
    )


def _badge(passed: bool, label: str = "") -> str:
    cls  = "badge-pass" if passed else "badge-fail"
    text = label or ("PASS" if passed else "FAIL")
    return f'<span class="badge {cls}">{text}</span>'


def generate_html_report(
    metric_results: list,
    behavioral_results: list,
    k: int,
    output_path: str = "eval_report.html",
) -> str:
    """Build a self-contained HTML evaluation report and write it to output_path."""

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Summary cards ────────────────────────────────────────────────────────
    if metric_results:
        avgs     = {m: sum(r["ranking"][m] for r in metric_results) / len(metric_results)
                    for m in ("precision", "recall", "ndcg", "mrr")}
        adv_all  = [a for r in metric_results for a in r["adversarial"]]
        adv_pass = sum(1 for a in adv_all if a["passed"])
    else:
        avgs     = {"precision": 0, "recall": 0, "ndcg": 0, "mrr": 0}
        adv_all, adv_pass = [], 0

    beh_pass  = sum(1 for r in behavioral_results if r["passed"])
    beh_total = len(behavioral_results)

    def _card(label: str, value: str, sub: str = "") -> str:
        return (
            f'<div class="card">'
            f'<div class="card-label">{label}</div>'
            f'<div class="card-value">{value}</div>'
            f'{"<div class=card-sub>" + sub + "</div>" if sub else ""}'
            f'</div>'
        )

    cards_html = "".join([
        _card(f"precision_at_k (k={k})", f"{avgs['precision']:.3f}",   "avg Claude-ranked"),
        _card("retrieval_recall",         f"{avgs['recall']:.3f}",      "avg Claude-ranked"),
        _card("ndcg_score",               f"{avgs['ndcg']:.3f}",        "avg Claude-ranked"),
        _card("mrr",                      f"{avgs['mrr']:.3f}",         "avg Claude-ranked"),
        _card("behavioral",               f"{beh_pass}/{beh_total}",    "tests passed"),
    ])

    # ── Section A ─────────────────────────────────────────────────────────────
    metric_labels = {
        "precision": f"precision_at_k(k={k})",
        "recall":    f"retrieval_recall@{k}",
        "ndcg":      f"ndcg_score@{k}",
        "mrr":       "mrr",
    }

    def _tc_card(res: dict) -> str:
        rows = ""
        for m, label in metric_labels.items():
            rv = res["retrieval"][m]
            rk = res["ranking"][m]
            rows += (
                f"<tr><td>{label}</td>"
                f"<td>{_bar(rv)}</td>"
                f"<td>{_bar(rk)}</td></tr>"
            )
        adv_rows = ""
        for adv in res["adversarial"]:
            rr = adv["retrieval_rank"] or "absent"
            fr = adv["ranking_rank"]   or "absent"
            adv_rows += (
                f'<tr class="adv-row">'
                f"<td>adversarial candidate</td>"
                f"<td>retrieval rank: <strong>{rr}</strong></td>"
                f"<td>final rank: <strong>{fr}</strong> &nbsp;{_badge(adv['passed'])}</td>"
                f"</tr>"
            )
        return (
            f'<div class="tc-card">'
            f'<div class="tc-title">{res["name"]}</div>'
            f'<table>'
            f'<thead><tr><th>Metric</th><th>Vector Search</th><th>Claude Ranked</th></tr></thead>'
            f'<tbody>{rows}{adv_rows}</tbody>'
            f'</table>'
            f'</div>'
        )

    section_a_html = "".join(_tc_card(r) for r in metric_results) if metric_results else "<p>No metric tests run.</p>"

    # ── Section B ─────────────────────────────────────────────────────────────
    def _beh_row(res: dict) -> str:
        icon  = "✓" if res["passed"] else "✗"
        cls   = "beh-pass" if res["passed"] else "beh-fail"
        return (
            f'<div class="beh-row {cls}">'
            f'<div class="beh-icon">{icon}</div>'
            f'<div class="beh-body">'
            f'<div class="beh-name">{res["id"].upper()}: {res["name"]}&nbsp;{_badge(res["passed"])}</div>'
            f'<div class="beh-desc">{res["description"]}</div>'
            f'<div class="beh-expect"><span class="beh-tag">expect</span>{res["expected"]}</div>'
            f'<div class="beh-detail"><span class="beh-tag">detail</span>{res["detail"]}</div>'
            f'</div>'
            f'</div>'
        )

    section_b_html = "".join(_beh_row(r) for r in behavioral_results) if behavioral_results else "<p>No behavioral tests run.</p>"

    # ── Full HTML ─────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Eval Report — Resume-JD Matcher</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: #f4f6f9; color: #1a1a2e; padding: 32px 20px; }}
  .wrap {{ max-width: 1060px; margin: 0 auto; }}

  /* Header */
  header {{ margin-bottom: 32px; }}
  header h1 {{ font-size: 1.6rem; font-weight: 700; }}
  header p  {{ color: #6b7280; font-size: 0.875rem; margin-top: 4px; }}

  /* Summary cards */
  .cards {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 40px; }}
  .card  {{ background: #fff; border-radius: 10px; padding: 20px 18px;
             box-shadow: 0 2px 10px rgba(0,0,0,.06); }}
  .card-label {{ font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
                  letter-spacing: .05em; color: #6b7280; }}
  .card-value {{ font-size: 1.9rem; font-weight: 700; color: #6366f1; margin-top: 4px; line-height: 1; }}
  .card-sub   {{ font-size: 0.72rem; color: #9ca3af; margin-top: 4px; }}

  /* Sections */
  .section       {{ margin-bottom: 40px; }}
  .section-title {{ font-size: 1rem; font-weight: 700; padding-bottom: 10px;
                    border-bottom: 2px solid #e5e7eb; margin-bottom: 18px; color: #374151; }}

  /* Metric test case cards */
  .tc-card  {{ background: #fff; border-radius: 10px; padding: 22px 24px; margin-bottom: 14px;
               box-shadow: 0 2px 10px rgba(0,0,0,.06); }}
  .tc-title {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 14px; }}
  table  {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th     {{ text-align: left; padding: 8px 12px; background: #f9fafb; color: #6b7280;
             font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }}
  td     {{ padding: 8px 12px; border-top: 1px solid #f0f0f0; vertical-align: middle; }}
  tr.adv-row td {{ background: #fafafa; font-size: 0.82rem; color: #6b7280; }}

  /* Bar charts */
  .bar-wrap {{ display: flex; align-items: center; gap: 8px; }}
  .bar      {{ height: 8px; border-radius: 4px; max-width: 160px; min-width: 3px; }}
  .bar-val  {{ font-size: 0.82rem; font-weight: 600; color: #374151; min-width: 36px; }}

  /* Badges */
  .badge      {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                  font-size: 0.72rem; font-weight: 700; vertical-align: middle; }}
  .badge-pass {{ background: #d1fae5; color: #065f46; }}
  .badge-fail {{ background: #fee2e2; color: #991b1b; }}

  /* Behavioral rows */
  .beh-row      {{ display: flex; gap: 14px; padding: 14px 16px; border-radius: 8px;
                    margin-bottom: 8px; border: 1px solid #e5e7eb; background: #fff; }}
  .beh-pass     {{ border-left: 3px solid #10b981; }}
  .beh-fail     {{ border-left: 3px solid #ef4444; }}
  .beh-icon     {{ font-size: 1.1rem; flex-shrink: 0; padding-top: 1px; }}
  .beh-body     {{ flex: 1; min-width: 0; }}
  .beh-name     {{ font-weight: 700; font-size: 0.9rem; margin-bottom: 3px; }}
  .beh-desc     {{ font-size: 0.82rem; color: #6b7280; margin-bottom: 6px; }}
  .beh-expect,
  .beh-detail   {{ font-size: 0.8rem; color: #374151; margin-top: 4px;
                    display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }}
  .beh-tag      {{ display: inline-block; background: #e0e7ff; color: #3730a3;
                    border-radius: 3px; padding: 1px 6px; font-size: 0.68rem;
                    font-weight: 700; text-transform: uppercase; flex-shrink: 0; }}

  @media (max-width: 700px) {{
    .cards {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>Resume-JD Matcher — Evaluation Report</h1>
    <p>Generated {ts} &nbsp;·&nbsp; K = {k}</p>
  </header>

  <div class="cards">{cards_html}</div>

  <div class="section">
    <div class="section-title">Section A — Retrieval &amp; Ranking Metrics</div>
    {section_a_html}
  </div>

  <div class="section">
    <div class="section-title">Section B — Behavioral Tests</div>
    {section_b_html}
  </div>

</div>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the resume-JD matching system.")
    parser.add_argument("--section", choices=["a", "b", "all"], default="all",
                        help="Which section to run: a=metrics, b=behavioral, all=both.")
    parser.add_argument("--no-teardown", action="store_true",
                        help="Keep seed data in DB after eval.")
    parser.add_argument("--k", type=int, default=10,
                        help="Evaluate at top-K results (default: 10).")
    parser.add_argument("--output", default="eval_report.html",
                        help="Path for the HTML report (default: eval_report.html).")
    args = parser.parse_args()

    conn = get_conn()
    inserted_ids = seed_db(conn)
    conn.close()

    metric_results, behavioral_results = [], []

    if args.section in ("a", "all"):
        print(f"\n[Section A] Running {len(METRIC_TEST_CASES)} metric test cases...")
        for i, tc in enumerate(METRIC_TEST_CASES, 1):
            print(f"  [{i}/{len(METRIC_TEST_CASES)}] {tc.name}")
            metric_results.append(run_metric_test(tc, args.k))

    if args.section in ("b", "all"):
        print(f"\n[Section B] Running {len(BEHAVIORAL_TESTS)} behavioral tests...")
        for i, bt in enumerate(BEHAVIORAL_TESTS, 1):
            print(f"  [{i}/{len(BEHAVIORAL_TESTS)}] {bt.name}")
            behavioral_results.append(run_behavioral_test(bt, args.k))

    print_report(metric_results, behavioral_results)

    out = generate_html_report(metric_results, behavioral_results, args.k, args.output)
    print(f"[html] Report saved → {out}")

    if not args.no_teardown:
        conn = get_conn()
        teardown_db(conn, inserted_ids)
        conn.close()
    else:
        print("[info] Seed data retained (--no-teardown).")


if __name__ == "__main__":
    main()
