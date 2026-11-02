
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

        # Tabla de servicios
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

        # Tabla de citas
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
                    REFERENCES servicios(id),

                UNIQUE (fecha, hora)
            )
        """)

        # Servicios iniciales
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


if __name__ == "__main__":
    init_db()
    print(f"Base de datos creada en: {DATABASE}")
