"""
Utilități pentru conformitatea cu GDPR - Regulamentul General privind Protecția Datelor
"""
import os
import json
import csv
import io
import logging
import tempfile
from datetime import datetime
import hashlib
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)

def anonymize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Anonimizează datele personale, păstrând doar informații statistice
    
    Args:
        data: Dicționar cu datele personale
        
    Returns:
        Dicționar cu datele anonimizate
    """
    if not data:
        return {}
        
    result = {}
    
    # Pentru fiecare cheie în dicționar, determinăm dacă trebuie anonimizată
    for key, value in data.items():
        # Chei care conțin date personale direct identificabile
        personal_keys = ['name', 'email', 'parent_name', 'parent_email', 'phone', 'address']
        
        if any(personal_key in key.lower() for personal_key in personal_keys):
            # Generăm un hash pentru chei personale
            if isinstance(value, str) and value:
                result[key] = f"ANONYMIZED_{hashlib.md5(value.encode()).hexdigest()[:8]}"
            else:
                result[key] = "ANONYMIZED"
        elif isinstance(value, dict):
            # Recursiv pentru dicționare imbricate
            result[key] = anonymize_data(value)
        elif isinstance(value, list):
            # Pentru liste, anonimizăm fiecare element dacă e dicționar
            if value and isinstance(value[0], dict):
                result[key] = [anonymize_data(item) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        else:
            # Păstrăm celelalte date neschimbate (date statistice, ID-uri, timestamp-uri)
            result[key] = value
    
    return result

def export_as_json(data: Dict[str, Any]) -> Tuple[str, bytes]:
    """
    Exportă datele în format JSON
    
    Args:
        data: Dicționar cu datele de exportat
        
    Returns:
        Tuple cu numele fișierului și conținutul binar
    """
    filename = f"gdpr_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Adăugăm metadate despre export
    export_data = {
        "export_date": datetime.now().isoformat(),
        "export_type": "gdpr_data_portability",
        "data": data
    }
    
    # Convertim în JSON cu indentare pentru lizibilitate
    json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
    return filename, json_data.encode('utf-8')

def export_as_csv(data: Dict[str, Any]) -> Tuple[str, bytes]:
    """
    Exportă datele în format CSV (aplatizat)
    
    Args:
        data: Dicționar cu datele de exportat
        
    Returns:
        Tuple cu numele fișierului și conținutul binar
    """
    filename = f"gdpr_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    # Aplatizăm structura pentru CSV
    flattened_data = flatten_dict(data)
    
    # Scriem în CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Scriem headerele
    writer.writerow(["Field", "Value"])
    
    # Scriem datele
    for key, value in flattened_data.items():
        writer.writerow([key, value])
    
    return filename, output.getvalue().encode('utf-8')

def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """
    Aplatizează un dicționar ierarhic într-o structură plată pentru CSV
    
    Args:
        d: Dicționarul de aplatizat
        parent_key: Cheia părinte pentru recursia internă
        sep: Separator pentru chei compuse
        
    Returns:
        Dicționar aplatizat
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    items.extend(flatten_dict(item, f"{new_key}[{i}]", sep=sep).items())
                else:
                    items.append((f"{new_key}[{i}]", str(item)))
        else:
            items.append((new_key, str(v)))
    return dict(items)

def check_gdpr_consent() -> bool:
    """
    Verifică dacă avem consimțământul GDPR pentru procesare
    
    Returns:
        boolean: True dacă avem consimțământ, False altfel
    """
    # În implementarea completă, am verifica în baza de date sau fișier de configurare
    # Pentru acum, returnăm True (presupunem că avem consimțământ)
    gdpr_consent_path = os.path.join('static', 'gdpr_consent.json')
    
    try:
        if os.path.exists(gdpr_consent_path):
            with open(gdpr_consent_path, 'r', encoding='utf-8') as f:
                consent_data = json.load(f)
                return bool(consent_data.get('consent_storage', False))
        return False
    except Exception as e:
        logger.error(f"Eroare la verificarea consimțământului GDPR: {e}")
        return False

def save_gdpr_consent(consent_data: Dict[str, Any]) -> bool:
    """
    Salvează setările de consimțământ GDPR
    
    Args:
        consent_data: Dicționar cu setările de consimțământ
        
    Returns:
        boolean: True dacă salvarea a reușit, False altfel
    """
    try:
        static_dir = 'static'
        if not os.path.exists(static_dir):
            os.makedirs(static_dir)
            
        gdpr_consent_path = os.path.join(static_dir, 'gdpr_consent.json')
        
        # Adăugăm data actualizării
        consent_data['updated_at'] = datetime.now().isoformat()
        
        with open(gdpr_consent_path, 'w', encoding='utf-8') as f:
            json.dump(consent_data, f, indent=2, ensure_ascii=False)
            
        return True
    except Exception as e:
        logger.error(f"Eroare la salvarea consimțământului GDPR: {e}")
        return False

def load_gdpr_settings() -> Dict[str, Any]:
    """
    Încarcă setările GDPR
    
    Returns:
        Dict cu setările GDPR sau un dicționar gol dacă nu există
    """
    gdpr_consent_path = os.path.join('static', 'gdpr_consent.json')
    
    try:
        if os.path.exists(gdpr_consent_path):
            with open(gdpr_consent_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Eroare la încărcarea setărilor GDPR: {e}")
        return {}

def generate_gdpr_form_html(student, form_template: Dict[str, Any]) -> str:
    """
    Generează conținutul HTML al formularului de consimțământ GDPR personalizat pentru un părinte
    
    Args:
        student: Obiectul student cu informațiile elevului și părintelui
        form_template: Dicționar cu șablonul formularului
        
    Returns:
        String cu HTML-ul formularului personalizat
    """
    # Data curentă formatată
    current_date = datetime.now().strftime('%d.%m.%Y')
    
    # Construim HTML-ul
    html = f"""
    <!DOCTYPE html>
    <html lang="ro">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{form_template.get('title', 'Formular GDPR')}</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1, h2, h3, h4, h5, h6 {{ color: #205493; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .content {{ margin-bottom: 20px; }}
            .footer {{ margin-top: 50px; border-top: 1px solid #ddd; padding-top: 20px; }}
            .consent-options {{ margin: 30px 0; }}
            .consent-option {{ margin-bottom: 15px; padding-left: 25px; position: relative; }}
            .consent-option::before {{ content: "☐"; position: absolute; left: 0; top: 0; }}
            .signature-area {{ margin-top: 40px; display: flex; justify-content: space-between; }}
            .signature-field {{ margin-top: 10px; border-bottom: 1px solid #333; padding-bottom: 5px; }}
            .school-info {{ text-align: center; font-size: 0.9em; color: #666; margin-top: 30px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{form_template.get('title', 'Formular de consimțământ GDPR')}</h1>
            <p><strong>Data: {current_date}</strong></p>
        </div>
        
        <div class="content">
            <p><strong>Către:</strong> {student.parent_name}</p>
            <p><strong>Părinte/tutore al elevului:</strong> {student.name}, Clasa {student.class_name}</p>
            
            <h3>Notificare privind prelucrarea datelor cu caracter personal</h3>
            
            <p>{form_template.get('intro', '')}</p>
            
            <h4>Date colectate:</h4>
            <p>{form_template.get('data_collected', '')}</p>
            
            <h4>Scopul prelucrării:</h4>
            <p>{form_template.get('purpose', '')}</p>
            
            <h4>Drepturile dumneavoastră:</h4>
            <p>{form_template.get('rights', '')}</p>
            
            <h4>Contact:</h4>
            <p>{form_template.get('contact', '')}</p>
            
            <div class="consent-options">
                <h3>Opțiuni de consimțământ</h3>
                
                <div class="consent-option">
                    Sunt de acord cu prelucrarea datelor personale ale mele și ale copilului meu în aplicația DiriginteSmart în scopurile menționate mai sus.
                </div>
                
                <div class="consent-option">
                    Sunt de acord să primesc notificări prin email cu privire la situația școlară a copilului meu.
                </div>
            </div>
            
            <div class="signature-area">
                <div>
                    <p><strong>Nume părinte/tutore:</strong></p>
                    <p class="signature-field">{student.parent_name}</p>
                    <p><strong>Data:</strong></p>
                    <p class="signature-field">{current_date}</p>
                </div>
                <div>
                    <p><strong>Semnătură:</strong></p>
                    <p class="signature-field">&nbsp;</p>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Acest document servește ca informare conform cerințelor GDPR și atestă drepturile dumneavoastră în ceea ce privește datele personale.</p>
            <div class="school-info">
                <p>DiriginteSmart - Platformă de management educațional</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def generate_gdpr_form_pdf(student, form_template: Dict[str, Any], include_signature: bool = True) -> Tuple[bool, str]:
    """
    Generează un PDF cu formularul de consimțământ GDPR personalizat pentru un părinte
    
    Args:
        student: Obiectul student cu informațiile elevului și părintelui
        form_template: Dicționar cu șablonul formularului
        include_signature: Dacă includem sau nu câmp pentru semnătură (pentru versiunea printabilă)
        
    Returns:
        Tuple (boolean de succes, calea către fișierul PDF generat)
    """
    try:
        # Generăm HTML-ul formularului
        html_content = generate_gdpr_form_html(student, form_template)
        
        # Cream un director temporar pentru PDF
        temp_dir = tempfile.mkdtemp()
        pdf_filename = f"gdpr_form_{student.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        pdf_path = os.path.join(temp_dir, pdf_filename)
        
        try:
            # Încercăm să folosim WeasyPrint (mai bun pentru documente complexe)
            import weasyprint
            weasyprint.HTML(string=html_content).write_pdf(pdf_path)
        except (ImportError, Exception) as e:
            # Fallback la pdfkit
            try:
                import pdfkit
                pdfkit.from_string(html_content, pdf_path)
            except (ImportError, Exception) as e:
                logger.error(f"Eroare la generarea PDF cu pdfkit: {e}")
                return False, ""
            
        return True, pdf_path
    except Exception as e:
        logger.error(f"Eroare la generarea formularului GDPR PDF: {e}")
        return False, ""

def load_gdpr_form_template() -> Dict[str, Any]:
    """
    Încarcă șablonul formularului de consimțământ GDPR pentru părinți
    
    Returns:
        Dict cu șablonul formularului sau un dicționar cu valori implicite
    """
    template_path = os.path.join('static', 'gdpr_form_template.json')
    
    try:
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        # Returnam valori implicite dacă nu există fișierul
        return {
            'title': 'Formular de consimțământ GDPR - DiriginteSmart',
            'intro': 'Conform Regulamentului (UE) 2016/679 privind protecția persoanelor fizice în ceea ce privește prelucrarea datelor cu caracter personal și libera circulație a acestor date (GDPR), vă informăm cu privire la procesarea datelor dumneavoastră și ale copilului dumneavoastră în aplicația DiriginteSmart.',
            'data_collected': 'Aplicația DiriginteSmart colectează următoarele date personale: numele elevului, clasa, numele părintelui/tutorelui, adresa de email a părintelui/tutorelui, notele obținute la diferite materii.',
            'purpose': 'Datele sunt utilizate exclusiv pentru: administrarea situației școlare, comunicarea rezultatelor academice către părinți, generarea de rapoarte statistice anonimizate la nivel de clasă/școală.',
            'rights': 'Conform GDPR, beneficiați de următoarele drepturi: dreptul de acces la date, dreptul la rectificarea datelor, dreptul la ștergerea datelor, dreptul la restricționarea prelucrării, dreptul la portabilitatea datelor, dreptul de a vă retrage consimțământul.',
            'contact': 'Pentru orice întrebări sau solicitări legate de protecția datelor, vă rugăm să contactați responsabilul GDPR al școlii prin email sau telefon.'
        }
    except Exception as e:
        logger.error(f"Eroare la încărcarea șablonului formularului GDPR: {e}")
        return {}