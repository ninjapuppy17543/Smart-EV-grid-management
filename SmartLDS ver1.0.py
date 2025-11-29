import tkinter as tk
from tkinter import ttk, messagebox
import math

# -----------------------------
# MODEL / DATA
# -----------------------------

NUM_HOURS = 24  # simulate 24 hours

# Real hourly price data in cents/kWh for hours 00–23
PRICE_PER_HOUR = [
    8.70, 8.48, 8.52, 8.61, 8.69, 8.69,
    9.56, 11.58, 12.72, 13.07, 15.65, 17.65,
    16.24, 15.55, 15.12, 16.64, 18.60, 21.53,
    22.68, 20.29, 17.09, 14.09, 12.81, 11.63
]


def generate_base_load(num_hours=NUM_HOURS):
    """
    Baseline: one day with morning and evening peaks.
    Units are arbitrary "kW" or "MW" (we call them 'units').
    """
    base = []
    for h in range(num_hours):
        hour_of_day = h % 24
        val = 40.0  # base level

        # morning bump
        if 7 <= hour_of_day <= 9:
            val += 25.0

        # evening bump
        if 17 <= hour_of_day <= 21:
            val += 35.0

        base.append(val)
    return base


def generate_winter_load():
    """
    Winter weekday: MUCH stronger heating in the morning and evening.
    This should clearly look 'wintery' on the chart.
    """
    base = []
    for h in range(NUM_HOURS):
        # higher night base (heating never fully off)
        val = 55.0

        # strong morning heating spike
        if 5 <= h <= 9:
            val += 70.0  # was ~40 before

        # very strong evening heating + EVs spike
        if 16 <= h <= 22:
            val += 90.0  # was ~50 before

        base.append(val)
    return base


def generate_future2030_load(baseline):
    """
    2030 future: clearly higher overall electrification.
    Highly amplified version of the baseline with a huge evening EV wave.
    """
    base = []
    for h in range(NUM_HOURS):
        # 90% more overall demand vs baseline
        val = baseline[h] * 1.9

        # extra mid-day electrification (heat pumps, industry, etc.)
        if 10 <= h <= 15:
            val += 35.0

        # massive EV / heat pump cluster in late afternoon–evening
        if 16 <= h <= 21:
            val += 70.0

        base.append(val)
    return base


# Real hourly CO2 intensity (your data), converted from tCO2/GWh to tCO2/MWh
CO2_PER_HOUR_BASELINE = [
    0.045,  # 00:00-01:00, 45 tCO2/GWh
    0.042,  # 01:00-02:00, 42
    0.040,  # 02:00-03:00, 40
    0.038,  # 03:00-04:00, 38
    0.035,  # 04:00-05:00, 35
    0.032,  # 05:00-06:00, 32
    0.030,  # 06:00-07:00, 30
    0.035,  # 07:00-08:00, 35
    0.050,  # 08:00-09:00, 50
    0.065,  # 09:00-10:00, 65
    0.070,  # 10:00-11:00, 70
    0.075,  # 11:00-12:00, 75
    0.080,  # 12:00-13:00, 80
    0.085,  # 13:00-14:00, 85
    0.090,  # 14:00-15:00, 90
    0.095,  # 15:00-16:00, 95
    0.100,  # 16:00-17:00, 100
    0.110,  # 17:00-18:00, 110
    0.105,  # 18:00-19:00, 105
    0.095,  # 19:00-20:00, 95
    0.085,  # 20:00-21:00, 85
    0.075,  # 21:00-22:00, 75
    0.060,  # 22:00-23:00, 60
    0.050,  # 23:00-00:00, 50
]


def generate_winter_co2():
    """
    Winter: clearly dirtier grid, especially in the evening.
    """
    arr = []
    for h, val in enumerate(CO2_PER_HOUR_BASELINE):
        factor = 1.25  # +25% generally
        if 17 <= h <= 21:
            factor = 1.45  # +45% at evening peak
        arr.append(val * factor)
    return arr


def generate_future2030_co2():
    """
    2030 future: clearly cleaner grid, especially at midday.
    """
    arr = []
    for h, val in enumerate(CO2_PER_HOUR_BASELINE):
        factor = 0.65  # 35% cleaner overall
        if 10 <= h <= 16:
            factor = 0.45  # 55% cleaner around solar / renewables peak
        arr.append(val * factor)
    return arr


# Scenario-dependent globals
BASE_LOAD_BASELINE = generate_base_load()
BASE_LOAD = BASE_LOAD_BASELINE[:]  # current base load

CO2_PER_HOUR = CO2_PER_HOUR_BASELINE[:]  # current CO2 profile

# -----------------------------
# ASSETS
# -----------------------------

# Each asset is a dict:
# {
#   "owner": str,
#   "appliance": str,
#   "power_kW": float,
#   "duration_h": int,
#   "start_hour": int,        # 0–23
#   "end_hour": int,          # 0–24 (can wrap if end <= start)
#   "variable": bool,         # True = can be split, False = continuous block
#   "enabled": bool,
#   "before_hours": [ints],
#   "after_hours": [ints],
#   "base_power_kW": float,   # original power for scenario scaling
# }

ASSETS = [
    # Original 4
    {
        "owner": "City EV fleet",
        "appliance": "Fast chargers",
        "power_kW": 80.0,
        "duration_h": 4,
        "start_hour": 17,
        "end_hour": 24,  # 17–23
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Office block A",
        "appliance": "HVAC pre-cooling",
        "power_kW": 30.0,
        "duration_h": 3,
        "start_hour": 14,
        "end_hour": 20,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Supermarket",
        "appliance": "Fridge defrost cycles",
        "power_kW": 20.0,
        "duration_h": 4,
        "start_hour": 0,
        "end_hour": 24,
        "variable": False,   # fixed block
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Residential block",
        "appliance": "EV chargers",
        "power_kW": 40.0,
        "duration_h": 6,
        "start_hour": 18,
        "end_hour": 24,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },

    # Extra loads to feel like a real district
    {
        "owner": "Apartment block 1",
        "appliance": "Heat pumps",
        "power_kW": 25.0,
        "duration_h": 5,
        "start_hour": 5,
        "end_hour": 10,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Apartment block 2",
        "appliance": "Heat pumps",
        "power_kW": 30.0,
        "duration_h": 5,
        "start_hour": 5,
        "end_hour": 10,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Tram depot",
        "appliance": "Night chargers",
        "power_kW": 60.0,
        "duration_h": 3,
        "start_hour": 0,
        "end_hour": 6,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Metro station",
        "appliance": "Ventilation",
        "power_kW": 35.0,
        "duration_h": 4,
        "start_hour": 10,
        "end_hour": 18,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Data center X",
        "appliance": "Battery charging",
        "power_kW": 70.0,
        "duration_h": 5,
        "start_hour": 0,
        "end_hour": 24,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Public swimming pool",
        "appliance": "Water heating",
        "power_kW": 20.0,
        "duration_h": 4,
        "start_hour": 6,
        "end_hour": 12,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "School A",
        "appliance": "Ventilation",
        "power_kW": 15.0,
        "duration_h": 3,
        "start_hour": 7,
        "end_hour": 15,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "School B",
        "appliance": "Ventilation",
        "power_kW": 15.0,
        "duration_h": 3,
        "start_hour": 7,
        "end_hour": 15,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "City hospital",
        "appliance": "Laundry machines",
        "power_kW": 25.0,
        "duration_h": 4,
        "start_hour": 8,
        "end_hour": 18,
        "variable": False,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Bakery",
        "appliance": "Oven preheat",
        "power_kW": 10.0,
        "duration_h": 2,
        "start_hour": 3,
        "end_hour": 7,
        "variable": False,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Street lighting",
        "appliance": "Early dimming",
        "power_kW": 10.0,
        "duration_h": 4,
        "start_hour": 18,
        "end_hour": 24,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Downtown chargers",
        "appliance": "Public EV charging",
        "power_kW": 50.0,
        "duration_h": 5,
        "start_hour": 17,
        "end_hour": 24,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "University labs",
        "appliance": "Freezer defrost",
        "power_kW": 8.0,
        "duration_h": 3,
        "start_hour": 1,
        "end_hour": 7,
        "variable": False,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Logistics warehouse",
        "appliance": "Pre-chill cooling",
        "power_kW": 22.0,
        "duration_h": 4,
        "start_hour": 12,
        "end_hour": 20,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Office block B",
        "appliance": "Server backup charging",
        "power_kW": 18.0,
        "duration_h": 3,
        "start_hour": 0,
        "end_hour": 8,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "City gym",
        "appliance": "Sauna heaters",
        "power_kW": 12.0,
        "duration_h": 3,
        "start_hour": 15,
        "end_hour": 22,
        "variable": False,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Central library",
        "appliance": "HVAC",
        "power_kW": 10.0,
        "duration_h": 4,
        "start_hour": 8,
        "end_hour": 18,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Small shops",
        "appliance": "Refrigeration",
        "power_kW": 18.0,
        "duration_h": 6,
        "start_hour": 8,
        "end_hour": 22,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Residential solar",
        "appliance": "Battery charging",
        "power_kW": 15.0,
        "duration_h": 5,
        "start_hour": 10,
        "end_hour": 20,
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
    {
        "owner": "Electric bus depot",
        "appliance": "Overnight charging",
        "power_kW": 90.0,
        "duration_h": 6,
        "start_hour": 22,
        "end_hour": 6,   # wraps over midnight
        "variable": True,
        "enabled": True,
        "before_hours": [],
        "after_hours": [],
    },
]

# remember original power for scenario scaling
for a in ASSETS:
    a["base_power_kW"] = a["power_kW"]

before_load = BASE_LOAD[:]
after_load = BASE_LOAD[:]

# cost of flexible loads only (in cents)
cost_before_flex = 0.0
cost_after_flex = 0.0


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def get_window_hours(start_hour, end_hour):
    """
    Return a list of allowed hours for an asset, as indices 0..23.
    Handles wrap-around:
      - if start < end:  [start, ..., end-1]
      - if start > end:  [start, ..., 23] + [0, ..., end-1]
    """
    sh = int(start_hour)
    eh = int(end_hour)

    if sh < eh:
        return list(range(sh, eh))
    else:
        # wrap across midnight
        return list(range(sh, NUM_HOURS)) + list(range(0, eh))


def recalculate_schedules():
    """
    Recompute BEFORE and AFTER curves, per-asset schedules,
    and cost of flexible loads.

    BEFORE: naive scheduling – first 'duration' hours in the allowed window
            with FULL power.

    AFTER:
      - start from BEFORE load (everyone naive)
      - for each asset, a fraction p = flex participation:
          * (1-p) stays in original naive hours
          * p is shifted to smarter hours (variable vs fixed)
        using a weighted combination of:
          - low grid load
          - low price
        where the weight is controlled by the Grid vs Price slider.
    """
    global before_load, after_load, cost_before_flex, cost_after_flex

    participation = flex_var.get() / 100.0  # 0..1
    priority_val = priority_var.get() / 100.0
    price_weight = priority_val          # 0..1
    grid_weight = 1.0 - priority_val     # 1..0

    # Reset schedules
    for a in ASSETS:
        a["before_hours"] = []
        a["after_hours"] = []

    # --------------------
    # 1) BEFORE scenario (everyone dumb, full power)
    # --------------------
    before_load = BASE_LOAD[:]

    for asset in ASSETS:
        if not asset.get("enabled", True):
            continue

        sh = clamp(asset["start_hour"], 0, NUM_HOURS - 1)
        # allow 0..24 for end
        eh = clamp(asset["end_hour"], 0, NUM_HOURS)

        if sh == eh:
            continue  # empty window

        window_hours = get_window_hours(sh, eh)
        if not window_hours:
            continue

        max_duration = len(window_hours)
        duration = int(clamp(asset["duration_h"], 1, max_duration))

        power_full = asset["power_kW"]
        if power_full <= 0:
            continue

        hours_used = window_hours[:duration]
        for h in hours_used:
            before_load[h] += power_full

        asset["before_hours"] = hours_used

    # cost BEFORE (flexible loads only)
    cost_before_flex = 0.0
    for asset in ASSETS:
        if not asset.get("enabled", True):
            continue
        power_full = asset["power_kW"]
        for h in asset["before_hours"]:
            cost_before_flex += power_full * PRICE_PER_HOUR[h]

    # --------------------
    # 2) AFTER scenario
    # --------------------
    after_load = before_load[:]

    # sort largest power first so big assets shape the curve first
    for asset in sorted(
        [a for a in ASSETS if a.get("enabled", True)],
        key=lambda a: -a["power_kW"]
    ):
        power_full = asset["power_kW"]
        if power_full <= 0:
            continue

        p = participation
        participating_power = power_full * p
        remaining_power = power_full * (1.0 - p)

        if p <= 0 or not asset["before_hours"]:
            asset["after_hours"] = asset["before_hours"][:]
            continue

        sh = clamp(asset["start_hour"], 0, NUM_HOURS - 1)
        eh = clamp(asset["end_hour"], 0, NUM_HOURS)
        if sh == eh:
            asset["after_hours"] = asset["before_hours"][:]
            continue

        window_hours = get_window_hours(sh, eh)
        if not window_hours:
            asset["after_hours"] = asset["before_hours"][:]
            continue

        duration = int(clamp(asset["duration_h"], 1, len(window_hours)))

        # 2a) remove participating part from old naive hours
        for h in asset["before_hours"]:
            after_load[h] -= participating_power

        # 2b) compute scores (grid + price) inside window
        window_loads = [after_load[hh] for hh in window_hours]
        min_load = min(window_loads)
        max_load = max(window_loads)

        window_prices = [PRICE_PER_HOUR[hh] for hh in window_hours]
        min_price = min(window_prices)
        max_price = max(window_prices)

        hour_score = {}
        for hh in window_hours:
            if max_load > min_load:
                load_norm = (after_load[hh] - min_load) / (max_load - min_load)
            else:
                load_norm = 0.0

            if max_price > min_price:
                price_norm = (PRICE_PER_HOUR[hh] - min_price) / (max_price - min_price)
            else:
                price_norm = 0.0

            # combine
            score = grid_weight * load_norm + price_weight * price_norm
            hour_score[hh] = score

        chosen_hours = []

        if asset.get("variable", True):
            # VARIABLE: pick best individual hours
            available_hours = window_hours.copy()
            for _ in range(duration):
                if not available_hours:
                    break
                best_h = min(available_hours, key=lambda h: hour_score[h])
                chosen_hours.append(best_h)
                available_hours.remove(best_h)
        else:
            # FIXED: best continuous block
            if duration > len(window_hours):
                duration = len(window_hours)
            best_block = None
            best_block_score = None
            for i in range(0, len(window_hours) - duration + 1):
                block = window_hours[i:i + duration]
                block_score = sum(hour_score[h] for h in block)
                if best_block_score is None or block_score < best_block_score:
                    best_block_score = block_score
                    best_block = block
            if best_block is not None:
                chosen_hours = best_block

        # 2c) add participating part to new hours
        for h in chosen_hours:
            after_load[h] += participating_power

        asset["after_hours"] = chosen_hours

    # cost AFTER
    cost_after_flex = 0.0
    for asset in ASSETS:
        if not asset.get("enabled", True):
            continue
        power_full = asset["power_kW"]
        p = participation
        participating_power = power_full * p
        remaining_power = power_full * (1.0 - p)

        for h in asset["before_hours"]:
            cost_after_flex += remaining_power * PRICE_PER_HOUR[h]
        for h in asset["after_hours"]:
            cost_after_flex += participating_power * PRICE_PER_HOUR[h]


# -----------------------------
# SCENARIOS
# -----------------------------

def apply_scenario(name: str):
    """
    Change BASE_LOAD, CO2_PER_HOUR and asset powers according to scenario.
    Then recompute schedules and update UI.
    """
    global BASE_LOAD, CO2_PER_HOUR

    if name == "Baseline":
        BASE_LOAD = BASE_LOAD_BASELINE[:]
        CO2_PER_HOUR = CO2_PER_HOUR_BASELINE[:]
        for a in ASSETS:
            a["power_kW"] = a["base_power_kW"]

    elif name == "Winter weekday":
        BASE_LOAD = generate_winter_load()
        CO2_PER_HOUR = generate_winter_co2()
        for a in ASSETS:
            base = a["base_power_kW"]
            if "Heat pumps" in a["appliance"] or "HVAC" in a["appliance"]:
                a["power_kW"] = base * 1.8   # much more heating demand
            elif "EV" in a["appliance"] or "charg" in a["appliance"]:
                a["power_kW"] = base * 1.4   # more EV charging in winter
            elif "Sauna" in a["appliance"]:
                a["power_kW"] = base * 1.6   # Finnish winter sauna meta 😈
            else:
                a["power_kW"] = base * 1.2   # everything slightly higher

    elif name == "2030 future":
        BASE_LOAD = generate_future2030_load(BASE_LOAD_BASELINE)
        CO2_PER_HOUR = generate_future2030_co2()
        for a in ASSETS:
            base = a["base_power_kW"]
            if "EV" in a["appliance"] or "charg" in a["appliance"]:
                a["power_kW"] = base * 2.2   # lots more EVs
            elif "Heat pumps" in a["appliance"] or "Battery" in a["appliance"]:
                a["power_kW"] = base * 1.9   # more electric heating & storage
            else:
                a["power_kW"] = base * 1.4   # more electrification overall


    recalculate_schedules()
    update_stats_and_graph()
    update_asset_listbox()


# -----------------------------
# UI
# -----------------------------

root = tk.Tk()
root.title("FlexiCity – Peak, Price & CO₂ Demo (24h, scenarios)")
root.geometry("1450x900")

mainframe = ttk.Frame(root, padding=10)
mainframe.grid(row=0, column=0, sticky="nsew")
root.rowconfigure(0, weight=1)
root.columnconfigure(0, weight=1)

# Left: scenario + stats + asset list + input + sliders
left_frame = ttk.Frame(mainframe)
left_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 15))

# Right: graphs
right_frame = ttk.Frame(mainframe)
right_frame.grid(row=0, column=1, sticky="nsew")
mainframe.columnconfigure(1, weight=1)
mainframe.rowconfigure(0, weight=1)

# --- Scenario selector ---

scenario_frame = ttk.LabelFrame(left_frame, text="Scenario")
scenario_frame.grid(row=0, column=0, sticky="new", pady=(0, 10))

scenario_var = tk.StringVar(value="Baseline")
scenario_combo = ttk.Combobox(
    scenario_frame,
    textvariable=scenario_var,
    state="readonly",
    values=["Baseline", "Winter weekday", "2030 future"]
)
scenario_combo.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
scenario_frame.columnconfigure(0, weight=1)


def on_scenario_change(event=None):
    apply_scenario(scenario_var.get())


scenario_combo.bind("<<ComboboxSelected>>", on_scenario_change)

# --- Stats ---

stats_frame = ttk.LabelFrame(left_frame, text="Peak, cost & CO₂")
stats_frame.grid(row=1, column=0, sticky="new", pady=(0, 10))

peak_before_var = tk.StringVar()
peak_after_var = tk.StringVar()
reduction_var = tk.StringVar()
cost_before_var = tk.StringVar()
cost_after_var = tk.StringVar()
saving_cost_var = tk.StringVar()
co2_var = tk.StringVar()

ttk.Label(stats_frame, text="Peak BEFORE: ").grid(row=0, column=0, sticky="w")
ttk.Label(stats_frame, textvariable=peak_before_var).grid(row=0, column=1, sticky="w")

ttk.Label(stats_frame, text="Peak AFTER: ").grid(row=1, column=0, sticky="w")
ttk.Label(stats_frame, textvariable=peak_after_var).grid(row=1, column=1, sticky="w")

ttk.Label(stats_frame, text="Peak reduction: ").grid(row=2, column=0, sticky="w")
ttk.Label(stats_frame, textvariable=reduction_var).grid(row=2, column=1, sticky="w")

ttk.Label(stats_frame, text="Cost BEFORE (flex): ").grid(row=3, column=0, sticky="w")
ttk.Label(stats_frame, textvariable=cost_before_var).grid(row=3, column=1, sticky="w")

ttk.Label(stats_frame, text="Cost AFTER (flex): ").grid(row=4, column=0, sticky="w")
ttk.Label(stats_frame, textvariable=cost_after_var).grid(row=4, column=1, sticky="w")

ttk.Label(stats_frame, text="Saving: ").grid(row=5, column=0, sticky="w")
ttk.Label(stats_frame, textvariable=saving_cost_var).grid(row=5, column=1, sticky="w")

ttk.Label(stats_frame, text="CO₂ saving: ").grid(row=6, column=0, sticky="w")
ttk.Label(stats_frame, textvariable=co2_var).grid(row=6, column=1, sticky="w")

# --- Asset list ---

assets_frame = ttk.LabelFrame(left_frame, text="Flexible loads")
assets_frame.grid(row=2, column=0, sticky="nsew")
left_frame.rowconfigure(2, weight=1)

asset_listbox = tk.Listbox(assets_frame, width=75, height=12)
asset_listbox.grid(row=0, column=0, sticky="nsew")
assets_frame.rowconfigure(0, weight=1)
assets_frame.columnconfigure(0, weight=1)

asset_scroll = ttk.Scrollbar(assets_frame, orient="vertical", command=asset_listbox.yview)
asset_scroll.grid(row=0, column=1, sticky="ns")
asset_listbox.config(yscrollcommand=asset_scroll.set)

asset_detail_var = tk.StringVar()
ttk.Label(
    assets_frame,
    textvariable=asset_detail_var,
    wraplength=500,
    justify="left"
).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))


def update_asset_listbox():
    asset_listbox.delete(0, tk.END)
    for a in ASSETS:
        var_str = "var" if a.get("variable", True) else "fixed"
        state_str = "ON" if a.get("enabled", True) else "OFF"
        text = (
            f"[{state_str}] {a['owner']} – {a['appliance']} | "
            f"{a['power_kW']:.1f} kW x {a['duration_h']} h | "
            f"{var_str} | window {a['start_hour']}-{a['end_hour']}h"
        )
        asset_listbox.insert(tk.END, text)


def on_asset_select(event):
    if not asset_listbox.curselection():
        return
    idx = asset_listbox.curselection()[0]
    asset = ASSETS[idx]
    after_hours = sorted(asset.get("after_hours", []))
    before_hours = sorted(asset.get("before_hours", []))
    var_str = "variable (can be split)" if asset.get("variable", True) else "fixed (continuous block)"
    state_str = "ENABLED" if asset.get("enabled", True) else "DISABLED"

    detail = (
        f"{asset['owner']} – {asset['appliance']}\n"
        f"State: {state_str}\n"
        f"Power: {asset['power_kW']} kW for {asset['duration_h']} h\n"
        f"Type: {var_str}\n"
        f"Time window: {asset['start_hour']}–{asset['end_hour']} h "
        f"(wraps past midnight if end ≤ start)\n\n"
        f"BEFORE scheduled at: {before_hours}\n"
        f"AFTER scheduled (participating part): {after_hours}"
    )
    asset_detail_var.set(detail)


asset_listbox.bind("<<ListboxSelect>>", on_asset_select)

# --- Add / edit asset ---

input_frame = ttk.LabelFrame(left_frame, text="Add / edit flexible load")
input_frame.grid(row=3, column=0, sticky="new", pady=(10, 0))

ttk.Label(input_frame, text="Owner / Name:").grid(row=0, column=0, sticky="w")
entry_owner = ttk.Entry(input_frame, width=25)
entry_owner.grid(row=0, column=1, sticky="w")

ttk.Label(input_frame, text="Appliance:").grid(row=1, column=0, sticky="w")
entry_appliance = ttk.Entry(input_frame, width=25)
entry_appliance.grid(row=1, column=1, sticky="w")

ttk.Label(input_frame, text="Power (kW):").grid(row=2, column=0, sticky="w")
entry_power = ttk.Entry(input_frame, width=10)
entry_power.grid(row=2, column=1, sticky="w")

ttk.Label(input_frame, text="Duration (h):").grid(row=3, column=0, sticky="w")
entry_duration = ttk.Entry(input_frame, width=10)
entry_duration.grid(row=3, column=1, sticky="w")

ttk.Label(input_frame, text="Start hour (0–23):").grid(row=4, column=0, sticky="w")
entry_start = ttk.Entry(input_frame, width=10)
entry_start.grid(row=4, column=1, sticky="w")

ttk.Label(input_frame, text="End hour (0–24, can wrap)").grid(row=5, column=0, sticky="w")
entry_end = ttk.Entry(input_frame, width=10)
entry_end.grid(row=5, column=1, sticky="w")

var_variable = tk.BooleanVar(value=True)
check_variable = ttk.Checkbutton(
    input_frame,
    text="Variable (can be split into separate hours)",
    variable=var_variable
)
check_variable.grid(row=6, column=0, columnspan=2, sticky="w", pady=(5, 0))

var_enabled = tk.BooleanVar(value=True)
check_enabled = ttk.Checkbutton(
    input_frame,
    text="Enabled (included in simulation)",
    variable=var_enabled
)
check_enabled.grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 0))

editing_index = None


def read_form_values():
    owner = entry_owner.get().strip() or "Custom house"
    appliance = entry_appliance.get().strip() or "Appliance"
    power = float(entry_power.get())
    duration = int(entry_duration.get())
    start = int(entry_start.get())
    end = int(entry_end.get())
    variable = var_variable.get()
    enabled = var_enabled.get()

    if not (0 <= start < NUM_HOURS):
        raise ValueError("Start hour must be between 0 and 23")
    if not (0 <= end <= NUM_HOURS):
        raise ValueError("End hour must be between 0 and 24")
    if start == end:
        raise ValueError("Start and end hour cannot be the same (empty window)")

    return {
        "owner": owner,
        "appliance": appliance,
        "power_kW": power,
        "duration_h": duration,
        "start_hour": start,
        "end_hour": end,
        "variable": variable,
        "enabled": enabled,
        "before_hours": [],
        "after_hours": [],
        "base_power_kW": power,
    }


def clear_form():
    global editing_index
    entry_owner.delete(0, tk.END)
    entry_appliance.delete(0, tk.END)
    entry_power.delete(0, tk.END)
    entry_duration.delete(0, tk.END)
    entry_start.delete(0, tk.END)
    entry_end.delete(0, tk.END)
    var_variable.set(True)
    var_enabled.set(True)
    editing_index = None


def add_asset():
    global editing_index
    try:
        asset = read_form_values()
        ASSETS.append(asset)
        recalculate_schedules()
        update_stats_and_graph()
        update_asset_listbox()
        clear_form()
    except ValueError as e:
        messagebox.showerror("Invalid input", str(e))


def load_selected_to_form():
    global editing_index
    if not asset_listbox.curselection():
        messagebox.showerror("No selection", "Select an asset in the list first.")
        return
    idx = asset_listbox.curselection()[0]
    editing_index = idx
    asset = ASSETS[idx]

    entry_owner.delete(0, tk.END)
    entry_owner.insert(0, asset["owner"])

    entry_appliance.delete(0, tk.END)
    entry_appliance.insert(0, asset["appliance"])

    entry_power.delete(0, tk.END)
    entry_power.insert(0, str(asset["base_power_kW"]))

    entry_duration.delete(0, tk.END)
    entry_duration.insert(0, str(asset["duration_h"]))

    entry_start.delete(0, tk.END)
    entry_start.insert(0, str(asset["start_hour"]))

    entry_end.delete(0, tk.END)
    entry_end.insert(0, str(asset["end_hour"]))

    var_variable.set(asset.get("variable", True))
    var_enabled.set(asset.get("enabled", True))


def save_changes():
    global editing_index
    if editing_index is None:
        messagebox.showerror("No asset loaded", "Click 'Load selected' first to edit.")
        return
    try:
        new_asset = read_form_values()
        # keep base_power_kW as new base
        ASSETS[editing_index] = new_asset
        recalculate_schedules()
        update_stats_and_graph()
        update_asset_listbox()
        clear_form()
    except ValueError as e:
        messagebox.showerror("Invalid input", str(e))


def toggle_enabled_selected():
    if not asset_listbox.curselection():
        messagebox.showerror("No selection", "Select an asset in the list first.")
        return
    idx = asset_listbox.curselection()[0]
    asset = ASSETS[idx]
    asset["enabled"] = not asset.get("enabled", True)
    recalculate_schedules()
    update_stats_and_graph()
    update_asset_listbox()


def delete_selected():
    global editing_index
    if not asset_listbox.curselection():
        messagebox.showerror("No selection", "Select an asset in the list first.")
        return
    idx = asset_listbox.curselection()[0]
    del ASSETS[idx]
    editing_index = None
    asset_detail_var.set("")
    recalculate_schedules()
    update_stats_and_graph()
    update_asset_listbox()


add_button = ttk.Button(input_frame, text="Add new", command=add_asset)
add_button.grid(row=8, column=0, pady=(5, 0), sticky="ew")

load_button = ttk.Button(input_frame, text="Load selected", command=load_selected_to_form)
load_button.grid(row=8, column=1, pady=(5, 0), sticky="ew")

save_button = ttk.Button(input_frame, text="Save changes", command=save_changes)
save_button.grid(row=9, column=0, columnspan=2, pady=(5, 0), sticky="ew")

toggle_button = ttk.Button(input_frame, text="Toggle ON/OFF selected", command=toggle_enabled_selected)
toggle_button.grid(row=10, column=0, columnspan=2, pady=(5, 0), sticky="ew")

delete_button = ttk.Button(input_frame, text="Delete selected", command=delete_selected)
delete_button.grid(row=11, column=0, columnspan=2, pady=(5, 0), sticky="ew")

# --- Sliders: priority & flex ---

priority_frame = ttk.LabelFrame(left_frame, text="Priority: grid vs price")
priority_frame.grid(row=4, column=0, sticky="new", pady=(10, 0))

priority_var = tk.DoubleVar(value=50.0)  # 0 = only grid, 100 = only price
ttk.Label(priority_frame, text="Grid  ←  focus  →  Price").grid(row=0, column=0, sticky="w")

priority_value_label = ttk.Label(priority_frame, text="Grid 50% / Price 50%")
priority_value_label.grid(row=2, column=0, sticky="w")


def on_priority_change(v):
    price_w = priority_var.get() / 100.0
    grid_w = 1.0 - price_w
    priority_value_label.config(
        text=f"Grid {grid_w*100:.0f}% / Price {price_w*100:.0f}%"
    )
    recalculate_schedules()
    update_stats_and_graph()


scale_priority = ttk.Scale(
    priority_frame,
    from_=0,
    to=100,
    orient="horizontal",
    variable=priority_var,
    command=on_priority_change
)
scale_priority.grid(row=1, column=0, sticky="ew")
priority_frame.columnconfigure(0, weight=1)

flex_frame = ttk.LabelFrame(left_frame, text="Flex participation")
flex_frame.grid(row=5, column=0, sticky="new", pady=(10, 0))

flex_var = tk.DoubleVar(value=100.0)  # percent

flex_value_label = ttk.Label(flex_frame, text="Flexible users: 100%")
flex_value_label.grid(row=0, column=0, columnspan=2, sticky="w")


def on_flex_change(v):
    flex_value_label.config(text=f"Flexible users: {flex_var.get():.0f}%")
    recalculate_schedules()
    update_stats_and_graph()


scale_flex = ttk.Scale(
    flex_frame,
    from_=0,
    to=100,
    orient="horizontal",
    variable=flex_var,
    command=on_flex_change
)
scale_flex.grid(row=1, column=0, columnspan=2, sticky="ew")

flex_frame.columnconfigure(0, weight=1)
flex_frame.columnconfigure(1, weight=1)

# --- Optimisation buttons ---

def find_optimal_settings():
    """
    Min-peak search over flex & grid/price.
    """
    global after_load

    best_peak = None
    best_flex = None
    best_priority = None

    for flex in range(0, 101, 10):
        for pr in range(0, 101, 10):
            flex_var.set(flex)
            priority_var.set(pr)
            recalculate_schedules()
            peak_a = max(after_load)
            if best_peak is None or peak_a < best_peak:
                best_peak = peak_a
                best_flex = flex
                best_priority = pr

    if best_flex is not None and best_priority is not None:
        flex_var.set(best_flex)
        priority_var.set(best_priority)
        on_flex_change(str(best_flex))
        on_priority_change(str(best_priority))


def find_optimal_co2_settings():
    """
    Min-CO2 search + report best CO2 and best balance (peak+CO2).
    """
    global before_load, after_load

    results = []

    for flex in range(0, 101, 10):
        for pr in range(0, 101, 10):
            flex_var.set(flex)
            priority_var.set(pr)
            recalculate_schedules()

            peak_a = max(after_load)

            emissions_before_t_day = 0.0
            emissions_after_t_day = 0.0
            for h in range(NUM_HOURS):
                emissions_before_t_day += before_load[h] * CO2_PER_HOUR[h]
                emissions_after_t_day += after_load[h] * CO2_PER_HOUR[h]

            results.append({
                "flex": flex,
                "priority": pr,
                "peak": peak_a,
                "emissions_before": emissions_before_t_day,
                "emissions_after": emissions_after_t_day,
            })

    if not results:
        messagebox.showinfo("CO₂ optimisation", "No results to analyse.")
        return

    # best CO2
    best_co2 = min(results, key=lambda r: r["emissions_after"])

    # balanced (peak+CO2)
    peaks = [r["peak"] for r in results]
    ems = [r["emissions_after"] for r in results]
    peak_min, peak_max = min(peaks), max(peaks)
    em_min, em_max = min(ems), max(ems)

    def normalise(x, lo, hi):
        if hi > lo:
            return (x - lo) / (hi - lo)
        return 0.0

    best_balanced = None
    best_score = None
    for r in results:
        peak_norm = normalise(r["peak"], peak_min, peak_max)
        em_norm = normalise(r["emissions_after"], em_min, em_max)
        score = 0.5 * peak_norm + 0.5 * em_norm
        if best_score is None or score < best_score:
            best_score = score
            best_balanced = r

    # Apply CO2-optimal
    flex_var.set(best_co2["flex"])
    priority_var.set(best_co2["priority"])
    on_flex_change(str(best_co2["flex"]))
    on_priority_change(str(best_co2["priority"]))

    base_em = best_co2["emissions_before"]
    best_em = best_co2["emissions_after"]
    saving_t_day = base_em - best_em
    saving_pct = (saving_t_day / base_em * 100) if base_em > 0 else 0.0

    base_em_bal = best_balanced["emissions_before"]
    best_em_bal = best_balanced["emissions_after"]
    saving_bal_day = base_em_bal - best_em_bal
    saving_bal_pct = (saving_bal_day / base_em_bal * 100) if base_em_bal > 0 else 0.0

    txt = (
        "Best CO₂ saving (min emissions):\n"
        f"  Flexible users: {best_co2['flex']}%\n"
        f"  Grid / Price: Grid {100 - best_co2['priority']}% / Price {best_co2['priority']}%\n"
        f"  Emissions AFTER: {best_em:.2f} tCO₂/day\n"
        f"  Saving vs baseline: {saving_t_day:.2f} tCO₂/day ({saving_pct:.1f}%)\n"
        f"  Peak AFTER: {best_co2['peak']:.1f} units\n\n"
        "Best balance (peak + CO₂ together):\n"
        f"  Flexible users: {best_balanced['flex']}%\n"
        f"  Grid / Price: Grid {100 - best_balanced['priority']}% / Price {best_balanced['priority']}%\n"
        f"  Emissions AFTER: {best_em_bal:.2f} tCO₂/day\n"
        f"  Saving vs baseline: {saving_bal_day:.2f} tCO₂/day ({saving_bal_pct:.1f}%)\n"
        f"  Peak AFTER: {best_balanced['peak']:.1f} units\n"
    )

    messagebox.showinfo("CO₂ optimisation results", txt)


def find_ideal_settings():
    """
    Balanced optimum: peak + cost + CO2 + flex + grid/price symmetry.
    """
    global before_load, after_load, cost_after_flex

    results = []
    baseline_emissions = None

    for flex in range(0, 101, 10):
        for pr in range(0, 101, 10):
            flex_var.set(flex)
            priority_var.set(pr)
            recalculate_schedules()

            peak_a = max(after_load)
            cost_a_eur = cost_after_flex / 100.0

            emissions_before_t_day = 0.0
            emissions_after_t_day = 0.0
            for h in range(NUM_HOURS):
                emissions_before_t_day += before_load[h] * CO2_PER_HOUR[h]
                emissions_after_t_day += after_load[h] * CO2_PER_HOUR[h]

            if baseline_emissions is None:
                baseline_emissions = emissions_before_t_day

            results.append({
                "flex": flex,
                "priority": pr,
                "peak": peak_a,
                "cost": cost_a_eur,
                "emissions": emissions_after_t_day,
            })

    if not results:
        messagebox.showinfo("Ideal balance", "No results to analyse.")
        return

    peaks = [r["peak"] for r in results]
    costs = [r["cost"] for r in results]
    ems = [r["emissions"] for r in results]
    peak_min, peak_max = min(peaks), max(peaks)
    cost_min, cost_max = min(costs), max(costs)
    em_min, em_max = min(ems), max(ems)

    def norm(x, lo, hi):
        if hi > lo:
            return (x - lo) / (hi - lo)
        return 0.0

    best_ideal = None
    best_score = None

    for r in results:
        peak_norm = norm(r["peak"], peak_min, peak_max)
        cost_norm = norm(r["cost"], cost_min, cost_max)
        em_norm = norm(r["emissions"], em_min, em_max)

        flex_norm = r["flex"] / 100.0
        flex_penalty = 1.0 - flex_norm

        priority_penalty = abs(r["priority"] - 50.0) / 50.0

        score = (peak_norm + cost_norm + em_norm + flex_penalty + priority_penalty) / 5.0

        if best_score is None or score < best_score:
            best_score = score
            best_ideal = r

    flex_var.set(best_ideal["flex"])
    priority_var.set(best_ideal["priority"])
    on_flex_change(str(best_ideal["flex"]))
    on_priority_change(str(best_ideal["priority"]))

    base_em = baseline_emissions if baseline_emissions is not None else best_ideal["emissions"]
    saving_t_day = base_em - best_ideal["emissions"]
    saving_pct = (saving_t_day / base_em * 100) if base_em > 0 else 0.0

    txt = (
        "Ideal balanced settings (peak + cost + CO₂ + flex + price/grid):\n"
        f"  Flexible users: {best_ideal['flex']}%\n"
        f"  Grid / Price: Grid {100 - best_ideal['priority']}% / Price {best_ideal['priority']}%\n"
        f"  Peak AFTER: {best_ideal['peak']:.1f} units\n"
        f"  Cost AFTER (flex loads): {best_ideal['cost']:.2f} € per day\n"
        f"  Emissions AFTER: {best_ideal['emissions']:.2f} tCO₂/day\n"
        f"  CO₂ saving vs baseline: {saving_t_day:.2f} tCO₂/day ({saving_pct:.1f}%)\n"
    )

    messagebox.showinfo("Ideal balance result", txt)


def find_ideal_peak_settings():
    """
    Max peak reduction, but only if cost saving >= 0 and CO2 saving >= 0.
    """
    global before_load, after_load, cost_before_flex, cost_after_flex

    baseline_peak = None
    baseline_cost_eur = None
    baseline_emissions = None

    best_combo = None
    best_peak_after = None

    for flex in range(0, 101, 10):
        for pr in range(0, 101, 10):
            flex_var.set(flex)
            priority_var.set(pr)
            recalculate_schedules()

            if baseline_peak is None:
                baseline_peak = max(before_load)
                baseline_cost_eur = cost_before_flex / 100.0
                baseline_emissions = 0.0
                for h in range(NUM_HOURS):
                    baseline_emissions += before_load[h] * CO2_PER_HOUR[h]

            peak_after = max(after_load)
            cost_after_eur = cost_after_flex / 100.0

            emissions_after_t_day = 0.0
            for h in range(NUM_HOURS):
                emissions_after_t_day += after_load[h] * CO2_PER_HOUR[h]

            saving_cost = baseline_cost_eur - cost_after_eur
            saving_co2 = baseline_emissions - emissions_after_t_day

            if saving_cost < 0 or saving_co2 < 0:
                continue

            if best_peak_after is None or peak_after < best_peak_after:
                best_peak_after = peak_after
                best_combo = {
                    "flex": flex,
                    "priority": pr,
                    "peak_after": peak_after,
                    "cost_after_eur": cost_after_eur,
                    "emissions_after_t_day": emissions_after_t_day,
                    "saving_cost": saving_cost,
                    "saving_co2": saving_co2,
                }

    if best_combo is None:
        messagebox.showinfo(
            "Ideal peak result",
            "No combination found that both saves money and CO₂.\n"
            "Try relaxing the constraints or adjusting loads."
        )
        return

    flex_var.set(best_combo["flex"])
    priority_var.set(best_combo["priority"])
    on_flex_change(str(best_combo["flex"]))
    on_priority_change(str(best_combo["priority"]))

    baseline_peak = baseline_peak if baseline_peak is not None else 0.0
    peak_reduction = baseline_peak - best_combo["peak_after"]
    peak_reduction_pct = (
        peak_reduction / baseline_peak * 100
        if baseline_peak > 0 else 0.0
    )

    txt = (
        "Ideal peak settings (max peak reduction with € & CO₂ savings):\n"
        f"  Flexible users: {best_combo['flex']}%\n"
        f"  Grid / Price: Grid {100 - best_combo['priority']}% / "
        f"Price {best_combo['priority']}%\n\n"
        f"  Peak AFTER: {best_combo['peak_after']:.1f} units\n"
        f"  Peak reduction vs baseline: {peak_reduction:.1f} units "
        f"({peak_reduction_pct:.1f}%)\n\n"
        f"  Cost AFTER (flex loads): {best_combo['cost_after_eur']:.2f} € / day\n"
        f"  Cost saving vs baseline: {best_combo['saving_cost']:.2f} € / day\n\n"
        f"  Emissions AFTER: {best_combo['emissions_after_t_day']:.2f} tCO₂ / day\n"
        f"  CO₂ saving vs baseline: {best_combo['saving_co2']:.2f} tCO₂ / day\n"
    )

    messagebox.showinfo("Ideal peak result", txt)


opt_button = ttk.Button(
    flex_frame,
    text="Auto-find optimal (min peak)",
    command=find_optimal_settings
)
opt_button.grid(row=2, column=0, sticky="ew", pady=(5, 0))

opt_co2_button = ttk.Button(
    flex_frame,
    text="Auto-find optimal (min CO₂ + balance)",
    command=find_optimal_co2_settings
)
opt_co2_button.grid(row=3, column=0, sticky="ew", pady=(5, 0))

ideal_button = ttk.Button(
    flex_frame,
    text="Ideal balance (peak, CO₂, price, flex)",
    command=find_ideal_settings
)
ideal_button.grid(row=2, column=1, sticky="ew", pady=(5, 0))

ideal_peak_button = ttk.Button(
    flex_frame,
    text="Ideal peak (max reduction with € & CO₂ gains)",
    command=find_ideal_peak_settings
)
ideal_peak_button.grid(row=3, column=1, sticky="ew", pady=(5, 0))

# --- Graph layout ---

before_frame = ttk.LabelFrame(right_frame, text="Before – dumb scheduling")
before_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 5))

after_frame = ttk.LabelFrame(right_frame, text="After – smart scheduling")
after_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(5, 5))

bottom_frame = ttk.Frame(right_frame)
bottom_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(5, 0))

right_frame.rowconfigure(0, weight=1)
right_frame.rowconfigure(1, weight=1)
right_frame.rowconfigure(2, weight=1)
right_frame.columnconfigure(0, weight=1)
right_frame.columnconfigure(1, weight=1)

bottom_frame.rowconfigure(0, weight=1)
bottom_frame.columnconfigure(0, weight=3)  # comparison wider
bottom_frame.columnconfigure(1, weight=2)  # price also fairly wide

combined_frame = ttk.LabelFrame(bottom_frame, text="Comparison")
combined_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

price_frame = ttk.LabelFrame(bottom_frame, text="Price curve (cents/kWh)")
price_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

canvas_before = tk.Canvas(before_frame, width=700, height=220, bg="white")
canvas_before.grid(row=0, column=0, sticky="nsew")
before_frame.rowconfigure(0, weight=1)
before_frame.columnconfigure(0, weight=1)

canvas_after = tk.Canvas(after_frame, width=700, height=220, bg="white")
canvas_after.grid(row=0, column=0, sticky="nsew")
after_frame.rowconfigure(0, weight=1)
after_frame.columnconfigure(0, weight=1)

canvas_combined = tk.Canvas(combined_frame, width=700, height=220, bg="white")
canvas_combined.grid(row=0, column=0, sticky="nsew")
combined_frame.rowconfigure(0, weight=1)
combined_frame.columnconfigure(0, weight=1)

canvas_price = tk.Canvas(price_frame, width=500, height=220, bg="white")
canvas_price.grid(row=0, column=0, sticky="nsew")
price_frame.rowconfigure(0, weight=1)
price_frame.columnconfigure(0, weight=1)


# ---- Drawing helpers ----

def get_y_scaling_params(h, margin):
    max_val_data = max(max(before_load), max(after_load))
    if max_val_data <= 0:
        max_tick = 25
    else:
        max_tick = max(25, 25 * math.ceil(max_val_data / 25.0))
    usable_height = h - 2 * margin
    return max_tick, usable_height


def draw_single_graph(canvas, load, title):
    canvas.delete("all")
    w = int(canvas["width"])
    h = int(canvas["height"])
    margin = 40

    max_tick, usable_height = get_y_scaling_params(h, margin)

    # Axes
    canvas.create_line(margin, h - margin, w - margin, h - margin)
    canvas.create_line(margin, margin, margin, h - margin)

    # Title
    canvas.create_text(w / 2, margin / 2, text=title, font=("Arial", 11, "bold"))

    # X axis: 0..24 (24 same value as 0)
    x_span = w - 2 * margin
    n_x_steps = 24
    x_step = x_span / n_x_steps

    for hour_label in range(0, 25):  # 0..24
        x = margin + hour_label * x_step
        canvas.create_line(x, h - margin, x, h - margin + 5)
        canvas.create_text(x, h - margin + 15, text=str(hour_label), font=("Arial", 8))

    # Y labels (0,25,50,...)
    for y_val in range(0, max_tick + 1, 25):
        y = h - margin - (y_val / max_tick) * usable_height
        canvas.create_line(margin - 5, y, margin, y)
        canvas.create_text(margin - 30, y, text=str(y_val), font=("Arial", 8))

    def to_point(k, value):
        x = margin + k * x_step
        y = h - margin - (value / max_tick) * usable_height
        return x, y

    pts = []
    for k in range(0, 25):
        idx = k % NUM_HOURS
        pts.extend(to_point(k, load[idx]))
    canvas.create_line(*pts, fill="blue", width=2)


def draw_combined_graph():
    canvas = canvas_combined
    canvas.delete("all")
    w = int(canvas["width"])
    h = int(canvas["height"])
    margin = 40

    max_tick, usable_height = get_y_scaling_params(h, margin)

    # Axes
    canvas.create_line(margin, h - margin, w - margin, h - margin)
    canvas.create_line(margin, margin, margin, h - margin)

    # Title
    canvas.create_text(
        w / 2,
        margin / 2,
        text="Comparison",
        font=("Arial", 11, "bold")
    )

    x_span = w - 2 * margin
    n_x_steps = 24
    x_step = x_span / n_x_steps

    for hour_label in range(0, 25):
        x = margin + hour_label * x_step
        canvas.create_line(x, h - margin, x, h - margin + 5)
        canvas.create_text(x, h - margin + 15, text=str(hour_label), font=("Arial", 8))

    for y_val in range(0, max_tick + 1, 25):
        y = h - margin - (y_val / max_tick) * usable_height
        canvas.create_line(margin - 5, y, margin, y)
        canvas.create_text(margin - 30, y, text=str(y_val), font=("Arial", 8))

    def to_point(k, value):
        x = margin + k * x_step
        y = h - margin - (value / max_tick) * usable_height
        return x, y

    # BEFORE
    pts_before = []
    for k in range(0, 25):
        idx = k % NUM_HOURS
        pts_before.extend(to_point(k, before_load[idx]))
    canvas.create_line(*pts_before, fill="blue", width=2)

    # AFTER
    pts_after = []
    for k in range(0, 25):
        idx = k % NUM_HOURS
        pts_after.extend(to_point(k, after_load[idx]))
    canvas.create_line(*pts_after, fill="red", width=2, dash=(4, 2))

    # Legend (top-right, outside)
    legend_y1 = margin / 2
    legend_y2 = legend_y1 + 20
    legend_x_line = w - 200
    legend_x_text = legend_x_line + 40

    canvas.create_line(
        legend_x_line, legend_y1, legend_x_line + 30, legend_y1,
        fill="blue", width=2
    )
    canvas.create_text(
        legend_x_text, legend_y1, text="Before", anchor="w", font=("Arial", 9)
    )

    canvas.create_line(
        legend_x_line, legend_y2, legend_x_line + 30, legend_y2,
        fill="red", width=2, dash=(4, 2)
    )
    canvas.create_text(
        legend_x_text, legend_y2, text="After", anchor="w", font=("Arial", 9)
    )


def draw_price_graph():
    canvas = canvas_price
    canvas.delete("all")
    w = int(canvas["width"])
    h = int(canvas["height"])
    margin = 40

    min_price_scale = 0.0
    max_price_scale = 25.0
    price_range = max_price_scale - min_price_scale

    canvas.create_line(margin, h - margin, w - margin, h - margin)
    canvas.create_line(margin, margin, margin, h - margin)

    canvas.create_text(
        w / 2,
        margin / 2,
        text="Price (cents/kWh)",
        font=("Arial", 11, "bold")
    )

    x_span = w - 2 * margin
    n_x_steps = 24
    x_step = x_span / n_x_steps

    for hour_label in range(0, 25):
        x = margin + hour_label * x_step
        canvas.create_line(x, h - margin, x, h - margin + 5)
        canvas.create_text(x, h - margin + 15, text=str(hour_label), font=("Arial", 8))

    usable_height = h - 2 * margin
    for price_val in range(0, 26, 5):
        frac = (price_val - min_price_scale) / price_range
        y = h - margin - frac * usable_height
        canvas.create_line(margin - 5, y, margin, y)
        canvas.create_text(
            margin - 10, y,
            text=str(price_val),
            font=("Arial", 8),
            anchor="e"
        )

    def to_point_price(k, price_value):
        pv = max(min_price_scale, min(max_price_scale, price_value))
        norm = (pv - min_price_scale) / price_range
        x = margin + k * x_step
        y = h - margin - norm * usable_height
        return x, y

    pts_price = []
    for k in range(0, 25):
        idx = k % NUM_HOURS
        pts_price.extend(to_point_price(k, PRICE_PER_HOUR[idx]))
    canvas.create_line(*pts_price, fill="gray", width=2)


def draw_graphs():
    draw_single_graph(canvas_before, before_load, "Total demand BEFORE flexibility")
    draw_single_graph(canvas_after, after_load, "Total demand AFTER flexibility")
    draw_combined_graph()
    draw_price_graph()


def update_stats_and_graph():
    peak_b = max(before_load)
    peak_a = max(after_load)
    reduction = peak_b - peak_a
    reduction_pct = (reduction / peak_b * 100) if peak_b > 0 else 0.0

    peak_before_var.set(f"{peak_b:.1f} units")
    peak_after_var.set(f"{peak_a:.1f} units")
    reduction_var.set(f"{reduction:.1f} units ({reduction_pct:.1f}%)")

    cost_b_eur = cost_before_flex / 100.0
    cost_a_eur = cost_after_flex / 100.0
    saving_eur = cost_b_eur - cost_a_eur
    saving_pct = (saving_eur / cost_b_eur * 100) if cost_b_eur > 0 else 0.0

    cost_before_var.set(f"{cost_b_eur:.2f} €")
    cost_after_var.set(f"{cost_a_eur:.2f} €")
    saving_cost_var.set(f"{saving_eur:.2f} € ({saving_pct:.1f}%)")

    # CO2: loads in "units" ~ MW, CO2_PER_HOUR in tCO2/MWh
    emissions_before_t_day = 0.0
    emissions_after_t_day = 0.0
    for h in range(NUM_HOURS):
        emissions_before_t_day += before_load[h] * CO2_PER_HOUR[h]
        emissions_after_t_day += after_load[h] * CO2_PER_HOUR[h]

    saving_t_day = emissions_before_t_day - emissions_after_t_day
    saving_pct_co2 = (
        saving_t_day / emissions_before_t_day * 100
        if emissions_before_t_day > 0 else 0.0
    )

    saving_t_year = saving_t_day * 365.0
    co2_var.set(
        f"{saving_t_day:.2f} tCO₂/day ({saving_pct_co2:.1f}%) "
        f"≈ {saving_t_year:.0f} tCO₂/year"
    )

    draw_graphs()


# Init with Baseline scenario
apply_scenario("Baseline")
scenario_var.set("Baseline")

update_asset_listbox()

root.mainloop()
