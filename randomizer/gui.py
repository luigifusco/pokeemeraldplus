import subprocess
import sys
import tkinter as tk
import os
import threading
from pathlib import Path
from tkinter import messagebox, scrolledtext
from tkinter import ttk


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
                log("[success] templates restored\n")

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
                log("[success] templates restored\n")
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

    ttk.Checkbutton(randomizer_group, text="Wild", variable=randomize_wild).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(randomizer_group, text="Starters", variable=randomize_starters).grid(row=1, column=0, sticky="w")
    ttk.Checkbutton(randomizer_group, text="Trainers", variable=randomize_trainers).grid(row=2, column=0, sticky="w")
    ttk.Button(randomizer_group, text="Restore templates", command=do_restore).grid(row=3, column=0, sticky="w", pady=(8, 0))

    build_group = ttk.Labelframe(top, text="Build", padding=10)
    build_group.grid(row=0, column=1, sticky="nw", padx=(10, 0))

    ttk.Checkbutton(build_group, text="RANDOM_EVOLUTIONS", variable=flag_random_evos).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(build_group, text="WALK_FAST", variable=flag_walk_fast).grid(row=1, column=0, sticky="w")
    ttk.Checkbutton(build_group, text="INSTANT_TEXT", variable=flag_instant_text).grid(row=2, column=0, sticky="w")
    ttk.Checkbutton(build_group, text="SKIP_BATTLE_TRANSITION", variable=flag_skip_transition).grid(row=3, column=0, sticky="w")
    ttk.Checkbutton(build_group, text="FORCE_DOUBLE_BATTLES", variable=flag_force_doubles).grid(row=4, column=0, sticky="w")
    ttk.Checkbutton(build_group, text="STEAL_TRAINER_TEAM", variable=flag_steal_trainer_team).grid(row=5, column=0, sticky="w")

    wait_frame = ttk.Frame(build_group)
    wait_frame.grid(row=6, column=0, sticky="w", pady=(8, 0))

    ttk.Label(wait_frame, text="WAIT_TIME_DIVISOR").pack(side="left")

    wait_value_label = ttk.Label(wait_frame, text=str(1 << int(round(wait_time_divisor_pow.get()))))
    wait_value_label.pack(side="left", padx=(8, 8))

    def on_wait_slider(_value: str) -> None:
        snapped = int(round(float(_value)))
        if int(round(wait_time_divisor_pow.get())) != snapped:
            wait_time_divisor_pow.set(float(snapped))
        wait_value_label.configure(text=str(1 << snapped))

    ttk.Scale(
        wait_frame,
        from_=0,
        to=5,
        orient="horizontal",
        variable=wait_time_divisor_pow,
        command=on_wait_slider,
        length=160,
    ).pack(side="left")

    build_btn = ttk.Button(build_group, text="Build", command=do_build)
    build_btn.grid(row=7, column=0, sticky="w", pady=(10, 0))

    output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    window.mainloop()


if __name__ == "__main__":
    main()
