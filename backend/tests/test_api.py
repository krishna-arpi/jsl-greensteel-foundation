"""
Smoke tests for the foundation API. Run from the project root:
    cd backend && python -m pytest tests/ -v
"""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["data_status"] == "DEMO_PLACEHOLDER"


def test_reference_data_bundle_loads():
    r = client.get("/reference-data")
    assert r.status_code == 200
    body = r.json()
    for key in ("emission_factors", "steel_grades", "scrap_quality", "energy_sources", "baseline", "alloy_specifications"):
        assert key in body["data"]
    # No validation issues expected against well-formed demo data.
    assert body["validation_issues"] == []


def test_individual_reference_endpoints():
    for path, top_key in [
        ("/reference-data/steel-grades", "grades"),
        ("/reference-data/scrap-quality", "categories"),
        ("/reference-data/energy-sources", "sources"),
        ("/reference-data/emission-factors", "factors"),
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert top_key in r.json(), path


def test_baseline_endpoint_has_corporate_benchmark_not_product_factor():
    r = client.get("/reference-data/baseline")
    assert r.status_code == 200
    body = r.json()
    bench = body["corporate_benchmark"]
    assert bench["label"] == "JSL FY26 corporate carbon-intensity benchmark"
    assert bench["scope_1_plus_2"]["value"] == 1.76
    assert bench["scope_3"]["value"] == 1.27
    assert bench["derived_reference_total"]["value"] == 3.03
    # Must not be presented as a universal product/grade emission factor.
    assert body["_meta"]["do_not_use_as"] == "A universal stainless-steel product emission factor"
    # Demo scenario used to pre-fill the calculator lives alongside it, separately.
    assert "demo_scenario" in body
    assert body["demo_scenario"]["_status"] == "DEMO_PLACEHOLDER"


def test_emission_factors_have_full_disclosure_schema():
    r = client.get("/reference-data/emission-factors")
    factors = r.json()["factors"]
    assert len(factors) > 0
    required_fields = {
        "name", "value", "unit", "year", "geography", "boundary", "scope", "source", "confidence", "notes",
    }
    for factor in factors:
        assert required_fields.issubset(factor.keys()), factor["id"]


def test_calculate_carbon_baseline():
    r = client.get("/reference-data/baseline")
    baseline_inputs = r.json()["demo_scenario"]["inputs"]
    payload = {
        "scrap_pct": baseline_inputs["scrap_pct"],
        "virgin_material_pct": baseline_inputs["virgin_material_pct"],
        "grade_id": baseline_inputs["grade_id"],
        "scrap_quality_id": baseline_inputs["scrap_quality_id"],
        "electricity_source_id": baseline_inputs["electricity_source_id"],
        "electricity_consumption_mwh_per_t": baseline_inputs["electricity_consumption_mwh_per_t"],
        "fuel_source_id": baseline_inputs["fuel_source_id"],
        "fuel_consumption_gj_per_t": baseline_inputs["fuel_consumption_gj_per_t"],
        "process_route_id": baseline_inputs["process_route_id"],
        "alloy_additions": {"values_kg_per_t": baseline_inputs["alloy_additions_kg_per_t"]},
    }
    r2 = client.post("/calculate/carbon", json=payload)
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "DEMO_PLACEHOLDER"
    assert body["total_tco2e_per_t"] > 0
    assert len(body["breakdown"]) == 5


def test_calculate_carbon_rejects_bad_mix():
    payload = {
        "scrap_pct": 60,
        "virgin_material_pct": 60,  # sums to 120 -> invalid
        "grade_id": "SS304",
        "scrap_quality_id": "SCRAP_HIGH_QUALITY",
        "electricity_source_id": "GRID_ELECTRICITY_IN",
        "electricity_consumption_mwh_per_t": 0.5,
        "fuel_source_id": "NATURAL_GAS",
        "fuel_consumption_gj_per_t": 0.8,
        "process_route_id": "EAF_HIGH_SCRAP",
        "alloy_additions": {"values_kg_per_t": {}},
    }
    r = client.post("/calculate/carbon", json=payload)
    assert r.status_code == 422


def test_optimize_endpoint_exists_and_rejects_empty_body():
    """/optimize is now a fully implemented LP/MILP engine (see
    test_optimizer.py for its behavior); an empty body is missing required
    fields and should 422, not 501."""
    r = client.post("/optimize", json={})
    assert r.status_code == 422


def test_unknown_grade_rejected():
    payload = {
        "scrap_pct": 60,
        "virgin_material_pct": 40,
        "grade_id": "NOT_A_REAL_GRADE",
        "scrap_quality_id": "SCRAP_HIGH_QUALITY",
        "electricity_source_id": "GRID_ELECTRICITY_IN",
        "electricity_consumption_mwh_per_t": 0.5,
        "fuel_source_id": "NATURAL_GAS",
        "fuel_consumption_gj_per_t": 0.8,
        "process_route_id": "EAF_HIGH_SCRAP",
        "alloy_additions": {"values_kg_per_t": {}},
    }
    r = client.post("/calculate/carbon", json=payload)
    assert r.status_code == 422


def test_steel_grades_have_required_fields():
    r = client.get("/reference-data/steel-grades")
    grades = r.json()["grades"]
    names = {g["grade_name"] for g in grades}
    assert {"304", "316", "430", "410", "Duplex 2205"}.issubset(names)
    required = {"grade_name", "Cr_min", "Cr_max", "Ni_min", "Ni_max", "Mo_min", "Mo_max", "C_max", "Si_max", "Mn_max", "N_max"}
    for g in grades:
        assert required.issubset(g.keys())


def test_scrap_quality_categories():
    r = client.get("/reference-data/scrap-quality")
    cats = r.json()["categories"]
    names = {c["category_name"] for c in cats}
    assert names == {"High Quality", "Medium Quality", "Low Quality"}
    required = {"Cr", "Ni", "Mo", "Fe", "C", "Si", "Mn", "N", "yield", "alloy_recovery"}
    for c in cats:
        assert required.issubset(c.keys())
