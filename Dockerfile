FROM python:3.13-slim

# rsync does the copying; the docker CLI lets pre-backup commands reach other containers
# (for example `docker exec my-postgres pg_dumpall`).
RUN apt-get update \
 && apt-get install -y --no-install-recommends rsync \
 && rm -rf /var/lib/apt/lists/*
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /app/
COPY tests/ /app/tests/

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
