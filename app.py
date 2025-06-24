# app.py
from flask import Flask, render_template, request, jsonify
import os
import sys
import threading
import time
import tempfile
import shutil
from werkzeug.utils import secure_filename

# Add the directory containing script_org.py to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import script_org # Import your modified script

# Initialize Flask app, specifying the current directory as the template folder
app = Flask(__name__, template_folder='.')

# Configure upload settings
UPLOAD_FOLDER = tempfile.gettempdir()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# Global variable to store organization status and messages
organization_status = {
    "running": False,
    "progress": 0, # Percentage
    "messages": [],
    "error": None,
    "completed": False,
    "current_step": ""
}

def run_organization_task(folder_path):
    global organization_status
    organization_status["running"] = True
    organization_status["progress"] = 0
    organization_status["messages"] = []
    organization_status["error"] = None
    organization_status["completed"] = False
    organization_status["current_step"] = "Starting organization..."

    try:
        # Override the _log_progress function in script_org to capture messages
        original_log_progress = script_org._log_progress
        step_count = 0
        
        def web_log_progress(message):
            nonlocal step_count
            original_log_progress(message) # Still print to console
            organization_status["messages"].append(message)
            
            # Update progress based on step indicators
            if message.startswith("Step"):
                step_count += 1
                organization_status["progress"] = min(90, step_count * 15)
                organization_status["current_step"] = message
            elif "complete" in message.lower():
                organization_status["progress"] = 100
                organization_status["current_step"] = "Organization completed!"
            else:
                # Gradual progress increase for other messages
                organization_status["progress"] = min(95, organization_status["progress"] + 1)
        
        script_org._log_progress = web_log_progress

        success, messages = script_org.organize_files_web(folder_path)
        organization_status["messages"] = messages # Ensure all messages are captured
        organization_status["completed"] = True
        organization_status["progress"] = 100
        organization_status["current_step"] = "Organization completed!"
        
        if not success:
            organization_status["error"] = "Organization failed. Check logs for details."
    except Exception as e:
        organization_status["error"] = str(e)
        organization_status["messages"].append(f"An unexpected error occurred: {e}")
        organization_status["completed"] = True
        organization_status["progress"] = 100
        organization_status["current_step"] = "Error occurred"
    finally:
        organization_status["running"] = False
        # Restore original log function
        script_org._log_progress = original_log_progress

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({"status": "error", "message": "No files uploaded."}), 400
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({"status": "error", "message": "No files selected."}), 400
    
    # Create a temporary directory for this upload
    upload_dir = tempfile.mkdtemp()
    
    try:
        # Process uploaded files and recreate folder structure
        folder_structure = {}
        
        for file in files:
            if file.filename == '':
                continue
                
            # Get the relative path from the webkitRelativePath
            relative_path = file.filename
            
            # Create directory structure
            file_path = os.path.join(upload_dir, relative_path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save the file
            file.save(file_path)
        
        return jsonify({
            "status": "success", 
            "message": "Files uploaded successfully.",
            "upload_path": upload_dir
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500

@app.route('/organize', methods=['POST'])
def organize():
    global organization_status
    if organization_status["running"]:
        return jsonify({"status": "error", "message": "Organization already in progress."}), 409

    data = request.get_json()
    folder_path = data.get('folder_path') if data else None
    
    if not folder_path:
        return jsonify({"status": "error", "message": "Folder path is required."}), 400

    if not os.path.exists(folder_path):
        return jsonify({"status": "error", "message": "Folder path does not exist."}), 400

    # Start the organization task in a separate thread
    thread = threading.Thread(target=run_organization_task, args=(folder_path,))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "success", "message": "Organization started."})

@app.route('/status')
def status():
    global organization_status
    return jsonify(organization_status)

@app.route('/download/<path:filename>')
def download_file(filename):
    # This would be used to download the organized files
    # Implementation depends on your specific needs
    pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
