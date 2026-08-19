from functools import wraps
from flask import Blueprint, render_template, request, abort, jsonify
from flask_login import login_required, current_user

from utils.command_center import COMMANDS, run_command, get_service_state, SERVICES

admin_command_center_bp = Blueprint(
	"admin_command_center",
	__name__,
	url_prefix="/admin"
)

def admin_required(fn):
	@wraps(fn)
	@login_required
	def wrapper(*args, **kwargs):
		if getattr(current_user, "role", None) != "admin":
			abort(403)
		return fn(*args, **kwargs)
	return wrapper

# --- Dashboard API (used by service modal in layout.html) ---

@admin_command_center_bp.route("/api/run-command", methods=["POST"])
@admin_required
def api_run_command():
	data = request.get_json(silent=True) or {}
	key = (data.get("cmd") or "").strip()

	out, code = run_command(key)
	return jsonify({
		"cmd": key,
		"exit_code": code,
		"output": out
	})

@admin_command_center_bp.route("/api/service/<service>/<action>", methods=["GET", "POST"])
@admin_required
def service_action(service, action):
	# whitelist
	if service not in SERVICES.values():
		return jsonify({"success": False, "error": "Unknown service"}), 404

	if action == "status":
		# reuse your command_center commands if you want, or call get_service_state
		out, code = run_command(f"status_{service}")
		return jsonify({"success": True, "output": out, "code": code})

	if action == "logs":
		out, code = run_command(f"logs_{service}")
		return jsonify({"success": True, "output": out, "code": code})

	if action == "restart":
		if request.method != "POST":
			return jsonify({"success": False, "error": "POST required"}), 405
		out, code = run_command(f"restart_{service}")
		return jsonify({"success": True, "output": out, "code": code})

	return jsonify({"success": False, "error": "Unknown action"}), 404
