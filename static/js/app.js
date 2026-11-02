
const servicio = document.getElementById("servicio");
const fecha = document.getElementById("fecha");
const horarios = document.getElementById("horarios");
const horaSeleccionada = document.getElementById("hora");
const formulario = document.getElementById("bookingForm");
const resultado = document.getElementById("resultado");
const boton = document.getElementById("btnReservar");

// Evitar fechas anteriores a hoy
const hoy = new Date();
const fechaLocal = new Date(
    hoy.getTime() - hoy.getTimezoneOffset() * 60000
).toISOString().split("T")[0];

fecha.min = fechaLocal;
fecha.value = fechaLocal;


// Consultar horarios disponibles
async function cargarHorarios() {

    horaSeleccionada.value = "";

    horarios.replaceChildren();

    if (!servicio.value || !fecha.value) {
        horarios.textContent = "Selecciona un servicio y una fecha.";
        return;
    }

    horarios.textContent = "Consultando disponibilidad...";

    try {
        const respuesta = await fetch(
            `/api/horarios?fecha=${encodeURIComponent(fecha.value)}&servicio_id=${encodeURIComponent(servicio.value)}`
        );

        const datos = await respuesta.json();

        horarios.replaceChildren();

        if (!respuesta.ok || datos.error) {
            horarios.textContent = datos.error || "No se pudieron consultar los horarios.";
            return;
        }

        if (datos.horarios.length === 0) {
            horarios.textContent = "No hay horarios disponibles para esta fecha.";
            return;
        }

        datos.horarios.forEach(hora => {

            const botonHora = document.createElement("button");

            botonHora.type = "button";
            botonHora.className = "slot";
            botonHora.textContent = hora;

            botonHora.addEventListener("click", () => {

                document.querySelectorAll(".slot").forEach(boton => {
                    boton.classList.remove("active");
                });

                botonHora.classList.add("active");

                horaSeleccionada.value = hora;
            });

            horarios.appendChild(botonHora);
        });

    } catch (error) {
        horarios.textContent = "Error al consultar los horarios.";
        console.error(error);
    }
}


// Actualizar horarios cuando cambien los datos
servicio.addEventListener("change", cargarHorarios);
fecha.addEventListener("change", cargarHorarios);


// Guardar la reserva
formulario.addEventListener("submit", async (event) => {

    event.preventDefault();

    resultado.textContent = "";
    resultado.className = "resultado";

    if (!horaSeleccionada.value) {
        resultado.textContent = "Selecciona un horario disponible.";
        resultado.classList.add("error");
        return;
    }

    const datos = {
        servicio_id: servicio.value,
        fecha: fecha.value,
        hora: horaSeleccionada.value,
        cliente: document.getElementById("cliente").value.trim(),
        telefono: document.getElementById("telefono").value.trim()
    };

    boton.disabled = true;
    boton.textContent = "PROCESANDO...";

    try {

        const respuesta = await fetch("/api/reservar", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(datos)
        });

        const resultadoAPI = await respuesta.json();

        if (!respuesta.ok) {
            throw new Error(resultadoAPI.error || "No se pudo registrar la cita.");
        }

        resultado.classList.add("success");

        resultado.textContent =
            `¡Solicitud registrada! Número de cita: #${resultadoAPI.cita_id}. ` +
            `Servicio: ${resultadoAPI.servicio}. ` +
            `Fecha: ${resultadoAPI.fecha}. Hora: ${resultadoAPI.hora}. ` +
            "Tu cita está pendiente de confirmación.";

        formulario.reset();

        fecha.value = fechaLocal;
        horaSeleccionada.value = "";

        await cargarHorarios();

    } catch (error) {

        resultado.classList.add("error");
        resultado.textContent = error.message;

        await cargarHorarios();

    } finally {

        boton.disabled = false;
        boton.textContent = "CONFIRMAR SOLICITUD →";
    }
});


// Cargar disponibilidad inicial
cargarHorarios();
