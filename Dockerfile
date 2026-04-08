FROM python:3.12-slim

WORKDIR /app

# ── System deps ───────────────────────────────────────────────────────────────
# psycopg2-binary is pre-built, no libpq-dev needed.
# pdfplumber uses pdfminer.six (pure Python). No extra system deps required.

# ── Python deps ───────────────────────────────────────────────────────────────
# Install CPU-only PyTorch first so pip doesn't pull the 2 GB CUDA variant.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Embedding model ───────────────────────────────────────────────────────────
# Bake the ~90 MB model into the image so containers start instantly without
# downloading from HuggingFace at runtime.
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN adduser --disabled-password --gecos "" appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "ingest:app", "--host", "0.0.0.0", "--port", "8000"]
