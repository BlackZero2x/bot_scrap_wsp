/**
 * Listener del bot "Yugi Backoffice" — escucha mensajes en los grupos de
 * zonal y responde a "/estado FE-XXXXXXXXXX" citando el mensaje original.
 *
 * Diseño acordado (sesión 2026-08-19/20):
 * - Solo procesa mensajes de GRUPO, nunca DMs individuales (ver documento
 *   de arquitectura: fan-out a contactos es el patrón de spam más vigilado
 *   por Meta; confinar todo a grupos imita uso humano real).
 * - Comando explícito "/estado ..." — no intenta adivinar qué mensajes
 *   son consultas de FE en medio del ruido normal del grupo (cobertura,
 *   evaluar, cuenta financiera siguen siendo atendidas por el backoffice
 *   humano en el mismo grupo, sin colisión).
 * - Acepta 3 variantes de formato (todas exigen exactamente 10 dígitos —
 *   ni más ni menos, para no aceptar un código truncado por error de
 *   digitación), normalizadas al canónico FE-XXXXXXXXXX antes de pasar a
 *   la cascada:
 *     1. /estado FE-XXXXXXXXXX  (formato completo)
 *     2. /estado FE XXXXXXXXXX  (sin guión — se completa)
 *     3. /estado XXXXXXXXXX     (sin "FE-" — se completa)
 *   Antes de probar los 3 formatos se colapsan espacios/tabs repetidos a
 *   uno solo (ej. "FE -  1128977209" o "FE-  1128977209" también matchean)
 *   — cubre el error de tipeo más común sin ampliar de más el patrón.
 * - Si tras limpiar espacios el texto sigue sin matchear ningún formato
 *   válido, el fallback es silencio total — igual que cualquier otro
 *   mensaje de ruido del grupo. No se distingue "intentó /estado y falló"
 *   de "no era una consulta de estado".
 * - Responde con msg.reply() (no sendMessage suelto) — ancla la respuesta
 *   visualmente al mensaje del vendedor, distingue la respuesta del bot del
 *   hilo de conversación humana.
 * - El vendedor espera en silencio hasta el resultado final — sin mensaje
 *   intermedio de "buscando...".
 * - La cascada de LECTURA (VENTORY -> eAuren -> pbi2.fija_data_toa) vive en
 *   Python (consultar_estado_fe.py), invocado como proceso hijo por
 *   consulta. Si el resultado es "FE aun no pasa a TOA" (paso 3b: el FE
 *   nunca fue buscado en TOA), este listener dispara la búsqueda real vía
 *   POST /buscar al servicio HTTP toa_servicio_busqueda.py --http (puerto
 *   8004, sesión TOA persistente), CON REINTENTOS (backoff 3s/6s/12s, ver
 *   BUSQUEDA_TOA_MAX_REINTENTOS) — un FE recién vendido puede no estar
 *   sincronizado en TOA todavía en el primer intento. Si encuentra algo,
 *   vuelve a llamar a consultar_estado_fe.py para releer el dato ya guardado.
 * - Objetivo del proyecto (2026-08-22, acordado con el usuario): priorizar
 *   información correcta y actualizada sobre velocidad de respuesta — el
 *   vendedor tolera hasta ~60s si eso evita un dato desactualizado o un "no
 *   encontrado" prematuro. Consecuencia directa: el vendedor NUNCA ve un
 *   mensaje que delate una dificultad técnica (timeout, conexión caída,
 *   servicio caído) — eso genera desconfianza hacia Yugi. Todo fallo técnico
 *   (en la cascada Python o en este listener) se traduce en el mismo mensaje
 *   neutro MSG_SIN_RASTRO_TOA, nunca en un mensaje de error explícito.
 *
 * Se importa y engancha desde wa_toa_server.js después de crear waClient,
 * para mantener wa_toa_server.js como réplica fiel del servidor original
 * (AVANCE_MOVISTAR/wa_server.js) y aislar la lógica nueva del bot aquí.
 */
const { execFile } = require("child_process");
const http = require("http");
const path = require("path");

// Los 3 formatos aceptados, en orden de prueba — todos exigen exactamente
// 10 dígitos tras el prefijo/guión, capturados en el grupo 1. Se aplican
// sobre el texto ya normalizado (ver _normalizarEspacios), así que un
// espacio suelto extra alrededor del guión ya viene colapsado.
const FORMATOS_FE = [
  /^\/estado\s+FE-\s*(\d{10})\b/i, // 1: /estado FE-XXXXXXXXXX (o "FE- XXXXXXXXXX")
  /^\/estado\s+FE\s+(\d{10})\b/i, // 2: /estado FE XXXXXXXXXX
  /^\/estado\s+(\d{10})\b/i, // 3: /estado XXXXXXXXXX
];

const PYTHON_EXE = "C:\\proyectos\\.venv\\Scripts\\python.exe";
const SCRIPT_CONSULTAR = path.join(__dirname, "..", "consultar_estado_fe.py");
// consultar_estado_fe.py reintenta con backoff exponencial (MAX_REINTENTOS=6,
// ver ese script — hasta 63s de esperas entre intentos en el peor caso).
// Objetivo del proyecto (2026-08-22): priorizar info correcta/actualizada
// sobre velocidad — el vendedor tolera hasta ~60s si eso evita un dato
// desactualizado o un "no encontrado" prematuro. Margen sobre esos 63s.
const TIMEOUT_MS = 75_000;

const MSG_SIN_RASTRO_TOA = "FE aun no pasa a TOA";
const SERVICIO_BUSQUEDA_HOST = "localhost";
const SERVICIO_BUSQUEDA_PORT = 8004;
const SERVICIO_BUSQUEDA_TIMEOUT_MS = 65_000; // ventana de 1 min acordada + margen

// Ventana laboral del servicio de búsqueda puntual en TOA (2026-08-24,
// confirmado con el usuario): toa_servicio_busqueda.py --http ya NO corre
// 24/7 — mantener una sesión TOA autenticada fuera de horario laboral es
// una huella de actividad no-humana innecesaria y riesgosa frente a
// Seguridad de Telefónica (ver toa_servicio_busqueda.py::VENTANA_INICIO/
// VENTANA_FIN, mismos horarios, y resucitar_servicio_toa.ps1, que ya no
// revive el servicio fuera de esta ventana). Este listener debe saberlo
// para no intentar golpear un servicio que sabe apagado, y — decisión
// explícita del usuario — fuera de esta ventana el paso 3b se omite en
// SILENCIO TOTAL (sin responder nada), no con un mensaje alternativo.
const VENTANA_BUSQUEDA_INICIO_HORA = 8;
const VENTANA_BUSQUEDA_FIN_HORA = 20;

function _dentroDeVentanaBusqueda() {
  const hora = new Date().getHours();
  return hora >= VENTANA_BUSQUEDA_INICIO_HORA && hora < VENTANA_BUSQUEDA_FIN_HORA;
}

// Paso 3b — reintentos de la búsqueda puntual en TOA cuando el FE no está
// en el caché local. Antes era un solo intento con una espera fija de
// 1.5s antes de releer — insuficiente: si TOA no tiene el FE en el primer
// intento (recién vendido, aún no le llega la sincronización), un solo
// intento no le da tiempo. Con el objetivo de priorizar correctitud sobre
// velocidad, se reintenta con backoff dentro del presupuesto de ~60s ya
// acordado para esta búsqueda puntual.
const BUSQUEDA_TOA_MAX_REINTENTOS = 3;
const BUSQUEDA_TOA_ESPERA_BASE_MS = 3_000; // backoff: 3s, 6s, 12s

// Demora humana antes de responder — DESACTIVADA mientras estamos en fase de
// pruebas (queremos respuesta instantánea para iterar rápido). Activar para
// producción cambiando RESPUESTA_HUMANA_ACTIVA a true: agrega una espera
// aleatoria entre RESPUESTA_HUMANA_MIN_MS y RESPUESTA_HUMANA_MAX_MS justo
// antes de msg.reply(), simulando el tiempo que tardaría un backoffice
// humano en leer y escribir la respuesta (evita el patrón "responde en
// milisegundos" que delata automatización a simple vista en el grupo).
const RESPUESTA_HUMANA_ACTIVA = false;
const RESPUESTA_HUMANA_MIN_MS = 2_000;
const RESPUESTA_HUMANA_MAX_MS = 8_000;

function _esperaHumana() {
  if (!RESPUESTA_HUMANA_ACTIVA) return Promise.resolve();
  const ms = RESPUESTA_HUMANA_MIN_MS + Math.random() * (RESPUESTA_HUMANA_MAX_MS - RESPUESTA_HUMANA_MIN_MS);
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Colapsa espacios/tabs repetidos a uno solo y recorta los extremos —
 * cubre errores de tipeo como "/estado  FE-  1128977209" o mensajes
 * pegados desde otro chat con espacios dobles.
 */
function _normalizarEspacios(texto) {
  return texto.trim().replace(/\s+/g, " ");
}

/**
 * Prueba los 3 formatos aceptados (sobre el texto ya normalizado) y
 * devuelve el FE normalizado a "FE-XXXXXXXXXX", o null si no matchea
 * ninguno — ese null es el disparador del fallback de silencio total.
 */
function _extraerFE(texto) {
  const limpio = _normalizarEspacios(texto);
  for (const patron of FORMATOS_FE) {
    const match = limpio.match(patron);
    if (match) return `FE-${match[1]}`;
  }
  return null;
}

/**
 * Invoca consultar_estado_fe.py como proceso hijo (mismo patrón que
 * notify_error.py vía child_process) — cascada de solo lectura sobre las 3
 * fuentes (VENTORY, eAuren, pbi2.fija_data_toa).
 */
function _consultarEstadoFE(fe, log) {
  return new Promise((resolve, reject) => {
    execFile(
      PYTHON_EXE,
      [SCRIPT_CONSULTAR, fe],
      { cwd: path.join(__dirname, ".."), timeout: TIMEOUT_MS, encoding: "utf8" },
      (err, stdout, stderr) => {
        if (stderr && stderr.trim() && log) {
          // consultar_estado_fe.py puede terminar en éxito (exit 0) y aun
          // así imprimir un warning de diagnóstico a stderr (ej. fallo de
          // conexión tras reintentos, capturado internamente como "no
          // encontrado") — sin esto, esos avisos se perdían siempre que el
          // proceso no fallaba del todo.
          log("WARN", "consultar_estado_fe.py stderr", { fe, stderr: stderr.trim() });
        }
        if (err) {
          reject(new Error(`consultar_estado_fe.py falló: ${err.message} | stderr: ${stderr}`));
          return;
        }
        resolve(stdout.trim());
      }
    );
  });
}

/**
 * Paso 3b: dispara la búsqueda real en TOA vía el servicio HTTP
 * (toa_servicio_busqueda.py --http), que mantiene una sesión TOA
 * autenticada en memoria y resuelve la búsqueda con ~1s de latencia real
 * (medido) en vez de un login completo por consulta. Bloquea hasta que el
 * servicio responde o se agota SERVICIO_BUSQUEDA_TIMEOUT_MS — está dentro
 * de la ventana de 1 minuto ya acordada como aceptable para el vendedor.
 * Devuelve true si TOA tenía el FE (y ya quedó guardado en
 * pbi2.fija_data_toa), false si TOA no lo tiene, null si el servicio no
 * respondió (caído, timeout, error de red).
 */
function _dispararBusquedaTOA(fe) {
  return new Promise((resolve) => {
    const body = JSON.stringify({ fe });
    const req = http.request(
      {
        host: SERVICIO_BUSQUEDA_HOST,
        port: SERVICIO_BUSQUEDA_PORT,
        path: "/buscar",
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
        timeout: SERVICIO_BUSQUEDA_TIMEOUT_MS,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          try {
            const parsed = JSON.parse(data);
            resolve(res.statusCode === 200 ? Boolean(parsed.encontrado) : null);
          } catch (_) {
            resolve(null);
          }
        });
      }
    );
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
    req.on("error", () => resolve(null)); // servicio no disponible — se trata como "no se pudo verificar"
    req.write(body);
    req.end();
  });
}

// Incidente 2026-08-24 — CAUSA RAÍZ CONFIRMADA (no es código propio, no es
// el perfil de Chrome, no es un cambio de versión local): msg.getChat()
// falla intermitentemente con un error interno minificado ("r: r"), dentro
// de Client.getChatById -> window.WWebJS.getChat (whatsapp-web.js/src/
// Client.js:1754). Verificado paso a paso:
//   1. Reproducido incluso con el código de este archivo revertido a la
//      forma más simple posible (sin reintento, sin contador) — descarta
//      que sea un bug introducido por este proyecto.
//   2. Reproducido con session_data completamente limpio y re-autenticado
//      desde cero — descarta perfil de Chrome corrupto.
//   3. whatsapp-web.js sigue en el mismo commit desde el 23/08 (sin
//      commits nuevos en el repo upstream desde julio) y la versión de WA
//      Web cacheada localmente no cambió desde el 21/08 — descarta una
//      actualización de nuestro lado.
//   4. Confirmado por búsqueda externa: es un bug ACTIVO Y CONOCIDO de la
//      comunidad de whatsapp-web.js (GitHub issues #201838 y #201845,
//      julio 2026, mismo error exacto "r: r" en getChatById/getChats,
//      persiste incluso limpiando caché/sesión — igual que en el punto 2).
//      Coincide con el lanzamiento de "WhatsApp Web Calling" por Meta
//      (28/07/2026), que cambió la estructura interna del store de
//      WhatsApp Web. Meta despliega este tipo de cambios de forma GRADUAL
//      por cuenta/región del lado del servidor, sin que cambie ningún
//      número de versión visible del cliente — explica por qué esta
//      cuenta funcionó bien varios días (viernes a domingo) y dejó de
//      funcionar sin que nada local hubiera cambiado: es plausible que el
//      rollout de Meta alcanzara a esta cuenta en ese lapso.
//   5. AVANCE_MOVISTAR/wa_server.js (mismo entorno, misma librería) nunca
//      se ve afectado porque es un bot puramente de ENVÍO — no tiene
//      listener de mensajes entrantes, nunca llama getChat()/getChatById.
//      El bug solo se dispara al intentar RESOLVER el chat de un mensaje
//      entrante, algo que Yugi sí necesita hacer (para leer /estado).
//
// FIX REAL (no solo mitigación): dejamos de llamar msg.getChat() por
// completo. Lo único que se usaba de `chat` era chat.isGroup y chat.name
// (solo para logging) — ambos se pueden derivar directo de msg.from sin
// tocar el store roto: todo ID de grupo de WhatsApp termina en "@g.us"
// (confirmado con datos reales de nuestros propios logs), a diferencia de
// "@c.us" (contacto individual) o "@lid". msg.reply() tampoco depende de
// chat. Con esto, Yugi vuelve a "escuchar" con normalidad SIN pasar por el
// método roto — no es que el bug se haya arreglado (sigue activo del lado
// de Meta/whatsapp-web.js), es que dejamos de necesitar la función que
// choca con él para este flujo en particular.
function _esMensajeDeGrupo(msg) {
  return typeof msg.from === "string" && msg.from.endsWith("@g.us");
}

/**
 * Registra el listener de mensajes sobre un cliente whatsapp-web.js ya
 * inicializado. `log` es la función de logging de wa_toa_server.js
 * (reutilizada para que todo quede en el mismo archivo de log diario).
 */
function registrarListenerEstado(waClient, log) {
  waClient.on("message", async (msg) => {
    // Solo grupos — nunca procesar DMs (ver diseño: constraint explícita).
    // Detectado sobre msg.from directo, sin getChat() (ver nota arriba).
    if (!_esMensajeDeGrupo(msg)) return;

    const fe = _extraerFE(msg.body || "");
    if (!fe) return; // no matchea ningún formato válido — se ignora silenciosamente

    log("INFO", "Consulta de estado recibida", { fe, grupo: msg.from, autor: msg.author || msg.from });

    try {
      let respuesta = await _consultarEstadoFE(fe, log);

      if (respuesta === MSG_SIN_RASTRO_TOA && !_dentroDeVentanaBusqueda()) {
        // Fuera de la ventana laboral del servicio de búsqueda (8:00-20:00)
        // — toa_servicio_busqueda.py --http no está corriendo a esta hora
        // (ver nota junto a VENTANA_BUSQUEDA_INICIO_HORA). Decisión
        // explícita del usuario (2026-08-24): silencio total, sin
        // responder nada, en vez de un mensaje avisando el horario.
        log("INFO", "Paso 3b omitido: fuera de ventana laboral de busqueda TOA, silencio total", { fe });
        return;
      }

      if (respuesta === MSG_SIN_RASTRO_TOA) {
        log("INFO", "Paso 3b: FE nunca buscado en TOA, disparando busqueda puntual con reintentos", { fe });
        // Objetivo del proyecto (2026-08-22): priorizar info correcta y
        // actualizada sobre velocidad de respuesta — un solo intento no le
        // da tiempo a TOA si el FE fue vendido hace poco. Reintenta con
        // backoff (3s, 6s, 12s) dentro del presupuesto de ~60s ya acordado
        // para esta búsqueda puntual, en vez de conformarse tras 1 intento.
        for (let intento = 1; intento <= BUSQUEDA_TOA_MAX_REINTENTOS; intento++) {
          const encontrado = await _dispararBusquedaTOA(fe);
          if (encontrado) {
            // El servicio ya confirmó el INSERT antes de responder, pero la
            // relectura es un proceso Python NUEVO (consultar_estado_fe.py
            // corre vía execFile) — cada relectura abre su propio pool de
            // conexiones. El DBA confirmó (2026-08-20) que hay que revisar
            // cómo el cliente consume la conexión: encadenar muchas
            // relecturas, cada una con sus propios reintentos internos,
            // multiplica la presión de logins contra adminpbi2 en vez de
            // aliviarla.
            await new Promise((r) => setTimeout(r, 1500));
            respuesta = await _consultarEstadoFE(fe, log);
            log("INFO", "Paso 3b: busqueda puntual resuelta", { fe, intento, respuesta });
            break;
          }
          log("INFO", "Paso 3b: TOA no tiene el FE aun o el servicio no respondio", { fe, intento, encontrado });
          // respuesta se mantiene como MSG_SIN_RASTRO_TOA — es lo correcto
          // tanto si TOA de verdad no tiene el FE como si el servicio de
          // búsqueda está caído (mismo mensaje, sin distinguir el motivo
          // técnico ante el vendedor).
          if (intento < BUSQUEDA_TOA_MAX_REINTENTOS) {
            const espera = BUSQUEDA_TOA_ESPERA_BASE_MS * 2 ** (intento - 1);
            await new Promise((r) => setTimeout(r, espera));
          }
        }
      }

      await _esperaHumana();
      await msg.reply(respuesta);
      log("INFO", "Respuesta de estado enviada", { fe, respuesta });
    } catch (e) {
      // Fallo del propio proceso Python (timeout/crash real, no "no
      // encontrado" — eso ya se maneja como mensaje normal). Objetivo del
      // proyecto (2026-08-22): el vendedor NUNCA debe ver un mensaje que
      // delate una dificultad técnica — eso genera desconfianza hacia
      // Yugi. Se responde el mismo mensaje neutro que "dato aún no
      // disponible" en vez de admitir el fallo.
      log("ERROR", "Error consultando estado de FE", { fe, error: e.message });
      try {
        await msg.reply(MSG_SIN_RASTRO_TOA);
      } catch (_) {
        // si ni siquiera se puede responder, el propio watchdog/circuit
        // breaker de wa_toa_server.js ya se encarga de detectar sesión caída
      }
    }
  });

  log("INFO", "Listener de /estado FE-... registrado");
}

module.exports = { registrarListenerEstado };
