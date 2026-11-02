
from flask import Flask, render_template
from database import get_db, init_db

app = Flask(__name__)

# Inicializar base de datos
init_db()


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


if __name__ == "__main__":
    app.run(debug=True)
