FROM python:3.11-slim
WORKDIR /app
COPY migrations/ ./migrations/
COPY seed/ ./seed/
RUN pip install --no-cache-dir psycopg2-binary
CMD ["python", "seed/seed.py"]
