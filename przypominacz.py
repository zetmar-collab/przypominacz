# -*- coding: utf-8 -*-
"""Przypominacz - tray'owy przypominacz o wodzie i przerwach od komputera."""

import json
import os
import queue
import sys
import threading
import tkinter as tk
import winreg
import winsound
from datetime import datetime

import pystray
from PIL import Image, ImageDraw

APP_NAME = "Przypominacz"
FROZEN = getattr(sys, "frozen", False)


def w_pakiecie_msix():
    """Czy dzialamy jako zainstalowany pakiet MSIX (wersja ze Sklepu Windows)."""
    import ctypes
    dlugosc = ctypes.c_uint32(0)
    # APPMODEL_ERROR_NO_PACKAGE = 15700 - brak pakietu, czyli zwykly exe
    return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(dlugosc), None) != 15700


MSIX = w_pakiecie_msix()

if MSIX:
    # Katalog instalacji pakietu jest tylko do odczytu - ustawienia ida do profilu.
    BASE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
    os.makedirs(BASE_DIR, exist_ok=True)
elif FROZEN:
    # W wersji .exe config lezy obok pliku exe, nie w rozpakowanym katalogu tymczasowym.
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULTS = {
    "wodaMinuty": 30,
    "przerwaMinuty": 60,
    "przerwaDlugoscMinut": 5,
    "drzemkaMinuty": 5,
    "dzwiek": True,
    "cichaPoraWlaczona": False,
    "cichaPoraOd": 22,
    "cichaPoraDo": 7,
}


# --- konfiguracja ---------------------------------------------------------

def wczytaj_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        zapisz_config(cfg)
    except (json.JSONDecodeError, OSError):
        pass
    for k, v in DEFAULTS.items():
        if isinstance(v, bool):
            cfg[k] = bool(cfg.get(k, v))
        else:
            try:
                cfg[k] = max(1, int(cfg.get(k, v))) if "Minut" in k else int(cfg.get(k, v))
            except (TypeError, ValueError):
                cfg[k] = v
    return cfg


def zapisz_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# --- autostart ------------------------------------------------------------

def polecenie_autostartu():
    if FROZEN:
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return f'"{pythonw}" "{os.path.join(BASE_DIR, "przypominacz.py")}"'


def wpis_autostartu():
    """Aktualna wartosc wpisu w rejestrze albo None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, APP_NAME)[0]
    except OSError:
        return None


def autostart_wlaczony():
    """Wlaczony = jakikolwiek wpis wskazujacy na ten plik (bez czepiania sie cudzyslowow)."""
    wpis = wpis_autostartu()
    if not wpis:
        return False
    return os.path.normcase(wpis.strip().strip('"')).startswith(
        os.path.normcase(sys.executable if FROZEN else os.path.dirname(sys.executable)))


def ustaw_autostart(wlacz):
    """Wlacza/wylacza autostart. Blad zglasza wyjatkiem - cisza tu szkodzi."""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
        if wlacz:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, polecenie_autostartu())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
    if wlacz:
        usun_skroty_ze_startupu()


def usun_skroty_ze_startupu():
    """Sprzata recznie dodane skroty z folderu Autostart - inaczej program startuje dwa razy."""
    folder = os.path.join(os.environ.get("APPDATA", ""),
                          "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    if not os.path.isdir(folder):
        return
    for nazwa in os.listdir(folder):
        if nazwa.lower().startswith("przypominacz") and nazwa.lower().endswith(".lnk"):
            try:
                os.remove(os.path.join(folder, nazwa))
            except OSError:
                pass


def napraw_autostart():
    """Wpis wskazuje na stara sciezke (np. exe przeniesiony)? Popraw go po cichu."""
    if MSIX:
        return  # w pakiecie autostartem zarzadza Windows (StartupTask z manifestu)
    wpis = wpis_autostartu()
    if wpis and wpis != polecenie_autostartu():
        try:
            ustaw_autostart(True)
        except OSError:
            pass


# --- ikona ----------------------------------------------------------------

def zrob_ikone(kolor):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(32, 6), (52, 34), (46, 52), (18, 52), (12, 34)], fill=kolor)
    d.ellipse([12, 28, 52, 58], fill=kolor)
    d.ellipse([22, 34, 32, 44], fill=(255, 255, 255, 110))
    return img


IKONA_AKTYWNA = zrob_ikone((41, 128, 185, 255))
IKONA_PAUZA = zrob_ikone((127, 140, 141, 255))


# --- aplikacja ------------------------------------------------------------

class Przypominacz:
    def __init__(self):
        self.cfg = wczytaj_config()
        self.pauza = False
        self.kolejka = queue.Queue()
        self.okno_przerwy = None
        self.okno_ustawien = None

        self.root = tk.Tk()
        self.root.withdraw()

        self.reset_wody()
        self.reset_przerwy()

        napraw_autostart()

        self.ikona = pystray.Icon(APP_NAME, IKONA_AKTYWNA, APP_NAME, self.zbuduj_menu())
        threading.Thread(target=self.ikona.run, daemon=True).start()

        self.root.after(200, self.tik)

    # --- liczniki ---
    def reset_wody(self):
        self.woda_sek = self.cfg["wodaMinuty"] * 60

    def reset_przerwy(self):
        self.przerwa_sek = self.cfg["przerwaMinuty"] * 60

    @staticmethod
    def fmt(sek):
        return f"{sek // 60}:{sek % 60:02d}"

    def cicha_pora(self):
        if not self.cfg["cichaPoraWlaczona"]:
            return False
        h = datetime.now().hour
        od, do = self.cfg["cichaPoraOd"], self.cfg["cichaPoraDo"]
        return od <= h or h < do if od > do else od <= h < do

    # --- menu ---
    def zbuduj_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda i: f"Woda za {self.fmt(self.woda_sek)}  |  przerwa za {self.fmt(self.przerwa_sek)}",
                             None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Przypomnij o wodzie teraz", lambda: self.kolejka.put("woda")),
            pystray.MenuItem("Zrob przerwe teraz", lambda: self.kolejka.put("przerwa")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pauza", lambda: self.kolejka.put("pauza"), checked=lambda i: self.pauza),
            pystray.MenuItem("Ustawienia...", lambda: self.kolejka.put("config")),
            pystray.MenuItem("Autostart - ustawienia Windows", lambda: self.kolejka.put("startupapps"))
            if MSIX else
            pystray.MenuItem("Uruchamiaj z Windows", lambda: self.kolejka.put("autostart"),
                             checked=lambda i: autostart_wlaczony()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Zakoncz", lambda: self.kolejka.put("koniec")),
        )

    # --- petla glowna ---
    def tik(self):
        while True:
            try:
                cmd = self.kolejka.get_nowait()
            except queue.Empty:
                break
            try:
                self.obsluz(cmd)
            except Exception as e:  # zadna akcja z menu nie moze umrzec po cichu
                self.powiadom("Blad", f"{cmd}: {e}")

        if not self.pauza:
            self.woda_sek -= 1
            self.przerwa_sek -= 1
            if self.woda_sek <= 0:
                self.reset_wody()
                if not self.cicha_pora():
                    self.przypomnij_wode()
            if self.przerwa_sek <= 0:
                self.reset_przerwy()
                if not self.cicha_pora():
                    self.pokaz_przerwe()

        stan = "PAUZA" if self.pauza else f"woda {self.fmt(self.woda_sek)} | przerwa {self.fmt(self.przerwa_sek)}"
        self.ikona.title = f"{APP_NAME} - {stan}"
        self.root.after(1000, self.tik)

    def obsluz(self, cmd):
        if cmd == "woda":
            self.reset_wody()
            self.przypomnij_wode()
        elif cmd == "przerwa":
            self.reset_przerwy()
            self.pokaz_przerwe()
        elif cmd == "pauza":
            self.pauza = not self.pauza
            self.ikona.icon = IKONA_PAUZA if self.pauza else IKONA_AKTYWNA
        elif cmd == "config":
            self.pokaz_ustawienia()
        elif cmd == "startupapps":
            os.startfile("ms-settings:startupapps")
        elif cmd == "autostart":
            wlacz = not autostart_wlaczony()
            try:
                ustaw_autostart(wlacz)
            except OSError as e:
                self.powiadom("Nie udalo sie zmienic autostartu", str(e))
                return
            if autostart_wlaczony() == wlacz:
                self.powiadom("Autostart " + ("wlaczony" if wlacz else "wylaczony"),
                              "Program bedzie startowal razem z Windows." if wlacz
                              else "Program nie bedzie juz startowal razem z Windows.")
            else:
                self.powiadom("Autostart bez zmian",
                              "Windows nie przyjal wpisu - sprawdz ustawienia zabezpieczen.")
        elif cmd == "koniec":
            self.ikona.stop()
            self.root.quit()

    # --- powiadomienia ---
    def powiadom(self, tytul, tresc):
        try:
            self.ikona.notify(tresc, tytul)
        except Exception:
            pass
        if self.cfg["dzwiek"]:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)

    def przypomnij_wode(self):
        self.powiadom("Czas na wode", "Wypij szklanke wody - nawodnij sie i wroc do pracy.")

    # --- okno ustawien ---
    def pokaz_ustawienia(self):
        if self.okno_ustawien is not None and self.okno_ustawien.winfo_exists():
            self.okno_ustawien.lift()
            self.okno_ustawien.focus_force()
            return

        TLO, TEKST, OPIS, AKCENT = "#1b2838", "#ffffff", "#a8c0d6", "#3498db"
        win = tk.Toplevel(self.root)
        self.okno_ustawien = win
        win.title(f"{APP_NAME} - ustawienia")
        win.configure(bg=TLO)
        win.attributes("-topmost", True)
        win.resizable(False, False)

        szer, wys = 420, 400
        x = (win.winfo_screenwidth() - szer) // 2
        y = (win.winfo_screenheight() - wys) // 3
        win.geometry(f"{szer}x{wys}+{x}+{y}")

        def zamknij():
            self.okno_ustawien = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        win.protocol("WM_DELETE_WINDOW", zamknij)

        tk.Label(win, text="Ustawienia", bg=TLO, fg=TEKST,
                 font=("Segoe UI", 16, "bold")).pack(pady=(18, 12))

        siatka = tk.Frame(win, bg=TLO)
        siatka.pack(padx=26, fill="x")

        zmienne = {}

        def pole(wiersz, etykieta, klucz, od, do):
            tk.Label(siatka, text=etykieta, bg=TLO, fg=OPIS, font=("Segoe UI", 10),
                     anchor="w").grid(row=wiersz, column=0, sticky="w", pady=5)
            v = tk.StringVar(value=str(self.cfg[klucz]))
            zmienne[klucz] = v
            tk.Spinbox(siatka, from_=od, to=do, textvariable=v, width=6, justify="center",
                       font=("Segoe UI", 10), relief="flat", bg="#2c3e50", fg=TEKST,
                       buttonbackground="#34495e", insertbackground=TEKST).grid(
                row=wiersz, column=1, sticky="e", pady=5)

        siatka.columnconfigure(0, weight=1)
        pole(0, "Woda co ile minut", "wodaMinuty", 1, 600)
        pole(1, "Przerwa co ile minut", "przerwaMinuty", 1, 600)
        pole(2, "Dlugosc przerwy (minuty)", "przerwaDlugoscMinut", 1, 120)
        pole(3, "Drzemka - odloz o (minuty)", "drzemkaMinuty", 1, 120)

        dzwiek = tk.BooleanVar(value=self.cfg["dzwiek"])
        cisza = tk.BooleanVar(value=self.cfg["cichaPoraWlaczona"])
        for wiersz, (txt, var) in enumerate([("Dzwiek przy przypomnieniach", dzwiek),
                                             ("Cicha pora (bez przypomnien)", cisza)], start=4):
            tk.Checkbutton(siatka, text=txt, variable=var, bg=TLO, fg=OPIS, selectcolor="#2c3e50",
                           activebackground=TLO, activeforeground=TEKST, font=("Segoe UI", 10),
                           anchor="w", highlightthickness=0, bd=0).grid(
                row=wiersz, column=0, columnspan=2, sticky="w", pady=3)

        pole(6, "Cicha pora od godziny", "cichaPoraOd", 0, 23)
        pole(7, "Cicha pora do godziny", "cichaPoraDo", 0, 23)

        blad = tk.Label(win, text="", bg=TLO, fg="#e74c3c", font=("Segoe UI", 9))
        blad.pack(pady=(8, 0))

        def zapisz():
            nowy = dict(self.cfg)
            for klucz, v in zmienne.items():
                try:
                    liczba = int(v.get())
                except ValueError:
                    blad.config(text="Wszystkie pola musza byc liczbami.")
                    return
                if klucz.startswith("cichaPora") and not 0 <= liczba <= 23:
                    blad.config(text="Godziny cichej pory: 0-23.")
                    return
                if klucz.endswith("Minuty") or klucz.endswith("Minut"):
                    if liczba < 1 and not klucz.startswith("cichaPora"):
                        blad.config(text="Minuty musza byc wieksze od zera.")
                        return
                nowy[klucz] = liczba
            nowy["dzwiek"] = dzwiek.get()
            nowy["cichaPoraWlaczona"] = cisza.get()

            zapisz_config(nowy)
            self.cfg = wczytaj_config()
            self.reset_wody()
            self.reset_przerwy()
            zamknij()
            self.powiadom("Ustawienia zapisane",
                          f"Woda co {self.cfg['wodaMinuty']} min, przerwa co {self.cfg['przerwaMinuty']} min.")

        ramka = tk.Frame(win, bg=TLO)
        ramka.pack(pady=(14, 0))
        tk.Button(ramka, text="Anuluj", width=14, font=("Segoe UI", 10), relief="flat",
                  bg="#34495e", fg=TEKST, command=zamknij).pack(side="left", padx=6)
        tk.Button(ramka, text="Zapisz", width=14, font=("Segoe UI", 10), relief="flat",
                  bg=AKCENT, fg=TEKST, command=zapisz).pack(side="left", padx=6)

        win.lift()
        win.focus_force()

    # --- okno przerwy ---
    def pokaz_przerwe(self):
        if self.okno_przerwy is not None and tk.Toplevel.winfo_exists(self.okno_przerwy):
            return
        if self.cfg["dzwiek"]:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

        win = tk.Toplevel(self.root)
        self.okno_przerwy = win
        win.title(f"{APP_NAME} - przerwa")
        win.configure(bg="#1b2838")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", lambda: self.zamknij_przerwe(win))

        szer, wys = 460, 260
        x = (win.winfo_screenwidth() - szer) // 2
        y = (win.winfo_screenheight() - wys) // 3
        win.geometry(f"{szer}x{wys}+{x}+{y}")

        tk.Label(win, text="Czas na przerwe", bg="#1b2838", fg="#ffffff",
                 font=("Segoe UI", 20, "bold")).pack(pady=(26, 4))
        tk.Label(win, text="Wstan, rozciagnij sie, odwroc wzrok od ekranu.",
                 bg="#1b2838", fg="#a8c0d6", font=("Segoe UI", 11)).pack()

        pozostalo = [self.cfg["przerwaDlugoscMinut"] * 60]
        zegar = tk.Label(win, text=self.fmt(pozostalo[0]), bg="#1b2838", fg="#3498db",
                         font=("Segoe UI", 40, "bold"))
        zegar.pack(pady=10)

        ramka = tk.Frame(win, bg="#1b2838")
        ramka.pack(pady=(4, 0))
        tk.Button(ramka, text=f"Odloz o {self.cfg['drzemkaMinuty']} min", width=18,
                  font=("Segoe UI", 10), relief="flat", bg="#34495e", fg="white",
                  command=lambda: self.drzemka(win)).pack(side="left", padx=6)
        tk.Button(ramka, text="Zamknij", width=14, font=("Segoe UI", 10), relief="flat",
                  bg="#3498db", fg="white",
                  command=lambda: self.zamknij_przerwe(win)).pack(side="left", padx=6)

        def odliczaj():
            if not tk.Toplevel.winfo_exists(win):
                return
            pozostalo[0] -= 1
            if pozostalo[0] <= 0:
                zegar.config(text="0:00")
                if self.cfg["dzwiek"]:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                self.zamknij_przerwe(win)
                self.powiadom("Przerwa zakonczona", "Mozesz wracac do pracy.")
                return
            zegar.config(text=self.fmt(pozostalo[0]))
            win.after(1000, odliczaj)

        win.after(1000, odliczaj)
        win.lift()
        win.focus_force()

    def zamknij_przerwe(self, win):
        self.okno_przerwy = None
        try:
            win.destroy()
        except tk.TclError:
            pass

    def drzemka(self, win):
        self.przerwa_sek = self.cfg["drzemkaMinuty"] * 60
        self.zamknij_przerwe(win)

    def start(self):
        self.root.mainloop()


def juz_uruchomiony():
    """Jedna instancja - drugie uruchomienie po prostu konczy sie po cichu."""
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\PrzypominaczMutex")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if juz_uruchomiony():
        sys.exit(0)
    Przypominacz().start()
