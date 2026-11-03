
const lista = document.getElementById("appointmentsList");
const tituloFecha = document.getElementById("selectedDate");

let fechaActual = fechaInicial;
let modalComprobante = null;

function crearElemento(tag, texto, clase = "") {
    const elemento = document.createElement(tag);
    elemento.textContent = texto;
    if (clase) elemento.className = clase;
    return elemento;
}

function mostrarComprobante(url) {

    // Crear el modal solamente una vez
    if (!modalComprobante) {

        modalComprobante = document.createElement("div");
        modalComprobante.className = "modal-comprobante";

        const contenido = document.createElement("div");
        contenido.className = "modal-comprobante-contenido";

        const cerrar = document.createElement("button");
        cerrar.type = "button";
        cerrar.className = "modal-comprobante-cerrar";
        cerrar.textContent = "✕";
        cerrar.setAttribute("aria-label", "Cerrar comprobante");

        const imagen = document.createElement("img");
        imagen.className = "modal-comprobante-imagen";
        imagen.alt = "Comprobante de pago";

        contenido.appendChild(cerrar);
        contenido.appendChild(imagen);
        modalComprobante.appendChild(contenido);

        document.body.appendChild(modalComprobante);

        // Cerrar con el botón
        cerrar.addEventListener("click", cerrarModalComprobante);

        // Cerrar al pulsar fuera de la imagen
        modalComprobante.addEventListener("click", (event) => {
            if (event.target === modalComprobante) {
                cerrarModalComprobante();
            }
        });

        // Cerrar con Escape
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                cerrarModalComprobante();
            }
        });
    }

    const imagen = modalComprobante.querySelector(
        ".modal-comprobante-imagen"
    );

    imagen.src = url;

    modalComprobante.classList.add("activo");
    document.body.classList.add("modal-abierto");
}

function cerrarModalComprobante() {

    if (!modalComprobante) return;

    modalComprobante.classList.remove("activo");
    document.body.classList.remove("modal-abierto");

    const imagen = modalComprobante.querySelector(
        ".modal-comprobante-imagen"
    );

    imagen.src = "";
}


async function cargarCitas(fecha) {

    fechaActual = fecha;
    tituloFecha.textContent = new Date(
        fecha + "T12:00:00"
    ).toLocaleDateString("es-DO", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
    });

    lista.replaceChildren(
        crearElemento("p", "Consultando citas...", "empty-state")
    );

    try {

        const respuesta = await fetch(
            `/api/admin/citas?fecha=${encodeURIComponent(fecha)}`
        );

        if (respuesta.status === 401 || respuesta.redirected) {
            window.location.href = "/admin/login";
            return;
        }

        const citas = await respuesta.json();

        lista.replaceChildren();

        if (!respuesta.ok) {
            throw new Error(citas.error || "Error consultando citas");
        }

        if (citas.length === 0) {
            lista.appendChild(
                crearElemento(
                    "p",
                    "No tienes citas registradas para este día.",
                    "empty-state"
                )
            );
            return;
        }

        citas.forEach(cita => {

            const tarjeta = crearElemento("article", "", "appointment-item");

            const hora = crearElemento(
                "div", cita.hora, "appointment-time"
            );

            const detalles = crearElemento("div", "", "appointment-details");

            detalles.appendChild(
                crearElemento("h3", cita.cliente)
            );

            detalles.appendChild(
                crearElemento("p", cita.servicio)
            );

            detalles.appendChild(
                crearElemento("p", `WhatsApp: ${cita.telefono}`)
            );

            detalles.appendChild(
                crearElemento("p", `RD$ ${cita.precio}`)
            );
            // Información del depósito
            detalles.appendChild(
                crearElemento(
                    "p",
                    `Depósito: RD$ ${cita.monto_deposito || 0}`
                )
            );

            detalles.appendChild(
                crearElemento(
                    "p",
                    `Pago: ${(cita.pago_estado || "pendiente").replaceAll("_", " ").toUpperCase()}`
                )
            );

            // Mostrar comprobante
        if (cita.comprobante) {

            const comprobante = crearElemento(
                "button",
                "🧾 Ver comprobante de pago",
                "action-comprobante"
            );

            comprobante.type = "button";

            comprobante.addEventListener("click", () => {
                mostrarComprobante(
                    `/admin/comprobantes/${encodeURIComponent(cita.comprobante)}`
                );
            });

            detalles.appendChild(comprobante);

        } else {

            detalles.appendChild(
                crearElemento("p", "Sin comprobante")
            );

        }       

            const estado = crearElemento(
                "span",
                cita.estado.toUpperCase(),
                `status status-${cita.estado}`
            );

            detalles.appendChild(estado);

            const acciones = crearElemento("div", "", "appointment-actions");

            // Contactar al cliente
            const whatsapp = document.createElement("a");

            let numero = cita.telefono.replace(/\D/g, "");
            if (numero.length === 10) numero = "1" + numero; // RD: 809/829/849

            whatsapp.href =
                `https://wa.me/${numero}?text=` +
                encodeURIComponent(
                    `Hola ${cita.cliente}, te contactamos de La Barbería sobre tu cita del ${cita.fecha} a las ${cita.hora}.`
                );

            whatsapp.target = "_blank";
            whatsapp.rel = "noopener noreferrer";
            whatsapp.textContent = "WhatsApp";
            whatsapp.className = "action-whatsapp";

            acciones.appendChild(whatsapp);

            // Cambiar estado
            if (cita.estado !== "cancelada") {

                const confirmar = crearElemento(
                    "button",
                    "Confirmar",
                    "action-confirm"
                );

                confirmar.disabled = cita.estado === "confirmada";

                confirmar.addEventListener("click", () => {
                    cambiarEstado(cita.id, "confirmada");
                });

                acciones.appendChild(confirmar);

                const cancelar = crearElemento(
                    "button",
                    "Cancelar",
                    "action-cancel"
                );

                cancelar.addEventListener("click", () => {
                    if (confirm("¿Deseas cancelar esta cita?")) {
                        cambiarEstado(cita.id, "cancelada");
                    }
                });

                acciones.appendChild(cancelar);
            }

            tarjeta.appendChild(hora);
            tarjeta.appendChild(detalles);
            tarjeta.appendChild(acciones);

            lista.appendChild(tarjeta);
        });

    } catch (error) {
        lista.replaceChildren(
            crearElemento("p", error.message, "empty-state")
        );
    }
}


async function cambiarEstado(id, estado) {

    try {

        const respuesta = await fetch(
            `/api/admin/citas/${id}/estado`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ estado })
            }
        );

        const datos = await respuesta.json();

        if (!respuesta.ok) {
            throw new Error(datos.error || "No se pudo actualizar");
        }

        await cargarCitas(fechaActual);

        // Actualizar la página para refrescar las estadísticas
        location.reload();

    } catch (error) {
        alert(error.message);
    }
}


// Seleccionar un día del calendario
document.querySelectorAll(".calendar-day").forEach(dia => {

    dia.addEventListener("click", () => {

        document.querySelectorAll(".calendar-day").forEach(boton => {
            boton.classList.remove("selected");
        });

        dia.classList.add("selected");

        cargarCitas(dia.dataset.date);
    });

});


// Abrir el calendario en el día actual
const diaHoy = document.querySelector(
    `.calendar-day[data-date="${fechaInicial}"]`
);

if (diaHoy) {
    diaHoy.classList.add("selected");
}

cargarCitas(fechaInicial);
