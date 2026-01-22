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
    flag_walk_through_walls = tk.BooleanVar(value=False)
    flag_nuzlocke_delete_fainted = tk.BooleanVar(value=False)
    flag_instant_text = tk.BooleanVar(value=False)
    flag_skip_transition = tk.BooleanVar(value=False)
    flag_skip_fade_anims = tk.BooleanVar(value=False)
    flag_fast_stat_anims = tk.BooleanVar(value=False)
    flag_force_doubles = tk.BooleanVar(value=False)
    flag_steal_trainer_team = tk.BooleanVar(value=False)
    flag_no_exp = tk.BooleanVar(value=False)
    flag_no_pokeballs = tk.BooleanVar(value=False)
    flag_remote_opponent = tk.BooleanVar(value=False)

    wait_time_divisor_pow = tk.DoubleVar(value=0.0)  # 0..5 => 1..32
    wild_level_percent = tk.DoubleVar(value=0.0)  # -100..100
    trainer_level_percent = tk.DoubleVar(value=0.0)  # -100..100

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

        wild_pct = int(round(wild_level_percent.get()))
        if int(round(wild_level_percent.get())) != wild_pct:
            wild_level_percent.set(float(wild_pct))
        if wild_pct != 0:
            rand_args.extend(["--wild-level-percent", str(wild_pct)])

        trainer_pct = int(round(trainer_level_percent.get()))
        if int(round(trainer_level_percent.get())) != trainer_pct:
            trainer_level_percent.set(float(trainer_pct))
        if trainer_pct != 0:
            rand_args.extend(["--trainer-level-percent", str(trainer_pct)])

        any_selected = randomize_wild.get() or randomize_starters.get() or randomize_trainers.get()
        did_scale_levels = (wild_pct != 0) or (trainer_pct != 0)
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
        add_bool_flag("WALK_THROUGH_WALLS", flag_walk_through_walls.get())
        add_bool_flag("NUZLOCKE_DELETE_FAINTED", flag_nuzlocke_delete_fainted.get())
        add_bool_flag("INSTANT_TEXT", flag_instant_text.get())
        add_bool_flag("SKIP_BATTLE_TRANSITION", flag_skip_transition.get())
        add_bool_flag("SKIP_FADE_ANIMS", flag_skip_fade_anims.get())
        add_bool_flag("FAST_STAT_ANIMS", flag_fast_stat_anims.get())
        add_bool_flag("FORCE_DOUBLE_BATTLES", flag_force_doubles.get())
        add_bool_flag("STEAL_TRAINER_TEAM", flag_steal_trainer_team.get())
        add_bool_flag("NO_EXP", flag_no_exp.get())
        add_bool_flag("NO_POKEBALLS", flag_no_pokeballs.get())

        # Remote opponent control (leader) build: keep all selected build flags.
        # The Makefile outputs the normal ROM name (pokeemerald.gba).
        if flag_remote_opponent.get():
            make_args.append("REMOTE_OPPONENT_LEADER=1")

        wtd = 1 << int(round(wait_time_divisor_pow.get()))
        make_args.append(f"WAIT_TIME_DIVISOR={wtd}")

        def after_randomizer(code: int) -> None:
            if code != 0:
                build_btn.configure(state="normal")
                return

            if not any_selected:
                if did_scale_levels:
                    log("[success] level scaling applied\n")
                else:
                    log("[success] repo files restored from templates\n")
            else:
                log("[success] randomizer completed\n")

            def after_make(make_code: int) -> None:
                if make_code != 0:
                    build_btn.configure(state="normal")
                    return

                gba_path = repo_root / "pokeemerald.gba"
                if gba_path.exists():
                    log(f"[success] rom generated: {gba_path.name}\n")
                else:
                    log("[success] build completed\n")

                # If remote opponent is enabled, also build the follower ROM with only the follower flag.
                if not flag_remote_opponent.get():
                    build_btn.configure(state="normal")
                    return

                follower_make_args = [
                    "make",
                    f"-j{os.cpu_count() or 1}",
                    "REMOTE_OPPONENT_FOLLOWER=1",
                ]

                def after_follower_make(follower_code: int) -> None:
                    build_btn.configure(state="normal")
                    if follower_code == 0:
                        follower_path = repo_root / "follower.gba"
                        if follower_path.exists():
                            log(f"[success] follower rom generated: {follower_path.name}\n")
                        else:
                            log("[success] follower build completed\n")

                run_command_stream(
                    window,
                    repo_root,
                    follower_make_args,
                    log,
                    on_done=after_follower_make,
                )

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
    randomizer_group.grid(row=0, column=0, sticky="nsew")

    wild_cb = ttk.Checkbutton(randomizer_group, text="Wild", variable=randomize_wild)
    wild_cb.grid(row=0, column=0, sticky="w")
    add_tooltip(wild_cb, "Randomize wild encounter species.")

    starters_cb = ttk.Checkbutton(randomizer_group, text="Starters", variable=randomize_starters)
    starters_cb.grid(row=1, column=0, sticky="w")
    add_tooltip(starters_cb, "Randomize starter choices.")

    trainers_cb = ttk.Checkbutton(randomizer_group, text="Trainers", variable=randomize_trainers)
    trainers_cb.grid(row=2, column=0, sticky="w")
    add_tooltip(trainers_cb, "Randomize trainer party species.")

    random_evos_cb = ttk.Checkbutton(randomizer_group, text="RANDOM_EVOLUTIONS", variable=flag_random_evos)
    random_evos_cb.grid(row=3, column=0, sticky="w", pady=(6, 0))
    add_tooltip(random_evos_cb, "Randomize evolutions (build flag).")

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
    per_occ_cb.grid(row=4, column=0, sticky="w", pady=(6, 0))
    add_tooltip(per_occ_cb, "Replace every SPECIES_* occurrence independently (more chaotic).")

    per_map_cb = ttk.Checkbutton(
        randomizer_group,
        text="Per-map consistent",
        variable=randomize_per_map,
        command=sync_randomizer_mode_ui,
    )
    per_map_cb.grid(row=5, column=0, sticky="w")
    add_tooltip(per_map_cb, "Wild encounters only: keep replacements consistent within each map.")

    sync_randomizer_mode_ui()

    restore_btn = ttk.Button(randomizer_group, text="Restore repo files", command=do_restore)
    restore_btn.grid(row=6, column=0, sticky="w", pady=(8, 0))
    add_tooltip(restore_btn, "Overwrite the repo's src/ files with the copies in randomizer/ (undo randomization).")

    levels_group = ttk.Labelframe(top, text="Level modifiers", padding=10)
    levels_group.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

    wild_level_frame = ttk.Frame(levels_group)
    wild_level_frame.grid(row=0, column=0, sticky="w")

    wild_level_label = ttk.Label(wild_level_frame, text="Wild Level %")
    wild_level_label.pack(side="left")
    add_tooltip(wild_level_label, "Scale wild encounter levels by a percentage (clamped to 1..100).")

    wild_level_value_label = ttk.Label(wild_level_frame, text="0%", width=6, anchor="e")
    wild_level_value_label.pack(side="left", padx=(8, 8))

    def on_wild_level_slider(_value: str) -> None:
        snapped = int(round(float(_value)))
        if int(round(wild_level_percent.get())) != snapped:
            wild_level_percent.set(float(snapped))
        sign = "+" if snapped > 0 else ""
        wild_level_value_label.configure(text=f"{sign}{snapped}%")

    def reset_wild_level() -> None:
        wild_level_percent.set(0.0)
        wild_level_value_label.configure(text="0%")

    wild_level_scale = ttk.Scale(
        wild_level_frame,
        from_=-100,
        to=100,
        orient="horizontal",
        variable=wild_level_percent,
        command=on_wild_level_slider,
        length=160,
    )
    wild_level_scale.pack(side="left")
    add_tooltip(wild_level_scale, "-100% (min 1) through +100% (double levels).")

    wild_level_reset_btn = ttk.Button(wild_level_frame, text="Reset", command=reset_wild_level)
    wild_level_reset_btn.pack(side="left", padx=(8, 0))
    add_tooltip(wild_level_reset_btn, "Reset wild level scaling to 0%.")

    trainer_level_frame = ttk.Frame(levels_group)
    trainer_level_frame.grid(row=1, column=0, sticky="w", pady=(6, 0))

    trainer_level_label = ttk.Label(trainer_level_frame, text="Trainer Level %")
    trainer_level_label.pack(side="left")
    add_tooltip(trainer_level_label, "Scale trainer party levels by a percentage (clamped to 1..100).")

    trainer_level_value_label = ttk.Label(trainer_level_frame, text="0%", width=6, anchor="e")
    trainer_level_value_label.pack(side="left", padx=(8, 8))

    def on_trainer_level_slider(_value: str) -> None:
        snapped = int(round(float(_value)))
        if int(round(trainer_level_percent.get())) != snapped:
            trainer_level_percent.set(float(snapped))
        sign = "+" if snapped > 0 else ""
        trainer_level_value_label.configure(text=f"{sign}{snapped}%")

    def reset_trainer_level() -> None:
        trainer_level_percent.set(0.0)
        trainer_level_value_label.configure(text="0%")

    trainer_level_scale = ttk.Scale(
        trainer_level_frame,
        from_=-100,
        to=100,
        orient="horizontal",
        variable=trainer_level_percent,
        command=on_trainer_level_slider,
        length=160,
    )
    trainer_level_scale.pack(side="left")
    add_tooltip(trainer_level_scale, "-100% (min 1) through +100% (double levels).")

    trainer_level_reset_btn = ttk.Button(
        trainer_level_frame, text="Reset", command=reset_trainer_level
    )
    trainer_level_reset_btn.pack(side="left", padx=(8, 0))
    add_tooltip(trainer_level_reset_btn, "Reset trainer level scaling to 0%.")

    build_group = ttk.Labelframe(top, text="Build", padding=10)
    build_group.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
    build_group.columnconfigure(0, weight=1)
    build_group.columnconfigure(1, weight=1)

    speed_group = ttk.Labelframe(build_group, text="Speed / Skips", padding=8)
    speed_group.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    rules_group = ttk.Labelframe(build_group, text="Rules / Restrictions", padding=8)
    rules_group.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))

    util_group = ttk.Labelframe(build_group, text="Utility", padding=8)
    util_group.grid(row=0, column=1, rowspan=2, sticky="nsew")

    actions_frame = ttk.Frame(build_group)
    actions_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    # Speed / Skips
    walk_fast_cb = ttk.Checkbutton(speed_group, text="WALK_FAST", variable=flag_walk_fast)
    walk_fast_cb.grid(row=0, column=0, sticky="w")
    add_tooltip(walk_fast_cb, "Increase player walking speed (build flag).")

    instant_text_cb = ttk.Checkbutton(speed_group, text="INSTANT_TEXT", variable=flag_instant_text)
    instant_text_cb.grid(row=1, column=0, sticky="w")
    add_tooltip(instant_text_cb, "Make in-game text display instantly (build flag).")

    skip_transition_cb = ttk.Checkbutton(speed_group, text="SKIP_BATTLE_TRANSITION", variable=flag_skip_transition)
    skip_transition_cb.grid(row=2, column=0, sticky="w")
    add_tooltip(skip_transition_cb, "Skip the battle transition effect (build flag).")

    skip_fade_cb = ttk.Checkbutton(speed_group, text="SKIP_FADE_ANIMS", variable=flag_skip_fade_anims)
    skip_fade_cb.grid(row=3, column=0, sticky="w")
    add_tooltip(skip_fade_cb, "Compile-time: make fade-in/out screen transitions instant (doors, menus, bag, etc).")

    fast_stat_cb = ttk.Checkbutton(speed_group, text="FAST_STAT_ANIMS", variable=flag_fast_stat_anims)
    fast_stat_cb.grid(row=4, column=0, sticky="w")
    add_tooltip(fast_stat_cb, "Compile-time: speed up the stat-change (rose/fell) animation.")

    wait_frame = ttk.Frame(speed_group)
    wait_frame.grid(row=5, column=0, sticky="w", pady=(8, 0))

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

    # Rules / Restrictions
    nuzlocke_delete_fainted_cb = ttk.Checkbutton(
        rules_group,
        text="NUZLOCKE_DELETE_FAINTED",
        variable=flag_nuzlocke_delete_fainted,
    )
    nuzlocke_delete_fainted_cb.grid(row=0, column=0, sticky="w")
    add_tooltip(
        nuzlocke_delete_fainted_cb,
        "Nuzlocke rule: delete a party Pokémon after it faints (deferred until a replacement is sent out).",
    )

    force_doubles_cb = ttk.Checkbutton(rules_group, text="FORCE_DOUBLE_BATTLES", variable=flag_force_doubles)
    force_doubles_cb.grid(row=1, column=0, sticky="w")
    add_tooltip(force_doubles_cb, "Force double battles everywhere (build flag).")

    steal_team_cb = ttk.Checkbutton(rules_group, text="STEAL_TRAINER_TEAM", variable=flag_steal_trainer_team)
    steal_team_cb.grid(row=2, column=0, sticky="w")
    add_tooltip(steal_team_cb, "After winning a trainer battle, replace your party with theirs (build flag).")

    no_exp_cb = ttk.Checkbutton(rules_group, text="NO_EXP", variable=flag_no_exp)
    no_exp_cb.grid(row=3, column=0, sticky="w", pady=(6, 0))
    add_tooltip(no_exp_cb, "Compile-time: prevent Pokémon from gaining experience.")

    no_pokeballs_cb = ttk.Checkbutton(rules_group, text="NO_POKEBALLS", variable=flag_no_pokeballs)
    no_pokeballs_cb.grid(row=4, column=0, sticky="w")
    add_tooltip(no_pokeballs_cb, "Compile-time: prevent using Poké Balls.")

    # Utility
    wtw_cb = ttk.Checkbutton(util_group, text="WALK_THROUGH_WALLS", variable=flag_walk_through_walls)
    wtw_cb.grid(row=0, column=0, sticky="w")
    add_tooltip(wtw_cb, "Allow the player to ignore impassable tiles (build flag).")

    remote_opp_cb = ttk.Checkbutton(
        util_group,
        text="REMOTE_OPPONENT_CONTROL",
        variable=flag_remote_opponent,
    )
    remote_opp_cb.grid(row=1, column=0, sticky="w", pady=(6, 0))
    add_tooltip(
        remote_opp_cb,
        "Build pokeemerald.gba with remote opponent control enabled, then also build follower.gba (transport-only ROM).",
    )

    build_btn = ttk.Button(actions_frame, text="Build", command=do_build)
    build_btn.grid(row=0, column=0, sticky="w")
    add_tooltip(build_btn, "Run randomizer (or restore) then build the ROM.")

    output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    window.mainloop()


if __name__ == "__main__":
    main()
