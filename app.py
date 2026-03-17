import io
import os
import sqlite3
import uuid
from datetime import datetime
from urllib.parse import urlparse

import qrcode
from flask import (
    Flask,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "qr_tracker.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT,
            target_url TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL,
            clicked_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            referer TEXT,
            FOREIGN KEY (link_id) REFERENCES links (id)
        );
        """
    )
    db.commit()


def normalize_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url


def generate_unique_code(db):
    while True:
        code = uuid.uuid4().hex[:7]
        exists = db.execute("SELECT 1 FROM links WHERE code = ?", (code,)).fetchone()
        if not exists:
            return code


@app.route("/", methods=["GET"])
def index():
    db = get_db()
    links = db.execute(
        """
        SELECT l.id, l.code, l.name, l.target_url, l.created_at, COUNT(c.id) AS total_clicks
        FROM links l
        LEFT JOIN clicks c ON c.link_id = l.id
        GROUP BY l.id
        ORDER BY l.created_at DESC
        """
    ).fetchall()
    return render_template("index.html", links=links)


@app.route("/create", methods=["POST"])
def create_link():
    db = get_db()
    target_url = request.form.get("target_url", "").strip()
    name = request.form.get("name", "").strip() or None
    custom_code = request.form.get("custom_code", "").strip().lower() or None

    if not target_url:
        flash("Debes ingresar una URL válida.")
        return redirect(url_for("index"))

    target_url = normalize_url(target_url)

    if custom_code:
        if not custom_code.replace("-", "").isalnum() or len(custom_code) < 3:
            flash("El alias debe tener al menos 3 caracteres alfanuméricos (puede incluir guión).")
            return redirect(url_for("index"))
        code = custom_code
        exists = db.execute("SELECT 1 FROM links WHERE code = ?", (code,)).fetchone()
        if exists:
            flash("Ese alias ya existe. Elige otro.")
            return redirect(url_for("index"))
    else:
        code = generate_unique_code(db)

    db.execute(
        "INSERT INTO links (code, name, target_url, created_at) VALUES (?, ?, ?, ?)",
        (code, name, target_url, datetime.utcnow().isoformat()),
    )
    db.commit()

    flash("QR creado correctamente.")
    return redirect(url_for("index"))


@app.route("/r/<code>")
def track_and_redirect(code):
    db = get_db()
    link = db.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
    if not link:
        return "Código no encontrado", 404

    db.execute(
        """
        INSERT INTO clicks (link_id, clicked_at, ip_address, user_agent, referer)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            link["id"],
            datetime.utcnow().isoformat(),
            request.headers.get("X-Forwarded-For", request.remote_addr),
            request.user_agent.string,
            request.headers.get("Referer"),
        ),
    )
    db.commit()

    return redirect(link["target_url"], code=302)


@app.route("/stats/<code>")
def stats(code):
    db = get_db()
    link = db.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
    if not link:
        return "Código no encontrado", 404

    total_clicks = db.execute("SELECT COUNT(*) AS c FROM clicks WHERE link_id = ?", (link["id"],)).fetchone()["c"]

    by_hour = db.execute(
        """
        SELECT substr(clicked_at, 1, 13) || ':00' AS hour_bucket, COUNT(*) AS clicks
        FROM clicks
        WHERE link_id = ?
        GROUP BY hour_bucket
        ORDER BY hour_bucket DESC
        LIMIT 48
        """,
        (link["id"],),
    ).fetchall()

    recent_clicks = db.execute(
        """
        SELECT clicked_at, ip_address, user_agent, referer
        FROM clicks
        WHERE link_id = ?
        ORDER BY clicked_at DESC
        LIMIT 100
        """,
        (link["id"],),
    ).fetchall()

    return render_template(
        "stats.html",
        link=link,
        total_clicks=total_clicks,
        by_hour=by_hour,
        recent_clicks=recent_clicks,
    )


@app.route("/qr/<code>.png")
def qr_image(code):
    db = get_db()
    link = db.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
    if not link:
        return "Código no encontrado", 404

    qr_url = url_for("track_and_redirect", code=code, _external=True)
    img = qrcode.make(qr_url)
    buff = io.BytesIO()
    img.save(buff, format="PNG")
    buff.seek(0)

    return Response(buff.read(), mimetype="image/png")


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
