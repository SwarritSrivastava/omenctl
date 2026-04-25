import os
import re
import customtkinter as ctk
from tkinter import colorchooser

# --- Hardware Interface ---
class OmenDevice:
    RGB_PATH = "/sys/devices/platform/omen-rgb-keyboard/rgb_zones"
    FAN_PATH = "/sys/class/hwmon/hwmon5"

    # Modes that generate their own colors — changing user color is meaningless
    SELF_COLORED_MODES = {"rainbow", "candle", "aurora", "disco"}
    # Modes that USE the user's color — changing color should NOT kill the animation
    USER_COLORED_MODES = {"breathing", "wave", "pulse", "chase", "sparkle", "gradient"}

    def _read_sysfs(self, node):
        if node in ["all", "brightness", "animation_mode", "animation_speed"] or node.startswith("zone"):
            path = f"{self.RGB_PATH}/{node}"
        else:
            path = f"{self.FAN_PATH}/{node}"
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except Exception:
            return None

    def _write_sysfs(self, node, value):
        if node in ["all", "brightness", "animation_mode", "animation_speed",
                     "gradient_config", "mute_led", "mute_state"] or node.startswith("zone"):
            path = f"{self.RGB_PATH}/{node}"
        else:
            path = f"{self.FAN_PATH}/{node}"
        try:
            with open(path, 'w') as f:
                f.write(str(value))
        except Exception as e:
            print(f"sysfs write error [{path}]: {e}")

    def get_current_mode(self):
        return self._read_sysfs("animation_mode") or "static"

    def set_color(self, hex_color, zone="all"):
        hex_color = hex_color.replace("#", "").upper()
        if not re.match(r'^[0-9A-F]{6}$', hex_color):
            return

        current_mode = self.get_current_mode()

        if current_mode in self.SELF_COLORED_MODES:
            # These modes own their colors; setting a color implies switching
            # back to static first so the user sees their color.
            self._write_sysfs("animation_mode", "static")

        # Write the color — the kernel driver will apply it without
        # touching the animation timer for user-colored modes.
        self._write_sysfs(zone, hex_color)


# --- Preset color palette shared across sections ---
PRESETS = [
    ("Red",    "FF0000"), ("Green",  "00FF00"), ("Blue",   "0000FF"),
    ("White",  "FFFFFF"), ("Purple", "800080"), ("Orange", "FF8000"),
    ("Cyan",   "00FFFF"), ("Pink",   "FF69B4"), ("Yellow", "FFFF00"),
]
LIGHT_TEXT_NAMES = {"White", "Green", "Cyan", "Yellow"}


# --- UI ---
class OmenControlPanel(ctk.CTk):
    # Color palette — dark, matte, Linux-terminal inspired
    BG           = "#0e0e12"
    SURFACE      = "#17171d"
    SURFACE_ALT  = "#1e1e26"
    BORDER       = "#2a2a36"
    ACCENT       = "#c33c54"      # OMEN red
    ACCENT_HOVER = "#e0475f"
    TEXT         = "#e0e0e8"
    TEXT_DIM     = "#7a7a8c"

    MONO = "monospace"

    def __init__(self):
        super().__init__()
        self.dev = OmenDevice()
        self.current_color = "FF0000"
        self.zone_colors = ["FF0000"] * 4  # track per-zone colors
        self._loading = False  # guard: True while syncing UI from hw

        # --- Window ---
        self.title("OMEN RGB & FAN Control")
        self.geometry("560x820")
        self.minsize(420, 500)
        self.configure(fg_color=self.BG)
        ctk.set_appearance_mode("dark")

        # Make root expand properly
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Scrollable container ---
        self.container = ctk.CTkScrollableFrame(
            self, fg_color=self.BG,
            scrollbar_button_color=self.BORDER,
            scrollbar_button_hover_color=self.ACCENT
        )
        self.container.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_header()
        self._build_color_section()
        self._build_brightness_section()
        self._build_animation_section()
        self._build_zone_section()
        self._build_fan_section()
        self._build_footer()

        # Sync UI with current hardware state (no writes)
        self._fetch_hw_state()

    # ── helpers ───────────────────────────────────────────────
    def _section(self, parent, title, icon=""):
        frame = ctk.CTkFrame(parent, fg_color=self.SURFACE, corner_radius=12,
                             border_width=1, border_color=self.BORDER)
        frame.pack(fill="x", padx=16, pady=(0, 10))

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(header, text=f"{icon}  {title}",
                     font=ctk.CTkFont(family=self.MONO, size=13, weight="bold"),
                     text_color=self.TEXT).pack(anchor="w")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(0, 14))
        return body

    # ── header ────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self.container, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(18, 6))

        title_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frame.pack(anchor="w")

        ctk.CTkLabel(
            title_frame, text="◆ OMEN",
            font=ctk.CTkFont(family=self.MONO, size=22, weight="bold"),
            text_color=self.ACCENT
        ).pack(side="left")
        ctk.CTkLabel(
            title_frame, text=" RGB Control",
            font=ctk.CTkFont(family=self.MONO, size=22),
            text_color=self.TEXT
        ).pack(side="left")

        ctk.CTkLabel(
            hdr, text="Linux kernel driver interface  ·  4-zone RGB",
            font=ctk.CTkFont(family=self.MONO, size=11),
            text_color=self.TEXT_DIM
        ).pack(anchor="w", pady=(2, 0))

        # Thin accent line
        line = ctk.CTkFrame(self.container, fg_color=self.ACCENT, height=2, corner_radius=1)
        line.pack(fill="x", padx=16, pady=(4, 12))

    # ── color section (all-zone) ──────────────────────────────
    def _build_color_section(self):
        body = self._section(self.container, "ALL-ZONE COLOR", "●")

        # Preset grid
        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x", pady=(4, 8))

        for i, (name, hx) in enumerate(PRESETS):
            fg = f"#{hx}"
            tc = "#000000" if name in LIGHT_TEXT_NAMES else "#FFFFFF"
            btn = ctk.CTkButton(
                grid, text=name, height=30, corner_radius=6,
                fg_color=fg, hover_color=fg,
                text_color=tc,
                font=ctk.CTkFont(family=self.MONO, size=10),
                command=lambda h=hx: self._apply_all_color(h)
            )
            btn.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="ew")

        for c in range(3):
            grid.columnconfigure(c, weight=1)

        # Custom hex + picker row
        hex_row = ctk.CTkFrame(body, fg_color="transparent")
        hex_row.pack(fill="x", pady=(0, 4))

        self.entry_hex = ctk.CTkEntry(
            hex_row, placeholder_text="Hex (e.g. 00FFCC)", height=32,
            corner_radius=6, fg_color=self.SURFACE_ALT,
            border_color=self.BORDER, border_width=1,
            text_color=self.TEXT,
            font=ctk.CTkFont(family=self.MONO, size=12)
        )
        self.entry_hex.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            hex_row, text="Apply", width=64, height=32, corner_radius=6,
            fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER,
            font=ctk.CTkFont(family=self.MONO, size=11, weight="bold"),
            command=lambda: self._apply_all_color(self.entry_hex.get())
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            hex_row, text="⊙", width=36, height=32, corner_radius=6,
            fg_color=self.SURFACE_ALT, hover_color=self.BORDER,
            border_width=1, border_color=self.BORDER,
            font=ctk.CTkFont(size=14),
            command=self._open_all_color_picker
        ).pack(side="left")

        # Color preview swatch
        self.color_preview = ctk.CTkFrame(
            body, height=8, corner_radius=4,
            fg_color=f"#{self.current_color}"
        )
        self.color_preview.pack(fill="x", pady=(2, 0))

    def _apply_all_color(self, hex_val):
        hex_val = hex_val.replace("#", "").upper()
        if not re.match(r'^[0-9A-F]{6}$', hex_val):
            return
        self.current_color = hex_val
        self.color_preview.configure(fg_color=f"#{hex_val}")
        self.dev.set_color(hex_val)

    def _open_all_color_picker(self):
        color = colorchooser.askcolor(
            initialcolor=f"#{self.current_color}",
            title="Pick a color — All Zones"
        )
        if color and color[1]:
            self._apply_all_color(color[1])

    # ── brightness ────────────────────────────────────────────
    def _build_brightness_section(self):
        body = self._section(self.container, "BRIGHTNESS", "◐")

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))

        self.lbl_bright = ctk.CTkLabel(
            row, text="50 %",
            font=ctk.CTkFont(family=self.MONO, size=12, weight="bold"),
            text_color=self.ACCENT, width=50
        )
        self.lbl_bright.pack(side="right")

        self.slider_bright = ctk.CTkSlider(
            row, from_=0, to=100, number_of_steps=100,
            button_color=self.ACCENT, button_hover_color=self.ACCENT_HOVER,
            progress_color=self.ACCENT,
            fg_color=self.BORDER,
            command=self._on_brightness
        )
        self.slider_bright.set(50)
        self.slider_bright.pack(side="left", fill="x", expand=True, padx=(0, 10))

    def _on_brightness(self, val):
        v = int(val)
        self.lbl_bright.configure(text=f"{v} %")
        if not self._loading:
            self.dev._write_sysfs("brightness", v)

    # ── animation ─────────────────────────────────────────────
    def _build_animation_section(self):
        body = self._section(self.container, "ANIMATION", "▶")

        modes = [
            "static", "breathing", "rainbow", "wave", "pulse",
            "chase", "sparkle", "candle", "aurora", "disco", "gradient"
        ]

        ctk.CTkLabel(
            body, text="Mode",
            font=ctk.CTkFont(family=self.MONO, size=11),
            text_color=self.TEXT_DIM
        ).pack(anchor="w", pady=(4, 2))

        self.dropdown_anim = ctk.CTkOptionMenu(
            body, values=modes, command=self._on_animation,
            fg_color=self.SURFACE_ALT, button_color=self.BORDER,
            button_hover_color=self.ACCENT,
            dropdown_fg_color=self.SURFACE,
            dropdown_hover_color=self.ACCENT,
            dropdown_text_color=self.TEXT,
            text_color=self.TEXT,
            font=ctk.CTkFont(family=self.MONO, size=12),
            corner_radius=6
        )
        self.dropdown_anim.pack(fill="x", pady=(0, 8))

        # Speed
        ctk.CTkLabel(
            body, text="Speed",
            font=ctk.CTkFont(family=self.MONO, size=11),
            text_color=self.TEXT_DIM
        ).pack(anchor="w", pady=(0, 2))

        speed_row = ctk.CTkFrame(body, fg_color="transparent")
        speed_row.pack(fill="x")

        self.lbl_speed = ctk.CTkLabel(
            speed_row, text="5",
            font=ctk.CTkFont(family=self.MONO, size=12, weight="bold"),
            text_color=self.ACCENT, width=30
        )
        self.lbl_speed.pack(side="right")

        self.slider_speed = ctk.CTkSlider(
            speed_row, from_=1, to=10, number_of_steps=9,
            button_color=self.ACCENT, button_hover_color=self.ACCENT_HOVER,
            progress_color=self.ACCENT,
            fg_color=self.BORDER,
            command=self._on_speed
        )
        self.slider_speed.set(5)
        self.slider_speed.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Mode info label
        self.lbl_mode_info = ctk.CTkLabel(
            body, text="",
            font=ctk.CTkFont(family=self.MONO, size=10),
            text_color=self.TEXT_DIM, justify="left"
        )
        self.lbl_mode_info.pack(anchor="w", fill="x", pady=(6, 0))

    def _on_animation(self, mode):
        if not self._loading:
            self.dev._write_sysfs("animation_mode", mode)
        info_map = {
            "static":    "No animation — static colors.",
            "breathing": "Smooth fade in/out using your set color.",
            "rainbow":   "Cycles through all colors automatically.",
            "wave":      "Wave moves across zones using your color.",
            "pulse":     "Pulsing intensity using your set color.",
            "chase":     "Lights chase across zones using your color.",
            "sparkle":   "Random white flashes over your base color.",
            "candle":    "Warm orange/red flickering (own colors).",
            "aurora":    "Green/blue flowing waves (own colors).",
            "disco":     "Multi-colored strobe flashes (own colors).",
            "gradient":  "Custom color cycling — configure via gradient_config.",
        }
        self.lbl_mode_info.configure(text=info_map.get(mode, ""))

    def _on_speed(self, val):
        v = int(val)
        self.lbl_speed.configure(text=str(v))
        if not self._loading:
            self.dev._write_sysfs("animation_speed", v)

    # ── per-zone control ──────────────────────────────────────
    def _build_zone_section(self):
        body = self._section(self.container, "PER-ZONE COLOR", "⊞")

        zone_names = ["Zone 0 — Right", "Zone 1 — Mid", "Zone 2 — Left", "Zone 3 — WASD"]
        self.zone_entries = []
        self.zone_swatches = []

        for i, name in enumerate(zone_names):
            zone_id = f"zone0{i}"

            # --- Zone card ---
            card = ctk.CTkFrame(body, fg_color=self.SURFACE_ALT, corner_radius=8,
                                border_width=1, border_color=self.BORDER)
            card.pack(fill="x", pady=(0, 8))

            # Title row with swatch
            title_row = ctk.CTkFrame(card, fg_color="transparent")
            title_row.pack(fill="x", padx=10, pady=(8, 4))

            swatch = ctk.CTkFrame(title_row, width=14, height=14, corner_radius=3,
                                  fg_color=f"#{self.zone_colors[i]}")
            swatch.pack(side="left", padx=(0, 8))
            swatch.pack_propagate(False)
            self.zone_swatches.append(swatch)

            ctk.CTkLabel(
                title_row, text=name,
                font=ctk.CTkFont(family=self.MONO, size=11, weight="bold"),
                text_color=self.TEXT
            ).pack(side="left")

            # Preset color buttons (compact row)
            preset_row = ctk.CTkFrame(card, fg_color="transparent")
            preset_row.pack(fill="x", padx=10, pady=(0, 4))

            for j, (pname, phx) in enumerate(PRESETS):
                fg = f"#{phx}"
                btn = ctk.CTkButton(
                    preset_row, text="", width=22, height=18, corner_radius=4,
                    fg_color=fg, hover_color=fg,
                    border_width=1, border_color=self.BORDER,
                    command=lambda h=phx, z=zone_id, idx=i: self._set_zone_color(h, z, idx)
                )
                btn.pack(side="left", padx=1)

            # Hex entry + Apply + Picker
            input_row = ctk.CTkFrame(card, fg_color="transparent")
            input_row.pack(fill="x", padx=10, pady=(0, 8))

            entry = ctk.CTkEntry(
                input_row, placeholder_text="RRGGBB", height=28,
                corner_radius=6, fg_color=self.BG,
                border_color=self.BORDER, border_width=1,
                text_color=self.TEXT,
                font=ctk.CTkFont(family=self.MONO, size=11)
            )
            entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
            self.zone_entries.append(entry)

            ctk.CTkButton(
                input_row, text="Set", width=40, height=28, corner_radius=6,
                fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER,
                font=ctk.CTkFont(family=self.MONO, size=10, weight="bold"),
                command=lambda e=entry, z=zone_id, idx=i: self._set_zone_color(e.get(), z, idx)
            ).pack(side="left", padx=(0, 4))

            ctk.CTkButton(
                input_row, text="⊙", width=30, height=28, corner_radius=6,
                fg_color=self.BG, hover_color=self.BORDER,
                border_width=1, border_color=self.BORDER,
                font=ctk.CTkFont(size=13),
                command=lambda z=zone_id, idx=i: self._open_zone_picker(z, idx)
            ).pack(side="left")

    def _set_zone_color(self, hex_val, zone_id, zone_idx):
        hex_val = hex_val.replace("#", "").upper()
        if not re.match(r'^[0-9A-F]{6}$', hex_val):
            return
        self.zone_colors[zone_idx] = hex_val
        self.zone_swatches[zone_idx].configure(fg_color=f"#{hex_val}")
        self.dev.set_color(hex_val, zone_id)

    def _open_zone_picker(self, zone_id, zone_idx):
        color = colorchooser.askcolor(
            initialcolor=f"#{self.zone_colors[zone_idx]}",
            title=f"Pick color — {zone_id}"
        )
        if color and color[1]:
            self._set_zone_color(color[1], zone_id, zone_idx)

    # ── fan profile ───────────────────────────────────────────
    def _build_fan_section(self):
        body = self._section(self.container, "FAN PROFILE", "⛭")

        # Profile description
        self.lbl_fan_info = ctk.CTkLabel(
            body, text="Auto — EC-managed fan curve",
            font=ctk.CTkFont(family=self.MONO, size=10),
            text_color=self.TEXT_DIM
        )
        self.lbl_fan_info.pack(anchor="w", pady=(2, 6))

        self.seg_fans = ctk.CTkSegmentedButton(
            body, values=["Auto", "Max"],
            command=self._on_fan,
            font=ctk.CTkFont(family=self.MONO, size=12),
            selected_color=self.ACCENT,
            selected_hover_color=self.ACCENT_HOVER,
            unselected_color=self.SURFACE_ALT,
            unselected_hover_color=self.BORDER,
            text_color=self.TEXT, corner_radius=6
        )
        self.seg_fans.set("Auto")
        self.seg_fans.pack(fill="x", pady=(0, 8))

        # Live RPM display
        rpm_frame = ctk.CTkFrame(body, fg_color=self.BG, corner_radius=8,
                                 border_width=1, border_color=self.BORDER)
        rpm_frame.pack(fill="x")

        fan_labels = [("Fan 1 (CPU)", "fan1_input"), ("Fan 2 (GPU)", "fan2_input")]
        self._rpm_labels = []

        for i, (label, node) in enumerate(fan_labels):
            row = ctk.CTkFrame(rpm_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(8 if i == 0 else 2, 8 if i == len(fan_labels) - 1 else 2))

            ctk.CTkLabel(
                row, text=label,
                font=ctk.CTkFont(family=self.MONO, size=11),
                text_color=self.TEXT_DIM
            ).pack(side="left")

            rpm_lbl = ctk.CTkLabel(
                row, text="— RPM",
                font=ctk.CTkFont(family=self.MONO, size=12, weight="bold"),
                text_color=self.ACCENT
            )
            rpm_lbl.pack(side="right")
            self._rpm_labels.append((rpm_lbl, node))

        # Start the RPM refresh loop
        self._rpm_timer_id = None
        self._refresh_rpm()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _refresh_rpm(self):
        for lbl, node in self._rpm_labels:
            raw = self.dev._read_sysfs(node)
            if raw is not None:
                try:
                    lbl.configure(text=f"{int(raw):,} RPM")
                except ValueError:
                    lbl.configure(text="— RPM")
            else:
                lbl.configure(text="— RPM")
        self._rpm_timer_id = self.after(1000, self._refresh_rpm)

    def _on_close(self):
        if self._rpm_timer_id is not None:
            self.after_cancel(self._rpm_timer_id)
        self.destroy()

    def _on_fan(self, choice):
        fan_info = {
            "Auto": "Auto — EC-managed fan curve",
            "Max": "Max — full speed (loud)",
        }
        self.lbl_fan_info.configure(text=fan_info.get(choice, ""))
        mode_map = {"Max": "0", "Auto": "2"}
        if not self._loading:
            self.dev._write_sysfs("pwm1_enable", mode_map[choice])

    # ── footer ────────────────────────────────────────────────
    def _build_footer(self):
        foot = ctk.CTkFrame(self.container, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(4, 16))

        ctk.CTkLabel(
            foot,
            text="omen-rgb-keyboard  ·  GPL-3.0  ·  sysfs interface",
            font=ctk.CTkFont(family=self.MONO, size=10),
            text_color=self.TEXT_DIM
        ).pack(anchor="center")

    # ── fetch current hardware state on startup ───────────────
    def _fetch_hw_state(self):
        """Read current values from sysfs and populate UI widgets.
        The _loading flag prevents callbacks from writing back."""
        self._loading = True
        try:
            # Brightness
            raw = self.dev._read_sysfs("brightness")
            if raw is not None:
                try:
                    bv = int(raw)
                    bv = max(0, min(100, bv))
                    self.slider_bright.set(bv)
                    self.lbl_bright.configure(text=f"{bv} %")
                except ValueError:
                    pass

            # Animation mode
            mode = self.dev._read_sysfs("animation_mode")
            if mode:
                mode = mode.strip().lower()
                valid_modes = [
                    "static", "breathing", "rainbow", "wave", "pulse",
                    "chase", "sparkle", "candle", "aurora", "disco", "gradient"
                ]
                if mode in valid_modes:
                    self.dropdown_anim.set(mode)
                    # Update the info label too
                    self._on_animation(mode)

            # Animation speed
            raw = self.dev._read_sysfs("animation_speed")
            if raw is not None:
                try:
                    sv = int(raw)
                    sv = max(1, min(10, sv))
                    self.slider_speed.set(sv)
                    self.lbl_speed.configure(text=str(sv))
                except ValueError:
                    pass

            # Per-zone colors
            for i in range(4):
                raw = self.dev._read_sysfs(f"zone0{i}")
                if raw and re.match(r'^[0-9A-Fa-f]{6}$', raw.strip()):
                    hx = raw.strip().upper()
                    self.zone_colors[i] = hx
                    self.zone_swatches[i].configure(fg_color=f"#{hx}")

            # Use zone 0 color as the "all-zone" preview
            if self.zone_colors[0]:
                self.current_color = self.zone_colors[0]
                self.color_preview.configure(fg_color=f"#{self.current_color}")

            # Fan profile
            raw = self.dev._read_sysfs("pwm1_enable")
            if raw is not None:
                profile_map = {"0": "Max", "2": "Auto"}
                profile = profile_map.get(raw.strip(), "Auto")
                self.seg_fans.set(profile)
                self._on_fan(profile)

        except Exception as e:
            print(f"hw state fetch error: {e}")
        finally:
            self._loading = False


if __name__ == "__main__":
    app = OmenControlPanel()
    app.mainloop()