FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install Python dependencies
COPY api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared /app/shared

# Copy service code
COPY api-gateway/main.py .

# Expose service and metrics ports
EXPOSE 8000 9000

# Run the service
CMD ["python", "main.py"]
