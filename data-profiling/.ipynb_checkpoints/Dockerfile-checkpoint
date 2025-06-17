# Use official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc

# Copy files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose Cloud Run's expected port
EXPOSE 8080

# Start FastAPI server on the correct port
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
