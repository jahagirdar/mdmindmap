import os
import subprocess
import json
from flask import Flask, request, jsonify, send_file
from pathlib import Path
from .core import render_html, parse_frontmatter

app = Flask(__name__)

# Globals set by serve()
MINDMAP_DATA = None
OUT_HTML = None

@app.route("/")
def index():
    global OUT_HTML
    if OUT_HTML and Path(OUT_HTML).exists():
        return send_file(OUT_HTML)
    return "Mindmap HTML not found. Run the CLI with --rebuild.", 500

@app.route("/data")
def data():
    global MINDMAP_DATA
    if MINDMAP_DATA is None:
        return jsonify({"error": "no data"}), 500
    return jsonify(MINDMAP_DATA)

@app.route("/edit")
def edit():
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "missing path"}), 400
    if not os.path.exists(path):
        return jsonify({"error": "file not found"}), 404
    editor = os.environ.get("EDITOR", "vim")
    try:
        subprocess.Popen([editor, path])
        return jsonify({"status": f"Opened {path} in {editor}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/reload")
def reload():
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "missing path"}), 400
    # if external link, just return error
    if path.startswith("http://") or path.startswith("https://") or path.startswith("mailto:"):
        return jsonify({"error": "external link"}), 400
    if not os.path.exists(path):
        return jsonify({"error": "file not found"}), 404
    try:
        txt = open(path, encoding="utf-8").read()
        # strip frontmatter and render body
        fm, body = parse_frontmatter(txt)
        html = render_html(body)
        return jsonify({"path": path, "content": html})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def serve(data: dict, out_html: str, port: int = 5000):
    """
    Set in-memory data and start Flask app; `out_html` is the HTML file path
    that will be served at '/' by this server.
    """
    global MINDMAP_DATA, OUT_HTML
    MINDMAP_DATA = data
    OUT_HTML = out_html
    print(f"Serving mindmap: http://127.0.0.1:{port}/ (ctrl-c to stop)")
    app.run(host="127.0.0.1", port=port, threaded=True)
