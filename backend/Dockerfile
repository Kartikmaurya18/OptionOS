# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Deployed backend always runs on Linux (this image), where uvloop is a
# real dependency -- unlike the Windows dev machine this was built on,
# there's no platform marker to skip here.
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runs as a non-root user -- if this container is ever compromised, the
# attacker doesn't get root inside it for free.
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

EXPOSE 8000

# --loop auto picks up uvloop automatically since it's installed (see
# requirements.txt's platform marker note) -- no explicit --loop flag needed.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
