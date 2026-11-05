# API JSON

Todas las rutas de proyecto requieren sesión y membresía, salvo las rutas de
autenticación. Las respuestas de error usan `{ "error": "mensaje" }`.

| Método | Ruta | Parámetros | Respuesta |
|---|---|---|---|
| GET | `/api/projects/<id>/gantt` | `id` de proyecto | `tasks`, `dependencies`, `milestones` |
| GET | `/api/projects/<id>/tracking` | `id` de proyecto | avance, costos, tareas atrasadas, utilización |
| GET | `/api/projects/<id>/changes-dashboard` | `id` de proyecto | estados, riesgos, costos y alertas |
| POST | `/api/projects/<id>/kpis/<kpi_id>/measure` | JSON con variables permitidas | resultado, estado e id de medición |
| POST | `/api/projects/<id>/changes/<change_id>/approve` | sin cuerpo | estado y número de aplicaciones |
| GET | `/privacy/export` | sesión actual | JSON de datos propios |

Ejemplo:

```json
GET /api/projects/abc/gantt
{
  "tasks": [{
    "id": "task-id",
    "name": "Diseño",
    "planned_start": "2026-01-05",
    "planned_end": "2026-01-07",
    "progress": "50.00",
    "overdue": false
  }],
  "dependencies": [],
  "milestones": []
}
```

La API nunca devuelve tareas de otro proyecto: el decorador de acceso verifica
el proyecto solicitado y la membresía del usuario.
