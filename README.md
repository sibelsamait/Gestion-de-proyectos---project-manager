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

`flask seed-demo` crea el proyecto `DEMO-2026` con tareas, hitos, recursos, KPI
y solicitudes de cambio, e imprime el correo y la contraseña de los dos usuarios
demo. Cualquier persona puede crear su cuenta en `/auth/register` (correo,
nombre, empresa y contraseña repetida).

Para usar SQLite local basta con omitir `DATABASE_URL`; no se debe usar SQLite
en Vercel porque el disco serverless es efímero.

## Variables de entorno

- `SECRET_KEY`: secreto aleatorio obligatorio en producción.
- `DATABASE_URL`: PostgreSQL Neon; se normaliza `postgres://` y se añade
  `sslmode=require`.
- `FLASK_ENV=production`: usa `NullPool` para conexiones serverless.
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

## Ciclo de gestión del proyecto

| Necesidad | Dónde se resuelve |
|---|---|
| Etapa de preinversión antes de la inversión | Cada proyecto nace en **Preinversión**; solo pasa a **Inversión** (y puede quedar "En ejecución") cuando el documento de autorización está completo |
| Estudios previos para inversionistas y bancos | Pestaña *Preinversión*: estudios de mercado, técnico, organizacional, legal y financiero, con estado y conclusión |
| Justificar la rentabilidad | Evaluación económica: flujo de caja por año, VAN, TIR, período de recuperación (simple y descontado) y relación beneficio/costo |
| Documento formal que autoriza el proyecto y designa al Director(a) | Pestaña *Preinversión* → Documento de autorización (quién autoriza, fecha, n.º de documento, Director(a)) |
| Gerente vs. Jefe de proyecto | Roles por proyecto con permisos distintos (ver tabla de roles) |
| Identificar factores de fracaso antes de comenzar | Pestaña *Riesgos*: probabilidad × impacto, matriz 5×5, estrategia y plan de respuesta (obligatorio para riesgos altos) |
| Alcance incluido/excluido con plantillas | Pestaña *Alcance*: requisitos, entregables, exclusiones, supuestos y restricciones; plantillas para software a medida, app móvil e integración |
| Controlar los gastos durante la ejecución | Asignación de recursos a tareas (unidades planificadas y reales) y valor ganado: PV, EV, AC, CPI, SPI, EAC |
| Estrategia de monitoreo y control | Campo del proyecto que se muestra en el resumen y en el informe |
| Informe completo | PDF de 10 capítulos con la misma información; la vista previa indica qué falta en cada capítulo |

Por indicación de la cátedra, la app **no** incluye EDT/WBS: las tareas son una lista plana y el campo
`etapa` solo las agrupa visualmente.

## Alcance de seguridad (demo)

Es una aplicación de demostración con seguridad mínima:

- **Inicio de sesión:** solo pueden entrar usuarios registrados. El acceso se
  concede si el texto ingresado es exactamente igual a la columna `password`
  (texto plano, sin hash).
- **Roles por proyecto** (tabla `project_members`, por correo): quien crea un
  proyecto queda como **administrador** y, en la pestaña *Usuarios*, agrega
  correos con un rol. Un correo agregado ve el proyecto en su panel apenas inicia
  sesión o se registra. Quien no está en la lista recibe 403.

  | Rol | Puede |
  |---|---|
  | Gerente de proyecto (`admin`) | Monitorea el proyecto en su conjunto: preinversión, autorización, alcance, presupuesto y recursos, aprobación de cambios y lista de usuarios |
  | Jefe de proyecto (`gestor`) | Trabaja con el equipo técnico en la ejecución: tareas, hitos, dependencias, asignación de recursos, riesgos y mediciones de KPI |
  | Miembro | Solo lectura y exportar el PDF para guardarlo o imprimirlo (p. ej., el cliente del proyecto); rol por defecto al agregar usuarios |

  Un proyecto siempre conserva al menos un administrador.
- **Validación de datos** (`app/validation.py`): tipos, largos máximos según
  cada columna, números no negativos, orden de fechas y opciones que deben
  coincidir exactamente con los valores `Enum` del esquema (por ejemplo
  `en_ejecucion` o `cumplido`).
- **Auditoría** (tabla `audit_log`, no visible en la interfaz): cada cambio guarda
  el correo del usuario, el rol con que actuó en ese proyecto (`admin`, `gestor`
  o `miembro`), el código del cambio (`task.created`,
  `change.approved`, etc.), una descripción y la fecha/hora. Permite medir qué
  usuarios trabajaron en la administración y gestión de cada proyecto, por
  ejemplo: `SELECT user_email, role, count(*) FROM audit_log GROUP BY 1, 2;`.

Como las contraseñas se guardan legibles, usa contraseñas exclusivas de esta demo
y no publiques datos reales.

Consulta [docs/api.md](./docs/api.md), [docs/guion_demo.md](./docs/guion_demo.md)
y [docs/licencias.md](./docs/licencias.md). La solución y sus decisiones de
cumplimiento están descritas en [docs/00_cumplimiento.md](./docs/00_cumplimiento.md).

## Solución de problemas

- **Error de conexión:** comprueba `DATABASE_URL`, credenciales Neon y
  `sslmode=require`.
- **Tablas inexistentes:** ejecuta `FLASK_APP=app flask db upgrade` en el
  entorno correcto.
- **PDF sin datos:** revisa la vista previa del informe (`/projects/<id>/informe`),
  que indica qué secciones tienen datos incompletos.
