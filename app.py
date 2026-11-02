
from flask import Flask, jsonify, render_template, request
from database import get_db, init_db
from database import migrar_citas
from datetime import datetime, date, timedelta

app = Flask(__name__)

# Inicializar base de datos
init_db()
migrar_citas()

@app.route("/")
def inicio():

    with get_db() as db:
        servicios = db.execute("""
            SELECT *
            FROM servicios
            WHERE activo = 1
            ORDER BY id
        """).fetchall()

    return render_template(
        "index.html",
        servicios=servicios
    )

def generar_horarios(fecha, duracion, db):
    apertura = datetime.strptime("09:00", "%H:%M")
    cierre = datetime.strptime("18:00", "%H:%M")

    horarios_ocupados = db.execute("""
        SELECT c.hora, s.duracion
        FROM citas c
        JOIN servicios s ON s.id = c.servicio_id
        WHERE c.fecha = ?
        AND c.estado IN ('pendiente', 'confirmada')
    """, (fecha,)).fetchall()

    ocupados = []

    for cita in horarios_ocupados:
        inicio = datetime.strptime(cita["hora"], "%H:%M")
        fin = inicio + timedelta(minutes=cita["duracion"])
        ocupados.append((inicio, fin))

    disponibles = []
    actual = apertura

    while actual + timedelta(minutes=duracion) <= cierre:
        fin = actual + timedelta(minutes=duracion)

        # Evitar horarios que ya pasaron
        if fecha == date.today().isoformat():
            if actual <= datetime.now():
                actual += timedelta(minutes=30)
                continue

        # Verificar solapamientos
        ocupado = any(
            actual < fin_ocupado and fin > inicio_ocupado
            for inicio_ocupado, fin_ocupado in ocupados
        )

        if not ocupado:
            disponibles.append(actual.strftime("%H:%M"))

        actual += timedelta(minutes=30)

    return disponibles


@app.route("/api/horarios")
def api_horarios():
    fecha = request.args.get("fecha")
    servicio_id = request.args.get("servicio_id")

    if not fecha or not servicio_id:
        return jsonify({"error": "Faltan datos"}), 400

    try:
        fecha_obj = date.fromisoformat(fecha)
        servicio_id = int(servicio_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Datos inválidos"}), 400

    if fecha_obj < date.today():
        return jsonify({"error": "No puedes reservar fechas pasadas"}), 400

    if fecha_obj.weekday() == 6:
        return jsonify({"error": "La barbería está cerrada los domingos"}), 200

    with get_db() as db:
        servicio = db.execute("""
            SELECT duracion
            FROM servicios
            WHERE id = ? AND activo = 1
        """, (servicio_id,)).fetchone()

        if not servicio:
            return jsonify({"error": "Servicio no encontrado"}), 404

        horarios = generar_horarios(
            fecha,
            servicio["duracion"],
            db
        )

    return jsonify({"horarios": horarios})


@app.route("/api/reservar", methods=["POST"])
def reservar():
    datos = request.get_json(silent=True) or {}

    cliente = str(datos.get("cliente", "")).strip()
    telefono = str(datos.get("telefono", "")).strip()
    fecha = datos.get("fecha", "")
    hora = datos.get("hora", "")
    servicio_id = datos.get("servicio_id")

    if not all([cliente, telefono, fecha, hora, servicio_id]):
        return jsonify({"error": "Completa todos los campos"}), 400

    if len(cliente) > 100 or len(telefono) > 20:
        return jsonify({"error": "Los datos exceden el límite permitido"}), 400

    if not all(c.isdigit() or c in "+- ()" for c in telefono):
        return jsonify({"error": "Número de teléfono inválido"}), 400

    try:
        fecha_obj = date.fromisoformat(fecha)
        hora_obj = datetime.strptime(hora, "%H:%M")
        servicio_id = int(servicio_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Fecha, hora o servicio inválido"}), 400

    if fecha_obj < date.today() or fecha_obj.weekday() == 6:
        return jsonify({"error": "Fecha no disponible"}), 400

    with get_db() as db:
        # Bloqueamos otras escrituras mientras verificamos y reservamos
        db.execute("BEGIN IMMEDIATE")

        servicio = db.execute("""
            SELECT id, nombre, duracion, precio
            FROM servicios
            WHERE id = ? AND activo = 1
        """, (servicio_id,)).fetchone()

        if not servicio:
            return jsonify({"error": "Servicio no disponible"}), 404

        horarios = generar_horarios(fecha, servicio["duracion"], db)

        if hora not in horarios:
            return jsonify({
                "error": "Ese horario ya no está disponible. Selecciona otro."
            }), 409

        cursor = db.execute("""
            INSERT INTO citas
            (cliente, telefono, servicio_id, fecha, hora, estado)
            VALUES (?, ?, ?, ?, ?, 'pendiente')
        """, (cliente, telefono, servicio_id, fecha, hora))

        cita_id = cursor.lastrowid
        db.commit()

    return jsonify({
        "mensaje": "Solicitud de cita registrada correctamente",
        "cita_id": cita_id,
        "cliente": cliente,
        "servicio": servicio["nombre"],
        "precio": servicio["precio"],
        "fecha": fecha,
        "hora": hora
    }), 201


if __name__ == "__main__":
    app.run(debug=True)
