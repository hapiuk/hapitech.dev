# journal_api.py
import json
import os
import re
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from utils.journal_db import get_db

bp_journal = Blueprint("bp_journal", __name__, url_prefix="/api")


ALLOWED_KINDS = {"planet", "moon", "satellite", "station", "general"}
MAX_RECENT = 50
MAX_ENTITY = 200
MAX_TITLE = 140

# Keep uploads in your static folder
UPLOAD_SUBDIR = os.path.join("uploads", "journal")  # under /static/


def iso_now():
	return datetime.now(timezone.utc).isoformat()


def owner_required(fn):
	"""This journal is Aaron's personal one — only the client-portal admin/client
	login (not the public Solar Journal accounts) should be able to write to it.
	"""
	from functools import wraps

	@wraps(fn)
	def wrapper(*args, **kwargs):
		if not current_user.is_authenticated or getattr(current_user, "role", None) not in ("admin", "client"):
			return jsonify({"success": False, "message": "Login required."}), 401
		return fn(*args, **kwargs)

	return wrapper


def safe_filename(name: str) -> str:
	name = (name or "").strip()
	name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
	return name[:180] or "image"


def parse_tags(value):
	"""
	Accepts:
	- list (already)
	- JSON string list
	- comma-separated string
	"""
	if value is None:
		return []
	if isinstance(value, list):
		return [str(x).strip() for x in value if str(x).strip()]

	if isinstance(value, str):
		s = value.strip()
		if not s:
			return []
		# Try JSON list
		try:
			j = json.loads(s)
			if isinstance(j, list):
				return [str(x).strip() for x in j if str(x).strip()]
		except Exception:
			pass
		# Comma list
		return [t.strip() for t in s.split(",") if t.strip()]

	return []


def row_to_entry(r):
        # sqlite3.Row does NOT implement .get(); use key checks + __getitem__
        def has(k):
                try:
                        return k in r.keys()
                except Exception:
                        return False

        def val(k, default=None):
                try:
                        return r[k]
                except Exception:
                        return default

        # Backwards compatible defaults for older rows
        tags = []
        try:
                tags = json.loads(val("tags_json") or "[]")
        except Exception:
                tags = []

        images = []
        try:
                images = json.loads((val("images_json") or "[]"))
        except Exception:
                images = []

        snapshot = None
        try:
                sj = val("snapshot_json")
                if sj:
                        snapshot = json.loads(sj)
        except Exception:
                snapshot = None

        return {
                "id": val("id"),
                "kind": val("entity_kind"),          # frontend expects kind/name
                "name": val("entity_name"),
                "parent": val("entity_parent"),
                "title": val("title"),
                "body": val("body"),
                "tags": tags,
                "images": images,
                "snapshot": snapshot,
                "created_at": val("created_at"),
                "updated_at": val("updated_at"),
        }


def ensure_upload_dir(entry_id: str) -> str:
	# physical path
	static_root = current_app.static_folder  # e.g. www/hapitech/static
	base = os.path.join(static_root, UPLOAD_SUBDIR, entry_id)
	os.makedirs(base, exist_ok=True)
	return base


def save_images(entry_id: str):
	"""
	Saves uploaded images from multipart field name "images".
	Returns list of public URLs.
	"""
	files = request.files.getlist("images") if request.files else []
	if not files:
		return []

	out_dir = ensure_upload_dir(entry_id)
	urls = []

	for f in files:
		if not f or not getattr(f, "filename", ""):
			continue

		fn = safe_filename(f.filename)
		# Prevent collisions
		prefix = uuid.uuid4().hex[:8]
		fn2 = f"{prefix}_{fn}"
		path = os.path.join(out_dir, fn2)
		f.save(path)

		public_url = f"/static/{UPLOAD_SUBDIR}/{entry_id}/{fn2}".replace("\\", "/")
		urls.append(public_url)

	return urls


def get_payload():
	"""
	Accept both JSON and multipart form.
	"""
	if request.is_json:
		return request.get_json(silent=True) or {}, "json"

	# multipart / form
	data = dict(request.form or {})
	return data, "form"


# -------------------------
# Journal routes expected by UI
# -------------------------

@bp_journal.get("/journal/recent")
def journal_recent():
	limit = request.args.get("limit", default=10, type=int)
	limit = max(1, min(limit, MAX_RECENT))

	conn = get_db()
	rows = conn.execute(
		"SELECT * FROM journal_entries ORDER BY created_at DESC LIMIT ?",
		(limit,)
	).fetchall()
	conn.close()

	return jsonify({"ok": True, "items": [row_to_entry(r) for r in rows]})


@bp_journal.get("/journal/entity")
def journal_entity():
	kind = (request.args.get("kind") or "").strip().lower()
	name = (request.args.get("name") or "").strip()

	if kind not in ALLOWED_KINDS:
		return jsonify({"ok": False, "error": "Invalid kind"}), 400

	# For general, we allow name to default
	if kind == "general" and not name:
		name = "General"

	if not name:
		return jsonify({"ok": False, "error": "Missing name"}), 400

	limit = request.args.get("limit", default=50, type=int)
	limit = max(1, min(limit, MAX_ENTITY))

	conn = get_db()
	rows = conn.execute(
		"""
		SELECT * FROM journal_entries
		WHERE entity_kind = ? AND entity_name = ?
		ORDER BY created_at DESC
		LIMIT ?
		""",
		(kind, name, limit)
	).fetchall()
	conn.close()

	return jsonify({
		"ok": True,
		"kind": kind,
		"name": name,
		"items": [row_to_entry(r) for r in rows],
	})


@bp_journal.get("/journal/entry/<entry_id>")
def journal_get_entry(entry_id):
	conn = get_db()
	row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
	conn.close()

	if not row:
		return jsonify({"ok": False, "error": "Not found"}), 404

	return jsonify({"ok": True, "item": row_to_entry(row)})


@bp_journal.post("/journal/create")
@owner_required
def journal_create():
	data, mode = get_payload()

	kind = (data.get("kind") or data.get("entity_kind") or "").strip().lower()
	name = (data.get("name") or data.get("entity_name") or "").strip()
	parent = (data.get("parent") or "").strip() or None

	title = (data.get("title") or "").strip()
	body = (data.get("body") or "").strip()

	tags = parse_tags(data.get("tags"))

	snapshot_raw = data.get("snapshot")
	snapshot_json = None
	if snapshot_raw:
		try:
			# allow already-dict from json mode
			if isinstance(snapshot_raw, (dict, list)):
				snapshot_json = json.dumps(snapshot_raw)
			else:
				snapshot_json = json.dumps(json.loads(str(snapshot_raw)))
		except Exception:
			# store as string if it isn't valid JSON
			snapshot_json = json.dumps({"raw": str(snapshot_raw)})

	# defaults for general
	if not kind:
		kind = "general"
	if kind == "general" and not name:
		name = "General"

	if kind not in ALLOWED_KINDS:
		return jsonify({"ok": False, "error": "Invalid kind"}), 400
	if not name:
		return jsonify({"ok": False, "error": "Missing name"}), 400
	if not title:
		return jsonify({"ok": False, "error": "Missing title"}), 400
	if not body:
		return jsonify({"ok": False, "error": "Missing body"}), 400
	if len(title) > MAX_TITLE:
		return jsonify({"ok": False, "error": f"Title too long (max {MAX_TITLE})"}), 400

	entry_id = uuid.uuid4().hex
	created_at = iso_now()
	updated_at = created_at

	# images: only from multipart
	image_urls = []
	if mode == "form":
		image_urls = save_images(entry_id)

	conn = get_db()
	conn.execute(
		"""
		INSERT INTO journal_entries (
			id, entity_kind, entity_name, entity_parent,
			title, body, tags_json,
			created_at, updated_at,
			snapshot_json, images_json
		)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			entry_id, kind, name, parent,
			title, body, json.dumps(tags),
			created_at, updated_at,
			snapshot_json, json.dumps(image_urls),
		)
	)
	conn.commit()

	row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
	conn.close()

	return jsonify({"ok": True, "item": row_to_entry(row)}), 201


@bp_journal.post("/journal/update")
@owner_required
def journal_update():
	data, mode = get_payload()

	entry_id = (data.get("id") or "").strip()
	if not entry_id:
		return jsonify({"ok": False, "error": "Missing id"}), 400

	conn = get_db()
	row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
	if not row:
		conn.close()
		return jsonify({"ok": False, "error": "Not found"}), 404

	# Existing values
	existing = row_to_entry(row)

	title = (data.get("title") or existing["title"] or "").strip()
	body = (data.get("body") or existing["body"] or "").strip()

	# tags can come as list/json/comma string
	tags = parse_tags(data.get("tags"))
	if tags == [] and ("tags" not in data):
		tags = existing.get("tags") or []

	parent = (data.get("parent") or existing.get("parent") or "").strip() or None

	snapshot_raw = data.get("snapshot")
	snapshot_json = row["snapshot_json"]
	if snapshot_raw:
		try:
			if isinstance(snapshot_raw, (dict, list)):
				snapshot_json = json.dumps(snapshot_raw)
			else:
				snapshot_json = json.dumps(json.loads(str(snapshot_raw)))
		except Exception:
			snapshot_json = json.dumps({"raw": str(snapshot_raw)})

	# merge images (append new uploads)
	images = existing.get("images") or []
	if mode == "form":
		new_urls = save_images(entry_id)
		if new_urls:
			images = images + new_urls

	updated_at = iso_now()

	conn.execute(
		"""
		UPDATE journal_entries
		SET title = ?, body = ?, tags_json = ?, entity_parent = ?,
		    updated_at = ?, snapshot_json = ?, images_json = ?
		WHERE id = ?
		""",
		(
			title, body, json.dumps(tags), parent,
			updated_at, snapshot_json, json.dumps(images),
			entry_id
		)
	)
	conn.commit()

	row2 = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
	conn.close()

	return jsonify({"ok": True, "item": row_to_entry(row2)})



# -------------------------
# Aliases to match frontend endpoints (so UI can call /api/journal/create + /api/journal/update)
# These keep your existing /journal/* routes intact.
# -------------------------

@bp_journal.post("/create")
@owner_required
def journal_create_alias():
        return journal_create()

@bp_journal.post("/update")
@owner_required
def journal_update_alias():
        return journal_update()

@bp_journal.get("/entry/<entry_id>")
def journal_get_entry_alias(entry_id):
        return journal_get_entry(entry_id)

# -------------------------
# Backwards compatible routes (optional)
# Keep these if anything else calls /api/recent or /api/entity or /api/entry
# -------------------------

@bp_journal.get("/recent")
def journal_recent_legacy():
	return journal_recent()

@bp_journal.get("/entity")
def journal_entity_legacy():
	return journal_entity()

@bp_journal.post("/entry")
@owner_required
def journal_create_entry_legacy():
	# Legacy JSON format: entity_kind/entity_name
	data = request.get_json(silent=True) or {}
	data2 = {
		"kind": data.get("entity_kind"),
		"name": data.get("entity_name"),
		"title": data.get("title"),
		"body": data.get("body"),
		"tags": data.get("tags"),
	}
	# spoof request.is_json path via calling create handler logic directly
	# simplest: temporarily reuse journal_create with json mode:
	# (we’ll just inline-call the create logic)
	with current_app.test_request_context(json=data2):
		return journal_create()


# -------------------------
# Goals API stays as-is (your original)
# -------------------------
def row_to_goal(r):
	return {
		"id": r["id"],
		"title": r["title"],
		"description": r["description"],
		"status": r["status"],
		"entity_kind": r["entity_kind"],
		"entity_name": r["entity_name"],
		"created_at": r["created_at"],
		"due_at": r["due_at"],
	}

@bp_journal.get("/goals")
def goals_list():
	status = (request.args.get("status") or "").strip().lower()
	where = ""
	params = []

	if status:
		if status not in {"todo", "doing", "done"}:
			return jsonify({"ok": False, "error": "Invalid status"}), 400
		where = "WHERE status = ?"
		params.append(status)

	conn = get_db()
	rows = conn.execute(
		f"SELECT * FROM goals {where} ORDER BY created_at DESC",
		params
	).fetchall()
	conn.close()

	return jsonify({"ok": True, "items": [row_to_goal(r) for r in rows]})

@bp_journal.post("/goals")
@owner_required
def goals_create():
	data = request.get_json(silent=True) or {}

	title = (data.get("title") or "").strip()
	description = (data.get("description") or "").strip()
	status = (data.get("status") or "todo").strip().lower()
	entity_kind = (data.get("entity_kind") or "").strip().lower() or None
	entity_name = (data.get("entity_name") or "").strip() or None
	due_at = (data.get("due_at") or "").strip() or None

	if not title:
		return jsonify({"ok": False, "error": "Missing title"}), 400
	if not description:
		return jsonify({"ok": False, "error": "Missing description"}), 400
	if status not in {"todo", "doing", "done"}:
		return jsonify({"ok": False, "error": "Invalid status"}), 400

	if entity_kind is not None and entity_kind not in {"planet", "moon", "satellite", "station"}:
		return jsonify({"ok": False, "error": "Invalid entity_kind"}), 400

	goal_id = uuid.uuid4().hex
	created_at = iso_now()

	conn = get_db()
	conn.execute(
		"""
		INSERT INTO goals (id, title, description, status, entity_kind, entity_name, created_at, due_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(goal_id, title, description, status, entity_kind, entity_name, created_at, due_at)
	)
	conn.commit()

	row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
	conn.close()

	return jsonify({"ok": True, "item": row_to_goal(row)}), 201

@bp_journal.patch("/goals/<goal_id>")
@owner_required
def goals_patch(goal_id):
	data = request.get_json(silent=True) or {}

	allowed = {"title", "description", "status", "due_at"}
	updates = []
	params = []

	for k in allowed:
		if k in data:
			if k == "status":
				v = (data[k] or "").strip().lower()
				if v not in {"todo", "doing", "done"}:
					return jsonify({"ok": False, "error": "Invalid status"}), 400
				updates.append("status = ?")
				params.append(v)
			else:
				v = (data[k] or "").strip()
				updates.append(f"{k} = ?")
				params.append(v)

	if not updates:
		return jsonify({"ok": False, "error": "No valid fields to update"}), 400

	params.append(goal_id)

	conn = get_db()
	conn.execute(f"UPDATE goals SET {', '.join(updates)} WHERE id = ?", params)
	conn.commit()

	row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
	conn.close()

	if not row:
		return jsonify({"ok": False, "error": "Goal not found"}), 404

	return jsonify({"ok": True, "item": row_to_goal(row)})