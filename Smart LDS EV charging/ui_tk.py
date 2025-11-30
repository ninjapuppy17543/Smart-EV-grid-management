# ui_tk.py
import tkinter as tk
from tkinter import ttk, messagebox

from logic import Simulator, NUM_HOURS
from database import PRICE_PER_HOUR, Asset


class FlexiCityApp:
    def __init__(self, root: tk.Tk, sim: Simulator):
        self.root = root
        self.sim = sim

        self.root.title("FlexiCity – Peak, Price & CO₂ (modular)")
        self.root.geometry("1450x880")

        # mapping: listbox index -> sim.assets index
        self.asset_index_map = []

        self._build_ui()
        self._refresh_all()

    # ---------------- UI BUILD ----------------

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # LEFT: scenarios + stats + assets + controls + edit form
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        main.columnconfigure(0, weight=0)
        main.rowconfigure(0, weight=1)

        # RIGHT: graphs
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(1, weight=1)

        # ---- Scenario selector ----
        scenario_frame = ttk.LabelFrame(left, text="Scenario")
        scenario_frame.grid(row=0, column=0, sticky="new", pady=(0, 10))

        self.scenario_var = tk.StringVar(value=self.sim.current_scenario.name)
        self.scenario_combo = ttk.Combobox(
            scenario_frame,
            textvariable=self.scenario_var,
            values=list(self.sim.scenarios.keys()),
            state="readonly",
        )
        self.scenario_combo.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        scenario_frame.columnconfigure(0, weight=1)
        self.scenario_combo.bind("<<ComboboxSelected>>", self._on_scenario_change)

        # ---- Stats ----
        stats_frame = ttk.LabelFrame(left, text="Stats")
        stats_frame.grid(row=1, column=0, sticky="new")

        self.peak_before_var = tk.StringVar()
        self.peak_after_var = tk.StringVar()
        self.peak_red_var = tk.StringVar()
        self.cost_before_var = tk.StringVar()
        self.cost_after_var = tk.StringVar()
        self.cost_saving_var = tk.StringVar()
        self.co2_var = tk.StringVar()

        labels = [
            ("Peak BEFORE:", self.peak_before_var),
            ("Peak AFTER:", self.peak_after_var),
            ("Peak reduction:", self.peak_red_var),
            ("Cost BEFORE (flex):", self.cost_before_var),
            ("Cost AFTER (flex):", self.cost_after_var),
            ("Cost saving:", self.cost_saving_var),
            ("CO₂ saving:", self.co2_var),
        ]
        for r, (txt, var) in enumerate(labels):
            ttk.Label(stats_frame, text=txt).grid(row=r, column=0, sticky="w")
            ttk.Label(stats_frame, textvariable=var).grid(row=r, column=1, sticky="w")

        # ---- Assets list ----
        assets_frame = ttk.LabelFrame(left, text="Flexible loads")
        assets_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        left.rowconfigure(2, weight=1)

        self.asset_listbox = tk.Listbox(assets_frame, width=60, height=10)
        self.asset_listbox.grid(row=0, column=0, sticky="nsew")
        assets_frame.rowconfigure(0, weight=1)
        assets_frame.columnconfigure(0, weight=1)

        scroll = ttk.Scrollbar(
            assets_frame, orient="vertical", command=self.asset_listbox.yview
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.asset_listbox.config(yscrollcommand=scroll.set)

        self.asset_listbox.bind("<<ListboxSelect>>", self._on_asset_select)

        self.asset_detail_var = tk.StringVar()
        ttk.Label(
            assets_frame,
            textvariable=self.asset_detail_var,
            wraplength=430,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        # asset buttons
        btn_frame = ttk.Frame(assets_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        assets_frame.rowconfigure(2, weight=0)

        self.btn_toggle = ttk.Button(
            btn_frame, text="Toggle enabled", command=self._on_toggle_asset
        )
        self.btn_toggle.grid(row=0, column=0, padx=(0, 5))

        self.btn_delete = ttk.Button(
            btn_frame, text="Delete asset", command=self._on_delete_asset
        )
        self.btn_delete.grid(row=0, column=1)

        # ---- Controls (sliders) ----
        ctrl_frame = ttk.LabelFrame(left, text="Controls")
        ctrl_frame.grid(row=3, column=0, sticky="new", pady=(10, 0))

        ttk.Label(ctrl_frame, text="Flexible users (%)").grid(
            row=0, column=0, sticky="w"
        )
        self.flex_var = tk.DoubleVar(value=100.0)
        self.flex_scale = ttk.Scale(
            ctrl_frame,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.flex_var,
            command=self._on_flex_change,
        )
        self.flex_scale.grid(row=1, column=0, sticky="ew")
        ctrl_frame.columnconfigure(0, weight=1)

        ttk.Label(
            ctrl_frame, text="Weight on price (0 = grid, 100 = price)"
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.price_weight_var = tk.DoubleVar(value=50.0)
        self.price_scale = ttk.Scale(
            ctrl_frame,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.price_weight_var,
            command=self._on_price_weight_change,
        )
        self.price_scale.grid(row=3, column=0, sticky="ew")

        # ---- Add / Edit Asset form ----
        form_frame = ttk.LabelFrame(left, text="Add / edit flexible load")
        form_frame.grid(row=4, column=0, sticky="new", pady=(10, 0))

        self.form_owner_var = tk.StringVar()
        self.form_appliance_var = tk.StringVar()
        self.form_power_var = tk.StringVar()
        self.form_duration_var = tk.StringVar()
        self.form_start_var = tk.StringVar()
        self.form_end_var = tk.StringVar()
        self.form_variable_var = tk.BooleanVar(value=True)

        ttk.Label(form_frame, text="Owner / Name:").grid(row=0, column=0, sticky="w")
        ttk.Entry(form_frame, textvariable=self.form_owner_var, width=22).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Label(form_frame, text="Appliance:").grid(row=1, column=0, sticky="w")
        ttk.Entry(form_frame, textvariable=self.form_appliance_var, width=22).grid(
            row=1, column=1, sticky="w"
        )

        ttk.Label(form_frame, text="Power (kW):").grid(row=2, column=0, sticky="w")
        ttk.Entry(form_frame, textvariable=self.form_power_var, width=10).grid(
            row=2, column=1, sticky="w"
        )

        ttk.Label(form_frame, text="Duration (h):").grid(row=3, column=0, sticky="w")
        ttk.Entry(form_frame, textvariable=self.form_duration_var, width=10).grid(
            row=3, column=1, sticky="w"
        )

        ttk.Label(form_frame, text="Start hour (0–23):").grid(
            row=4, column=0, sticky="w"
        )
        ttk.Entry(form_frame, textvariable=self.form_start_var, width=10).grid(
            row=4, column=1, sticky="w"
        )

        ttk.Label(form_frame, text="End hour (1–24):").grid(
            row=5, column=0, sticky="w"
        )
        ttk.Entry(form_frame, textvariable=self.form_end_var, width=10).grid(
            row=5, column=1, sticky="w"
        )

        ttk.Checkbutton(
            form_frame,
            text="Variable (can split hours)",
            variable=self.form_variable_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(5, 0))

        form_btn_frame = ttk.Frame(form_frame)
        form_btn_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        self.btn_add_new = ttk.Button(
            form_btn_frame, text="Add as new load", command=self._on_add_asset
        )
        self.btn_add_new.grid(row=0, column=0, padx=(0, 5))

        self.btn_apply_edit = ttk.Button(
            form_btn_frame,
            text="Apply to selected",
            command=self._on_apply_edit_to_selected,
        )
        self.btn_apply_edit.grid(row=0, column=1)

        # ---- Graphs layout ----
        # Right: 3 demand graphs + 1 price graph
        # Row 0: Before (colspan 2)
        # Row 1: After (colspan 2)
        # Row 2: Comparison (col 0), Price (col 1)

        before_frame = ttk.LabelFrame(right, text="Before – total demand")
        before_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 5))

        after_frame = ttk.LabelFrame(right, text="After – with flexibility")
        after_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=5)

        combined_frame = ttk.LabelFrame(right, text="Comparison")
        combined_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0), padx=(0, 5))

        price_frame = ttk.LabelFrame(right, text="Price (cents/kWh)")
        price_frame.grid(row=2, column=1, sticky="nsew", pady=(5, 0))

        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=3)
        right.columnconfigure(1, weight=2)

        self.canvas_before = tk.Canvas(before_frame, bg="white", height=230)
        self.canvas_before.grid(row=0, column=0, sticky="nsew")
        before_frame.rowconfigure(0, weight=1)
        before_frame.columnconfigure(0, weight=1)

        self.canvas_after = tk.Canvas(after_frame, bg="white", height=230)
        self.canvas_after.grid(row=0, column=0, sticky="nsew")
        after_frame.rowconfigure(0, weight=1)
        after_frame.columnconfigure(0, weight=1)

        self.canvas_combined = tk.Canvas(combined_frame, bg="white", height=230)
        self.canvas_combined.grid(row=0, column=0, sticky="nsew")
        combined_frame.rowconfigure(0, weight=1)
        combined_frame.columnconfigure(0, weight=1)

        self.canvas_price = tk.Canvas(price_frame, bg="white", height=230)
        self.canvas_price.grid(row=0, column=0, sticky="nsew")
        price_frame.rowconfigure(0, weight=1)
        price_frame.columnconfigure(0, weight=1)

        # Make graphs redraw on resize
        self.canvas_before.bind("<Configure>", lambda e: self._redraw_graphs())
        self.canvas_after.bind("<Configure>", lambda e: self._redraw_graphs())
        self.canvas_combined.bind("<Configure>", lambda e: self._redraw_graphs())
        self.canvas_price.bind("<Configure>", lambda e: self._draw_price())

    # ---------------- CALLBACKS ----------------

    def _on_scenario_change(self, event=None):
        name = self.scenario_var.get()
        self.sim.apply_scenario(name)
        self._refresh_all()

    def _on_flex_change(self, val):
        self.sim.set_flex_participation(self.flex_var.get() / 100.0)
        self._refresh_all()

    def _on_price_weight_change(self, val):
        self.sim.set_price_weight(self.price_weight_var.get() / 100.0)
        self._refresh_all()

    def _on_asset_select(self, event=None):
        sel = self.asset_listbox.curselection()
        if not sel:
            return
        list_idx = sel[0]
        if list_idx < 0 or list_idx >= len(self.asset_index_map):
            return
        asset_idx = self.asset_index_map[list_idx]
        a = self.sim.assets[asset_idx]

        before_hours = sorted(a.before_hours)
        after_hours = sorted(a.after_hours)

        enabled_str = "Yes" if a.enabled else "No"

        detail = (
            f"{a.owner} – {a.appliance}\n"
            f"Power: {a.power_kw:.1f} kW for {a.duration_h} h\n"
            f"Window: {a.start_hour:02d}–{a.end_hour:02d} h\n"
            f"Variable: {'Yes' if a.variable else 'No'}\n"
            f"Enabled: {enabled_str}\n\n"
            f"BEFORE hours: {before_hours}\n"
            f"AFTER hours:  {after_hours}"
        )
        self.asset_detail_var.set(detail)

        # Populate form for editing
        self.form_owner_var.set(a.owner)
        self.form_appliance_var.set(a.appliance)
        self.form_power_var.set(f"{a.power_kw:.1f}")
        self.form_duration_var.set(str(a.duration_h))
        self.form_start_var.set(str(a.start_hour))
        self.form_end_var.set(str(a.end_hour))
        self.form_variable_var.set(a.variable)

    def _on_toggle_asset(self):
        sel = self.asset_listbox.curselection()
        if not sel:
            messagebox.showinfo("Toggle", "Please select an asset first.")
            return
        list_idx = sel[0]
        asset_idx = self.asset_index_map[list_idx]
        a = self.sim.assets[asset_idx]
        a.enabled = not a.enabled
        self.sim.recalculate()
        self._refresh_all()
        self.asset_listbox.selection_set(list_idx)
        self._on_asset_select()

    def _on_delete_asset(self):
        sel = self.asset_listbox.curselection()
        if not sel:
            messagebox.showinfo("Delete", "Please select an asset to delete.")
            return
        list_idx = sel[0]
        asset_idx = self.asset_index_map[list_idx]
        a = self.sim.assets[asset_idx]

        if not messagebox.askyesno(
            "Delete",
            f"Delete asset:\n\n{a.owner} – {a.appliance}?",
        ):
            return

        del self.sim.assets[asset_idx]
        # rebuild base_power mapping (logic uses it for scenarios)
        self.sim.base_power = {
            i: asset.power_kw for i, asset in enumerate(self.sim.assets)
        }
        self.sim.recalculate()
        self._refresh_all()

    def _read_form_asset(self):
        try:
            owner = self.form_owner_var.get().strip() or "Custom house"
            appliance = self.form_appliance_var.get().strip() or "Appliance"
            power_kw = float(self.form_power_var.get())
            duration_h = int(self.form_duration_var.get())
            start = int(self.form_start_var.get())
            end = int(self.form_end_var.get())
            variable = bool(self.form_variable_var.get())

            if not (0 <= start < 24):
                raise ValueError("Start hour must be between 0 and 23")
            if not (1 <= end <= 24):
                raise ValueError("End hour must be between 1 and 24")
            if len(self._window_hours(start, end)) == 0:
                raise ValueError("Time window is empty or invalid.")
            if duration_h < 1:
                raise ValueError("Duration must be at least 1 hour.")
            if duration_h > len(self._window_hours(start, end)):
                raise ValueError("Duration cannot exceed window length.")

            return owner, appliance, power_kw, duration_h, start, end, variable
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return None

    def _window_hours(self, start: int, end: int):
        if start < end:
            return list(range(start, end))
        else:
            return list(range(start, NUM_HOURS)) + list(range(0, end))

    def _on_add_asset(self):
        data = self._read_form_asset()
        if data is None:
            return
        owner, appliance, power_kw, duration_h, start, end, variable = data

        new_asset = Asset(
            owner=owner,
            appliance=appliance,
            power_kw=power_kw,
            duration_h=duration_h,
            start_hour=start,
            end_hour=end,
            variable=variable,
        )
        self.sim.assets.append(new_asset)
        # base_power reference for scenarios
        self.sim.base_power[len(self.sim.assets) - 1] = power_kw
        self.sim.recalculate()
        self._refresh_all()
        # select the newly added asset
        self.asset_listbox.selection_clear(0, tk.END)
        self.asset_listbox.selection_set(tk.END)
        self._on_asset_select()

    def _on_apply_edit_to_selected(self):
        sel = self.asset_listbox.curselection()
        if not sel:
            messagebox.showinfo("Edit", "Select an asset to apply changes to.")
            return
        list_idx = sel[0]
        asset_idx = self.asset_index_map[list_idx]

        data = self._read_form_asset()
        if data is None:
            return
        owner, appliance, power_kw, duration_h, start, end, variable = data

        a = self.sim.assets[asset_idx]
        a.owner = owner
        a.appliance = appliance
        a.power_kw = power_kw
        a.duration_h = duration_h
        a.start_hour = start
        a.end_hour = end
        a.variable = variable

        self.sim.base_power[asset_idx] = power_kw
        self.sim.recalculate()
        self._refresh_all()
        self.asset_listbox.selection_set(list_idx)
        self._on_asset_select()

    # ---------------- REFRESH & DRAWING ----------------

    def _refresh_all(self):
        self._update_stats()
        self._update_asset_list()
        self._redraw_graphs()
        self._draw_price()

    def _update_stats(self):
        stats = self.sim.compute_stats()
        self.peak_before_var.set(f"{stats.peak_before:.1f} units")
        self.peak_after_var.set(f"{stats.peak_after:.1f} units")
        self.peak_red_var.set(
            f"{stats.peak_reduction:.1f} ({stats.peak_reduction_pct:.1f}%)"
        )
        self.cost_before_var.set(f"{stats.cost_before_eur:.2f} €")
        self.cost_after_var.set(f"{stats.cost_after_eur:.2f} €")
        self.cost_saving_var.set(
            f"{stats.cost_saving_eur:.2f} € ({stats.cost_saving_pct:.1f}%)"
        )
        self.co2_var.set(
            f"{stats.co2_saving_day:.2f} tCO₂/day "
            f"({stats.co2_saving_pct:.1f}%) ≈ {stats.co2_saving_year:.0f} tCO₂/year"
        )

    def _update_asset_list(self):
        self.asset_listbox.delete(0, tk.END)
        self.asset_index_map.clear()

        for idx, a in enumerate(self.sim.assets):
            status = "ON" if a.enabled else "OFF"
            text = (
                f"[{status}] {a.owner} – {a.appliance} | "
                f"{a.power_kw:.1f} kW x {a.duration_h} h | "
                f"{a.start_hour:02d}-{a.end_hour:02d}h | "
                f"{'var' if a.variable else 'fixed'}"
            )
            self.asset_listbox.insert(tk.END, text)
            self.asset_index_map.append(idx)

        if not self.sim.assets:
            self.asset_detail_var.set("")
        # if something is selected, reselect it (helps after refresh)
        if self.asset_listbox.size() > 0:
            self.asset_listbox.selection_set(0)
            self._on_asset_select()

    def _redraw_graphs(self):
        self._draw_curve(self.canvas_before, self.sim.before_load, "Total demand BEFORE")
        self._draw_curve(self.canvas_after, self.sim.after_load, "Total demand AFTER")
        self._draw_combined(self.canvas_combined, self.sim.before_load, self.sim.after_load)

    def _draw_curve(self, canvas: tk.Canvas, load: list, title: str):
        canvas.delete("all")
        w = canvas.winfo_width() or int(canvas["width"])
        h = canvas.winfo_height() or int(canvas["height"])
        margin = 40
        max_val = max(load) * 1.1 if max(load) > 0 else 1.0

        # axes
        canvas.create_line(margin, h - margin, w - margin, h - margin)
        canvas.create_line(margin, margin, margin, h - margin)
        canvas.create_text(w / 2, margin / 2, text=title, font=("Arial", 11, "bold"))

        x_span = w - 2 * margin
        x_step = x_span / 24.0

        # X labels every 3 hours
        for hour in range(0, 25, 3):
            x = margin + hour * x_step
            canvas.create_line(x, h - margin, x, h - margin + 5)
            canvas.create_text(x, h - margin + 15, text=str(hour), font=("Arial", 8))

        # Y labels (0, 50%, 100%)
        for frac in [0.0, 0.5, 1.0]:
            val = max_val * frac
            y = h - margin - frac * (h - 2 * margin)
            canvas.create_line(margin - 5, y, margin, y)
            canvas.create_text(margin - 35, y, text=f"{int(val)}", font=("Arial", 8))

        pts = []
        for k in range(0, 25):  # 0..24
            idx = k % NUM_HOURS
            v = load[idx]
            x = margin + k * x_step
            y = h - margin - (v / max_val) * (h - 2 * margin)
            pts.extend((x, y))
        if pts:
            canvas.create_line(*pts, fill="blue", width=2)

    def _draw_combined(self, canvas: tk.Canvas, before: list, after: list):
        canvas.delete("all")
        w = canvas.winfo_width() or int(canvas["width"])
        h = canvas.winfo_height() or int(canvas["height"])
        margin = 40
        max_val = max(max(before), max(after)) * 1.1 if max(before + after) > 0 else 1.0

        # axes
        canvas.create_line(margin, h - margin, w - margin, h - margin)
        canvas.create_line(margin, margin, margin, h - margin)
        canvas.create_text(w / 2, margin / 2, text="Comparison", font=("Arial", 11, "bold"))

        x_span = w - 2 * margin
        x_step = x_span / 24.0

        for hour in range(0, 25, 3):
            x = margin + hour * x_step
            canvas.create_line(x, h - margin, x, h - margin + 5)
            canvas.create_text(x, h - margin + 15, text=str(hour), font=("Arial", 8))

        for frac in [0.0, 0.5, 1.0]:
            val = max_val * frac
            y = h - margin - frac * (h - 2 * margin)
            canvas.create_line(margin - 5, y, margin, y)
            canvas.create_text(margin - 35, y, text=f"{int(val)}", font=("Arial", 8))

        def pts_for(curve):
            pts = []
            for k in range(0, 25):
                idx = k % NUM_HOURS
                v = curve[idx]
                x = margin + k * x_step
                y = h - margin - (v / max_val) * (h - 2 * margin)
                pts.extend((x, y))
            return pts

        pts_b = pts_for(before)
        pts_a = pts_for(after)

        if pts_b:
            canvas.create_line(*pts_b, fill="blue", width=2)
        if pts_a:
            canvas.create_line(*pts_a, fill="red", width=2, dash=(4, 2))

        # legend in top-right
        ly1 = margin / 2
        ly2 = ly1 + 20
        lx = w - 210
        canvas.create_line(lx, ly1, lx + 30, ly1, fill="blue", width=2)
        canvas.create_text(lx + 40, ly1, text="Before", anchor="w", font=("Arial", 9))
        canvas.create_line(lx, ly2, lx + 30, ly2, fill="red", width=2, dash=(4, 2))
        canvas.create_text(lx + 40, ly2, text="After", anchor="w", font=("Arial", 9))

    def _draw_price(self):
        canvas = self.canvas_price
        canvas.delete("all")
        w = canvas.winfo_width() or int(canvas["width"])
        h = canvas.winfo_height() or int(canvas["height"])
        margin = 40

        min_price_scale = 0.0
        max_price_scale = 25.0
        price_range = max_price_scale - min_price_scale

        # axes
        canvas.create_line(margin, h - margin, w - margin, h - margin)
        canvas.create_line(margin, margin, margin, h - margin)
        canvas.create_text(
            w / 2, margin / 2, text="Price (cents/kWh)", font=("Arial", 11, "bold")
        )

        x_span = w - 2 * margin
        x_step = x_span / 24.0
        usable_height = h - 2 * margin

        # x labels
        for hour in range(0, 25, 3):
            x = margin + hour * x_step
            canvas.create_line(x, h - margin, x, h - margin + 5)
            canvas.create_text(x, h - margin + 15, text=str(hour), font=("Arial", 8))

        # y labels 0..25 by 5
        for price_val in range(0, 26, 5):
            frac = (price_val - min_price_scale) / price_range
            y = h - margin - frac * usable_height
            canvas.create_line(margin - 5, y, margin, y)
            canvas.create_text(
                margin - 10, y, text=str(price_val), font=("Arial", 8), anchor="e"
            )

        def to_point(hour, val):
            pv = max(min_price_scale, min(max_price_scale, val))
            norm = (pv - min_price_scale) / price_range
            x = margin + hour * x_step
            y = h - margin - norm * usable_height
            return x, y

        pts = []
        for k in range(0, 25):
            idx = k % NUM_HOURS
            v = PRICE_PER_HOUR[idx]
            x, y = to_point(k, v)
            pts.extend((x, y))
        if pts:
            canvas.create_line(*pts, width=2)
