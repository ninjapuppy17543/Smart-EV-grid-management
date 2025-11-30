# database.py
from dataclasses import dataclass, field
from typing import List, Literal, Dict

TimeIndex = int  # 0..23

@dataclass
class Asset:
    owner: str
    appliance: str
    power_kw: float
    duration_h: int
    start_hour: int    # 0..23
    end_hour: int      # 0..24 (can wrap)
    variable: bool     # True = split over hours, False = fixed block
    enabled: bool = True

    # runtime fields (filled by logic)
    before_hours: List[TimeIndex] = field(default_factory=list)
    after_hours: List[TimeIndex] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    base_load: List[float]          # length 24
    co2_per_hour: List[float]       # length 24, tCO2/MWh
    scaling_factors: Dict[str, float]  # e.g. {"EV": 1.6, "HVAC": 1.3}


# ---- Price & CO2 "database" ----

PRICE_PER_HOUR = [
    8.70, 8.48, 8.52, 8.61, 8.69, 8.69,
    9.56, 11.58, 12.72, 13.07, 15.65, 17.65,
    16.24, 15.55, 15.12, 16.64, 18.60, 21.53,
    22.68, 20.29, 17.09, 14.09, 12.81, 11.63
]

CO2_PER_HOUR_BASELINE = [
    0.045, 0.042, 0.040, 0.038, 0.035, 0.032,
    0.030, 0.035, 0.050, 0.065, 0.070, 0.075,
    0.080, 0.085, 0.090, 0.095, 0.100, 0.110,
    0.105, 0.095, 0.085, 0.075, 0.060, 0.050
]


def generate_baseline_base_load() -> List[float]:
    base = []
    for h in range(24):
        val = 40.0
        if 7 <= h <= 9:
            val += 25.0
        if 17 <= h <= 21:
            val += 35.0
        base.append(val)
    return base


def generate_winter_base_load() -> List[float]:
    base = []
    for h in range(24):
        val = 55.0
        if 5 <= h <= 9:
            val += 70.0
        if 16 <= h <= 22:
            val += 90.0
        base.append(val)
    return base


def generate_future_base_load() -> List[float]:
    baseline = generate_baseline_base_load()
    base = []
    for h in range(24):
        val = baseline[h] * 1.9
        if 10 <= h <= 15:
            val += 35.0
        if 16 <= h <= 21:
            val += 70.0
        base.append(val)
    return base


def generate_winter_co2() -> List[float]:
    arr = []
    for h, val in enumerate(CO2_PER_HOUR_BASELINE):
        factor = 1.25
        if 17 <= h <= 21:
            factor = 1.45
        arr.append(val * factor)
    return arr


def generate_future_co2() -> List[float]:
    arr = []
    for h, val in enumerate(CO2_PER_HOUR_BASELINE):
        factor = 0.65
        if 10 <= h <= 16:
            factor = 0.45
        arr.append(val * factor)
    return arr


def get_scenarios() -> Dict[str, Scenario]:
    return {
        "Baseline": Scenario(
            name="Baseline",
            base_load=generate_baseline_base_load(),
            co2_per_hour=CO2_PER_HOUR_BASELINE,
            scaling_factors={},  # no extra scaling
        ),
        "Winter weekday": Scenario(
            name="Winter weekday",
            base_load=generate_winter_base_load(),
            co2_per_hour=generate_winter_co2(),
            scaling_factors={"EV": 1.4, "HVAC": 1.8, "Sauna": 1.6},
        ),
        "2030 future": Scenario(
            name="2030 future",
            base_load=generate_future_base_load(),
            co2_per_hour=generate_future_co2(),
            scaling_factors={"EV": 2.2, "HVAC": 1.9, "Battery": 1.9},
        ),
    }


def initial_assets() -> List[Asset]:
    assets: List[Asset] = []

    # --- Core "hero" assets you already had ---
    assets.extend([
        Asset("City EV fleet", "Fast chargers (EV)", 80.0, 4, 17, 24, True),
        Asset("Office block A", "HVAC", 30.0, 3, 14, 20, True),
        Asset("Supermarket", "Fridge defrost", 20.0, 4, 0, 24, False),
        Asset("Residential block", "EV chargers (EV)", 40.0, 6, 18, 24, True),
    ])

    # -------------------------
    # 1) Residential EV chargers (neighbourhoods)
    # -------------------------
    # ~10 blocks, evening/night charging, variable, moderate power
    for i in range(10):
        start = 18 + (i % 3)      # 18–20
        end = 24                  # until midnight
        power = 6.0 + (i % 4) * 1.5  # 6, 7.5, 9, 10.5 kW
        duration = 3 + (i % 3)    # 3–5 h
        assets.append(
            Asset(
                owner=f"Res block EV #{i+1}",
                appliance="EV chargers (EV)",
                power_kw=power,
                duration_h=duration,
                start_hour=start,
                end_hour=end,
                variable=True,
            )
        )

    # -------------------------
    # 2) Household appliances (dishwashers / laundry)
    # -------------------------
    # Fixed blocks, short duration, late evening windows
    for i in range(10):
        start = 20 + (i % 3)      # 20–22
        end = 24                  # runs before midnight
        power = 1.5 + (i % 2) * 0.5   # 1.5 or 2.0 kW
        duration = 2              # 2-hour wash program
        assets.append(
            Asset(
                owner=f"Household #{i+1}",
                appliance="Dishwasher (fixed)",
                power_kw=power,
                duration_h=duration,
                start_hour=start,
                end_hour=end,
                variable=False,   # fixed block
            )
        )

    # -------------------------
    # 3) Office HVAC / ventilation
    # -------------------------
    # Daytime office loads, variable (pre-cooling / pre-heating possible)
    for i in range(10):
        start = 7                 # workday morning
        end = 19                  # 7–19
        power = 15.0 + i * 1.5    # increasing size of buildings
        duration = 6 + (i % 3)    # 6–8 h active HVAC
        assets.append(
            Asset(
                owner=f"Office block #{i+1}",
                appliance="HVAC",
                power_kw=power,
                duration_h=duration,
                start_hour=start,
                end_hour=end,
                variable=True,
            )
        )

    # -------------------------
    # 4) Supermarket / cold storage
    # -------------------------
    # Can shift some cooling cycles throughout the night/day
    for i in range(8):
        start = (i % 4) * 6       # 0,6,12,18
        end = start + 6           # 6-hour windows
        power = 8.0 + (i % 3) * 2.0   # 8,10,12 kW
        duration = 3              # 3 hours of heavy cooling
        assets.append(
            Asset(
                owner=f"Supermarket #{i+1}",
                appliance="Cold storage",
                power_kw=power,
                duration_h=duration,
                start_hour=start,
                end_hour=end,
                variable=True,
            )
        )

    # -------------------------
    # 5) Bus depot EV chargers (wrap over midnight)
    # -------------------------
    # Start late evening, can run until morning → use wrap (start > end)
    for i in range(6):
        start = 22                # 22:00
        end = 6                   # 06:00 next day (wrap)
        power = 30.0 + i * 5.0    # larger depots
        duration = 4 + (i % 3)    # 4–6 h
        assets.append(
            Asset(
                owner=f"Bus depot #{i+1}",
                appliance="Bus chargers (EV)",
                power_kw=power,
                duration_h=duration,
                start_hour=start,
                end_hour=end,
                variable=True,
            )
        )

    # -------------------------
    # 6) Small community batteries
    # -------------------------
    # These can represent charging (load) that is shiftable at night.
    for i in range(6):
        start = 0                 # midnight
        end = 7                   # 7 am
        power = 10.0 + i * 2.0
        duration = 3 + (i % 2)    # 3–4 h
        assets.append(
            Asset(
                owner=f"Community battery #{i+1}",
                appliance="Battery charging",
                power_kw=power,
                duration_h=duration,
                start_hour=start,
                end_hour=end,
                variable=True,
            )
        )

    # Count check: 4 base + 10 + 10 + 10 + 8 + 6 + 6 = 54 assets
    return assets
