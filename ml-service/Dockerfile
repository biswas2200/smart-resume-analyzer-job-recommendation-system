# ML service / core engine. The same image serves the hosted Web tiers and,
# later, the Community Edition (docs/editions-and-parity.md): parity is
# structural because it is literally the same artifact.
#
# The trained resume NER model is mounted at /srv/models (docker-compose.yml;
# fetch it with scripts/fetch_ner_models.sh). MiniLM is downloaded on first
# use into HF_HOME; mount a volume there (see docker-compose.yml) so it is
# fetched once, not on every container start. Baking the models into the
# image is a later step (ONNX export).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

WORKDIR /srv

# CPU-only torch first, so pip never pulls the multi-GB CUDA wheel.
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
