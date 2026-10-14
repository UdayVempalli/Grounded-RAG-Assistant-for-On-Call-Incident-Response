FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
WORKDIR /code
COPY requirements-lock.txt .
# CPU-only torch: the API embeds on CPU; the LLM runs in Ollama.
# Install torch from the CPU index FIRST - PyPI's torch wheel pulls ~3GB of CUDA libs.
RUN TORCH_VER=$(grep '^torch==' requirements-lock.txt | cut -d= -f3) && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VER}" && pip install --no-cache-dir -r requirements-lock.txt
COPY app/ ./app/
COPY data/ ./data/
COPY evals/ ./evals/
RUN useradd -m appuser && chown -R appuser:appuser /code
USER appuser
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/health", timeout=5)'
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
