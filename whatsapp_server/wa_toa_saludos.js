/**
 * Saludos de entrada/salida de Yugi según ventana horaria de atención de
 * consultas de estado — acordado con el usuario (2026-08-22).
 *
 * IMPORTANTE — alcance deliberadamente acotado: estos saludos SOLO se
 * envían al grupo de pruebas (GRUPO_SALUDOS_ID abajo), nunca a los grupos
 * reales de soporte zonal (Tacna, Trujillo, Chimbote, Arequipa, Ilo/Moq. —
 * ver whatsapp_server/wa_toa_server.js::/list-groups). El usuario pidió
 * explícitamente tener cuidado de no aplicar esto a todos los grupos.
 *
 * Ventanas horarias de atención (hora local del servidor):
 *   08:00–13:00 y 14:00–20:00
 * En los 4 bordes se envía un mensaje al grupo de pruebas, elegido al azar
 * entre varias variantes por borde (mismo criterio que la espera humana
 * antes de responder /estado — evita sonar repetitivo/mecánico con el
 * mismo texto exacto todos los días):
 *   08:00 -> apertura de jornada
 *   13:00 -> salida a refrigerio
 *   14:00 -> vuelta del refrigerio
 *   20:00 -> cierre de jornada
 *
 * Nota: estas ventanas son solo para el saludo — HOY el listener de
 * /estado (wa_toa_listener.js) sigue respondiendo consultas a cualquier
 * hora, no se corta fuera de ventana. Si más adelante se quiere que Yugi
 * deje de responder fuera de horario, es un cambio aparte en
 * wa_toa_listener.js, no en este módulo.
 */
const GRUPO_SALUDOS_ID = "120363426514211263@g.us"; // ESTADOS/PRUEBAS/ESHORADELDUELO

const SALUDOS_HORARIOS = [
  {
    hora: 8,
    minuto: 0,
    variantes: [
      "Buenos días, ya estoy atendiendo consultas de estados",
      "Buenos días, ya estoy disponible para consultas de estados",
      "Buenos días, arrancamos, ya puedo atender consultas de estados",
    ],
  },
  {
    hora: 13,
    minuto: 0,
    variantes: [
      "Me retiro a tomar mi refrigerio, regreso luego",
      "Voy a tomar mi refrigerio, ya vuelvo",
      "Me tomo un break para el refrigerio, regreso en un rato",
    ],
  },
  {
    hora: 14,
    minuto: 0,
    variantes: [
      "Activo nuevamente para responder estados",
      "Ya estoy de vuelta, activo nuevamente para responder estados",
      "Regresé del refrigerio, ya puedo atender consultas de estados",
    ],
  },
  {
    hora: 20,
    minuto: 0,
    variantes: [
      "Buenas tardes, paso a retirarme, hasta mañana",
      "Buenas tardes, ya me retiro por hoy, hasta mañana",
      "Cierro por hoy, buenas tardes, nos vemos mañana",
    ],
  },
];

function _elegirVariante(variantes) {
  return variantes[Math.floor(Math.random() * variantes.length)];
}

const CHEQUEO_INTERVALO_MS = 60 * 1000; // revisa cada minuto si toca enviar algún saludo

/**
 * Registra el scheduler de saludos sobre un cliente whatsapp-web.js ya
 * listo. `log` es la función de logging de wa_toa_server.js.
 *
 * Se llama una sola vez por proceso de vida del servidor Node (no por cada
 * reconexión del cliente WA), a diferencia de registrarListenerEstado —
 * el setInterval no depende de `waClient` seguir siendo el mismo objeto,
 * así que no hace falta re-registrar en cada reinicio de sesión. Se pasa
 * un getter en vez de la instancia directa para siempre usar el cliente
 * vivo más reciente, igual que el resto de wa_toa_server.js maneja sus
 * setInterval de mantenimiento.
 */
function registrarSaludosHorarios(getWaClient, log) {
  let ultimoDisparado = null; // "HH:MM" del último saludo enviado, evita reenvÃ­o si el proceso sigue corriendo en el mismo minuto

  setInterval(async () => {
    const ahora = new Date();
    const hhmm = `${ahora.getHours()}:${ahora.getMinutes()}`;

    const saludo = SALUDOS_HORARIOS.find((s) => s.hora === ahora.getHours() && s.minuto === ahora.getMinutes());
    if (!saludo || hhmm === ultimoDisparado) return;
    ultimoDisparado = hhmm;

    const mensaje = _elegirVariante(saludo.variantes);

    const waClient = getWaClient();
    if (!waClient) {
      log("WARN", "Saludo horario: cliente WhatsApp no disponible, se omite", { mensaje });
      return;
    }

    try {
      await waClient.sendMessage(GRUPO_SALUDOS_ID, mensaje);
      log("INFO", "Saludo horario enviado", { grupo: GRUPO_SALUDOS_ID, mensaje });
    } catch (e) {
      log("ERROR", "No se pudo enviar el saludo horario", { mensaje, error: e.message });
    }
  }, CHEQUEO_INTERVALO_MS);

  log("INFO", "Scheduler de saludos horarios registrado (solo grupo de pruebas)", { grupo: GRUPO_SALUDOS_ID });
}

module.exports = { registrarSaludosHorarios };
