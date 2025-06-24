from flask import Flask, render_template, request, jsonify
import os
import sys
import threading
import time
from flask_cors import CORS

# Add the directory containing script_org.py to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import script_org

# Initialize Flask app
app = Flask(__name__, template_folder='.')
CORS(app)  # Enable CORS for all routes

# Global variable to store organization status
organization_status = {
    "running": False,
    "progress": 0,
    "messages": [],
    "error": None,
    "completed": False
}

def run_organization_task(folder_path):
    global organization_status
    organization_status["running"] = True
    organization_status["progress"] = 0
    organization_status["messages"] = []
    organization_status["error"] = None
    organization_status["completed"] = False

    try:
        # Override the _log_progress function to capture messages
        original_log_progress = script_org._log_progress
        def web_log_progress(message):
            original_log_progress(message)
            organization_status["messages"].append(message)
            organization_status["progress"] = min(100, organization_status["progress"] + 5)
        script_org._log_progress = web_log_progress

        success, messages = script_org.organize_files_web(folder_path)
        organization_status["messages"] = messages
        organization_status["completed"] = True
        organization_status["progress"] = 100
        if not success:
            organization_status["error"] = "Organization failed. Check logs for details."
    except Exception as e:
        organization_status["error"] = str(e)
        organization_status["messages"].append(f"Error: {e}")
        organization_status["completed"] = True
        organization_status["progress"] = 100
    finally:
        organization_status["running"] = False
        script_org._log_progress = original_log_progress

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/organize', methods=['POST'])
def organize():
    global organization_status
    if organization_status["running"]:
        return jsonify({"status": "error", "message": "Organization already in progress."}), 409

    folder_path = request.form.get('folder_path')
    if not folder_path:
        return jsonify({"status": "error", "message": "Folder path is required."}), 400

    thread = threading.Thread(target=run_organization_task, args=(folder_path,))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "success", "message": "Organization started."})

@app.route('/status')
def status():
    global organization_status
    return jsonify(organization_status)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
