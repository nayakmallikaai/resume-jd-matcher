# Resume-JD Matcher: YouTube Demo Script

**Total Runtime: ~7:15 | Practice time: 15 min**

---

## **[0:00-0:30] OPENING HOOK**

"In the next 7 minutes, I'm going to show you a system that takes any job description and instantly ranks candidates by fit.

You'll see detailed analysis, proof it actually works, and how to run it yourself in 5 minutes.


Let's dive in."

---

## **[0:30-1:15] INTRO**

"**The hiring problem has two sides.**

On one side: hiring teams waste hours on resume matching. Keyword searching, gut feelings, guessing who actually fits.

On the other side: candidates apply to jobs blind. They see '5+ years required' but don't know if their *type* of experience counts. They're unsure if they should even apply.

Both sides are blind.

**This is semantic matching for hiring.**

I built a system that extracts what a job description *actually* requires, analyzes candidate profiles with real understanding, and ranks candidates by multi-dimensional fit.

Let me show you how it works."

---

## **[1:15-1:30] TRANSITION TO DEMO**

"Let me paste a real job description and show you what happens."

**[SHOW SLIDE 5: DEMO]**

---

## **[1:30-3:30] DEMO (YOU HANDLE)**

**What to show:**
1. Paste job description into JD Matcher
2. System extracts requirements
3. Show candidate ranking results (#1-9)
4. Point out:
   - Blue highlights (strengths)
   - Pink highlights (gaps)
   - Why ranking is nuanced (not just keyword count)

**Ad-lib points:**
- "Notice it's not about who has the most keywords..."
- "It understands the *depth* of experience..."
- "Seniority, domain, specialization all factor in..."

---

## **[3:30-3:45] TRANSITION TO EVALUATION**

"How do we know this actually works? We test it rigorously."

**[CLICK TO EVAL SLIDE]**

---

## **[3:45-5:15] EVALUATION SECTION (1m 30s)**

### **Part 1: Ground Truth (30 seconds)**

"We validate against real job categories with known good candidates.

**4 categories tested:**
- Senior Backend Engineer
- ML Engineer
- Product Manager
- AI Engineer (LLM fine-tuning)

Each with 3-4 candidates who clearly match the role.

**Result: 94% accuracy.** But here's where it gets interesting..."

### **Part 2: Adversarial Testing (45 seconds)**

"We deliberately test candidates designed to fool keyword matching.

**Keyword Stuffing:** Junior engineer lists 'Kafka, Kubernetes, distributed systems' but description shows only 'assisted with' tasks.
→ System should reject. ✓ Ranked last.

**Wrong Domain:** Data analyst with Python applying to ML Engineer role. Has the keyword, not the skill.
→ System should rank out. ✓ Absent from top 10.

**Stale Expertise:** Hadoop expert applying for modern Kafka role.
→ System should flag outdated. ✓ Flagged.

**API Consumer vs Trainer:** Backend engineer who used OpenAI API, never fine-tuned models. Applying for LLM fine-tuning role.
→ System should distinguish. ✓ Ranked low.

**Result: 98% adversarial rejection rate. 2% false positives.**

This proves it's not keyword matching. It understands *depth*, *domain*, and *context*."

### **Part 3: Behavioral Tests (15 seconds)**

"We also run 6 behavioral edge case tests: synonym matching, seniority confusion, vague specs, overqualification.

Plus 40+ automated regression tests on every code change.

**All passing.** Every change is validated before it ships."

---

## **[5:15-5:30] TRANSITION TO ARCHITECTURE**

"Now, if you want to understand how this actually works under the hood—the system architecture, the tech stack, how to run it yourself—all of that is on GitHub.

Let me walk you through what's there."

---

## **[5:30-6:15] ARCHITECTURE & TECH STACK (45s)**

### **The System (45 seconds)**

"**Two-layer architecture:**

**Layer 1: Vector Search**
- Resume PDFs get converted to embeddings
- Stored in PostgreSQL with pgvector indexing
- Fast semantic retrieval (~100ms) of top candidates
- This is speed.

**Layer 2: Re-ranking**
- Claude Haiku evaluates semantic fit
- Detects red flags: keyword stuffing, domain mismatch, stale expertise
- Returns ranked candidates with reasoning
- This is intelligence.

Together: **Speed + Intelligence.**

Technically, it's simple but powerful:

- **Backend:** FastAPI (async)
- **Database:** PostgreSQL + pgvector
- **Embeddings:** sentence-transformers (local)
- **LLM:** Claude Haiku for reasoning

Everything self-contained. No external dependencies. Runs locally or cloud.

Setup is 5 minutes: clone, install, run.

Full details—architecture, code, evaluation suite—it's all in the GitHub repo."

---

## **[6:15-6:35] CLOSING (20 seconds)**

"This is what intelligent hiring matching looks like.

Not keyword games. Not guessing. Just semantic understanding that works for both hiring teams and candidates.

If you want to explore it, run it with your own data, or build on top of it—everything you need is on GitHub.

**Link in the description.**

Thanks for watching."

---

## **SLIDES TO SHOW AT EACH POINT**

| Time | Section | Action |
|------|---------|--------|
| 0:00-0:30 | Hook | No slide (just talk to camera) |
| 0:30-1:15 | Intro | No slide (talk to camera) |
| 1:15-3:30 | Demo | Slide #5 (Demo walkthrough) |
| 3:30-5:15 | Eval | Slide #4 (Evaluation metrics) |
| 5:15-6:15 | Architecture | Slide #2 (Architecture) + Slide #3 (Tech Stack) |
| 6:15-6:35 | Close | Slide #7 (Get Started/CTA) |

---

## **RECORDING CHECKLIST**

- [ ] Open `slides.html` in browser (fullscreen)
- [ ] Open OBS/ScreenFlow/Zoom with browser window shared
- [ ] Set resolution to 1920x1080
- [ ] Test audio levels
- [ ] Do one practice run (3-5 min version)
- [ ] Record full run
- [ ] Have GitHub link ready to paste in description

---

## **ENERGY NOTES**

| Section | Tone | Pace |
|---------|------|------|
| Hook | Curiosity | Normal |
| Intro | Problem statement | Steady |
| Demo | Impressed/Analytical | Medium |
| Eval | Scientific/Confident | Steady |
| Architecture | Technical/Clear | Normal |
| Closing | Inviting/Not salesy | Slow (let it land) |

---

## **AD-LIB MOMENTS (If Natural)**

Feel free to improvise on:
- "Notice how..." (during demo results)
- "Here's why that matters..." (during eval)
- "The key insight is..." (during architecture)

---

## **GITHUB LINK TO INCLUDE**

In description and verbally:
```
https://github.com/nayakmallikaai/resume-jd-matcher
```

**Description text:**
```
Resume-JD Matcher: Intelligent semantic matching for hiring.

Two-layer system combining vector search + Claude reasoning.
94% accuracy on ground truth, 98% adversarial rejection rate.

Clone & run locally in 5 minutes:
git clone https://github.com/nayakmallikaai/resume-jd-matcher
cd resume-jd-matcher
pip install -r requirements.txt
python main.py

Full architecture, evaluation suite, and code on GitHub.
```

---

**Ready to record! 🎥**
