#!/usr/bin/env python3
"""RARNinja GUI - a light, wizard-style desktop front-end for the RAR cracker.

Pure standard library (tkinter). Four steps:
  1. Select archive
  2. Choose how much of the computer to use (workers)
  3. Choose a wordlist  OR  generate one (charset + length settings)
  4. Run - live progress, then the password (saved to history) or "not found"

Plus a History view of previously recovered passwords.
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
import RARNinja as engine  # noqa: E402

# --- light palette -------------------------------------------------------
BG = "#f4f5f7"; CARD = "#ffffff"; INK = "#1f2328"; MUTE = "#6b7280"
ACCENT = "#2563eb"; OK = "#15803d"; ERR = "#b91c1c"; BORDER = "#e2e4e8"
STEPS = ["Archive", "Resources", "Dictionary", "Run"]


def human_time(seconds):
    if seconds < 1:
        return "under a second"
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= n:
            v = seconds / n
            return f"~{v:.0f} {unit}{'s' if v >= 2 else ''}"
    return f"~{seconds:.0f} seconds"


def short(path, n=52):
    return path if len(path) <= n else "…" + path[-(n - 1):]


class RARNinjaGUI:
    def __init__(self, root):
        self.root = root
        self.cpu = os.cpu_count() or 4
        self.step = 0

        # state
        self.rar = ""
        self.words = ""
        self.workers = tk.IntVar(value=self.cpu)
        self.mode = tk.StringVar(value="file")          # 'file' | 'generate'
        self.charset = tk.StringVar(value="digits")
        self.min_len = tk.IntVar(value=1)
        self.max_len = tk.IntVar(value=4)
        self.extract = tk.BooleanVar(value=True)

        self.q = queue.Queue()
        self.cancel = None
        self.tool, self.family = engine.detect_backend()

        self._build()
        self._show_step(0)
        self.root.after(80, self._pump)

    # ---- chrome ---------------------------------------------------------
    def _build(self):
        r = self.root
        r.title("RARNinja")
        r.configure(bg=BG)
        r.minsize(600, 500)
        self._set_window_icon()

        st = ttk.Style(r)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=CARD, foreground=INK)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=CARD, foreground=INK, font=("Helvetica", 12))
        st.configure("Head.TLabel", background=BG, foreground=INK, font=("Helvetica", 22, "bold"))
        st.configure("Sub.TLabel", background=BG, foreground=MUTE, font=("Helvetica", 11))
        st.configure("Step.TLabel", background=BG, foreground=MUTE, font=("Helvetica", 11, "bold"))
        st.configure("Mute.TLabel", background=CARD, foreground=MUTE, font=("Helvetica", 11))
        st.configure("Big.TLabel", background=CARD, foreground=INK, font=("Helvetica", 15, "bold"))
        st.configure("Path.TLabel", background=CARD, foreground=INK, font=("Courier", 11))
        st.configure("TButton", font=("Helvetica", 12), padding=(10, 6))
        st.configure("Accent.TButton", font=("Helvetica", 13, "bold"), padding=(16, 9))
        st.configure("TCheckbutton", background=CARD, foreground=INK)
        st.configure("TRadiobutton", background=CARD, foreground=INK, font=("Helvetica", 12))
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BORDER)

        head = ttk.Frame(r)
        head.pack(fill="x", padx=22, pady=(18, 4))
        ttk.Label(head, text="🥷  RARNinja", style="Head.TLabel").pack(side="left")
        self.step_lbl = ttk.Label(head, text="", style="Step.TLabel")
        self.step_lbl.pack(side="right", pady=(12, 0))

        # card holds the step frames (built after nav so callbacks can find buttons)
        self.card = tk.Frame(r, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.card.pack(fill="both", expand=True, padx=22, pady=(6, 6))

        # nav bar
        nav = ttk.Frame(r)
        nav.pack(fill="x", padx=22, pady=(0, 14))
        self.hist_btn = ttk.Button(nav, text="History", command=self._show_history)
        self.hist_btn.pack(side="left")
        self.next_btn = ttk.Button(nav, text="Next  ›", style="Accent.TButton", command=self._next)
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(nav, text="‹  Back", command=self._back)
        self.back_btn.pack(side="right", padx=8)

        backend = f"{os.path.basename(self.tool)} ({self.family})" if self.tool else "NONE FOUND"
        self.status = tk.Label(r, text=f"backend: {backend}   ·   {self.cpu} CPU cores",
                               bg=BG, fg=MUTE, font=("Helvetica", 10), anchor="w")
        self.status.pack(fill="x", padx=24, pady=(0, 10))
        if not self.tool:
            self.status.config(text="No RAR backend found — install unrar / 7zz / 7z.", fg=ERR)

        # build step frames last, now that nav buttons exist for their callbacks
        self.frames = [self._step_archive(), self._step_resources(),
                       self._step_dictionary(), self._step_run()]

    def _set_window_icon(self):
        # Tk 8.6+ can load PNG; 8.5 cannot — fail quietly.
        png = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
                           "assets", "icon_1024.png")
        try:
            if os.path.isfile(png):
                self.root.iconphoto(True, tk.PhotoImage(file=png))
        except Exception:
            pass

    def _blank(self):
        f = tk.Frame(self.card, bg=CARD)
        return f

    # ---- step 1: archive ------------------------------------------------
    def _step_archive(self):
        f = self._blank()
        ttk.Label(f, text="Select the encrypted archive", style="Big.TLabel").pack(anchor="w", padx=22, pady=(22, 4))
        ttk.Label(f, text="Choose the password-protected .rar file you want to open.",
                  style="Mute.TLabel").pack(anchor="w", padx=22)
        row = tk.Frame(f, bg=CARD); row.pack(fill="x", padx=22, pady=22)
        ttk.Button(row, text="Select Archive…", command=self._pick_rar).pack(side="left")
        self.rar_lbl = ttk.Label(row, text="No file selected", style="Path.TLabel")
        self.rar_lbl.pack(side="left", padx=14)
        return f

    def _pick_rar(self):
        p = filedialog.askopenfilename(title="Select encrypted RAR",
                                       filetypes=[("RAR archives", "*.rar"), ("All files", "*.*")])
        if p:
            self.rar = p
            self.rar_lbl.config(text=short(p))
            self._refresh_nav()

    # ---- step 2: resources ---------------------------------------------
    def _step_resources(self):
        f = self._blank()
        ttk.Label(f, text="How much of the computer to use", style="Big.TLabel").pack(anchor="w", padx=22, pady=(22, 4))
        ttk.Label(f, text="More workers = faster, but leaves less for other apps.",
                  style="Mute.TLabel").pack(anchor="w", padx=22)
        self.workers_lbl = ttk.Label(f, text="", style="Big.TLabel")
        self.workers_lbl.pack(anchor="w", padx=22, pady=(18, 2))
        self.workers_scale = ttk.Scale(f, from_=1, to=self.cpu, orient="horizontal",
                                       command=self._on_workers)
        self.workers_scale.set(self.cpu)
        self.workers_scale.pack(fill="x", padx=22, pady=(0, 6))
        ttk.Label(f, text="1 = gentle   ·   max = fastest", style="Mute.TLabel").pack(anchor="w", padx=22)
        self._on_workers(self.cpu)
        return f

    def _on_workers(self, value):
        w = max(1, min(self.cpu, int(round(float(value)))))
        self.workers.set(w)
        pct = int(100 * w / self.cpu)
        self.workers_lbl.config(text=f"Use {w} of {self.cpu} cores  ({pct}%)")

    # ---- step 3: dictionary --------------------------------------------
    def _step_dictionary(self):
        f = self._blank()
        ttk.Label(f, text="Choose or generate a dictionary", style="Big.TLabel").pack(anchor="w", padx=22, pady=(22, 4))

        r1 = tk.Frame(f, bg=CARD); r1.pack(fill="x", padx=22, pady=(10, 2))
        ttk.Radiobutton(r1, text="I have a wordlist", value="file",
                        variable=self.mode, command=self._on_mode).pack(side="left")
        wl = tk.Frame(f, bg=CARD); wl.pack(fill="x", padx=44, pady=(0, 8))
        self.words_btn = ttk.Button(wl, text="Select Wordlist…", command=self._pick_words)
        self.words_btn.pack(side="left")
        self.words_lbl = ttk.Label(wl, text="No file selected", style="Path.TLabel")
        self.words_lbl.pack(side="left", padx=12)

        ttk.Radiobutton(f, text="Generate one for me", value="generate",
                        variable=self.mode, command=self._on_mode).pack(anchor="w", padx=22, pady=(8, 2))
        g = tk.Frame(f, bg=CARD); g.pack(fill="x", padx=44, pady=(0, 6))
        ttk.Label(g, text="Complexity", style="Mute.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        self.charset_box = ttk.Combobox(g, state="readonly", width=26,
                                        values=[engine.CHARSET_LABELS[k] for k in engine.CHARSETS])
        self.charset_box.current(0)
        self.charset_box.grid(row=0, column=1, sticky="w", padx=10)
        self.charset_box.bind("<<ComboboxSelected>>", lambda e: self._on_gen_change())

        ttk.Label(g, text="Length", style="Mute.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        lf = tk.Frame(g, bg=CARD); lf.grid(row=1, column=1, sticky="w", padx=10)
        ttk.Label(lf, text="from", style="Mute.TLabel").pack(side="left")
        self.min_spin = tk.Spinbox(lf, from_=1, to=12, width=3, textvariable=self.min_len,
                                   command=self._on_gen_change, relief="solid", bd=1)
        self.min_spin.pack(side="left", padx=4)
        ttk.Label(lf, text="to", style="Mute.TLabel").pack(side="left")
        self.max_spin = tk.Spinbox(lf, from_=1, to=12, width=3, textvariable=self.max_len,
                                   command=self._on_gen_change, relief="solid", bd=1)
        self.max_spin.pack(side="left", padx=4)

        self.gen_est = ttk.Label(f, text="", style="Mute.TLabel")
        self.gen_est.pack(anchor="w", padx=44, pady=(6, 0))
        self._on_mode()
        return f

    def _pick_words(self):
        p = filedialog.askopenfilename(title="Select wordlist",
                                       filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if p:
            self.words = p
            self.words_lbl.config(text=short(p))
            self._refresh_nav()

    def _charset_key(self):
        keys = list(engine.CHARSETS)
        return keys[self.charset_box.current() if self.charset_box.current() >= 0 else 0]

    def _on_mode(self):
        gen = self.mode.get() == "generate"
        state = "normal" if gen else "disabled"
        for w in (self.charset_box, self.min_spin, self.max_spin):
            try:
                w.config(state="readonly" if (gen and w is self.charset_box) else state)
            except tk.TclError:
                pass
        self.words_btn.config(state="disabled" if gen else "normal")
        self._on_gen_change()
        self._refresh_nav()

    def _on_gen_change(self):
        try:
            lo, hi = int(self.min_len.get()), int(self.max_len.get())
        except (tk.TclError, ValueError):
            self.gen_est.config(text=""); return
        if hi < lo:
            self.gen_est.config(text="Max length must be ≥ min length.", foreground=ERR)
            self._refresh_nav(); return
        total = engine.gen_count(self._charset_key(), lo, hi)
        est = human_time(total / max(1, self.workers.get() * 50))
        warn = "   ⚠ very large — consider a wordlist" if total > 5_000_000 else ""
        self.gen_est.config(text=f"{total:,} candidates   ·   {est} to exhaust{warn}",
                            foreground=(ERR if total > 50_000_000 else MUTE))
        self._refresh_nav()

    # ---- step 4: run ----------------------------------------------------
    def _step_run(self):
        f = self._blank()
        ttk.Label(f, text="Ready to crack", style="Big.TLabel").pack(anchor="w", padx=22, pady=(22, 4))
        self.summary = ttk.Label(f, text="", style="Mute.TLabel", justify="left")
        self.summary.pack(anchor="w", padx=22, pady=(2, 10))

        br = tk.Frame(f, bg=CARD); br.pack(fill="x", padx=22, pady=(2, 4))
        self.start_btn = ttk.Button(br, text="Start Cracking", style="Accent.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(br, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.new_btn = ttk.Button(br, text="New Search", command=self._reset, state="disabled")
        self.new_btn.pack(side="left", padx=8)

        self.bar = ttk.Progressbar(f, mode="determinate", style="Horizontal.TProgressbar")
        self.bar.pack(fill="x", padx=22, pady=(10, 4))
        self.run_status = ttk.Label(f, text="", style="Mute.TLabel")
        self.run_status.pack(anchor="w", padx=22)
        self.result = tk.Label(f, text="", bg=CARD, fg=INK, font=("Courier", 15, "bold"),
                               anchor="w", wraplength=520, justify="left")
        self.result.pack(anchor="w", fill="x", padx=22, pady=(8, 6))
        return f

    # ---- navigation -----------------------------------------------------
    def _show_step(self, i):
        self.step = i
        for fr in self.frames:
            fr.pack_forget()
        self.frames[i].pack(fill="both", expand=True)
        self.step_lbl.config(text=f"Step {i + 1} of {len(STEPS)}  ·  {STEPS[i]}")
        if i == 3:
            self._update_summary()
        self._refresh_nav()

    def _refresh_nav(self):
        self.back_btn.pack_forget(); self.next_btn.pack_forget()
        if self.step < 3:
            self.next_btn.pack(side="right")
        self.back_btn.pack(side="right", padx=8)
        self.back_btn.config(state="normal" if self.step > 0 else "disabled")
        self.next_btn.config(state="normal" if self._can_advance() else "disabled")

    def _can_advance(self):
        if self.step == 0:
            return bool(self.rar) and os.path.isfile(self.rar)
        if self.step == 2:
            if self.mode.get() == "file":
                return bool(self.words) and os.path.isfile(self.words)
            try:
                return int(self.max_len.get()) >= int(self.min_len.get())
            except (tk.TclError, ValueError):
                return False
        return True

    def _next(self):
        if self._can_advance() and self.step < 3:
            self._show_step(self.step + 1)

    def _back(self):
        if self.step > 0:
            self._show_step(self.step - 1)

    def _reset(self):
        self.result.config(text=""); self.run_status.config(text="")
        self.bar.config(mode="determinate", value=0)
        self.new_btn.config(state="disabled")
        self._show_step(0)

    def _update_summary(self):
        if self.mode.get() == "generate":
            lo, hi = self.min_len.get(), self.max_len.get()
            dic = f"generate {engine.CHARSET_LABELS[self._charset_key()]}, length {lo}-{hi}"
        else:
            dic = f"wordlist {os.path.basename(self.words)}"
        self.summary.config(text=f"Archive:  {os.path.basename(self.rar)}\n"
                                 f"Workers:  {self.workers.get()} of {self.cpu} cores\n"
                                 f"Source:   {dic}")

    # ---- run ------------------------------------------------------------
    def _start(self):
        if not self.tool:
            self.result.config(text="No RAR backend found.", fg=ERR); return
        mode = self.mode.get()
        job = dict(rar=self.rar, workers=max(1, self.workers.get()),
                   extract=bool(self.extract.get()), mode=mode,
                   words=self.words, charset=self._charset_key(),
                   lo=int(self.min_len.get()), hi=int(self.max_len.get()))
        self.cancel = threading.Event()
        self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal")
        self.new_btn.config(state="disabled"); self.back_btn.config(state="disabled")
        self.result.config(text="", fg=INK)
        self.bar.config(mode="indeterminate"); self.bar.start(12)
        self.run_status.config(text="Working…")
        threading.Thread(target=self._run, kwargs=job, daemon=True).start()

    def _stop(self):
        if self.cancel:
            self.cancel.set()
            self.run_status.config(text="Stopping…")
            self.stop_btn.config(state="disabled")

    def _run(self, rar, workers, extract, mode, words, charset, lo, hi):
        try:
            source = engine.gen_candidates(charset, lo, hi) if mode == "generate" else words
            hit, tried, elapsed = engine.crack(
                rar, source, self.tool, self.family, workers, progress=False,
                on_progress=lambda t, r, e: self.q.put(("progress", t, r, e)),
                cancel=self.cancel)
            dest = None
            if hit is not None:
                engine.history_add(rar, hit)
                if extract:
                    dest = os.path.join(os.path.dirname(rar) or ".", "Extracted")
                    os.makedirs(dest, exist_ok=True)
                    cmd = engine.make_extract_cmd(self.tool, self.family, rar, hit, dest)
                    subprocess.run(cmd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.q.put(("done", hit, tried, elapsed, dest))
        except Exception as e:
            self.q.put(("error", str(e)))

    def _pump(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "progress":
                    _, t, r, e = m
                    self.run_status.config(text=f"Tried {t:,}  ·  {r:,.0f}/sec  ·  {e:.0f}s")
                elif m[0] == "done":
                    self._finish(*m[1:])
                elif m[0] == "error":
                    self.bar.stop(); self.bar.config(mode="determinate", value=0)
                    self.result.config(text=f"Error: {m[1]}", fg=ERR)
                    self.run_status.config(text="Failed.")
                    self._run_done()
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _run_done(self):
        self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled")
        self.new_btn.config(state="normal"); self.back_btn.config(state="normal")

    def _finish(self, hit, tried, elapsed, dest):
        self.bar.stop(); self.bar.config(mode="determinate", value=100 if hit else 0)
        rate = tried / elapsed if elapsed > 0 else 0
        if hit is not None:
            self.result.config(text=f"✓  Password:  {hit}", fg=OK)
            extra = f"   ·   extracted to {dest}" if dest else ""
            self.run_status.config(text=f"Found in {tried:,} tries "
                                        f"({elapsed:.1f}s, ~{rate:,.0f}/sec) · saved to history{extra}")
        elif self.cancel and self.cancel.is_set():
            self.result.config(text="Stopped.", fg=MUTE)
            self.run_status.config(text=f"Cancelled after {tried:,} tries.")
        else:
            self.result.config(text="✗  Password not found in this dictionary", fg=ERR)
            self.run_status.config(text=f"Exhausted {tried:,} candidates ({elapsed:.1f}s, ~{rate:,.0f}/sec).")
        self._run_done()

    # ---- history --------------------------------------------------------
    def _show_history(self):
        win = tk.Toplevel(self.root)
        win.title("RARNinja — History")
        win.configure(bg=CARD)
        win.minsize(520, 320)
        ttk.Label(win, text="Recovered passwords", style="Big.TLabel").pack(anchor="w", padx=18, pady=(16, 6))
        rows = engine.history_list()
        if not rows:
            ttk.Label(win, text="No passwords recovered yet.", style="Mute.TLabel").pack(anchor="w", padx=18, pady=10)
            return
        box = tk.Text(win, height=14, width=70, bg="#fbfbfc", fg=INK, relief="flat",
                      font=("Courier", 11), padx=10, pady=8, wrap="none")
        box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        for r in reversed(rows):
            box.insert("end", f"{r.get('when','?')}   {r.get('password','')}\n"
                              f"    {r.get('archive','')}\n\n")
        box.config(state="disabled")


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 2.0)
    except tk.TclError:
        pass
    RARNinjaGUI(root)
    root.mainloop()


def _selftest(rar, words):
    """Headlessly drive the wizard against a fixture; return True if it cracks.

    Used by CI (under xvfb) to prove the FROZEN GUI actually runs on the target.
    """
    import time
    root = tk.Tk(); root.withdraw()
    app = RARNinjaGUI(root)
    if not app.tool:
        print("selftest: no backend found"); return False
    app.rar = rar; app._refresh_nav(); app._next()      # -> resources
    app.workers.set(2); app._next()                      # -> dictionary
    app.mode.set("file"); app._on_mode()
    app.words = words; app._refresh_nav(); app._next()   # -> run
    app.extract.set(False)
    app._start()
    deadline = time.time() + 90
    while time.time() < deadline:
        root.update()
        if str(app.new_btn["state"]) == "normal":
            break
        time.sleep(0.03)
    txt = app.result.cget("text")
    print("selftest result:", txt)
    root.destroy()
    return "Password:" in txt


if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    if len(sys.argv) >= 4 and sys.argv[1] == "--selftest":
        sys.exit(0 if _selftest(sys.argv[2], sys.argv[3]) else 1)
    main()
