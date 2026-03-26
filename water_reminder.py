#!/usr/bin/env python3
"""💧 喝水提醒 Water Reminder"""

import sys, time, json, threading, os, tkinter as tk
from datetime import date

try:
    import customtkinter as ctk
    from PIL import Image, ImageDraw
    import pystray
except ImportError:
    print("请先安装依赖：\npip install customtkinter pillow pystray")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────
CFG_FILE = os.path.join(os.path.expanduser("~"), ".water_reminder.json")
DEFAULTS = dict(interval=30, goal=8, snooze=5, today_date="", today_count=0)

BG    = "#0F1829"   # 窗口底色（设为透明色，实现圆角效果）
CARD  = "#1C2742"   # 卡片色
BLUE  = "#4B9EFF"   # 主色
BLUE2 = "#2B7FFF"   # 深蓝
MUTED = "#6B80A8"   # 次要文字
SEC   = "#243058"   # 次级按钮


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


# ── 托盘图标 ───────────────────────────────────────────────
def make_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(32, 4), (14, 36), (50, 36)], fill="#2B7FFF")
    d.ellipse([14, 30, 50, 60], fill="#2B7FFF")
    d.ellipse([22, 36, 28, 44], fill=(255, 255, 255, 80))
    return img


# ── 提醒弹窗 ───────────────────────────────────────────────
class ReminderPopup:
    W, H = 300, 220

    def __init__(self, app):
        self.app = app
        self.win = None

    def show(self):
        if self.win and self.win.winfo_exists():
            self.win.lift()
            return

        W, H = self.W, self.H
        sw = self.app.root.winfo_screenwidth()
        sh = self.app.root.winfo_screenheight()

        win = tk.Toplevel(self.app.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.configure(bg=BG)
        win.wm_attributes("-transparentcolor", BG)   # BG 透明 → 视觉圆角
        win.geometry(f"{W}x{H}+{sw - W - 20}+{sh - H - 62}")
        self.win = win

        # 卡片
        card = ctk.CTkFrame(win, width=W, height=H,
                            corner_radius=18, fg_color=CARD,
                            border_width=1, border_color="#223060")
        card.place(x=0, y=0)
        card.pack_propagate(False)

        # 关闭按钮
        ctk.CTkButton(card, text="✕", width=26, height=26,
                      fg_color="transparent", hover_color=SEC,
                      text_color=MUTED, font=ctk.CTkFont(size=13),
                      command=self._close).place(x=W - 36, y=8)

        # 图标
        ctk.CTkLabel(card, text="💧",
                     font=ctk.CTkFont(size=36)).pack(pady=(18, 0))

        # 标题
        ctk.CTkLabel(card, text="该喝水了！",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="white").pack(pady=(4, 2))

        # 进度
        cnt  = self.app.cfg["today_count"]
        goal = self.app.cfg["goal"]
        pct  = min(cnt / max(goal, 1), 1.0)

        ctk.CTkLabel(card, text=f"今日进度   {cnt} / {goal} 杯",
                     font=ctk.CTkFont(size=11), text_color=MUTED).pack()

        bar = ctk.CTkProgressBar(card, width=240, height=8,
                                  corner_radius=4,
                                  progress_color=BLUE, fg_color=SEC)
        bar.set(pct)
        bar.pack(pady=(6, 16))

        # 按钮行
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack()

        ctk.CTkButton(row, text="稍后提醒", width=110, height=36,
                      corner_radius=10, fg_color=SEC,
                      hover_color="#2A3A6A", text_color=MUTED,
                      font=ctk.CTkFont(size=12),
                      command=self._snooze).pack(side="left", padx=(0, 8))

        ctk.CTkButton(row, text="✓  已喝水", width=110, height=36,
                      corner_radius=10, fg_color=BLUE, hover_color=BLUE2,
                      text_color="white",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._drink).pack(side="left")

        self._fade_in(0.0)

    def _fade_in(self, a):
        if self.win and self.win.winfo_exists():
            a = min(a + 0.1, 1.0)
            self.win.attributes("-alpha", a)
            if a < 1.0:
                self.win.after(16, lambda: self._fade_in(a))

    def _close(self):
        if self.win and self.win.winfo_exists():
            self.win.destroy()
        self.win = None

    def _drink(self):
        self.app.drink()
        self._close()

    def _snooze(self):
        self.app.snooze()
        self._close()


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

        # 提醒间隔
        ctk.CTkLabel(win, text="提醒间隔",
                     font=ctk.CTkFont(size=12), text_color=MUTED,
                     anchor="w").pack(fill="x", padx=32)

        self._iv = ctk.IntVar(value=cfg["interval"])
        ctk.CTkSlider(win, from_=5, to=120, number_of_steps=23,
                      variable=self._iv,
                      button_color=BLUE, progress_color=BLUE,
                      fg_color=SEC, width=256).pack(padx=32, pady=(4, 0))

        self._il = ctk.CTkLabel(win, text=f"{cfg['interval']} 分钟",
                                 font=ctk.CTkFont(size=11), text_color=BLUE)
        self._il.pack()
        self._iv.trace_add("write",
            lambda *_: self._il.configure(text=f"{self._iv.get()} 分钟"))

        # 每日目标
        ctk.CTkLabel(win, text="每日目标",
                     font=ctk.CTkFont(size=12), text_color=MUTED,
                     anchor="w").pack(fill="x", padx=32, pady=(12, 0))

        self._gv = ctk.IntVar(value=cfg["goal"])
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=6)

        ctk.CTkButton(row, text="−", width=34, height=34,
                      fg_color=SEC, hover_color="#2A3A6A", text_color="white",
                      font=ctk.CTkFont(size=16),
                      command=lambda: self._gv.set(max(1, self._gv.get() - 1))
                      ).pack(side="left", padx=5)

        ctk.CTkLabel(row, textvariable=self._gv,
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white", width=46, anchor="center").pack(side="left")

        ctk.CTkButton(row, text="+", width=34, height=34,
                      fg_color=SEC, hover_color="#2A3A6A", text_color="white",
                      font=ctk.CTkFont(size=16),
                      command=lambda: self._gv.set(min(20, self._gv.get() + 1))
                      ).pack(side="left", padx=5)

        ctk.CTkLabel(row, text="杯 / 天",
                     font=ctk.CTkFont(size=12), text_color=MUTED).pack(side="left", padx=4)

        # 重置今日
        ctk.CTkButton(win, text="重置今日计数", width=160, height=32,
                      corner_radius=8, fg_color=SEC,
                      hover_color="#2A3A6A", text_color=MUTED,
                      font=ctk.CTkFont(size=11),
                      command=self._reset_today).pack(pady=(10, 0))

        # 保存
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
        cnt, goal = self.cfg["today_count"], self.cfg["goal"]
        self._tray.title = f"喝水提醒  {cnt}/{goal} 杯"

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

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("显示提醒",  lambda _, __: self.root.after(0, self.popup.show), default=True),
            pystray.MenuItem("设置",      lambda _, __: self.root.after(0, self.settings.show)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出",      self._quit),
        )
        self._tray = pystray.Icon("water", make_icon(), "喝水提醒", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self, _, __):
        self._tray.stop()
        self.root.after(0, self.root.quit)


if __name__ == "__main__":
    App()
