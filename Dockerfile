FROM python:3.11-slim

# Evitar que Python escriba archivos .pyc y habilitar salida en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Instalar dependencias esenciales de compilación y librerías C para psycopg2 y utilidades
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente de la aplicación
COPY . .

# Crear directorios para persistencia de datos y logs
RUN mkdir -p /app/data /app/logs

EXPOSE 8000

# Entrypoint por defecto: arrancar servidor web
CMD ["python", "main.py", "run-server"]
