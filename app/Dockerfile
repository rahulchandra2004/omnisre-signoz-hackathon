FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Install opentelemetry auto-instrumentation packages
RUN pip install "setuptools<70"
RUN opentelemetry-bootstrap -a install

COPY buggy_service.py .

EXPOSE 8000

# Run uvicorn wrapped with opentelemetry-instrument
CMD ["opentelemetry-instrument", "uvicorn", "buggy_service:app", "--host", "0.0.0.0", "--port", "8000"]
