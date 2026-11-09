# Una imagen para el ingestor, la API y los 4 contenedores de dispositivos.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY static ./static
CMD ["python", "ingestor.py"]
