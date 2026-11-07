FROM python:3.12-slim
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py stream_worker.py hls_worker.py ./
CMD ["sh", "-c", "python hls_worker.py & exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8765}"]
