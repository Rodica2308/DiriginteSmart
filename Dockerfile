# Pasul 1: Alege o imagine Python de bază oficială
FROM python:3.11-slim

# Pasul 2: Setează directorul de lucru în container
WORKDIR /app

# Pasul 3: Copiază fișierul de dependențe mai întâi
COPY requirements.txt requirements.txt

# Pasul 4: Instalează dependențele
RUN pip install --no-cache-dir -r requirements.txt

# Pasul 5: Copiază restul codului aplicației în container
COPY . .

# Pasul 6: Expune portul pe care Gunicorn va asculta
EXPOSE 8080

# Pasul 7: Comanda pentru a rula aplicația
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--log-level", "debug", "app:app"]