import tkinter as tk
import urllib.request
import socket

def get_my_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1)) 
        return sock.getsockname()[0]
    except OSError:
        return "не удалось узнать"
    finally:
        sock.close()

PORT = "8090"  # порт, на котором запущен TorrServer
ip = get_my_ip()
WARP_URL = "https://www.cloudflare.com/cdn-cgi/trace"


def get_status():
    try:
        url = "http://127.0.0.1:" + PORT + "/echo"
        version = urllib.request.urlopen(url, timeout=2).read().decode("utf-8").strip()
                
        line1 =  "TorrServer: работает, версия " + version + ", порт " + PORT
        line2 = f"Адрес для NUM/Lampa: http://{ip}:{PORT}"
        line3 = f"WARP: {checkWARP()}"
        return f"{line1}\n{line2}\n{line3}"
    except Exception:
        return "TorrServer: не отвечает (он запущен?)"
        
def checkWARP():
    try:
        text = urllib.request.urlopen(WARP_URL, timeout=3).read().decode("utf-8")
    except Exception:
        return "не удалось проверить"
 
    if "warp=on" in text or "warp=plus" in text:
        return "включён"
    return "выключен"


def copy_address():
    window.clipboard_clear()
    window.clipboard_append(f"http://{ip}:{PORT}")
    message.config(text="Адрес скопирован")

def refresh():
    label.config(text="Проверяю...")
    window.update() # "Проверяю..."
    label.config(text=get_status())
    message.config(text="")
 


window = tk.Tk()
window.title("Netorr")

label = tk.Label(window, text=get_status(), font=("Consolas", 14), padx=20, pady=20)
label.pack()


buttons = tk.Frame(window)
buttons.pack(pady=(0, 10))

tk.Button(buttons, text="Обновить", command=refresh).pack(side="left", padx=5)
tk.Button(buttons, text="Скопировать адрес", command=copy_address).pack(side="left", padx=5)

message = tk.Label(window, text="", fg="green")
message.pack(pady=(0, 10))

window.mainloop()
