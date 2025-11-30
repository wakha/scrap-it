FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copy requirements and install Python dependencies
COPY analyzer-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared /app/shared

# Copy service code
COPY analyzer-service/config.py .
COPY analyzer-service/analyzer.py .
COPY analyzer-service/main.py .

# Expose service and metrics ports
EXPOSE 8001 9001

# Run the service
CMD ["python", "main.py"]
