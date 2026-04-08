# Resume JD Matcher — 2–3 Minute Demo Guide

---

## 📋 Topic Outline

| Section | Time | Key Points |
|---------|------|-----------|
| **Problem** | 0:15 | Recruiters drown in resumes; keyword search fails at nuance |
| **Solution** | 0:30 | Two-layer matching: vector search + Claude re-ranking |
| **Ingest** | 0:45 | PDF → Claude extracts profile + experience → embedded & stored |
| **Search #1** | 1:30 | Senior Backend: strong matches, overqualified flag, keyword stuffer caught |
| **Search #2** | 2:15 | LLM fine-tuning: API user filtered out, real expertise surfaces |
| **Search #3** | 2:45 | Vague JD: honest uncertainty, no false high-confidence |
| **Eval Suite** | 3:15 | Behavioral tests prove system isn't just lucky |
| **Close** | 3:30 | Two-layer, intelligent, tested |

---

## 🎬 Full Script (Word-for-Word)

**[OPEN — 0:00]**

"Imagine you're hiring a senior backend engineer. You get 200 applications. Most recruiting tools rank them by keyword overlap — whoever mentioned Kafka the most, wins. That's not recruiting, that's Ctrl+F.

This tool does something smarter: two-layer matching. First, semantic vector search finds candidates with relevant experience. Then Claude re-ranks them with judgment — looking at depth, seniority fit, and flags like overqualification. The result is a ranking that thinks like a recruiter, not a search engine."

---

**[INGEST — 0:30]**

"Step one: ingest. I'm dropping a PDF resume."

*(drag and drop PDF onto upload UI)*

"In about two seconds, Claude reads the document and extracts structure: profile, seniority, summary, and each work experience as a separate chunk. Each chunk gets a semantic embedding. So when I search later, I'm not matching against a flat document — I'm matching against *this person's actual career*."

*(show the JSON response with extracted profile)*

"Key insight: the system knows this person is a senior engineer with 9 years in distributed systems. It's not just that they mentioned Kafka once."

---

**[SEARCH #1: Senior Backend — 1:00]**

"Now I search for a senior backend engineer. Seven-plus years. Distributed systems, Kafka, Kubernetes. Led teams."

*(paste JD, hit search)*

"Top three are all genuinely senior engineers with scale. Read the reason on the first one: *'Owned event-processing backbone serving 200,000 events per second, led six-engineer team through zero-downtime migration.'* That's a judgment, not a keyword count.

Now look at Alexandra Hunt. Fifteen years, staff engineer, architect. She matches on every technical dimension."

*(scroll to Alexandra, show overqualified flag)*

"But she has a flag: **overqualified**. The system tells the recruiter: *this person exists, but think twice — she'll outgrow the role.*

And here's Tyler Brooks."

*(scroll to bottom)*

"Junior developer. His resume says Kafka, Kubernetes, distributed systems, microservices — literally every word in the job description. He's dead last.

Why? Because when you read what he actually *did*, he wrote YAML files under supervision. The system sees through keyword stuffing. Depth matters."

---

**[SEARCH #2: LLM Fine-tuning — 1:45]**

"Different role. AI engineer specializing in LLM fine-tuning. LoRA, QLoRA, RLHF. And I explicitly said: *this is not a role for API integrations.*"

*(clear, paste LLM JD, search)*

"Top results fine-tuned Llama and Mistral, built RLHF pipelines, ran model evaluations. High confidence.

Priya Patel is not here. She's a solid backend engineer who integrated OpenAI and Anthropic APIs via LangChain. She works with LLMs, but she never trained one. Both people touch LLMs. Only one is qualified.

The system knows the difference."

---

**[SEARCH #3: Vague JD — 2:15]**

"Last search. I'm deliberately giving it bad input."

*(read slowly)* "'Looking for a strong engineer to join our growing team. You will work on interesting technical challenges and collaborate with smart people. We value passion, curiosity, and the ability to learn quickly.'"

*(hit search)*

"Results come back. But look at every confidence score: medium, medium, low, low. Not a single high.

The system won't manufacture certainty it doesn't have. Most AI tools are confidently wrong. This one tells you when it doesn't know."

---

**[EVAL SUITE — 2:45]**

"Everything I showed you is tested."

*(show terminal output or screenshot of eval results)*

"The eval suite runs two sections. Section A measures retrieval quality — Precision, Recall, NDCG, MRR — against known ground-truth candidates across four job types.

Section B runs eight behavioral tests for failure modes:"

*(read test names as they pass)*

"Does keyword stuffing get penalised? Pass. Does a candidate using synonyms instead of exact keywords still surface? Pass. Does a staff engineer for a mid-level role get flagged as overqualified? Pass. Does a vague JD avoid high-confidence results? Pass.

These aren't vibes. They're assertions you can run after every change."

---

**[CLOSE — 3:15]**

"Two-layer matching: semantic retrieval finds candidates, Claude re-ranks with reasoning, confidence, and flags. Built on FastAPI, PostgreSQL with pgvector embeddings, and Claude Haiku."

"Why it matters: recruiters waste time on keyword games and false confidence. This system surfaces real depth and flags red flags early."

---

## 🔍 Demo Use-Case JDs

Copy and paste these into the search UI during the demo.

### JD #1: Senior Backend Engineer *(strong matches + overqualified flag)*

```
Senior Backend Engineer - 7+ years building distributed systems at scale. 
Deep expertise in event-driven architecture, Kafka, and Kubernetes. 
Led teams of 5+ engineers. Owned reliability for services processing 100k+ req/s. 
Python or Go required. Strong systems design fundamentals.
```

**Watch for:**
- Top 3 are all genuinely senior (Elena Vasquez, Jordan Kim, Marcus Osei)
- Alexandra Hunt (staff/15 yrs) shows with `overqualified` flag
- Tyler Brooks (verbose junior) ranks last or absent

---

### JD #2: ML Engineer *(smart filtering)*

```
ML Engineer for production ML systems. 4+ years training and deploying models. 
PyTorch required. Feature engineering, model evaluation, A/B testing. 
Build and maintain ML pipelines from data ingestion to model serving.
```

**Watch for:**
- Aria Zhang, Omar Hassan, Nina Rodriguez surface (real ML training)
- Sarah Chen (Python data analyst, no model training) stays out despite having Python

---

### JD #3: AI Engineer — LLM Fine-tuning *(domain precision)*

```
AI Engineer - LLM fine-tuning specialist. 3+ years hands-on with LoRA, QLoRA, 
RLHF, and model evaluation. Hugging Face, custom training pipelines. 
This is not a role for API integrations or prompt engineering.
```

**Watch for:**
- Yuki Tanaka and Carlos Vega surface (actual fine-tuning work)
- Priya Patel (API integrations only) is filtered out
- Shows nuance: both "work with LLMs," only one qualifies

---

### JD #4: Mid-level Backend *(overqualification + seniority nuance)*

```
Mid-level Backend Engineer, 3-4 years experience. 
Build and maintain Python microservices with Kafka integration and Kubernetes deployments. 
Work within an established architecture — not a design/leadership role. 
Individual contributor focused on feature delivery and reliability.
```

**Watch for:**
- Alexandra Hunt (staff engineer) gets `overqualified` flag
- Shows the system gives recruiters actionable signals (risk of person leaving)

---

### JD #5: Vague JD *(honest uncertainty)*

```
Looking for a strong engineer to join our growing team. 
You will work on interesting technical challenges and collaborate with smart people. 
We value passion, curiosity, and the ability to learn quickly.
```

**Watch for:**
- All results come back with `confidence: medium` or `confidence: low`
- Zero high-confidence matches
- Punchline: "The system is honest about uncertainty instead of confident BS."

---

## 📊 Eval Suite Talking Points

Run: `python eval.py`

### What it tests

| Section | What | How |
|---------|------|-----|
| **A** | Retrieval quality | Precision@K, Recall, NDCG, MRR on 4 JD categories with known good candidates |
| **B** | Behavior in edge cases | 8 scenarios: keyword stuffing, synonyms, stale skills, vague JDs, overqualification, split projects, skill aggregation |

### Key Assertions (from Section B)

When discussing eval results, highlight these:

1. **Keyword stuffing caught**: Verbose junior with all keywords ranks below humble senior with depth
   - *"Depth beats density."*

2. **Synonyms work**: Candidate using "event streaming" instead of "Kafka" still surfaces
   - *"Semantic matching, not keyword matching."*

3. **Stale expertise flagged**: Hadoop expert (last used 2016) gets `stale_expertise` flag for modern JD
   - *"The system tracks recency."*

4. **Vague JDs get low confidence**: No high-confidence results for buzzword JD
   - *"Honest uncertainty, not false confidence."*

5. **Overqualification caught**: Staff engineer for mid-level role flagged
   - *"Protects against wrong-fit hires."*

6. **Chunk boundaries don't break it**: Candidate whose achievement spans two jobs still surfaces
   - *"Understands career continuity."*

7. **Skills aggregation works**: Candidate with Python + Kafka + Kubernetes spread across 3 roles still found
   - *"Sees the full picture, not just individual bullets."*

8. **Adversarial candidates defeated**: 4/4 adversarial cases properly handled
   - *"Robust against gaming."*

### Sample Output to Show

```
── SECTION B: Behavioral Tests ──
✓ [PASS]  B1: Keyword present, wrong context
✓ [PASS]  B2: Right experience, no keywords
✓ [PASS]  B3: Seniority confusion — humble senior > verbose junior
✓ [PASS]  B4: Stale expertise
✓ [PASS]  B5: Vague JD — no high-confidence results
✓ [PASS]  B6: Overqualification flagged
✓ [PASS]  B7: Chunk boundary — split-project candidate surfaces
✓ [PASS]  B8: Aggregation — distributed skills surface correctly

Behavioral: 8/8 passed ✓

── SECTION A: Standard Metrics ──
Precision@10: 0.85
Recall: 0.92
NDCG: 0.88
MRR: 0.95
```

### What to Say

"This isn't a cherry-picked demo. Every run, the system validates itself against these tests. If you tweak the ranking logic, these assertions catch regressions immediately. That's how you know a tool isn't just lucky on demo day."

---

## 🚀 How to Run the Demo

### Setup
```bash
cd /Users/mallikanayak/AI_WORK/resume-jd-matcher
source .venv/bin/activate
uvicorn ingest:app --reload
# In another terminal:
# Navigate to http://localhost:8000
```

### Demo Flow (3 minutes)
1. **[0:30]** Show ingest UI, upload a PDF
2. **[1:30]** Search JD #1 (Senior Backend) — show overqualified flag + keyword stuffer caught
3. **[2:15]** Search JD #3 (LLM fine-tuning) — show API user filtered out
4. **[2:45]** Search JD #5 (Vague) — show no high-confidence results
5. **[3:15]** Quickly show eval output on terminal or screenshot

### Optional (if time allows)
- Search JD #4 (mid-level) to show overqualification in action
- Run `python eval.py` live and show tests passing in real-time

---

## 💡 Key Messages to Reinforce

| Moment | Message |
|--------|---------|
| Ingest | "Vector embeddings capture meaning, not just words." |
| Overqualified | "Recruiters waste time on people who'll leave in 6 months. Flag it early." |
| Keyword stuffer | "Depth beats density. The system reads descriptions, not just titles." |
| LLM fine-tuning | "This is the nuance that kills keyword search. Both people work with LLMs. Only one trained a model." |
| Vague JD | "Garbage in, honest uncertainty out — not garbage in, confident garbage out." |
| Eval suite | "Most AI demos are cherry-picked. The eval suite proves the system isn't just lucky." |

---

## 🎯 Talkathon Version (if you need 5+ minutes)

Expand by:
- Walk through the database schema (PostgreSQL + pgvector)
- Show the ranking prompt in detail — how it instructs Claude
- Run eval.py live, explain each test as it passes
- Demo the `/ingest` endpoint with file upload flow
- Show the API response structure
- Discuss the embedding model choice (all-MiniLM-L6-v2)

---

