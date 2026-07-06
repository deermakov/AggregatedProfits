FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for matplotlib if needed
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Create a volume for data so we can mount the local folder
VOLUME ["/app/data"]

# We'll run the script and expect input/output to be in /app/data
CMD ["python", "main.py"]
