
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib.util
import json
import os
import platform
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import winreg  # только Windows
except ImportError:
    winreg = None

try:
    import psutil  # необязательно
except ImportError:
    psutil = None

# ─────────────────────────────── Константы ────────────────────────────────

APP_NAME = "Netorr"
APP_VERSION = "2.4.2"
IS_WIN = platform.system() == "Windows"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0

if getattr(sys, "frozen", False):
    SCRIPT_DIR = Path(sys.executable).resolve().parent
else:
    SCRIPT_DIR = Path(__file__).resolve().parent

CONFIG_PATH = SCRIPT_DIR / "netorr_config.json"
PLUGINS_DIR = SCRIPT_DIR / "netorr_plugins"

WARP_URL = "https://www.cloudflare.com/cdn-cgi/trace"
TORRSERVER_URL = "https://github.com/YouROK/TorrServer"
NETORR_URL = "https://github.com/nesstyx/Netorr"
NETORR_ISSUES_URL = "https://github.com/nesstyx/Netorr/issues"
LAMPA_URL = "http://lampa.mx/"
RELEASES_API = "https://api.github.com/repos/YouROK/TorrServer/releases/latest"
SPEEDTEST_URL = "https://speed.cloudflare.com/__down?bytes=25000000"

# Цвета (тёмная тема как на скриншоте)
BG = "#07142a"
NAV = "#0a1b36"
PANEL = "#0d2042"
PANEL2 = "#0a1a36"
BORDER = "#1b3a6b"
BTN = "#10274c"
BTN_BORDER = "#1f4a86"
BTN_HOVER = "#17376a"
ACCENT = "#2d8cff"
ACCENT_DARK = "#1769c2"
CYAN = "#5cc8ff"
TEXT = "#e8f0ff"
MUTED = "#8ea6c9"
GREEN = "#2fd27a"
RED = "#ff4d4d"
YELLOW = "#ffc857"

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_H = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)
FONT_ICON = ("Segoe UI Symbol", 12)

DEFAULT_CONFIG = {
    "port": "8090",
    "num_port": "8090",
    "external_host": "",
    "torr_exe": "",
    "poll_interval": 2,
    "autorestart": False,
    "proxy_enabled": False,
    "proxy_url": "",
}


# ─────────────────────────────── Конфигурация ─────────────────────────────

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


CFG = load_config()


def save_config():
    try:
        CONFIG_PATH.write_text(json.dumps(CFG, ensure_ascii=False, indent=2), "utf-8")
    except OSError as error:
        log(f"Не удалось сохранить настройки Netorr: {error}", "err")


def valid_port(value):
    return str(value).isdigit() and 1 <= int(value) <= 65535


def port_int(key="port"):
    try:
        return int(CFG[key])
    except (ValueError, TypeError):
        return 8090


# ─────────────────────────────── Сеть ─────────────────────────────────────

LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
NET_OPENER = None


def rebuild_net_opener():
    global NET_OPENER
    if CFG["proxy_enabled"] and CFG["proxy_url"]:
        handler = urllib.request.ProxyHandler(
            {"http": CFG["proxy_url"], "https": CFG["proxy_url"]}
        )
    else:
        handler = urllib.request.ProxyHandler()
    NET_OPENER = urllib.request.build_opener(handler)


rebuild_net_opener()


def fetch(url, timeout=5, local=False, data=None, headers=None):
    all_headers = {"User-Agent": f"Netorr/{APP_VERSION}"}
    if headers:
        all_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=all_headers)
    opener = LOCAL_OPENER if local else NET_OPENER
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def base_url():
    return f"http://127.0.0.1:{CFG['port']}"


def api(path, payload=None, timeout=5):
    data = None
    headers = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    raw = fetch(base_url() + path, timeout, True, data, headers)
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def get_version():
    try:
        text = fetch(base_url() + "/echo", 2, True).decode("utf-8", "replace").strip()
        return text or None
    except Exception:
        return None


def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def host_address():
    host = CFG["external_host"].strip()
    host = re.sub(r"^https?://", "", host).rstrip("/")
    if not host:
        host = get_local_ip()
    return f"http://{host}:{CFG['num_port']}"


def tcp_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def oem_encoding():
    if IS_WIN:
        try:
            import ctypes
            return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        except Exception:
            return "cp866"
    return "utf-8"


OEM = oem_encoding()


def run_cmd(args, timeout=30):
    try:
        result = subprocess.run(
            args, capture_output=True, timeout=timeout, creationflags=NO_WINDOW
        )
        output = (result.stdout or b"") + (result.stderr or b"")
        return result.returncode, output.decode(OEM, "replace").strip()
    except subprocess.TimeoutExpired:
        return -1, "Превышено время ожидания"
    except OSError as error:
        return -2, f"Не удалось запустить {args[0]}: {error}"


def human_size(value):
    value = float(value)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024


def format_speed(bytes_per_second):
    if bytes_per_second >= 1024 * 1024:
        return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
    return f"{bytes_per_second / 1024:.0f} KB/s"


def open_path(path):
    path = str(path)
    try:
        if IS_WIN:
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as error:
        log(f"Не удалось открыть {path}: {error}", "err")


# ───────────────────────────── Потоки и UI-очередь ────────────────────────

root = None
W = SimpleNamespace()
STATE = {"version": None, "manual_stop": False, "was_running": False, "fails": 0}
UI_QUEUE = queue.Queue()


def ui_call(fn, *args, **kwargs):
    UI_QUEUE.put((fn, args, kwargs))


def _drain_queue():
    try:
        while True:
            fn, args, kwargs = UI_QUEUE.get_nowait()
            try:
                fn(*args, **kwargs)
            except Exception:
                traceback.print_exc()
    except queue.Empty:
        pass
    if root is not None:
        root.after(50, _drain_queue)


def bg(fn, *args):
    def runner():
        try:
            fn(*args)
        except Exception as error:
            traceback.print_exc()
            log(f"Ошибка: {error}", "err")

    threading.Thread(target=runner, daemon=True).start()


def log(message, kind="info"):
    ui_call(_log_impl, message, kind)


def _log_impl(message, kind="info"):
    box = getattr(W, "log", None)
    if box is None:
        print(message)
        return
    box.config(state="normal")
    box.insert("end", datetime.now().strftime("[%H:%M:%S] "), "ts")
    box.insert("end", str(message) + "\n", kind)
    lines = int(box.index("end-1c").split(".")[0])
    if lines > 600:
        box.delete("1.0", f"{lines - 600}.0")
    box.see("end")
    box.config(state="disabled")


def run_action(func, *args, box=None, busy=None, window=None):
    """Запускает func в потоке; результат (str | (str, kind)) выводится в лог/бокс/окно."""
    if busy:
        log(busy, "info")
        if box:
            box.set(busy)

    def work():
        try:
            result = func(*args)
        except Exception as error:
            traceback.print_exc()
            result = (f"Ошибка: {error}", "err")
        if result is None:
            return
        text, kind = result if isinstance(result, tuple) else (result, "info")
        ui_call(_finish_action, text, kind, box, window)

    threading.Thread(target=work, daemon=True).start()


def _finish_action(text, kind, box, window):
    if window:
        text_window(window, text)
    else:
        _log_impl(text, kind)
    if box:
        box.set(text)


# ───────────────────────────── Поиск TorrServer ───────────────────────────

def find_exe():
    saved = CFG.get("torr_exe")
    if saved and Path(saved).is_file():
        return Path(saved)
    candidates = [SCRIPT_DIR, Path.cwd(), Path.home() / "TorrServer", Path.home() / "Downloads"]
    if IS_WIN:
        candidates += [Path("C:/TorrServer"), Path("D:/TorrServer")]
    for folder in candidates:
        try:
            if not folder.is_dir():
                continue
            for item in sorted(folder.glob("[Tt]orr[Ss]erver*")):
                if not item.is_file() or item.suffix.lower() in (".py", ".log", ".db", ".json", ".bak", ".new"):
                    continue
                if IS_WIN and item.suffix.lower() != ".exe":
                    continue
                if not IS_WIN and not os.access(item, os.X_OK):
                    continue
                CFG["torr_exe"] = str(item)
                save_config()
                return item
        except OSError:
            continue
    return None


def ensure_exe():
    """Только из UI-потока: ищет TorrServer, при необходимости спрашивает путь."""
    exe = find_exe()
    if exe:
        return exe
    messagebox.showinfo(
        "TorrServer не найден",
        "Не удалось найти файл TorrServer.\nУкажите его вручную.",
    )
    path = filedialog.askopenfilename(
        title="Выберите файл TorrServer",
        filetypes=[("Программы", "*.exe" if IS_WIN else "*"), ("Все файлы", "*.*")],
    )
    if path:
        CFG["torr_exe"] = path
        save_config()
        return Path(path)
    return None


def torr_dir():
    exe = find_exe()
    return exe.parent if exe else None


# ───────────────────────────── Управление сервером ────────────────────────

def _start_impl(exe):
    if get_version():
        log("TorrServer уже запущен", "warn")
        return True
    directory = exe.parent
    try:
        logfile = open(directory / "torrserver.log", "ab")
        kwargs = {
            "cwd": str(directory),
            "stdout": logfile,
            "stderr": logfile,
            "stdin": subprocess.DEVNULL,
        }
        if IS_WIN:
            kwargs["creationflags"] = NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(
            [str(exe), "--port", str(CFG["port"]), "--path", str(directory)], **kwargs
        )
        logfile.close()
    except OSError as error:
        log(f"Не удалось запустить TorrServer: {error}", "err")
        return False
    STATE["manual_stop"] = False
    for _ in range(40):
        time.sleep(0.25)
        version = get_version()
        if version:
            log(f"TorrServer запущен ({version})", "ok")
            POLLER.event.set()
            return True
    log("TorrServer не ответил за 10 секунд — смотрите torrserver.log", "err")
    return False


def _stop_impl(quiet=False):
    if not get_version():
        if not quiet:
            log("TorrServer уже остановлен", "warn")
        return True
    STATE["manual_stop"] = True
    try:
        fetch(base_url() + "/shutdown", 3, True)
    except Exception:
        pass
    for _ in range(20):
        time.sleep(0.25)
        if not get_version():
            log("TorrServer остановлен", "ok")
            POLLER.event.set()
            return True
    exe = find_exe()
    if exe:
        if IS_WIN:
            run_cmd(["taskkill", "/F", "/IM", exe.name])
        else:
            run_cmd(["pkill", "-f", exe.name])
        time.sleep(1)
    if not get_version():
        log("TorrServer остановлен принудительно", "warn")
        POLLER.event.set()
        return True
    log("Не удалось остановить TorrServer", "err")
    return False


def start_server():
    exe = ensure_exe()
    if exe:
        log("Запускаю TorrServer...", "info")
        bg(_start_impl, exe)


def stop_server():
    log("Останавливаю TorrServer...", "info")
    bg(_stop_impl)


def restart_server(auto=False):
    exe = ensure_exe()
    if not exe:
        return
    log("Автоперезапуск TorrServer..." if auto else "Перезапускаю TorrServer...", "warn" if auto else "info")

    def work():
        _stop_impl(quiet=True)
        time.sleep(0.5)
        _start_impl(exe)

    bg(work)


def refresh_now():
    log("Проверка статуса...", "info")
    POLLER.event.set()


# ───────────────────────────── Опрос состояния ────────────────────────────

def get_traffic_counters():
    text = fetch(base_url() + "/stat", 2, True).decode("utf-8", "replace")
    down = re.search(r"BytesReadData:\s*(?:\([^)]*\)\s*)?(\d+)", text)
    up = re.search(r"BytesWrittenData:\s*(?:\([^)]*\)\s*)?(\d+)", text)
    if not down or not up:
        raise ValueError("Не найдены счётчики трафика")
    return int(down.group(1)), int(up.group(1))


def parse_trace(text):
    result = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


class Poller(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.event = threading.Event()
        self.tick = 0
        self.prev = None
        self.torrents = []
        self.warp = None
        self.lan_ip = "127.0.0.1"

    def run(self):
        time.sleep(0.3)
        while True:
            try:
                self.poll()
            except Exception:
                traceback.print_exc()
            self.tick += 1
            try:
                interval = max(1.0, float(CFG["poll_interval"]))
            except (ValueError, TypeError):
                interval = 2.0
            self.event.wait(interval)
            self.event.clear()

    def poll(self):
        started = time.perf_counter()
        version = get_version()
        ms = (time.perf_counter() - started) * 1000 if version else None
        if self.tick % 15 == 0:
            self.lan_ip = get_local_ip()
        state = {
            "version": version,
            "ms": ms,
            "port_open": tcp_open("127.0.0.1", port_int(), 0.5),
            "ip": self.lan_ip,
        }
        state["num_ok"] = bool(version) and tcp_open(self.lan_ip, port_int("num_port"), 0.5)

        down_speed = up_speed = 0.0
        counters_ok = False
        if version:
            try:
                down_bytes, up_bytes = get_traffic_counters()
                now = time.perf_counter()
                if self.prev:
                    elapsed = now - self.prev[2]
                    if elapsed > 0:
                        down_speed = max(0, down_bytes - self.prev[0]) / elapsed
                        up_speed = max(0, up_bytes - self.prev[1]) / elapsed
                self.prev = (down_bytes, up_bytes, now)
                counters_ok = True
            except Exception:
                self.prev = None
            if self.tick % 2 == 0:
                try:
                    data = api("/torrents", {"action": "list"})
                    self.torrents = data if isinstance(data, list) else []
                except Exception:
                    self.torrents = []
            if self.tick % 15 == 0:
                try:
                    settings = api("/settings", {"action": "get"})
                    if isinstance(settings, dict):
                        state["settings"] = settings
                except Exception:
                    pass
        else:
            self.prev = None
            self.torrents = []

        if version and not counters_ok:
            down_speed = sum(float(t.get("download_speed") or 0) for t in self.torrents)
            up_speed = sum(float(t.get("upload_speed") or 0) for t in self.torrents)

        if self.tick % 10 == 0:
            try:
                trace = parse_trace(fetch(WARP_URL, 3).decode("utf-8", "replace"))
                self.warp = trace.get("warp", "off")
            except Exception:
                self.warp = None

        state.update(
            down=down_speed,
            up=up_speed,
            peers=sum(int(t.get("active_peers") or 0) for t in self.torrents),
            seeds=sum(int(t.get("connected_seeders") or 0) for t in self.torrents),
            torrents=list(self.torrents),
            warp=self.warp,
        )
        ui_call(apply_status, state)


POLLER = Poller()


# ───────────────────────────── Действия (без UI) ──────────────────────────

def ping_host(host="1.1.1.1"):
    if IS_WIN:
        args = ["ping", "-n", "2", "-w", "2000", host]
    else:
        args = ["ping", "-c", "2", "-W", "2", host]
    code, output = run_cmd(args, timeout=15)
    if code == 0:
        return f"Узел {host} доступен\n{output}", "ok"
    return f"Нет ответа от {host}\n{output}", "err"


def check_dns(host="cloudflare.com"):
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ips = []
        for info in infos:
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
        if ips:
            return f"DNS работает: {host}\nIP: {', '.join(ips)}", "ok"
        return f"DNS не вернул адреса для {host}", "err"
    except socket.gaierror as error:
        return f"Ошибка DNS для {host}: {error}", "err"
    except OSError as error:
        return f"Ошибка сети: {error}", "err"


def check_connection(url, name, local=False):
    started = time.perf_counter()
    try:
        opener = LOCAL_OPENER if local else NET_OPENER
        request = urllib.request.Request(url, headers={"User-Agent": f"Netorr/{APP_VERSION}"})
        with opener.open(request, timeout=5) as response:
            elapsed = (time.perf_counter() - started) * 1000
            return (
                f"{name}: доступен\nHTTP: {response.status}\nВремя ответа: {elapsed:.0f} мс",
                "ok",
            )
    except Exception as error:
        elapsed = (time.perf_counter() - started) * 1000
        return (
            f"{name}: ошибка соединения\nПричина: {error}\nВремя до ошибки: {elapsed:.0f} мс",
            "err",
        )


def act_diagnostics():
    parts = [
        ping_host()[0],
        check_dns("cloudflare.com")[0],
        check_connection(base_url() + "/echo", "TorrServer", local=True)[0],
        check_connection(WARP_URL, "Cloudflare")[0],
        check_connection("https://github.com", "GitHub")[0],
    ]
    return "=== Диагностика соединения ===\n" + "\n\n".join(parts), "info"


def act_check_ports():
    ip = get_local_ip()
    checks = [
        ("TorrServer (локально)", "127.0.0.1", port_int()),
        ("TorrServer (в сети)", ip, port_int()),
        ("NUM/Lampa", ip, port_int("num_port")),
    ]
    lines = []
    bad = False
    for name, host, port in checks:
        ok = tcp_open(host, port, 1.5)
        bad = bad or not ok
        lines.append(f"{'✔' if ok else '✘'} {name}: {host}:{port} — {'открыт' if ok else 'закрыт'}")
    if bad:
        lines.append("Подсказка: проверьте, что TorrServer запущен и брандмауэр разрешает порт.")
    return "\n".join(lines), ("err" if bad else "ok")


def act_check_port_custom(host, port):
    if not valid_port(port):
        return "Некорректный порт", "err"
    ok = tcp_open(host, int(port), 3)
    return f"{host}:{port} — {'открыт' if ok else 'закрыт или недоступен'}", ("ok" if ok else "err")


def act_check_address():
    address = host_address()
    started = time.perf_counter()
    try:
        text = fetch(address + "/echo", 4, True).decode("utf-8", "replace").strip()
        elapsed = (time.perf_counter() - started) * 1000
        return f"Адрес {address} отвечает: «{text}» ({elapsed:.0f} мс)", "ok"
    except Exception as error:
        return f"Адрес {address} недоступен: {error}", "err"


def act_connections():
    port = str(port_int())
    if IS_WIN:
        code, output = run_cmd(["netstat", "-ano"], 20)
    else:
        code, output = run_cmd(["ss", "-tn"], 20)
    lines = [l for l in output.splitlines() if f":{port}" in l]
    if not lines:
        return f"Активных соединений с портом {port} нет"
    return f"Соединения с портом {port}: {len(lines)}\n" + "\n".join(lines)


def act_speedtest():
    started = time.perf_counter()
    total = 0
    first_byte = None
    try:
        request = urllib.request.Request(SPEEDTEST_URL, headers={"User-Agent": f"Netorr/{APP_VERSION}"})
        with NET_OPENER.open(request, timeout=10) as response:
            while True:
                chunk = response.read(65536)
                if first_byte is None:
                    first_byte = (time.perf_counter() - started) * 1000
                if not chunk:
                    break
                total += len(chunk)
                if time.perf_counter() - started > 12:
                    break
    except Exception as error:
        return f"Тест скорости не удался: {error}", "err"
    elapsed = time.perf_counter() - started
    if elapsed <= 0 or total == 0:
        return "Нет данных для расчёта скорости", "err"
    mbit = total * 8 / elapsed / 1_000_000
    return (
        f"Скорость загрузки: {mbit:.1f} Мбит/с ({total / elapsed / 1048576:.2f} МБ/с)\n"
        f"Получено: {human_size(total)} за {elapsed:.1f} с, задержка {first_byte or 0:.0f} мс",
        "ok",
    )


def act_vpn_check():
    try:
        trace = parse_trace(fetch(WARP_URL, 5).decode("utf-8", "replace"))
    except Exception as error:
        return f"Не удалось получить данные: {error}", "err"
    warp = trace.get("warp", "?")
    return (
        f"Внешний IP: {trace.get('ip', '?')}\nСтрана: {trace.get('loc', '?')}\n"
        f"Дата-центр: {trace.get('colo', '?')}\nWARP: {'включён' if warp in ('on', 'plus') else 'выключен'}",
        "ok" if warp in ("on", "plus") else "warn",
    )


def act_reset_warp():
    cli = shutil.which("warp-cli")
    if not cli:
        return "warp-cli не найден. Установите Cloudflare WARP (1.1.1.1) и добавьте его в PATH.", "warn"
    run_cmd([cli, "disconnect"], 15)
    time.sleep(1.5)
    code, output = run_cmd([cli, "connect"], 15)
    POLLER.event.set()
    return f"WARP переподключён\n{output}", ("ok" if code == 0 else "err")


def act_toggle_vpn():
    cli = shutil.which("warp-cli")
    if not cli:
        return "VPN-клиент (warp-cli) не найден. Переключите VPN вручную.", "warn"
    _, status = run_cmd([cli, "status"], 10)
    connected = "connected" in status.lower() and "disconnected" not in status.lower()
    code, output = run_cmd([cli, "disconnect" if connected else "connect"], 15)
    POLLER.event.set()
    return f"VPN {'отключён' if connected else 'включён'}\n{output}", ("ok" if code == 0 else "err")


def act_reset_connections():
    lines = []
    if IS_WIN:
        _, out = run_cmd(["ipconfig", "/flushdns"], 15)
        lines.append(out)
    else:
        lines.append("DNS-кэш сбрасывается средствами вашей ОС (resolvectl flush-caches)")
    try:
        torrents = api("/torrents", {"action": "list"})
        if isinstance(torrents, list):
            for torrent in torrents:
                api("/torrents", {"action": "drop", "hash": torrent.get("hash")})
            lines.append(f"Освобождено торрентов из памяти: {len(torrents)}")
    except Exception:
        pass
    return "Соединения сброшены\n" + "\n".join(lines), "ok"


def act_flush_dns():
    if not IS_WIN:
        return "Доступно только в Windows", "warn"
    _, out = run_cmd(["ipconfig", "/flushdns"], 15)
    return out, "ok"


def act_trace(host):
    args = (
        ["tracert", "-d", "-h", "20", "-w", "1000", host]
        if IS_WIN
        else ["traceroute", "-n", "-m", "20", host]
    )
    _, out = run_cmd(args, 120)
    return f"Трассировка до {host}\n{out}"


def act_disk():
    directory = torr_dir() or SCRIPT_DIR
    usage = shutil.disk_usage(directory)
    percent = usage.used / usage.total * 100
    return (
        f"Диск с TorrServer ({directory})\nВсего: {human_size(usage.total)}\n"
        f"Занято: {human_size(usage.used)} ({percent:.0f}%)\nСвободно: {human_size(usage.free)}",
        "warn" if usage.free < 5 * 1024 ** 3 else "ok",
    )


def act_scan():
    ip = get_local_ip()
    if ip.startswith("127."):
        return "Не удалось определить локальную сеть", "err"
    prefix = ip.rsplit(".", 1)[0]
    ports = [port_int(), 80, 443, 445, 22]

    def probe(i):
        host = f"{prefix}.{i}"
        return host, [p for p in ports if tcp_open(host, p, 0.4)]

    with ThreadPoolExecutor(max_workers=100) as pool:
        results = [r for r in pool.map(probe, range(1, 255)) if r[1]]
    lines = [f"Сканирование {prefix}.0/24 — найдено устройств: {len(results)}"]
    for host, open_ports in results:
        note = ""
        if port_int() in open_ports:
            try:
                version = fetch(f"http://{host}:{port_int()}/echo", 2, True).decode().strip()
                note = f"  ← TorrServer {version}"
            except Exception:
                pass
        suffix = "  (этот ПК)" if host == ip else ""
        lines.append(f"{host}: порты {', '.join(map(str, open_ports))}{note}{suffix}")
    return "\n".join(lines), "ok"


def get_settings():
    data = api("/settings", {"action": "get"})
    return data if isinstance(data, dict) else None


def set_torr_setting(key, value):
    settings = get_settings()
    if settings is None:
        raise RuntimeError("TorrServer не отвечает")
    settings[key] = value
    api("/settings", {"action": "set", "sets": settings})


# ── Очистка ──

def safe_clear_dir(path):
    """Удаляет содержимое папки, но не её саму. Возвращает (файлов, байт)."""
    count = size = 0
    for item in Path(path).iterdir():
        try:
            if item.is_dir() and not item.is_symlink():
                for sub in item.rglob("*"):
                    if sub.is_file():
                        size += sub.stat().st_size
                        count += 1
                shutil.rmtree(item, ignore_errors=True)
            else:
                size += item.stat().st_size
                count += 1
                item.unlink()
        except OSError:
            continue
    return count, size


def act_clear_cache():
    torrents = api("/torrents", {"action": "list"})
    if not isinstance(torrents, list) or not torrents:
        return "Кэш TorrServer пуст (активных торрентов нет)", "ok"
    for torrent in torrents:
        api("/torrents", {"action": "drop", "hash": torrent.get("hash")})
    return f"Кэш очищен: освобождено торрентов — {len(torrents)}", "ok"


def act_clean_temp():
    temp = Path(tempfile.gettempdir())
    count = size = 0
    for item in temp.iterdir():
        name = item.name.lower()
        if not name.startswith(("torrserver", "torrent", "netorr")):
            continue
        try:
            if item.is_dir():
                for sub in item.rglob("*"):
                    if sub.is_file():
                        size += sub.stat().st_size
                        count += 1
                shutil.rmtree(item, ignore_errors=True)
            else:
                size += item.stat().st_size
                count += 1
                item.unlink()
        except OSError:
            continue
    return f"Временные файлы удалены: {count} шт., {human_size(size)}", "ok"


def act_clean_logs():
    directory = torr_dir()
    cleared = 0
    if directory:
        for item in directory.glob("*.log"):
            try:
                item.write_bytes(b"")
                cleared += 1
            except OSError:
                continue
    ui_call(clear_log_widget)
    return f"Логи очищены (файлов: {cleared})", "ok"


def act_delete_old(days):
    torrents = api("/torrents", {"action": "list"})
    if not isinstance(torrents, list):
        return "Не удалось получить список торрентов", "err"
    limit = time.time() - days * 86400
    removed = 0
    for torrent in torrents:
        stamp = torrent.get("timestamp") or 0
        if stamp and stamp < limit:
            api("/torrents", {"action": "rem", "hash": torrent.get("hash")})
            removed += 1
    return f"Удалено торрентов старше {days} дн.: {removed} из {len(torrents)}", "ok"


def downloads_path():
    try:
        settings = get_settings() or {}
    except Exception:
        settings = {}
    return (settings.get("TorrentsSavePath") or "").strip()


def act_clear_downloads(path):
    count, size = safe_clear_dir(path)
    return f"Загрузки очищены: {count} файл(ов), {human_size(size)}", "ok"


# ── Конфиг ──

def act_backup():
    directory = torr_dir()
    if not directory:
        return "Папка TorrServer не найдена", "err"
    target = directory / "backups" / datetime.now().strftime("config_%Y%m%d_%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in directory.iterdir():
        if item.is_file() and item.suffix.lower() in (".db", ".json", ".ls") and item.name != CONFIG_PATH.name:
            try:
                shutil.copy2(item, target / item.name)
                copied += 1
            except OSError:
                continue
    if copied == 0:
        return "Файлы конфигурации (config.db / settings.json) не найдены", "warn"
    return f"Резервная копия создана ({copied} файл.):\n{target}", "ok"


def act_restore(folder):
    directory = torr_dir()
    if not directory:
        return "Папка TorrServer не найдена", "err"
    exe = find_exe()
    was_running = bool(get_version())
    if was_running:
        _stop_impl(quiet=True)
    copied = 0
    for item in Path(folder).iterdir():
        if item.is_file():
            try:
                shutil.copy2(item, directory / item.name)
                copied += 1
            except OSError as error:
                log(f"Не удалось восстановить {item.name}: {error}", "err")
    if was_running and exe:
        _start_impl(exe)
    return f"Конфигурация восстановлена из {folder} (файлов: {copied})", "ok"


def act_reset_config():
    backup = act_backup()[0]
    api("/settings", {"action": "def"})
    return f"Настройки TorrServer сброшены к значениям по умолчанию.\n{backup}", "ok"


# ── Обновление ──

def version_key(text):
    numbers = [int(x) for x in re.findall(r"\d+", text or "")]
    return tuple((numbers + [0, 0, 0])[:3])


def asset_name():
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(platform.system(), "linux")
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("i386", "i686", "x86"):
        arch = "386"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif machine.startswith("armv7"):
        arch = "arm7"
    else:
        arch = "amd64"
    return f"TorrServer-{system}-{arch}" + (".exe" if IS_WIN else "")


def update_info_worker(install):
    try:
        release = json.loads(fetch(RELEASES_API, 10).decode("utf-8"))
    except Exception as error:
        log(f"Не удалось получить информацию об обновлении: {error}", "err")
        return
    tag = release.get("tag_name", "?")
    current = STATE.get("version")
    newer = current is None or version_key(tag) > version_key(current)
    ui_call(on_update_info, release, tag, current, newer, install)


def on_update_info(release, tag, current, newer, install):
    if not install:
        if newer:
            log(f"Доступно обновление: {tag} (сейчас: {current or 'неизвестно'})", "warn")
        else:
            log(f"У вас последняя версия ({current}, на GitHub: {tag})", "ok")
        return
    if newer:
        question = f"Установить TorrServer {tag}?\nТекущая версия: {current or 'неизвестно'}"
    else:
        question = f"Версия {current} уже актуальна (GitHub: {tag}).\nПереустановить?"
    if not messagebox.askyesno("Обновить Matrix", question):
        return
    exe = ensure_exe()
    if exe:
        bg(download_and_install, release, exe)


def download_and_install(release, exe):
    wanted = asset_name()
    asset = next((a for a in release.get("assets", []) if a.get("name") == wanted), None)
    if not asset:
        log(f"В релизе нет файла {wanted}", "err")
        return
    tmp = exe.with_name(exe.name + ".new")
    log(f"Скачиваю {wanted} ({human_size(asset.get('size', 0))})...", "info")
    try:
        request = urllib.request.Request(
            asset["browser_download_url"], headers={"User-Agent": f"Netorr/{APP_VERSION}"}
        )
        total = int(asset.get("size") or 0)
        done = 0
        last = -1
        with NET_OPENER.open(request, timeout=30) as response, open(tmp, "wb") as out:
            while True:
                chunk = response.read(262144)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    percent = done * 100 // total // 25 * 25
                    if percent != last:
                        last = percent
                        log(f"Загрузка: {done * 100 // total}%", "info")
    except Exception as error:
        log(f"Ошибка загрузки: {error}", "err")
        try:
            tmp.unlink()
        except OSError:
            pass
        return
    was_running = bool(get_version())
    if was_running:
        _stop_impl(quiet=True)
        time.sleep(1)
    backup = exe.with_name(exe.name + ".bak")
    try:
        if exe.exists():
            shutil.copy2(exe, backup)
        os.replace(tmp, exe)
        if not IS_WIN:
            os.chmod(exe, 0o755)
    except OSError as error:
        log(f"Не удалось заменить файл: {error}", "err")
        return
    log(f"TorrServer обновлён до {release.get('tag_name')} (старый файл: {backup.name})", "ok")
    if was_running:
        _start_impl(exe)


# ── Автозапуск ──

AUTORUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_autostart():
    if not (IS_WIN and winreg):
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY) as key:
            winreg.QueryValueEx(key, "TorrServer")
            return True
    except OSError:
        return False


def set_autostart(enable):
    if not (IS_WIN and winreg):
        return False, "Автозапуск поддерживается только в Windows"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                exe = find_exe()
                if not exe:
                    return False, "Сначала укажите путь к TorrServer"
                command = f'"{exe}" --port {CFG["port"]} --path "{exe.parent}"'
                winreg.SetValueEx(key, "TorrServer", 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, "TorrServer")
                except FileNotFoundError:
                    pass
        return True, "Автозапуск включён" if enable else "Автозапуск выключен"
    except OSError as error:
        return False, f"Ошибка реестра: {error}"


# ── Системная информация ──

def memory_info():
    if psutil:
        mem = psutil.virtual_memory()
        return f"{human_size(mem.used)} / {human_size(mem.total)} ({mem.percent:.0f}%)"
    if IS_WIN:
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            used = stat.ullTotalPhys - stat.ullAvailPhys
            return f"{human_size(used)} / {human_size(stat.ullTotalPhys)} ({stat.dwMemoryLoad}%)"
        except Exception:
            pass
    return "нет данных (установите psutil)"


def system_info_text():
    directory = torr_dir() or SCRIPT_DIR
    usage = shutil.disk_usage(directory)
    lines = [
        f"ОС:            {platform.platform()}",
        f"Имя ПК:        {socket.gethostname()}",
        f"Python:        {platform.python_version()}",
        f"Процессор:     {platform.processor() or platform.machine()} ({os.cpu_count()} потоков)",
        f"Память:        {memory_info()}",
        f"Диск ({directory}):",
        f"               свободно {human_size(usage.free)} из {human_size(usage.total)}",
        f"Локальный IP:  {get_local_ip()}",
        f"TorrServer:    {find_exe() or 'не найден'}",
        f"Версия:        {STATE.get('version') or 'не запущен'}",
    ]
    if psutil:
        lines.insert(5, f"Загрузка CPU:  {psutil.cpu_percent(interval=0.3):.0f}%")
    return "\n".join(lines)


def act_report():
    parts = [
        f"Netorr {APP_VERSION} — отчёт {datetime.now():%Y-%m-%d %H:%M:%S}",
        system_info_text(),
        act_check_ports()[0],
        act_diagnostics()[0],
    ]
    return "\n\n".join(parts)


# ───────────────────────────── Виджеты ────────────────────────────────────

class FlatButton(tk.Frame):
    def __init__(self, parent, text, command, icon="", icon_fg=ACCENT, compact=False, bg=BTN):
        super().__init__(parent, bg=bg, highlightbackground=BTN_BORDER, highlightthickness=1, cursor="hand2")
        self._bg = bg
        self.command = command
        self.widgets = [self]
        if compact:
            self.icon = tk.Label(self, text=icon, font=("Segoe UI Symbol", 17), fg=icon_fg, bg=bg)
            self.icon.pack(pady=(7, 0))
            self.label = tk.Label(self, text=text, font=FONT_SMALL, fg=TEXT, bg=bg,
                                  justify="center", wraplength=96)
            self.label.pack(pady=(0, 7), padx=4)
        else:
            self.icon = tk.Label(self, text=icon, font=FONT_ICON, fg=icon_fg, bg=bg, width=3)
            self.icon.pack(side="left", padx=(6, 2), pady=6)
            self.label = tk.Label(self, text=text, font=FONT, fg=TEXT, bg=bg, anchor="w")
            self.label.pack(side="left", fill="x", expand=True, pady=6, padx=(0, 8))
        self.widgets += [self.icon, self.label]
        for widget in self.widgets:
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            widget.bind("<Button-1>", self._click)

    def _paint(self, color):
        for widget in self.widgets:
            widget.config(bg=color)

    def _enter(self, _event):
        self._paint(BTN_HOVER)

    def _leave(self, _event):
        self._paint(self._bg)

    def _click(self, _event):
        try:
            self.command()
        except Exception as error:
            traceback.print_exc()
            log(f"Ошибка: {error}", "err")


class Toggle(tk.Canvas):
    def __init__(self, parent, value=False, command=None, bg=PANEL):
        super().__init__(parent, width=40, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.value = bool(value)
        self.command = command
        self.bind("<Button-1>", self._click)
        self.draw()

    def draw(self):
        self.delete("all")
        color = ACCENT if self.value else "#3a4a66"
        self.create_oval(1, 1, 21, 21, fill=color, outline=color)
        self.create_oval(19, 1, 39, 21, fill=color, outline=color)
        self.create_rectangle(11, 1, 29, 21, fill=color, outline=color)
        cx = 29 if self.value else 11
        self.create_oval(cx - 8, 3, cx + 8, 19, fill="white", outline="white")

    def set(self, value):
        self.value = bool(value)
        self.draw()

    def _click(self, _event):
        self.value = not self.value
        self.draw()
        if self.command:
            self.command(self.value)


class OutputBox(tk.Frame):
    def __init__(self, parent, height=10):
        super().__init__(parent, bg=PANEL2, highlightbackground=BORDER, highlightthickness=1)
        self.text = tk.Text(self, height=height, bg=PANEL2, fg=TEXT, font=FONT_MONO, relief="flat",
                            wrap="word", state="disabled", insertbackground=TEXT, padx=8, pady=6)
        scroll = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

    def set(self, text):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", text)
        self.text.config(state="disabled")


class ScrollFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))


def make_card(parent, title, icon="", icon_fg=ACCENT):
    card = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
    head = tk.Frame(card, bg=PANEL)
    head.pack(fill="x", padx=12, pady=(10, 6))
    if icon:
        tk.Label(head, text=icon, font=("Segoe UI Symbol", 13), fg=icon_fg, bg=PANEL).pack(side="left", padx=(0, 8))
    tk.Label(head, text=title, font=FONT_H, fg=TEXT, bg=PANEL).pack(side="left")
    body = tk.Frame(card, bg=PANEL)
    body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    card.body = body
    card.head = head
    return card


def make_entry(parent, variable, width=12, show=None):
    return tk.Entry(parent, textvariable=variable, width=width, bg=PANEL2, fg=TEXT, insertbackground=TEXT,
                    relief="flat", font=FONT, highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=ACCENT, show=show or "")


def small_button(parent, text, command):
    button = tk.Label(parent, text=text, font=FONT_SMALL, fg=ACCENT, bg=PANEL2, padx=10, pady=5,
                      cursor="hand2", highlightbackground=BTN_BORDER, highlightthickness=1)
    button.bind("<Button-1>", lambda e: command())
    button.bind("<Enter>", lambda e: button.config(bg=BTN_HOVER))
    button.bind("<Leave>", lambda e: button.config(bg=PANEL2))
    return button


def buttons_column(card, specs):
    for icon, text, command, color in specs:
        FlatButton(card.body, text, command, icon=icon, icon_fg=color).pack(fill="x", pady=3)


def new_window(title, width, height):
    window = tk.Toplevel(root)
    window.title(title)
    window.geometry(f"{width}x{height}")
    window.configure(bg=BG)
    window.transient(root)
    return window


def text_window(title, text, width=720, height=460):
    window = new_window(title, width, height)
    box = OutputBox(window, height=20)
    box.pack(fill="both", expand=True, padx=10, pady=(10, 4))
    box.set(text)

    def copy():
        root.clipboard_clear()
        root.clipboard_append(text)

    row = tk.Frame(window, bg=BG)
    row.pack(fill="x", padx=10, pady=(0, 10))
    small_button(row, "Копировать", copy).pack(side="left")
    small_button(row, "Закрыть", window.destroy).pack(side="right")
    return window


# ───────────────────────────── Действия с UI ──────────────────────────────

def clear_log_widget():
    W.log.config(state="normal")
    W.log.delete("1.0", "end")
    W.log.config(state="disabled")


def copy_address():
    root.clipboard_clear()
    root.clipboard_append(host_address())
    log(f"Адрес скопирован: {host_address()}", "ok")


def confirm(title, question):
    return messagebox.askyesno(title, question, icon="warning")


def ui_clear_cache():
    run_action(act_clear_cache, busy="Очищаю кэш TorrServer...")


def ui_clean_temp():
    if confirm("Временные файлы", "Удалить временные файлы TorrServer/Netorr из папки TEMP?"):
        run_action(act_clean_temp, busy="Очищаю временные файлы...")


def ui_clean_logs():
    if confirm("Логи", "Очистить файлы логов (*.log) TorrServer и окно логов?"):
        run_action(act_clean_logs)


def ui_delete_old():
    days = simpledialog.askinteger("Старые торренты", "Удалить торренты старше N дней:",
                                   initialvalue=30, minvalue=1, maxvalue=3650, parent=root)
    if days and confirm("Удаление", f"Удалить из TorrServer все торренты старше {days} дн.?"):
        run_action(act_delete_old, days, busy="Ищу старые торренты...")


def ui_clear_downloads():
    def work():
        path = downloads_path()
        ui_call(_after_path, path)

    def _after_path(path):
        if not path:
            log("Путь загрузок на диск не задан — TorrServer хранит данные в памяти/кэше", "warn")
            return
        target = Path(path)
        if not target.is_dir():
            log(f"Папка загрузок не найдена: {path}", "warn")
            return
        if target.parent == target or target == Path.home():
            log("Отказ: слишком опасный путь для очистки", "err")
            return
        if confirm("Очистить загрузки",
                   f"БУДЕТ УДАЛЕНО всё содержимое папки:\n\n{path}\n\nПродолжить?"):
            run_action(act_clear_downloads, path, busy="Очищаю загрузки...")

    bg(work)


def ui_open_folder():
    directory = torr_dir()
    if directory:
        open_path(directory)
    else:
        log("Папка TorrServer не найдена — запустите/укажите TorrServer", "warn")


def ui_open_config():
    directory = torr_dir()
    if not directory:
        log("Папка TorrServer не найдена", "warn")
        return
    for name in ("settings.json", "config.db"):
        if (directory / name).exists():
            open_path(directory / name)
            return
    open_path(directory)
    log("Файл конфигурации не найден, открыта папка", "warn")


def ui_reset_config():
    if confirm("Сбросить конфигурацию",
               "Настройки TorrServer будут сброшены к значениям по умолчанию.\n"
               "Перед этим будет создана резервная копия. Продолжить?"):
        run_action(act_reset_config, busy="Сбрасываю конфигурацию...")


def ui_backup():
    run_action(act_backup, busy="Создаю резервную копию...")


def ui_restore():
    directory = torr_dir()
    start = (directory / "backups") if directory and (directory / "backups").is_dir() else directory
    folder = filedialog.askdirectory(title="Выберите папку резервной копии", initialdir=str(start or SCRIPT_DIR))
    if folder and confirm("Восстановить", f"Восстановить конфигурацию из:\n{folder}\n\nTorrServer будет перезапущен."):
        run_action(act_restore, folder, busy="Восстанавливаю конфигурацию...")


def ui_check_updates():
    log("Проверяю обновления на GitHub...", "info")
    bg(update_info_worker, False)


def ui_update_matrix():
    log("Получаю информацию о последнем релизе...", "info")
    bg(update_info_worker, True)


def ui_autostart(value, toggle):
    ok, message = set_autostart(value)
    log(message, "ok" if ok else "err")
    if not ok:
        toggle.set(not value)
        if not IS_WIN:
            return


def ui_open_browser():
    webbrowser.open(base_url())


def ui_reset_warp():
    run_action(act_reset_warp, busy="Переподключаю WARP...")


def ui_stats_window():
    window = new_window("Статистика TorrServer", 760, 500)
    box = OutputBox(window, height=24)
    box.pack(fill="both", expand=True, padx=10, pady=10)
    box.set("Загрузка...")

    def refresh():
        if not window.winfo_exists():
            return

        def work():
            try:
                text = fetch(base_url() + "/stat", 3, True).decode("utf-8", "replace")
            except Exception as error:
                text = f"Не удалось получить /stat: {error}"
            ui_call(apply, text)

        bg(work)
        window.after(3000, refresh)

    def apply(text):
        if window.winfo_exists():
            box.set(text)

    refresh()


def ask_host(title, default):
    return simpledialog.askstring(title, "Адрес узла (IP или домен):", initialvalue=default, parent=root)


def ui_ping():
    host = ask_host("Ping", "1.1.1.1")
    if host:
        run_action(ping_host, host.strip(), busy=f"Ping {host}...")


def ui_trace():
    host = ask_host("Трассировка", "1.1.1.1")
    if host:
        run_action(act_trace, host.strip(), busy=f"Трассировка до {host} (до 2 минут)...", window=None)


def ui_dns_check():
    host = ask_host("Проверка DNS", "cloudflare.com")
    if host:
        run_action(check_dns, host.strip())


def ui_scan():
    run_action(act_scan, busy="Сканирую локальную сеть (5–10 секунд)...", window="Сканер сети")


def ui_reboot():
    if not IS_WIN:
        log("Перезагрузка из Netorr поддерживается только в Windows", "warn")
        return
    if confirm("Перезагрузка ПК", "Перезагрузить компьютер через 30 секунд?"):
        run_cmd(["shutdown", "/r", "/t", "30", "/c", "Перезагрузка из Netorr"])
        if messagebox.askyesno("Перезагрузка", "Компьютер перезагрузится через 30 секунд.\nОтменить перезагрузку?"):
            run_cmd(["shutdown", "/a"])
            log("Перезагрузка отменена", "ok")
        else:
            log("Перезагрузка через 30 секунд", "warn")


def ui_change_dns():
    if not IS_WIN:
        log("Смена DNS поддерживается только в Windows", "warn")
        return
    window = new_window("Смена DNS", 460, 380)
    tk.Label(window, text="Сетевой адаптер:", fg=TEXT, bg=BG, font=FONT).pack(anchor="w", padx=16, pady=(14, 2))
    code, output = run_cmd(["netsh", "interface", "show", "interface"], 15)
    adapters = []
    for line in output.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 4 and parts[0].lower() in ("connected", "подключен"):
            adapters.append(parts[-1])
    adapter_var = tk.StringVar(value=adapters[0] if adapters else "Ethernet")
    ttk.Combobox(window, textvariable=adapter_var, values=adapters or ["Ethernet", "Wi-Fi"]).pack(
        fill="x", padx=16)
    presets = {
        "Cloudflare (1.1.1.1 / 1.0.0.1)": ("1.1.1.1", "1.0.0.1"),
        "Google (8.8.8.8 / 8.8.4.4)": ("8.8.8.8", "8.8.4.4"),
        "Yandex (77.88.8.8 / 77.88.8.1)": ("77.88.8.8", "77.88.8.1"),
        "Автоматически (DHCP)": None,
    }
    choice = tk.StringVar(value="Cloudflare (1.1.1.1 / 1.0.0.1)")
    for name in presets:
        tk.Radiobutton(window, text=name, variable=choice, value=name, fg=TEXT, bg=BG, selectcolor=PANEL2,
                       activebackground=BG, activeforeground=TEXT, font=FONT).pack(anchor="w", padx=16, pady=2)
    tk.Label(window, text="Нужны права администратора (запустите Netorr от имени администратора).",
             fg=YELLOW, bg=BG, font=FONT_SMALL, wraplength=420, justify="left").pack(anchor="w", padx=16, pady=8)

    def apply():
        adapter = adapter_var.get().strip()
        preset = presets[choice.get()]

        def work():
            if preset is None:
                results = [run_cmd(["netsh", "interface", "ip", "set", "dns", f"name={adapter}", "source=dhcp"], 20)]
            else:
                results = [
                    run_cmd(["netsh", "interface", "ip", "set", "dns", f"name={adapter}", "static", preset[0]], 20),
                    run_cmd(["netsh", "interface", "ip", "add", "dns", f"name={adapter}", preset[1], "index=2"], 20),
                ]
            bad = [r for r in results if r[0] != 0]
            if bad:
                return f"Не удалось сменить DNS ({adapter}):\n{bad[0][1]}", "err"
            return f"DNS для «{adapter}» изменён: {choice.get()}", "ok"

        run_action(work, busy="Меняю DNS...")
        window.destroy()

    small_button(window, "Применить", apply).pack(pady=6)


# ── Прокси ──

def ui_proxy_dialog():
    window = new_window("Настроить прокси", 480, 230)
    url_var = tk.StringVar(value=CFG["proxy_url"])
    enabled_var = tk.BooleanVar(value=CFG["proxy_enabled"])
    tk.Label(window, text="Адрес HTTP-прокси (например http://127.0.0.1:8080):", fg=TEXT, bg=BG,
             font=FONT).pack(anchor="w", padx=16, pady=(16, 4))
    make_entry(window, url_var, 48).pack(padx=16, fill="x")
    tk.Checkbutton(window, text="Использовать прокси для проверок Netorr", variable=enabled_var, fg=TEXT,
                   bg=BG, selectcolor=PANEL2, activebackground=BG, activeforeground=TEXT).pack(anchor="w", padx=16, pady=8)
    tk.Label(window, text="Прокси применяется к проверкам интернета, обновлениям и тесту скорости.\n"
                          "Запросы к локальному TorrServer всегда идут напрямую.",
             fg=MUTED, bg=BG, font=FONT_SMALL, justify="left").pack(anchor="w", padx=16)

    def save():
        url = url_var.get().strip()
        if enabled_var.get() and not re.match(r"^https?://", url):
            messagebox.showerror("Прокси", "Адрес должен начинаться с http:// или https://", parent=window)
            return
        CFG["proxy_url"] = url
        CFG["proxy_enabled"] = enabled_var.get()
        save_config()
        rebuild_net_opener()
        sync_proxy_widgets()
        log("Настройки прокси сохранены" + (" (включён)" if CFG["proxy_enabled"] else " (выключен)"), "ok")
        window.destroy()

    row = tk.Frame(window, bg=BG)
    row.pack(pady=14)
    small_button(row, "Сохранить", save).pack(side="left", padx=6)
    small_button(row, "Отмена", window.destroy).pack(side="left", padx=6)


def sync_proxy_widgets():
    if hasattr(W, "proxy_toggle"):
        W.proxy_toggle.set(CFG["proxy_enabled"])
    if hasattr(W, "proxy_var"):
        W.proxy_var.set(CFG["proxy_url"])


def on_proxy_toggle(value):
    if value and not CFG["proxy_url"]:
        W.proxy_toggle.set(False)
        ui_proxy_dialog()
        return
    CFG["proxy_enabled"] = value
    save_config()
    rebuild_net_opener()
    log("Прокси " + ("включён" if value else "выключен"), "ok")


def ui_check_proxy():
    if not CFG["proxy_url"]:
        log("Прокси не настроен", "warn")
        return
    run_action(act_vpn_check, busy="Проверяю внешний адрес (через прокси, если включён)...")


# ── Плагины ──

EXAMPLE_PLUGIN = '''# Пример плагина Netorr.
# Файл должен лежать в папке netorr_plugins и содержать NAME и run(api).
NAME = "Пример: версия TorrServer"
DESCRIPTION = "Пишет в лог версию TorrServer"


def run(api):
    api.log("Версия TorrServer: " + str(api.get_version()), "ok")
'''


class PluginAPI:
    version = APP_VERSION
    cfg = CFG

    @staticmethod
    def log(message, kind="info"):
        log(message, kind)

    @staticmethod
    def get_version():
        return get_version()

    @staticmethod
    def torr_api(path, payload=None):
        return api(path, payload)

    @staticmethod
    def address():
        return host_address()


def list_plugins():
    PLUGINS_DIR.mkdir(exist_ok=True)
    return sorted(PLUGINS_DIR.glob("*.py"))


def load_plugin(path):
    spec = importlib.util.spec_from_file_location(f"netorr_plugin_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ui_plugins():
    window = new_window("Управление плагинами", 560, 420)
    tk.Label(window, text="Плагины — это Python-файлы из папки netorr_plugins.\n"
                          "Запускайте только те плагины, которым доверяете.",
             fg=YELLOW, bg=BG, font=FONT_SMALL, justify="left").pack(anchor="w", padx=12, pady=(10, 4))
    listbox = tk.Listbox(window, bg=PANEL2, fg=TEXT, font=FONT, relief="flat", selectbackground=ACCENT_DARK,
                         highlightthickness=1, highlightbackground=BORDER, activestyle="none")
    listbox.pack(fill="both", expand=True, padx=12, pady=4)
    info = tk.Label(window, text="", fg=MUTED, bg=BG, font=FONT_SMALL, anchor="w", justify="left")
    info.pack(fill="x", padx=12)
    paths = []

    def reload():
        listbox.delete(0, "end")
        paths.clear()
        for path in list_plugins():
            name = path.stem
            try:
                name = getattr(load_plugin(path), "NAME", path.stem)
            except Exception:
                name = f"{path.stem} (ошибка загрузки)"
            paths.append(path)
            listbox.insert("end", f"{name}   [{path.name}]")

    def run_selected():
        selection = listbox.curselection()
        if not selection:
            return
        path = paths[selection[0]]
        try:
            module = load_plugin(path)
            module.run(PluginAPI)
            info.config(text=f"Плагин {path.name} выполнен", fg=GREEN)
        except Exception as error:
            info.config(text=f"Ошибка плагина: {error}", fg=RED)
            log(f"Ошибка плагина {path.name}: {error}", "err")

    def create_example():
        PLUGINS_DIR.mkdir(exist_ok=True)
        target = PLUGINS_DIR / "example_plugin.py"
        if not target.exists():
            target.write_text(EXAMPLE_PLUGIN, "utf-8")
        reload()

    row = tk.Frame(window, bg=BG)
    row.pack(fill="x", padx=12, pady=10)
    small_button(row, "▶ Запустить", run_selected).pack(side="left", padx=(0, 6))
    small_button(row, "Создать пример", create_example).pack(side="left", padx=6)
    small_button(row, "Открыть папку", lambda: (PLUGINS_DIR.mkdir(exist_ok=True), open_path(PLUGINS_DIR))).pack(
        side="left", padx=6)
    small_button(row, "Обновить", reload).pack(side="left", padx=6)
    reload()


def ui_lampa_settings():
    show_app_settings("Настройки Lampa", "Lampa", LAMPA_URL)


def ui_num_settings():
    show_app_settings("Настройки NUM", "NUM", None)


def show_app_settings(title, app, web_url):
    window = new_window(title, 520, 330)
    address = host_address()
    tk.Label(window, text=f"Адрес TorrServer для {app}:", fg=TEXT, bg=BG, font=FONT).pack(anchor="w", padx=16, pady=(16, 4))
    var = tk.StringVar(value=address)
    entry = make_entry(window, var, 46)
    entry.pack(padx=16, fill="x")
    steps = (
        f"1. Откройте {app} → Настройки → TorrServer.\n"
        f"2. В поле «Ссылка» вставьте адрес выше.\n"
        f"3. Устройство должно быть в той же сети, что и этот ПК.\n"
        f"4. Если {app} не видит сервер — проверьте порт {CFG['num_port']} и брандмауэр."
    )
    tk.Label(window, text=steps, fg=MUTED, bg=BG, font=FONT_SMALL, justify="left").pack(anchor="w", padx=16, pady=12)
    row = tk.Frame(window, bg=BG)
    row.pack(pady=4)
    small_button(row, "Копировать адрес", copy_address).pack(side="left", padx=5)
    small_button(row, "Проверить доступность", lambda: run_action(act_check_address)).pack(side="left", padx=5)
    if web_url:
        small_button(row, "Открыть Lampa", lambda: webbrowser.open(web_url)).pack(side="left", padx=5)
    tk.Label(window, text="Порт и внешний IP/домен меняются в блоке «Настройки TorrServer» на главной.",
             fg=MUTED, bg=BG, font=FONT_SMALL).pack(pady=6)


def ui_other_tools():
    window = new_window("Другие инструменты", 380, 330)
    tk.Label(window, text="Дополнительно", fg=TEXT, bg=BG, font=FONT_H).pack(anchor="w", padx=16, pady=(14, 6))
    tools = [
        ("＋", "Добавить magnet-ссылку", ui_add_magnet, GREEN),
        ("▤", "Экспорт отчёта диагностики", ui_export_report, ACCENT),
        ("⧉", "Скопировать адрес", copy_address, ACCENT),
        ("▣", "Папка Netorr", lambda: open_path(SCRIPT_DIR), YELLOW),
        ("⚙", "Файл настроек Netorr", lambda: open_path(CONFIG_PATH) if CONFIG_PATH.exists() else save_config(), MUTED),
    ]
    for icon, text, command, color in tools:
        FlatButton(window, text, command, icon=icon, icon_fg=color).pack(fill="x", padx=16, pady=3)


def ui_export_report():
    path = filedialog.asksaveasfilename(
        title="Сохранить отчёт", defaultextension=".txt",
        initialfile=f"netorr_report_{datetime.now():%Y%m%d_%H%M}.txt",
        filetypes=[("Текстовый файл", "*.txt")],
    )
    if not path:
        return

    def work():
        Path(path).write_text(act_report(), "utf-8")
        return f"Отчёт сохранён: {path}", "ok"

    run_action(work, busy="Собираю отчёт...")


def ui_add_magnet():
    link = simpledialog.askstring("Добавить торрент", "Вставьте magnet-ссылку:", parent=root)
    if not link:
        return
    link = link.strip()
    if not link.startswith("magnet:"):
        messagebox.showerror("Ошибка", "Ссылка должна начинаться с magnet:")
        return

    def work():
        api("/torrents", {"action": "add", "link": link, "save_to_db": True}, timeout=20)
        POLLER.event.set()
        return "Торрент добавлен в TorrServer", "ok"

    run_action(work, busy="Добавляю торрент...")


# ── Консоль ──

def handle_command(event=None):
    raw = W.console_var.get().strip()
    W.console_var.set("")
    if not raw:
        return
    log("> " + raw, "cmd")
    parts = raw.split()
    cmd, args = parts[0].lower(), parts[1:]
    if cmd == "help":
        log("Команды: help, status, start, stop, restart, ping [хост], dns [хост], trace [хост], "
            "port <порт>, ip, version, backup, clear", "info")
    elif cmd == "status":
        refresh_now()
    elif cmd == "start":
        start_server()
    elif cmd == "stop":
        stop_server()
    elif cmd == "restart":
        restart_server()
    elif cmd == "ping":
        run_action(ping_host, args[0] if args else "1.1.1.1")
    elif cmd == "dns":
        run_action(check_dns, args[0] if args else "cloudflare.com")
    elif cmd == "trace":
        run_action(act_trace, args[0] if args else "1.1.1.1", busy="Трассировка...")
    elif cmd == "port" and args:
        run_action(act_check_port_custom, "127.0.0.1", args[0])
    elif cmd == "ip":
        log(f"Локальный IP: {get_local_ip()}  |  Адрес: {host_address()}", "info")
    elif cmd == "version":
        log(f"Netorr {APP_VERSION}; TorrServer: {STATE.get('version') or 'не запущен'}", "info")
    elif cmd == "backup":
        ui_backup()
    elif cmd == "clear":
        clear_log_widget()
    else:
        log("Неизвестная команда. Введите help", "warn")


# ───────────────────────────── Применение состояния ───────────────────────

def warp_view(warp):
    if warp in ("on", "plus"):
        return "ВКЛЮЧЁН", GREEN
    if warp == "off":
        return "ВЫКЛЮЧЕН", RED
    return "НЕИЗВЕСТНО", YELLOW


def set_row(row, text, color):
    row.config(text=text, fg=color)


def apply_status(st):
    STATE.update({k: v for k, v in st.items() if k not in ("torrents", "settings")})
    version = st["version"]
    running = version is not None
    port = CFG["port"]
    address = host_address()
    warp_text, warp_color = warp_view(st["warp"])

    W.hdr_dot.config(fg=GREEN if running else RED)
    if running:
        W.hdr1.config(text=f"TorrServer: работает, версия {version}, порт {port}", fg=TEXT)
    else:
        W.hdr1.config(text=f"TorrServer: не запущен (порт {port})", fg=RED)
    W.hdr_addr.config(text=address)
    W.hdr_warp.config(text=warp_text, fg=warp_color)

    set_row(W.mini["ts"], "Работает" if running else "Остановлен", GREEN if running else RED)
    set_row(W.mini["port"], "Открыт" if st["port_open"] else "Закрыт", GREEN if st["port_open"] else RED)
    set_row(W.mini["num"], "Доступен" if st["num_ok"] else "Недоступен", GREEN if st["num_ok"] else RED)
    set_row(W.mini["warp"], warp_text.capitalize(), warp_color)

    W.speed_down.config(text=format_speed(st["down"]))
    W.speed_up.config(text=format_speed(st["up"]))
    W.peers.config(text=str(st["peers"]))
    W.seeds.config(text=str(st["seeds"]))

    W.info["version"].config(text=version.replace("MatriX", "Matrix") if running else "—")
    W.info["port"].config(text=str(port))
    W.info["num"].config(text=str(CFG["num_port"]))
    W.info["addr"].config(text=address)
    set_row(W.info["warp"], warp_text.capitalize(), warp_color)
    W.info["ms"].config(text=f"{st['ms']:.0f} мс" if st["ms"] is not None else "—")

    W.server_dot.config(fg=GREEN if running else RED)
    W.footer_status.config(text="Готово к работе" if running else "TorrServer не запущен",
                           fg=TEXT if running else YELLOW)
    W.footer_dot.config(fg=GREEN if running else YELLOW)
    W.footer_right.config(text=f"Netorr {APP_VERSION}   |   TorrServer {version or '—'}   |   {address.replace('http://', '')}")

    settings = st.get("settings")
    if settings:
        W.dht_toggle.set(not settings.get("DisableDHT", False))
        W.upnp_toggle.set(not settings.get("DisableUPNP", False))

    if CURRENT_PAGE[0] == "torrents":
        fill_torrents(st["torrents"])
    if CURRENT_PAGE[0] == "system":
        pass

    # Автоперезапуск
    if running:
        STATE["was_running"] = True
        STATE["fails"] = 0
    else:
        STATE["fails"] += 1
        if (CFG["autorestart"] and STATE["was_running"] and not STATE["manual_stop"]
                and STATE["fails"] >= 3):
            STATE["fails"] = 0
            restart_server(auto=True)


# ───────────────────────────── Построение UI ──────────────────────────────

PAGES = {}
NAV_BUTTONS = {}
CURRENT_PAGE = ["main"]
SCROLLERS = {}


def show_page(name):
    for key, frame in PAGES.items():
        frame.pack_forget()
    PAGES[name].pack(fill="both", expand=True)
    CURRENT_PAGE[0] = name
    for key, button in NAV_BUTTONS.items():
        button.config(bg=ACCENT_DARK if key == name else NAV, fg="white" if key == name else TEXT)
    if name == "system":
        refresh_system()
    elif name == "files":
        refresh_files()
    elif name == "torrents":
        POLLER.event.set()


def build_nav(parent):
    nav = tk.Frame(parent, bg=NAV, padx=10, pady=8)
    nav.pack(fill="x")
    tabs = [
        ("main", "Главная"), ("torrents", "Торрсервер"), ("ports", "Порты"), ("proxy", "Прокси / VPN"),
        ("files", "Файлы"), ("system", "Система"), ("settings", "Настройки"), ("help", "Справка"),
    ]
    for key, title in tabs:
        button = tk.Label(nav, text=title, font=("Segoe UI", 11), fg=TEXT, bg=NAV, padx=16, pady=7, cursor="hand2")
        button.pack(side="left", padx=2)
        button.bind("<Button-1>", lambda e, k=key: show_page(k))
        NAV_BUTTONS[key] = button
    right = tk.Frame(nav, bg=NAV)
    right.pack(side="right")
    tk.Label(right, text="●", fg=GREEN, bg=NAV).pack(side="right", padx=(8, 0))
    tk.Label(right, text="Программа запущена", fg=GREEN, bg=NAV, font=FONT).pack(side="right")
    tk.Label(right, text=f"⚙ Версия {APP_VERSION}", fg=CYAN, bg=NAV, font=FONT).pack(side="right", padx=18)


def build_logo(parent):
    canvas = tk.Canvas(parent, width=96, height=96, bg=BG, highlightthickness=0)
    canvas.create_oval(4, 4, 92, 92, fill=ACCENT_DARK, outline=ACCENT, width=3)
    canvas.create_oval(14, 14, 82, 82, fill="#0b2a58", outline="")
    canvas.create_text(48, 48, text="T", fill="white", font=("Segoe UI", 44, "bold"))
    return canvas


def build_header(parent):
    header = tk.Frame(parent, bg=BG)
    header.columnconfigure(1, weight=1)

    brand = tk.Frame(header, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
    brand.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    build_logo(brand).pack(side="left", padx=14, pady=12)
    text = tk.Frame(brand, bg=PANEL)
    text.pack(side="left", padx=(0, 16))
    tk.Label(text, text="Netorr", font=("Segoe UI", 30, "bold"), fg="white", bg=PANEL).pack(anchor="w")
    tk.Label(text, text="TorrServer Assistant", font=("Segoe UI", 15), fg=CYAN, bg=PANEL).pack(anchor="w")
    tk.Label(text, text="Управляй. Очищай. Загружай. Быстрее.", font=FONT_SMALL, fg=ACCENT, bg=PANEL).pack(anchor="w", pady=(4, 0))

    status = tk.Frame(header, bg=PANEL2, highlightbackground=BORDER, highlightthickness=1)
    status.grid(row=0, column=1, sticky="nsew", padx=6)
    W.hdr_dot = tk.Label(status, text="●", fg=YELLOW, bg=PANEL2, font=("Segoe UI", 14))
    W.hdr_dot.pack(side="left", padx=(14, 8), anchor="n", pady=14)
    lines = tk.Frame(status, bg=PANEL2)
    lines.pack(side="left", fill="both", expand=True, pady=12)
    W.hdr1 = tk.Label(lines, text="Проверка...", font=FONT_MONO, fg=TEXT, bg=PANEL2, anchor="w")
    W.hdr1.pack(fill="x", pady=2)
    row = tk.Frame(lines, bg=PANEL2)
    row.pack(fill="x", pady=2)
    tk.Label(row, text="Адрес для NUM/Lampa: ", font=FONT_MONO, fg=TEXT, bg=PANEL2).pack(side="left")
    W.hdr_addr = tk.Label(row, text="—", font=FONT_MONO, fg=ACCENT, bg=PANEL2, cursor="hand2")
    W.hdr_addr.pack(side="left")
    W.hdr_addr.bind("<Button-1>", lambda e: copy_address())
    row = tk.Frame(lines, bg=PANEL2)
    row.pack(fill="x", pady=2)
    tk.Label(row, text="WARP: ", font=FONT_MONO, fg=TEXT, bg=PANEL2).pack(side="left")
    W.hdr_warp = tk.Label(row, text="—", font=("Consolas", 10, "bold"), fg=MUTED, bg=PANEL2)
    W.hdr_warp.pack(side="left")

    mini = tk.Frame(header, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
    mini.grid(row=0, column=2, sticky="nsew", padx=6)
    W.mini = {}
    for key, icon, title in (("ts", "⏻", "TorrServer"), ("port", "◉", "Порт"), ("num", "☁", "NUM/Lampa"), ("warp", "▲", "WARP")):
        row = tk.Frame(mini, bg=PANEL)
        row.pack(fill="x", padx=12, pady=3)
        tk.Label(row, text=icon, fg=MUTED, bg=PANEL, font=FONT_ICON, width=2).pack(side="left")
        label_text = f"{title} {CFG['port']}" if key == "port" else title
        W.mini[key + "_title"] = tk.Label(row, text=label_text, fg=TEXT, bg=PANEL, font=FONT, width=14, anchor="w")
        W.mini[key + "_title"].pack(side="left")
        W.mini[key] = tk.Label(row, text="—", fg=MUTED, bg=PANEL, font=FONT, anchor="e", width=11)
        W.mini[key].pack(side="right")

    speed = tk.Frame(header, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
    speed.grid(row=0, column=3, sticky="nsew", padx=(6, 0))
    tk.Label(speed, text="Скорость (сейчас)", fg=MUTED, bg=PANEL, font=FONT_SMALL).pack(anchor="w", padx=12, pady=(8, 2))
    row = tk.Frame(speed, bg=PANEL)
    row.pack(fill="x", padx=12)
    tk.Label(row, text="↓", fg=CYAN, bg=PANEL, font=("Segoe UI", 14, "bold")).pack(side="left")
    W.speed_down = tk.Label(row, text="0.0 MB/s", fg=TEXT, bg=PANEL, font=("Segoe UI", 12), width=10, anchor="w")
    W.speed_down.pack(side="left", padx=(2, 12))
    tk.Label(row, text="↑", fg=GREEN, bg=PANEL, font=("Segoe UI", 14, "bold")).pack(side="left")
    W.speed_up = tk.Label(row, text="0.0 MB/s", fg=TEXT, bg=PANEL, font=("Segoe UI", 12), width=10, anchor="w")
    W.speed_up.pack(side="left", padx=2)
    row = tk.Frame(speed, bg=PANEL)
    row.pack(fill="x", padx=12, pady=(6, 8))
    for title, attr in (("Пиры", "peers"), ("Сидов", "seeds")):
        col = tk.Frame(row, bg=PANEL)
        col.pack(side="left", expand=True, fill="x")
        tk.Label(col, text=title, fg=MUTED, bg=PANEL, font=FONT_SMALL).pack(anchor="w")
        label = tk.Label(col, text="0", fg=TEXT, bg=PANEL, font=("Segoe UI", 14))
        label.pack(anchor="w")
        setattr(W, attr, label)
    return header


def build_quick_actions(parent):
    card = make_card(parent, "Быстрые действия")
    buttons_column(card, [
        ("▶", "Запустить TorrServer", start_server, GREEN),
        ("■", "Остановить TorrServer", stop_server, RED),
        ("⟳", "Перезапустить", restart_server, ACCENT),
        ("∿", "Проверить статус", refresh_now, CYAN),
    ])
    return card


def build_cleanup(parent):
    card = make_card(parent, "Очистка и обслуживание")
    buttons_column(card, [
        ("🗑", "Очистить кэш TorrServer", ui_clear_cache, ACCENT),
        ("◷", "Очистить временные файлы", ui_clean_temp, ACCENT),
        ("▤", "Очистить логи", ui_clean_logs, ACCENT),
        ("⚠", "Удалить старые торренты", ui_delete_old, YELLOW),
        ("⇩", "Очистить загрузки", ui_clear_downloads, ACCENT),
    ])
    return card


def build_files_card(parent):
    card = make_card(parent, "Файлы и конфигурация")
    buttons_column(card, [
        ("📁", "Открыть папку TorrServer", ui_open_folder, YELLOW),
        ("▤", "Открыть конфиг", ui_open_config, ACCENT),
        ("↺", "Сбросить конфигурацию", ui_reset_config, ACCENT),
        ("◰", "Резервная копия конфига", ui_backup, ACCENT),
        ("◲", "Восстановить конфиг", ui_restore, ACCENT),
    ])
    return card


def build_logs(parent):
    card = make_card(parent, "Логи / Статус", "▤", ACCENT)
    FlatButton(card.head, "Очистить", clear_log_widget, icon="🗑").pack(side="right")
    frame = tk.Frame(card.body, bg=PANEL2, highlightbackground=BORDER, highlightthickness=1)
    frame.pack(fill="both", expand=True)
    W.log = tk.Text(frame, height=11, bg=PANEL2, fg=TEXT, font=FONT_MONO, relief="flat", wrap="word",
                    state="disabled", padx=8, pady=6, highlightthickness=0)
    scroll = ttk.Scrollbar(frame, command=W.log.yview)
    W.log.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    W.log.pack(side="left", fill="both", expand=True)
    for tag, color in (("ts", GREEN), ("info", CYAN), ("ok", GREEN), ("err", RED), ("warn", YELLOW), ("cmd", "white")):
        W.log.tag_configure(tag, foreground=color)
    row = tk.Frame(card.body, bg=PANEL2, highlightbackground=BORDER, highlightthickness=1)
    row.pack(fill="x", pady=(6, 0))
    tk.Label(row, text=">", fg=CYAN, bg=PANEL2, font=FONT_MONO).pack(side="left", padx=(8, 4))
    W.console_var = tk.StringVar()
    entry = tk.Entry(row, textvariable=W.console_var, bg=PANEL2, fg=TEXT, insertbackground=TEXT,
                     relief="flat", font=FONT_MONO)
    entry.pack(side="left", fill="x", expand=True, pady=5)
    entry.bind("<Return>", handle_command)
    return card


def build_server_mgmt(parent):
    card = make_card(parent, "Управление сервером", "⚙", ACCENT)
    W.server_dot = tk.Label(card.head, text="●", fg=YELLOW, bg=PANEL)
    W.server_dot.pack(side="right")
    buttons_column(card, [
        ("⟳", "Перезапустить TorrServer", restart_server, ACCENT),
        ("⇩", "Обновить Matrix", ui_update_matrix, ACCENT),
        ("☁", "Проверить обновления", ui_check_updates, ACCENT),
    ])
    row = tk.Frame(card.body, bg=BTN, highlightbackground=BTN_BORDER, highlightthickness=1)
    row.pack(fill="x", pady=3)
    tk.Label(row, text="⏻", fg=ACCENT, bg=BTN, font=FONT_ICON, width=3).pack(side="left", padx=(6, 2), pady=6)
    tk.Label(row, text="Установить автостарт", fg=TEXT, bg=BTN, font=FONT).pack(side="left")
    W.autostart_toggle = Toggle(row, get_autostart(), bg=BTN)
    W.autostart_toggle.command = lambda v: ui_autostart(v, W.autostart_toggle)
    W.autostart_toggle.pack(side="right", padx=8)
    return card


def build_network(parent):
    card = make_card(parent, "Сеть / Доступ", "◍", ACCENT)
    buttons_column(card, [
        ("⌖", "Проверить доступность портов", lambda: run_action(act_check_ports, busy="Проверяю порты..."), ACCENT),
        (">_", "Проверить адрес (curl)", lambda: run_action(act_check_address, busy="Проверяю адрес..."), ACCENT),
        ("🛡", "Сбросить WARP", ui_reset_warp, RED),
        ("↗", "Открыть в браузере", ui_open_browser, YELLOW),
    ])
    return card


def save_port():
    value = W.port_var.get().strip()
    if not valid_port(value):
        messagebox.showerror("Порт", "Введите число от 1 до 65535")
        return
    if value == CFG["port"]:
        log("Порт не изменился", "info")
        return
    if STATE.get("version") and messagebox.askyesno(
            "Смена порта", f"Порт изменится на {value}. Перезапустить TorrServer сейчас?"):
        exe = ensure_exe()
        if exe:
            def work():
                _stop_impl(quiet=True)
                CFG["port"] = value
                save_config()
                _start_impl(exe)
                log(f"Порт TorrServer: {value}", "ok")

            bg(work)
            return
    CFG["port"] = value
    save_config()
    log(f"Порт TorrServer сохранён: {value}. Применится при следующем запуске.", "ok")
    POLLER.event.set()


def save_num_port():
    value = W.num_var.get().strip()
    if not valid_port(value):
        messagebox.showerror("Порт", "Введите число от 1 до 65535")
        return
    CFG["num_port"] = value
    save_config()
    log(f"Порт NUM/Lampa: {value}", "ok")
    POLLER.event.set()


def save_host():
    value = W.host_var.get().strip()
    CFG["external_host"] = "" if value == get_local_ip() else value
    save_config()
    log(f"Внешний IP/домен: {value or 'авто'}", "ok")
    POLLER.event.set()


def on_torr_toggle(key, invert, toggle):
    def callback(value):
        new_value = (not value) if invert else value

        def work():
            try:
                set_torr_setting(key, new_value)
                log(f"Настройка {key} = {new_value}", "ok")
            except Exception as error:
                log(f"Не удалось изменить {key}: {error}", "err")
                ui_call(toggle.set, not value)

        bg(work)

    return callback


def build_settings_card(parent):
    card = make_card(parent, "Настройки TorrServer", "🔧", ACCENT)
    W.port_var = tk.StringVar(value=CFG["port"])
    W.num_var = tk.StringVar(value=CFG["num_port"])
    W.host_var = tk.StringVar(value=CFG["external_host"] or get_local_ip())
    grid = tk.Frame(card.body, bg=PANEL)
    grid.pack(fill="x")
    grid.columnconfigure(1, weight=1)
    for index, (title, var, command) in enumerate((
            ("Порт TorrServer:", W.port_var, save_port),
            ("Порт NUM/Lampa:", W.num_var, save_num_port),
            ("Внешний IP/Домен:", W.host_var, save_host))):
        tk.Label(grid, text=title, fg=TEXT, bg=PANEL, font=FONT, anchor="w").grid(row=index, column=0, sticky="w", pady=4)
        make_entry(grid, var, 14).grid(row=index, column=1, sticky="ew", padx=8, pady=4, ipady=3)
        small_button(grid, "Сохранить", command).grid(row=index, column=2, pady=4)
    toggles = tk.Frame(card.body, bg=PANEL2, highlightbackground=BORDER, highlightthickness=1)
    toggles.pack(fill="x", pady=(10, 0))
    inner = tk.Frame(toggles, bg=PANEL2)
    inner.pack(padx=10, pady=8)
    for title, attr, value in (("DHT", "dht_toggle", True), ("Прокси", "proxy_toggle", CFG["proxy_enabled"]),
                               ("UPnP", "upnp_toggle", True)):
        tk.Label(inner, text=title, fg=TEXT, bg=PANEL2, font=FONT).pack(side="left", padx=(8, 4))
        toggle = Toggle(inner, value, bg=PANEL2)
        toggle.pack(side="left", padx=(0, 10))
        setattr(W, attr, toggle)
    W.dht_toggle.command = on_torr_toggle("DisableDHT", True, W.dht_toggle)
    W.upnp_toggle.command = on_torr_toggle("DisableUPNP", True, W.upnp_toggle)
    W.proxy_toggle.command = on_proxy_toggle
    return card


def build_ports_card(parent):
    card = make_card(parent, "Порты и соединения", "⌘", ACCENT)
    buttons_column(card, [
        ("◎", f"Проверить порты ({CFG['port']})", lambda: run_action(act_check_ports, busy="Проверяю порты..."), ACCENT),
        ("◔", "Тест скорости", lambda: run_action(act_speedtest, busy="Тест скорости (до 12 сек)..."), ACCENT),
        ("⚭", "Показать активные соединения",
         lambda: run_action(act_connections, busy="Читаю соединения...", window="Активные соединения"), ACCENT),
        ("▥", "Открыть статистику", ui_stats_window, ACCENT),
    ])
    return card


def build_proxy_card(parent):
    card = make_card(parent, "Прокси / VPN", "🛡", ACCENT)
    buttons_column(card, [
        ("▭", "Настроить прокси", ui_proxy_dialog, ACCENT),
        ("⇄", "Переключить VPN", lambda: run_action(act_toggle_vpn, busy="Переключаю VPN..."), ACCENT),
        ("✔", "Проверить VPN", lambda: run_action(act_vpn_check, busy="Проверяю VPN..."), ACCENT),
        ("↻", "Сбросить соединения", lambda: run_action(act_reset_connections, busy="Сбрасываю соединения..."), ACCENT),
    ])
    return card


def build_plugins_card(parent):
    card = make_card(parent, "Плагины / Дополнительно", "✚", ACCENT)
    buttons_column(card, [
        ("✚", "Управление плагинами", ui_plugins, ACCENT),
        ("📂", "Файловый браузер", lambda: show_page("files"), YELLOW),
        ("▭", "Настройки Lampa", ui_lampa_settings, ACCENT),
        ("⚙", "Настройки NUM", ui_num_settings, ACCENT),
        ("•••", "Другие инструменты", ui_other_tools, ACCENT),
    ])
    return card


def build_utils_card(parent):
    card = make_card(parent, "Полезные утилиты", "★", YELLOW)
    grid = tk.Frame(card.body, bg=PANEL)
    grid.pack(fill="both", expand=True)
    items = [
        ("▭", "Проверка диска", lambda: run_action(act_disk), ACCENT),
        ("⌫", "Очистка DNS-кэша", lambda: run_action(act_flush_dns), ACCENT),
        ("⚡", "Пинг", ui_ping, ACCENT),
        ("⇶", "Трассировка", ui_trace, ACCENT),
        ("DNS", "Проверка DNS", ui_dns_check, ACCENT),
        ("⌖", "Сканер сети", ui_scan, ACCENT),
        ("🌐", "Смена DNS", ui_change_dns, ACCENT),
        ("⏻", "Перезагрузка ПК", ui_reboot, RED),
    ]
    for index, (icon, text, command, color) in enumerate(items):
        grid.columnconfigure(index % 4, weight=1, uniform="util")
        FlatButton(grid, text, command, icon=icon, icon_fg=color, compact=True).grid(
            row=index // 4, column=index % 4, padx=3, pady=3, sticky="nsew")
    return card


def build_info_card(parent):
    card = make_card(parent, "Информация", "ⓘ", ACCENT)
    W.info = {}
    for key, title in (("version", "Версия Matrix"), ("port", "Порт TorrServer"), ("num", "NUM/Lampa порт"),
                       ("addr", "Внешний адрес"), ("warp", "WARP"), ("ms", "Время ответа")):
        row = tk.Frame(card.body, bg=PANEL)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=title, fg=TEXT, bg=PANEL, font=FONT).pack(side="left")
        label = tk.Label(row, text="—", fg=ACCENT if key == "addr" else TEXT, bg=PANEL, font=FONT)
        label.pack(side="right")
        W.info[key] = label
    return card


def build_links_card(parent):
    card = make_card(parent, "Быстрые ссылки", "⛓", ACCENT)
    grid = tk.Frame(card.body, bg=PANEL)
    grid.pack(fill="both", expand=True)
    links = [
        ("◍", "TorrServer (веб)", lambda: webbrowser.open(base_url())),
        ("▭", "NUM (веб)", lambda: webbrowser.open(host_address())),
        ("▭", "Lampa (веб)", lambda: webbrowser.open(LAMPA_URL)),
        ("◉", "GitHub проекта", lambda: webbrowser.open(NETORR_URL)),
        ("▯", "Документация", lambda: webbrowser.open(TORRSERVER_URL)),
        ("✉", "Поддержка", lambda: webbrowser.open(NETORR_ISSUES_URL)),
    ]
    for index, (icon, text, command) in enumerate(links):
        grid.columnconfigure(index % 2, weight=1, uniform="link")
        FlatButton(grid, text, command, icon=icon, icon_fg=ACCENT).grid(
            row=index // 2, column=index % 2, padx=3, pady=3, sticky="nsew")
    return card


def grid_row(parent, row, specs):
    frame = tk.Frame(parent, bg=BG)
    frame.grid(row=row, column=0, sticky="nsew", pady=4)
    for index, (builder, weight) in enumerate(specs):
        frame.columnconfigure(index, weight=weight, uniform=f"row{row}")
        builder(frame).grid(row=0, column=index, sticky="nsew", padx=4)
    frame.rowconfigure(0, weight=1)
    return frame


def build_main_page(parent):
    scroller = ScrollFrame(parent)
    SCROLLERS["main"] = scroller
    inner = tk.Frame(scroller.inner, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=10)
    build_header(inner).pack(fill="x", pady=(0, 8))
    body = tk.Frame(inner, bg=BG)
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)

    left = tk.Frame(body, bg=BG)
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    for builder in (build_quick_actions, build_cleanup, build_files_card):
        builder(left).pack(fill="x", pady=4)

    right = tk.Frame(body, bg=BG)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)
    grid_row(right, 0, [(build_logs, 14), (build_server_mgmt, 5), (build_network, 5)])
    grid_row(right, 1, [(build_settings_card, 8), (build_ports_card, 5), (build_proxy_card, 5), (build_plugins_card, 6)])
    grid_row(right, 2, [(build_utils_card, 10), (build_info_card, 7), (build_links_card, 7)])
    return scroller


# ── Страница «Торрсервер» ──

def fill_torrents(torrents):
    tree = W.tree
    selected = set(tree.selection())
    tree.delete(*tree.get_children())
    for torrent in torrents:
        hash_ = torrent.get("hash") or ""
        name = torrent.get("title") or torrent.get("name") or hash_
        tree.insert("", "end", iid=hash_ or None, values=(
            name,
            human_size(torrent.get("torrent_size") or 0),
            torrent.get("stat_string") or "",
            torrent.get("active_peers") or 0,
            torrent.get("connected_seeders") or 0,
            format_speed(float(torrent.get("download_speed") or 0)),
        ))
    for iid in selected:
        if tree.exists(iid):
            tree.selection_add(iid)
    W.tor_count.config(text=f"Торрентов: {len(torrents)}")


def tor_selected():
    return list(W.tree.selection())


def tor_action(action, title):
    selection = tor_selected()
    if not selection:
        messagebox.showinfo("Торренты", "Выберите торрент в списке")
        return
    if action == "rem" and not confirm("Удаление", f"Удалить выбранных торрентов: {len(selection)}?"):
        return

    def work():
        for hash_ in selection:
            api("/torrents", {"action": action, "hash": hash_})
        POLLER.event.set()
        return f"{title}: {len(selection)}", "ok"

    run_action(work)


def build_torrents_page(parent):
    page = tk.Frame(parent, bg=BG)
    inner = tk.Frame(page, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    row = tk.Frame(inner, bg=BG)
    row.pack(fill="x", pady=(0, 8))
    tk.Label(row, text="Торренты TorrServer", fg=TEXT, bg=BG, font=("Segoe UI", 16, "bold")).pack(side="left")
    W.tor_count = tk.Label(row, text="", fg=MUTED, bg=BG, font=FONT)
    W.tor_count.pack(side="left", padx=14)
    for text, command in (("Обновить", POLLER.event.set), ("＋ Добавить magnet", ui_add_magnet),
                          ("Освободить память", lambda: tor_action("drop", "Освобождено")),
                          ("Удалить выбранные", lambda: tor_action("rem", "Удалено")),
                          ("Открыть веб-интерфейс", ui_open_browser)):
        small_button(row, text, command).pack(side="right", padx=3)
    columns = ("name", "size", "status", "peers", "seeds", "speed")
    frame = tk.Frame(inner, bg=BG)
    frame.pack(fill="both", expand=True)
    W.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
    for key, title, width in (("name", "Название", 420), ("size", "Размер", 90), ("status", "Статус", 200),
                              ("peers", "Пиры", 60), ("seeds", "Сиды", 60), ("speed", "Скорость", 100)):
        W.tree.heading(key, text=title)
        W.tree.column(key, width=width, anchor="w" if key in ("name", "status") else "center")
    scroll = ttk.Scrollbar(frame, command=W.tree.yview)
    W.tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    W.tree.pack(side="left", fill="both", expand=True)
    return page


# ── Страница «Порты» ──

def build_ports_page(parent):
    page = tk.Frame(parent, bg=BG)
    inner = tk.Frame(page, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(inner, text="Порты и соединения", fg=TEXT, bg=BG, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
    W.ports_box = OutputBox(inner, height=14)
    card = make_card(inner, "Проверка порта", "⌖")
    card.pack(fill="x", pady=4)
    row = tk.Frame(card.body, bg=PANEL)
    row.pack(fill="x")
    host_var = tk.StringVar(value="127.0.0.1")
    port_var = tk.StringVar(value=CFG["port"])
    tk.Label(row, text="Хост:", fg=TEXT, bg=PANEL, font=FONT).pack(side="left")
    make_entry(row, host_var, 20).pack(side="left", padx=6, ipady=3)
    tk.Label(row, text="Порт:", fg=TEXT, bg=PANEL, font=FONT).pack(side="left", padx=(10, 0))
    make_entry(row, port_var, 8).pack(side="left", padx=6, ipady=3)
    small_button(row, "Проверить", lambda: run_action(
        act_check_port_custom, host_var.get().strip(), port_var.get().strip(), box=W.ports_box)).pack(side="left", padx=6)
    quick = tk.Frame(inner, bg=BG)
    quick.pack(fill="x", pady=6)
    for text, func, args in (
            ("Проверить порты TorrServer / NUM", act_check_ports, ()),
            ("Активные соединения", act_connections, ()),
            ("Тест скорости", act_speedtest, ()),
            ("Диагностика соединения", act_diagnostics, ()),
            ("Сканер сети", act_scan, ())):
        small_button(quick, text, lambda f=func, a=args: run_action(f, *a, box=W.ports_box, busy="Выполняю...")).pack(
            side="left", padx=3)
    W.ports_box.pack(fill="both", expand=True, pady=6)
    return page


# ── Страница «Прокси / VPN» ──

def build_proxy_page(parent):
    page = tk.Frame(parent, bg=BG)
    inner = tk.Frame(page, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(inner, text="Прокси / VPN", fg=TEXT, bg=BG, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
    card = make_card(inner, "Прокси для Netorr", "▭")
    card.pack(fill="x", pady=4)
    W.proxy_var = tk.StringVar(value=CFG["proxy_url"])
    row = tk.Frame(card.body, bg=PANEL)
    row.pack(fill="x")
    make_entry(row, W.proxy_var, 40).pack(side="left", ipady=3)
    small_button(row, "Настроить...", ui_proxy_dialog).pack(side="left", padx=6)
    small_button(row, "Проверить", ui_check_proxy).pack(side="left")
    card2 = make_card(inner, "WARP / VPN", "🛡")
    card2.pack(fill="x", pady=4)
    W.proxy_box = OutputBox(inner, height=12)
    row = tk.Frame(card2.body, bg=PANEL)
    row.pack(fill="x")
    for text, func in (("Переключить VPN", act_toggle_vpn), ("Проверить VPN", act_vpn_check),
                       ("Сбросить WARP", act_reset_warp), ("Сбросить соединения", act_reset_connections)):
        small_button(row, text, lambda f=func: run_action(f, box=W.proxy_box, busy="Выполняю...")).pack(side="left", padx=3)
    W.proxy_box.pack(fill="both", expand=True, pady=6)
    return page


# ── Страница «Файлы» ──

FILES_DIR = [None]


def refresh_files(path=None):
    if path is not None:
        FILES_DIR[0] = Path(path)
    if FILES_DIR[0] is None:
        FILES_DIR[0] = torr_dir() or SCRIPT_DIR
    current = FILES_DIR[0]
    W.files_path.config(text=str(current))
    W.files_tree.delete(*W.files_tree.get_children())
    try:
        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as error:
        log(f"Не удалось прочитать папку: {error}", "err")
        return
    for item in entries:
        try:
            stat = item.stat()
        except OSError:
            continue
        W.files_tree.insert("", "end", iid=str(item), values=(
            ("📁 " if item.is_dir() else "   ") + item.name,
            "" if item.is_dir() else human_size(stat.st_size),
            datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M"),
        ))


def files_open(_event=None):
    selection = W.files_tree.selection()
    if not selection:
        return
    item = Path(selection[0])
    if item.is_dir():
        refresh_files(item)
    else:
        open_path(item)


def files_delete():
    selection = W.files_tree.selection()
    if not selection:
        return
    names = "\n".join(Path(s).name for s in selection[:10])
    if not confirm("Удаление", f"Удалить безвозвратно?\n\n{names}"):
        return
    for s in selection:
        item = Path(s)
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except OSError as error:
            log(f"Не удалось удалить {item.name}: {error}", "err")
    refresh_files()


def build_files_page(parent):
    page = tk.Frame(parent, bg=BG)
    inner = tk.Frame(page, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(inner, text="Файловый браузер", fg=TEXT, bg=BG, font=("Segoe UI", 16, "bold")).pack(anchor="w")
    W.files_path = tk.Label(inner, text="", fg=CYAN, bg=BG, font=FONT_MONO, anchor="w")
    W.files_path.pack(fill="x", pady=4)
    row = tk.Frame(inner, bg=BG)
    row.pack(fill="x", pady=4)
    for text, command in (("↑ Вверх", lambda: refresh_files(FILES_DIR[0].parent)),
                          ("Обновить", refresh_files), ("Открыть", files_open),
                          ("Папка TorrServer", lambda: refresh_files(torr_dir() or SCRIPT_DIR)),
                          ("Резервная копия", ui_backup), ("Восстановить", ui_restore),
                          ("Удалить", files_delete)):
        small_button(row, text, command).pack(side="left", padx=3)
    frame = tk.Frame(inner, bg=BG)
    frame.pack(fill="both", expand=True, pady=6)
    W.files_tree = ttk.Treeview(frame, columns=("name", "size", "date"), show="headings", selectmode="extended")
    for key, title, width in (("name", "Имя", 480), ("size", "Размер", 100), ("date", "Изменён", 160)):
        W.files_tree.heading(key, text=title)
        W.files_tree.column(key, width=width, anchor="w")
    scroll = ttk.Scrollbar(frame, command=W.files_tree.yview)
    W.files_tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    W.files_tree.pack(side="left", fill="both", expand=True)
    W.files_tree.bind("<Double-1>", files_open)
    return page


# ── Страница «Система» ──

def refresh_system():
    def work():
        text = system_info_text()
        ui_call(W.system_box.set, text)

    bg(work)


def build_system_page(parent):
    page = tk.Frame(parent, bg=BG)
    inner = tk.Frame(page, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(inner, text="Система", fg=TEXT, bg=BG, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
    W.system_box = OutputBox(inner, height=14)
    row = tk.Frame(inner, bg=BG)
    row.pack(fill="x", pady=4)
    for text, command in (("Обновить", refresh_system), ("Экспорт отчёта", ui_export_report),
                          ("Проверка диска", lambda: run_action(act_disk, box=W.system_box)),
                          ("Очистка DNS-кэша", lambda: run_action(act_flush_dns, box=W.system_box)),
                          ("Смена DNS", ui_change_dns), ("Перезагрузка ПК", ui_reboot)):
        small_button(row, text, command).pack(side="left", padx=3)
    W.system_box.pack(fill="both", expand=True, pady=6)
    return page


# ── Страница «Настройки» ──

def save_app_settings():
    exe = W.s_exe.get().strip()
    if exe and not Path(exe).is_file():
        messagebox.showerror("Настройки", "Указанный файл TorrServer не найден")
        return
    try:
        interval = float(W.s_interval.get().replace(",", "."))
        if not 1 <= interval <= 60:
            raise ValueError
    except ValueError:
        messagebox.showerror("Настройки", "Интервал опроса — число от 1 до 60 секунд")
        return
    url = W.s_proxy.get().strip()
    if url and not re.match(r"^https?://", url):
        messagebox.showerror("Настройки", "Прокси должен начинаться с http:// или https://")
        return
    CFG.update(torr_exe=exe, poll_interval=interval, autorestart=bool(W.s_auto.get()), proxy_url=url)
    if not url:
        CFG["proxy_enabled"] = False
    save_config()
    rebuild_net_opener()
    sync_proxy_widgets()
    POLLER.event.set()
    log("Настройки Netorr сохранены", "ok")


def build_settings_page(parent):
    page = tk.Frame(parent, bg=BG)
    inner = tk.Frame(page, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(inner, text="Настройки Netorr", fg=TEXT, bg=BG, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
    card = make_card(inner, "Общие", "⚙")
    card.pack(fill="x", pady=4)
    grid = tk.Frame(card.body, bg=PANEL)
    grid.pack(fill="x")
    grid.columnconfigure(1, weight=1)
    W.s_exe = tk.StringVar(value=CFG["torr_exe"])
    W.s_interval = tk.StringVar(value=str(CFG["poll_interval"]))
    W.s_proxy = tk.StringVar(value=CFG["proxy_url"])
    W.s_auto = tk.BooleanVar(value=CFG["autorestart"])
    tk.Label(grid, text="Файл TorrServer:", fg=TEXT, bg=PANEL, font=FONT).grid(row=0, column=0, sticky="w", pady=5)
    make_entry(grid, W.s_exe, 50).grid(row=0, column=1, sticky="ew", padx=8, ipady=3)

    def browse():
        path = filedialog.askopenfilename(title="Файл TorrServer")
        if path:
            W.s_exe.set(path)

    small_button(grid, "Обзор...", browse).grid(row=0, column=2)
    tk.Label(grid, text="Интервал опроса, сек:", fg=TEXT, bg=PANEL, font=FONT).grid(row=1, column=0, sticky="w", pady=5)
    make_entry(grid, W.s_interval, 8).grid(row=1, column=1, sticky="w", padx=8, ipady=3)
    tk.Label(grid, text="HTTP-прокси:", fg=TEXT, bg=PANEL, font=FONT).grid(row=2, column=0, sticky="w", pady=5)
    make_entry(grid, W.s_proxy, 40).grid(row=2, column=1, sticky="w", padx=8, ipady=3)
    tk.Checkbutton(grid, text="Автоматически перезапускать TorrServer, если он упал", variable=W.s_auto,
                   fg=TEXT, bg=PANEL, selectcolor=PANEL2, activebackground=PANEL, activeforeground=TEXT,
                   font=FONT).grid(row=3, column=0, columnspan=3, sticky="w", pady=6)
    small_button(card.body, "Сохранить настройки", save_app_settings).pack(anchor="w", pady=(8, 0))
    return page


# ── Страница «Справка» ──

HELP_TEXT = f"""Netorr {APP_VERSION} — помощник для TorrServer

БЫСТРЫЙ СТАРТ
• Если TorrServer лежит рядом с Netorr или в папке C:\\TorrServer — он найдётся сам.
  Иначе при первом запуске Netorr попросит указать файл.
• Адрес в шапке (http://IP:порт) вставьте в Lampa/NUM → Настройки → TorrServer.
  Клик по адресу копирует его.

КОНСОЛЬ ВНИЗУ ЛОГОВ
help, status, start, stop, restart, ping [хост], dns [хост], trace [хост],
port <порт>, ip, version, backup, clear

ПЛАГИНЫ
Python-файлы в папке netorr_plugins с переменной NAME и функцией run(api).
Пример можно создать кнопкой в «Управление плагинами».

ЗАМЕЧАНИЯ
• Смена DNS и перезагрузка требуют прав администратора (Windows).
• Тумблеры DHT/UPnP меняют настройки самого TorrServer.
• Тумблер «Прокси» включает HTTP-прокси только для проверок Netorr.
• Горячие клавиши: F5 — обновить статус.
"""


def build_help_page(parent):
    page = tk.Frame(parent, bg=BG)
    inner = tk.Frame(page, bg=BG)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(inner, text="Справка", fg=TEXT, bg=BG, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
    box = OutputBox(inner, height=18)
    box.pack(fill="both", expand=True)
    box.set(HELP_TEXT)
    row = tk.Frame(inner, bg=BG)
    row.pack(fill="x", pady=8)
    for text, url in (("GitHub Netorr", NETORR_URL), ("GitHub TorrServer", TORRSERVER_URL), ("Lampa", LAMPA_URL)):
        small_button(row, text, lambda u=url: webbrowser.open(u)).pack(side="left", padx=3)
    return page


# ── Стили, футер, запуск ──

def setup_styles():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Treeview", background=PANEL2, fieldbackground=PANEL2, foreground=TEXT, rowheight=26,
                    borderwidth=0, font=FONT)
    style.configure("Treeview.Heading", background=PANEL, foreground=CYAN, font=("Segoe UI", 10, "bold"),
                    relief="flat")
    style.map("Treeview", background=[("selected", ACCENT_DARK)], foreground=[("selected", "white")])
    style.configure("Vertical.TScrollbar", background=BTN, troughcolor=PANEL2, bordercolor=PANEL2,
                    arrowcolor=MUTED)
    style.configure("TCombobox", fieldbackground=PANEL2, background=BTN, foreground=TEXT)


def build_footer(parent):
    footer = tk.Frame(parent, bg=NAV, padx=16, pady=6)
    footer.pack(fill="x", side="bottom")
    W.footer_dot = tk.Label(footer, text="●", fg=YELLOW, bg=NAV)
    W.footer_dot.pack(side="left")
    W.footer_status = tk.Label(footer, text="Запуск...", fg=TEXT, bg=NAV, font=FONT)
    W.footer_status.pack(side="left", padx=8)
    W.footer_right = tk.Label(footer, text="", fg=CYAN, bg=NAV, font=FONT_SMALL)
    W.footer_right.pack(side="right")


def on_close():
    root.destroy()


def on_wheel(event):
    widget = event.widget
    if isinstance(widget, (tk.Text, ttk.Treeview, tk.Listbox)):
        return
    scroller = SCROLLERS.get(CURRENT_PAGE[0])
    if scroller:
        scroller.canvas.yview_scroll(int(-event.delta / 120) if event.delta else (1 if event.num == 5 else -1), "units")


def main():
    global root
    root = tk.Tk()
    root.title(f"{APP_NAME} — TorrServer Assistant")
    root.geometry("1420x900")
    root.minsize(1100, 680)
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    root.report_callback_exception = lambda *a: traceback.print_exception(*a)
    setup_styles()

    build_nav(root)
    build_footer(root)
    container = tk.Frame(root, bg=BG)
    container.pack(fill="both", expand=True)

    PAGES["main"] = build_main_page(container)
    PAGES["torrents"] = build_torrents_page(container)
    PAGES["ports"] = build_ports_page(container)
    PAGES["proxy"] = build_proxy_page(container)
    PAGES["files"] = build_files_page(container)
    PAGES["system"] = build_system_page(container)
    PAGES["settings"] = build_settings_page(container)
    PAGES["help"] = build_help_page(container)

    root.bind_all("<MouseWheel>", on_wheel)
    root.bind_all("<Button-4>", on_wheel)
    root.bind_all("<Button-5>", on_wheel)
    root.bind("<F5>", lambda e: refresh_now())
    root.protocol("WM_DELETE_WINDOW", on_close)

    show_page("main")
    _drain_queue()

    log(f"Netorr {APP_VERSION} запущен", "ok")
    log(f"Конфигурация: {CONFIG_PATH}", "info")
    exe = find_exe()
    log(f"TorrServer: {exe}" if exe else "TorrServer не найден — укажите путь при первом запуске", "info" if exe else "warn")
    POLLER.start()
    root.mainloop()


if __name__ == "__main__":
    main()
