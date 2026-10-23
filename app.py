import os, io, sqlite3, secrets
from functools import wraps
from flask import Flask, request, redirect, url_for, session, send_file, flash, render_template_string, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from PIL import Image

APP_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get("MAC_DATA_DIR", os.path.join(APP_DIR, "data"))
UPLOAD_DIR = os.path.join(DATA_DIR, "logos")
DB_PATH = os.path.join(DATA_DIR, "mac_watermark.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("MAC_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB por archivo

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS watermarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            text_value TEXT,
            logo_filename TEXT,
            color TEXT NOT NULL DEFAULT '#777777',
            opacity REAL NOT NULL DEFAULT 0.22,
            size REAL NOT NULL DEFAULT 42,
            rotation REAL NOT NULL DEFAULT 35,
            position TEXT NOT NULL DEFAULT 'center',
            created_by TEXT NOT NULL
        )""")
        count = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            # First-run credentials can be overridden with environment variables.
            username = os.environ.get("MAC_ADMIN_USER", "MAC")
            password = os.environ.get("MAC_ADMIN_PASSWORD", "marcasdeagua")
            con.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                        (username, generate_password_hash(password), "admin"))

init_db()

LOGIN_PAGE = """
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Marcas de agua - Acceso</title><style>
body{font-family:Arial;background:#eef2f7;margin:0;display:grid;min-height:100vh;place-items:center;color:#1e293b}
.card{background:white;padding:30px;border-radius:14px;box-shadow:0 8px 28px #0001;width:min(360px,85vw)}
h1{color:#17365d;font-size:24px;margin-top:0}label{display:block;margin:14px 0 5px}input{box-sizing:border-box;width:100%;padding:11px;border:1px solid #cbd5e1;border-radius:7px}
button{margin-top:18px;width:100%;padding:12px;border:0;border-radius:7px;background:#17365d;color:white;font-weight:bold;cursor:pointer}.muted{color:#64748b;font-size:13px}
</style></head><body><div class="card"><h1>Marcas de agua</h1><p>MAC Servicios Ambientales Â· Control de marcas de agua para documentos PDF.</p>
{% with messages = get_flashed_messages() %}{% for m in messages %}<p style="color:#b91c1c">{{m}}</p>{% endfor %}{% endwith %}
<form method="post"><label>Usuario</label><input name="username" required autocomplete="username"><label>ContraseÃ±a</label><input name="password" type="password" required autocomplete="current-password"><button>Iniciar sesiÃ³n</button></form>
<p class="muted">Acceso inicial: MAC / marcasdeagua.</p></div></body></html>
"""

HOME_PAGE = """
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Marcas de agua</title><style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#f3f6fa;color:#172033;margin:0}
header{background:#17365d;color:white;padding:18px 5%;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
main{max-width:1100px;margin:25px auto;padding:0 16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
.card{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:20px;box-shadow:0 3px 12px #00000008}
h1{font-size:22px;margin:0}h2{font-size:18px;color:#17365d;margin-top:0}label{display:block;margin:12px 0 5px;font-size:14px;font-weight:bold}
input,select{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:7px;background:white}button,.btn{display:inline-block;background:#17365d;color:white;border:0;border-radius:7px;padding:11px 14px;cursor:pointer;text-decoration:none;font-weight:bold}
.secondary{background:#64748b}.danger{background:#a12b2b}.muted{color:#64748b;font-size:13px}.message{background:#fff7ed;border:1px solid #fed7aa;padding:10px;border-radius:7px;margin-bottom:14px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0;font-size:14px}th{background:#f8fafc}
.inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.inline input[type=checkbox]{width:auto}
</style></head><body>
<header><div><h1>Marcas de agua</h1><div>MAC Servicios Ambientales Â· Control de marcas de agua</div></div><div>SesiÃ³n: <b>{{user}}</b> ({{role}}) &nbsp; <a class="btn secondary" href="{{url_for('logout')}}">Salir</a></div></header>
<main>
{% with messages = get_flashed_messages() %}{% for m in messages %}<div class="message">{{m}}</div>{% endfor %}{% endwith %}
<div class="grid">
<section class="card"><h2>1. Guardar una marca de agua</h2>
<form method="post" action="{{url_for('create_watermark')}}" enctype="multipart/form-data">
<label>Nombre para identificarla</label><input name="name" placeholder="Ej. CONFIDENCIAL, LOGO MAC" required>
<label>Tipo</label><select name="kind" id="kind" onchange="toggleKind()"><option value="text">Texto</option><option value="logo">Logotipo / sello</option></select>
<div id="text-fields"><label>Texto</label><input name="text_value" placeholder="CONFIDENCIAL"></div>
<div id="logo-fields" style="display:none"><label>Archivo de imagen (PNG, JPG o WEBP)</label><input type="file" name="logo" accept=".png,.jpg,.jpeg,.webp"></div>
<label>Color del texto (ej. #777777)</label><input name="color" value="#777777" pattern="#[0-9a-fA-F]{6}" required>
<label>Transparencia (0.05 a 1.00)</label><input name="opacity" type="number" min="0.05" max="1" step="0.05" value="0.22" required>
<label>TamaÃ±o</label><input name="size" type="number" min="10" max="180" value="42" required>
<label>InclinaciÃ³n en grados (-90 a 90)</label><input name="rotation" type="number" min="-90" max="90" value="35" required>
<label>PosiciÃ³n</label><select name="position"><option value="center">Centro</option><option value="diagonal">Diagonal al centro</option><option value="top">Parte superior</option><option value="bottom">Parte inferior</option><option value="pattern">Logos pequeÃ±os en toda la hoja</option></select>
<button type="submit">Guardar marca</button>
</form></section>
<section class="card"><h2>2. Aplicar a un PDF</h2>
<form method="post" action="{{url_for('apply_watermark')}}" enctype="multipart/form-data">
<label>Selecciona el PDF</label><input type="file" name="pdf" accept=".pdf,application/pdf" required>
<label>Marca guardada</label><select name="watermark_id" required>{% for w in watermarks %}<option value="{{w.id}}">{{w.name}} â€” {{'Texto' if w.kind=='text' else 'Logotipo'}}</option>{% endfor %}</select>
<label>Aplicar a</label><select name="pages"><option value="all">Todas las pÃ¡ginas</option><option value="first">Solo primera pÃ¡gina</option></select>
<button type="submit" {% if not watermarks %}disabled{% endif %}>Generar PDF con marca</button>
<p class="muted">El archivo original no se modifica. El PDF resultante se descarga al terminar.</p></form>
</section></div>
<section class="card" style="margin-top:18px"><h2>3. Biblioteca de marcas guardadas</h2>
{% if watermarks %}<table><thead><tr><th>Nombre</th><th>Tipo</th><th>Vista / texto</th><th>Creada por</th><th></th></tr></thead><tbody>
{% for w in watermarks %}<tr><td>{{w.name}}</td><td>{{'Texto' if w.kind=='text' else 'Logotipo'}}</td><td>{{w.text_value if w.kind=='text' else w.logo_filename}}</td><td>{{w.created_by}}</td><td><form method="post" action="{{url_for('delete_watermark', watermark_id=w.id)}}" onsubmit="return confirm('Â¿Eliminar esta marca guardada?')"><button class="danger" type="submit">Eliminar</button></form></td></tr>{% endfor %}
</tbody></table>{% else %}<p>AÃºn no hay marcas guardadas. Crea la primera en el formulario.</p>{% endif %}
<p class="muted">La biblioteca se conserva en la base de datos local. Para que varios empleados compartan la misma biblioteca, el programa debe ejecutarse en un servidor comÃºn.</p></section>
{% if role == 'admin' %}<section class="card" style="margin-top:18px"><h2>AdministraciÃ³n de usuarios</h2><p class="muted">Crea accesos para empleados. Comparte las credenciales de forma segura.</p>
<form method="post" action="{{url_for('create_user')}}"><div class="grid"><div><label>Nuevo usuario</label><input name="username" required minlength="3"></div><div><label>ContraseÃ±a inicial</label><input name="password" type="password" required minlength="10"></div></div><button type="submit">Crear usuario</button></form>
<h3>Usuarios registrados</h3><table><tr><th>Usuario</th><th>Rol</th></tr>{% for u in users %}<tr><td>{{u.username}}</td><td>{{u.role}}</td></tr>{% endfor %}</table></section>{% endif %}
</main><script>function toggleKind(){let k=document.getElementById('kind').value;document.getElementById('text-fields').style.display=k==='text'?'block':'none';document.getElementById('logo-fields').style.display=k==='logo'?'block':'none';}</script></body></html>
"""

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def current_user():
    with db() as con:
        return con.execute("SELECT * FROM users WHERE id=?", (session.get("user_id"),)).fetchone()

def admin_required():
    user = current_user()
    if not user or user["role"] != "admin":
        abort(403)
    return user

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("home"))
        flash("Usuario o contraseÃ±a incorrectos.")
    return render_template_string(LOGIN_PAGE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    user = current_user()
    with db() as con:
        watermarks = con.execute("SELECT * FROM watermarks ORDER BY id DESC").fetchall()
        users = con.execute("SELECT username,role FROM users ORDER BY username").fetchall() if user["role"] == "admin" else []
    return render_template_string(HOME_PAGE, user=user["username"], role=user["role"],
                                  watermarks=watermarks, users=users)

@app.route("/watermarks/create", methods=["POST"])
@login_required
def create_watermark():
    user = current_user()
    name = request.form.get("name", "").strip()
    kind = request.form.get("kind", "text")
    text_value = request.form.get("text_value", "").strip()
    logo_filename = None
    if not name:
        flash("Escribe un nombre para la marca.")
        return redirect(url_for("home"))
    if kind not in ("text", "logo"):
        abort(400)
    if kind == "text" and not text_value:
        flash("Escribe el texto de la marca.")
        return redirect(url_for("home"))
    if kind == "logo":
        f = request.files.get("logo")
        if not f or not f.filename:
            flash("Selecciona una imagen para el logotipo.")
            return redirect(url_for("home"))
        ext = os.path.splitext(secure_filename(f.filename))[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            flash("Formato no permitido. Usa PNG, JPG o WEBP.")
            return redirect(url_for("home"))
        logo_filename = secrets.token_hex(12) + ext
        f.save(os.path.join(UPLOAD_DIR, logo_filename))
        try:
            with Image.open(os.path.join(UPLOAD_DIR, logo_filename)) as im:
                im.verify()
        except Exception:
            os.remove(os.path.join(UPLOAD_DIR, logo_filename))
            flash("La imagen no es vÃ¡lida.")
            return redirect(url_for("home"))
    try:
        color = request.form.get("color", "#777777")
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError()
        opacity = max(0.05, min(1.0, float(request.form.get("opacity", "0.22"))))
        size = max(10, min(180, float(request.form.get("size", "42"))))
        rotation = max(-90, min(90, float(request.form.get("rotation", "35"))))
    except ValueError:
        flash("Revisa color, transparencia, tamaÃ±o e inclinaciÃ³n.")
        return redirect(url_for("home"))
    position = request.form.get("position", "center")
    if position not in ("center", "diagonal", "top", "bottom", "pattern"):
        position = "center"
    with db() as con:
        con.execute("""INSERT INTO watermarks(name,kind,text_value,logo_filename,color,opacity,size,rotation,position,created_by)
        VALUES(?,?,?,?,?,?,?,?,?,?)""", (name,kind,text_value or None,logo_filename,color,opacity,size,rotation,position,user["username"]))
    flash("Marca guardada correctamente.")
    return redirect(url_for("home"))

@app.route("/watermarks/<int:watermark_id>/delete", methods=["POST"])
@login_required
def delete_watermark(watermark_id):
    user = current_user()
    with db() as con:
        w = con.execute("SELECT * FROM watermarks WHERE id=?", (watermark_id,)).fetchone()
        if not w:
            abort(404)
        if user["role"] != "admin" and w["created_by"] != user["username"]:
            abort(403)
        con.execute("DELETE FROM watermarks WHERE id=?", (watermark_id,))
    if w["logo_filename"]:
        try: os.remove(os.path.join(UPLOAD_DIR, w["logo_filename"]))
        except FileNotFoundError: pass
    flash("Marca eliminada.")
    return redirect(url_for("home"))

def make_overlay(width, height, wm):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))
    opacity = float(wm["opacity"])
    color = HexColor(wm["color"] or "#777777")
    color.alpha = opacity
    c.saveState()
    pos = wm["position"]
    if pos == "pattern" and wm["kind"] == "logo":
        logo_path = os.path.join(UPLOAD_DIR, wm["logo_filename"] or "")
        if not os.path.isfile(logo_path):
            c.restoreState(); c.save(); packet.seek(0); return packet
        # PatrÃ³n repetido de logos pequeÃ±os que cubre toda la pÃ¡gina.
        logo_w = max(24, float(wm["size"]))
        try:
            with Image.open(logo_path) as im:
                aspect = im.height / im.width
        except Exception:
            aspect = 0.6
        logo_h = logo_w * aspect
        step_x = logo_w * 1.65
        step_y = logo_h * 2.0
        c.setFillAlpha(opacity)
        c.rotate(float(wm["rotation"]))
        y = -height
        row = 0
        while y < height * 1.5:
            x = -width if row % 2 == 0 else -width + step_x / 2
            while x < width * 1.5:
                c.drawImage(logo_path, x, y, width=logo_w, height=logo_h, preserveAspectRatio=True, anchor='c', mask='auto')
                x += step_x
            y += step_y
            row += 1
    else:
        if pos == "top":
            x, y = width/2, height - min(height*0.12, 70)
        elif pos == "bottom":
            x, y = width/2, min(height*0.12, 70)
        else:
            x, y = width/2, height/2
        c.translate(x, y)
        c.rotate(float(wm["rotation"]))
    if wm["kind"] == "text":
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", float(wm["size"]))
        c.drawCentredString(0, 0, wm["text_value"] or "")
    elif pos != "pattern":
        logo_path = os.path.join(UPLOAD_DIR, wm["logo_filename"] or "")
        if not os.path.isfile(logo_path):
            c.restoreState(); c.save(); packet.seek(0); return packet
        # Preserve transparency for PNG; reportlab supports mask="auto".
        side = float(wm["size"]) * 3
        c.setFillAlpha(opacity)
        c.drawImage(logo_path, -side/2, -side/2, width=side, height=side,
                    preserveAspectRatio=True, anchor='c', mask='auto')
    c.restoreState()
    c.save()
    packet.seek(0)
    return packet

@app.route("/apply", methods=["POST"])
@login_required
def apply_watermark():
    f = request.files.get("pdf")
    if not f or not f.filename or not f.filename.lower().endswith(".pdf"):
        flash("Selecciona un archivo PDF vÃ¡lido.")
        return redirect(url_for("home"))
    try:
        reader = PdfReader(f.stream, strict=False)
        if reader.is_encrypted:
            flash("El PDF estÃ¡ protegido con contraseÃ±a. DesbloquÃ©alo antes de cargarlo.")
            return redirect(url_for("home"))
        if len(reader.pages) > 500:
            flash("Por seguridad, el lÃ­mite es de 500 pÃ¡ginas por documento.")
            return redirect(url_for("home"))
        wm_id = int(request.form.get("watermark_id", "0"))
        with db() as con:
            wm = con.execute("SELECT * FROM watermarks WHERE id=?", (wm_id,)).fetchone()
        if not wm:
            flash("Selecciona una marca de agua guardada.")
            return redirect(url_for("home"))
        pages_choice = request.form.get("pages", "all")
        writer = PdfWriter()
        for index, page in enumerate(reader.pages):
            if pages_choice == "first" and index > 0:
                writer.add_page(page)
                continue
            box = page.mediabox
            width, height = float(box.width), float(box.height)
            overlay_pdf = PdfReader(make_overlay(width, height, wm))
            page.merge_page(overlay_pdf.pages[0])
            writer.add_page(page)
        writer.add_metadata({"/Producer": "MAC PDF Watermark"})
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        original = secure_filename(f.filename) or "documento.pdf"
        out_name = os.path.splitext(original)[0] + "_con_marca_MAC.pdf"
        return send_file(output, as_attachment=True, download_name=out_name, mimetype="application/pdf")
    except Exception:
        flash("No se pudo procesar el PDF. Comprueba que el archivo no estÃ© daÃ±ado y vuelve a intentarlo.")
        return redirect(url_for("home"))

@app.route("/users/create", methods=["POST"])
@login_required
def create_user():
    admin = admin_required()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if len(username) < 3 or len(password) < 10:
        flash("El usuario debe tener al menos 3 caracteres y la contraseÃ±a 10.")
        return redirect(url_for("home"))
    try:
        with db() as con:
            con.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                        (username, generate_password_hash(password), "user"))
        flash("Usuario creado.")
    except sqlite3.IntegrityError:
        flash("Ese nombre de usuario ya existe.")
    return redirect(url_for("home"))

@app.errorhandler(403)
def forbidden(e):
    return "No tienes permiso para realizar esta acciÃ³n.", 403

@app.errorhandler(413)
def too_large(e):
    return "El archivo supera el lÃ­mite de 25 MB.", 413

if __name__ == "__main__":
    # Local use only. For internet deployment, use a production server and HTTPS.
    app.run(host="0.0.0.0", port=5000, debug=False)

