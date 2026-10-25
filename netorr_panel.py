import tkinter as tk
import urllib.request
import socket
import webbrowser

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

TORRSERVER_URL = "https://github.com/YouROK/TorrServer"
NETORR_URL = "https://github.com/nesstyx/Netorr"
LAMPA_URL = "http://lampa.mx/"

BG = "#0b1426"            # фон окна
CARD = "#111f3a"          # фон карточек
BORDER = "#24457d"        # рамка карточек
BUTTON = "#1a3a6e"        # кнопки
BUTTON_ACTIVE = "#2a5bb0" # кнопка в момент нажатия
TEXT = "#e8f0ff"          # основной текст
TITLE = "#4fb3ff"         # заголовки
GREEN = "#5ee08a"         # сообщения об успехе

def get_status():
    try:
        url = "http://127.0.0.1:" + PORT + "/echo"
        version = urllib.request.urlopen(url, timeout=2).read().decode("utf-8").strip()
                
        line1 =  "TorrServer: работает, версия " + version + ", порт " + PORT
        line2 = f"Адрес для NUM/Lampa: http://{ip}:{PORT}"
        line3 = f"WARP: {checkWARP()}"
        return line1, line2, line3
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
    label1.config(text="Проверяю...")
    label2.config(text="")
    label3.config(text="")
    window.update() # "Проверяю..."
    show_status()
    message.config(text="")
 
def open_torrserver():
        webbrowser.open(TORRSERVER_URL)
 
def open_netorr():
    webbrowser.open(NETORR_URL)
 
def open_lampa():
    webbrowser.open(LAMPA_URL)


def show_status():
    line1, line2, line3 = get_status()   # получили три строки сразу
    label1.config(text=line1)
    label2.config(text=line2)
    label3.config(text=line3)

window = tk.Tk()
window.title("Netorr")
window.geometry("1150x730")
 
left = tk.Frame(window)
left.pack(side="left", anchor="n", padx=20, pady=20)
 
right = tk.Frame(window)
right.pack(side="right", anchor="s", padx=20, pady=20)
 
center = tk.Frame(window)
center.pack(side="left", anchor="n", padx=20, pady=20)
 
 
# Слева: настройки Netorr
tk.Label(left, text="Настройки Netorr").pack(pady=(0, 10))
tk.Button(left, text="Обновить", command=refresh).pack()
 
# ИЗМЕНЕНО: по центру теперь три отдельные надписи, а кнопка копирования стоит рядом со второй
label1 = tk.Label(center, font=("Consolas", 14), padx=20)
label1.pack(anchor="w")
 
row = tk.Frame(center)    # строка, в которой рядом стоят адрес и кнопка
row.pack(anchor="w")
label2 = tk.Label(row, font=("Consolas", 14), padx=20)
label2.pack(side="left")
tk.Button(row, text="Скопировать адрес", command=copy_address).pack(side="left")
 
label3 = tk.Label(center, font=("Consolas", 14), padx=20)
label3.pack(anchor="w")
 
message = tk.Label(center, text="", fg="green")
message.pack(pady=10)
 
show_status()   # показать статус при запуске
 
# Справа снизу: быстрые ссылки
tk.Label(right, text="Быстрые ссылки").pack(pady=(0, 10))
tk.Button(right, text="GitHub TorrServer", command=open_torrserver).pack(fill="x", pady=2)
tk.Button(right, text="GitHub Netorr", command=open_netorr).pack(fill="x", pady=2)
tk.Button(right, text="Lampa (веб)", command=open_lampa).pack(fill="x", pady=2)
 
window.mainloop()
