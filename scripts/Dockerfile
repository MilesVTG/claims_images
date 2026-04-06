FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    sqlalchemy \
    pg8000 \
    bcrypt \
    cloud-sql-python-connector[pg8000]

COPY seed.py .
COPY schema.sql .

CMD ["python3", "seed.py"]
