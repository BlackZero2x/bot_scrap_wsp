const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
require("dotenv").config({ path: path.join(__dirname, "..", ".env") });
const { registrarListenerEstado } = require("./wa_toa_listener");
const { registrarSaludosHorarios } = require("./wa_toa_saludos");

// ============================================================
// CONFIGURACIÓN
// ============================================================
// Instancia dedicada al bot "Yugi Backoffice" (au_tl_bot / TOA).
// Puerto y clientId distintos de la instancia de AVANCE_MOVISTAR (8002,
// automation_session) a propósito: son dos números de WhatsApp separados,
// cada uno con su propia sesión de Chrome — nunca deben compartir carpeta
// de sesión ni puerto (ver guard de instancia única al final del archivo).
const PORT = 8003;
const SESSION_DIR = path.join(__dirname, "session_data");
const LOG_DIR = path.join(__dirname, "logs");
const CONFIG_PATH = path.join(__dirname, "config.json");

[SESSION_DIR, LOG_DIR].forEach((dir) => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// ============================================================
// LOGGER
// ============================================================
function log(level, message, data) {
  const timestamp = new Date().toISOString();
  const entry = `[${timestamp}] [${level}] ${message}${data ? " | " + JSON.stringify(data) : ""}`;
  console.log(entry);
  const today = new Date().toISOString().slice(0, 10);
  const logFile = path.join(LOG_DIR, `wa_toa_server_${today}.log`);
  fs.appendFileSync(logFile, entry + "\n");
}

// ============================================================
// CARGAR CONFIG
// ============================================================
function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  } catch {
    log("WARN", "No se pudo cargar config.json, usando config vacia");
    return { groups: {}, contacts: {} };
  }
}

// ============================================================
// RESOLVER DESTINATARIO
// ============================================================
function resolveRecipient(nameOrId) {
  if (nameOrId.includes("@")) return nameOrId;
  const config = loadConfig();
  if (config.groups && config.groups[nameOrId]) return config.groups[nameOrId];
  if (config.contacts && config.contacts[nameOrId]) return config.contacts[nameOrId];
  return null;
}

// ============================================================
// CLIENTE WHATSAPP
// ============================================================
let waClient = null;
let isReady = false;
let _readySince = null;        // timestamp del último evento "ready" (ventana de gracia post-reinicio)
let _lastUploadError = null;   // timestamp del último "upload failed" para el health check
let _lastNotificacion = null;  // timestamp del último correo de alerta (throttle 30 min)

// Ventana de gracia tras un reinicio: el evento "ready" de whatsapp-web.js se
// dispara antes de que el store interno de WhatsApp Web termine de sincronizar
// del todo. Si hay envíos en cola justo en ese momento, sendMessage() no lanza
// excepción pero devuelve `undefined` — eso se contaba como "fallo de
// protocolo" y disparaba OTRO reinicio, entrando en loop (mismo patrón que
// AVANCE_MOVISTAR: 204 reinicios el 14/08/2026 en un solo día).
// _enGraciaPostReinicio() se usa para no drenar la cola de inmediato y para no
// sumar al contador de fallos consecutivos mientras dura la ventana.
const _GRACIA_POST_REINICIO_MS = 12000;
function _enGraciaPostReinicio() {
  return _readySince !== null && (Date.now() - _readySince) < _GRACIA_POST_REINICIO_MS;
}

// Envía una alerta por correo al administrador cuando la sesión WA falla.
// Tiene throttle: solo envía un correo cada 30 minutos aunque el error persista.
function _notificarError(tipo, detalle) {
  const THROTTLE_MS = 30 * 60 * 1000; // 30 minutos
  const ahora = Date.now();
  if (_lastNotificacion && (ahora - _lastNotificacion) < THROTTLE_MS) {
    log("INFO", "Notificacion de error omitida (throttle 30 min activo)");
    return;
  }
  _lastNotificacion = ahora;

  const { exec } = require("child_process");
  const pythonExe = "C:\\proyectos\\.venv\\Scripts\\python.exe";
  const script = path.join(__dirname, "notify_error.py");
  const safeDetalle = (detalle || "").replace(/"/g, "'").replace(/\n/g, " ");
  const cmd = `"${pythonExe}" "${script}" --tipo "${tipo}" --detalle "${safeDetalle}"`;

  log("INFO", "Enviando alerta por correo", { tipo });
  exec(cmd, { cwd: path.join(__dirname, "..") }, (err, stdout, stderr) => {
    if (err) {
      log("WARN", "No se pudo enviar alerta por correo", { error: err.message, stderr });
    } else {
      log("INFO", "Alerta por correo enviada", { stdout: stdout.trim() });
    }
  });
}

function startWhatsApp() {
  log("INFO", "Iniciando cliente WhatsApp (Yugi Backoffice)...");

  // Resolver la version de WA Web mas reciente disponible en cache local.
  // La libreria pide por defecto una version que puede no estar en cache; si
  // esa version no existe localmente Y el proxy bloquea web.whatsapp.com en
  // la descarga de la version exacta, el cliente se queda colgado entre
  // "authenticated" y "ready" indefinidamente (authTimeoutMs=0 => sin
  // timeout). Fix: inyectar la version mas reciente del cache local para que
  // no haga request externo (mismo fix aplicado en AVANCE_MOVISTAR 08/08/2026).
  const _wwebCacheDir = path.join(__dirname, ".wwebjs_cache");
  let _wwebVersion = "2.3000.1017054665"; // fallback al default de la libreria
  try {
    const _cacheFiles = fs.readdirSync(_wwebCacheDir)
      .filter(f => f.endsWith(".html"))
      // Comparación numérica real por segmento de versión (ej. "2.3000.X"),
      // no orden lexicográfico de string: un .sort() plano solo da el orden
      // cronológico correcto mientras todos los archivos cacheados tengan
      // la misma cantidad de dígitos por segmento — "2.10000.X" ordenaría
      // ANTES que "2.3000.Y" lexicográficamente (compara carácter a
      // carácter: '1' < '3'), eligiendo silenciosamente la versión
      // numéricamente más vieja como "más reciente" y reintroduciendo el
      // colgado "authenticated pero nunca ready" que este cache existe
      // para evitar. No reproducido aún con el contenido actual del cache
      // (los nombres existentes comparten cantidad de dígitos), pero es un
      // supuesto frágil que se rompe sin ninguna señal el día que cambie.
      .sort((a, b) => {
        const partesA = a.replace(".html", "").split(".").map(Number);
        const partesB = b.replace(".html", "").split(".").map(Number);
        for (let i = 0; i < Math.max(partesA.length, partesB.length); i++) {
          const diff = (partesA[i] || 0) - (partesB[i] || 0);
          if (diff !== 0) return diff;
        }
        return 0;
      });
    if (_cacheFiles.length > 0) {
      _wwebVersion = _cacheFiles[_cacheFiles.length - 1].replace(".html", "");
      log("INFO", "Usando version WA Web del cache local", { version: _wwebVersion });
    }
  } catch (_) {
    log("WARN", "No se pudo leer cache local de WA Web, usando version default", { version: _wwebVersion });
  }

  waClient = new Client({
    authStrategy: new LocalAuth({
      clientId: "toa_session",
      dataPath: SESSION_DIR,
    }),
    webVersion: _wwebVersion,
    webVersionCache: {
      type: "local",
      path: _wwebCacheDir,
    },
    puppeteer: {
      headless: true,
      executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-default-apps",
        "--no-first-run",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=TranslateUI",
        // NOTA: sin --single-process ni --no-zygote (ver AVANCE_MOVISTAR
        // 18/07/2026) — bajo carga sostenida provocaban que Chrome descartara
        // el contexto JS de la pagina => "Promise was collected". Multi-proceso
        // aisla el renderer y evita esa corrupcion de contexto.
        //
        // Las 3 variables (HTTP_PROXY + PROXY_USER + PROXY_PASS) se exigen
        // juntas aquí, no solo HTTP_PROXY — si solo HTTP_PROXY estuviera
        // seteada, Chrome arrancaría apuntando a un proxy que exige
        // autenticación, pero el bloque de abajo (que instala el handler de
        // authenticate()) nunca se activaría por faltarle PROXY_USER/PASS,
        // dejando el cliente colgado indefinidamente sin ningún diagnóstico
        // que lo relacione con las credenciales de proxy incompletas.
        ...(process.env.HTTP_PROXY && process.env.PROXY_USER && process.env.PROXY_PASS
          ? [`--proxy-server=${process.env.HTTP_PROXY}`]
          : []),
      ],
    },
  });

  // Autenticar proxy antes de cada navegación
  if (process.env.HTTP_PROXY && process.env.PROXY_USER && process.env.PROXY_PASS) {
    const _origInit = waClient.initialize.bind(waClient);
    waClient.initialize = async function () {
      const result = _origInit();
      // Esperar a que pupPage esté disponible y configurar autenticación.
      // Límite de intentos: sin esto, si Chrome se cae antes de crear la
      // página, o _reiniciarCliente() reemplaza waClient mientras este
      // intervalo aún apunta a la instancia vieja, el poll de 200ms corre
      // para siempre — un timer que se filtra por cada initialize(),
      // acumulándose entre reconexiones (ver historial de 204+ reinicios/día
      // en incidentes pasados, donde este tipo de fuga agrava el problema).
      const MAX_INTENTOS_AUTH_PROXY = 150; // 150 x 200ms = 30s de margen
      let intentos = 0;
      const interval = setInterval(async () => {
        intentos++;
        if (waClient.pupPage) {
          clearInterval(interval);
          try {
            await waClient.pupPage.authenticate({
              username: process.env.PROXY_USER,
              password: process.env.PROXY_PASS,
            });
            log("INFO", "Proxy autenticado en pupPage");
          } catch (e) {
            log("WARN", "Error autenticando proxy", { err: e.message });
          }
        } else if (intentos >= MAX_INTENTOS_AUTH_PROXY) {
          clearInterval(interval);
          log("WARN", "Timeout esperando pupPage para autenticar proxy — abortando poll", { intentos });
        }
      }, 200);
      return result;
    };
  }

  waClient.on("qr", (qr) => {
    log("INFO", "QR recibido — escanea con el numero +51 946 149 539 (Yugi Backoffice):");
    qrcode.generate(qr, { small: true });
  });

  waClient.on("ready", () => {
    isReady = true;
    _readySince = Date.now();
    log("INFO", "Cliente WhatsApp listo");
  });

  // Se registra una sola vez el listener de /estado FE-... — waClient es un
  // objeto nuevo cada vez que _reiniciarCliente() llama a startWhatsApp(), así
  // que el listener se re-adjunta automáticamente en cada reconexión sin
  // acumular handlers duplicados sobre el cliente anterior (destruido).
  //
  // 2026-08-24: el listener YA NO llama msg.getChat() (ver comentario
  // extenso en wa_toa_listener.js junto a _esMensajeDeGrupo) — se
  // reemplazó por una verificación directa sobre msg.from, evitando por
  // completo el bug conocido de whatsapp-web.js (GitHub issues
  // #201838/#201845, ligado al rollout de "WhatsApp Web Calling" de Meta).
  // Ya no hace falta el callback de auto-reinicio por fallos de getChat().
  registrarListenerEstado(waClient, log);

  waClient.on("authenticated", () => {
    log("INFO", "Autenticado correctamente");
  });

  waClient.on("auth_failure", (msg) => {
    isReady = false;
    log("ERROR", "Fallo de autenticacion — reintentando en 30s", { msg });
    setTimeout(() => _reiniciarCliente(), 30000);
  });

  waClient.on("disconnected", (reason) => {
    isReady = false;
    log("WARN", "Cliente desconectado — reintentando en 20s", { reason });
    _notificarError("Cliente desconectado", `WhatsApp Web se desconecto del servidor (Yugi Backoffice). Razon: ${reason}. Reconectando en 20 segundos.`);
    setTimeout(() => _reiniciarCliente(), 20000);
  });

  waClient.initialize();
}

let _reconectando = false;

// Circuit breaker: si hay demasiados reinicios en poco tiempo, el propio
// auto-reinicio deja de ser la solución y pasa a ser parte del problema
// (ver incidente AVANCE_MOVISTAR 15/08/2026: 217 reinicios en una tarde,
// cada 20-40s, sin estabilizarse nunca — compatible con una sesión de
// WhatsApp Web degradada del lado de Meta, no con algo que un reinicio de
// Chrome pueda arreglar). Si se detectan más de _BREAKER_MAX_REINICIOS
// dentro de _BREAKER_VENTANA_MS, se deja de reintentar automáticamente y se
// escala una alerta inmediata (sin el throttle de 30 min) para revisión manual.
const _BREAKER_MAX_REINICIOS = 6;
const _BREAKER_VENTANA_MS = 10 * 60 * 1000; // 10 minutos
let _reinicios = []; // timestamps de reinicios recientes
let _breakerAbierto = false;

async function _reiniciarCliente() {
  if (_breakerAbierto) {
    log("WARN", "Circuit breaker abierto — reinicio automatico suspendido, se requiere revision manual");
    return;
  }
  if (_reconectando) {
    log("INFO", "Reconexion ya en curso, ignorando duplicado");
    return;
  }

  const ahora = Date.now();
  _reinicios = _reinicios.filter((t) => ahora - t < _BREAKER_VENTANA_MS);
  _reinicios.push(ahora);
  if (_reinicios.length > _BREAKER_MAX_REINICIOS) {
    _breakerAbierto = true;
    isReady = false;
    log("ERROR", `Circuit breaker activado: ${_reinicios.length} reinicios en los ultimos ${_BREAKER_VENTANA_MS / 60000} min — se detiene el auto-reinicio`);
    _lastNotificacion = null; // fuerza que la siguiente alerta ignore el throttle de 30 min
    _notificarError(
      "Circuit breaker WA activado (Yugi Backoffice)",
      `Se detectaron ${_reinicios.length} reinicios en ${_BREAKER_VENTANA_MS / 60000} minutos. El servidor dejo de reintentar automaticamente para no agravar el problema. Revisar manualmente la sesion de WhatsApp Web (Dispositivos vinculados, numero +51 946 149 539) y reiniciar el proceso wa_toa_server.js cuando este resuelto.`
    );
    return;
  }

  _reconectando = true;
  isReady = false;
  log("INFO", "Destruyendo cliente anterior...");
  try {
    // Timeout de 15s para destroy — si Chrome está completamente bloqueado, no esperar indefinidamente
    if (waClient) {
      await Promise.race([
        waClient.destroy(),
        new Promise((_, rej) => setTimeout(() => rej(new Error("destroy timeout")), 15000)),
      ]);
    }
  } catch (e) {
    log("WARN", "Error al destruir cliente (ignorado)", { e: e.message });
  }
  // Siempre matar Chrome al reiniciar — libera RAM acumulada que causa "Promise was collected".
  // NOTA: taskkill /IM chrome.exe mata TODOS los procesos Chrome del sistema,
  // incluido el de la instancia de AVANCE_MOVISTAR si corre en la misma
  // máquina. Si ambas instancias conviven en el mismo servidor, este es un
  // punto de acoplamiento a vigilar — un reinicio de esta instancia también
  // reinicia (fuerza) la del otro proyecto.
  try {
    execSync("taskkill /F /IM chrome.exe /T", { stdio: "ignore" });
    log("INFO", "Procesos Chrome terminados forzosamente");
  } catch (_) { /* ignorar si no hay Chrome corriendo */ }

  waClient = null;

  // Esperar 8s para que el SO libere la RAM de Chrome antes de relanzar
  log("INFO", "Esperando 8s para liberar RAM antes de relanzar...");
  await new Promise((res) => setTimeout(res, 8000));

  log("INFO", "Relanzando cliente WhatsApp...");
  _reconectando = false;
  startWhatsApp();
}

// Watchdog: cada 2 minutos verifica que la página de WhatsApp Web sigue operativa.
// Usa un evaluate real sobre el contexto de WA (no solo `true`) para detectar
// Promise was collected antes de que llegue un envío real.
setInterval(async () => {
  if (!isReady || _reconectando) return;
  try {
    // Evalúa algo real en el contexto de la página WA — si el contexto JS fue descartado
    // por Chrome, esto lanzará "Promise was collected" igual que sendMessage
    await waClient.pupPage.evaluate(() => typeof window !== "undefined");
  } catch (e) {
    if (_isDetachedFrame(e)) {
      log("ERROR", "Watchdog: Chrome caido (detached Frame) — reiniciando cliente");
      isReady = false;
      _reiniciarCliente();
    } else if (_isPromiseCollected(e)) {
      log("ERROR", "Watchdog: contexto JS descartado (Promise collected) — reiniciando cliente");
      isReady = false;
      _lastUploadError = Date.now();
      _notificarError("Promise was collected (Watchdog, Yugi Backoffice)", "El watchdog de 2 minutos detecto que Chrome perdio el contexto JS de la pagina WA. Reiniciando sesion automaticamente.");
      _reiniciarCliente();
    } else {
      log("WARN", "Watchdog: error inesperado en ping", { error: e.message });
    }
  }
}, 2 * 60 * 1000);

// ============================================================
// COLA DE ENVÍO — dedicada a este proyecto (au_tl_bot / Yugi).
// A diferencia de wa_server.js (AVANCE_MOVISTAR), que comparte su cola entre
// 5 proyectos, esta instancia solo sirve al bot TOA — la prioridad "avance"
// no aplica aquí, pero se mantiene el mismo mecanismo por si en el futuro
// conviven varios consumidores (ej. bot conversacional + mantenimiento de
// scrapper.py compitiendo por el mismo envío).
//
// Diseño (idéntico al de AVANCE_MOVISTAR, reescrito 18/07/2026):
//  - Cola explícita (array), no cadena de promesas, para poder
//    DRENARLA de golpe cuando Chrome pierde el contexto y para
//    soportar PRIORIDAD.
//  - Mínimo 5 s entre mensajes salientes (anti-ban).
//  - Al detectar contexto muerto (Promise collected / Protocol
//    error / detached Frame) se DRENA la cola: todos los pendientes
//    se rechazan al instante en vez de esperar 5 s por cada uno.
// ============================================================
const SEND_DELAY_MS = 5000;
const QUEUE_MAX = 12;          // máximo de mensajes esperando en cola
const PRIORITY_AVANCE = 10;    // reservado para eventos puntuales de alta prioridad
const PRIORITY_NORMAL = 0;     // respuestas normales del bot /estado

let _queue = [];               // items: { fn, priority, seq, resolve, reject }
let _queueDepth = 0;           // = _queue.length (contador cacheado para los guards)
let _draining = false;         // true mientras el worker procesa un envío
let _seqCounter = 0;           // desempate FIFO dentro de la misma prioridad

function _isDetachedFrame(err) {
  return err && err.message && err.message.includes("detached Frame");
}

function _isUploadFailure(err) {
  return err && err.message && err.message.includes("upload failed");
}

function _isPromiseCollected(err) {
  return err && err.message && err.message.includes("Promise was collected");
}

function _isProtocolError(err) {
  return err && err.message && err.message.includes("Protocol error");
}

function _isUndefinedResult(err) {
  return err && err.message && err.message.includes("Cannot read properties of undefined");
}

// Un contexto muerto justifica drenar la cola completa (todos los
// envíos pendientes fallarían igual, uno por uno, esperando 5 s cada vez).
function _isContextoMuerto(err) {
  return _isDetachedFrame(err) || _isPromiseCollected(err) ||
         _isProtocolError(err) || _isUndefinedResult(err);
}

// Devuelve true si la cola está llena. Los endpoints deben rechazar con 503 si es así.
function queueFull() {
  return _queueDepth >= QUEUE_MAX;
}

// Rechaza al instante todos los envíos pendientes. Se llama cuando el
// contexto de Chrome murió: no tiene sentido esperar 5 s por cada uno.
function _drenarCola(motivo) {
  if (_queue.length === 0) return;
  const n = _queue.length;
  log("WARN", `Drenando cola — ${n} envios pendientes rechazados al instante`, { motivo });
  const pendientes = _queue;
  _queue = [];
  _queueDepth = 0;
  for (const item of pendientes) {
    item.reject(new Error(`Envio cancelado: ${motivo}. Reintenta cuando el servidor reconecte.`));
  }
}

// Encola un envío. priority alto => se atiende antes (dentro de la misma
// prioridad se respeta el orden de llegada vía seq).
function enqueue(fn, priority = PRIORITY_NORMAL) {
  return new Promise((resolve, reject) => {
    const item = { fn, priority, seq: _seqCounter++, resolve, reject };
    // Insertar respetando prioridad (mayor primero), luego FIFO por seq.
    let i = _queue.length;
    while (i > 0 && _queue[i - 1].priority < priority) i--;
    _queue.splice(i, 0, item);
    _queueDepth = _queue.length;
    _procesarCola();
  });
}

// Worker: procesa un envío a la vez, con SEND_DELAY_MS entre uno y otro.
async function _procesarCola() {
  if (_draining) return;           // ya hay un envío en curso
  if (_queue.length === 0) return;

  // Ventana de gracia post-reinicio: no drenar la cola hasta que el store de
  // WhatsApp Web probablemente terminó de sincronizar (ver _enGraciaPostReinicio).
  // Reintenta más tarde en vez de disparar sendMessage() contra una sesión
  // que aún no está lista de verdad.
  if (_enGraciaPostReinicio()) {
    const _restante = _GRACIA_POST_REINICIO_MS - (Date.now() - _readySince);
    setTimeout(() => _procesarCola(), Math.max(_restante, 500));
    return;
  }

  _draining = true;

  const item = _queue.shift();
  _queueDepth = _queue.length;

  try {
    const result = await item.fn();
    item.resolve(result);
  } catch (err) {
    // Manejo de errores de contexto: reiniciar cliente + drenar cola.
    if (_isUploadFailure(err)) {
      log("WARN", "upload failed detectado — sesion WA degradada, se reconectara en proximo health check");
      _lastUploadError = Date.now();
    } else if (_isContextoMuerto(err)) {
      log("ERROR", "Contexto WA muerto en envio — reiniciando cliente y drenando cola", { error: err.message.slice(0, 80) });
      isReady = false;
      _lastUploadError = Date.now();
      _notificarError("Contexto WA muerto (Yugi Backoffice)", `sendMessage fallo por contexto de Chrome perdido (${err.message.slice(0, 120)}). Reiniciando y drenando cola de ${_queue.length} pendientes.`);
      item.reject(err);
      _drenarCola("contexto de Chrome perdido");
      _draining = false;
      setTimeout(() => _reiniciarCliente(), 3000);
      return; // no aplicar el delay de 5s: no hay nada en cola y el cliente se reinicia
    }
    item.reject(err);
  }

  // Delay anti-ban antes del siguiente envío.
  setTimeout(() => {
    _draining = false;
    _procesarCola();
  }, SEND_DELAY_MS);
}

// ============================================================
// REINICIO PREVENTIVO PERIÓDICO — cada 6 horas reinicia Chrome
// para liberar RAM acumulada. Solo actúa si la cola está vacía
// (no interrumpe envíos en curso).
// ============================================================
const _REINICIO_PREVENTIVO_MS = 6 * 60 * 60 * 1000; // 6 horas
let _ultimoReinicioPreventivo = Date.now();

function _reinicioPreventivo() {
  if (_reconectando) return;
  const ahora = Date.now();
  if ((ahora - _ultimoReinicioPreventivo) < _REINICIO_PREVENTIVO_MS) return;
  if (_queueDepth > 0) {
    // No reprogramar el temporizador: reintentará en el próximo tick cuando la cola se vacíe.
    log("INFO", "Reinicio preventivo postergado — cola no vacia", { pendientes: _queueDepth });
    return;
  }
  _ultimoReinicioPreventivo = ahora;
  log("INFO", "Reinicio preventivo (cada 6h) — liberando RAM de Chrome acumulada");
  _reiniciarCliente();
}

// Verificar cada minuto si toca el reinicio preventivo
setInterval(_reinicioPreventivo, 60 * 1000);

// Saludos de entrada/salida por ventana horaria — SOLO en el grupo de
// pruebas, ver wa_toa_saludos.js para el detalle de alcance y horarios.
// Se registra una sola vez a nivel de módulo (no dentro de startWhatsApp):
// el propio scheduler usa un getter (() => waClient) para siempre tomar el
// cliente vivo más reciente, así que sobrevive a reconexiones sin
// duplicarse.
registrarSaludosHorarios(() => waClient, log);

// ============================================================
// SERVIDOR EXPRESS
// ============================================================
const app = express();
app.use(cors());
app.use(express.json({ limit: "50mb" }));

// Resuelve la prioridad del envío a partir del body.
// Acepta priority numérico directo, o el atajo priority:"avance".
// Por defecto PRIORITY_NORMAL (respuestas normales del bot /estado).
function _resolverPrioridad(body) {
  const p = body && body.priority;
  if (typeof p === "number") return p;
  if (typeof p === "string" && p.toLowerCase() === "avance") return PRIORITY_AVANCE;
  return PRIORITY_NORMAL;
}

// sendMessage() de whatsapp-web.js puede devolver `undefined` sin lanzar
// excepción cuando WhatsApp Web cambió algo en su protocolo (mismo síntoma
// que detecta el send-test periódico, ver más abajo). Se registra como WARN y
// alimenta el mismo contador de fallos consecutivos que usa el send-test, así
// un patrón repetido en envíos reales también dispara el reinicio.
function _registrarResultadoEnvio(kind, result, ctx) {
  if (result && result.id) {
    if (_sendTestFails > 0) log("INFO", "Envio recuperado tras fallos previos de protocolo");
    _sendTestFails = 0;
    log("INFO", kind, ctx);
    return;
  }
  if (_enGraciaPostReinicio()) {
    // Dentro de la ventana de gracia post-reinicio: el store de WhatsApp Web
    // probablemente aún no sincronizó del todo. No cuenta como fallo de
    // protocolo — evita el loop de reinicios en cascada (ver _GRACIA_POST_REINICIO_MS).
    log("WARN", `${kind}: sendMessage devolvio resultado sin id (dentro de ventana de gracia post-reinicio, no cuenta como fallo)`, ctx);
    return;
  }
  _sendTestFails++;
  log("WARN", `${kind}: sendMessage devolvio resultado sin id (fallo #${_sendTestFails})`, ctx);
  if (_sendTestFails >= 2) {
    log("ERROR", "2 fallos consecutivos de protocolo en envios reales — protocolo WA degradado, reiniciando cliente");
    _notificarError(
      "Protocolo WA degradado (envio real, Yugi Backoffice)",
      `sendMessage devolvio resultado sin id en 2 envios consecutivos (ultimo: ${kind}). Es probable un cambio de protocolo de Meta. Reiniciando cliente automaticamente.`
    );
    _sendTestFails = 0;
    isReady = false;
    _reiniciarCliente();
  }
}

// Guard reutilizable: rechaza si el servidor no está listo o la cola está llena.
function _guardReady(res) {
  if (!isReady) {
    log("WARN", "Envio rechazado: WhatsApp no esta listo (503)");
    res.status(503).json({ error: "WhatsApp no esta listo" });
    return false;
  }
  if (queueFull()) {
    log("WARN", "Cola llena — rechazando envio para proteger RAM de Chrome", { depth: _queueDepth });
    res.status(503).json({ error: `Cola llena (${_queueDepth}/${QUEUE_MAX} mensajes pendientes). Reintenta en unos segundos.` });
    return false;
  }
  return true;
}

// --- Health check ---
// Además de isReady, verifica que el frame de Chrome siga respondiendo.
// Si hubo un "upload failed" reciente (último minuto), reporta degraded y fuerza reconexión.
app.get("/health", async (req, res) => {
  if (_breakerAbierto) {
    return res.json({ status: "circuit_breaker_abierto", reinicios_recientes: _reinicios.length, timestamp: new Date().toISOString() });
  }
  if (!isReady) {
    return res.json({ status: "not_ready", timestamp: new Date().toISOString() });
  }

  // Detectar upload failures recientes (en los últimos 90s)
  const ahoraMs = Date.now();
  if (_lastUploadError && (ahoraMs - _lastUploadError) < 90_000) {
    log("WARN", "Health: upload failure reciente detectado — marcando not_ready y reconectando");
    isReady = false;
    _lastUploadError = null;
    _reiniciarCliente();
    return res.json({ status: "not_ready", reason: "upload_failure", timestamp: new Date().toISOString() });
  }

  // Verificar que el frame de Chrome siga vivo
  try {
    await waClient.pupPage.evaluate(() => true);
    res.json({ status: "ready", timestamp: new Date().toISOString() });
  } catch (e) {
    log("WARN", "Health: Chrome no responde — marcando not_ready", { error: e.message });
    isReady = false;
    _reiniciarCliente();
    res.json({ status: "not_ready", reason: "chrome_unresponsive", timestamp: new Date().toISOString() });
  }
});

// --- Listar grupos ---
app.get("/list-groups", async (req, res) => {
  if (!isReady) return res.status(503).json({ error: "WhatsApp no esta listo" });
  try {
    const chats = await waClient.getChats();
    const groups = chats
      .filter((c) => c.isGroup)
      .map((g) => ({ name: g.name, id: g.id._serialized, participants: g.participants?.length || 0 }));
    log("INFO", `Listados ${groups.length} grupos`);
    res.json(groups);
  } catch (err) {
    log("ERROR", "Error al listar grupos", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

// --- Buscar contactos por nombre ---
app.get("/list-contacts", async (req, res) => {
  if (!isReady) return res.status(503).json({ error: "WhatsApp no esta listo" });
  const { name } = req.query;
  if (!name) return res.status(400).json({ error: "Parametro 'name' requerido" });
  try {
    const contacts = await waClient.getContacts();
    const filtered = contacts
      .filter((c) =>
        (c.name && c.name.toLowerCase().includes(name.toLowerCase())) ||
        (c.pushname && c.pushname.toLowerCase().includes(name.toLowerCase()))
      )
      .map((c) => ({
        name: c.name || c.pushname || "Sin nombre",
        pushname: c.pushname || "",
        id: c.id._serialized,
        number: c.id.user,
      }));
    log("INFO", `Encontrados ${filtered.length} contactos para "${name}"`);
    res.json(filtered);
  } catch (err) {
    log("ERROR", "Error al buscar contactos", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

// --- Enviar texto ---
app.post("/send-text", async (req, res) => {
  if (!_guardReady(res)) return;
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: "Campos 'to' y 'message' requeridos" });
  const chatId = resolveRecipient(to);
  if (!chatId) return res.status(404).json({ error: `Destinatario "${to}" no encontrado en config` });
  try {
    const result = await enqueue(() => waClient.sendMessage(chatId, message), _resolverPrioridad(req.body));
    _registrarResultadoEnvio("Texto enviado", result, { to, chatId });
    res.json({ success: true, messageId: result?.id?._serialized || null });
  } catch (err) {
    log("ERROR", "Error al enviar texto", { to, error: err.message });
    res.status(500).json({ error: err.message });
  }
});

// --- Enviar imagen (desde ruta local) ---
app.post("/send-image", async (req, res) => {
  if (!_guardReady(res)) return;
  const { to, image_path, caption } = req.body;
  if (!to || !image_path) return res.status(400).json({ error: "Campos 'to' y 'image_path' requeridos" });
  const chatId = resolveRecipient(to);
  if (!chatId) return res.status(404).json({ error: `Destinatario "${to}" no encontrado en config` });
  if (!fs.existsSync(image_path)) return res.status(404).json({ error: `Archivo no encontrado: ${image_path}` });
  try {
    const media = MessageMedia.fromFilePath(image_path);
    const result = await enqueue(() => waClient.sendMessage(chatId, media, { caption: caption || "" }), _resolverPrioridad(req.body));
    _registrarResultadoEnvio("Imagen enviada", result, { to, chatId, image_path });
    res.json({ success: true, messageId: result?.id?._serialized || null });
  } catch (err) {
    log("ERROR", "Error al enviar imagen", { to, error: err.message });
    res.status(500).json({ error: err.message });
  }
});

// --- Enviar archivo (desde ruta local) ---
app.post("/send-file", async (req, res) => {
  if (!_guardReady(res)) return;
  const { to, file_path, caption } = req.body;
  if (!to || !file_path) return res.status(400).json({ error: "Campos 'to' y 'file_path' requeridos" });
  const chatId = resolveRecipient(to);
  if (!chatId) return res.status(404).json({ error: `Destinatario "${to}" no encontrado en config` });
  if (!fs.existsSync(file_path)) return res.status(404).json({ error: `Archivo no encontrado: ${file_path}` });
  try {
    const media = MessageMedia.fromFilePath(file_path);
    const result = await enqueue(() => waClient.sendMessage(chatId, media, { caption: caption || "" }), _resolverPrioridad(req.body));
    _registrarResultadoEnvio("Archivo enviado", result, { to, chatId, file_path });
    res.json({ success: true, messageId: result?.id?._serialized || null });
  } catch (err) {
    log("ERROR", "Error al enviar archivo", { to, error: err.message });
    res.status(500).json({ error: err.message });
  }
});

// --- Enviar texto con menciones ---
app.post("/send-mention", async (req, res) => {
  if (!_guardReady(res)) return;
  const { to, message, mentions } = req.body;
  if (!to || !message) return res.status(400).json({ error: "Campos 'to' y 'message' requeridos" });
  const chatId = resolveRecipient(to);
  if (!chatId) return res.status(404).json({ error: `Destinatario "${to}" no encontrado en config` });
  try {
    // whatsapp-web.js >=1.34 acepta directamente IDs (string[]) en `mentions`
    // y los resuelve internamente — pasar objetos Contact esta deprecado.
    const mentionIds = mentions || [];
    log("INFO", "Intentando enviar menciones", { to, chatId, mentionIds });

    const _prio = _resolverPrioridad(req.body);
    let result;
    try {
      result = await enqueue(() =>
        waClient.sendMessage(chatId, message, { mentions: mentionIds })
      , _prio);
    } catch (mentionErr) {
      log("WARN", "Menciones fallaron, enviando sin ellas", { to, error: mentionErr.message });
      result = await enqueue(() => waClient.sendMessage(chatId, message), _prio);
    }
    _registrarResultadoEnvio("Mensaje con menciones enviado", result, { to, chatId, menciones: mentionIds.length });
    res.json({ success: true, messageId: result?.id?._serialized || null });
  } catch (err) {
    log("ERROR", "Error al enviar menciones", { to, error: err.message, stack: err.stack });
    res.status(500).json({ error: err.message });
  }
});

// --- Enviar link ---
app.post("/send-link", async (req, res) => {
  if (!_guardReady(res)) return;
  const { to, url, description } = req.body;
  if (!to || !url) return res.status(400).json({ error: "Campos 'to' y 'url' requeridos" });
  const chatId = resolveRecipient(to);
  if (!chatId) return res.status(404).json({ error: `Destinatario "${to}" no encontrado en config` });
  try {
    const message = description ? `${description}\n${url}` : url;
    const result = await enqueue(() => waClient.sendMessage(chatId, message), _resolverPrioridad(req.body));
    _registrarResultadoEnvio("Link enviado", result, { to, chatId, url });
    res.json({ success: true, messageId: result?.id?._serialized || null });
  } catch (err) {
    log("ERROR", "Error al enviar link", { to, error: err.message });
    res.status(500).json({ error: err.message });
  }
});

// --- Enviar texto citando (reply) un mensaje entrante ---
// Endpoint nuevo respecto a wa_server.js: pensado para el listener del bot
// /estado (wa_toa_listener.js) — permite responder citando el mensaje
// original del vendedor vía msg.reply() en vez de sendMessage() suelto (ver
// diseño de arquitectura: ancla la respuesta visualmente, evita confusión
// con el hilo de conversación humana del backoffice en el mismo grupo).
// No pasa por la cola de salida: se invoca directamente desde el propio
// listener del cliente (mismo proceso), no vía HTTP externo.
// Se documenta aquí para quien lea este archivo buscando paridad 1:1 con
// wa_server.js y se pregunte por qué no hay un endpoint /send-reply: el
// reply vive en el listener, no en la API HTTP, porque requiere el objeto
// `msg` original que solo existe en el evento "message" del propio cliente.

// --- Enviar imagen (desde ruta local) --- ya cubierto arriba.

// ============================================================
// SEND-TEST PERIÓDICO — detecta fallos de protocolo antes de que
// fallen envíos reales. Cada 3 horas envía un mensaje silencioso
// al propio número (OWNER_WA_ID en .env). Si sendMessage devuelve
// undefined dos veces seguidas, dispara alerta y reinicia el cliente.
// ============================================================
const _SEND_TEST_INTERVAL_MS = 3 * 60 * 60 * 1000; // 3 horas
let _sendTestFails = 0;

async function _runSendTest() {
  if (!isReady || _reconectando) return;

  // Usa OWNER_WA_ID_TOA si está definida (para separar la alerta de la
  // instancia de AVANCE_MOVISTAR), si no cae de vuelta a OWNER_WA_ID.
  const myNumber = process.env.OWNER_WA_ID_TOA || process.env.OWNER_WA_ID;
  if (!myNumber) return; // variable no configurada → omitir silenciosamente

  const chatId = myNumber.includes("@") ? myNumber : `${myNumber}@c.us`;
  try {
    const result = await waClient.sendMessage(chatId, "✔️ [auto-test] servidor WA (Yugi Backoffice) operativo");
    if (!result || !result.id) {
      if (_enGraciaPostReinicio()) {
        // Ver _GRACIA_POST_REINICIO_MS: no cuenta como fallo de protocolo.
        log("WARN", "Send-test: sendMessage devolvio undefined (dentro de ventana de gracia post-reinicio, no cuenta como fallo)", { chatId });
        return;
      }
      _sendTestFails++;
      log("WARN", `Send-test: sendMessage devolvio undefined (fallo #${_sendTestFails})`, { chatId });
      if (_sendTestFails >= 2) {
        log("ERROR", "Send-test: 2 fallos consecutivos — protocolo WA degradado, reiniciando cliente");
        _notificarError(
          "Protocolo WA degradado (send-test, Yugi Backoffice)",
          `sendMessage devolvio undefined en 2 pruebas consecutivas. Es probable un cambio de protocolo de Meta. Reiniciando cliente automaticamente.`
        );
        _sendTestFails = 0;
        isReady = false;
        _reiniciarCliente();
      }
    } else {
      if (_sendTestFails > 0) log("INFO", "Send-test: recuperado tras fallos anteriores");
      _sendTestFails = 0;
      log("INFO", "Send-test OK", { chatId });
    }
  } catch (e) {
    _sendTestFails++;
    log("WARN", `Send-test: error al enviar (fallo #${_sendTestFails})`, { error: e.message });
    if (_sendTestFails >= 2) {
      log("ERROR", "Send-test: 2 errores consecutivos — reiniciando cliente");
      _notificarError("Protocolo WA degradado (send-test, Yugi Backoffice)", `Error en send-test: ${e.message}`);
      _sendTestFails = 0;
      isReady = false;
      _reiniciarCliente();
    }
  }
}

// Primera prueba 5 minutos después de arrancar (esperar a que el cliente esté listo)
setTimeout(() => {
  _runSendTest();
  setInterval(_runSendTest, _SEND_TEST_INTERVAL_MS);
}, 5 * 60 * 1000);

// ============================================================
// AUTO-UPDATE SEMANAL — actualiza whatsapp-web.js desde GitHub
// (el repo tiene fixes antes que npm). Se ejecuta los domingos
// a las 3 AM hora local para minimizar impacto operativo.
// ============================================================
function _autoUpdateWwjs() {
  const ahora = new Date();
  // Solo ejecutar domingos (0) entre 03:00 y 03:59
  if (ahora.getDay() !== 0 || ahora.getHours() !== 3) return;

  log("INFO", "Auto-update: iniciando actualización de whatsapp-web.js desde GitHub...");
  const { exec } = require("child_process");
  const cmd = "npm install github:pedroslopez/whatsapp-web.js --save";
  exec(cmd, { cwd: __dirname }, (err, stdout, stderr) => {
    if (err) {
      log("WARN", "Auto-update: error al actualizar whatsapp-web.js", { error: err.message, stderr });
      return;
    }
    // Verificar si cambió algo comparando el gitHead del package instalado
    try {
      const pkgPath = path.join(__dirname, "node_modules", "whatsapp-web.js", "package.json");
      const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
      log("INFO", "Auto-update: whatsapp-web.js actualizado", {
        version: pkg.version,
        gitHead: pkg.gitHead || "N/A",
      });
    } catch (_) {
      log("INFO", "Auto-update: actualización completada", { stdout: stdout.trim() });
    }
    // Reiniciar el cliente para que tome la nueva versión
    log("INFO", "Auto-update: reiniciando cliente para aplicar nueva version...");
    setTimeout(() => _reiniciarCliente(), 3000);
  });
}

// Verificar cada hora si es momento de hacer el update
setInterval(_autoUpdateWwjs, 60 * 60 * 1000);

// ============================================================
// INICIAR TODO — con guard de INSTANCIA ÚNICA
// Si el puerto 8003 ya está en uso, significa que otro
// wa_toa_server.js ya está corriendo (watchdog + reinicio interno
// pisándose). En ese caso NO arrancamos Chrome: abortamos limpio para
// no tener dos clientes WhatsApp compitiendo por la misma sesión.
// ============================================================
const server = app.listen(PORT);

server.on("listening", () => {
  log("INFO", `Servidor HTTP escuchando en puerto ${PORT} (Yugi Backoffice)`);
  startWhatsApp();
});

server.on("error", (err) => {
  if (err.code === "EADDRINUSE") {
    log("ERROR", `Puerto ${PORT} ya en uso — ya existe otra instancia de wa_toa_server.js. Abortando esta instancia para evitar sesiones WA duplicadas.`);
    process.exit(1);
  } else {
    log("ERROR", "Error al iniciar servidor HTTP", { error: err.message });
    process.exit(1);
  }
});
