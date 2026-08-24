# Vigilante externo de toa_servicio_busqueda.py --http (puerto 8004).
#
# Contexto (2026-08-21): este servicio se caia sin que nadie lo notara,
# a diferencia de Yugi (que ya tenia resucitar_yugi.ps1). Causa real
# identificada: mientras varias personas comparten la misma cuenta de
# TOA_PORTAL_USERNAME, cualquier backoffice humano que se loguea despues
# y marca "cerrar sesiones anteriores" invalida NUESTRA sesion del lado
# del servidor, sin que el proceso muera segun el sistema operativo.
#
# El propio servicio ya tiene auto-relogin interno (ver
# toa_servicio_busqueda.py::ServicioBusquedaTOA - FALLOS_CONSECUTIVOS_PARA_RELOGIN)
# para ese caso especifico. Este vigilante es la red de seguridad para el
# caso mas simple: el proceso murio de verdad (no solo la sesion) y no
# queda nadie corriendo en el puerto 8004.
#
# A diferencia de resucitar_yugi.ps1, aqui NO conviene matar y relanzar
# solo porque /health no responde "ready" de inmediato - el login con
# Playwright tarda 10-40s, y este vigilante corre cada 5 min. Se usa un
# timeout generoso antes de considerarlo caido.
#
# Ventana laboral (2026-08-24, confirmado con el usuario): este servicio
# mantiene una sesion TOA autenticada de forma continua - antes corria
# 24/7 (confirmado en produccion: procesos de casi 48h seguidas), riesgo
# innecesario frente a Seguridad de Telefonica. Ahora solo debe operar de
# 8:00 a 20:00 - este vigilante NUNCA debe revivirlo fuera de esa ventana,
# aunque el health-check falle (esa caida fuera de horario es la conducta
# CORRECTA: toa_servicio_busqueda.py se auto-cierra a las 20:00, ver
# _vigilar_cierre_ventana en el propio script Python).

$ErrorActionPreference = "Stop"

$ProyectoDir = "C:\proyectos\au_tl_bot"
$LogDir = Join-Path $ProyectoDir "logs"
$LogFile = Join-Path $LogDir "resucitar_servicio_toa.log"
$HealthUrl = "http://localhost:8004/health"
$PythonExe = "C:\proyectos\.venv\Scripts\python.exe"
$VentanaInicio = New-Object DateTime 1, 1, 1, 8, 0, 0
$VentanaFin = New-Object DateTime 1, 1, 1, 20, 0, 0

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-Log {
    param([string]$Mensaje)
    $timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    "[$timestamp] $Mensaje" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Test-ServicioVivo {
    try {
        Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 8 -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-ProcesoServicio {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -like "*toa_servicio_busqueda.py*--http*" }
}

function Test-DentroVentanaLaboral {
    $ahora = Get-Date
    $horaActual = New-Object DateTime 1, 1, 1, $ahora.Hour, $ahora.Minute, $ahora.Second
    return ($horaActual -ge $VentanaInicio -and $horaActual -lt $VentanaFin)
}

if (-not (Test-DentroVentanaLaboral)) {
    # Fuera de ventana: si el servicio sigue vivo por alguna razon (el
    # propio Python no llego a auto-cerrarse a tiempo), lo apaga - nunca
    # debe quedar una sesion TOA activa fuera de horario laboral.
    $procesos = Get-ProcesoServicio
    if ($procesos) {
        Write-Log "Fuera de ventana laboral (8:00-20:00) y el servicio sigue vivo - deteniendolo."
        foreach ($p in $procesos) {
            try {
                Stop-Process -Id $p.ProcessId -Force -Confirm:$false -ErrorAction Stop
                Write-Log "PID $($p.ProcessId) detenido (fuera de horario)."
            } catch {
                Write-Log "No se pudo detener PID $($p.ProcessId): $($_.Exception.Message)"
            }
        }
    }
    exit 0
}

if (Test-ServicioVivo) {
    exit 0
}

Write-Log "Servicio de busqueda TOA (puerto 8004) no responde - investigando."

$procesos = Get-ProcesoServicio

if ($procesos) {
    $pids = $procesos.ProcessId -join ", "
    Write-Log "Proceso(s) encontrados (PID: $pids) pero no responden /health - terminando antes de relanzar."
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
    Write-Log "Ningun proceso toa_servicio_busqueda.py --http encontrado - estaba completamente caido."
}

Write-Log "Relanzando toa_servicio_busqueda.py --http..."

try {
    Start-Process -FilePath $PythonExe -ArgumentList "toa_servicio_busqueda.py --http" -WorkingDirectory $ProyectoDir -WindowStyle Hidden
    Write-Log "Proceso relanzado. Esperando a que el login termine..."
} catch {
    Write-Log "ERROR al relanzar: $($_.Exception.Message)"
    exit 1
}

# El login con Playwright puede tardar 10-40s - margen generoso antes de
# reportar advertencia, evita falsos positivos de "no revivio" cuando en
# realidad solo esta tardando el login normal.
Start-Sleep -Seconds 35

if (Test-ServicioVivo) {
    Write-Log "Servicio de busqueda TOA revivido correctamente - /health responde."
} else {
    Write-Log "ADVERTENCIA: servicio relanzado pero aun no responde tras 35s (puede seguir en login, o el login esta fallando - revisar manualmente)."
}
