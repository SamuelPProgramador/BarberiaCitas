
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DATABASE = INSTANCE_DIR / "barberia.db"


def get_db():
    INSTANCE_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    return connection


def init_db():
    with get_db() as db:

        # ---------------------------------
        # TABLA DE SERVICIOS
        # ---------------------------------
        db.execute("""
            CREATE TABLE IF NOT EXISTS servicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                precio INTEGER NOT NULL,
                duracion INTEGER NOT NULL,
                activo INTEGER DEFAULT 1
            )
        """)

        # ---------------------------------
        # TABLA DE CITAS
        # ---------------------------------
        db.execute("""
            CREATE TABLE IF NOT EXISTS citas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT NOT NULL,
                telefono TEXT NOT NULL,
                servicio_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                estado TEXT DEFAULT 'pendiente',
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (servicio_id)
                    REFERENCES servicios(id)
            )
        """)

        # ---------------------------------
        # TABLA DE CONFIGURACIÓN
        # ---------------------------------
        db.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)

        # ---------------------------------
        # MIGRACIÓN DE CITAS EXISTENTES
        # ---------------------------------
        columnas = {
            fila["name"]
            for fila in db.execute(
                "PRAGMA table_info(citas)"
            ).fetchall()
        }

        nuevas_columnas = {
            "precio_reservado": "INTEGER DEFAULT 0",
            "monto_deposito": "INTEGER DEFAULT 0",
            "pago_estado": "TEXT DEFAULT 'pendiente'",
            "comprobante": "TEXT",
            "fecha_pago": "TEXT"
        }

        for nombre, tipo in nuevas_columnas.items():
            if nombre not in columnas:
                db.execute(
                    f"ALTER TABLE citas ADD COLUMN {nombre} {tipo}"
                )

        # ---------------------------------
        # PRECIO HISTÓRICO
        # ---------------------------------
        db.execute("""
            UPDATE citas
            SET precio_reservado = (
                SELECT precio
                FROM servicios
                WHERE servicios.id = citas.servicio_id
            )
            WHERE precio_reservado = 0
        """)

        # ---------------------------------
        # CONFIGURACIÓN INICIAL
        # ---------------------------------
        configuraciones = [
            ("banco_nombre", ""),
            ("banco_titular", ""),
            ("banco_tipo_cuenta", ""),
            ("banco_numero_cuenta", ""),
            ("banco_documento", ""),
            ("porcentaje_deposito", "50"),
            ("hora_apertura", "08:00"),
            ("hora_cierre", "23:00"),
            ("descanso_minutos", "15"),
            ("descanso_opcional", "1")
        ]

        db.executemany("""
            INSERT OR IGNORE INTO configuracion
            (clave, valor)
            VALUES (?, ?)
        """, configuraciones)

        # ---------------------------------
        # SERVICIOS INICIALES
        # ---------------------------------
        cantidad = db.execute(
            "SELECT COUNT(*) FROM servicios"
        ).fetchone()[0]

        if cantidad == 0:
            servicios = [
                ("Corte clásico", "Un corte limpio y definido.", 300, 30),
                ("Corte + barba", "Un look completo y fresco.", 500, 45),
                ("Barba completa", "Perfilado y acabado preciso.", 300, 30),
                ("Diseño especial", "Detalles personalizados.", 400, 40)
            ]

            db.executemany("""
                INSERT INTO servicios
                (nombre, descripcion, precio, duracion)
                VALUES (?, ?, ?, ?)
            """, servicios)

        db.commit()


def migrar_citas():
    """
    Elimina la restricción UNIQUE(fecha, hora)
    para permitir citas según su duración real.
    """
    with get_db() as db:

        tabla = db.execute("""
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = 'citas'
        """).fetchone()

        if tabla and "UNIQUE (fecha, hora)" in tabla["sql"]:
            db.execute("PRAGMA foreign_keys = OFF")

            db.execute("""
                CREATE TABLE citas_nueva (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente TEXT NOT NULL,
                    telefono TEXT NOT NULL,
                    servicio_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    hora TEXT NOT NULL,
                    estado TEXT DEFAULT 'pendiente',
                    fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                    precio_reservado INTEGER DEFAULT 0,
                    monto_deposito INTEGER DEFAULT 0,
                    pago_estado TEXT DEFAULT 'pendiente',
                    comprobante TEXT,
                    fecha_pago TEXT,
                    FOREIGN KEY (servicio_id)
                        REFERENCES servicios(id)
                )
            """)

            db.execute("""
                INSERT INTO citas_nueva
                SELECT *
                FROM citas
            """)

            db.execute("DROP TABLE citas")
            db.execute("""
                ALTER TABLE citas_nueva
                RENAME TO citas
            """)

            db.execute("PRAGMA foreign_keys = ON")
            db.commit()


if __name__ == "__main__":
    init_db()
    migrar_citas()
    print(f"Base de datos preparada: {DATABASE}")
