FROM python:3.10-slim
RUN apt-get update && apt-get install -y gcc libffi-dev curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
