import csv
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Any, DefaultDict

logger = logging.getLogger(__name__)

def calculate_average(grades: List[float]) -> float:
    """
    Calculate the average grade for a list of grades
    
    Args:
        grades: List of numeric grades
    
    Returns:
        The average grade or 0 if list is empty
    """
    if not grades:
        return 0
    return sum(grades) / len(grades)

def process_csv_data(csv_file_path: str) -> Optional[Dict[str, Any]]:
    """
    Process the CSV file and group data by parent's email
    
    Args:
        csv_file_path: Path to the CSV file
    
    Returns:
        Dictionary with parent emails as keys and their children's grades as values
        or None if processing fails
    """
    # The results dictionary (parent email -> data)
    grouped_data: Dict[str, Any] = {}
    
    # Temporary structure to process student data (parent email -> student ID -> data)
    student_grades: Dict[str, Dict[str, Dict[str, Any]]] = {}
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            
            # Verify required columns
            required_columns = ["NumeElev", "Clasa", "Materie", "Nota", "Data", "NumeParinte", "EmailParinte"]
            headers = csv_reader.fieldnames
            
            if not headers:
                logger.error("CSV file is empty or has no headers")
                return None
                
            missing_columns = [col for col in required_columns if col not in headers]
            if missing_columns:
                logger.error(f"CSV file is missing required columns: {', '.join(missing_columns)}")
                return None
            
            # First pass: collect all data from CSV and organize by parent/student
            for row in csv_reader:
                # Extract and clean basic data
                email = row.get('EmailParinte', '').strip()
                student_name = row.get('NumeElev', '').strip()
                class_name = row.get('Clasa', '').strip()
                subject = row.get('Materie', '').strip()
                grade_str = row.get('Nota', '').strip()
                date = row.get('Data', '').strip()
                parent_name = row.get('NumeParinte', '').strip()
                
                # Skip rows with missing critical data
                if not email or not student_name:
                    logger.warning(f"Skipping row with missing email or student name: {row}")
                    continue
                
                # Initialize parent entry if needed
                if email not in grouped_data:
                    grouped_data[email] = {
                        'parent_name': parent_name,
                        'grades': [],  # Individual grade entries
                        'students': {},  # Student data including averages
                        'averages': []  # Formatted average text for email
                    }
                
                # Initialize student data structure if needed
                student_key = f"{student_name}_{class_name}"
                if email not in student_grades:
                    student_grades[email] = {}
                
                if student_key not in student_grades[email]:
                    student_grades[email][student_key] = {
                        'name': student_name,
                        'class': class_name,
                        'subjects': defaultdict(list)
                    }
                
                # Format and add individual grade info
                grade_info = (
                    f"- {subject}: "
                    f"Nota {grade_str} "
                    f"(Data: {date}) - "
                    f"Elev: {student_name}, "
                    f"Clasa: {class_name}"
                )
                grouped_data[email]['grades'].append(grade_info)
                
                # Add grade to student's subject data (for average calculation)
                if subject:
                    try:
                        # Try to convert grade to float for calculations
                        grade_value = float(grade_str)
                        student_grades[email][student_key]['subjects'][subject].append({
                            'value': grade_value,
                            'date': date
                        })
                    except (ValueError, TypeError):
                        # If grade can't be converted to float, skip it
                        logger.warning(f"Non-numeric grade '{grade_str}' for {student_name} in {subject}")
            
            # Second pass: calculate averages for each student and subject
            for email, students in student_grades.items():
                for student_key, student_data in students.items():
                    name = student_data['name']
                    class_name = student_data['class']
                    
                    # Calculate averages for each subject
                    subject_averages = []
                    overall_grades = []
                    
                    for subject, grades in student_data['subjects'].items():
                        # Extract values for calculation
                        values = [g['value'] for g in grades]
                        
                        if values:
                            avg = calculate_average(values)
                            subject_averages.append({
                                'subject': subject,
                                'average': avg,
                                'count': len(values)
                            })
                            overall_grades.append(avg)
                    
                    # Calculate overall average
                    overall_avg = calculate_average(overall_grades)
                    
                    # Store calculated averages in result data
                    student_result = {
                        'name': name,
                        'class': class_name,
                        'subject_averages': subject_averages,
                        'overall_average': overall_avg
                    }
                    
                    grouped_data[email]['students'][student_key] = student_result
                    
                    # Format average info for email
                    avg_info = (
                        f"- {name} (Clasa {class_name}): "
                        f"Media Generală: {overall_avg:.2f}"
                    )
                    
                    # Add subject averages
                    for subj in subject_averages:
                        avg_info += f"\n  * {subj['subject']}: {subj['average']:.2f} ({subj['count']} note)"
                    
                    grouped_data[email]['averages'].append(avg_info)
        
        return grouped_data
    
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_file_path}")
        return None
    except Exception as e:
        logger.error(f"Error processing CSV file: {str(e)}")
        return None
