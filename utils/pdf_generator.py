"""
Modul pentru generarea de PDF-uri cu notificări pentru părinți.
"""
import os
import logging
from datetime import datetime
import weasyprint
import tempfile

logger = logging.getLogger(__name__)

def generate_notification_pdf(parent_name, student_name, parent_email, subject, content):
    """
    Generează un PDF cu notificarea pentru părinte
    
    Args:
        parent_name (str): Numele părintelui
        student_name (str): Numele elevului
        parent_email (str): Emailul părintelui (folosit pentru numele fișierului)
        subject (str): Subiectul notificării
        content (str): Conținutul HTML sau text al notificării
        
    Returns:
        tuple: (bool, str) - Succes și calea către fișierul generat
    """
    try:
        # Asigură-te că directorul există
        pdf_dir = os.path.join('static', 'notifications_pdf')
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir)
            
        # Creează un nume de fișier bazat pe timestamp și email
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_email = parent_email.replace('@', '_').replace('.', '_')
        safe_student = student_name.replace(' ', '_').replace('-', '_')
        
        filename = f"{timestamp}_{safe_student}_{safe_email}.pdf"
        pdf_path = os.path.join(pdf_dir, filename)
        
        # Generează HTML-ul pentru PDF
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{subject}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 2cm;
                    font-size: 12pt;
                }}
                .header {{
                    margin-bottom: 30px;
                    border-bottom: 1px solid #ccc;
                    padding-bottom: 10px;
                }}
                .footer {{
                    margin-top: 40px;
                    font-size: 10pt;
                    color: #666;
                    text-align: center;
                }}
                h1 {{
                    font-size: 18pt;
                    color: #333;
                }}
                .content {{
                    margin: 20px 0;
                    line-height: 1.5;
                }}
                .metadata {{
                    margin: 20px 0;
                    font-size: 10pt;
                    color: #666;
                }}
                .school-info {{
                    text-align: center;
                    font-weight: bold;
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="school-info">DIRIGINTESMART - SISTEM DE NOTIFICĂRI ȘCOLARE</div>
                <h1>{subject}</h1>
            </div>
            
            <p>Către: <strong>{parent_name}</strong></p>
            <p>Referitor la elevul: <strong>{student_name}</strong></p>
            
            <div class="content">
                {content}
            </div>
            
            <div class="metadata">
                Notificare generată la: {datetime.now().strftime('%d.%m.%Y, %H:%M')}
            </div>
            
            <div class="footer">
                Această notificare a fost generată automat de sistemul DiriginteSmart.
                <br>Pentru orice întrebări, vă rugăm contactați secretariatul școlii.
            </div>
        </body>
        </html>
        """
        
        # Creează un fișier temporar pentru HTML
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as temp_html:
            temp_html_path = temp_html.name
            temp_html.write(html_content)
        
        try:
            # Generează PDF-ul folosind WeasyPrint
            weasyprint.HTML(filename=temp_html_path).write_pdf(pdf_path)
            
            # Șterge fișierul temporar HTML
            os.unlink(temp_html_path)
            
            logger.info(f"PDF generat cu succes: {pdf_path}")
            return True, pdf_path
            
        except Exception as pdf_error:
            logger.error(f"Eroare la generarea PDF-ului: {pdf_error}")
            
            # Verifică dacă WeasyPrint a eșuat și încearcă o alternativă mai simplă
            try:
                # Salvează ca HTML dacă PDF eșuează
                html_fallback_path = os.path.join(pdf_dir, filename.replace('.pdf', '.html'))
                with open(html_fallback_path, 'w', encoding='utf-8') as html_file:
                    html_file.write(html_content)
                    
                logger.info(f"HTML salvat ca alternativă: {html_fallback_path}")
                return True, html_fallback_path
                
            except Exception as html_error:
                logger.error(f"Eroare și la salvarea HTML: {html_error}")
                return False, str(html_error)
        
    except Exception as e:
        logger.error(f"Eroare generală la generarea PDF-ului: {e}")
        return False, str(e)