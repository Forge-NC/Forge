FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps — headless Forge (no GUI, no audio, no Tkinter)
RUN pip install --no-cache-dir \
    runpod \
    requests \
    cryptography \
    numpy \
    tiktoken

# Copy Forge package (headless subset — no GUI, no audio)
COPY forge/ /app/forge/
COPY pyproject.toml /app/

# Copy handler
COPY runpod/handler.py /app/handler.py

# Entry point
CMD ["python", "-u", "handler.py"]
