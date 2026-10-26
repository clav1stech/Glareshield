"""Small always-on-top notice band for events the pilot must see while the simulator has the screen.

The window never takes focus and ignores the mouse, so it cannot interrupt the flight controls. It is
visible over a windowed or borderless simulator; exclusive full screen may still hide it, which the
test notification in the interface lets the pilot check.
"""
from __future__ import annotations

import gc
import queue
import threading
import time

WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x08000000
GWL_EXSTYLE, HWND_TOPMOST = -20, -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
VISIBLE_MAX = 6
POLL_MS = 250
MARGIN = 24


class Overlay:
    """Shows notices from any thread; Tk lives in one worker thread started on the first notice."""

    def __init__(self):
        self.pending: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.failed = False

    def show(self, lines: list[str], seconds: float = 10) -> None:
        if self.failed or not lines:
            return
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, name='glareshield-overlay', daemon=True)
            self.thread.start()
        self.pending.put((list(lines), seconds))

    def close(self) -> None:
        if self.thread is not None:
            self.pending.put(None)
            self.thread.join(2)
            self.thread = None

    def run(self) -> None:
        try:
            self.serve()
        except Exception:
            # No display or no Tk: notices are simply unavailable, never an error for the flight tools.
            self.failed = True
        # Tk objects must be released in the thread that created them, after serve() dropped its locals.
        gc.collect()

    def serve(self) -> None:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        window = tkinter.Toplevel(root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes('-topmost', True, '-alpha', .92)
        label = tkinter.Label(window, justify='left', anchor='w', bg='#10151f', fg='#e8eef7',
                              font=('Segoe UI', 12), padx=16, pady=12)
        label.pack()
        notices: list[tuple[str, float]] = []

        def tick():
            now = time.monotonic()
            try:
                while True:
                    item = self.pending.get_nowait()
                    if item is None:
                        root.destroy()
                        return
                    notices.extend((line, now+item[1]) for line in item[0])
            except queue.Empty:
                pass
            notices[:] = [item for item in notices if item[1] > now][-VISIBLE_MAX:]
            if notices:
                label.config(text='\n'.join(line for line, _ in notices))
                window.update_idletasks()
                window.geometry(f'+{root.winfo_screenwidth()-window.winfo_reqwidth()-MARGIN}+{MARGIN}')
                window.deiconify()
                self.pin(window)
            else:
                window.withdraw()
            root.after(POLL_MS, tick)

        root.after(POLL_MS, tick)
        root.mainloop()

    @staticmethod
    def pin(window) -> None:
        """Click-through, never activated, and kept above other topmost windows such as the simulator."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetParent.argtypes, user32.GetParent.restype = [wintypes.HWND], wintypes.HWND
        user32.GetWindowLongW.argtypes, user32.GetWindowLongW.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, wintypes.UINT]
        handle = user32.GetParent(window.winfo_id()) or window.winfo_id()
        style = user32.GetWindowLongW(handle, GWL_EXSTYLE)
        wanted = style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE
        if wanted != style:
            user32.SetWindowLongW(handle, GWL_EXSTYLE, wanted)
        user32.SetWindowPos(handle, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
