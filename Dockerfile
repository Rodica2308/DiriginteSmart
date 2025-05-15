# Pasul 1: Alege o imagine Python de bază oficială
# ----- ÎNTREBARE PENTRU TINE: Ce versiune de Python folosește proiectul tău? -----
# ----- Exemplu: dacă e Python 3.11, lasă așa. Dacă e 3.9, schimbă în python:3.9-slim -----
FROM python:3.11-slim

# Pasul 2: Setează directorul de lucru în container
WORKDIR /app

# Pasul 3: Copiază fișierul de dependențe mai întâi
# Acest lucru profită de caching-ul Docker; dacă requirements.txt nu se schimbă, acest pas nu se reface.
COPY requirements.txt requirements.txt

# Pasul 4: Instalează dependențele
# --no-cache-dir reduce dimensiunea imaginii
RUN pip install --no-cache-dir -r requirements.txt

# Pasul 5: Copiază restul codului aplicației în container
COPY . .

# Pasul 6: Expune portul pe care Gunicorn va asculta
# Cloud Run va injecta o variabilă de mediu PORT, de obicei 8080.
# Gunicorn trebuie să asculte pe acest port.
EXPOSE 8080

# Pasul 7: Comanda pentru a rula aplicația
# ----- ÎNTREBARE PENTRU TINE: Instanța ta Flask 'app' este definită în 'app.py' sau 'main.py'? -----
# ----- Dacă e în 'app.py' (ex: în app.py ai 'app = Flask(__name__)'), lasă 'app:app'. -----
# ----- Dacă e în 'main.py' (ex: în main.py ai 'app = Flask(__name__)'), schimbă în 'main:app'. -----
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]