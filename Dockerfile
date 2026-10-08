FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY src ./src
COPY static ./static
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1 WEB_HOST=0.0.0.0

RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
USER app
EXPOSE 8000
CMD ["python", "main.py"]
