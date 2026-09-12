"""
Material balance calculation engine.

Functional unit: 1 tonne of finished stainless steel.

This module is mass accounting ONLY - no emissions are calculated here
(that remains the job of backend/services/carbon_calculator.py). It exists
so the charge composition (scrap vs. virgin material, and the total mass
that must be charged to a furnace to net 1 tonne of finished steel after
yield losses) is computed once, consistently, and can be validated on its
own before any emission factor is applied to it.

Formulae (functional unit = 1 t finished steel):
    virgin_percentage = 100 - scrap_percentage
    charge_mass        = 1 / yield
    scrap_mass          = (scrap_percentage / 100) * charge_mass
    virgin_mass         = (virgin_percentage / 100) * charge_mass
"""
from __future__ import annotations

import math

from backend.models.schemas import MaterialBalanceInput, MaterialBalanceResult, MaterialBalanceValidationStatus

# Floating point tolerance for the balance-closes / sums-to-100 checks.
_EPSILON = 1e-6


def calculate_material_balance(payload: MaterialBalanceInput) -> MaterialBalanceResult:
    scrap_percentage = payload.scrap_percentage
    yield_fraction = payload.yield_fraction

    virgin_percentage = 100.0 - scrap_percentage

    scrap_fraction = scrap_percentage / 100.0
    virgin_fraction = virgin_percentage / 100.0

    charge_mass = 1.0 / yield_fraction
    scrap_mass = scrap_fraction * charge_mass
    virgin_mass = virgin_fraction * charge_mass

    # --- Required validation ---

    mix_sums_to_100 = math.isclose(scrap_percentage + virgin_percentage, 100.0, abs_tol=_EPSILON)
    mass_balance_closes = math.isclose(scrap_mass + virgin_mass, charge_mass, abs_tol=_EPSILON)
    no_negative_mass = charge_mass >= 0 and scrap_mass >= -_EPSILON and virgin_mass >= -_EPSILON

    overall = "PASS" if (mix_sums_to_100 and mass_balance_closes and no_negative_mass) else "FAIL"

    validation_status = MaterialBalanceValidationStatus(
        mix_sums_to_100=mix_sums_to_100,
        mass_balance_closes=mass_balance_closes,
        no_negative_mass=no_negative_mass,
        overall=overall,
    )

    return MaterialBalanceResult(
        charge_mass=round(charge_mass, 6),
        scrap_mass=round(scrap_mass, 6),
        virgin_mass=round(virgin_mass, 6),
        scrap_percentage=round(scrap_percentage, 6),
        virgin_percentage=round(virgin_percentage, 6),
        yield_fraction=round(yield_fraction, 6),
        validation_status=validation_status,
    )
