FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copy requirements and install Python dependencies
COPY scraper-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared /app/shared

# Copy service code
COPY scraper-service/config.py .
COPY scraper-service/scraper.py .
COPY scraper-service/utils/ ./utils/
COPY scraper-service/main.py .

# Create directories for screenshots
RUN mkdir -p /app/screenshots

# Expose metrics port
EXPOSE 9002

# Run the service
CMD ["python", "main.py"]
