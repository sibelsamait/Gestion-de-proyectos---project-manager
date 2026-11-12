# Requerimientos y modelo de datos

## Reglas transversales

1. Toda entidad de proyecto se autoriza por membresía y `project_id`; `admin`
   puede operar globalmente.
2. Todas las fechas se almacenan con zona horaria definida o como fecha civil
   explícita; las fechas de término no pueden preceder a las de inicio.
3. Dinero usa `NUMERIC`/`Decimal` y nunca `float`; porcentajes están entre 0 y
   100. Estados y tipos usan valores controlados.
4. Tareas son planas. `etapa` no es una relación ni una jerarquía.
5. Cambios y tareas tienen `version` para bloqueo optimista. Las operaciones
   compuestas usan una transacción única.
6. Dependencias se rechazan si crean ciclos; la eliminación o modificación
   inválida no deja cambios parciales.
7. Evidencias de hitos y cambios son texto o URL; no se suben archivos al
   disco de la aplicación.

## Requerimientos por módulo

### Autenticación, portafolio y privacidad

- Registro, login, logout, expiración de sesión, rate limit y bloqueo temporal.
- Roles `admin` y `usuario_proyecto`; membresía usuario-proyecto.
- Dashboard de proyectos propios y `project_id` activo en sesión.
- Consentimiento obligatorio y fecha de aceptación.
- Exportación JSON y eliminación/anonimización de datos del titular.

### Proyectos

- Código único, nombre, descripción, objetivos, director, patrocinador,
  presupuesto autorizado y fechas planificadas/reales.
- Estados: `planificado`, `en_ejecucion`, `suspendido`, `terminado`.
- Avance calculado automáticamente y cierre auditado.

### Tareas y calendario

- Lista plana con nombre, descripción, responsable, `etapa`, fechas,
  duración hábil planificada/real y avance.
- Dependencias múltiples FS/SS/FF/SF con `lag` positivo o negativo.
- Feriados y días no laborables configurables por proyecto; precarga de
  feriados de Chile.
- Recalculo topológico de sucesoras al cambiar fecha o duración.

### Recursos, costos e hitos

- Recursos Profesional, Licencia, Material, Equipamiento y Otros.
- Asignaciones a tareas, costo planificado/real y alerta de sobreasignación
  semanal profesional.
- Hitos asociados a una o más tareas, responsables, fechas, estado, criterios,
  evidencia y KPI; duración cero en Gantt.

### KPI

- Definición configurable: código, nombre, objetivo, ámbito, variables,
  fórmula, unidad, meta, sentido, umbrales, periodicidad, fuente, responsable,
  resultado y estado.
- Evaluación mediante `simpleeval`, lista blanca de variables/funciones, sin
  `eval`/`exec`.
- Histórico en `kpi_measurements` y alertas al cruzar umbrales.
- Variables backend: trabajo completado/total, hitos en plazo/vencidos, costos,
  tareas atrasadas/evaluadas, horas asignadas/disponibles, entre otras.

### Gestión del cambio

- Solicitud con impacto en alcance, plazo, costo y recursos; riesgo, prioridad,
  responsable, evidencias y costos estimado/real.
- Flujo configurable de diez etapas: Registro, Clasificación, Evaluación de
  impacto, Análisis de riesgo, Decisión, Planificación de implementación,
  Implementación, Verificación, Cierre con resultado y Seguimiento de
  adopción.
- Solo el rol autorizado aprueba.
- Línea base de fechas/costos y `change_applications` con entidad, atributo,
  valor anterior y nuevo; la aprobación aplica el impacto y dispara scheduler,
  costos y KPI en una transacción.

### Presentación, API y despliegue

- Gantt JSON con plan/real, avance, relaciones, hitos, atrasos y escalas
  día/semana/mes.
- Tableros de seguimiento y cambios con filtros, alertas y alternativas
  tabulares para gráficos.
- PDF ReportLab con Gantt dibujado con primitivas.
- API documentada en `docs/api.md`; plantillas y JS separados del negocio.
- Vercel expone `app` desde `api/index.py`; PostgreSQL Neon persistente,
  migraciones solo en el workflow de despliegue.

## Modelo entidad-relación

El diagrama omite columnas de auditoría repetitivas (`created_at`,
`updated_at`) cuando no cambian la relación. Todas las tablas tienen una clave
primaria; las claves foráneas deben usar `ON DELETE` explícito y las
restricciones indicadas.

```mermaid
erDiagram
    USERS ||--o{ PROJECT_MEMBERSHIPS : belongs
    PROJECTS ||--o{ PROJECT_MEMBERSHIPS : has
    USERS ||--o{ PROJECTS : directs
    PROJECTS ||--o{ TASKS : contains
    USERS ||--o{ TASKS : responsible
    TASKS ||--o{ TASK_DEPENDENCIES : successor
    TASKS ||--o{ TASK_DEPENDENCIES : predecessor
    PROJECTS ||--o{ NON_WORKING_DAYS : configures
    TASKS ||--o{ TASK_RESOURCE_ASSIGNMENTS : uses
    RESOURCES ||--o{ TASK_RESOURCE_ASSIGNMENTS : assigned
    PROJECTS ||--o{ RESOURCES : owns
    PROJECTS ||--o{ MILESTONES : contains
    MILESTONES ||--o{ MILESTONE_TASKS : links
    TASKS ||--o{ MILESTONE_TASKS : supports
    PROJECTS ||--o{ KPI_DEFINITIONS : defines
    KPI_DEFINITIONS ||--o{ KPI_MEASUREMENTS : records
    KPI_DEFINITIONS ||--o{ KPI_TASKS : targets
    TASKS ||--o{ KPI_TASKS : measured
    KPI_DEFINITIONS ||--o{ KPI_MILESTONES : targets
    MILESTONES ||--o{ KPI_MILESTONES : measured
    KPI_DEFINITIONS ||--o{ KPI_CHANGES : targets
    CHANGE_REQUESTS ||--o{ KPI_CHANGES : measured
    PROJECTS ||--o{ CHANGE_REQUESTS : receives
    USERS ||--o{ CHANGE_REQUESTS : requests
    CHANGE_REQUESTS ||--o{ CHANGE_BASELINES : snapshots
    CHANGE_REQUESTS ||--o{ CHANGE_APPLICATIONS : applies
    AUDIT_LOG }o--|| USERS : actor

    USERS {
        uuid id PK
        string name
        string email UK
        string password_hash
        enum role
        datetime terms_accepted_at
        boolean is_active
    }
    PROJECTS {
        uuid id PK
        string code UK
        string name
        text description
        text objectives
        uuid director_id FK
        string sponsor
        numeric authorized_budget
        date planned_start
        date planned_end
        date actual_start
        date actual_end
        enum status
    }
    PROJECT_MEMBERSHIPS {
        uuid project_id PK,FK
        uuid user_id PK,FK
        enum membership_role
    }
    TASKS {
        uuid id PK
        uuid project_id FK
        uuid responsible_id FK
        string name
        text description
        string etapa
        date planned_start
        date planned_end
        date actual_start
        date actual_end
        integer planned_duration_days
        integer actual_duration_days
        numeric progress_percent
        integer version
    }
    TASK_DEPENDENCIES {
        uuid predecessor_id PK,FK
        uuid successor_id PK,FK
        enum dependency_type
        integer lag_days
    }
    NON_WORKING_DAYS {
        uuid id PK
        uuid project_id FK
        date day
        string reason
        boolean is_working_override
    }
    RESOURCES {
        uuid id PK
        uuid project_id FK
        enum type
        string name
        string specialty
        numeric hourly_rate
        numeric hours_per_week
        numeric weeks  # Dato histórico de capacidad; el costo usa la duración hábil de cada actividad.
        numeric quantity
        numeric unit_cost
    }
    TASK_RESOURCE_ASSIGNMENTS {
        uuid task_id PK,FK
        uuid resource_id PK,FK
        numeric planned_units
        numeric actual_units
    }
    MILESTONES {
        uuid id PK
        uuid project_id FK
        string name
        text description
        uuid responsible_id FK
        date committed_date
        date actual_date
        enum status
        text acceptance_criteria
        text evidence
    }
    MILESTONE_TASKS {
        uuid milestone_id PK,FK
        uuid task_id PK,FK
    }
    KPI_DEFINITIONS {
        uuid id PK
        uuid project_id FK
        string code
        string name
        enum scope
        json variables
        text formula
        string unit
        numeric target
        enum direction
        json thresholds
        enum periodicity
        enum source
    }
    KPI_MEASUREMENTS {
        uuid id PK
        uuid kpi_id FK
        datetime measured_at
        numeric result
        enum status
        json inputs
    }
    KPI_TASKS {
        uuid kpi_id PK,FK
        uuid task_id PK,FK
    }
    KPI_MILESTONES {
        uuid kpi_id PK,FK
        uuid milestone_id PK,FK
    }
    KPI_CHANGES {
        uuid kpi_id PK,FK
        uuid change_request_id PK,FK
    }
    CHANGE_REQUESTS {
        uuid id PK
        uuid project_id FK
        string change_code
        uuid requester_id FK
        date requested_at
        text description
        text justification
        enum change_type
        enum priority
        enum risk
        json impact
        uuid responsible_id FK
        enum stage
        enum status
        date committed_date
        date actual_date
        numeric estimated_cost
        numeric actual_cost
        text result
        text evidence
        integer version
    }
    CHANGE_BASELINES {
        uuid id PK
        uuid change_request_id FK
        datetime captured_at
        json snapshot
    }
    CHANGE_APPLICATIONS {
        uuid id PK
        uuid change_request_id FK
        string entity_type
        uuid entity_id
        string attribute
        text old_value
        text new_value
        datetime applied_at
    }
    AUDIT_LOG {
        uuid id PK
        uuid actor_id FK
        string action
        string entity_type
        uuid entity_id
        datetime occurred_at
        json metadata
    }
```

## Restricciones e índices esenciales

- `users.email` y `projects.code` son únicos; email se normaliza antes de
  comparar.
- `project_memberships` es único por `(project_id, user_id)`.
- `task_dependencies` es único por `(predecessor_id, successor_id)` y prohíbe
  auto-dependencias; el ciclo completo se valida en servicio antes de guardar.
- Fechas de tareas, proyectos, hitos y cambios se validan en aplicación y BD
  cuando el motor lo permita; duraciones, cantidades, horas y dinero son
  mayores o iguales a cero.
- `progress_percent` está entre 0 y 100; `version` es entero no negativo.
- `kpi_definitions.code` es único por proyecto y cada medición conserva sus
  entradas para reproducibilidad.
- Índices en todas las FK, `tasks(project_id, planned_start)`,
  `change_requests(project_id, stage, status)` y
  `audit_log(entity_type, entity_id, occurred_at)`.
