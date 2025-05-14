"""
Modul pentru trimiterea de notificări prin webhook-uri
Integrare cu servicii precum Pipedream, Make.com, etc.
"""

import os
import json
import logging
import requests
import base64
from datetime import datetime

# Configurare logging
logger = logging.getLogger(__name__)

def send_through_webhook(to_email, subject, content, from_email=None, attachment_path=None):
    """
    Trimite date prin webhook pentru a fi procesate extern și transformate în email
    
    Args:
        to_email (str): Adresa de email a destinatarului
        subject (str): Subiectul emailului 
        content (str): Conținutul emailului (HTML sau text)
        from_email (str, optional): Adresa expeditorului (poate fi ignorată de webhook)
        attachment_path (str, optional): Calea către fișierul atașament
        
    Returns:
        bool: True dacă datele au fost trimise cu succes, False altfel
    """
    try:
        # Obține URL-ul webhook-ului din variabilele de mediu
        webhook_url = os.environ.get('EMAIL_WEBHOOK_URL')
        
        if not webhook_url:
            logger.error("EMAIL_WEBHOOK_URL nu este configurat în variabilele de mediu")
            return False
            
        logger.info(f"Se trimit date prin webhook către {webhook_url[:30]}...")
        
        # Pregătire date pentru webhook
        payload = {
            "to_email": to_email,
            "subject": subject,
            "content": content,
            "from_email": from_email or os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@dirigintesmart.ro'),
            "sent_at": datetime.now().isoformat(),
            "app_name": "DiriginteSmart"
        }
        
        # Adaugă atașament dacă există
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, 'rb') as f:
                    file_content = f.read()
                    file_name = os.path.basename(attachment_path)
                    encoded_file = base64.b64encode(file_content).decode('utf-8')
                    
                    payload["attachment"] = {
                        "filename": file_name,
                        "content": encoded_file,
                        "content_type": "application/pdf"
                    }
                    
                    logger.info(f"Atașament adăugat în webhook: {file_name}")
            except Exception as attach_error:
                logger.error(f"Eroare la adăugarea atașamentului în webhook: {attach_error}")
        
        # Trimite cererea POST către webhook
        response = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload)
        )
        
        # Verifică răspunsul
        if response.status_code in [200, 201, 202]:
            logger.info(f"Date trimise cu succes către webhook. Răspuns: {response.status_code}")
            
            # Salvează în log pentru referință
            with open('sent_emails.log', 'a', encoding='utf-8') as log:
                log.write(f"[{datetime.now().isoformat()}] Email către {to_email}: {subject}\n")
                
            return True
        else:
            logger.error(f"Eroare webhook: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Eroare la trimiterea prin webhook: {e}")
        return False