import subprocess
import sys
import tkinter as tk
import os
import threading
from pathlib import Path
from tkinter import messagebox, scrolledtext
from tkinter import ttk


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None

        widget.bind("<Enter>", self._on_enter, add=True)
        widget.bind("<Leave>", self._on_leave, add=True)
        widget.bind("<ButtonPress>", self._on_leave, add=True)

    def _on_enter(self, _event=None) -> None:
        self._schedule()

    def _on_leave(self, _event=None) -> None:
        self._unschedule()
        self._hide()

    def _schedule(self) -> None:
        self._unschedule()
        self._after_id = self._widget.after(450, self._show)

    def _unschedule(self) -> None:
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._tip is not None:
            return

        tip = tk.Toplevel(self._widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)

        label = ttk.Label(tip, text=self._text, padding=(8, 6))
        label.pack()

        x = self._widget.winfo_rootx() + 12
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 8
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self) -> None:
        if self._tip is None:
            return
        try:
            self._tip.destroy()
        except Exception:
            pass
        self._tip = None


def add_tooltip(widget: tk.Widget, text: str) -> Tooltip:
    return Tooltip(widget, text)


def run_command_stream(
    window: tk.Tk,
    root: Path,
    args: list[str],
    on_output,
    on_done=None,
) -> None:
    def worker() -> None:
        try:
            proc = subprocess.Popen(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
        except Exception as e:
            window.after(0, lambda: messagebox.showerror("Command failed", str(e)))
            if on_done is not None:
                window.after(0, lambda: on_done(1))
            return

        assert proc.stdout is not None
        for line in proc.stdout:
            window.after(0, lambda l=line: on_output(l))

        code = proc.wait()
        window.after(0, lambda: on_output(f"\n[exit code {code}]\n"))
        if code != 0:
            window.after(0, lambda: messagebox.showerror("Command failed", f"Exit code {code}"))
        if on_done is not None:
            window.after(0, lambda: on_done(code))

    threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    window = tk.Tk()
    window.title("pokeemerald mod GUI")

    style = ttk.Style(window)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    randomize_wild = tk.BooleanVar(value=False)
    randomize_starters = tk.BooleanVar(value=False)
    randomize_trainers = tk.BooleanVar(value=False)
    randomize_per_occurrence = tk.BooleanVar(value=False)
    randomize_per_map = tk.BooleanVar(value=False)

    flag_random_evos = tk.BooleanVar(value=False)
    flag_walk_fast = tk.BooleanVar(value=False)
    flag_instant_text = tk.BooleanVar(value=False)
    flag_skip_transition = tk.BooleanVar(value=False)
    flag_force_doubles = tk.BooleanVar(value=False)
    flag_steal_trainer_team = tk.BooleanVar(value=False)

    wait_time_divisor_pow = tk.DoubleVar(value=0.0)  # 0..5 => 1..32

    output = scrolledtext.ScrolledText(window, height=18, width=100)

    def log(text: str) -> None:
        output.insert("end", text)
        output.see("end")

    def do_restore() -> None:
        def on_restore_done(code: int) -> None:
            if code == 0:
                log("[success] repo files restored from templates\n")

        run_command_stream(
            window,
            repo_root,
            [sys.executable, "randomizer/randomize.py", "--restore"],
            log,
            on_done=on_restore_done,
        )

    def do_build() -> None:
        build_btn.configure(state="disabled")

        # Randomizer is a prerequisite to build.
        rand_args = [sys.executable, "randomizer/randomize.py"]
        if randomize_per_occurrence.get():
            rand_args.append("--per-occurrence")
        if randomize_per_map.get():
            rand_args.append("--per-map-consistent")
        any_selected = randomize_wild.get() or randomize_starters.get() or randomize_trainers.get()
        if not any_selected:
            rand_args.append("--restore")
        else:
            if randomize_wild.get():
                rand_args.append("--wild")
            if randomize_starters.get():
                rand_args.append("--starters")
            if randomize_trainers.get():
                rand_args.append("--trainers")

        make_args = ["make", f"-j{os.cpu_count() or 1}"]

        def add_bool_flag(name: str, enabled: bool) -> None:
            make_args.append(f"{name}={'1' if enabled else '0'}")

        add_bool_flag("RANDOM_EVOLUTIONS", flag_random_evos.get())
        add_bool_flag("WALK_FAST", flag_walk_fast.get())
        add_bool_flag("INSTANT_TEXT", flag_instant_text.get())
        add_bool_flag("SKIP_BATTLE_TRANSITION", flag_skip_transition.get())
        add_bool_flag("FORCE_DOUBLE_BATTLES", flag_force_doubles.get())
        add_bool_flag("STEAL_TRAINER_TEAM", flag_steal_trainer_team.get())

        wtd = 1 << int(round(wait_time_divisor_pow.get()))
        make_args.append(f"WAIT_TIME_DIVISOR={wtd}")

        def after_randomizer(code: int) -> None:
            if code != 0:
                build_btn.configure(state="normal")
                return

            if not any_selected:
                log("[success] repo files restored from templates\n")
            else:
                log("[success] randomizer completed\n")

            def after_make(make_code: int) -> None:
                build_btn.configure(state="normal")
                if make_code == 0:
                    gba_path = repo_root / "pokeemerald.gba"
                    if gba_path.exists():
                        log(f"[success] rom generated: {gba_path.name}\n")
                    else:
                        log("[success] build completed\n")

            run_command_stream(
                window,
                repo_root,
                make_args,
                log,
                on_done=after_make,
            )

        run_command_stream(window, repo_root, rand_args, log, on_done=after_randomizer)

    top = ttk.Frame(window, padding=10)
    top.pack(fill="x", expand=False)
    top.columnconfigure(0, weight=1)
    top.columnconfigure(1, weight=1)

    randomizer_group = ttk.Labelframe(top, text="Randomizer", padding=10)
    randomizer_group.grid(row=0, column=0, sticky="nw")

    wild_cb = ttk.Checkbutton(randomizer_group, text="Wild", variable=randomize_wild)
    wild_cb.grid(row=0, column=0, sticky="w")
    add_tooltip(wild_cb, "Randomize wild encounter species.")

    starters_cb = ttk.Checkbutton(randomizer_group, text="Starters", variable=randomize_starters)
    starters_cb.grid(row=1, column=0, sticky="w")
    add_tooltip(starters_cb, "Randomize starter choices.")

    trainers_cb = ttk.Checkbutton(randomizer_group, text="Trainers", variable=randomize_trainers)
    trainers_cb.grid(row=2, column=0, sticky="w")
    add_tooltip(trainers_cb, "Randomize trainer party species.")

    def sync_randomizer_mode_ui() -> None:
        if randomize_per_occurrence.get():
            randomize_per_map.set(False)
            per_map_cb.state(["disabled"])
        else:
            per_map_cb.state(["!disabled"])

        if randomize_per_map.get():
            randomize_per_occurrence.set(False)
            per_occ_cb.state(["disabled"])
        else:
            per_occ_cb.state(["!disabled"])

    per_occ_cb = ttk.Checkbutton(
        randomizer_group,
        text="Per-occurrence",
        variable=randomize_per_occurrence,
        command=sync_randomizer_mode_ui,
    )
    per_occ_cb.grid(row=3, column=0, sticky="w", pady=(6, 0))
    add_tooltip(per_occ_cb, "Replace every SPECIES_* occurrence independently (more chaotic).")

    per_map_cb = ttk.Checkbutton(
        randomizer_group,
        text="Per-map consistent",
        variable=randomize_per_map,
        command=sync_randomizer_mode_ui,
    )
    per_map_cb.grid(row=4, column=0, sticky="w")
    add_tooltip(per_map_cb, "Wild encounters only: keep replacements consistent within each map.")

    sync_randomizer_mode_ui()

    restore_btn = ttk.Button(randomizer_group, text="Restore repo files", command=do_restore)
    restore_btn.grid(row=5, column=0, sticky="w", pady=(8, 0))
    add_tooltip(restore_btn, "Overwrite the repo's src/ files with the copies in randomizer/ (undo randomization).")

    build_group = ttk.Labelframe(top, text="Build", padding=10)
    build_group.grid(row=0, column=1, sticky="nw", padx=(10, 0))

    random_evos_cb = ttk.Checkbutton(build_group, text="RANDOM_EVOLUTIONS", variable=flag_random_evos)
    random_evos_cb.grid(row=0, column=0, sticky="w")
    add_tooltip(random_evos_cb, "Randomize evolutions (build flag).")

    walk_fast_cb = ttk.Checkbutton(build_group, text="WALK_FAST", variable=flag_walk_fast)
    walk_fast_cb.grid(row=1, column=0, sticky="w")
    add_tooltip(walk_fast_cb, "Increase player walking speed (build flag).")

    instant_text_cb = ttk.Checkbutton(build_group, text="INSTANT_TEXT", variable=flag_instant_text)
    instant_text_cb.grid(row=2, column=0, sticky="w")
    add_tooltip(instant_text_cb, "Make in-game text display instantly (build flag).")

    skip_transition_cb = ttk.Checkbutton(build_group, text="SKIP_BATTLE_TRANSITION", variable=flag_skip_transition)
    skip_transition_cb.grid(row=3, column=0, sticky="w")
    add_tooltip(skip_transition_cb, "Skip the battle transition effect (build flag).")

    force_doubles_cb = ttk.Checkbutton(build_group, text="FORCE_DOUBLE_BATTLES", variable=flag_force_doubles)
    force_doubles_cb.grid(row=4, column=0, sticky="w")
    add_tooltip(force_doubles_cb, "Force double battles everywhere (build flag).")

    steal_team_cb = ttk.Checkbutton(build_group, text="STEAL_TRAINER_TEAM", variable=flag_steal_trainer_team)
    steal_team_cb.grid(row=5, column=0, sticky="w")
    add_tooltip(steal_team_cb, "After winning a trainer battle, replace your party with theirs (build flag).")

    wait_frame = ttk.Frame(build_group)
    wait_frame.grid(row=6, column=0, sticky="w", pady=(8, 0))

    wait_label = ttk.Label(wait_frame, text="WAIT_TIME_DIVISOR")
    wait_label.pack(side="left")
    add_tooltip(wait_label, "Divides various wait/timing delays. Higher = faster.")

    wait_value_label = ttk.Label(wait_frame, text=str(1 << int(round(wait_time_divisor_pow.get()))))
    wait_value_label.pack(side="left", padx=(8, 8))

    def on_wait_slider(_value: str) -> None:
        snapped = int(round(float(_value)))
        if int(round(wait_time_divisor_pow.get())) != snapped:
            wait_time_divisor_pow.set(float(snapped))
        wait_value_label.configure(text=str(1 << snapped))

    wait_scale = ttk.Scale(
        wait_frame,
        from_=0,
        to=5,
        orient="horizontal",
        variable=wait_time_divisor_pow,
        command=on_wait_slider,
        length=160,
    )
    wait_scale.pack(side="left")
    add_tooltip(wait_scale, "Select 1, 2, 4, 8, 16, or 32.")

    build_btn = ttk.Button(build_group, text="Build", command=do_build)
    build_btn.grid(row=7, column=0, sticky="w", pady=(10, 0))
    add_tooltip(build_btn, "Run randomizer (or restore) then build the ROM.")

    output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    window.mainloop()


if __name__ == "__main__":
    main()
