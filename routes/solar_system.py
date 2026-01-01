from flask import Blueprint, render_template, jsonify

solar_system_bp = Blueprint(
    "solar_system",
    __name__,
    url_prefix="/solar-system"
)

@solar_system_bp.route("/")
def index():
    return render_template("solar_system/index.html")

@solar_system_bp.route("/api/objects")
def api_objects():
    return jsonify([])
