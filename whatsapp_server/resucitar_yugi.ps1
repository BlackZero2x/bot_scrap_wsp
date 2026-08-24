# Vigilante externo de wa_toa_server.js ("Yugi Backoffice").
#
# Contexto (2026-08-20/21): el proceso Node murio sin dejar ningun rastro
# en su propio log (no fue un fallo controlado del codigo - ni
# "disconnected", ni circuit breaker, ni error - simplemente dejo de
# aparecer en la lista de procesos). Eso significa que el propio proceso
# no puede detectar ni reportar su propia muerte externa. Este script
# corre APARTE (via Programador de Tareas de Windows, no como hijo de
# wa_toa_server.js) para que la muerte de Yugi no se lleve consigo al
# mecanismo que lo revive.
#
# Que hace, en cada ejecucion:
#   1. Si el proceso node.exe con wa_toa_server.js en su linea de comando
#      no existe, o existe pero el puerto 8003 no responde /health como
#      "ready" dentro de un margen razonable, lo considera caido.
#   2. Si esta caido: mata cualquier resto del proceso (por si quedo
#      zombie) y relanza wa_toa_server.js.
#   3. Registra cada accion en logs/resucitar_yugi.log - separado del log
#      propio de Yugi, para no depender de que Yugi este vivo para poder
#      loguear su propia caida.
#
# Uso previsto: tarea programada de Windows, ejecutandose cada 5 minutos.
# No hace nada (silencioso) si Yugi ya esta sano - solo actua y loguea
# cuando detecta y corrige una caida real.

$ErrorActionPreference = "Stop"

$ProyectoDir = "C:\proyectos\au_tl_bot\whatsapp_server"
$LogDir = Join-Path $ProyectoDir "logs"
$LogFile = Join-Path $LogDir "resucitar_yugi.log"
$HealthUrl = "http://localhost:8003/health"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-Log {
    param([string]$Mensaje)
    $timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    "[$timestamp] $Mensaje" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Test-YugiSano {
    try {
        $respuesta = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 8
        return $respuesta.status -eq "ready"
    } catch {
        return $false
    }
}

function Get-ProcesoYugi {
    Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
        Where-Object { $_.CommandLine -like "*wa_toa_server.js*" }
}

$sano = Test-YugiSano

if ($sano) {
    exit 0
}

Write-Log "Yugi no responde /health como ready - investigando."

$procesos = Get-ProcesoYugi

if ($procesos) {
    $pids = $procesos.ProcessId -join ", "
    Write-Log "Proceso(s) node.exe con wa_toa_server.js encontrados (PID: $pids) pero no responde /health - terminando antes de relanzar."
    foreach ($p in $procesos) {
        try {
            Stop-Process -Id $p.ProcessId -Force -Confirm:$false -ErrorAction Stop
            Write-Log "PID $($p.ProcessId) terminado."
        } catch {
            Write-Log "No se pudo terminar PID $($p.ProcessId): $($_.Exception.Message)"
        }
    }
    Start-Sleep -Seconds 3
} else {
    Write-Log "Ningun proceso node.exe con wa_toa_server.js encontrado - estaba completamente caido."
}

Write-Log "Relanzando wa_toa_server.js..."

try {
    Start-Process -FilePath "node" -ArgumentList "wa_toa_server.js" -WorkingDirectory $ProyectoDir -WindowStyle Hidden
    Write-Log "Proceso relanzado. Esperando a que levante..."
} catch {
    Write-Log "ERROR al relanzar: $($_.Exception.Message)"
    exit 1
}

Start-Sleep -Seconds 15

if (Test-YugiSano) {
    Write-Log "Yugi revivido correctamente - /health responde ready."
} else {
    Write-Log "ADVERTENCIA: Yugi relanzado pero aun no responde ready tras 15s (puede seguir cargando la sesion de WhatsApp, o requerir escaneo de QR si la sesion se perdio)."
}
