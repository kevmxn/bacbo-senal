FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Si tienes la sesión, copia el archivo (asegúrate de que exista)
COPY session.session .

EXPOSE 5000

CMD ["python", "main.py"]
