document.addEventListener('DOMContentLoaded', function() {
    // Add an event listener to file input to display the selected file name
    const fileInput = document.getElementById('csv_file');
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            const fileName = this.files[0] ? this.files[0].name : 'No file selected';
            const fileLabel = document.querySelector('.form-file-text');
            if (fileLabel) {
                fileLabel.textContent = fileName;
            }
        });
    }
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Add validation for the email form
    const emailForm = document.querySelector('form[action*="send_notifications"]');
    if (emailForm) {
        emailForm.addEventListener('submit', function(event) {
            const emailUser = document.getElementById('email_user').value;
            const emailPass = document.getElementById('email_pass').value;
            
            if (!emailUser || !emailPass) {
                event.preventDefault();
                alert('Please provide both email address and password.');
            }
        });
    }
});
