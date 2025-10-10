FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
  && update-ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot /app/bot
COPY main-app /app/main-app

ENV PYTHONPATH=/app/main-app \
    DJANGO_SETTINGS_MODULE=config.settings

CMD ["python","-m","bot.main"]
