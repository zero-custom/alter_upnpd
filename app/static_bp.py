import os
from flask import Blueprint, send_from_directory

static_bp = Blueprint("static_assets", __name__)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@static_bp.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)
