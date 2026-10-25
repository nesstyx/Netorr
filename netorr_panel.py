import tkinter as tk
import urllib.request

PORT = "8090"  # порт, на котором запущен TorrServer


def get_status():
    """Спросить у TorrServer версию и вернуть готовую надпись."""
    try:
        url = "http://127.0.0.1:" + PORT + "/echo"
        version = urllib.request.urlopen(url, timeout=2).read().decode("utf-8").strip()
        return "TorrServer: работает, версия " + version + ", порт " + PORT
    except Exception:
        return "TorrServer: не отвечает (он запущен?)"


window = tk.Tk()
window.title("Netorr")

label = tk.Label(window, text=get_status(), font=("Consolas", 14), padx=20, pady=20)
label.pack()

window.mainloop()