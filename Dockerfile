FROM python:3.11-slim

WORKDIR /app

# Dependencies first so code edits do not invalidate the layer. Every demo
# scenario changes app/ and nothing else, so this is the difference between a
# two-second rebuild and a two-minute one.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && rm -rf /root/.cache

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY openapi.yaml ./

EXPOSE 8000

# The deploy stage polls /health before running the post-deploy smoke test.
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
