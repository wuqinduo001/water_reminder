#!/usr/bin/env python3
"""💧 喝水提醒"""

import sys, time, json, threading, os, tkinter as tk
from datetime import date

try:
    import customtkinter as ctk
    from PIL import Image, ImageDraw
    import pystray
except ImportError:
    print("请先安装依赖：\npip install customtkinter pillow pystray")
    sys.exit(1)

CFG_FILE = os.path.join(os.path.expanduser("~"), ".water_reminder.json")
DEFAULTS = dict(interval=30, goal=8, snooze=5, today_date="", today_count=0)

BG    = "#0F1829"
CARD  = "#1C2742"
BLUE  = "#4B9EFF"
BLUE2 = "#2B7FFF"
MUTED = "#6B80A8"
SEC   = "#243058"
GREEN = "#27ae60"


def cfg_load():
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except Exception:
        return dict(DEFAULTS)


def cfg_save(c):
    try:
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def make_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(32, 4), (14, 36), (50, 36)], fill="#2B7FFF")
    d.ellipse([14, 30, 50, 60], fill="#2B7FFF")
    d.ellipse([22, 36, 28, 44], fill=(255, 255, 255, 80))
    return img


# ── 提醒弹窗 ───────────────────────────────────────────────
class ReminderPopup:
    W, H = 300, 232

    def __init__(self, app):
        self.app = app
        self.win = None
        self._countdown_id = None
        self._drag_x = self._drag_y = 0
        self._card = self._title = self._btn_row = self._cbar = None

    def show(self):
        if self.win and self.win.winfo_exists():
            self.win.lift()
            return

        W, H = self.W, self.H
        win = tk.Toplevel(self.app.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.configure(bg=BG)
        win.wm_attributes("-transparentcolor", BG)   # BG 透明 → 视觉圆角

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        # 初始在屏幕右侧外，动画滑入
        win.geometry(f"{W}x{H}+{sw + 20}+{sh - H - 62}")
        self.win = win

        win.bind("<Escape>", lambda e: self._close())

        self._build_ui(W, H)
        self._animate_in(sw, sh)

    def _build_ui(self, W, H):
        card = ctk.CTkFrame(self.win, width=W, height=H,
                            corner_radius=18, fg_color=CARD,
                            border_width=1, border_color="#223060")
        card.place(x=0, y=0)
        card.pack_propagate(False)
        self._card = card

        # 关闭按钮（x=W-48，远离圆角区域，确保可点击）
        ctk.CTkButton(card, text="✕", width=26, height=26,
                      fg_color="transparent", hover_color=SEC,
                      text_color=MUTED, font=ctk.CTkFont(size=13),
                      command=self._close).place(x=W - 48, y=10)

        ctk.CTkLabel(card, text="💧", font=ctk.CTkFont(size=36)).pack(pady=(18, 0))

        title = ctk.CTkLabel(card, text="该喝水了！",
                             font=ctk.CTkFont(size=18, weight="bold"),
                             text_color="white")
        title.pack(pady=(4, 2))
        self._title = title

        cnt  = self.app.cfg["today_count"]
        goal = self.app.cfg["goal"]
        pct  = min(cnt / max(goal, 1), 1.0)

        ctk.CTkLabel(card, text=f"今日进度   {cnt} / {goal} 杯",
                     font=ctk.CTkFont(size=11), text_color=MUTED).pack()

        bar = ctk.CTkProgressBar(card, width=240, height=8,
                                  corner_radius=4, progress_color=BLUE, fg_color=SEC)
        bar.set(pct)
        bar.pack(pady=(6, 14))

        # 按钮行
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack()
        self._btn_row = row

        snooze_min = self.app.cfg.get("snooze", 5)
        ctk.CTkButton(row, text=f"稍后 {snooze_min} 分钟", width=115, height=36,
                      corner_radius=10, fg_color=SEC, hover_color="#2A3A6A",
                      text_color=MUTED, font=ctk.CTkFont(size=12),
                      command=self._snooze).pack(side="left", padx=(0, 8))

        ctk.CTkButton(row, text="✓  已喝水", width=115, height=36,
                      corner_radius=10, fg_color=BLUE, hover_color=BLUE2,
                      text_color="white", font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._drink).pack(side="left")

        # 底部倒计时细条（30 秒后自动消失）
        cbar = ctk.CTkProgressBar(card, width=260, height=3,
                                   corner_radius=2,
                                   progress_color=MUTED, fg_color="transparent")
        cbar.set(1.0)
        cbar.pack(pady=(10, 8))
        self._cbar = cbar

        # 拖拽（跳过按钮，避免干扰点击）
        self._bind_drag(card)

    def _bind_drag(self, widget):
        if not isinstance(widget, ctk.CTkButton):
            widget.bind("<Button-1>", self._drag_start, add="+")
            widget.bind("<B1-Motion>", self._drag_motion, add="+")
        for child in widget.winfo_children():
            self._bind_drag(child)

    def _drag_start(self, event):
        self._drag_x = event.x_root - self.win.winfo_x()
        self._drag_y = event.y_root - self.win.winfo_y()

    def _drag_motion(self, event):
        if self.win and self.win.winfo_exists():
            self.win.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    # ── 滑入动画 ──────────────────────────────────────────
    def _animate_in(self, sw, sh, step=0, total=18):
        if not self.win or not self.win.winfo_exists():
            return
        t    = step / total
        ease = 1 - (1 - t) ** 2          # ease-out quad
        W, H = self.W, self.H
        x = int((sw + 20) + (sw - W - 20 - sw - 20) * ease)
        self.win.geometry(f"{W}x{H}+{x}+{sh - H - 62}")
        self.win.attributes("-alpha", min(ease * 1.5, 1.0))
        if step < total:
            self.win.after(18, lambda: self._animate_in(sw, sh, step + 1, total))
        else:
            self.win.attributes("-alpha", 1.0)
            self._start_countdown(30)

    # ── 淡出动画 ──────────────────────────────────────────
    def _fade_out(self, a=1.0):
        if not self.win or not self.win.winfo_exists():
            return
        a = round(a - 0.12, 2)
        self.win.attributes("-alpha", max(a, 0.0))
        if a > 0:
            self.win.after(16, lambda: self._fade_out(a))
        else:
            self.win.destroy()
            self.win = None

    # ── 30 秒倒计时 ───────────────────────────────────────
    def _start_countdown(self, seconds=30):
        self._countdown_total = seconds
        self._countdown_left  = seconds
        self._tick()

    def _tick(self):
        if not self.win or not self.win.winfo_exists():
            return
        self._countdown_left -= 1
        if self._cbar and self._cbar.winfo_exists():
            self._cbar.set(max(self._countdown_left / self._countdown_total, 0))
        if self._countdown_left <= 0:
            self._fade_out()
        else:
            self._countdown_id = self.win.after(1000, self._tick)

    def _cancel_countdown(self):
        if self._countdown_id and self.win and self.win.winfo_exists():
            self.win.after_cancel(self._countdown_id)
        self._countdown_id = None

    # ── 操作 ──────────────────────────────────────────────
    def _close(self):
        self._cancel_countdown()
        self._fade_out()

    def _drink(self):
        self._cancel_countdown()
        self.app.drink()
        # 成功反馈：变绿 → 0.9s 后淡出
        if self._card and self._card.winfo_exists():
            self._card.configure(border_color=GREEN)
        if self._title and self._title.winfo_exists():
            self._title.configure(text="✓ 记录成功！", text_color=GREEN)
        if self._btn_row and self._btn_row.winfo_exists():
            for w in self._btn_row.winfo_children():
                w.pack_forget()
        if self.win:
            self.win.after(900, self._fade_out)

    def _snooze(self):
        self._cancel_countdown()
        self.app.snooze()
        self._fade_out()


# ── 设置窗口 ───────────────────────────────────────────────
class SettingsWin:
    def __init__(self, app):
        self.app = app
        self.win = None

    def show(self):
        if self.win and self.win.winfo_exists():
            self.win.lift()
            return

        win = ctk.CTkToplevel(self.app.root)
        win.title("喝水提醒 · 设置")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(fg_color=CARD)
        self.win = win

        W, H = 320, 300
        sw = self.app.root.winfo_screenwidth()
        sh = self.app.root.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
        self._build(win)

    def _build(self, win):
        cfg = self.app.cfg

        ctk.CTkLabel(win, text="⚙  设置",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").pack(pady=(22, 14))

        ctk.CTkLabel(win, text="提醒间隔",
                     font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w").pack(fill="x", padx=32)

        self._iv = ctk.IntVar(value=cfg["interval"])
        ctk.CTkSlider(win, from_=5, to=120, number_of_steps=23,
                      variable=self._iv, button_color=BLUE, progress_color=BLUE,
                      fg_color=SEC, width=256).pack(padx=32, pady=(4, 0))

        self._il = ctk.CTkLabel(win, text=f"{cfg['interval']} 分钟",
                                 font=ctk.CTkFont(size=11), text_color=BLUE)
        self._il.pack()
        self._iv.trace_add("write", lambda *_: self._il.configure(text=f"{self._iv.get()} 分钟"))

        ctk.CTkLabel(win, text="每日目标",
                     font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w").pack(fill="x", padx=32, pady=(12, 0))

        self._gv = ctk.IntVar(value=cfg["goal"])
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=6)

        ctk.CTkButton(row, text="−", width=34, height=34, fg_color=SEC,
                      hover_color="#2A3A6A", text_color="white", font=ctk.CTkFont(size=16),
                      command=lambda: self._gv.set(max(1, self._gv.get() - 1))
                      ).pack(side="left", padx=5)
        ctk.CTkLabel(row, textvariable=self._gv,
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white", width=46, anchor="center").pack(side="left")
        ctk.CTkButton(row, text="+", width=34, height=34, fg_color=SEC,
                      hover_color="#2A3A6A", text_color="white", font=ctk.CTkFont(size=16),
                      command=lambda: self._gv.set(min(20, self._gv.get() + 1))
                      ).pack(side="left", padx=5)
        ctk.CTkLabel(row, text="杯 / 天",
                     font=ctk.CTkFont(size=12), text_color=MUTED).pack(side="left", padx=4)

        ctk.CTkButton(win, text="重置今日计数", width=160, height=32,
                      corner_radius=8, fg_color=SEC, hover_color="#2A3A6A",
                      text_color=MUTED, font=ctk.CTkFont(size=11),
                      command=self._reset_today).pack(pady=(10, 0))

        ctk.CTkButton(win, text="保存", width=160, height=38,
                      corner_radius=10, fg_color=BLUE, hover_color=BLUE2,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._save).pack(pady=(12, 0))

    def _reset_today(self):
        self.app.cfg["today_count"] = 0
        cfg_save(self.app.cfg)
        if self.win and self.win.winfo_exists():
            self.win.destroy()
        self.win = None

    def _save(self):
        self.app.cfg["interval"] = self._iv.get()
        self.app.cfg["goal"]     = self._gv.get()
        cfg_save(self.app.cfg)
        if self.win and self.win.winfo_exists():
            self.win.destroy()
        self.win = None


# ── 主应用 ─────────────────────────────────────────────────
class App:
    def __init__(self):
        self.cfg = cfg_load()
        self._check_date()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.withdraw()

        self.popup    = ReminderPopup(self)
        self.settings = SettingsWin(self)
        self._next    = time.time() + self.cfg["interval"] * 60

        self._setup_tray()
        self._start_timer()
        self._start_tray_updater()
        self.root.mainloop()

    def _check_date(self):
        td = date.today().isoformat()
        if self.cfg["today_date"] != td:
            self.cfg["today_count"] = 0
            self.cfg["today_date"]  = td
            cfg_save(self.cfg)

    def drink(self):
        self._check_date()
        self.cfg["today_count"] += 1
        cfg_save(self.cfg)
        self._next = time.time() + self.cfg["interval"] * 60

    def snooze(self):
        self._next = time.time() + self.cfg.get("snooze", 5) * 60

    def _start_timer(self):
        def loop():
            while True:
                time.sleep(5)
                if time.time() >= self._next:
                    self._check_date()
                    self._next = time.time() + self.cfg["interval"] * 60
                    self.root.after(0, self.popup.show)
        threading.Thread(target=loop, daemon=True).start()

    def _start_tray_updater(self):
        """每 30 秒更新托盘 tooltip：今日进度 + 距下次提醒"""
        def loop():
            while True:
                remaining = max(0, int((self._next - time.time()) / 60))
                cnt, goal = self.cfg["today_count"], self.cfg["goal"]
                try:
                    self._tray.title = f"喝水提醒  今日 {cnt}/{goal} 杯 · {remaining} 分钟后提醒"
                except Exception:
                    pass
                time.sleep(30)
        threading.Thread(target=loop, daemon=True).start()

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("显示提醒", lambda _, __: self.root.after(0, self.popup.show), default=True),
            pystray.MenuItem("设置",     lambda _, __: self.root.after(0, self.settings.show)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出",     self._quit),
        )
        self._tray = pystray.Icon("water", make_icon(), "喝水提醒", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self, _, __):
        self._tray.stop()
        self.root.after(0, self.root.quit)


if __name__ == "__main__":
    App()
