# logic.py
from dataclasses import dataclass
from typing import List, Dict, Tuple

from database import (
    Asset, Scenario, PRICE_PER_HOUR,
    get_scenarios, initial_assets
)

NUM_HOURS = 24


@dataclass
class Stats:
    peak_before: float
    peak_after: float
    peak_reduction: float
    peak_reduction_pct: float
    cost_before_eur: float
    cost_after_eur: float
    cost_saving_eur: float
    cost_saving_pct: float
    co2_saving_day: float
    co2_saving_pct: float
    co2_saving_year: float


class Simulator:
    def __init__(self):
        self.scenarios: Dict[str, Scenario] = get_scenarios()
        self.current_scenario: Scenario = self.scenarios["Baseline"]

        self.assets: List[Asset] = initial_assets()
        # store unscaled reference power
        self.base_power: Dict[int, float] = {i: a.power_kw for i, a in enumerate(self.assets)}

        self.before_load: List[float] = self.current_scenario.base_load[:]
        self.after_load: List[float] = self.current_scenario.base_load[:]

        self.flex_participation: float = 1.0      # 0..1
        self.price_weight: float = 0.5            # 0..1

        self.cost_before_cents: float = 0.0
        self.cost_after_cents: float = 0.0

        self.recalculate()

    # ------------ helpers ------------

    @staticmethod
    def get_window_hours(start: int, end: int) -> List[int]:
        if start < end:
            return list(range(start, end))
        else:
            # wrap over midnight
            return list(range(start, NUM_HOURS)) + list(range(0, end))

    def apply_scenario(self, name: str):
        self.current_scenario = self.scenarios[name]
        # scale assets according to scenario
        for i, a in enumerate(self.assets):
            base = self.base_power[i]
            factor = 1.0
            if "EV" in a.appliance:
                factor *= self.current_scenario.scaling_factors.get("EV", 1.0)
            if "HVAC" in a.appliance or "Heat" in a.appliance:
                factor *= self.current_scenario.scaling_factors.get("HVAC", 1.0)
            if "Battery" in a.appliance:
                factor *= self.current_scenario.scaling_factors.get("Battery", 1.0)
            if "Sauna" in a.appliance:
                factor *= self.current_scenario.scaling_factors.get("Sauna", 1.0)
            a.power_kw = base * factor

        self.recalculate()

    # ------------ core math ------------

    def recalculate(self):
        """Rebuild before/after curves, costs, etc."""
        self._build_before_curve()
        self._build_after_curve()

    def _build_before_curve(self):
        # reset
        self.before_load = self.current_scenario.base_load[:]
        for a in self.assets:
            a.before_hours = []
            if not a.enabled:
                continue

            window = self.get_window_hours(a.start_hour, a.end_hour)
            if not window:
                continue

            duration = min(a.duration_h, len(window))
            hours = window[:duration]
            a.before_hours = hours

            for h in hours:
                self.before_load[h] += a.power_kw

        # cost BEFORE (flex loads only, simplified)
        self.cost_before_cents = 0.0
        for a in self.assets:
            if not a.enabled:
                continue
            for h in a.before_hours:
                self.cost_before_cents += a.power_kw * PRICE_PER_HOUR[h]

    def _build_after_curve(self):
        """Apply flex participation + grid/price score and rebuild after_curve."""
        self.after_load = self.before_load[:]  # start from naive
        self.cost_after_cents = 0.0

        p_flex = self.flex_participation
        w_price = self.price_weight
        w_grid = 1.0 - w_price

        # clear after_hours
        for a in self.assets:
            a.after_hours = []

        # sort big assets first
        enabled_assets = [a for a in self.assets if a.enabled]
        enabled_assets.sort(key=lambda x: -x.power_kw)

        # place each asset
        for a in enabled_assets:
            power_full = a.power_kw
            if power_full <= 0 or not a.before_hours:
                continue

            participate_power = power_full * p_flex
            remain_power = power_full * (1.0 - p_flex)

            window = self.get_window_hours(a.start_hour, a.end_hour)
            if not window:
                a.after_hours = a.before_hours[:]
                continue

            duration = min(a.duration_h, len(window))

            # remove participating part from previous hours
            for h in a.before_hours:
                self.after_load[h] -= participate_power

            # score each hour in window based on current after_load + price
            loads = [self.after_load[h] for h in window]
            prices = [PRICE_PER_HOUR[h] for h in window]
            Lmin, Lmax = min(loads), max(loads)
            Pmin, Pmax = min(prices), max(prices)

            def norm(val, lo, hi):
                if hi > lo:
                    return (val - lo) / (hi - lo)
                return 0.0

            scores: Dict[int, float] = {}
            for h in window:
                l_norm = norm(self.after_load[h], Lmin, Lmax)
                p_norm = norm(PRICE_PER_HOUR[h], Pmin, Pmax)
                scores[h] = w_grid * l_norm + w_price * p_norm

            chosen: List[int] = []
            if a.variable:
                # take best individual hours
                available = window.copy()
                for _ in range(duration):
                    if not available:
                        break
                    best = min(available, key=lambda hh: scores[hh])
                    chosen.append(best)
                    available.remove(best)
            else:
                # best continuous block
                if duration > len(window):
                    duration = len(window)
                best_block = None
                best_score = None
                for i in range(len(window) - duration + 1):
                    block = window[i:i+duration]
                    s = sum(scores[h] for h in block)
                    if best_score is None or s < best_score:
                        best_score = s
                        best_block = block
                if best_block:
                    chosen = best_block

            # add participating part to chosen hours
            for h in chosen:
                self.after_load[h] += participate_power

            a.after_hours = chosen

            # cost for this asset (simplified: before+after, cents)
            for h in a.before_hours:
                self.cost_after_cents += remain_power * PRICE_PER_HOUR[h]
            for h in a.after_hours:
                self.cost_after_cents += participate_power * PRICE_PER_HOUR[h]

    # ------------ public API ------------

    def set_flex_participation(self, pct: float):
        self.flex_participation = max(0.0, min(1.0, pct))
        self.recalculate()

    def set_price_weight(self, pct: float):
        self.price_weight = max(0.0, min(1.0, pct))
        self.recalculate()

    def compute_stats(self) -> Stats:
        peak_before = max(self.before_load)
        peak_after = max(self.after_load)
        red = peak_before - peak_after
        red_pct = (red / peak_before * 100) if peak_before > 0 else 0.0

        cb_eur = self.cost_before_cents / 100.0
        ca_eur = self.cost_after_cents / 100.0
        saving_eur = cb_eur - ca_eur
        saving_pct = (saving_eur / cb_eur * 100) if cb_eur > 0 else 0.0

        # CO2
        co2_before = 0.0
        co2_after = 0.0
        co2_curve = self.current_scenario.co2_per_hour
        for h in range(NUM_HOURS):
            co2_before += self.before_load[h] * co2_curve[h]
            co2_after += self.after_load[h] * co2_curve[h]
        co2_saving_day = co2_before - co2_after
        co2_saving_pct = (co2_saving_day / co2_before * 100) if co2_before > 0 else 0.0
        co2_saving_year = co2_saving_day * 365.0

        return Stats(
            peak_before, peak_after, red, red_pct,
            cb_eur, ca_eur, saving_eur, saving_pct,
            co2_saving_day, co2_saving_pct, co2_saving_year
        )
