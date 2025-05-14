import logging
import os
import base64
import json
import requests
from datetime import datetime
# Importurile dinamice sunt realizate în funcțiile specifice pentru a evita probleme

logger = logging.getLogger(__name__)

def send_email_notification(email_user, smtp_server, smtp_port, recipient, subject, body, email_password=None, attachment_path=None):
    """
    Trimite o notificare prin email către un părinte
    
    Args:
        email_user (str): Adresa de email a expeditorului
        smtp_server (str): Ignorat - păstrat pentru compatibilitate
        smtp_port (int): Ignorat - păstrat pentru compatibilitate
        recipient (str): Adresa de email a destinatarului
        subject (str): Subiectul emailului
        body (str): Conținutul emailului
        email_password (str, optional): Ignorat - păstrat pentru compatibilitate
        attachment_path (str, optional): Calea către un fișier de atașat
    
    Returns:
        bool: True dacă emailul a fost trimis cu succes, False altfel
    """
    # Salvează în fișierul sent_emails.log pentru referință
    save_email_to_log(email_user, recipient, subject, body)
    
    # ETAPA 1: Verificăm dacă avem un webhook configurat și încercăm să trimitem prin acesta
    webhook_url = os.environ.get('EMAIL_WEBHOOK_URL')
    if webhook_url:
        logger.info(f"Se încearcă trimiterea prin webhook către {recipient}")
        webhook_result = send_through_webhook(
            to_email=recipient,
            subject=subject,
            content=body,
            from_email=email_user,
            attachment_path=attachment_path
        )
        
        if webhook_result:
            logger.info(f"Email trimis cu succes prin webhook către {recipient}")
            return True
        else:
            logger.warning("Webhook-ul nu a funcționat. Se încearcă alte metode.")
    
    # ETAPA 2: Încercăm SendGrid (poate fi blocat pe Replit)
    sendgrid_key = os.environ.get('SENDGRID_API_KEY')
    if sendgrid_key:
        logger.info(f"Se trimite email prin SendGrid API către {recipient}")
        sendgrid_result = send_with_sendgrid(
            from_email=email_user,
            to_email=recipient,
            subject=subject,
            text_content=body,
            attachment_path=attachment_path
        )
        
        if sendgrid_result:
            logger.info(f"Email trimis cu succes prin SendGrid către {recipient}")
            return True
        else:
            logger.warning("SendGrid API nu a funcționat. Se încearcă alte metode.")
    
    # ETAPA 3: Încercăm Brevo API (poate fi blocat pe Replit)
    brevo_key = os.environ.get('BREVO_API_KEY')
    if brevo_key:
        logger.info(f"Se trimite email prin Brevo API către {recipient}")
        brevo_result = send_with_brevo(
            from_email=email_user,
            to_email=recipient,
            subject=subject,
            text_content=body,
            attachment_path=attachment_path
        )
        
        if brevo_result:
            logger.info(f"Email trimis cu succes prin Brevo către {recipient}")
            return True
        else:
            logger.warning("Brevo API nu a funcționat. Verificați BREVO_API_KEY în variabilele de mediu.")
        
    # ETAPA 4: Generăm PDF local pentru backup
    logger.info("Se generează PDF pentru backup manual...")
    from utils.pdf_generator import generate_notification_pdf
    
    try:
        # Generăm numele destinatarului și expeditorului din email
        parent_name = recipient.split('@')[0].replace('.', ' ').title()
        student_name = "Elev"  # În contextul real, acest nume ar trebui extras din date
        
        # Generăm PDF-ul
        success, pdf_path = generate_notification_pdf(
            parent_name=parent_name,
            student_name=student_name,
            parent_email=recipient,
            subject=subject,
            content=body
        )
        
        if success:
            logger.info(f"S-a generat un PDF de backup: {pdf_path}")
        else:
            logger.error("Eroare la generarea PDF-ului")
            
        return False  # Returnăm False pentru a indica că emailul electronic nu a fost trimis
            
    except Exception as e:
        logger.error(f"Eroare la generarea PDF-ului: {e}")
        return False

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
        # Adăugăm loguri detaliate pentru depanare
        logging.basicConfig(level=logging.INFO)
        
        # Obține URL-ul webhook-ului din variabilele de mediu
        webhook_url = os.environ.get('EMAIL_WEBHOOK_URL')
        
        if not webhook_url:
            logger.error("EMAIL_WEBHOOK_URL nu este configurat în variabilele de mediu")
            print("EMAIL_WEBHOOK_URL lipsește din variabilele de mediu!")
            return False
            
        print(f"DEBUG: Se trimit date prin webhook către {webhook_url[:30]}...")
        logger.info(f"Se trimit date prin webhook către {webhook_url[:30]}...")
        
        # Pregătire date pentru webhook - format mai simplu pentru compatibilitate maximă
        payload = {
            "to": to_email,
            "subject": subject,
            "body": content,
            "from": from_email or os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@dirigintesmart.ro')
        }
        
        # Adaugă atașament dacă există (opțional)
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, 'rb') as f:
                    file_content = f.read()
                    file_name = os.path.basename(attachment_path)
                    encoded_file = base64.b64encode(file_content).decode('utf-8')
                    
                    # Format mai simplu pentru atașament
                    payload["attachment_name"] = file_name
                    payload["attachment_content"] = encoded_file
                    payload["attachment_type"] = "application/pdf"
                    
                    print(f"DEBUG: Atașament adăugat în webhook: {file_name}")
                    logger.info(f"Atașament adăugat în webhook: {file_name}")
            except Exception as attach_error:
                print(f"DEBUG: Eroare la adăugarea atașamentului în webhook: {attach_error}")
                logger.error(f"Eroare la adăugarea atașamentului în webhook: {attach_error}")
        
        # Înregistrăm datele trimise (fără conținut sensibil)
        print(f"DEBUG: Trimitem datele: to={to_email}, subject={subject}, webhook={webhook_url[:30]}")
        
        try:
            # Trimite cererea POST către webhook
            response = requests.post(
                webhook_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=10  # Timeout de 10 secunde
            )
            
            # Verifică răspunsul
            print(f"DEBUG: Răspuns webhook: {response.status_code}")
            logger.info(f"Răspuns webhook: {response.status_code}")
            
            if response.status_code in [200, 201, 202]:
                print(f"DEBUG: Date trimise cu succes către webhook. Răspuns: {response.status_code}")
                logger.info(f"Date trimise cu succes către webhook. Răspuns: {response.status_code}")
                
                # Salvează în log pentru referință
                with open('sent_emails.log', 'a', encoding='utf-8') as log:
                    log.write(f"[{datetime.now().isoformat()}] Email către {to_email} (webhook): {subject}\n")
                    
                return True
            else:
                print(f"DEBUG: Eroare webhook: {response.status_code} - {response.text}")
                logger.error(f"Eroare webhook: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as req_error:
            print(f"DEBUG: Eroare la conectarea la webhook: {req_error}")
            logger.error(f"Eroare la conectarea la webhook: {req_error}")
            return False
            
    except Exception as e:
        print(f"DEBUG: Eroare globală la trimiterea prin webhook: {e}")
        logger.error(f"Eroare la trimiterea prin webhook: {e}")
        return False

def send_with_sendgrid(from_email, to_email, subject, text_content=None, html_content=None, attachment_path=None):
    """
    Trimite email folosind API-ul SendGrid
    
    Args:
        from_email (str): Email expeditor
        to_email (str): Email destinatar
        subject (str): Subiect email
        text_content (str, optional): Conținut text simplu
        html_content (str, optional): Conținut HTML (opțional)
        attachment_path (str, optional): Calea către un fișier atașament
        
    Returns:
        bool: True dacă emailul a fost trimis cu succes, False altfel
    """
    try:
        # Verificăm dacă avem un API key configurat
        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        logger.info(f"Verificare cheie SendGrid API. Cheia există: {bool(sendgrid_api_key)}")
        logger.info(f"Lungimea cheii API: {len(sendgrid_api_key) if sendgrid_api_key else 0} caractere")
        
        if not sendgrid_api_key:
            logger.error("SENDGRID_API_KEY nu este configurată în variabilele de mediu")
            return False

        # Importăm aici pentru a evita erorile de import
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId

        # Pregătim mesajul
        content = html_content if html_content else text_content
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=content if html_content else None,
            plain_text_content=text_content if not html_content else None
        )
        
        # Adăugăm atașament dacă există
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, 'rb') as f:
                    file_content = f.read()
                    file_name = os.path.basename(attachment_path)
                    encoded_file = base64.b64encode(file_content).decode()
                    
                    attachment = Attachment()
                    attachment.file_content = FileContent(encoded_file)
                    attachment.file_name = FileName(file_name)
                    attachment.file_type = FileType('application/pdf')
                    attachment.disposition = Disposition('attachment')
                    attachment.content_id = ContentId('PDF Notification')
                    
                    message.attachment = attachment
                    logger.info(f"Atașament adăugat în SendGrid: {file_name}")
            except Exception as attach_error:
                logger.error(f"Eroare la adăugarea atașamentului în SendGrid: {attach_error}")
        
        # Trimite emailul
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        
        # Verificăm răspunsul
        if response.status_code in [200, 201, 202]:
            logger.info(f"Email trimis cu succes prin SendGrid API: {response.status_code}")
            return True
        else:
            logger.error(f"Eroare SendGrid API: {response.status_code} - {response.body}")
            return False
        
    except Exception as e:
        logger.error(f"Eroare SendGrid API: {e}")
        # Verificăm dacă este o eroare de autentificare
        if "401" in str(e) or "unauthorized" in str(e).lower() or "invalid" in str(e).lower():
            logger.error("EROARE: API Key SendGrid invalid sau expirat!")
            logger.error("Verificați și actualizați SENDGRID_API_KEY în variabilele de mediu din Replit")
        return False


# Alias pentru compatibilitate cu codul existent
send_with_brevo = send_with_sendgrid

# Această funcție a fost eliminată întrucât utilizăm exclusiv Brevo API


def save_email_to_log(from_email, to_email, subject, text_content):
    """
    Salvează conținutul emailului în fișierul de log pentru referință
    
    Args:
        from_email (str): Email expeditor
        to_email (str): Email destinatar
        subject (str): Subiect email
        text_content (str): Conținut email
    """
    try:
        formatted_message = f"""
----- NOTIFICARE EMAIL -----
De la: {from_email}
Către: {to_email}
Subiect: {subject}
----- CONȚINUT -----
{text_content}
----- SFÂRȘIT CONȚINUT -----
        """
        
        logger.info(f"Trimitere email: {from_email} -> {to_email}")
        logger.info(f"Subiect: {subject}")
        logger.info(formatted_message)
        
        with open('sent_emails.log', 'a', encoding='utf-8') as log_file:
            log_file.write(f"\n{'-' * 50}\n")
            log_file.write(f"TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(formatted_message)
            log_file.write(f"\n{'-' * 50}\n")
    except Exception as log_error:
        logger.error(f"Nu s-a putut scrie în fișierul de log: {log_error}")
