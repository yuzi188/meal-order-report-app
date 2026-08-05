FROM python:3.11-slim

WORKDIR /app

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "order_app_server.py"]
