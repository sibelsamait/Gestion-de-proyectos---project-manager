"""Preinversión, autorización, alcance, riesgos, control de costos (valor ganado) e informe."""

from datetime import date
from decimal import Decimal

from support import create_user
from test_registration_and_roles import _project_with, create_project, register

from app.extensions import db
from app.models import (
    CashFlow,
    PreinvestmentStudy,
    Project,
    ProjectMember,
    Resource,
    Risk,
    ScopeItem,
    Task,
    TaskResourceAssignment,
)
from app.services.planning import earned_value, irr, npv, payback

# ------------------------------------------------------------------ cálculos


def test_npv_irr_and_payback_match_manual_calculation():
    flows = [Decimal(-120000), Decimal(55000), Decimal(67000), Decimal(70000), Decimal(73000)]
    # VAN al 12 %: -120000 + 55000/1,12 + 67000/1,12² + 70000/1,12³ + 73000/1,12⁴ = 78.737
    assert round(npv(Decimal("0.12"), flows)) == 78737
    rate = irr(flows)
    assert abs(npv(rate, flows)) < 1
    assert Decimal("0.38") < rate < Decimal("0.40")
    # Recuperación simple: año 1 acumula -65000; en el año 2 se recupera 65000/67000 = 0,97
    assert round(payback(flows), 2) == Decimal("1.97")
    assert irr([Decimal(10), Decimal(20)]) is None
    assert payback([Decimal(-100), Decimal(10)]) is None


def test_earned_value_indices():
    task = Task(id="t1", planned_start=date(2026, 1, 1), planned_end=date(2026, 1, 10), progress_percent=Decimal(40))
    evm = earned_value([task], {"t1": Decimal(1000)}, {"t1": Decimal(500)}, today=date(2026, 1, 5))
    assert (evm.bac, evm.pv, evm.ev, evm.ac) == (Decimal(1000), Decimal(500), Decimal(400), Decimal(500))
    assert evm.cpi == Decimal("0.8")
    assert evm.spi == Decimal("0.8")
    assert evm.eac == Decimal(1250)


def test_risk_score_and_level():
    assert [Risk(probability=p, impact=i).level for p, i in ((2, 2), (3, 3), (3, 4), (4, 4))] == [
        "bajo", "medio", "alto", "critico",
    ]


# ------------------------------------------------- preinversión y autorización


def test_project_starts_in_preinvestment_and_cannot_execute_without_authorization(anon_client, app):
    register(anon_client, "gerente@b.cl")
    with app.app_context():
        project_id = create_project(anon_client)
        assert db.session.get(Project, project_id).phase == "preinversion"
    blocked = anon_client.post(f"/projects/{project_id}/edit", data={"name": "X", "status": "en_ejecucion"},
                               follow_redirects=True)
    assert "sigue en preinversión".encode() in blocked.data
    gate = anon_client.post(f"/projects/{project_id}/phase", data={"phase": "inversion"}, follow_redirects=True)
    assert "No es posible pasar a la etapa de inversión".encode() in gate.data
    with app.app_context():
        director = db.session.get(Project, project_id).director_id
    anon_client.post(f"/projects/{project_id}/edit", data={"name": "X", "status": "planificado",
                                                           "authorized_budget": "5000", "director_id": director})
    anon_client.post(f"/projects/{project_id}/authorization", data={
        "authorized_by": "Directorio", "authorization_date": "2026-01-10",
        "authorization_reference": "Acta 12", "director_id": director,
    })
    ok = anon_client.post(f"/projects/{project_id}/phase", data={"phase": "inversion"}, follow_redirects=True)
    assert "pasó a la etapa de inversión".encode() in ok.data
    started = anon_client.post(f"/projects/{project_id}/edit", data={
        "name": "X", "status": "en_ejecucion", "authorized_budget": "5000", "director_id": director,
    })
    assert started.status_code == 302
    with app.app_context():
        project = db.session.get(Project, project_id)
        assert (project.phase, project.status, project.authorization_reference) == ("inversion", "en_ejecucion", "Acta 12")


def test_director_must_be_a_registered_member(anon_client, app):
    register(anon_client, "gerente@b.cl")
    with app.app_context():
        project_id = create_project(anon_client)
    outsider = create_user(app, "externo@b.cl")
    response = anon_client.post(f"/projects/{project_id}/authorization", data={"director_id": outsider},
                                follow_redirects=True)
    assert b"debe ser un usuario registrado del proyecto" in response.data


def test_studies_and_evaluation(anon_client, app):
    register(anon_client, "gerente@b.cl")
    with app.app_context():
        project_id = create_project(anon_client)
    missing = anon_client.post(f"/projects/{project_id}/studies/mercado", data={"status": "completado"},
                               follow_redirects=True)
    assert "debe registrar su conclusión".encode() in missing.data
    anon_client.post(f"/projects/{project_id}/studies/mercado",
                     data={"status": "completado", "conclusion": "Demanda validada."})
    assert anon_client.post(f"/projects/{project_id}/studies/inventado", data={}).status_code == 404
    form = {"discount_rate": "12", "evaluation_years": "2"}
    for period, (inv, inc, cost) in enumerate([(100, 0, 0), (0, 80, 10), (0, 90, 10)]):
        form.update({f"investment_{period}": inv, f"income_{period}": inc, f"costs_{period}": cost})
    anon_client.post(f"/projects/{project_id}/evaluation", data=form)
    bad = anon_client.post(f"/projects/{project_id}/evaluation", data={**form, "evaluation_years": "40"},
                           follow_redirects=True)
    assert b"entre 1 y 20" in bad.data
    negative = anon_client.post(f"/projects/{project_id}/evaluation", data={**form, "income_1": "-5"},
                                follow_redirects=True)
    assert b"no puede ser negativo" in negative.data
    page = anon_client.get(f"/projects/{project_id}?vista=preinversion").data.decode()
    assert "El proyecto es rentable" in page
    with app.app_context():
        assert PreinvestmentStudy.query.filter_by(project_id=project_id, status="completado").count() == 1
        assert CashFlow.query.filter_by(project_id=project_id).count() == 3


# ---------------------------------------------------------- alcance y riesgos


def test_scope_template_is_idempotent_and_items_editable(anon_client, app):
    register(anon_client, "gerente@b.cl")
    with app.app_context():
        project_id = create_project(anon_client)
    anon_client.post(f"/projects/{project_id}/scope/template", data={"template": "aplicacion_movil"})
    anon_client.post(f"/projects/{project_id}/scope/template", data={"template": "aplicacion_movil"})
    with app.app_context():
        total = ScopeItem.query.filter_by(project_id=project_id).count()
        assert total == 11
        item_id = ScopeItem.query.filter_by(project_id=project_id, category="exclusion").first().id
    anon_client.post(f"/projects/{project_id}/scope/{item_id}/edit",
                     data={"category": "exclusion", "description": "Sin versión web."})
    invalid = anon_client.post(f"/projects/{project_id}/scope/new", data={"category": "Exclusion", "description": "X"},
                               follow_redirects=True)
    assert b"La categor" in invalid.data
    page = anon_client.get(f"/projects/{project_id}?vista=alcance").data.decode()
    assert "Sin versión web." in page and "Excluido del alcance" in page


def test_high_risk_requires_response_plan(anon_client, app):
    register(anon_client, "gerente@b.cl")
    with app.app_context():
        project_id = create_project(anon_client)
    data = {"description": "Proveedor no entrega", "probability": "4", "impact": "4", "response": "mitigar"}
    rejected = anon_client.post(f"/projects/{project_id}/risks/new", data=data, follow_redirects=True)
    assert b"requiere un plan de respuesta" in rejected.data
    out_of_scale = anon_client.post(f"/projects/{project_id}/risks/new", data={**data, "impact": "7"},
                                    follow_redirects=True)
    assert b"debe estar entre 1 y 5" in out_of_scale.data
    anon_client.post(f"/projects/{project_id}/risks/new", data={**data, "response_plan": "Proveedor alternativo."})
    with app.app_context():
        risk = Risk.query.filter_by(project_id=project_id).one()
        assert (risk.score, risk.level) == (16, "critico")


# ----------------------------------------------- control de costos y permisos


def test_assignments_feed_earned_value(anon_client, app):
    register(anon_client, "gerente@b.cl")
    with app.app_context():
        project_id = create_project(anon_client)
        resource = Resource(project_id=project_id, type="Material", name="Servidor", quantity=Decimal(1),
                            unit_cost=Decimal(1000))
        task = Task(project_id=project_id, name="Instalar", planned_start=date(2026, 1, 1),
                    planned_end=date(2026, 1, 2), progress_percent=Decimal(50))
        db.session.add_all([resource, task])
        db.session.commit()
        resource_id, task_id = resource.id, task.id
    anon_client.post(f"/projects/{project_id}/tasks/{task_id}/assignments",
                     data={"resource_id": resource_id, "planned_units": "1", "actual_units": "0.8"})
    with app.app_context():
        assignment = db.session.get(TaskResourceAssignment, (task_id, resource_id))
        assert (assignment.planned_units, assignment.actual_units) == (Decimal(1), Decimal("0.8"))
    page = anon_client.get(f"/projects/{project_id}").data.decode()
    assert "Valor ganado (EV)" in page and "$500" in page and "$800" in page
    anon_client.post(f"/projects/{project_id}/tasks/{task_id}/assignments/{resource_id}/delete")
    with app.app_context():
        assert TaskResourceAssignment.query.count() == 0


def test_project_lead_permissions(app):
    _, lead, project_id = _project_with(app, "gestor")
    assert lead.post(f"/projects/{project_id}/risks/new", data={
        "description": "Riesgo", "probability": "1", "impact": "1", "response": "aceptar"}).status_code == 302
    for path, data in (
        ("/scope/new", {"category": "exclusion", "description": "X"}),
        ("/evaluation", {"discount_rate": "10"}),
        ("/authorization", {}),
        ("/phase", {"phase": "inversion"}),
        ("/studies/legal", {"status": "en_curso"}),
        ("/resource/new", {"name": "R", "type": "Otros"}),
    ):
        assert lead.post(f"/projects/{project_id}{path}", data=data).status_code == 403, path


def test_member_cannot_manage_risks_or_assignments(app):
    _, member, project_id = _project_with(app, "miembro")
    assert member.get(f"/projects/{project_id}?vista=riesgos").status_code == 200
    assert member.post(f"/projects/{project_id}/risks/new", data={}).status_code == 403
    assert member.post(f"/projects/{project_id}/tasks/x/assignments", data={}).status_code == 403
    page = member.get(f"/projects/{project_id}?vista=preinversion").data.decode()
    assert "Guardar estudio" not in page and "Guardar evaluación" not in page


def test_role_labels_follow_manager_and_lead_definition(app):
    admin, _, project_id = _project_with(app, "gestor")
    page = admin.get(f"/projects/{project_id}?vista=usuarios").data.decode()
    assert "Gerente de proyecto" in page and "Jefe de proyecto" in page
    with app.app_context():
        assert ProjectMember.query.filter_by(project_id=project_id, role="gestor").count() == 1


# --------------------------------------------------------------------- informe


def test_report_has_all_chapters(client, app):
    from test_phase6_pdf import authenticated_project

    project_id = authenticated_project(client, app)
    preview = client.get(f"/projects/{project_id}/informe").data.decode()
    for title in ("Organización y autorización", "Estudios de preinversión y evaluación económica",
                  "Alcance del proyecto", "Control de costos y plazo", "Gestión de riesgos"):
        assert title in preview
    pdf = client.get(f"/projects/{project_id}/export_pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
