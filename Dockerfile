FROM python:3.9-slim

WORKDIR /app

# Copiar requirements.txt e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código (incluyendo main.py y session.session)
COPY . .

EXPOSE 5000

CMD ["python", "main.py"]
