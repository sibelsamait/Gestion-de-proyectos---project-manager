# Entrega final y rúbrica

| Indicador | Peso | Antes | Después | Pendiente |
|---|---:|---:|---:|---|
| Requerimientos y modelo de datos | 5% | 80% | 100% | Ninguno crítico |
| Administración de proyectos | 5% | 80% | 100% | Administración visual avanzada de miembros |
| Tiempos, recursos y costos | 10% | 60% | 90% | Formularios especializados por subtipo |
| Carta Gantt y dependencias | 10% | 60% | 90% | Edición visual avanzada de relaciones |
| Hitos | Incluido | 60% | 90% | Asociación visual completa desde interfaz |
| KPI configurables | 10% | 60% | 90% | Editor visual completo y KPI manuales agregados |
| Gestión del cambio | 5% | 60% | 90% | Pantalla completa de historial y línea base |
| Tableros | 5% | 60% | 85% | Gráficos Chart.js más completos |
| Integración, pruebas y demo | 50% | 60% | 85% | Pruebas browser end-to-end externas |
| Experiencia y coherencia | Transversal | 60% | 85% | Mejoras visuales y textos finales |

## Alcance no incluido

- No existe EDT/WBS ni jerarquía de actividades.
- No se implementa inicio de sesión corporativo.
- Los costos se persisten en CLP; UF y USD son monedas de presentación.
- Las páginas legales son borradores académicos y no constituyen asesoría legal.

## Verificación final

```bash
python -m pytest -q
ruff check app api migrations scripts tests
bandit -r app api scripts -ll
pip-audit -r requirements.txt
```
