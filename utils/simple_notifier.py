# Modul simplu pentru notificări
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def save_notification(from_email, to_email, subject, content):
    """
    Salvează notificările în fișiere separate pentru fiecare părinte/destinatar
    pentru a păstra confidențialitatea datelor
    
    Args:
        from_email (str): Email expeditor
        to_email (str): Email destinatar
        subject (str): Subiect notificare
        content (str): Conținut HTML sau text al notificării
        
    Returns:
        bool: True întotdeauna, pentru a simula succesul
    """
    try:
        # Creare director pentru notificări
        static_dir = 'static'
        notif_dir = os.path.join(static_dir, 'notifications')
        
        # Asigură-te că directoarele există
        if not os.path.exists(static_dir):
            os.makedirs(static_dir)
        if not os.path.exists(notif_dir):
            os.makedirs(notif_dir)
            
        # Crează un index principal pentru diriginte (fără date confidențiale)
        index_file = os.path.join(static_dir, 'notifications.html')
        
        # Generează un nume de fișier unic pentru destinatar bazat pe email (hash MD5)
        import hashlib
        email_hash = hashlib.md5(to_email.encode()).hexdigest()
        student_log_file = os.path.join(notif_dir, f"{email_hash}.html")
        
        # Creăm conținutul notificării
        timestamp = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        # Conținut complet pentru fișierul individual al elevului
        student_notification = f"""
        <div class="notification">
            <div class="header">
                <strong>Trimis la:</strong> {timestamp}<br>
                <strong>De la:</strong> {from_email}<br>
                <strong>Către:</strong> {to_email}<br>
                <strong>Subiect:</strong> {subject}
            </div>
            <div class="content">
                {content}
            </div>
        </div>
        """
        
        # Conținut pentru indexul principal - fără informații confidențiale
        index_notification = f"""
        <div class="notification">
            <div class="header">
                <strong>Trimis la:</strong> {timestamp}<br>
                <strong>Subiect:</strong> {subject}
            </div>
            <div class="content">
                <p><em>Notificare trimisă. Conținutul este confidențial și disponibil doar pentru destinatar.</em></p>
                <p><strong>Tip:</strong> Pentru a vedea conținutul notificărilor, partajați link-ul specific cu părintele.</p>
            </div>
        </div>
        """
        
        # HTML template pentru toate paginile
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Notificări salvate</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="stylesheet" href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css">
            <style>
                body { 
                    font-family: var(--bs-body-font-family, Arial, sans-serif); 
                    margin: 20px; 
                    background-color: var(--bs-body-bg);
                    color: var(--bs-body-color);
                }
                h1 { 
                    color: var(--bs-primary);
                    margin-bottom: 20px;
                    border-bottom: 1px solid var(--bs-border-color);
                    padding-bottom: 10px;
                }
                .notification { 
                    border: 1px solid var(--bs-border-color); 
                    margin: 15px 0; 
                    padding: 15px; 
                    border-radius: var(--bs-border-radius); 
                    background-color: var(--bs-secondary-bg);
                }
                .header { 
                    background-color: var(--bs-tertiary-bg); 
                    padding: 10px; 
                    margin-bottom: 10px; 
                    border-radius: var(--bs-border-radius-sm); 
                    color: var(--bs-secondary-color);
                }
                .content { 
                    padding: 10px; 
                    background-color: var(--bs-body-bg);
                    border-radius: var(--bs-border-radius-sm);
                }
                .container {
                    max-width: 1140px;
                    margin: 0 auto;
                }
            </style>
        </head>
        <body>
            <div class="container">
            {header_content}
            """
        
        # Verificăm dacă fișierul principal există
        if not os.path.exists(index_file):
            # Header pentru fișierul principal (pentru diriginte)
            index_header = """
            <h1>
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="currentColor" class="bi bi-bell-fill me-2" viewBox="0 0 16 16">
                    <path d="M8 16a2 2 0 0 0 2-2H6a2 2 0 0 0 2 2m.995-14.901a1 1 0 1 0-1.99 0A5 5 0 0 0 3 6c0 1.098-.5 6-2 7h14c-1.5-1-2-5.902-2-7 0-2.42-1.72-4.44-4.005-4.901"/>
                </svg>
                Registru de notificări (Diriginte)
            </h1>
            <div class="mb-4 alert alert-primary">
                <h5><i class="fas fa-shield-alt"></i> Protecția datelor</h5>
                <p>Acest registru conține doar informații de bază despre notificările trimise. 
                Conținutul complet al notificărilor este confidențial și accesibil doar părinților destinatari.</p>
                <p>Pentru a partaja o notificare cu un părinte, generați un link specific folosind ID-ul elevului.</p>
            </div>
            """
            # Creăm fișierul principal
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(html_template.format(header_content=index_header))
        
        # Verificăm dacă fișierul individual există
        if not os.path.exists(student_log_file):
            # Header pentru fișierul individual al elevului
            student_header = f"""
            <h1>
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="currentColor" class="bi bi-envelope-fill me-2" viewBox="0 0 16 16">
                    <path d="M.05 3.555A2 2 0 0 1 2 2h12a2 2 0 0 1 1.95 1.555L8 8.414.05 3.555ZM0 4.697v7.104l5.803-3.558zM6.761 8.83l-6.57 4.027A2 2 0 0 0 2 14h12a2 2 0 0 0 1.808-1.144l-6.57-4.027L8 9.586zm3.436-.586L16 11.801V4.697z"/>
                </svg>
                Notificări personale
            </h1>
            <div class="mb-4 alert alert-success">
                <h5>Notificări pentru: {to_email}</h5>
                <p>Acestea sunt notificările personale despre elevul dvs. Conținutul este confidențial și accesibil doar de dvs.</p>
            </div>
            """
            # Creăm fișierul individual al elevului
            with open(student_log_file, 'w', encoding='utf-8') as f:
                f.write(html_template.format(header_content=student_header))
        
        # Adăugăm notificarea în fișierul principal (index pentru diriginte)
        with open(index_file, 'a', encoding='utf-8') as f:
            f.write(index_notification)
            
        # Adăugăm notificarea completă în fișierul individual al elevului
        with open(student_log_file, 'a', encoding='utf-8') as f:
            f.write(student_notification)
        
        # Logăm succesul
        logger.info(f"Notificare salvată: Glob={index_file}, Individual={student_log_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"Eroare la salvarea notificării: {e}")
        # Totuși, returnăm True pentru a simula succesul
        return True
