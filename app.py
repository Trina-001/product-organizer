# app.py
from flask import Flask, render_template, request, jsonify
import os
import sys
import threading
import time

# Add the directory containing b-up.py to the Python path
# This assumes b-up.py is in the same directory as app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import script_org # Import your modified script

# Initialize Flask app, specifying the current directory as the template folder
app = Flask(__name__, template_folder='.')

# Global variable to store organization status and messages
# In a production environment, consider a more robust solution like a database
# or a dedicated message queue for long-running tasks.
organization_status = {
    "running": False,
    "progress": 0, # Percentage
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
        # Override the _log_progress function in b_up to capture messages
        # This is a simple way to redirect logs to our status variable.
        # A more robust solution would involve passing a logger object.
        original_log_progress = script_org._log_progress
        def web_log_progress(message):
            original_log_progress(message) # Still print to console
            organization_status["messages"].append(message)
            # Simple progress update based on number of messages
            # You might want a more sophisticated progress tracking in b_up.py
            organization_status["progress"] = min(100, organization_status["progress"] + 1)
        script_org._log_progress = web_log_progress

        success, messages = script_org.organize_files_web(folder_path)
        organization_status["messages"] = messages # Ensure all messages are captured
        organization_status["completed"] = True
        organization_status["progress"] = 100
        if not success:
            organization_status["error"] = "Organization failed. Check logs for details."
    except Exception as e:
        organization_status["error"] = str(e)
        organization_status["messages"].append(f"An unexpected error occurred: {e}")
        organization_status["completed"] = True
        organization_status["progress"] = 100
    finally:
        organization_status["running"] = False
        # Restore original log function
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

    # Start the organization task in a separate thread
    # This prevents the web request from timing out during a long operation
    thread = threading.Thread(target=run_organization_task, args=(folder_path,))
    thread.daemon = True # Allow the main program to exit even if thread is running
    thread.start()

    return jsonify({"status": "success", "message": "Organization started."})

@app.route('/status')
def status():
    global organization_status
    return jsonify(organization_status)

if __name__ == '__main__':
    app.run(debug=True) # Set debug=False for production
