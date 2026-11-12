# Gestión de proyectos

Aplicación Flask para el Proyecto Integrador de Gestión de Proyectos de
Software. El backend usa Python 3.12, SQLAlchemy 2.x y PostgreSQL en
producción. Las tareas son una lista plana: `etapa` solo agrupa visualmente y
no existe EDT/WBS.

## Instalación local

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
export FLASK_APP=app
flask db upgrade
flask seed-demo
flask run
```

`flask seed-demo` imprime dos contraseñas aleatorias una sola vez. No hay
credenciales demo fijas en el código.

Para usar SQLite local basta con omitir `DATABASE_URL`; no se debe usar SQLite
en Vercel porque el disco serverless es efímero.

## Variables de entorno

- `SECRET_KEY`: secreto aleatorio obligatorio en producción.
- `DATABASE_URL`: PostgreSQL Neon; se normaliza `postgres://` y se añade
  `sslmode=require`.
- `FLASK_ENV=production`: activa HTTPS, cookies Secure y `NullPool`.
- `RATELIMIT_STORAGE_URI`: localmente `memory://`; en Vercel usa la cadena
  Redis TLS (`rediss://...`) de Upstash para un límite compartido entre
  instancias. La URL REST y el token de `upstash-redis` no sirven directamente
  como `RATELIMIT_STORAGE_URI`; copia la conexión Redis desde Upstash.
- `RATES_API_URL`: URL HTTPS fija del proveedor, por defecto
  `https://mindicador.cl/api`.
- `CRON_SECRET`: secreto usado por Vercel Cron para `/internal/refresh-rates`.

Nunca se debe commitear `.env`.

## Pruebas y calidad

```bash
pytest -q
ruff check app api migrations scripts tests
bandit -r app api scripts -ll
pip-audit -r requirements.txt
```

La CI ejecuta estas comprobaciones en cada push y pull request.

## Despliegue Vercel + Neon

La entrada WSGI es [api/index.py](./api/index.py) y
[vercel.json](./vercel.json) reescribe todas las rutas hacia esa función.
Vercel detecta `requirements.txt` automáticamente. Los estáticos se sirven
desde Flask mediante `static_folder`; no se necesita Node ni un build step.

1. Crear una base PostgreSQL en Neon y copiar su URL con TLS.
2. Crear un proyecto Vercel conectado al repositorio.
3. Configurar en Vercel `SECRET_KEY`, `DATABASE_URL` y
   `FLASK_ENV=production`.
4. Crear en GitHub Actions los secrets `DATABASE_URL`, `SECRET_KEY`,
   `VERCEL_TOKEN`, `VERCEL_ORG_ID` y `VERCEL_PROJECT_ID`.
5. Hacer merge a `main`. `deploy.yml` ejecuta `flask db upgrade` contra Neon y
   después `vercel deploy --prod`.

Para cargar tasas históricas en producción, configura `DATABASE_URL` y
`SECRET_KEY` como secrets de GitHub y ejecuta manualmente el workflow
**Actualizar tasas**, o usa:

```bash
FLASK_APP=app flask backfill-rates --days 90
```

Vercel Cron ejecuta el refresco diario usando `CRON_SECRET`; el workflow
programado ofrece un respaldo independiente.

La moneda de presentación se selecciona en la barra superior. CLP es la moneda
base persistida; UF y USD se convierten únicamente al mostrar datos. Si la
última tasa disponible supera tres días, la interfaz muestra una advertencia.
El campo opcional de moneda de ingreso para recursos y cambios no forma parte
de esta fase.

Las migraciones nunca se ejecutan al importar la función serverless y nunca se
llama `create_all()` en producción.

## Seguridad, privacidad y soporte

El proyecto aplica CSRF, hash scrypt, RBAC, aislamiento por proyecto, auditoría,
cabeceras de seguridad y bloqueo/rate limit de login. La eliminación de cuenta
anonimiza autoría histórica cuando la integridad del proyecto requiere
conservarla. `/privacidad` y `/terminos` son borradores académicos, no asesoría
legal.

Consulta [docs/api.md](./docs/api.md), [docs/guion_demo.md](./docs/guion_demo.md)
y [docs/licencias.md](./docs/licencias.md). La solución y sus decisiones de
cumplimiento están descritas en [docs/00_cumplimiento.md](./docs/00_cumplimiento.md).

## Solución de problemas

- **Error de conexión:** comprueba `DATABASE_URL`, credenciales Neon y
  `sslmode=require`.
- **Tablas inexistentes:** ejecuta `FLASK_APP=app flask db upgrade` en el
  entorno correcto.
- **Rate limit inesperado:** limpia el almacenamiento local o configura Redis
  compartido.
- **PDF sin datos:** confirma que el usuario sea miembro del proyecto y que
  existan tareas/KPI.
