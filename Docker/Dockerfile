# Base image for Python
FROM python:3.9

# Set the working directory
WORKDIR /app

# Install required system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /app/files/extracted /app/reports /app/src

# Install requests
RUN pip install requests

RUN pip install elasticsearch

# Copy requirements first to leverage Docker cache
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Copy source code
COPY src/ /app/src/

# Run the application
CMD ["python", "src/dmarc_analyzer.py"]