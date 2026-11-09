# Assara: the CLI with every system tool it can call (PDF text, OCR, audio decoding, Whisper).
# Build:  docker build -t assara .
# Use:    docker run --rm -v ~/library:/library assara status
#         docker run --rm -v ~/library:/library -v ~/books:/in:ro assara add BOOK1 /in/book.pdf
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ASSARA_HOME=/library \
    HF_HOME=/cache/huggingface

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      poppler-utils ffmpeg tesseract-ocr tesseract-ocr-eng ocrmypdf ghostscript \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/assara
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[all]"

RUN useradd --create-home --uid 1000 assara \
 && mkdir -p /library /cache \
 && chown assara:assara /library /cache
USER assara
VOLUME ["/library", "/cache"]
WORKDIR /library

ENTRYPOINT ["assara"]
CMD ["--help"]
