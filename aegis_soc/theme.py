"""
AEGIS IDEA 3 — Theme & reusable widgets (สี ฟอนต์ การ์ด)
แยกออกมาเพื่อให้ gui.py และ wizard.py ใช้ร่วมกันโดยไม่เกิด circular import
"""
import tkinter as tk

COLOR_BG        = "#0b1220"
COLOR_PANEL     = "#151f32"
COLOR_PANEL_ALT = "#0a0f1a"
COLOR_BORDER    = "#263349"
COLOR_TEXT      = "#e2e8f0"
COLOR_MUTED     = "#7c8aa5"
COLOR_ACCENT    = "#38bdf8"
COLOR_DANGER    = "#dc2626"
COLOR_DANGER_HL = "#ef4444"
COLOR_SUCCESS   = "#16a34a"
COLOR_SUCCESS_HL= "#22c55e"
COLOR_GOOD      = "#4ade80"
COLOR_WARN      = "#d97706"
COLOR_WARN_HL   = "#f59e0b"
COLOR_PURPLE    = "#c084fc"
COLOR_BLUE      = "#2563eb"
COLOR_BLUE_HL   = "#3b82f6"
COLOR_GREY      = "#94a3b8"

# สีของ log ตามระดับความรุนแรง
LEVEL_COLORS = {"INFO": "#7dd3fc", "WARN": COLOR_WARN_HL, "CRITICAL": COLOR_DANGER_HL}

FONT_TITLE   = ("Segoe UI", 15, "bold")
FONT_SUB     = ("Segoe UI", 9)
FONT_SECTION = ("Segoe UI", 10, "bold")
FONT_BTN     = ("Segoe UI", 10, "bold")
FONT_BTN_SM  = ("Segoe UI", 9, "bold")
FONT_HINT    = ("Segoe UI", 8)
FONT_MONO    = ("Consolas", 9)


class Card(tk.Frame):
    """การ์ดพื้นหลังเข้ม มีแถบสีคาดซ้ายบอกความหมาย"""
    def __init__(self, parent, accent=COLOR_ACCENT, **kwargs):
        super().__init__(parent, bg=COLOR_BORDER, **kwargs)
        self.inner = tk.Frame(self, bg=COLOR_PANEL)
        self.inner.pack(fill="both", expand=True, padx=(0, 1), pady=1)
        self.bar = tk.Frame(self.inner, bg=accent, width=4)
        self.bar.pack(side="left", fill="y")
        self.body = tk.Frame(self.inner, bg=COLOR_PANEL)
        self.body.pack(side="left", fill="both", expand=True)

    def set_accent(self, color):
        self.bar.config(bg=color)


class Section(tk.Frame):
    """กล่อง section มีหัวข้อคาดบน"""
    def __init__(self, parent, title, accent=COLOR_ACCENT, **kwargs):
        super().__init__(parent, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER,
                          highlightthickness=1, bd=0, **kwargs)
        head = tk.Frame(self, bg=COLOR_PANEL)
        head.pack(fill="x", padx=12, pady=(8, 5))
        tk.Frame(head, bg=accent, width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(head, text=title, font=FONT_SECTION, fg=COLOR_TEXT, bg=COLOR_PANEL).pack(side="left")
        tk.Frame(self, bg=COLOR_BORDER, height=1).pack(fill="x")
        self.body = tk.Frame(self, bg=COLOR_PANEL)
        self.body.pack(fill="both", expand=True, padx=12, pady=8)


class ScrollFrame(tk.Frame):
    """กล่องเลื่อนแนวตั้ง — ใส่เนื้อหาจริงใน self.inner"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLOR_BG, **kwargs)
        self.canvas = tk.Canvas(self, bg=COLOR_BG, highlightthickness=0, bd=0)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                width=10, troughcolor=COLOR_BG, bg=COLOR_BORDER,
                                activebackground=COLOR_MUTED, bd=0, relief="flat")
        self.inner = tk.Frame(self.canvas, bg=COLOR_BG)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.canvas.bind_all(seq, self._on_wheel)

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(1, "units")
        elif getattr(event, "delta", 0):
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")


def make_hint(parent, text):
    return tk.Label(parent, text=text, font=FONT_HINT, fg=COLOR_MUTED, bg=COLOR_PANEL,
                    wraplength=288, justify="left")
