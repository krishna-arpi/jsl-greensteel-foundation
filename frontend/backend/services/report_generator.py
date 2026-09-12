"""
PDF report generator.

Orchestrates material_balance, scrap_chemistry, carbon_emissions, the
LP/MILP optimizer, sensitivity analysis, and validation against one
configuration, then renders a comprehensive PDF suitable for submission or
presentation. No new calculation logic lives here - every number in the
report comes from the same engines used elsewhere in this application.

Modeling note carried into the report itself: the optimizer's objective
uses a simplified single-commodity MWh-equivalent energy model (see
backend/optimization/lp_optimizer.py), while the detailed "Current Carbon
Intensity" figure comes from the full multi-fuel carbon_emissions engine.
The two can differ slightly for that reason - the report discloses this
explicitly rather than presenting one blended, ambiguous number.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing

from backend.data.loader import get_emission_factors, get_energy_sources, get_scrap_quality, get_steel_grades
from backend.models.schemas import (
    CarbonEmissionInput,
    MaterialBalanceInput,
    MaterialQuantityInput,
    OptimizationInput,
    ReportInput,
    ScrapChemistryInput,
    SensitivityInput,
    ValidationMaterialInput,
    ValidationRequest,
)
from backend.services.carbon_emissions import calculate_carbon_emissions
from backend.services.material_balance import calculate_material_balance
from backend.services.scrap_chemistry import calculate_scrap_chemistry
from backend.services.sensitivity_analysis import run_sensitivity_analysis
from backend.optimization.lp_optimizer import optimize_carbon_and_energy
from backend.validation.validation_engine import run_validation

_GJ_PER_MWH = 3.6

# --- Palette (print-friendly: white background, steel-blue accent) ---------
STEEL = colors.HexColor("#3A6688")
STEEL_LIGHT = colors.HexColor("#E8EEF3")
EMBER = colors.HexColor("#DB8A2C")
GOOD = colors.HexColor("#3F7F5C")
WARN = colors.HexColor("#B94A2C")
CARBON_GREY = colors.HexColor("#5C6975")
INK = colors.HexColor("#1A1F24")
MUTED = colors.HexColor("#6B7785")
ROW_ALT = colors.HexColor("#F4F6F8")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("ReportTitle", parent=ss["Title"], fontSize=20, textColor=INK, spaceAfter=4))
    ss.add(ParagraphStyle("ReportSubtitle", parent=ss["Normal"], fontSize=11, textColor=MUTED, spaceAfter=14))
    ss.add(ParagraphStyle("SectionHeading", parent=ss["Heading1"], fontSize=13, textColor=STEEL, spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("SubHeading", parent=ss["Heading2"], fontSize=10.5, textColor=INK, spaceBefore=8, spaceAfter=4))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9.5, textColor=INK, leading=13.5))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, textColor=MUTED, leading=11))
    ss.add(ParagraphStyle("WarningBanner", parent=ss["Normal"], fontSize=9, textColor=WARN, leading=13))
    ss.add(ParagraphStyle("BigNumber", parent=ss["Normal"], fontSize=22, textColor=STEEL, alignment=TA_CENTER, spaceAfter=2))
    ss.add(ParagraphStyle("BigNumberCaption", parent=ss["Normal"], fontSize=8.5, textColor=MUTED, alignment=TA_CENTER))
    return ss


def _table(data: list[list], col_widths=None, header=True) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8DEE4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), STEEL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
        for row_idx in range(1, len(data)):
            if row_idx % 2 == 0:
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), ROW_ALT))
    t.setStyle(TableStyle(style))
    return t


def _status_color(status: str):
    return {"PASS": GOOD, "OPTIMAL": GOOD, "WARNING": EMBER, "ERROR": WARN, "INFEASIBLE": WARN}.get(status, MUTED)


def _pie_chart(labels_values: list[tuple[str, float]], slice_colors: list) -> Drawing:
    drawing = Drawing(430, 160)
    pie = Pie()
    pie.x, pie.y = 60, 5
    pie.width, pie.height = 150, 150
    values = [max(v, 0.0001) for _, v in labels_values]
    pie.data = values
    pie.labels = None
    pie.slices.strokeWidth = 0.75
    pie.slices.strokeColor = colors.white
    for i, c in enumerate(slice_colors[: len(values)]):
        pie.slices[i].fillColor = c
    drawing.add(pie)

    legend = Legend()
    legend.x, legend.y = 240, 130
    legend.dx, legend.dy = 8, 8
    legend.fontSize = 8
    legend.fontName = "Helvetica"
    legend.alignment = "left"
    legend.columnMaximum = 10
    legend.colorNamePairs = [(slice_colors[i], f"{name}: {value:.3f}") for i, (name, value) in enumerate(labels_values)]
    drawing.add(legend)
    return drawing


def _bar_chart(categories: list[str], values: list[float], bar_colors, width=470, height=190) -> Drawing:
    drawing = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x, bc.y = 45, 40
    bc.width, bc.height = width - 70, height - 70
    bc.data = [values]
    bc.categoryAxis.categoryNames = categories
    bc.categoryAxis.labels.fontSize = 7.5
    bc.categoryAxis.labels.angle = 0 if len(categories) <= 5 else 30
    bc.categoryAxis.labels.dy = -12 if len(categories) <= 5 else -18
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontSize = 7.5
    bc.bars[0].fillColor = STEEL
    if isinstance(bar_colors, list):
        for i, c in enumerate(bar_colors):
            bc.bars[(0, i)].fillColor = c
    drawing.add(bc)
    return drawing


def _assemble(payload: ReportInput) -> dict:
    """Runs every engine once against the given configuration and returns a
    plain dict of everything the PDF needs."""
    grades = {g["id"]: g for g in get_steel_grades()["grades"]}
    scrap_categories = {c["id"]: c for c in get_scrap_quality()["categories"]}
    energy_sources = {s["id"]: s for s in get_energy_sources()["sources"]}
    factors = get_emission_factors()["factors"]

    if payload.grade_id not in grades:
        raise HTTPException(status_code=422, detail=f"Unknown grade_id '{payload.grade_id}'.")
    if payload.scrap_quality_id not in scrap_categories:
        raise HTTPException(status_code=422, detail=f"Unknown scrap_quality_id '{payload.scrap_quality_id}'.")
    if payload.energy_source_id not in energy_sources:
        raise HTTPException(status_code=422, detail=f"Unknown energy_source_id '{payload.energy_source_id}'.")

    grade = grades[payload.grade_id]
    scrap_quality = scrap_categories[payload.scrap_quality_id]
    energy_source = energy_sources[payload.energy_source_id]

    mb = calculate_material_balance(MaterialBalanceInput(scrap_percentage=payload.scrap_pct, **{"yield": payload.yield_fraction}))

    sc = calculate_scrap_chemistry(
        ScrapChemistryInput(scrap_quality_id=payload.scrap_quality_id, scrap_mass=mb.scrap_mass, grade_id=payload.grade_id)
    )

    alloy_materials = [
        MaterialQuantityInput(material_id=a.alloy_id, quantity_t=a.required_mass_kg / 1000.0, label=a.alloy_name)
        for a in sc.alloy_additions
        if a.required_mass_kg > 0.01
    ]

    ce_input = CarbonEmissionInput(
        materials=[
            MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=mb.scrap_mass, label="Scrap"),
            MaterialQuantityInput(material_id="VIRGIN_EMBODIED", quantity_t=mb.virgin_mass, label="Virgin iron"),
            *alloy_materials,
        ],
        electricity_consumption_mwh_per_t=payload.electricity_consumption_mwh_per_t,
        electricity_mix=[],
        electricity_source_id=payload.energy_source_id,
        natural_gas_consumption_gj_per_t=payload.natural_gas_consumption_gj_per_t,
        coal_consumption_gj_per_t=payload.coal_consumption_gj_per_t,
    )
    ce = calculate_carbon_emissions(ce_input)

    energy_demand_mwh_equiv = payload.electricity_consumption_mwh_per_t + (
        payload.natural_gas_consumption_gj_per_t + payload.coal_consumption_gj_per_t
    ) / _GJ_PER_MWH

    opt = optimize_carbon_and_energy(
        OptimizationInput(
            grade_id=payload.grade_id,
            scrap_quality_id=payload.scrap_quality_id,
            **{"yield": payload.yield_fraction},
            scrap_pct_min=payload.scrap_pct_min,
            scrap_pct_max=payload.scrap_pct_max,
            energy_demand_mwh_equivalent_per_t=max(energy_demand_mwh_equiv, 0.01),
            allow_energy_blending=True,
            energy_capacity_pct={},
            current_scrap_pct=payload.scrap_pct,
            current_energy_mix_pct={payload.energy_source_id: 100},
        )
    )

    sens = run_sensitivity_analysis(
        SensitivityInput(
            grade_id=payload.grade_id,
            scrap_quality_id=payload.scrap_quality_id,
            scrap_pct=payload.scrap_pct,
            energy_source_id=payload.energy_source_id,
            **{"yield": payload.yield_fraction},
            energy_demand_mwh_equivalent_per_t=max(energy_demand_mwh_equiv, 0.01),
        )
    )

    validation = run_validation(
        ValidationRequest(
            material=ValidationMaterialInput(scrap_percentage=payload.scrap_pct, **{"yield": payload.yield_fraction}),
            scrap_chemistry=ScrapChemistryInput(
                scrap_quality_id=payload.scrap_quality_id, scrap_mass=mb.scrap_mass, grade_id=payload.grade_id
            ),
            carbon_emission=ce_input,
        )
    )

    return {
        "grade": grade,
        "scrap_quality": scrap_quality,
        "energy_source": energy_source,
        "factors": factors,
        "mb": mb,
        "sc": sc,
        "ce": ce,
        "opt": opt,
        "sens": sens,
        "validation": validation,
    }


def generate_report_pdf(payload: ReportInput) -> bytes:  # noqa: C901
    data = _assemble(payload)
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        title="JSL GreenSteel Carbon Optimization Report",
    )
    story = []

    # --- Cover / Section 1: Project title ---
    story.append(Paragraph("JSL GreenSteel Carbon Optimization Report", ss["ReportTitle"]))
    story.append(Paragraph("Data-driven decision support for lower-carbon stainless steelmaking", ss["ReportSubtitle"]))
    story.append(
        Paragraph(
            "⚠ Every emission factor, alloy specification, and scrap composition used in this report is an "
            "unverified DEMO_PLACEHOLDER value (see Emission-Factor Sources and Model Limitations). This is a "
            "decision-support prototype, not a verified ISO product carbon footprint.",
            ss["WarningBanner"],
        )
    )
    story.append(Spacer(1, 10))

    # --- Section 2: Scenario information ---
    story.append(Paragraph("1. Scenario Information", ss["SectionHeading"]))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(
        _table(
            [
                ["Field", "Value"],
                ["Scenario name", payload.scenario_name],
                ["Functional unit", "1 tonne of finished stainless steel (tSS)"],
                ["Generated", generated_at],
            ],
            col_widths=[5 * cm, 11 * cm],
        )
    )

    # --- Section 3: User inputs ---
    story.append(Paragraph("2. User Inputs", ss["SectionHeading"]))
    story.append(
        _table(
            [
                ["Parameter", "Value"],
                ["Stainless steel grade", data["grade"]["grade_name"]],
                ["Scrap %", f"{payload.scrap_pct:.1f}%"],
                ["Virgin %", f"{100 - payload.scrap_pct:.1f}%"],
                ["Scrap quality", data["scrap_quality"]["category_name"]],
                ["Energy source", data["energy_source"]["name"]],
                ["Electricity consumption", f"{payload.electricity_consumption_mwh_per_t} MWh/t"],
                ["Natural gas consumption", f"{payload.natural_gas_consumption_gj_per_t} GJ/t"],
                ["Coal consumption", f"{payload.coal_consumption_gj_per_t} GJ/t"],
                ["Production yield", f"{payload.yield_fraction * 100:.1f}%"],
            ],
            col_widths=[6 * cm, 10 * cm],
        )
    )

    # --- Section 4: Material balance ---
    mb = data["mb"]
    story.append(Paragraph("3. Material Balance", ss["SectionHeading"]))
    story.append(
        Paragraph(
            "Functional unit = 1 t finished steel. charge_mass = 1 / yield. scrap_mass = scrap% x charge_mass; "
            "virgin_mass = virgin% x charge_mass.",
            ss["Body"],
        )
    )
    story.append(
        _table(
            [
                ["Quantity", "Value"],
                ["Charge mass", f"{mb.charge_mass:.4f} t"],
                ["Scrap mass", f"{mb.scrap_mass:.4f} t"],
                ["Virgin mass", f"{mb.virgin_mass:.4f} t"],
                ["Yield", f"{mb.yield_fraction * 100:.1f}%"],
                ["Balance validation", mb.validation_status.overall],
            ],
            col_widths=[6 * cm, 10 * cm],
        )
    )

    # --- Section 5: Scrap/virgin mix (chart) ---
    story.append(Paragraph("4. Scrap / Virgin Mix", ss["SectionHeading"]))
    story.append(_pie_chart([("Scrap", mb.scrap_mass), ("Virgin", mb.virgin_mass)], [STEEL, EMBER]))

    # --- Section 6: Alloy additions ---
    sc = data["sc"]
    story.append(Paragraph("5. Alloy Additions", ss["SectionHeading"]))
    story.append(
        Paragraph(
            "deficit = max(0, required_mass - supplied_mass). alloy_required = deficit / (concentration x recovery).",
            ss["Body"],
        )
    )
    deficit_rows = [["Element", "Required (t)", "Supplied (t)", "Deficit (t)"]]
    for d in sc.element_deficits:
        deficit_rows.append([d.element, f"{d.required_mass:.4f}", f"{d.supplied_mass:.4f}", f"{d.deficit_mass:.4f}"])
    story.append(_table(deficit_rows, col_widths=[3 * cm, 4.3 * cm, 4.3 * cm, 4.3 * cm]))
    story.append(Spacer(1, 6))
    addition_rows = [["Element", "Alloy", "Required (kg)"]]
    for a in sc.alloy_additions:
        addition_rows.append([a.element, a.alloy_name, f"{a.required_mass_kg:.2f}"])
    story.append(_table(addition_rows, col_widths=[3 * cm, 8 * cm, 5 * cm]))
    story.append(
        Paragraph(
            f"Grade chemistry validation (scrap + alloy additions vs. {data['grade']['grade_name']}'s full Cr/Ni/Mo/C/Si/Mn/N "
            f"envelope): <b><font color='{'#3F7F5C' if sc.chemistry_validation.overall == 'PASS' else '#B94A2C'}'>"
            f"{sc.chemistry_validation.overall}</font></b>.",
            ss["Body"],
        )
    )

    story.append(PageBreak())

    # --- Section 7: Carbon calculation methodology ---
    story.append(Paragraph("6. Carbon Calculation", ss["SectionHeading"]))
    story.append(
        Paragraph(
            "Total Carbon = Material Carbon + Energy Carbon + Process Carbon. Material Carbon sums quantity x "
            "emission factor across scrap, virgin material, and every alloy addition above. Energy Carbon is "
            "consumption x emission factor for electricity, natural gas, and coal. Process Carbon is a "
            "configurable, exogenous term (not used in this scenario unless a process route was selected).",
            ss["Body"],
        )
    )

    # --- Section 8: Emission breakdown (chart + table) ---
    ce = data["ce"]
    story.append(Paragraph("7. Emission Breakdown", ss["SectionHeading"]))
    story.append(
        _pie_chart(
            [
                ("Material", ce.material_emissions.total_tco2e),
                ("Electricity", ce.electricity_emissions.total_tco2e),
                ("Fuel", ce.fuel_emissions.total_tco2e),
                ("Process", ce.process_emissions.tco2e_per_t),
            ],
            [STEEL, EMBER, CARBON_GREY, GOOD],
        )
    )
    breakdown_rows = [["Material", "Quantity (t)", "Factor (tCO2e/t)", "tCO2e"]]
    for item in ce.emission_breakdown_by_material:
        factor_str = f"{item.emission_factor_tco2e_per_t}" if item.factor_available else "unavailable"
        breakdown_rows.append([item.label, f"{item.quantity_t:.4f}", factor_str, f"{item.tco2e:.4f}"])
    story.append(_table(breakdown_rows, col_widths=[5 * cm, 3.7 * cm, 3.7 * cm, 3.6 * cm]))
    if ce.emission_breakdown_by_material:
        story.append(Spacer(1, 6))
        story.append(
            _bar_chart(
                [item.label for item in ce.emission_breakdown_by_material],
                [item.tco2e for item in ce.emission_breakdown_by_material],
                STEEL,
            )
        )
    if ce.missing_factor_warnings:
        story.append(Spacer(1, 4))
        for w in ce.missing_factor_warnings:
            story.append(Paragraph(f"⚠ {w}", ss["WarningBanner"]))

    story.append(PageBreak())

    # --- Section 9: Current carbon intensity ---
    story.append(Paragraph("8. Current Carbon Intensity", ss["SectionHeading"]))
    story.append(Paragraph(f"{ce.carbon_intensity_tCO2e_per_tSS:.4f}", ss["BigNumber"]))
    story.append(Paragraph("tCO2e / tSS (full multi-fuel emissions engine, including alloy additions)", ss["BigNumberCaption"]))
    story.append(Spacer(1, 10))

    # --- Section 10 & 11: Optimized carbon intensity + reduction ---
    opt = data["opt"]
    story.append(Paragraph("9. Optimized Carbon Intensity &amp; Carbon Reduction", ss["SectionHeading"]))
    if opt.status == "OPTIMAL":
        story.append(
            Paragraph(
                "The optimizer's objective uses a simplified single-commodity, MWh-equivalent energy model "
                "(see Methodology &amp; Sources), distinct from the detailed multi-fuel model used for Current "
                f"Carbon Intensity above. Its own internal baseline for this configuration is "
                f"{opt.current_carbon_intensity:.4f} tCO2e/tSS, which may differ slightly from the "
                f"{ce.carbon_intensity_tCO2e_per_tSS:.4f} tCO2e/tSS figure above for that reason.",
                ss["Small"],
            )
        )
        story.append(Spacer(1, 6))
        story.append(
            _bar_chart(
                ["Current (optimizer model)", "Optimized"],
                [opt.current_carbon_intensity, opt.optimized_carbon_intensity],
                [EMBER, GOOD],
            )
        )
        story.append(
            _table(
                [
                    ["Metric", "Value"],
                    ["Optimized scrap %", f"{opt.optimal_scrap_percentage:.1f}%"],
                    ["Optimized virgin %", f"{opt.optimal_virgin_percentage:.1f}%"],
                    ["Optimized carbon intensity", f"{opt.optimized_carbon_intensity:.4f} tCO2e/tSS"],
                    ["CO2 saved (absolute)", f"{opt.absolute_reduction:.4f} tCO2e/tSS"],
                    ["Carbon reduction (%)", f"{opt.percentage_reduction:.1f}%"],
                ],
                col_widths=[7 * cm, 9 * cm],
            )
        )
        story.append(Spacer(1, 4))
        mix_rows = [["Energy source", "Share (%)"]]
        for m in opt.optimal_energy_mix:
            if m.share_pct > 0.05:
                mix_rows.append([m.label, f"{m.share_pct:.1f}%"])
        story.append(_table(mix_rows, col_widths=[10 * cm, 6 * cm]))
        addition_rows2 = [["Element", "Alloy", "Required (kg)"]]
        for a in opt.optimal_alloy_additions:
            if a.required_mass_kg > 0.01:
                addition_rows2.append([a.element, a.alloy_name, f"{a.required_mass_kg:.2f}"])
        if len(addition_rows2) > 1:
            story.append(Spacer(1, 4))
            story.append(_table(addition_rows2, col_widths=[3 * cm, 8 * cm, 5 * cm]))
        if opt.current_scenario_chemistry_valid is False:
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"⚠ {opt.current_scenario_chemistry_note}", ss["WarningBanner"]))
    else:
        story.append(
            Paragraph(
                f"<b>{opt.status}</b>: {opt.message}",
                ss["Body"],
            )
        )

    story.append(PageBreak())

    # --- Section 12: Sensitivity results ---
    sens = data["sens"]
    story.append(Paragraph("10. Sensitivity Results", ss["SectionHeading"]))
    story.append(Paragraph("Scrap % vs. Carbon Intensity", ss["SubHeading"]))
    scrap_points = sens.scrap_percentage_sweep.points
    story.append(
        _bar_chart(
            [p.label for p in scrap_points],
            [p.carbon_intensity_tco2e_per_t for p in scrap_points],
            [GOOD if p.is_lowest_feasible else (STEEL if p.chemistry_valid else CARBON_GREY) for p in scrap_points],
        )
    )
    story.append(Paragraph(sens.scrap_percentage_sweep.insight, ss["Body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Energy Source vs. Carbon Intensity", ss["SubHeading"]))
    energy_points = sens.energy_source_sweep.points
    story.append(
        _bar_chart(
            [p.label for p in energy_points],
            [p.carbon_intensity_tco2e_per_t for p in energy_points],
            [GOOD if p.is_lowest_feasible else (STEEL if p.chemistry_valid else CARBON_GREY) for p in energy_points],
        )
    )
    story.append(Paragraph(sens.energy_source_sweep.insight, ss["Body"]))

    story.append(PageBreak())

    # --- Section 13: Validation results ---
    validation = data["validation"]
    story.append(Paragraph("11. Validation Results", ss["SectionHeading"]))
    story.append(
        Paragraph(
            f"Overall status: <b><font color='{'#3F7F5C' if validation.overall_status == 'PASS' else ('#DB8A2C' if validation.overall_status == 'WARNING' else '#B94A2C')}'>"
            f"{validation.overall_status}</font></b> — {validation.summary}",
            ss["Body"],
        )
    )
    val_rows = [["#", "Check", "Status", "Message"]]
    for c in validation.checks:
        val_rows.append([str(c.check_id), c.name, c.status, c.message])
    story.append(_table(val_rows, col_widths=[0.8 * cm, 3.7 * cm, 2 * cm, 9.5 * cm]))

    story.append(PageBreak())

    # --- Section 14: Assumptions ---
    story.append(Paragraph("12. Assumptions", ss["SectionHeading"]))
    assumptions = [
        "Functional unit is 1 tonne of finished stainless steel (tSS) throughout.",
        "charge_mass = 1 / yield; scrap_mass and virgin_mass are split from charge_mass by scrap%.",
        "Scrap contributes Cr/Ni/Mo via element_mass = scrap_mass x element_fraction x recovery.",
        "Any deficit against the selected grade's minimum Cr/Ni/Mo is closed with the minimum alloy addition needed.",
        "Material Carbon sums quantity x emission factor across scrap, virgin material, and alloy additions.",
        "Energy Carbon is consumption x emission factor for the selected electricity source, natural gas, and coal.",
        "The optimizer's energy term uses a simplified single-commodity MWh-equivalent blend (1 MWh = 3.6 GJ) "
        "across grid/renewable electricity, natural gas, and coal - see Methodology & Sources for why.",
        "All twelve validation checks were run against this exact configuration; see Validation Results above.",
    ]
    for a in assumptions:
        story.append(Paragraph(f"• {a}", ss["Body"]))

    # --- Section 15: Emission-factor sources ---
    story.append(Paragraph("13. Emission-Factor Sources", ss["SectionHeading"]))
    story.append(
        Paragraph(
            "Every factor below is an unverified DEMO_PLACEHOLDER value inserted so this application runs "
            "end-to-end - none has been sourced from a verified standard, plant record, or published dataset.",
            ss["Small"],
        )
    )
    factor_rows = [["Parameter", "Value", "Unit", "Year", "Scope", "Boundary", "Source", "Confidence"]]
    for f in data["factors"]:
        factor_rows.append(
            [f["name"], str(f["value"]), f["unit"], str(f.get("year") or "—"), f["scope"], f["boundary"], f["source"], f["confidence"]]
        )
    story.append(
        _table(
            factor_rows,
            col_widths=[3.2 * cm, 1.6 * cm, 2 * cm, 1.2 * cm, 1.6 * cm, 2.6 * cm, 3 * cm, 1.8 * cm],
        )
    )

    story.append(PageBreak())

    # --- Section 16: Model limitations ---
    story.append(Paragraph("14. Model Limitations", ss["SectionHeading"]))
    limitations = [
        "Scrap composition varies — a real scrap lot's Cr/Ni/Mo content is a distribution, not a fixed number.",
        "Emission factors vary by geography and technology — a grid factor in one region or year is not another's.",
        "Energy consumption varies by operating conditions — furnace practice, campaign length, and equipment condition all matter.",
        "Alloy recovery varies — furnace practice and alloy form (lump, briquette, fines) affect how much of an addition actually reports to the melt.",
        "LCA allocation methodology affects scrap emissions — how upstream burden is allocated to scrap (cut-off vs. substitution vs. shared) changes its embodied factor.",
        "Corporate carbon intensity and product carbon footprint have different boundaries — a company-wide Scope 1+2+3 figure is not the same measurement as a per-tonne product footprint, and the two should never be swapped for each other.",
        "This is a decision-support prototype, not a verified ISO product carbon footprint.",
    ]
    for lim in limitations:
        story.append(Paragraph(f"• {lim}", ss["Body"]))

    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "JSL GreenSteel — Carbon &amp; Energy Optimization Calculator. Generated automatically; all figures "
            "are illustrative DEMO_PLACEHOLDER values unless otherwise stated.",
            ss["Small"],
        )
    )

    doc.build(story)
    return buf.getvalue()
