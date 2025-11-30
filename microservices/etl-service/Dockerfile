FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for MySQL client
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY etl-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared /app/shared

# Copy service code
COPY etl-service/config.py .
COPY etl-service/constants.py .
COPY etl-service/etl.py .
COPY etl-service/database/ ./database/
COPY etl-service/main.py .

# Expose metrics port
EXPOSE 9003

# Run the service
CMD ["python", "main.py"]
