# Fase 0 — Cumplimiento y decisiones de diseño

## Alcance y advertencias

La aplicación será una herramienta académica de gestión de proyectos. No está
diseñada para menores ni para tratar datos sensibles, sanitarios, financieros o
laborales. Por ello, COPPA, HIPAA y GLBA no son objetivos funcionales de esta
aplicación; aun así, se aplicarán minimización, seguridad y derechos del titular
conforme al RGPD, CCPA, Ley 19.628 y Ley 21.719 de Chile. Las páginas legales se
marcarán como **borrador y no asesoría legal**.

No se implementará EDT/WBS: `tasks` será una lista plana. `etapa` será solo un
texto opcional para agrupación visual; no habrá jerarquía, consolidación ni
cálculos jerárquicos.

No hay instrucciones contradictorias que impidan una implementación segura.
La única precisión necesaria es operacional: el límite de `Flask-Limiter` en
memoria es una protección local/debilitada en serverless. En producción se
documentará y podrá sustituirse por Redis/Upstash compartido.

## 1. Calidad — ISO/IEC 25010

- **Mantenibilidad:** app factory en `app/__init__.py`, blueprints por módulo,
  servicios aislados en `services/`, SQLAlchemy 2.x tipado y docstrings en
  español.
- **Integridad y concurrencia:** transacciones SQLAlchemy; `version` en tareas y
  cambios para bloqueo optimista; conflictos devuelven error explícito y hacen
  rollback. `NullPool` o pool mínimo en producción serverless.
- **Cálculos consistentes:** scheduler, costos y KPI serán servicios
  reutilizables; sus actualizaciones relacionadas ocurrirán dentro de la misma
  transacción.
- **Verificación:** pytest para reglas de negocio y rutas críticas; ruff,
  bandit y pip-audit en CI. Se probarán especialmente dependencias FS/SS/FF/SF,
  desfases, ciclos, feriados, permisos y validaciones.
- **Portabilidad:** SQLite solo para desarrollo/pruebas; PostgreSQL de Neon en
  producción mediante `DATABASE_URL`, normalizando `postgres://` a
  `postgresql+psycopg2://`. Nunca se ejecutará `create_all()` ni migraciones al
  arrancar una función serverless.

## 2. Seguridad — ISO/IEC 27001 y Secure SDLC

- **Identidad:** contraseñas con `werkzeug.security` usando scrypt o PBKDF2 y
  mínimo de 12 caracteres. Registro con Flask-WTF, CSRF obligatorio y
  validación estricta; las restricciones críticas también estarán en la BD.
- **Consultas y salida:** solo ORM o consultas parametrizadas; nunca SQL
  concatenado. Jinja conservará autoescape; no se usará `|safe` con datos de
  usuario.
- **Sesión y cabeceras:** cookies `Secure`, `HttpOnly`, `SameSite=Lax`, tiempo
  de expiración; Flask-Talisman para CSP, HSTS y cabeceras de seguridad.
- **Abuso:** Flask-Limiter y bloqueo temporal tras intentos fallidos de login.
  El límite en memoria no es suficiente entre instancias serverless; una
  instalación real usará Redis/Upstash.
- **Autorización:** RBAC con `admin` y `usuario_proyecto`. Cada lectura o
  modificación de recursos de proyecto verificará simultáneamente `project_id`
  y membresía. Un decorador reutilizable `@project_access_required` centralizará
  la defensa contra IDOR; administrar usuarios y aprobar cambios quedará
  restringido al privilegio correspondiente.
- **Secretos y transporte:** secretos únicamente en variables de entorno;
  `.env` se excluirá y `.env.example` documentará nombres sin valores reales.
  Vercel servirá HTTPS y PostgreSQL usará `sslmode=require`; el cifrado en
  reposo corresponderá al proveedor de BD.
- **Auditoría y errores:** `audit_log` guardará actor, acción, fecha y entidad,
  nunca contraseñas ni datos innecesarios. Errores 400/403/404/500 tendrán
  páginas propias y no expondrán trazas.

## 3. Privacidad

- **Minimización:** del usuario se conservarán nombre, email, rol y hash de
  contraseña, además de la fecha de aceptación legal necesaria para demostrar
  consentimiento.
- **Consentimiento:** registro bloqueado sin aceptar Términos y Política de
  Privacidad; se guardará `terms_accepted_at`.
- **Derechos:** `/privacy/export` permitirá descargar los datos propios en JSON
  y `/privacy/delete` permitirá supresión real o anonimización de autoría. Se
  elegirá anonimización de auditoría y autoría histórica cuando la integridad
  del proyecto requiera conservar el registro, dejándolo documentado y
  evitando conservar datos identificables innecesarios.
- **Transparencia:** `/privacidad` y `/terminos` serán plantillas editables,
  explícitamente marcadas como borrador y no asesoría legal.

## 4. Accesibilidad y legal

- HTML semántico, `label` asociado, foco visible, contraste AA, teclado y
  `aria-*` en componentes dinámicos.
- Los KPI usarán icono y texto además del color. Cada gráfico tendrá una tabla
  alternativa accesible.
- Solo se aceptarán dependencias con licencias MIT, BSD, Apache, ISC o
  equivalentes permisivas. Se entregarán `LICENSE` y `docs/licencias.md` con
  dependencias y licencias.

## Decisiones de implementación por fase

| Fase | Resultado verificable |
|---|---|
| 1 | Configuración, modelos base, migraciones, autenticación, RBAC y auditoría |
| 2 | CRUD y validaciones de proyectos, tareas, recursos e hitos |
| 3 | Scheduler, costos y pruebas de concurrencia/dependencias |
| 4 | Evaluador seguro de KPI y trazabilidad de cambios |
| 5 | Gantt, tablero de seguimiento y tablero de cambios |
| 6 | PDF, privacidad y accesibilidad |
| 7 | Datos demo, documentación, CI/CD y despliegue |
