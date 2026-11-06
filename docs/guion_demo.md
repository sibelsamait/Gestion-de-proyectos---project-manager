# Guion de demostración

1. Ejecutar `flask db upgrade` y `flask seed-demo`. Usar las credenciales
   aleatorias impresas en consola.
2. Abrir el proyecto `DEMO-2026` y el tablero de seguimiento.
3. **Cambiar una duración:** editar una tarea y observar la fecha sucesora en
   Gantt y el avance agregado.
4. **Modificar recursos:** cambiar una asignación o recurso; revisar costos,
   utilización y alerta de sobreasignación.
5. **Aprobar una solicitud:** llevar `CH-03` a la etapa Decisión y aprobarla
   como admin/manager. Ver el presupuesto, la línea base, la trazabilidad y el
   recálculo del scheduler.
6. Volver a los tableros y verificar Gantt, costos, KPI y alertas.
7. **Conversión multidivisa:** usar el selector global para cambiar de CLP a
   UF y luego a USD. Verificar que las tablas de costos, los tableros, los
   tooltips/gráficos y el PDF descargado mantienen los mismos montos base,
   convertidos con la tasa mostrada y su fecha.
8. Mostrar la franja `Fuente: mindicador.cl / Banco Central de Chile` y, si
   corresponde, el aviso de tasa desactualizada.
