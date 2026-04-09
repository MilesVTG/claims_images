FROM python:3.12-slim

WORKDIR /project

RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install API dependencies
COPY api/requirements.txt /project/api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Install test dependencies
RUN pip install --no-cache-dir pytest

# Copy full project structure for test runner
COPY api/ /project/api/
COPY worker/ /project/worker/
COPY tests/ /project/tests/
COPY pytest.ini /project/pytest.ini

WORKDIR /project/api

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
