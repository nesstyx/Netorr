import tkinter as tk
import urllib.request
import socket
import webbrowser
import subprocess
import time

def get_my_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1)) 
        return sock.getsockname()[0]
    except OSError:
        return "не удалось узнать"
    finally:
        sock.close()
        

def ping_host(host="1.1.1.1"):
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "2000", host],
            capture_output=True,
            text=True,
            encoding="cp866",
            errors="replace",
            timeout=4
        )

        if result.returncode == 0:
            return f"Узел {host} доступен\n{result.stdout}"

        return f"Нет ответа от {host}\n{result.stdout}"

    except subprocess.TimeoutExpired:
        return "Проверка Ping превысила время ожидания"

    except OSError as error:
        return f"Ошибка запуска Ping: {error}"
    

def check_dns(host="cloudflare.com"):
    try:
        addresses = socket.getaddrinfo(
            host,
            None,
            type=socket.SOCK_STREAM
        )

        ips = []

        for address in addresses:
            ip_address = address[4][0]

            if ip_address not in ips:
                ips.append(ip_address)

        if ips:
            return f"DNS работает: {host}\nIP: {', '.join(ips)}"

        return f"DNS не вернул адреса для {host}"

    except socket.gaierror as error:
        return f"Ошибка DNS для {host}: {error}"

    except OSError as error:
        return f"Ошибка сети: {error}"


def check_connection(url, name):
    start = time.perf_counter()

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Netorr/1.0"}
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            elapsed = (time.perf_counter() - start) * 1000

            return (
                f"{name}: доступен\n"
                f"HTTP: {response.status}\n"
                f"Время ответа: {elapsed:.0f} мс"
            )

    except Exception as error:
        elapsed = (time.perf_counter() - start) * 1000

        return (
            f"{name}: ошибка соединения\n"
            f"Причина: {error}\n"
            f"Время до ошибки: {elapsed:.0f} мс"
        )


PORT = "8090"  # порт, на котором запущен TorrServer
ip = get_my_ip()
WARP_URL = "https://www.cloudflare.com/cdn-cgi/trace"

TORRSERVER_URL = "https://github.com/YouROK/TorrServer"
NETORR_URL = "https://github.com/nesstyx/Netorr"
LAMPA_URL = "http://lampa.mx/"


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
window.minsize(900, 600)
window.configure(bg="#edf1f7")

BG = "#edf1f7"
PANEL = "#ffffff"
BORDER = "#d5deea"
BLUE = "#1769c2"
BLUE_HOVER = "#0f56a8"
TEXT = "#172b46"
MUTED = "#65758b"
GREEN = "#16834a"
RED = "#c63737"

window.option_add("*Font", ("Segoe UI", 10))

# Main menu
menu_bar = tk.Menu(window)
window.config(menu=menu_bar)

file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Обновить статус", command=refresh)
file_menu.add_command(label="Скопировать адрес", command=copy_address)
file_menu.add_separator()
file_menu.add_command(label="Выход", command=window.destroy)
menu_bar.add_cascade(label="Файл", menu=file_menu)

server_menu = tk.Menu(menu_bar, tearoff=0)
server_menu.add_command(label="Проверить статус", command=refresh)
server_menu.add_command(
    label="Открыть TorrServer",
    command=lambda: webbrowser.open(
        "http://127.0.0.1:" + PORT
    )
)
menu_bar.add_cascade(label="TorrServer", menu=server_menu)

links_menu = tk.Menu(menu_bar, tearoff=0)
links_menu.add_command(label="GitHub TorrServer", command=open_torrserver)
links_menu.add_command(label="GitHub Netorr", command=open_netorr)
links_menu.add_command(label="Lampa", command=open_lampa)
menu_bar.add_cascade(label="Ссылки", menu=links_menu)

menu_bar.add_cascade(
    label="Справка",
    menu=tk.Menu(menu_bar, tearoff=0)
)

# Header
header = tk.Frame(window, bg="#142c4d", padx=22, pady=16)
header.pack(fill="x")

tk.Label(
    header,
    text="Netorr",
    font=("Segoe UI", 23, "bold"),
    bg="#142c4d",
    fg="white"
).pack(side="left")

tk.Label(
    header,
    text="TorrServer Assistant",
    font=("Segoe UI", 11),
    bg="#142c4d",
    fg="#b9d8ff"
).pack(side="left", padx=16, pady=(8, 0))

tk.Button(
    header,
    text="⟳  Обновить",
    command=refresh,
    bg=BLUE,
    fg="white",
    activebackground=BLUE_HOVER,
    activeforeground="white",
    relief="flat",
    padx=14,
    pady=7,
    cursor="hand2"
).pack(side="right")

# Main content
content = tk.Frame(window, bg=BG, padx=16, pady=14)
content.pack(fill="both", expand=True)

content.columnconfigure(0, weight=1)
content.columnconfigure(1, weight=1)
content.rowconfigure(1, weight=1)

# Card helper
def make_card(parent, title, row, column, columnspan=1):
    card = tk.Frame(
        parent,
        bg=PANEL,
        highlightbackground=BORDER,
        highlightthickness=1,
        padx=14,
        pady=12
    )
    card.grid(
        row=row,
        column=column,
        columnspan=columnspan,
        sticky="nsew",
        padx=6,
        pady=6
    )

    tk.Label(
        card,
        text=title,
        font=("Segoe UI", 12, "bold"),
        bg=PANEL,
        fg=TEXT
    ).pack(anchor="w", pady=(0, 10))

    return card

# Server status
status_card = make_card(content, "Состояние TorrServer", 0, 0, 2)

label1 = tk.Label(
    status_card,
    text="Проверка...",
    font=("Consolas", 11),
    bg=PANEL,
    fg=TEXT,
    anchor="w",
    justify="left",
    wraplength=850
)
label1.pack(fill="x", pady=3)

label2 = tk.Label(
    status_card,
    text="",
    font=("Consolas", 11),
    bg=PANEL,
    fg=BLUE,
    anchor="w"
)
label2.pack(fill="x", pady=3)

tk.Button(
    status_card,
    text="Скопировать адрес",
    command=copy_address,
    bg="#e6f0ff",
    fg=BLUE,
    activebackground="#d4e5ff",
    relief="flat",
    padx=12,
    pady=5,
    cursor="hand2"
).pack(anchor="w", pady=(8, 4))

label3 = tk.Label(
    status_card,
    text="",
    font=("Segoe UI", 10),
    bg=PANEL,
    fg=MUTED,
    anchor="w"
)
label3.pack(fill="x", pady=3)

message = tk.Label(
    status_card,
    text="",
    font=("Segoe UI", 10),
    bg=PANEL,
    fg=GREEN,
    anchor="w"
)
message.pack(fill="x", pady=(4, 0))

# Diagnostics
diagnostics = make_card(content, "Диагностика соединения", 1, 0)

def run_diagnostics():
    diagnostics_result.config(
        text="Проверяю соединение...",
        fg=MUTED
    )
    window.update_idletasks()

    results = [
        ping_host(),
        check_dns("cloudflare.com"),
        check_connection(
            "http://127.0.0.1:" + PORT + "/echo",
            "TorrServer"
        ),
        check_connection(
            "https://www.cloudflare.com/cdn-cgi/trace",
            "Cloudflare"
        ),
        check_connection(
            "https://github.com",
            "GitHub"
        )
    ]

    diagnostics_result.config(
        text="\n\n".join(results),
        fg=TEXT
    )

tk.Button(
    diagnostics,
    text="Запустить диагностику",
    command=run_diagnostics,
    bg=BLUE,
    fg="white",
    activebackground=BLUE_HOVER,
    activeforeground="white",
    relief="flat",
    padx=12,
    pady=7,
    cursor="hand2"
).pack(fill="x", pady=(0, 10))

diagnostics_result = tk.Label(
    diagnostics,
    text="Нажми кнопку, чтобы проверить сеть.",
    bg=PANEL,
    fg=MUTED,
    justify="left",
    anchor="nw",
    wraplength=460
)
diagnostics_result.pack(fill="both", expand=True)

# Quick links
right = make_card(content, "Быстрые ссылки", 1, 1)

def link_button(parent, title, command):
    tk.Button(
        parent,
        text=title,
        command=command,
        bg="#f2f6fc",
        fg=TEXT,
        activebackground="#dce9fa",
        activeforeground=BLUE,
        relief="flat",
        anchor="w",
        padx=12,
        pady=9,
        cursor="hand2"
    ).pack(fill="x", pady=4)

link_button(right, "GitHub TorrServer", open_torrserver)
link_button(right, "GitHub Netorr", open_netorr)
link_button(right, "Lampa (веб)", open_lampa)

tk.Label(
    right,
    text="Netorr  •  TorrServer Matrix",
    bg=PANEL,
    fg=MUTED,
    font=("Segoe UI", 9)
).pack(anchor="w", pady=(18, 0))

# Footer
footer = tk.Frame(window, bg="#dfe7f1", padx=16, pady=8)
footer.pack(fill="x", side="bottom")

tk.Label(
    footer,
    text="●",
    fg=GREEN,
    bg="#dfe7f1"
).pack(side="left")

tk.Label(
    footer,
    text="Netorr готов к работе",
    fg=TEXT,
    bg="#dfe7f1"
).pack(side="left", padx=6)

tk.Label(
    footer,
    text="Python • Tkinter",
    fg=MUTED,
    bg="#dfe7f1"
).pack(side="right")

show_status()

window.after(300, run_diagnostics)

window.mainloop()
