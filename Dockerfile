# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Для работы matplotlib в режиме без монитора (headless) достаточно установить libgl1.
# Мы также добавим libglib2.0-0 на случай, если понадобятся другие зависимости.
# Очистка apt-get list уменьшает размер образа.
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# MATPLOTLIB_BACKEND=Agg критически важен для работы Docker-контейнеров.
# Он позволяет отрисовывать графики в память без необходимости наличия видеокарты или монитора.
ENV MATPLOTLIB_BACKEND=Agg

ENTRYPOINT ["python", "main.py"]
