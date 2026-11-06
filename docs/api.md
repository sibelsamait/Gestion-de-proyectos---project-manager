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
| POST | `/settings/currency` | formulario/JSON `currency=CLP|UF|USD` | preferencia de moneda |
| GET | `/internal/refresh-rates` | `Authorization: CRON_SECRET` | conteo de tasas actualizadas |
| GET | `/projects/<id>/export_pdf` | `currency=CLP|UF|USD` opcional | informe PDF en la moneda solicitada |

Los endpoints de Gantt y tableros aceptan `?currency=CLP|UF|USD` y devuelven
`currency`, `rate_used`, `rate_date`, `rate_date_display` e `is_stale`. La
conversión ocurre en el backend y los costos persistidos continúan en CLP.

Ejemplo:

```json
GET /api/projects/abc/tracking?currency=USD
{
  "currency": "USD",
  "rate_used": "950.123456",
  "rate_date": "2026-11-05",
  "rate_date_display": "05-11-2026",
  "is_stale": false,
  "costs_by_category": {"Profesional": "105.25"},
  "task_counts": {"total": 1, "evaluated": 1, "overdue": 0}
}
```

La API nunca devuelve tareas de otro proyecto: el decorador de acceso verifica
el proyecto solicitado y la membresía del usuario.
