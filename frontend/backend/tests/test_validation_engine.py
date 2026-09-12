"""
Automated tests for the comprehensive validation engine.

Covers the service function (backend/validation/validation_engine.py) and
the POST /validate API route. Each of the 12 required checks is tested for
both its PASS and its failing (WARNING/ERROR) path where applicable, plus
the overall_status/blocked aggregation rules:
    - overall_status is ERROR (blocked=True) if any check is ERROR
    - else WARNING if any check is WARNING
    - else PASS

"Do not allow invalid configurations to silently produce results" is tested
via the `blocked` flag: any scenario with an ERROR-status check must report
blocked=True.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import (
    CarbonEmissionInput,
    ElectricityMixComponentInput,
    ScrapChemistryInput,
    ValidationMaterialInput,
    ValidationRequest,
)
from backend.validation.validation_engine import run_validation

client = TestClient(app)


def _checks_by_id(report):
    return {c.check_id: c for c in report.checks}


# --- Domain omission: no fabricated 4th status ------------------------------


def test_empty_request_produces_no_checks_and_overall_pass():
    report = run_validation(ValidationRequest())
    assert report.checks == []
    assert report.overall_status == "PASS"
    assert report.blocked is False


def test_only_material_domain_produces_only_checks_1_through_6():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0.92})))
    ids = {c.check_id for c in report.checks}
    assert ids == {1, 2, 3, 4, 5, 6}


# --- Checks 1-6: material domain --------------------------------------------


def test_check1_pass_within_practical_limit():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0.92})))
    assert _checks_by_id(report)[1].status == "PASS"


def test_check1_error_exceeds_practical_limit():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=97, **{"yield": 0.92})))
    assert _checks_by_id(report)[1].status == "ERROR"
    assert "practical limit" in _checks_by_id(report)[1].message


def test_check1_error_outside_physical_range():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=150, **{"yield": 0.92})))
    assert _checks_by_id(report)[1].status == "ERROR"
    assert "0-100%" in _checks_by_id(report)[1].message


def test_check2_pass_when_virgin_not_supplied():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0.92})))
    assert _checks_by_id(report)[2].status == "PASS"


def test_check2_pass_when_virgin_matches():
    report = run_validation(
        ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, virgin_percentage=35, **{"yield": 0.92}))
    )
    assert _checks_by_id(report)[2].status == "PASS"


def test_check2_error_when_virgin_mismatches():
    report = run_validation(
        ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, virgin_percentage=30, **{"yield": 0.92}))
    )
    assert _checks_by_id(report)[2].status == "ERROR"


def test_check3_error_when_sum_not_100():
    report = run_validation(
        ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, virgin_percentage=30, **{"yield": 0.92}))
    )
    assert _checks_by_id(report)[3].status == "ERROR"
    assert "not 100%" in _checks_by_id(report)[3].message


def test_check4_pass_when_balance_closes():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0.92})))
    assert _checks_by_id(report)[4].status == "PASS"


def test_check4_error_when_yield_invalid_blocks_balance():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0})))
    assert _checks_by_id(report)[4].status == "ERROR"


def test_check5_pass_valid_yield():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0.92})))
    assert _checks_by_id(report)[5].status == "PASS"


@pytest.mark.parametrize("bad_yield", [0, -0.5, 1.5])
def test_check5_error_invalid_yield(bad_yield):
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": bad_yield})))
    assert _checks_by_id(report)[5].status == "ERROR"


def test_check6_pass_no_negative_quantity():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0.92})))
    assert _checks_by_id(report)[6].status == "PASS"


def test_check6_error_negative_scrap_percentage():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=-10, **{"yield": 0.92})))
    assert _checks_by_id(report)[6].status == "ERROR"


def test_check6_omitted_when_insufficient_data():
    """When yield is invalid (0), material balance can't be computed, so
    check 6 is omitted entirely rather than guessed - not fabricated."""
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0})))
    assert 6 not in _checks_by_id(report)


# --- Checks 7, 8, 10, 11: energy/emissions domain ---------------------------


def test_check7_pass_positive_energy():
    report = run_validation(
        ValidationRequest(carbon_emission=CarbonEmissionInput(electricity_consumption_mwh_per_t=0.5, electricity_source_id="GRID_ELECTRICITY_IN"))
    )
    assert _checks_by_id(report)[7].status == "PASS"


def test_check7_warning_all_zero_energy():
    report = run_validation(ValidationRequest(carbon_emission=CarbonEmissionInput()))
    assert _checks_by_id(report)[7].status == "WARNING"


def test_check8_pass_mix_sums_to_100():
    report = run_validation(
        ValidationRequest(
            carbon_emission=CarbonEmissionInput(
                electricity_consumption_mwh_per_t=0.5,
                electricity_mix=[
                    ElectricityMixComponentInput(source_id="GRID_ELECTRICITY_IN", share_pct=70),
                    ElectricityMixComponentInput(source_id="RENEWABLE_ELECTRICITY_IN", share_pct=30),
                ],
            )
        )
    )
    assert _checks_by_id(report)[8].status == "PASS"


def test_check8_error_mix_not_100():
    report = run_validation(
        ValidationRequest(
            carbon_emission=CarbonEmissionInput(
                electricity_consumption_mwh_per_t=0.5,
                electricity_mix=[
                    ElectricityMixComponentInput(source_id="GRID_ELECTRICITY_IN", share_pct=70),
                    ElectricityMixComponentInput(source_id="RENEWABLE_ELECTRICITY_IN", share_pct=50),
                ],
            )
        )
    )
    assert _checks_by_id(report)[8].status == "ERROR"
    assert "120" in _checks_by_id(report)[8].message


def test_check8_warning_no_source_configured():
    report = run_validation(ValidationRequest(carbon_emission=CarbonEmissionInput()))
    assert _checks_by_id(report)[8].status == "WARNING"


def test_check10_warning_demo_factors_when_all_present():
    report = run_validation(ValidationRequest(carbon_emission=CarbonEmissionInput(process_route_id="EAF_HIGH_SCRAP")))
    assert _checks_by_id(report)[10].status == "WARNING"
    assert "DEMO_PLACEHOLDER" in _checks_by_id(report)[10].message


def test_check10_error_missing_factor():
    from backend.models.schemas import MaterialQuantityInput

    report = run_validation(
        ValidationRequest(carbon_emission=CarbonEmissionInput(materials=[MaterialQuantityInput(material_id="NOT_REAL_ID", quantity_t=0.1)]))
    )
    assert _checks_by_id(report)[10].status == "ERROR"
    assert _checks_by_id(report)[10].details is not None
    assert "missing" in _checks_by_id(report)[10].details


def test_check11_pass_plausible_units():
    report = run_validation(ValidationRequest(carbon_emission=CarbonEmissionInput(electricity_consumption_mwh_per_t=0.5)))
    assert _checks_by_id(report)[11].status == "PASS"


def test_check11_warning_implausible_electricity_value():
    """A value like 550 MWh/t is a strong hint the caller meant kWh, not MWh."""
    report = run_validation(ValidationRequest(carbon_emission=CarbonEmissionInput(electricity_consumption_mwh_per_t=550)))
    assert _checks_by_id(report)[11].status == "WARNING"
    assert "electricity_consumption_mwh_per_t" in _checks_by_id(report)[11].message


# --- Checks 9, 12: scrap chemistry domain -----------------------------------


def test_check9_pass_grade_chemistry_satisfied():
    report = run_validation(
        ValidationRequest(scrap_chemistry=ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    )
    assert _checks_by_id(report)[9].status == "PASS"


def test_check9_error_grade_chemistry_fails():
    """SS304 has Mo_max=0; high-quality scrap carries trace Mo - a real failure."""
    report = run_validation(
        ValidationRequest(scrap_chemistry=ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS304"))
    )
    assert _checks_by_id(report)[9].status == "ERROR"
    assert "Mo" in _checks_by_id(report)[9].details["failed_elements"]


def test_check12_pass_when_deficits_closable():
    report = run_validation(
        ValidationRequest(scrap_chemistry=ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.3, grade_id="SS316"))
    )
    assert _checks_by_id(report)[12].status == "PASS"


def test_scrap_chemistry_unknown_id_reports_error_not_500():
    report = run_validation(
        ValidationRequest(scrap_chemistry=ScrapChemistryInput(scrap_quality_id="NOT_REAL", scrap_mass=0.7, grade_id="SS304"))
    )
    assert _checks_by_id(report)[9].status == "ERROR"
    assert _checks_by_id(report)[12].status == "ERROR"


# --- Overall aggregation -----------------------------------------------------


def test_overall_pass_when_all_pass():
    report = run_validation(
        ValidationRequest(
            material=ValidationMaterialInput(scrap_percentage=65, **{"yield": 0.92}),
            scrap_chemistry=ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS316"),
        )
    )
    # Note: including carbon_emission always introduces the DEMO warning (check 10),
    # so we omit it here to test a genuinely all-PASS report.
    assert report.overall_status == "PASS"
    assert report.blocked is False


def test_overall_warning_when_only_warnings():
    report = run_validation(ValidationRequest(carbon_emission=CarbonEmissionInput(process_route_id="EAF_HIGH_SCRAP")))
    assert report.overall_status == "WARNING"
    assert report.blocked is False


def test_overall_error_when_any_error_present():
    report = run_validation(ValidationRequest(material=ValidationMaterialInput(scrap_percentage=150, **{"yield": 0.92})))
    assert report.overall_status == "ERROR"
    assert report.blocked is True


def test_summary_counts_match_checks():
    report = run_validation(
        ValidationRequest(
            material=ValidationMaterialInput(scrap_percentage=150, **{"yield": 0}),
            carbon_emission=CarbonEmissionInput(),
        )
    )
    pass_count = sum(1 for c in report.checks if c.status == "PASS")
    warn_count = sum(1 for c in report.checks if c.status == "WARNING")
    error_count = sum(1 for c in report.checks if c.status == "ERROR")
    assert report.summary == f"{pass_count} passed, {warn_count} warning(s), {error_count} error(s)"


# --- API-level tests -----------------------------------------------------------


def test_endpoint_returns_report_shape():
    r = client.post(
        "/validate",
        json={"material": {"scrap_percentage": 65, "yield": 0.92}},
    )
    assert r.status_code == 200
    body = r.json()
    assert {"overall_status", "blocked", "summary", "checks"}.issubset(body.keys())
    assert len(body["checks"]) == 6


def test_endpoint_accepts_out_of_range_scrap_percentage_without_422():
    """The whole point of this engine: an out-of-range value should be
    reported as a failed check, not rejected by the framework before this
    engine can explain why."""
    r = client.post("/validate", json={"material": {"scrap_percentage": 150, "yield": 0.92}})
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is True
    assert body["overall_status"] == "ERROR"


def test_endpoint_empty_body_returns_empty_report():
    r = client.post("/validate", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["checks"] == []
    assert body["overall_status"] == "PASS"


def test_endpoint_full_scenario_all_domains():
    r = client.post(
        "/validate",
        json={
            "material": {"scrap_percentage": 65, "yield": 0.92},
            "scrap_chemistry": {"scrap_quality_id": "SCRAP_HIGH_QUALITY", "scrap_mass": 0.7, "grade_id": "SS316"},
            "carbon_emission": {
                "electricity_consumption_mwh_per_t": 0.55,
                "electricity_mix": [
                    {"source_id": "GRID_ELECTRICITY_IN", "share_pct": 80},
                    {"source_id": "RENEWABLE_ELECTRICITY_IN", "share_pct": 20},
                ],
                "natural_gas_consumption_gj_per_t": 0.9,
                "process_route_id": "EAF_HIGH_SCRAP",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["checks"]) == 12
    # Only the DEMO-factor disclosure should prevent a clean PASS.
    assert body["overall_status"] == "WARNING"
    assert body["blocked"] is False
