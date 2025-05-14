from app import db
from datetime import datetime, timedelta

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    class_name = db.Column(db.String(20), nullable=False)
    parent_name = db.Column(db.String(100), nullable=False)
    parent_email = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relație one-to-many cu Grade
    grades = db.relationship('Grade', backref='student', lazy=True, cascade="all, delete-orphan")
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __repr__(self):
        return f"<Student {self.name} (Class {self.class_name})>"

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    
    # Relație one-to-many cu Grade
    grades = db.relationship('Grade', backref='subject', lazy=True)
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __repr__(self):
        return f"<Subject {self.name}>"

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow().date)
    
    # Chei străine
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __repr__(self):
        return f"<Grade {self.value} for Student ID {self.student_id} in Subject ID {self.subject_id}>"


class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Ziua săptămânii (0-6, unde 0 este luni, 5 este vineri, 6 este duminică)
    day_of_week = db.Column(db.Integer, nullable=False, default=4)  # Vineri în mod implicit
    
    # Ora zilei (format 24h, de ex. 15:30)
    time_of_day = db.Column(db.String(5), nullable=False, default="17:00")
    
    # Dacă reminder-ul este activ
    active = db.Column(db.Boolean, default=True)
    
    # Dacă reminder-ul se aplică doar în perioada școli (fără vacanțe)
    school_time_only = db.Column(db.Boolean, default=True)
    
    # Date pentru perioada școlii (opțional)
    school_start_date = db.Column(db.Date, nullable=True)  # Data începerii anului școlar
    school_end_date = db.Column(db.Date, nullable=True)    # Data terminării anului școlar
    
    # Ultima dată când a fost trimis reminder-ul
    last_triggered = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __repr__(self):
        return f"<Reminder {self.title} (Day {self.day_of_week}, Time {self.time_of_day})>"
    
    @property
    def day_name(self):
        days = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
        return days[self.day_of_week]
    
    @property
    def is_due(self):
        """Verifică dacă reminder-ul trebuie declanșat acum"""
        if not self.active:
            return False
            
        now = datetime.now()
        
        # Verifică dacă ziua săptămânii este potrivită (0 = luni, 6 = duminică)
        current_day = now.weekday()
        if current_day != self.day_of_week:
            return False
            
        # Verifică ora
        hour, minute = map(int, self.time_of_day.split(':'))
        if now.hour != hour or now.minute < minute:
            return False
            
        # Verifică dacă a fost deja declanșat astăzi
        if self.last_triggered:
            last_date = self.last_triggered.date()
            if last_date == now.date():
                return False
                
        return True