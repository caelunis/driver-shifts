FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is reused until requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY static ./static
COPY data ./data

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# slim has no curl, so the check uses Python's standard library
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" || exit 1

# One worker: the login rate limiter lives in process memory
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
