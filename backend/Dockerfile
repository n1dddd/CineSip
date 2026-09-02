FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn aiosqlite httpx python-dotenv pydantic

COPY app/ ./app/

RUN mkdir -p /app/data
ENV DB_PATH=/app/data/cinesip.db

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]