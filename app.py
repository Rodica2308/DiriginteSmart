import os
import io
import csv
import time
import json
import logging
import datetime
import tempfile
import hashlib
from typing import Dict, List, Optional, Any
from functools import wraps

import xlsxwriter
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate

from utils.email_sender import send_email_notification
from utils.csv_processor import process_csv_data, calculate_average
from utils.simple_notifier import save_notification
from utils.pdf_generator import generate_notification_pdf
from utils.gdpr_utils import (
    check_gdpr_consent, save_gdpr_consent, load_gdpr_settings, anonymize_data, 
    export_as_json, export_as_csv, load_gdpr_form_template, 
    generate_gdpr_form_html, generate_gdpr_form_pdf
)

# Configurare logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Declarare bază de date
class Base(DeclarativeBase):
    pass

# Inițializare aplicație
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # necesar pentru url_for pentru a genera cu https

# Configurare bază de date
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Inițializare bază de date
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Inițializare migrării (dacă va fi necesar în viitor)
migrate = Migrate(app, db)

# Importăm modelele după inițializarea db
from models import Student, Subject, Grade, Reminder

# Creăm baza de date și adăugăm materii inițiale
with app.app_context():
    db.create_all()
    
    # Adăugăm materii default
    try:
        # Verificăm dacă există deja materii
        if Subject.query.count() == 0:
            default_subjects = [
                # Materii principale
                "Matematică", "Română", "Istorie", "Geografie", "Fizică", 
                "Chimie", "Biologie", "Informatică", "Engleză", "Franceză",
                # Materii suplimentare
                "Educație Fizică", "Educație Muzicală", "Educație Plastică", 
                "Educație Civică", "Psihologie", "Economie", "Filosofie", 
                "Tehnologie", "Religie", "Logică"
            ]
            
            for subject_name in default_subjects:
                subject = Subject(name=subject_name)
                db.session.add(subject)
            
            db.session.commit()
            logger.info(f"Added {len(default_subjects)} default subjects")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding default subjects: {str(e)}")

# Funcție helper pentru a obține elevii grupați după clasă
def get_students_by_class():
    """Funcție utilitară pentru a obține elevii grupați după clasă pentru bara de navigare"""
    # Obține toți elevii pentru bara de navigare
    students = Student.query.order_by(Student.class_name, Student.name).all()
    
    # Grupare după clasă pentru bara de navigare
    students_by_class = {}
    for student in students:
        if student.class_name not in students_by_class:
            students_by_class[student.class_name] = []
        students_by_class[student.class_name].append(student)
    
    return students, students_by_class

# Adăugăm direct elevii și gruparea după clase în render_template

# Funcția pentru verificarea reminderelor active
def check_active_reminders():
    """Verifică dacă există remindere active care trebuie afișate"""
    now = datetime.datetime.now()
    active_reminders = Reminder.query.filter_by(active=True).all()
    due_reminders = [r for r in active_reminders if r.is_due]
    
    # Actualizăm timpul ultimei declanșări pentru reminder-urile active
    for reminder in due_reminders:
        reminder.last_triggered = now
        db.session.commit()
        
    return due_reminders

@app.route('/')
def index():
    now = datetime.datetime.now()
    students, students_by_class = get_students_by_class()
    
    # Verifică dacă există remindere active
    active_reminders = check_active_reminders()
    
    return render_template('index.html', 
                          now=now,
                          students=students,
                          students_by_class=students_by_class,
                          active_reminders=active_reminders)
    
# Ruta pentru adăugarea notelor individuale a fost eliminată și înlocuită cu ruta pentru note multiple

@app.route('/add-multiple-grades', methods=['GET', 'POST'])
def add_multiple_grades():
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        subject_id = request.form.get('subject_id')
        values = request.form.getlist('values[]')
        dates = request.form.getlist('dates[]')
        
        # Validarea datelor
        if not student_id or not subject_id:
            flash('Selectați un elev și o materie', 'danger')
            return redirect(url_for('add_multiple_grades'))
        
        # Verifică dacă există elev și materie
        student = Student.query.get(student_id)
        subject = Subject.query.get(subject_id)
        
        if not student or not subject:
            flash('Elevul sau materia selectată nu există', 'danger')
            return redirect(url_for('add_multiple_grades'))
        
        # Contorizare note adăugate cu succes
        success_count = 0
        
        # Iterăm prin note și le adăugăm
        for i in range(len(values)):
            # Verificăm că avem valoare pentru această notă
            if not values[i]:
                continue
            
            try:
                # Convertește și validează valoarea notei
                value = float(values[i])
                if value < 1 or value > 10:
                    continue  # Sărim peste notele invalide
                
                # Convertește data string la obiect date
                date_obj = datetime.datetime.strptime(dates[i], '%Y-%m-%d').date()
                
                # Creează și salvează nota
                grade = Grade(value=value, date=date_obj, student_id=student_id, subject_id=subject_id)
                db.session.add(grade)
                success_count += 1
                
            except ValueError:
                continue  # Sărim peste valorile invalide
            except Exception as e:
                logger.error(f"Eroare la adăugarea notei: {str(e)}")
                db.session.rollback()
                flash(f'Eroare la adăugarea notelor: {str(e)}', 'danger')
                return redirect(url_for('add_multiple_grades'))
        
        # Commit la baza de date
        if success_count > 0:
            db.session.commit()
            flash(f'Au fost adăugate {success_count} note pentru {student.name} la {subject.name}', 'success')
        else:
            flash('Nu a fost adăugată nicio notă validă', 'warning')
        
        return redirect(url_for('add_multiple_grades'))
    
    # Pentru metoda GET
    now = datetime.datetime.now()
    students, students_by_class = get_students_by_class()
    subjects = Subject.query.order_by(Subject.name).all()
    
    return render_template('add_multiple_grades.html', 
                           now=now, 
                           students=students, 
                           students_by_class=students_by_class,
                           subjects=subjects)

@app.route('/view-grades')
def view_grades():
    now = datetime.datetime.now()
    
    # Obține parametrii de filtrare
    student_id = request.args.get('student_id')
    subject_id = request.args.get('subject_id')
    
    # Obține toți studenții și materiile pentru filtre
    students, students_by_class = get_students_by_class()
    subjects = Subject.query.order_by(Subject.name).all()
    
    # Inițializează lista de elevi cu note
    students_with_grades = []
    
    # Procesează elevii vizibili (conform filtrelor)
    query_students = students
    if student_id:
        query_students = [s for s in students if str(s.id) == student_id]
    
    # Pentru fiecare elev vizibil, calculăm notele și mediile
    for student in query_students:
        # Inițializează datele elevului
        student_data = {
            'id': student.id,
            'name': student.name,
            'class_name': student.class_name,
            'subjects': [],
            'overall_average': 0.0
        }
        
        # Obține toate materiile cu note sau toate materiile dacă există filtru
        subject_query = Subject.query
        if subject_id:
            subject_query = subject_query.filter(Subject.id == subject_id)
        
        available_subjects = subject_query.order_by(Subject.name).all()
        
        # Construiește lista de materii cu note pentru elev
        total_average = 0.0
        subjects_with_grades = 0
        
        for subject in available_subjects:
            # Obține notele elevului la această materie
            grade_query = Grade.query.filter_by(
                student_id=student.id,
                subject_id=subject.id
            ).order_by(Grade.date.desc())
            
            grades = grade_query.all()
            
            # Dacă există note sau dacă este un filtru pe materie, adaugă materia
            if grades or subject_id:
                grade_values = [float(g.value) for g in grades]
                average = round(sum(grade_values) / len(grade_values), 2) if grade_values else 0
                
                # Adaugă la media generală
                if grade_values:
                    total_average += average
                    subjects_with_grades += 1
                
                # Adaugă materia la lista elevului
                student_data['subjects'].append({
                    'id': subject.id,
                    'name': subject.name,
                    'grades': grades,
                    'average': average if grade_values else None,
                    'count': len(grade_values)
                })
        
        # Calculează media generală a elevului
        if subjects_with_grades > 0:
            student_data['overall_average'] = round(total_average / subjects_with_grades, 2)
        
        # Adaugă elevul la lista finală
        if student_data['subjects'] or not subject_id:
            students_with_grades.append(student_data)
    
    # Sortează elevii după clasă și nume
    students_with_grades.sort(key=lambda x: (x['class_name'], x['name']))
    
    return render_template(
        'view_grades.html',
        now=now,
        students=students,
        students_by_class=students_by_class,
        subjects=subjects,
        filtered_student_id=student_id,
        filtered_subject_id=subject_id,
        students_with_grades=students_with_grades
    )

@app.route('/manage-students')
def manage_students():
    now = datetime.datetime.now()
    students, students_by_class = get_students_by_class()
    
    # Obține toate clasele pentru filtrare
    class_names = list(students_by_class.keys())
    
    return render_template('manage_students.html', 
                           now=now, 
                           students=students, 
                           students_by_class=students_by_class,
                           class_names=class_names)

@app.route('/add-student', methods=['POST'])
def add_student():
    name = request.form.get('name')
    class_name = request.form.get('class_name')
    parent_name = request.form.get('parent_name')
    parent_email = request.form.get('parent_email')
    
    if not all([name, class_name, parent_name, parent_email]):
        flash('Toate câmpurile sunt obligatorii', 'danger')
        return redirect(url_for('add_grades_form'))
    
    # Creare student nou
    student = Student(name=name, class_name=class_name, 
                     parent_name=parent_name, parent_email=parent_email)
    
    db.session.add(student)
    db.session.commit()
    
    flash(f'Elevul {name} a fost adăugat cu succes', 'success')
    return redirect(url_for('add_grades_form'))

@app.route('/add-student-from-manage', methods=['POST'])
def add_student_from_manage():
    name = request.form.get('name')
    class_name = request.form.get('class_name')
    parent_name = request.form.get('parent_name')
    parent_email = request.form.get('parent_email')
    
    if not all([name, class_name, parent_name, parent_email]):
        flash('Toate câmpurile sunt obligatorii', 'danger')
        return redirect(url_for('manage_students'))
    
    # Creare student nou
    student = Student(name=name, class_name=class_name, 
                     parent_name=parent_name, parent_email=parent_email)
    
    db.session.add(student)
    db.session.commit()
    
    flash(f'Elevul {name} a fost adăugat cu succes', 'success')
    return redirect(url_for('manage_students'))

@app.route('/edit-student/<int:student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        class_name = request.form.get('class_name')
        parent_name = request.form.get('parent_name')
        parent_email = request.form.get('parent_email')
        
        if not all([name, class_name, parent_name, parent_email]):
            flash('Toate câmpurile sunt obligatorii', 'danger')
            return redirect(url_for('edit_student', student_id=student_id))
        
        # Actualizare student
        student.name = name
        student.class_name = class_name
        student.parent_name = parent_name
        student.parent_email = parent_email
        
        db.session.commit()
        
        flash(f'Datele elevului {name} au fost actualizate cu succes', 'success')
        return redirect(url_for('manage_students'))
    
    # GET request - render form
    now = datetime.datetime.now()
    students, students_by_class = get_students_by_class()
    
    return render_template('edit_student.html', 
                           now=now, 
                           student=student,
                           students=students,
                           students_by_class=students_by_class)

@app.route('/delete-student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    
    # Verifică dacă elevul are note asociate
    if len(student.grades) > 0:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Nu se poate șterge elevul deoarece are note asociate'
            })
        flash('Nu se poate șterge elevul deoarece are note asociate', 'danger')
        return redirect(url_for('manage_students'))
    
    try:
        name = student.name  # Salvăm numele înainte de ștergere
        db.session.delete(student)
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Elevul {name} a fost șters cu succes'
            })
        
        flash(f'Elevul {name} a fost șters cu succes', 'success')
        
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Eroare la ștergerea elevului: {str(e)}'
            })
        
        flash(f'Eroare la ștergerea elevului: {str(e)}', 'danger')
    
    return redirect(url_for('manage_students'))

@app.route('/manage-subjects')
def manage_subjects():
    now = datetime.datetime.now()
    subjects = Subject.query.order_by(Subject.name).all()
    return render_template('manage_subjects.html', now=now, subjects=subjects)

@app.route('/add-subject', methods=['POST'])
def add_subject():
    name = request.form.get('name')
    
    # Verifică dacă numele materiei există deja
    existing_subject = Subject.query.filter_by(name=name).first()
    if existing_subject:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Această materie există deja'
            })
        else:
            flash('Această materie există deja', 'warning')
            return redirect(url_for('manage_subjects'))
    
    # Verifică limita de 20 de materii
    if Subject.query.count() >= 20:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Numărul maxim de materii (20) a fost atins'
            })
        else:
            flash('Numărul maxim de materii (20) a fost atins', 'warning')
            return redirect(url_for('manage_subjects'))
    
    # Adaugă materia nouă
    new_subject = Subject(name=name)
    db.session.add(new_subject)
    db.session.commit()
    
    # Răspuns pentru cereri AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'subject': {
                'id': new_subject.id,
                'name': new_subject.name
            }
        })
    
    flash(f'Materia {name} a fost adăugată cu succes', 'success')
    
    # Redirect în funcție de pagina de unde a venit cererea
    referer = request.headers.get('Referer', '')
    if '/add-grades' in referer:
        return redirect(url_for('add_grades_form'))
    else:
        return redirect(url_for('manage_subjects'))

@app.route('/edit-subject/<int:subject_id>', methods=['POST'])
def edit_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    new_name = request.form.get('name')
    
    # Verifică dacă numele nou există deja la o altă materie
    existing_subject = Subject.query.filter(Subject.name == new_name, Subject.id != subject_id).first()
    if existing_subject:
        flash('Există deja o materie cu acest nume', 'warning')
        return redirect(url_for('manage_subjects'))
    
    # Actualizează materia
    subject.name = new_name
    db.session.commit()
    
    flash(f'Materia a fost actualizată cu succes', 'success')
    return redirect(url_for('manage_subjects'))

@app.route('/delete-subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    
    # Verifică dacă materia are note asociate
    if len(subject.grades) > 0:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Nu se poate șterge materia deoarece are note asociate'
            })
        flash('Nu se poate șterge materia deoarece are note asociate', 'danger')
        return redirect(url_for('manage_subjects'))
    
    try:
        db.session.delete(subject)
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Materia a fost ștearsă cu succes'
            })
        
        flash('Materia a fost ștearsă cu succes', 'success')
        
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Eroare la ștergerea materiei: {str(e)}'
            })
        
        flash(f'Eroare la ștergerea materiei: {str(e)}', 'danger')
    
    return redirect(url_for('manage_subjects'))

# Ruta pentru adăugarea unei singure note a fost eliminată și înlocuită cu funcționalitatea de note multiple

@app.route('/edit-grade/<int:grade_id>', methods=['GET', 'POST'])
def edit_grade(grade_id):
    # Obține nota care va fi editată
    grade = Grade.query.get_or_404(grade_id)
    
    if request.method == 'POST':
        # Obține noile valori pentru notă
        value = request.form.get('value')
        date_str = request.form.get('date')
        subject_id = request.form.get('subject_id')
        
        # Validare
        if not value or not date_str or not subject_id:
            flash('Toate câmpurile sunt obligatorii', 'danger')
            return redirect(url_for('edit_grade', grade_id=grade_id))
        
        try:
            # Convertește și validează valoarea notei
            value = float(value)
            if value < 1 or value > 10:
                flash('Nota trebuie să fie între 1 și 10', 'danger')
                return redirect(url_for('edit_grade', grade_id=grade_id))
                
            # Convertește și validează data
            date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Verifică dacă materia există
            subject = Subject.query.get(subject_id)
            if not subject:
                flash('Materia selectată nu există', 'danger')
                return redirect(url_for('edit_grade', grade_id=grade_id))
            
            # Actualizează nota
            grade.value = value
            grade.date = date_obj
            grade.subject_id = subject_id
            
            db.session.commit()
            
            flash('Nota a fost actualizată cu succes', 'success')
            return redirect(url_for('view_grades'))
            
        except ValueError as e:
            flash(f'Eroare la convertirea valorilor: {str(e)}', 'danger')
            return redirect(url_for('edit_grade', grade_id=grade_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la actualizarea notei: {str(e)}', 'danger')
            return redirect(url_for('edit_grade', grade_id=grade_id))
    
    # Metoda GET - afișează formularul de editare
    now = datetime.datetime.now()
    subjects = Subject.query.all()
    
    return render_template('edit_grade.html', 
                          now=now, 
                          grade=grade, 
                          subjects=subjects)

@app.route('/delete-grade/<int:grade_id>', methods=['POST'])
def delete_grade(grade_id):
    grade = Grade.query.get_or_404(grade_id)
    
    try:
        db.session.delete(grade)
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Nota a fost ștearsă cu succes'
            })
        
        flash('Nota a fost ștearsă cu succes', 'success')
        
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Eroare la ștergerea notei: {str(e)}'
            })
        
        flash(f'Eroare la ștergerea notei: {str(e)}', 'danger')
    
    return redirect(url_for('view_grades'))
    
@app.route('/send-notifications-page')
def send_notifications_page():
    now = datetime.datetime.now()
    
    # Obține lista cu toți elevii
    students = Student.query.order_by(Student.class_name, Student.name).all()
    
    # Obține lista cu toate clasele unice
    class_names = sorted(list(set([s.class_name for s in students])))
    
    # Verifică dacă există un ID de elev specificat în query params
    selected_student_id = request.args.get('student_id')
    
    return render_template('send_notifications.html', 
                           now=now, 
                           students=students,
                           class_names=class_names,
                           selected_student=selected_student_id)

@app.route('/send-notifications', methods=['POST'])
def send_notifications():
    now = datetime.datetime.now()
    
    # Obține parametrii de formular
    email_user = request.form.get('email_user', '')
    email_password = request.form.get('email_password', '').replace(' ', '')  # Eliminăm spațiile din parolă
    smtp_server = request.form.get('smtp_server', 'smtp.gmail.com')
    smtp_port = int(request.form.get('smtp_port', 587))
    
    # Obținem conținutul și subiectul notificării
    subject = request.form.get('subject', 'Notificare privind situația școlară')
    content = request.form.get('content', '')
    include_grades = 'include_grades' in request.form
    include_gdpr = 'include_gdpr' in request.form
    
    # Obține lista de ID-uri de elevi selectate
    student_ids = request.form.getlist('student_ids[]')
    
    # Stochează setările de email pentru refolosire (NU stocăm parola în sesiune din motive de securitate)
    session['email_user'] = email_user
    session['smtp_server'] = smtp_server
    session['smtp_port'] = smtp_port
    
    # Setează temporar parola de email ca variabilă de mediu pentru această cerere
    if email_password.strip():
        os.environ['EMAIL_PASS'] = email_password
    
    # Email validation
    if not email_user:
        flash('Adresa de email a expeditorului este obligatorie', 'danger')
        return redirect(url_for('send_notifications_page'))
    
    # Verifică dacă au fost selectați elevi
    if not student_ids:
        flash('Vă rugăm să selectați cel puțin un elev pentru a trimite notificări.', 'warning')
        return redirect(url_for('send_notifications_page'))
    
    # Obține elevii selectați
    students = Student.query.filter(Student.id.in_(student_ids)).all()
    
    # Organizează elevii după email-ul părintelui
    parent_data = {}
    
    for student in students:
        # Verifică dacă elevul are email părinte și note
        if not student.parent_email or not student.parent_email.strip():
            continue
        
        parent_email = student.parent_email.strip()
        
        # Inițializează datele pentru acest părinte dacă nu există deja
        if parent_email not in parent_data:
            parent_data[parent_email] = {
                'name': student.parent_name,
                'students': [],
                'all_grades': []
            }
        
        # Inițializează informațiile elevului
        student_info = {
            'id': student.id,
            'name': student.name,
            'class_name': student.class_name,
            'grades': [],
            'subject_averages': [],
            'overall_average': 0.0
        }
        
        # Procesează notele și calculează mediile
        if student.grades:
            # Organizează notele după materie
            subject_grades = {}
            
            for grade in student.grades:
                subject_name = grade.subject.name
                
                # Adaugă nota la lista de note pentru această materie
                if subject_name not in subject_grades:
                    subject_grades[subject_name] = []
                
                subject_grades[subject_name].append(grade.value)
                
                # Adaugă nota la lista de note a elevului
                student_info['grades'].append({
                    'value': grade.value,
                    'date': grade.date,
                    'subject': subject_name
                })
                
                # Adaugă nota și la lista generală pentru email
                grade_text = f"{student.name} (Clasa {student.class_name}) - {subject_name}: {grade.value} din {grade.date.strftime('%d-%m-%Y')}"
                parent_data[parent_email]['all_grades'].append(grade_text)
            
            # Calculează mediile pe materii
            overall_sum = 0.0
            subject_count = 0
            
            for subject_name, grades in subject_grades.items():
                if grades:
                    # Calculează media pentru această materie
                    avg = sum(grades) / len(grades)
                    
                    # Adaugă media la lista de medii pe materii
                    student_info['subject_averages'].append({
                        'subject': subject_name,
                        'average': avg,
                        'count': len(grades)
                    })
                    
                    # Adaugă media și la lista generală pentru email
                    avg_text = f"{student.name} (Clasa {student.class_name}) - Media la {subject_name}: {avg:.2f}"
                    if 'averages' not in parent_data[parent_email]:
                        parent_data[parent_email]['averages'] = []
                    parent_data[parent_email]['averages'].append(avg_text)
                    
                    # Adaugă la suma generală
                    overall_sum += avg
                    subject_count += 1
            
            # Calculează media generală (ca medie a mediilor pe materii, nu ca medie a tuturor notelor)
            if subject_count > 0:
                student_info['overall_average'] = overall_sum / subject_count  # overall_sum conține suma mediilor pe materii și subject_count numărul de materii
                
                # Adaugă media generală la lista pentru email
                overall_avg_text = f"{student.name} (Clasa {student.class_name}) - Media generală: {student_info['overall_average']:.2f}"
                parent_data[parent_email]['averages'].append(overall_avg_text)
        
        # Adaugă informațiile elevului la lista de elevi pentru acest părinte
        parent_data[parent_email]['students'].append(student_info)
    
    # Inițializează rezultatele
    results = {
        'success': 0,
        'failed': 0,
        'total': len(parent_data),
        'emails_sent': 0,  # Adăugăm contor pentru emailuri trimise cu succes
        'details': []
    }
    
    # Trimite emailuri pentru fiecare părinte
    for parent_email, info in parent_data.items():
        try:
            parent_name = info['name']
            students_info = info['students']
            
            # Verifică dacă există note pentru a trimite email
            if not any(student['grades'] for student in students_info):
                continue
            
            # Construiește subiectul emailului
            if len(students_info) == 1:
                subject = f"DiriginteSmart - Note Școlare - {students_info[0]['name']}"
            else:
                subject = f"DiriginteSmart - Note Școlare - {len(students_info)} elevi"
            
            # Folosim conținutul furnizat de utilizator
            custom_content = content
            
            # Personalizăm conținutul cu numele părintelui
            body = custom_content.replace("Stimat părinte", f"Stimat părinte {parent_name}")
            
            # Adăugăm secțiunea cu note, dacă este solicitată
            if include_grades and 'all_grades' in info and info['all_grades']:
                body += "\n\n**NOTE NOI ȘI RECENTE:**\n"
                body += "\n".join(info['all_grades'])
                
                # Adaugă și mediile dacă există
                if 'averages' in info and info['averages']:
                    body += "\n\nInformații privind mediile școlare:\n"
                    body += "\n".join(info['averages'])
            
            # Adăugăm notificarea GDPR dacă este activată
            if include_gdpr:
                body += "\n\n---------------------------------------------"
                body += "\nNOTĂ PRIVIND PROTECȚIA DATELOR (GDPR):"
                body += "\nDatele personale sunt procesate conform Regulamentului (UE) 2016/679 privind protecția persoanelor fizice."
                body += "\nAveți dreptul de acces, rectificare, ștergere, restricționare și portabilitate a datelor."
                body += "\nPentru mai multe informații sau pentru a vă exercita drepturile, contactați școala."
                body += "\n---------------------------------------------"
            
            # Adaugă un footer
            body += "\n\nAceastă notificare a fost generată automat de sistemul DiriginteSmart."
            body += "\nVă rugăm să nu răspundeți la acest email."
            body += "\n\nCu stimă,"
            body += "\nConducerea Școlii"
            
            # Trimite și salvează notificarea
            try:
                # Debug pentru a vedea detalii în logs
                logger.info(f"Salvare notificare pentru {parent_email}...")
                
                # Formatăm conținutul pentru HTML
                html_content = body.replace('\n', '<br>')
                
                # 1. Salvăm notificarea în fișier local (va fi mereu disponibilă)
                notification_saved = save_notification(
                    from_email=email_user,
                    to_email=parent_email,
                    subject=subject,
                    content=html_content
                )
                
                # 2. Generăm PDF pentru printare sau distribuție
                # Obținem numele elevului (primul elev dacă sunt mai mulți)
                student_name = students_info[0]['name'] if students_info else "Elev"
                
                pdf_success, pdf_path = generate_notification_pdf(
                    parent_name=parent_name,
                    student_name=student_name,
                    parent_email=parent_email,
                    subject=subject,
                    content=html_content
                )
                
                # 3. Încearcă să trimită și prin email (opțional, nu depinde de rezultat)
                # Folosim HTML pentru o formatare mai bună
                html_body = body.replace('\n', '<br>')
                
                # Adăugăm mesaje de debug
                print(f"DEBUG: Trimitem email către {parent_email}, subiect: {subject}")
                print(f"DEBUG: Email webhook URL configurat: {bool(os.environ.get('EMAIL_WEBHOOK_URL'))}")
                
                email_success = send_email_notification(
                    email_user=email_user,
                    smtp_server=smtp_server,
                    smtp_port=smtp_port,
                    recipient=parent_email,
                    subject=subject,
                    body=html_body,
                    email_password=email_password,  # Transmitem direct parola introdusă de utilizator
                    attachment_path=pdf_path if pdf_success else None
                )
                
                # Debug pentru rezultat
                print(f"DEBUG: Rezultat trimitere email: {email_success}")
                
                # Înregistrează rezultatul (notificarea se consideră trimisă dacă a fost salvată local sau ca PDF)
                results['success'] += 1
                
                status_parts = []
                if notification_saved:
                    status_parts.append('Notificare salvată')
                
                if pdf_success:
                    pdf_filename = os.path.basename(pdf_path)
                    status_parts.append(f'PDF generat (<a href="/static/notifications_pdf/{pdf_filename}" target="_blank">Deschide</a>)')
                    
                if email_success:
                    status_parts.append('Email trimis')
                    results['emails_sent'] += 1  # Incrementăm contorul de emailuri trimise
                else:
                    status_parts.append('Email indisponibil')
                
                status_mesaj = ' | '.join(status_parts)
                
                logger.info(f"Notificare: Local={notification_saved}, PDF={pdf_success}, Email={email_success}")
                
            except Exception as send_error:
                logger.error(f"Eroare la procesarea notificării: {send_error}")
                results['failed'] += 1
                status_mesaj = f'Eroare notificare: {str(send_error)[:50]}...'
            
            results['details'].append({
                'email': parent_email,
                'name': parent_name,
                'status': status_mesaj,
                'students_count': len(students_info),
                'grades_count': len(info.get('all_grades', []))
            })
            
            # Mică pauză pentru a evita supraîncărcarea serverului SMTP
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Eroare la trimiterea email-ului către {parent_email}: {str(e)}")
            results['failed'] += 1
            results['details'].append({
                'email': parent_email,
                'name': info.get('name', 'Necunoscut'),
                'status': 'Eroare',
                'error': str(e)
            })
    
    # Afișează mesaje de rezultat
    if results['total'] == 0:
        flash('Nu există note pentru elevii selectați. Nu s-au trimis notificări.', 'warning')
    else:
        if results['success'] > 0:
            # Verificăm câte emailuri au fost trimise cu succes
            if results["emails_sent"] > 0:
                flash(f'S-au trimis cu succes {results["success"]} din {results["total"]} notificări ({results["emails_sent"]} prin email).', 'success')
            else:
                flash(f'S-au generat {results["success"]} din {results["total"]} notificări ca PDF-uri, dar NU s-au trimis emailuri. Puteți găsi PDF-urile în folderul static/notifications_pdf/ pentru a le distribui manual.', 'primary')
        
        if results['failed'] > 0:
            flash(f'Au eșuat {results["failed"]} notificări. Verificați setările serverului SMTP și adresele de email.', 'danger')
    
    return redirect(url_for('send_notifications_page'))
    
@app.route('/export-excel')
def export_excel():
    # Creează un buffer pentru output
    output = io.BytesIO()
    
    # Creează workbook-ul Excel și adaugă un format pentru header
    workbook = xlsxwriter.Workbook(output)
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4F81BD',
        'color': 'white',
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })
    
    # Format pentru note
    grade_format = workbook.add_format({
        'num_format': '0.00',
        'align': 'center'
    })
    
    # Format pentru note bune (peste 8)
    good_grade_format = workbook.add_format({
        'num_format': '0.00',
        'align': 'center',
        'bg_color': '#C6EFCE',
        'color': '#006100'
    })
    
    # Format pentru note medii (între 5 și 8)
    average_grade_format = workbook.add_format({
        'num_format': '0.00',
        'align': 'center',
        'bg_color': '#FFEB9C',
        'color': '#9C6500'
    })
    
    # Format pentru note slabe (sub 5)
    poor_grade_format = workbook.add_format({
        'num_format': '0.00',
        'align': 'center',
        'bg_color': '#FFC7CE',
        'color': '#9C0006'
    })
    
    # Format pentru medii
    average_format = workbook.add_format({
        'bold': True,
        'num_format': '0.00',
        'align': 'center',
        'bg_color': '#E6E6E6'
    })
    
    # Format pentru data
    date_format = workbook.add_format({
        'num_format': 'dd/mm/yyyy',
        'align': 'center'
    })
    
    # Obține toți elevii
    students = Student.query.order_by(Student.class_name, Student.name).all()
    
    # Creează sheet-ul general cu toți elevii
    overview_sheet = workbook.add_worksheet('Situație Generală')
    
    # Adaugă header-ul
    headers = ['Nr.', 'Elev', 'Clasa', 'Părinte', 'Email', 'Media Generală']
    
    # Adaugă materii la header
    subjects = Subject.query.order_by(Subject.name).all()
    for subject in subjects:
        headers.append(subject.name)
    
    for col, header in enumerate(headers):
        overview_sheet.write(0, col, header, header_format)
    
    # Setează lățimea coloanelor
    overview_sheet.set_column(0, 0, 5)  # Nr.
    overview_sheet.set_column(1, 1, 25)  # Elev
    overview_sheet.set_column(2, 2, 10)  # Clasa
    overview_sheet.set_column(3, 3, 25)  # Părinte
    overview_sheet.set_column(4, 4, 30)  # Email
    overview_sheet.set_column(5, 5, 15)  # Media Generală
    overview_sheet.set_column(6, len(headers) - 1, 15)  # Materii
    
    # Calculează mediile pentru fiecare elev și materie și completează tabelul
    for i, student in enumerate(students):
        row = i + 1
        overall_sum = 0
        subject_count = 0
        
        # Date elev
        overview_sheet.write(row, 0, i + 1)  # Număr
        overview_sheet.write(row, 1, student.name)  # Nume
        overview_sheet.write(row, 2, student.class_name)  # Clasa
        overview_sheet.write(row, 3, student.parent_name)  # Părinte
        overview_sheet.write(row, 4, student.parent_email)  # Email
        
        # Calculează mediile pentru fiecare materie
        subject_averages = {}
        
        for grade in student.grades:
            if grade.subject_id not in subject_averages:
                subject_averages[grade.subject_id] = []
            subject_averages[grade.subject_id].append(grade.value)
        
        # Scrie mediile pe materii
        for j, subject in enumerate(subjects):
            col = j + 6  # Offset pentru primele 6 coloane
            
            if subject.id in subject_averages:
                subject_grades = subject_averages[subject.id]
                avg = sum(subject_grades) / len(subject_grades)
                
                # Folosește formatul adecvat în funcție de valoarea mediei
                if avg >= 8:
                    overview_sheet.write(row, col, avg, good_grade_format)
                elif avg >= 5:
                    overview_sheet.write(row, col, avg, average_grade_format)
                else:
                    overview_sheet.write(row, col, avg, poor_grade_format)
                
                overall_sum += avg
                subject_count += 1
            else:
                overview_sheet.write(row, col, '-')  # Fără note
        
        # Calculează și scrie media generală
        if subject_count > 0:
            overall_avg = overall_sum / subject_count
            
            # Folosește formatul adecvat în funcție de valoarea mediei generale
            if overall_avg >= 8:
                overview_sheet.write(row, 5, overall_avg, good_grade_format)
            elif overall_avg >= 5:
                overview_sheet.write(row, 5, overall_avg, average_grade_format)
            else:
                overview_sheet.write(row, 5, overall_avg, poor_grade_format)
        else:
            overview_sheet.write(row, 5, '-')  # Fără note
    
    # Creează sheet-uri individuale pentru fiecare clasă
    classes = {}
    for student in students:
        if student.class_name not in classes:
            classes[student.class_name] = []
        classes[student.class_name].append(student)
    
    for class_name, class_students in classes.items():
        # Creează sheet pentru clasa curentă
        class_sheet = workbook.add_worksheet(f'Clasa {class_name}')
        
        # Adaugă header
        class_headers = ['Nr.', 'Elev', 'Media Generală']
        for subject in subjects:
            class_headers.append(subject.name)
        
        for col, header in enumerate(class_headers):
            class_sheet.write(0, col, header, header_format)
        
        # Setează lățimea coloanelor
        class_sheet.set_column(0, 0, 5)      # Nr.
        class_sheet.set_column(1, 1, 30)     # Elev
        class_sheet.set_column(2, 2, 15)     # Media Generală
        class_sheet.set_column(3, len(class_headers) - 1, 15)  # Materii
        
        # Scrie datele elevilor
        student_overall_averages = []  # Lista pentru a stoca mediile generale ale elevilor
        
        for i, student in enumerate(class_students):
            row = i + 1
            overall_sum = 0
            subject_count = 0
            
            # Date elev
            class_sheet.write(row, 0, i + 1)      # Număr
            class_sheet.write(row, 1, student.name)  # Nume
            
            # Calculează mediile pentru fiecare materie
            subject_averages = {}
            
            for grade in student.grades:
                if grade.subject_id not in subject_averages:
                    subject_averages[grade.subject_id] = []
                subject_averages[grade.subject_id].append(grade.value)
            
            # Scrie mediile pe materii
            for j, subject in enumerate(subjects):
                col = j + 3  # Offset pentru primele 3 coloane
                
                if subject.id in subject_averages:
                    subject_grades = subject_averages[subject.id]
                    avg = sum(subject_grades) / len(subject_grades)
                    
                    # Folosește formatul adecvat în funcție de valoarea mediei
                    if avg >= 8:
                        class_sheet.write(row, col, avg, good_grade_format)
                    elif avg >= 5:
                        class_sheet.write(row, col, avg, average_grade_format)
                    else:
                        class_sheet.write(row, col, avg, poor_grade_format)
                    
                    overall_sum += avg
                    subject_count += 1
                else:
                    class_sheet.write(row, col, '-')  # Fără note
            
            # Calculează și scrie media generală
            if subject_count > 0:
                overall_avg = overall_sum / subject_count
                student_overall_averages.append(overall_avg)  # Adaugă la lista de medii generale
                
                # Folosește formatul adecvat în funcție de valoarea mediei generale
                if overall_avg >= 8:
                    class_sheet.write(row, 2, overall_avg, good_grade_format)
                elif overall_avg >= 5:
                    class_sheet.write(row, 2, overall_avg, average_grade_format)
                else:
                    class_sheet.write(row, 2, overall_avg, poor_grade_format)
            else:
                class_sheet.write(row, 2, '-')  # Fără note
        
        # Calculează statistici pentru clasă (doar dacă există cel puțin un elev cu medie generală)
        if student_overall_averages:
            # Rândul pentru statistici (după ultimul elev)
            stats_row = len(class_students) + 3
            
            # Media clasei
            class_avg = sum(student_overall_averages) / len(student_overall_averages)
            class_sheet.write(stats_row, 0, "Statistici clasă:", header_format)
            class_sheet.write(stats_row, 1, "Media clasei:")
            class_sheet.write(stats_row, 2, class_avg, good_grade_format)
            
            # Calculează abaterea medie
            mean_deviation = sum(abs(avg - class_avg) for avg in student_overall_averages) / len(student_overall_averages)
            class_sheet.write(stats_row + 1, 1, "Abaterea medie:")
            class_sheet.write(stats_row + 1, 2, mean_deviation)
            
            # Calculează abaterea standard
            variance = sum((avg - class_avg) ** 2 for avg in student_overall_averages) / len(student_overall_averages)
            std_deviation = variance ** 0.5  # Rădăcina pătrată a varianței
            class_sheet.write(stats_row + 2, 1, "Abaterea standard:")
            class_sheet.write(stats_row + 2, 2, std_deviation)
    
    # Crează sheet-uri individuale pentru fiecare elev cu toate notele
    for student in students:
        if student.grades:  # Doar pentru elevii care au note
            # Creează sheet pentru elevul curent
            student_sheet = workbook.add_worksheet(f'{student.name} ({student.class_name})')
            
            # Adaugă header pentru informații elev
            student_sheet.write(0, 0, f'Elev: {student.name}')
            student_sheet.write(1, 0, f'Clasa: {student.class_name}')
            student_sheet.write(2, 0, f'Părinte: {student.parent_name}')
            student_sheet.write(3, 0, f'Email: {student.parent_email}')
            
            # Setează lățimea coloanelor
            student_sheet.set_column(0, 0, 5)   # Nr.
            student_sheet.set_column(1, 1, 25)  # Materie
            student_sheet.set_column(2, 2, 15)  # Notă
            student_sheet.set_column(3, 3, 15)  # Data
            
            # Adaugă header pentru tabelul de note
            note_headers = ['Nr.', 'Materie', 'Notă', 'Data']
            row = 5  # Începe după informațiile despre elev
            
            for col, header in enumerate(note_headers):
                student_sheet.write(row, col, header, header_format)
            
            # Grupează notele după materie
            subject_grades = {}
            for grade in student.grades:
                if grade.subject_id not in subject_grades:
                    subject_grades[grade.subject_id] = []
                subject_grades[grade.subject_id].append(grade)
            
            # Numărător pentru rânduri
            count = 1
            row += 1
            
            # Pentru fiecare materie, afișează notele și calculează media
            for subject_id, grades in subject_grades.items():
                subject = Subject.query.get(subject_id)
                
                # Scrie fiecare notă
                for grade in sorted(grades, key=lambda g: g.date, reverse=True):
                    student_sheet.write(row, 0, count)
                    student_sheet.write(row, 1, subject.name if subject else "Materie necunoscută")
                    
                    # Folosește formatul adecvat în funcție de valoarea notei
                    if grade.value >= 8:
                        student_sheet.write(row, 2, grade.value, good_grade_format)
                    elif grade.value >= 5:
                        student_sheet.write(row, 2, grade.value, average_grade_format)
                    else:
                        student_sheet.write(row, 2, grade.value, poor_grade_format)
                    
                    # Formatează data
                    student_sheet.write(row, 3, grade.date, date_format)
                    
                    row += 1
                    count += 1
                
                # Calculează și afișează media pentru materie
                avg = sum(g.value for g in grades) / len(grades)
                student_sheet.write(row, 0, '')
                student_sheet.write(row, 1, f'Media la {subject.name if subject else "Materie necunoscută"}:')
                
                # Folosește formatul adecvat în funcție de valoarea mediei
                if avg >= 8:
                    student_sheet.write(row, 2, avg, good_grade_format)
                elif avg >= 5:
                    student_sheet.write(row, 2, avg, average_grade_format)
                else:
                    student_sheet.write(row, 2, avg, poor_grade_format)
                
                student_sheet.write(row, 3, '')
                row += 1  # Lasă un rând liber între materii
                row += 1
            
            # Calculează și afișează media generală
            if subject_grades:
                subject_averages = []
                for subject_id, grades in subject_grades.items():
                    avg = sum(g.value for g in grades) / len(grades)
                    subject_averages.append(avg)
                
                overall_avg = sum(subject_averages) / len(subject_averages)
                
                # Folosim write în loc de merge_range pentru a evita erorile
                student_sheet.write(row, 0, 'MEDIA GENERALĂ:')
                student_sheet.write(row, 1, '')
                
                # Folosește formatul adecvat în funcție de valoarea mediei generale
                if overall_avg >= 8:
                    student_sheet.write(row, 2, overall_avg, good_grade_format)
                elif overall_avg >= 5:
                    student_sheet.write(row, 2, overall_avg, average_grade_format)
                else:
                    student_sheet.write(row, 2, overall_avg, poor_grade_format)
                student_sheet.write(row, 3, '')
    
    # Închide workbook-ul
    workbook.close()
    
    # Setează pointer-ul la început pentru a citi
    output.seek(0)
    
    # Crează răspunsul
    response = make_response(output.read())
    response.headers["Content-Disposition"] = "attachment; filename=Situatie_Scolara.xlsx"
    response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    return response

@app.route('/student/<int:student_id>')
def student_profile(student_id):
    now = datetime.datetime.now()
    student = Student.query.get_or_404(student_id)
    subjects = Subject.query.order_by(Subject.name).all()
    
    # Verifică dacă există un parametru subject_id pentru a păstra selecția materiei
    selected_subject_id = request.args.get('subject_id', None)
    
    # Obține elevii pentru meniul de navigare
    students, students_by_class = get_students_by_class()
    
    # Calculează media elevului
    student_grades = []
    subject_grades = {}
    subject_sums = {}
    subject_counts = {}
    overall_sum = 0
    overall_count = 0
    
    for grade in student.grades:
        student_grades.append(grade)
        overall_sum += grade.value
        overall_count += 1
        
        # Grupează notele după materie
        if grade.subject_id not in subject_grades:
            subject_grades[grade.subject_id] = {
                'name': grade.subject.name,
                'grades': [],
                'average': 0
            }
            subject_sums[grade.subject_id] = 0
            subject_counts[grade.subject_id] = 0
        
        subject_grades[grade.subject_id]['grades'].append(grade)
        subject_sums[grade.subject_id] += grade.value
        subject_counts[grade.subject_id] += 1
    
    # Calculează media pentru fiecare materie
    for subject_id in subject_grades:
        if subject_counts[subject_id] > 0:
            subject_grades[subject_id]['average'] = subject_sums[subject_id] / subject_counts[subject_id]
    
    # Calculează media generală corect (media mediilor pe materii)
    subject_averages_sum = 0
    subject_with_grades_count = 0
    
    for subject_id in subject_grades:
        if subject_counts[subject_id] > 0:
            subject_averages_sum += subject_grades[subject_id]['average']
            subject_with_grades_count += 1
            
    # Media generală este media mediilor pe materii (nu media tuturor notelor)
    student_average = subject_averages_sum / subject_with_grades_count if subject_with_grades_count > 0 else 0
    
    return render_template('student_profile.html',
                          now=now,
                          student=student,
                          subjects=subjects,
                          students=students,
                          students_by_class=students_by_class,
                          student_grades=student_grades,
                          subject_grades=subject_grades,
                          student_average=student_average,
                          selected_subject_id=selected_subject_id)
                          
@app.route('/student/<int:student_id>/add-grade', methods=['POST'])
def add_grade_for_student(student_id):
    """Adaugă multiple note pentru un elev specific din profilul acestuia"""
    student = Student.query.get_or_404(student_id)
    
    subject_id = request.form.get('subject_id')
    values = request.form.getlist('values[]')
    dates = request.form.getlist('dates[]')
    
    if not subject_id or not values:
        flash('Selectați materia și introduceți cel puțin o notă', 'danger')
        return redirect(url_for('student_profile', student_id=student_id))
    
    # Verifică dacă materia există
    subject = Subject.query.get(subject_id)
    if not subject:
        flash('Materia selectată nu există', 'danger')
        return redirect(url_for('student_profile', student_id=student_id))
    
    # Contorizare note adăugate cu succes
    success_count = 0
    
    # Iterăm prin note și le adăugăm
    for i in range(len(values)):
        # Verificăm că avem valoare pentru această notă
        if not values[i]:
            continue
        
        try:
            # Convertește și validează valoarea notei
            value = float(values[i])
            if value < 1 or value > 10:
                continue  # Sărim peste notele invalide
            
            # Convertește data string la obiect date
            try:
                if i < len(dates) and dates[i]:
                    date_obj = datetime.datetime.strptime(dates[i], '%Y-%m-%d').date()
                else:
                    date_obj = datetime.datetime.now().date()  # Folosește data curentă dacă nu e specificată
            except ValueError:
                date_obj = datetime.datetime.now().date()  # Folosește data curentă în caz de eroare
            
            # Creează și salvează nota
            grade = Grade(value=value, date=date_obj, student_id=student_id, subject_id=subject_id)
            db.session.add(grade)
            success_count += 1
            
        except ValueError:
            continue  # Sărim peste valorile invalide
        except Exception as e:
            logger.error(f"Eroare la adăugarea notei: {str(e)}")
            db.session.rollback()
            flash(f'Eroare la adăugarea notelor: {str(e)}', 'danger')
            return redirect(url_for('student_profile', student_id=student_id, subject_id=subject_id))
    
    # Commit la baza de date
    if success_count > 0:
        db.session.commit()
        flash(f'Au fost adăugate {success_count} note pentru {student.name} la {subject.name}', 'success')
    else:
        flash('Nu a fost adăugată nicio notă validă', 'warning')
    
    # Trimitem înapoi și ID-ul materiei pentru a păstra selecția
    return redirect(url_for('student_profile', student_id=student_id, subject_id=subject_id))
    
# Rute pentru sistemul de remindere
@app.route('/gdpr')
def gdpr_settings():
    """Pagina pentru setările GDPR și consimțământ"""
    # Încărcăm setările existente
    current_settings = load_gdpr_settings()
    
    return render_template('gdpr_consent.html', 
                           current_settings=current_settings,
                           now=datetime.datetime.now())

@app.route('/gdpr/parent-forms')
def gdpr_parent_forms():
    """Pagina pentru gestionarea formularelor de consimțământ GDPR pentru părinți"""
    # Încărcăm șablonul existent sau folosim un șablon implicit
    form_template = load_gdpr_form_template()
    
    return render_template('gdpr_parent_consent_form.html',
                           form_template=form_template,
                           now=datetime.datetime.now())

@app.route('/gdpr/save-form-template', methods=['POST'])
def save_gdpr_form_template():
    """Salvează șablonul formularului de consimțământ GDPR pentru părinți"""
    form_data = {
        'title': request.form.get('form_title', ''),
        'intro': request.form.get('form_intro', ''),
        'data_collected': request.form.get('form_data_collected', ''),
        'purpose': request.form.get('form_purpose', ''),
        'rights': request.form.get('form_rights', ''),
        'contact': request.form.get('form_contact', ''),
        'updated_at': datetime.datetime.now().isoformat()
    }
    
    # Salvăm șablonul
    try:
        static_dir = 'static'
        if not os.path.exists(static_dir):
            os.makedirs(static_dir)
            
        template_path = os.path.join(static_dir, 'gdpr_form_template.json')
        
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(form_data, f, indent=2, ensure_ascii=False)
            
        flash('Șablonul formularului GDPR a fost salvat cu succes.', 'success')
    except Exception as e:
        logger.error(f"Eroare la salvarea șablonului formularului GDPR: {e}")
        flash(f'Eroare la salvarea șablonului: {str(e)}', 'danger')
    
    return redirect(url_for('gdpr_parent_forms'))

@app.route('/gdpr/send-forms-email', methods=['POST'])
def send_gdpr_forms_email():
    """Trimite formulare de consimțământ GDPR personalizate către toți părinții prin email"""
    include_pdf = 'include_gdpr_pdf_email' in request.form
    
    # Obținem toți elevii pentru a trimite părinților
    students = Student.query.all()
    
    # Încărcăm șablonul formularului
    form_template = load_gdpr_form_template()
    
    # Inițializăm contoare
    success_count = 0
    failure_count = 0
    
    for student in students:
        # Personalizăm formatul pentru fiecare părinte
        html_content = generate_gdpr_form_html(student, form_template)
        
        # Pregătim subiectul emailului
        subject = f"Informare GDPR - DiriginteSmart pentru {student.name}"
        
        # Adăugăm un text simplu pentru emailurile fără suport HTML
        text_content = f"""INFORMARE PRIVIND PROTECȚIA DATELOR (GDPR)
        
Stimate părinte/tutore al elevului {student.name},

Conform Regulamentului (UE) 2016/679 privind protecția persoanelor fizice în ceea ce privește prelucrarea datelor cu caracter personal (GDPR), vă informăm că datele dumneavoastră și ale copilului dumneavoastră sunt prelucrate în aplicația DiriginteSmart.

Vă rugăm să consultați documentul atașat pentru informații complete și pentru a vă exprima consimțământul.

Cu stimă,
Conducerea școlii
"""
        
        # Generăm un PDF cu formularul dacă este necesar
        pdf_attachment = None
        if include_pdf:
            pdf_success, pdf_path = generate_gdpr_form_pdf(student, form_template)
            if pdf_success:
                pdf_attachment = pdf_path
        
        # Trimitem emailul
        try:
            # Configurarea email-ului din mediu sau din setări
            email_user = os.environ.get('EMAIL_USER', '')
            
            # Folosim direct Brevo API pentru a trimite emailuri (configurat în Replit)
            from utils.email_sender import send_with_brevo
            if send_with_brevo(
                from_email=email_user, 
                to_email=student.parent_email, 
                subject=subject, 
                text_content=text_content, 
                html_content=html_content
            ):
                success_count += 1
            else:
                failure_count += 1
                # Generăm PDF local pentru backup
                logger.info(f"Generăm PDF local pentru {student.parent_email}")
                    
            # Salvăm o copie locală a notificării
            save_notification(
                from_email=email_user,
                to_email=student.parent_email,
                subject=subject,
                content=html_content
            )
            
        except Exception as e:
            logger.error(f"Eroare la trimiterea formularului GDPR către {student.parent_email}: {e}")
            failure_count += 1
    
    # Afișăm un mesaj cu rezultatele
    if success_count > 0:
        flash(f'S-au trimis cu succes {success_count} formulare GDPR către părinți.', 'success')
    if failure_count > 0:
        flash(f'Nu s-au putut trimite {failure_count} formulare. Verificați setările de email.', 'warning')
    
    return redirect(url_for('gdpr_parent_forms'))

@app.route('/gdpr/generate-forms-pdf', methods=['POST'])
def generate_gdpr_forms_pdf():
    """Generează formulare PDF pentru toți părinții pentru print"""
    include_signature = 'include_signature_field' in request.form
    
    # Obținem toți elevii
    students = Student.query.all()
    
    # Încărcăm șablonul formularului
    form_template = load_gdpr_form_template()
    
    # Creăm un director temporar pentru PDF-uri
    temp_dir = tempfile.mkdtemp()
    
    # Creăm un arhivă ZIP pentru toate PDF-urile
    import zipfile
    zip_filename = os.path.join(temp_dir, 'formulare_gdpr.zip')
    
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        for student in students:
            # Generăm PDF pentru fiecare student
            pdf_success, pdf_path = generate_gdpr_form_pdf(
                student, 
                form_template, 
                include_signature=include_signature
            )
            
            if pdf_success:
                # Adăugăm PDF-ul la arhiva ZIP
                pdf_filename = os.path.basename(pdf_path)
                zipf.write(pdf_path, pdf_filename)
    
    # Pregătim răspunsul pentru download
    with open(zip_filename, 'rb') as f:
        response = make_response(f.read())
        
    response.headers.set('Content-Type', 'application/zip')
    response.headers.set('Content-Disposition', 'attachment; filename=formulare_gdpr.zip')
    
    return response

@app.route('/gdpr/save', methods=['POST'])
def save_gdpr_settings():
    """Salvează setările GDPR"""
    # Extragem datele din formular
    consent_data = {
        'consent_storage': 'consent_storage' in request.form,
        'consent_email': 'consent_email' in request.form,
        'consent_stats': 'consent_stats' in request.form,
        'consent_retention': 'consent_retention' in request.form,
        'gdpr_contact_name': request.form.get('gdpr_contact_name', ''),
        'gdpr_contact_email': request.form.get('gdpr_contact_email', '')
    }
    
    # Salvăm consimțământul
    if save_gdpr_consent(consent_data):
        flash('Setările GDPR au fost salvate cu succes.', 'success')
    else:
        flash('Eroare la salvarea setărilor GDPR. Verificați permisiunile.', 'danger')
    
    return redirect(url_for('gdpr_settings'))

@app.route('/gdpr/export')
def gdpr_export_data():
    """Pagina pentru exportul datelor conform GDPR"""
    students = Student.query.order_by(Student.class_name, Student.name).all()
    return render_template('gdpr_export.html', students=students, now=datetime.datetime.now())

@app.route('/gdpr/export', methods=['POST'])
def gdpr_export_data_post():
    """Procesează cererea de export date GDPR"""
    export_type = request.form.get('export_type')
    subject_id = request.form.get('subject_id')
    export_format = request.form.get('export_format', 'json')
    anonymize_others = 'anonymize_others' in request.form
    
    if not subject_id:
        flash('Selectați un elev pentru a exporta datele.', 'warning')
        return redirect(url_for('gdpr_export_data'))
    
    # Obținem studentul și datele asociate
    student = Student.query.get_or_404(subject_id)
    
    # Construim datele pentru export
    export_data = {
        'student': {
            'id': student.id,
            'name': student.name,
            'class_name': student.class_name,
            'created_at': student.created_at.isoformat() if student.created_at else None,
            'updated_at': student.updated_at.isoformat() if student.updated_at else None
        },
        'parent': {
            'name': student.parent_name,
            'email': student.parent_email
        }
    }
    
    if export_type in ['student', 'all']:
        # Adăugăm notele dacă sunt solicitate
        grades_data = []
        for grade in student.grades:
            grades_data.append({
                'id': grade.id,
                'value': grade.value,
                'date': grade.date.isoformat() if grade.date else None,
                'subject': {
                    'id': grade.subject.id,
                    'name': grade.subject.name
                } if grade.subject else None,
                'created_at': grade.created_at.isoformat() if grade.created_at else None
            })
        
        export_data['grades'] = grades_data
    
    # Generăm fișierul în formatul solicitat
    if export_format == 'json':
        filename, file_data = export_as_json(export_data)
        mimetype = 'application/json'
    else:
        filename, file_data = export_as_csv(export_data)
        mimetype = 'text/csv'
    
    # Creăm răspunsul pentru download
    response = make_response(file_data)
    response.headers.set('Content-Type', mimetype)
    response.headers.set('Content-Disposition', f'attachment; filename={filename}')
    
    return response

@app.route('/gdpr/delete')
def gdpr_delete_data():
    """Pagina pentru ștergerea datelor conform GDPR"""
    students = Student.query.order_by(Student.class_name, Student.name).all()
    return render_template('gdpr_delete.html', students=students, now=datetime.datetime.now())

@app.route('/gdpr/delete', methods=['POST'])
def gdpr_delete_data_post():
    """Procesează cererea de ștergere date GDPR"""
    delete_type = request.form.get('delete_type')
    subject_id = request.form.get('subject_id')
    confirmation = request.form.get('confirmation')
    anonymize_option = 'anonymize' in request.form
    
    if not subject_id or not delete_type:
        flash('Selectați un elev și tipul de ștergere.', 'warning')
        return redirect(url_for('gdpr_delete_data'))
    
    if confirmation != 'ȘTERGE':
        flash('Confirmarea ștergerii este incorectă. Tastați ȘTERGE pentru a confirma.', 'danger')
        return redirect(url_for('gdpr_delete_data'))
    
    # Obținem studentul
    student = Student.query.get_or_404(subject_id)
    
    try:
        if delete_type == 'student_complete' or delete_type == 'all':
            # Ștergem toate notele studentului
            for grade in student.grades:
                db.session.delete(grade)
            
        if delete_type == 'student' or delete_type == 'student_complete' or delete_type == 'all':
            if anonymize_option:
                # Anonimizăm datele studentului
                student.name = f"ANONYMIZED_{hashlib.md5(student.name.encode()).hexdigest()[:8]}"
                # Păstrăm class_name pentru statistici
            else:
                # Ștergem studentul complet
                db.session.delete(student)
                
        if delete_type == 'parent' or delete_type == 'all':
            if anonymize_option:
                # Anonimizăm datele părintelui
                student.parent_name = f"ANONYMIZED_{hashlib.md5(student.parent_name.encode()).hexdigest()[:8]}"
                student.parent_email = f"anonymized_{hashlib.md5(student.parent_email.encode()).hexdigest()[:8]}@example.com"
            else:
                # Dacă ștergem doar părintele dar păstrăm elevul
                if delete_type == 'parent':
                    student.parent_name = "Șters GDPR"
                    student.parent_email = "gdpr@example.com"
        
        # Commit schimbările
        db.session.commit()
        
        flash('Datele au fost procesate conform solicitării GDPR.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Eroare la ștergerea datelor GDPR: {e}")
        flash(f'Eroare la procesarea datelor: {str(e)}', 'danger')
    
    return redirect(url_for('gdpr_settings'))

@app.route('/reminders')
def reminders():
    """Pagina pentru managementul reminderelor"""
    now = datetime.datetime.now()
    active_reminders = check_active_reminders()  # Pentru afișarea notificărilor
    all_reminders = Reminder.query.order_by(Reminder.day_of_week, Reminder.time_of_day).all()
    return render_template('reminders.html', now=now, reminders=all_reminders, active_reminders=active_reminders)

@app.route('/add-reminder', methods=['POST'])
def add_reminder():
    """Adaugă un reminder nou"""
    title = request.form.get('title')
    description = request.form.get('description')
    day_of_week = int(request.form.get('day_of_week', 5))  # 5 = Sâmbătă în mod implicit
    time_of_day = request.form.get('time_of_day', '09:00')
    
    if not title:
        flash('Titlul reminderului este obligatoriu!', 'danger')
        return redirect(url_for('reminders'))
        
    reminder = Reminder(
        title=title, 
        description=description,
        day_of_week=day_of_week,
        time_of_day=time_of_day,
        active=True
    )
    
    db.session.add(reminder)
    db.session.commit()
    
    flash(f'Reminder "{title}" a fost adăugat cu succes!', 'success')
    return redirect(url_for('reminders'))

@app.route('/edit-reminder/<int:reminder_id>')
def edit_reminder(reminder_id):
    """Pagina pentru editarea unui reminder"""
    reminder = Reminder.query.get_or_404(reminder_id)
    active_reminders = check_active_reminders()  # Pentru afișarea notificărilor
    return render_template('edit_reminder.html', reminder=reminder, active_reminders=active_reminders)
    
@app.route('/update-reminder/<int:reminder_id>', methods=['POST'])
def update_reminder(reminder_id):
    """Actualizează un reminder existent"""
    reminder = Reminder.query.get_or_404(reminder_id)
    
    reminder.title = request.form.get('title')
    reminder.description = request.form.get('description')
    reminder.day_of_week = int(request.form.get('day_of_week', 5))
    reminder.time_of_day = request.form.get('time_of_day', '09:00')
    reminder.active = 'active' in request.form
    
    db.session.commit()
    
    flash(f'Reminder "{reminder.title}" a fost actualizat cu succes!', 'success')
    return redirect(url_for('reminders'))
    
@app.route('/toggle-reminder/<int:reminder_id>')
def toggle_reminder(reminder_id):
    """Activează/dezactivează un reminder"""
    reminder = Reminder.query.get_or_404(reminder_id)
    reminder.active = not reminder.active
    db.session.commit()
    
    status = "activat" if reminder.active else "dezactivat"
    flash(f'Reminder "{reminder.title}" a fost {status}!', 'success')
    return redirect(url_for('reminders'))
    
@app.route('/delete-reminder/<int:reminder_id>')
def delete_reminder(reminder_id):
    """Șterge un reminder"""
    reminder = Reminder.query.get_or_404(reminder_id)
    
    title = reminder.title
    db.session.delete(reminder)
    db.session.commit()
    
    flash(f'Reminder "{title}" a fost șters cu succes!', 'success')
    return redirect(url_for('reminders'))