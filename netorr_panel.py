import tkinter as tk
import urllib.request
import socket

PORT = "8090"  # порт, на котором запущен TorrServer
WARP_URL = "https://www.cloudflare.com/cdn-cgi/trace"


def get_status():
    try:
        url = "http://127.0.0.1:" + PORT + "/echo"
        version = urllib.request.urlopen(url, timeout=2).read().decode("utf-8").strip()
        
        ip = get_my_ip()
        
        line1 =  "TorrServer: работает, версия " + version + ", порт " + PORT
        line2 = f"Адрес для NUM/Lampa: http://{ip}:{PORT}"
        line3 = f"WARP: {checkWARP()}"
        return f"{line1}\n{line2}\n{line3}"
    except Exception:
        return "TorrServer: не отвечает (он запущен?)"
    
def get_my_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1)) 
        return sock.getsockname()[0]
    except OSError:
        return "не удалось узнать"
    finally:
        sock.close()
        
def checkWARP():
    try:
        text = urllib.request.urlopen(WARP_URL, timeout=3).read().decode("utf-8")
    except Exception:
        return "не удалось проверить"
 
    if "warp=on" in text or "warp=plus" in text:
        return "включён"
    return "ВЫКЛЮЧЕН"


window = tk.Tk()
window.title("Netorr")

label = tk.Label(window, text=get_status(), font=("Consolas", 14), padx=20, pady=20)
label.pack()

window.mainloop()
