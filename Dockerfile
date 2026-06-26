FROM python:3.9-slim

WORKDIR /app

# Обновляем список пакетов и устанавливаем зависимости для работы с графикой (matplotlib)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aggregator.py .

CMD ["python", "aggregator.py"]
