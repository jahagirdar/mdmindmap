import os
import subprocess
import json
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# Global state (set by serve())
MINDMAP_DATA = None
OUT_HTML = None


@app.route("/")
def index():
    """Serve the cached HTML mindmap file."""
    global OUT_HTML
    if OUT_HTML and os.path.exists(OUT_HTML):
        return send_file(OUT_HTML)
    return "Mindmap HTML not found. Did you run with --rebuild?", 500


@app.route("/data")
def get_data():
    """Return parsed mindmap JSON (for dynamic reload)."""
    global MINDMAP_DATA
    if MINDMAP_DATA:
        return jsonify(MINDMAP_DATA)
    return jsonify({"error": "No mindmap data"}), 500


@app.route("/edit")
def edit_file():
    """Open a node’s file in $EDITOR."""
    path = request.args.get("path")
    if not path or not os.path.exists(path):
        return jsonify({"error": "file not found"}), 404

    editor = os.environ.get("EDITOR", "vim")
    try:
        subprocess.Popen([editor, path])
        return jsonify({"status": f"Opened {path} in {editor}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



def serve(data, out_html, port=5000):
    """Start Flask server with cached mindmap data + HTML file path."""
    global MINDMAP_DATA, OUT_HTML
    MINDMAP_DATA = data
    OUT_HTML = out_html
    app.run(host="127.0.0.1", port=port, debug=False)

@app.route("/reload")
def reload():
    path = request.args.get("path")
    if not path or not os.path.exists(path):
        return jsonify({"error": "File not found", "content": ""})
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except Exception as e:
        content = f"(error reading file: {e})"
    return jsonify({"path": path, "content": content})

