FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
WORKDIR /code
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY app/ ./app/
COPY data/ ./data/
COPY evals/ ./evals/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
