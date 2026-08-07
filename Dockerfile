FROM python:3.11-slim

WORKDIR /app

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "order_bootstrap_v2.py"]
