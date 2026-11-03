
import os
import hmac
import calendar
from datetime import datetime, date, timedelta
from functools import wraps
import math
import uuid

from flask import send_from_directory

from werkzeug.utils import secure_filename

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, flash
)
from dotenv import load_dotenv

from database import get_db, init_db, migrar_citas

load_dotenv()

app = Flask(__name__)

# ---------------------------------
# CONFIGURACIÓN DE COMPROBANTES
# ---------------------------------

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

CARPETA_COMPROBANTES = (
    os.path.join(app.instance_path, "comprobantes")
)

os.makedirs(CARPETA_COMPROBANTES, exist_ok=True)

EXTENSIONES_PERMITIDAS = {
    ".jpg", ".jpeg", ".png", ".webp"
}


app.secret_key = os.getenv("SECRET_KEY", "clave-solo-desarrollo")

ADMIN_USER = os.getenv("ADMIN_USER", "barbero")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "cambiar-password")

init_db()
migrar_citas()


# ---------------------------------
# SEGURIDAD
# ---------------------------------

def requiere_login(func):
    @wraps(func)
    def decorada(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return decorada

@app.route("/admin/login", methods=["GET", "POST"])
def login():

    if session.get("admin"):
        return redirect(url_for("admin"))

    if request.method == "POST":

        usuario = request.form.get("usuario", "")
        password = request.form.get("password", "")

        usuario_valido = hmac.compare_digest(
            usuario, ADMIN_USER
        )

        password_valido = hmac.compare_digest(
            password, ADMIN_PASSWORD
        )

        if usuario_valido and password_valido:
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin"))

        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.route("/admin/logout")
@requiere_login
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin/comprobantes/<nombre_archivo>")
@requiere_login
def ver_comprobante(nombre_archivo):

    # Evitar rutas manipuladas
    if os.path.basename(nombre_archivo) != nombre_archivo:
        return "Archivo no válido", 400

    return send_from_directory(
        CARPETA_COMPROBANTES,
        nombre_archivo
    )

# ---------------------------------
# PÁGINA PRINCIPAL
# ---------------------------------


@app.route("/")
def inicio():
    with get_db() as db:
        servicios = db.execute("""
            SELECT *
            FROM servicios
            WHERE activo = 1
            ORDER BY id
        """).fetchall()

        filas = db.execute("""
            SELECT clave, valor
            FROM configuracion
        """).fetchall()

    configuracion = {
        fila["clave"]: fila["valor"]
        for fila in filas
    }

    return render_template(
        "index.html",
        servicios=servicios,
        configuracion=configuracion
    )



# ---------------------------------
# CALENDARIO ADMINISTRATIVO
# ---------------------------------

@app.route("/admin")
@requiere_login
def admin():

    hoy = date.today()

    mes = request.args.get("mes", hoy.month, type=int)
    anio = request.args.get("anio", hoy.year, type=int)

    if mes < 1 or mes > 12 or anio < 2020 or anio > 2100:
        return "Fecha inválida", 400

    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])

    inicio = primer_dia.isoformat()
    fin = ultimo_dia.isoformat()

    calendario = calendar.Calendar(firstweekday=0)
    semanas = calendario.monthdatescalendar(anio, mes)

    with get_db() as db:

        citas = db.execute("""
            SELECT
                c.id,
                c.cliente,
                c.telefono,
                c.fecha,
                c.hora,
                c.estado,
                s.nombre AS servicio,
                s.precio,
                s.duracion
            FROM citas c
            JOIN servicios s ON s.id = c.servicio_id
            WHERE c.fecha BETWEEN ? AND ?
            ORDER BY c.fecha, c.hora
        """, (inicio, fin)).fetchall()

        estadisticas = db.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN estado = 'pendiente'
                    THEN 1 ELSE 0 END) AS pendientes,
                SUM(CASE WHEN estado = 'confirmada'
                    THEN 1 ELSE 0 END) AS confirmadas,
                SUM(CASE WHEN estado = 'cancelada'
                    THEN 1 ELSE 0 END) AS canceladas
            FROM citas
        """).fetchone()

    citas_por_dia = {}

    for cita in citas:
        citas_por_dia.setdefault(cita["fecha"], []).append(dict(cita))

    meses = [
        "Enero", "Febrero", "Marzo", "Abril",
        "Mayo", "Junio", "Julio", "Agosto",
        "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    return render_template(
        "admin.html",
        semanas=semanas,
        citas_por_dia=citas_por_dia,
        estadisticas=estadisticas,
        mes=mes,
        anio=anio,
        nombre_mes=meses[mes - 1],
        hoy=hoy.isoformat(),
        fecha_seleccionada=hoy.isoformat()
    )


# ---------------------------------
# CONSULTAR CITAS DE UN DÍA
# ---------------------------------


@app.route("/api/admin/citas")
@requiere_login
def admin_citas():

    fecha = request.args.get("fecha")

    try:
        date.fromisoformat(fecha)
    except (ValueError, TypeError):
        return jsonify({"error": "Fecha inválida"}), 400

    with get_db() as db:
        citas = db.execute("""
            SELECT
                c.id,
                c.cliente,
                c.telefono,
                c.fecha,
                c.hora,
                c.estado,

                s.nombre AS servicio,

                COALESCE(c.precio_reservado, s.precio) AS precio,
                s.duracion,

                COALESCE(c.monto_deposito, 0) AS monto_deposito,
                COALESCE(c.pago_estado, 'pendiente') AS pago_estado,
                c.comprobante

            FROM citas c
            JOIN servicios s ON s.id = c.servicio_id

            WHERE c.fecha = ?

            ORDER BY c.hora
        """, (fecha,)).fetchall()

    return jsonify([dict(cita) for cita in citas])


# ---------------------------------
# CAMBIAR ESTADO DE UNA CITA
# ---------------------------------

@app.route("/api/admin/citas/<int:cita_id>/estado", methods=["POST"])
@requiere_login
def cambiar_estado(cita_id):

    datos = request.get_json(silent=True) or {}
    nuevo_estado = datos.get("estado")

    estados_validos = ["pendiente", "confirmada", "cancelada"]

    if nuevo_estado not in estados_validos:
        return jsonify({"error": "Estado inválido"}), 400

    with get_db() as db:

        db.execute("BEGIN IMMEDIATE")

        cita = db.execute("""
            SELECT fecha, hora, servicio_id
            FROM citas
            WHERE id = ?
        """, (cita_id,)).fetchone()

        if not cita:
            return jsonify({"error": "Cita no encontrada"}), 404

        if nuevo_estado in ["pendiente", "confirmada"]:

            servicio = db.execute("""
                SELECT duracion
                FROM servicios
                WHERE id = ?
            """, (cita["servicio_id"],)).fetchone()

            inicio = datetime.strptime(cita["hora"], "%H:%M")
            fin = inicio + timedelta(minutes=servicio["duracion"])

            otras = db.execute("""
                SELECT c.hora, s.duracion
                FROM citas c
                JOIN servicios s ON s.id = c.servicio_id
                WHERE c.fecha = ?
                AND c.id != ?
                AND c.estado IN ('pendiente', 'confirmada')
            """, (cita["fecha"], cita_id)).fetchall()

            for otra in otras:
                otro_inicio = datetime.strptime(otra["hora"], "%H:%M")
                otro_fin = otro_inicio + timedelta(minutes=otra["duracion"])

                if inicio < otro_fin and fin > otro_inicio:
                    return jsonify({
                        "error": "Este horario coincide con otra cita activa."
                    }), 409

        db.execute("""
            UPDATE citas
            SET estado = ?
            WHERE id = ?
        """, (nuevo_estado, cita_id))

        db.commit()

    return jsonify({
        "mensaje": "Estado actualizado correctamente",
        "estado": nuevo_estado
    })


# ---------------------------------
# GESTIÓN DE SERVICIOS
# ---------------------------------

@app.route("/admin/servicios", methods=["GET", "POST"])
@requiere_login
def admin_servicios():

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        precio = request.form.get("precio", type=int)
        duracion = request.form.get("duracion", type=int)

        if not nombre or precio is None or duracion is None:
            flash("Completa todos los campos.", "error")
            return redirect(url_for("admin_servicios"))

        if precio <= 0 or duracion <= 0:
            flash("El precio y la duración deben ser mayores que cero.", "error")
            return redirect(url_for("admin_servicios"))

        with get_db() as db:
            db.execute("""
                INSERT INTO servicios
                (nombre, descripcion, precio, duracion, activo)
                VALUES (?, ?, ?, ?, 1)
            """, (nombre, descripcion, precio, duracion))
            db.commit()

        flash("Servicio creado correctamente.", "success")
        return redirect(url_for("admin_servicios"))

    with get_db() as db:
        servicios = db.execute("""
            SELECT *
            FROM servicios
            ORDER BY activo DESC, nombre
        """).fetchall()

    return render_template(
        "servicios_admin.html",
        servicios=servicios
    )


# ---------------------------------
# CONFIGURACIÓN DE LA BARBERÍA
# ---------------------------------

@app.route("/admin/configuracion", methods=["GET", "POST"])
@requiere_login
def admin_configuracion():

    if request.method == "POST":

        datos = {
            "banco_nombre": request.form.get("banco_nombre", "").strip(),
            "banco_titular": request.form.get("banco_titular", "").strip(),
            "banco_tipo_cuenta": request.form.get("banco_tipo_cuenta", "").strip(),
            "banco_numero_cuenta": request.form.get("banco_numero_cuenta", "").strip(),
            "banco_documento": request.form.get("banco_documento", "").strip(),
            "porcentaje_deposito": request.form.get("porcentaje_deposito", "50").strip()
        }

        try:
            porcentaje = int(datos["porcentaje_deposito"])
        except ValueError:
            flash("El porcentaje debe ser un número.", "error")
            return redirect(url_for("admin_configuracion"))

        if porcentaje < 1 or porcentaje > 100:
            flash("El porcentaje debe estar entre 1 y 100.", "error")
            return redirect(url_for("admin_configuracion"))

        with get_db() as db:
            for clave, valor in datos.items():
                db.execute("""
                    INSERT INTO configuracion (clave, valor)
                    VALUES (?, ?)
                    ON CONFLICT(clave)
                    DO UPDATE SET valor = excluded.valor
                """, (clave, valor))

            db.commit()

        flash("Configuración guardada correctamente.", "success")
        return redirect(url_for("admin_configuracion"))

    with get_db() as db:
        filas = db.execute("""
            SELECT clave, valor FROM configuracion
        """).fetchall()

    configuracion = {
        fila["clave"]: fila["valor"]
        for fila in filas
    }

    return render_template(
        "configuracion.html",
        configuracion=configuracion
    )



@app.route("/admin/servicios/<int:servicio_id>/editar", methods=["POST"])
@requiere_login
def editar_servicio(servicio_id):

    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    precio = request.form.get("precio", type=int)
    duracion = request.form.get("duracion", type=int)

    if not nombre or precio is None or duracion is None:
        flash("Completa todos los campos.", "error")
        return redirect(url_for("admin_servicios"))

    if precio <= 0 or duracion <= 0:
        flash("Precio y duración deben ser mayores que cero.", "error")
        return redirect(url_for("admin_servicios"))

    with get_db() as db:
        db.execute("""
            UPDATE servicios
            SET nombre = ?, descripcion = ?, precio = ?, duracion = ?
            WHERE id = ?
        """, (nombre, descripcion, precio, duracion, servicio_id))
        db.commit()

    flash("Servicio actualizado.", "success")
    return redirect(url_for("admin_servicios"))


@app.route("/admin/servicios/<int:servicio_id>/estado", methods=["POST"])
@requiere_login
def cambiar_estado_servicio(servicio_id):

    with get_db() as db:
        db.execute("""
            UPDATE servicios
            SET activo = CASE WHEN activo = 1 THEN 0 ELSE 1 END
            WHERE id = ?
        """, (servicio_id,))
        db.commit()

    flash("Estado del servicio actualizado.", "success")
    return redirect(url_for("admin_servicios"))



# ---------------------------------
# MOTOR DE HORARIOS Y RESERVAS
# ---------------------------------

def generar_horarios(fecha, duracion, db):
    apertura = datetime.strptime("09:00", "%H:%M")
    cierre = datetime.strptime("18:00", "%H:%M")

    ocupados = db.execute("""
        SELECT c.hora, s.duracion
        FROM citas c
        JOIN servicios s ON s.id = c.servicio_id
        WHERE c.fecha = ?
        AND c.estado IN ('pendiente', 'confirmada')
    """, (fecha,)).fetchall()

    bloques = []

    for cita in ocupados:
        inicio = datetime.strptime(cita["hora"], "%H:%M")
        fin = inicio + timedelta(minutes=cita["duracion"])
        bloques.append((inicio, fin))

    disponibles = []
    actual = apertura

    while actual + timedelta(minutes=duracion) <= cierre:

        fin = actual + timedelta(minutes=duracion)

        if fecha == date.today().isoformat():
            if actual <= datetime.now():
                actual += timedelta(minutes=30)
                continue

        ocupado = any(
            actual < fin_bloque and fin > inicio_bloque
            for inicio_bloque, fin_bloque in bloques
        )

        if not ocupado:
            disponibles.append(actual.strftime("%H:%M"))

        actual += timedelta(minutes=30)

    return disponibles


@app.route("/api/horarios")
def api_horarios():

    fecha = request.args.get("fecha")
    servicio_id = request.args.get("servicio_id")

    try:
        fecha_obj = date.fromisoformat(fecha)
        servicio_id = int(servicio_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Datos inválidos"}), 400

    if fecha_obj < date.today():
        return jsonify({"error": "Fecha pasada"}), 400

    if fecha_obj.weekday() == 6:
        return jsonify({"horarios": []})

    with get_db() as db:
        servicio = db.execute("""
            SELECT duracion FROM servicios
            WHERE id = ? AND activo = 1
        """, (servicio_id,)).fetchone()

        if not servicio:
            return jsonify({"error": "Servicio no encontrado"}), 404

        disponibles = generar_horarios(
            fecha, servicio["duracion"], db
        )

    return jsonify({"horarios": disponibles})



@app.route("/api/reservar", methods=["POST"])
def reservar():

    cliente = request.form.get("cliente", "").strip()
    telefono = request.form.get("telefono", "").strip()
    fecha = request.form.get("fecha", "")
    hora = request.form.get("hora", "")
    servicio_id = request.form.get("servicio_id", "")

    archivo = request.files.get("comprobante")

    if not all([cliente, telefono, fecha, hora, servicio_id]):
        return jsonify({
            "error": "Completa todos los campos."
        }), 400

    if not archivo or not archivo.filename:
        return jsonify({
            "error": "Debes adjuntar el comprobante de pago."
        }), 400

    if len(cliente) > 100 or len(telefono) > 20:
        return jsonify({
            "error": "Datos demasiado largos."
        }), 400

    if not all(c.isdigit() or c in "+- ()" for c in telefono):
        return jsonify({
            "error": "Teléfono inválido."
        }), 400

    extension = os.path.splitext(archivo.filename)[1].lower()

    if extension not in EXTENSIONES_PERMITIDAS:
        return jsonify({
            "error": "Formato inválido. Usa JPG, PNG o WEBP."
        }), 400

    try:
        fecha_obj = date.fromisoformat(fecha)
        datetime.strptime(hora, "%H:%M")
        servicio_id = int(servicio_id)
    except (ValueError, TypeError):
        return jsonify({
            "error": "Datos inválidos."
        }), 400

    if fecha_obj < date.today() or fecha_obj.weekday() == 6:
        return jsonify({
            "error": "Fecha no disponible."
        }), 400

    nombre_archivo = (
        uuid.uuid4().hex + extension
    )

    ruta_archivo = os.path.join(
        CARPETA_COMPROBANTES,
        secure_filename(nombre_archivo)
    )

    with get_db() as db:

        db.execute("BEGIN IMMEDIATE")

        servicio = db.execute("""
            SELECT id, nombre, duracion, precio
            FROM servicios
            WHERE id = ? AND activo = 1
        """, (servicio_id,)).fetchone()

        if not servicio:
            return jsonify({
                "error": "Servicio no disponible."
            }), 404

        # Obtener porcentaje de depósito
        fila_porcentaje = db.execute("""
            SELECT valor
            FROM configuracion
            WHERE clave = 'porcentaje_deposito'
        """).fetchone()

        porcentaje = (
            int(fila_porcentaje["valor"])
            if fila_porcentaje else 50
        )

        if porcentaje < 1 or porcentaje > 100:
            return jsonify({
                "error": "Porcentaje de depósito inválido."
            }), 500

        precio = servicio["precio"]

        monto_deposito = math.ceil(
            precio * porcentaje / 100
        )

        disponibles = generar_horarios(
            fecha, servicio["duracion"], db
        )

        if hora not in disponibles:
            return jsonify({
                "error": "Horario no disponible."
            }), 409

        # Guardar imagen
        archivo.save(ruta_archivo)

        cursor = db.execute("""
            INSERT INTO citas (
                cliente,
                telefono,
                servicio_id,
                fecha,
                hora,
                estado,
                precio_reservado,
                monto_deposito,
                pago_estado,
                comprobante
            )
            VALUES (?, ?, ?, ?, ?, 'pendiente',
                    ?, ?, 'pendiente_revision', ?)
        """, (
            cliente,
            telefono,
            servicio_id,
            fecha,
            hora,
            precio,
            monto_deposito,
            nombre_archivo
        ))

        cita_id = cursor.lastrowid
        db.commit()

    return jsonify({
        "mensaje": "Solicitud registrada.",
        "cita_id": cita_id,
        "servicio": servicio["nombre"],
        "precio": precio,
        "deposito": monto_deposito,
        "fecha": fecha,
        "hora": hora,
        "pago_estado": "pendiente_revision"
    }), 201


if __name__ == "__main__":
    app.run(debug=True)
