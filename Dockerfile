FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
WORKDIR /code
ENV HF_HOME=/opt/hf-cache
COPY requirements-lock.txt .
# CPU-only torch: the API embeds on CPU; the LLM runs in Ollama.
# Install torch from the CPU index FIRST - PyPI's torch wheel pulls ~3GB of CUDA libs.
RUN TORCH_VER=$(grep '^torch==' requirements-lock.txt | cut -d= -f3) && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VER}" && pip install --no-cache-dir -r requirements-lock.txt
COPY app/ ./app/
COPY data/ ./data/
COPY evals/ ./evals/
RUN useradd -m appuser && chown -R appuser:appuser /code && mkdir -p /opt/hf-cache && chown appuser:appuser /opt/hf-cache
USER appuser
# Bake the embedding model into the image: the first /ask must not need a
# HuggingFace download (or internet). Runs as appuser into HF_HOME.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
# Models are baked into the image above: never hit the Hub at runtime,
# so there is no cold-start download and no unauthenticated Hub request.
ENV HF_HUB_OFFLINE=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/health", timeout=5)'
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
