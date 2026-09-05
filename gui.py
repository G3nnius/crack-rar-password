#!/usr/bin/env python3
"""RARNinja GUI - a light, native desktop front-end for the RAR cracker.

Pure standard library (tkinter). Reuses the engine in RARNinja.py: pick an
archive and a wordlist, hit Start, and it runs the all-core attack on a
background thread while the window stays responsive.
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

# Import the engine (works both from source and inside a PyInstaller bundle).
sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
import RARNinja as engine  # noqa: E402

# --- light palette -------------------------------------------------------
BG = "#f4f5f7"        # window background
CARD = "#ffffff"      # panel background
INK = "#1f2328"       # primary text
MUTE = "#6b7280"      # secondary text
ACCENT = "#2563eb"    # buttons / highlights
OK = "#15803d"        # success
ERR = "#b91c1c"       # failure
BORDER = "#e2e4e8"


class RARNinjaGUI:
    def __init__(self, root):
        self.root = root
        self.rar = tk.StringVar()
        self.words = tk.StringVar()
        self.workers = tk.IntVar(value=os.cpu_count() or 4)
        self.extract = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Select an archive and a wordlist to begin.")
        self.q = queue.Queue()
        self.cancel = None
        self.worker_thread = None
        self.tool, self.family = engine.detect_backend()

        self._build()
        self.root.after(80, self._pump)

    # -- layout -----------------------------------------------------------
    def _build(self):
        r = self.root
        r.title("RARNinja")
        r.configure(bg=BG)
        r.minsize(560, 440)

        style = ttk.Style(r)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=CARD, foreground=INK, font=("SF Pro Text", 12))
        style.configure("Head.TLabel", background=BG, foreground=INK,
                        font=("SF Pro Display", 22, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTE, font=("SF Pro Text", 11))
        style.configure("Mute.TLabel", background=CARD, foreground=MUTE, font=("SF Pro Text", 11))
        style.configure("Path.TLabel", background=CARD, foreground=INK, font=("SF Mono", 11))
        style.configure("Accent.TButton", font=("SF Pro Text", 13, "bold"), padding=(14, 9))
        style.configure("TButton", font=("SF Pro Text", 12), padding=(10, 6))
        style.configure("TCheckbutton", background=CARD, foreground=INK, font=("SF Pro Text", 11))
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BORDER)

        head = ttk.Frame(r, style="TFrame")
        head.pack(fill="x", padx=22, pady=(20, 8))
        ttk.Label(head, text="🥷  RARNinja", style="Head.TLabel").pack(anchor="w")
        ttk.Label(head, text="Multi-core RAR password recovery", style="Sub.TLabel").pack(anchor="w")

        card = ttk.Frame(r, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=22, pady=(6, 12))
        card_inner = tk.Frame(card, bg=CARD, highlightbackground=BORDER,
                              highlightthickness=1, bd=0)
        card_inner.pack(fill="both", expand=True)
        pad = {"padx": 18, "pady": 8}

        # Archive row
        ttk.Label(card_inner, text="Encrypted archive (.rar)", style="Mute.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 0))
        self.rar_lbl = ttk.Label(card_inner, text="No file selected", style="Path.TLabel")
        self.rar_lbl.grid(row=1, column=0, sticky="w", **pad)
        ttk.Button(card_inner, text="Select Archive…",
                   command=self._pick_rar).grid(row=1, column=1, sticky="e", **pad)

        # Wordlist row
        ttk.Label(card_inner, text="Dictionary / wordlist", style="Mute.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=18, pady=(6, 0))
        self.words_lbl = ttk.Label(card_inner, text="No file selected", style="Path.TLabel")
        self.words_lbl.grid(row=3, column=0, sticky="w", **pad)
        ttk.Button(card_inner, text="Select Wordlist…",
                   command=self._pick_words).grid(row=3, column=1, sticky="e", **pad)

        # Options row
        opt = tk.Frame(card_inner, bg=CARD)
        opt.grid(row=4, column=0, columnspan=2, sticky="we", padx=18, pady=(10, 4))
        ttk.Label(opt, text="Workers", style="Mute.TLabel").pack(side="left")
        tk.Spinbox(opt, from_=1, to=(os.cpu_count() or 8) * 2, width=4,
                   textvariable=self.workers, relief="solid", bd=1,
                   highlightthickness=0).pack(side="left", padx=(8, 18))
        ttk.Checkbutton(opt, text="Extract on success", variable=self.extract,
                        style="TCheckbutton").pack(side="left")

        card_inner.columnconfigure(0, weight=1)

        # Action buttons
        actions = tk.Frame(card_inner, bg=CARD)
        actions.grid(row=5, column=0, columnspan=2, sticky="we", padx=18, pady=(6, 8))
        self.start_btn = ttk.Button(actions, text="Start Cracking",
                                    style="Accent.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(actions, text="Stop", command=self._stop,
                                   state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        # Progress + result
        self.bar = ttk.Progressbar(card_inner, mode="determinate",
                                   style="Horizontal.TProgressbar")
        self.bar.grid(row=6, column=0, columnspan=2, sticky="we", padx=18, pady=(6, 2))
        self.result = tk.Label(card_inner, text="", bg=CARD, fg=INK,
                               font=("SF Mono", 13, "bold"), anchor="w")
        self.result.grid(row=7, column=0, columnspan=2, sticky="we", padx=18, pady=(4, 4))

        # Status bar
        bar = tk.Frame(r, bg=BG)
        bar.pack(fill="x", padx=22, pady=(0, 14))
        backend = f"{os.path.basename(self.tool)} ({self.family})" if self.tool else "none found!"
        tk.Label(bar, textvariable=self.status, bg=BG, fg=MUTE,
                 font=("SF Pro Text", 11), anchor="w").pack(side="left")
        tk.Label(bar, text=f"backend: {backend}", bg=BG, fg=MUTE,
                 font=("SF Pro Text", 10), anchor="e").pack(side="right")

        if not self.tool:
            self.status.set("No RAR backend found — install unrar / 7zz / 7z.")
            self.start_btn.config(state="disabled")

    # -- file pickers -----------------------------------------------------
    def _pick_rar(self):
        p = filedialog.askopenfilename(
            title="Select encrypted RAR",
            filetypes=[("RAR archives", "*.rar"), ("All files", "*.*")])
        if p:
            self.rar.set(p)
            self.rar_lbl.config(text=self._short(p))

    def _pick_words(self):
        p = filedialog.askopenfilename(
            title="Select wordlist",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if p:
            self.words.set(p)
            self.words_lbl.config(text=self._short(p))

    @staticmethod
    def _short(path, n=46):
        return path if len(path) <= n else "…" + path[-(n - 1):]

    # -- run control ------------------------------------------------------
    def _start(self):
        if not self.rar.get() or not os.path.isfile(self.rar.get()):
            self.status.set("Please select a valid archive first.")
            return
        if not self.words.get() or not os.path.isfile(self.words.get()):
            self.status.set("Please select a valid wordlist first.")
            return
        # Snapshot every Tk value on the main thread; the worker must not touch Tk.
        job = (self.rar.get(), self.words.get(),
               max(1, self.workers.get()), bool(self.extract.get()))
        self.cancel = threading.Event()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result.config(text="", fg=INK)
        self.bar.config(mode="indeterminate")
        self.bar.start(12)
        self.status.set("Working…")
        self.worker_thread = threading.Thread(target=self._run, args=job, daemon=True)
        self.worker_thread.start()

    def _stop(self):
        if self.cancel:
            self.cancel.set()
            self.status.set("Stopping…")
            self.stop_btn.config(state="disabled")

    def _run(self, rar, words, workers, extract):
        try:
            hit, tried, elapsed = engine.crack(
                rar, words, self.tool, self.family, workers, progress=False,
                on_progress=lambda t, r, e: self.q.put(("progress", t, r, e)),
                cancel=self.cancel)
            if hit is not None and extract:
                dest = os.path.join(os.path.dirname(rar) or ".", "Extracted")
                os.makedirs(dest, exist_ok=True)
                cmd = engine.make_extract_cmd(self.tool, self.family,
                                              rar, hit, dest)
                subprocess.run(cmd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.q.put(("done", hit, tried, elapsed, dest))
            else:
                self.q.put(("done", hit, tried, elapsed, None))
        except Exception as e:  # surface any engine error in the UI
            self.q.put(("error", str(e)))

    # -- UI update loop ---------------------------------------------------
    def _pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    _, tried, rate, elapsed = msg
                    self.status.set(f"Tried {tried:,}  ·  {rate:,.0f}/sec  ·  {elapsed:.0f}s")
                elif msg[0] == "done":
                    self._finish(*msg[1:])
                elif msg[0] == "error":
                    self.bar.stop(); self.bar.config(mode="determinate", value=0)
                    self.result.config(text=f"Error: {msg[1]}", fg=ERR)
                    self.status.set("Failed.")
                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _finish(self, hit, tried, elapsed, dest):
        self.bar.stop()
        self.bar.config(mode="determinate", value=100 if hit else 0)
        rate = tried / elapsed if elapsed > 0 else 0
        if hit is not None:
            self.result.config(text=f"✓  Password: {hit}", fg=OK)
            extra = f"  ·  extracted → {dest}" if dest else ""
            self.status.set(f"Found in {tried:,} tries ({elapsed:.1f}s, ~{rate:,.0f}/sec){extra}")
        elif self.cancel and self.cancel.is_set():
            self.result.config(text="Stopped.", fg=MUTE)
            self.status.set(f"Cancelled after {tried:,} tries.")
        else:
            self.result.config(text="✗  Not found in this wordlist", fg=ERR)
            self.status.set(f"Exhausted {tried:,} candidates ({elapsed:.1f}s, ~{rate:,.0f}/sec).")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 2.0)  # crisper on Retina
    except tk.TclError:
        pass
    RARNinjaGUI(root)
    root.mainloop()


if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    main()
