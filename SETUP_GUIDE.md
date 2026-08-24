# Guía de Configuración - au_tl_bot

## ✅ Paso 3 Completado: Credenciales y Variables de Entorno

### Archivos Creados

#### 1. **`.env.example`** (Template público)
- Contiene todas las variables de entorno necesarias con placeholders
- Úsalo como referencia para crear configuraciones nuevas
- Se puede commitear al repositorio

#### 2. **`.env`** (Archivo local con credenciales reales)
- Contiene las credenciales reales
- **NUNCA se commitea** (está en `.gitignore`)
- Cada desarrollador debe tener su propia copia

#### 3. **`config.py`** (Configuración centralizada)
- Módulo Python que carga variables desde `.env`
- Proporciona funciones helper para obtener motores SQLAlchemy
- Importable desde cualquier script del proyecto:
  ```python
  from config import engine_auren, engine_toa
  from config import TOA_USER, AUREN_DB, etc.
  ```

#### 4. **`.gitignore`** (Actualizado)
- Ahora ignora: `.env`, `.env.local`, `*.xlsx`, `*.csv`, `__pycache__/`, etc.
- Protege credenciales de commits accidentales

### Scripts Refactorizados

Se actualizaron los siguientes archivos para usar la configuración centralizada:

| Archivo | Cambio |
|---------|--------|
| `scripts_db/fe_consultar.py` | Ahora importa `engine_auren()` desde `config.py` |
| `scripts_db/data_extraida.py` | Ahora importa `engine_toa()` desde `config.py` |
| `query_fe_filter.py` | Ahora importa ambos engines desde `config.py` |

### Nuevo: Script de Test

**`test_connection.py`** — Valida que ambas conexiones SQL Server funcionen:

```bash
python test_connection.py
```

Salida esperada:
```
✅ eAuren
   Servidor: AUREN22\AUREN
   Base de datos: eAuren
   Usuario: eauren
   Versión SQL: Microsoft SQL Server 2019...

✅ pbi2
   Servidor: AUREN22\AUREN
   Base de datos: pbi2
   Usuario: adminpbi2
   Versión SQL: Microsoft SQL Server 2019...

✅ Todas las conexiones están funcionando correctamente.
```

### Archivos Modificados en `.gitignore`

```
.env                      # Variables sensibles
.env.local               # Overrides locales
*.xlsx                   # Archivos Excel temporales
*.csv                    # Archivos CSV de extracción
__pycache__/             # Bytecode Python
*.pyc                    # Compiled Python
.pytest_cache/           # Cache de tests
.coverage                # Coverage reports
htmlcov/                 # Coverage HTML
```

### Cómo Usar

1. **Instalación inicial:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuración por primera vez:**
   ```bash
   cp .env.example .env
   # Editar .env con credenciales reales
   ```

3. **Verificar conectividad:**
   ```bash
   python test_connection.py
   ```

4. **Usar en scripts:**
   ```python
   from config import engine_auren, engine_toa
   
   # Obtener datos de eAuren (fuente)
   with engine_auren().connect() as conn:
       df = pd.read_sql("SELECT * FROM dbo.fija_controlnet_detallado", conn)
   
   # Guardar en pbi2 (destino)
   with engine_toa().connect() as conn:
       df.to_sql("fija_data_toa", conn, if_exists="append", index=False)
   ```

### Variables de Entorno Disponibles

#### SQL Server - eAuren (Fuente)
- `AUREN_SERVER` — Servidor SQL
- `AUREN_DB` — Nombre de BD
- `AUREN_USER` — Usuario
- `AUREN_PASSWORD` — Contraseña
- `AUREN_DRIVER` — Driver ODBC

#### SQL Server - pbi2 (Destino)
- `TOA_SERVER` — Servidor SQL
- `TOA_DB` — Nombre de BD
- `TOA_USER` — Usuario
- `TOA_PASSWORD` — Contraseña
- `TOA_DRIVER` — Driver ODBC

#### TOA Portal
- `TOA_USERNAME` — Usuario de login en portal TOA
- `TOA_PASSWORD` — Contraseña de portal TOA

#### WhatsApp Bot (Futuro)
- `WHATSAPP_PHONE_NUMBER_ID` — ID de número de WhatsApp
- `WHATSAPP_ACCESS_TOKEN` — Token de acceso Meta
- `WHATSAPP_VERIFY_TOKEN` — Token de verificación webhook

### Próximos Pasos

1. **Paso 4:** Integrar credenciales TOA Portal en `scrapper.py`
2. **Paso 5:** Implementar WhatsApp Bot con variables de entorno
3. **Paso 6:** Actualizar documentación de deployment
