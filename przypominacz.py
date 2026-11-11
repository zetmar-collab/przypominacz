# -*- coding: utf-8 -*-
"""Przypominacz - tray'owy przypominacz o wodzie i przerwach od komputera."""

import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
import winreg
import winsound
from datetime import datetime
from logging.handlers import RotatingFileHandler

import pystray
from PIL import Image, ImageDraw

APP_NAME = "Przypominacz"
__version__ = "1.2.0"
FROZEN = getattr(sys, "frozen", False)


def w_pakiecie_msix():
    """Czy dzialamy jako zainstalowany pakiet MSIX (wersja ze Sklepu Windows)."""
    import ctypes
    dlugosc = ctypes.c_uint32(0)
    # APPMODEL_ERROR_NO_PACKAGE = 15700 - brak pakietu, czyli zwykly exe
    return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(dlugosc), None) != 15700


MSIX = w_pakiecie_msix()

# Dane uzytkownika zawsze w profilu. Katalog instalacji bywa tylko do odczytu
# (pakiet MSIX, Program Files, dysk sieciowy), a nieudany zapis zabijal start.
DANE_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME)
CONFIG_PATH = os.path.join(DANE_DIR, "config.json")
LOG_PATH = os.path.join(DANE_DIR, "przypominacz.log")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# Katalog samego programu (exe albo skryptu) - potrzebny do autostartu i migracji.
KATALOG_PROGRAMU = (os.path.dirname(sys.executable) if FROZEN
                    else os.path.dirname(os.path.abspath(__file__)))

# Wersje do 1.1 trzymaly ustawienia obok pliku exe - stamtad je przenosimy.
STARY_CONFIG = os.path.join(KATALOG_PROGRAMU, "config.json")

DEFAULTS = {
    "wodaMinuty": 30,
    "przerwaMinuty": 60,
    "przerwaDlugoscMinut": 5,
    "drzemkaMinuty": 5,
    "dzwiek": True,
    "cichaPoraWlaczona": False,
    "cichaPoraOd": 22,
    "cichaPoraDo": 7,
    "bezczynnoscWlaczona": True,
    "bezczynnoscMinuty": 5,
    "szanujPelnyEkran": True,
}

# Odstep miedzy tikami wiekszy niz to znaczy, ze proces byl zamrozony.
PROG_WZNOWIENIA = 90

# Dopuszczalne zakresy - jedno zrodlo prawdy dla pliku i okna ustawien.
LIMITY = {
    "wodaMinuty": (1, 600),
    "przerwaMinuty": (1, 600),
    "przerwaDlugoscMinut": (1, 120),
    "drzemkaMinuty": (1, 120),
    "cichaPoraOd": (0, 23),
    "cichaPoraDo": (0, 23),
    "bezczynnoscMinuty": (1, 120),
}

# O tyle odkladamy przypomnienie, gdy akurat nie wypada przeszkadzac.
ODROCZENIE = 60

# Paleta w jednym miejscu - wczesniej te same kolory byly wpisane w osmiu.
TLO = "#1b2838"
TEKST = "#ffffff"
OPIS = "#a8c0d6"
AKCENT = "#3498db"
POLE = "#2c3e50"
PRZYCISK = "#34495e"
BLAD = "#e74c3c"

log = logging.getLogger(APP_NAME)


# --- logowanie ------------------------------------------------------------

def uruchom_logowanie():
    """Bez logu kazda cicha awaria u uzytkownika jest nie do odtworzenia."""
    try:
        os.makedirs(DANE_DIR, exist_ok=True)
        uchwyt = RotatingFileHandler(LOG_PATH, maxBytes=256 * 1024, backupCount=1,
                                     encoding="utf-8")
        uchwyt.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(uchwyt)
        log.setLevel(logging.INFO)
    except OSError:
        log.addHandler(logging.NullHandler())  # brak logu nie moze blokowac programu

    def zglos_wyjatek(typ, wartosc, slad):
        log.critical("Nieobsluzony wyjatek", exc_info=(typ, wartosc, slad))

    sys.excepthook = zglos_wyjatek
    log.info("Start %s %s (msix=%s, frozen=%s)", APP_NAME, __version__, MSIX, FROZEN)


# --- konfiguracja ---------------------------------------------------------

def zapisz_config(cfg):
    """Zapis atomowy - przerwany zapis nie zostawia obcietego pliku.

    Zwraca True/False zamiast rzucac: brak prawa zapisu nie moze zabic startu.
    """
    try:
        os.makedirs(DANE_DIR, exist_ok=True)
        tymczasowy = CONFIG_PATH + ".tmp"
        with open(tymczasowy, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tymczasowy, CONFIG_PATH)
        return True
    except OSError as e:
        log.error("Nie udalo sie zapisac ustawien: %s", e)
        return False


def odloz_uszkodzony_config():
    """Uszkodzonego pliku nie kasujemy po cichu - odkladamy go obok."""
    try:
        os.replace(CONFIG_PATH, CONFIG_PATH + ".uszkodzony")
        log.warning("Uszkodzony plik odlozony jako config.json.uszkodzony")
    except OSError as e:
        log.error("Nie udalo sie odlozyc uszkodzonego pliku: %s", e)


def migruj_stary_config():
    """Przenosi ustawienia ze starej lokalizacji (obok exe) - jednorazowo."""
    if os.path.exists(CONFIG_PATH) or not os.path.exists(STARY_CONFIG):
        return
    try:
        with open(STARY_CONFIG, encoding="utf-8") as f:
            dane = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Nie udalo sie odczytac starych ustawien: %s", e)
        return
    if zapisz_config(dane):
        log.info("Przeniesiono ustawienia ze starej lokalizacji")


def wczytaj_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        zapisz_config(cfg)
    except json.JSONDecodeError as e:
        log.warning("Uszkodzony config.json (%s) - wracam do domyslnych", e)
        odloz_uszkodzony_config()
        zapisz_config(cfg)
    except OSError as e:
        log.warning("Nie moge odczytac ustawien: %s", e)

    for k, v in DEFAULTS.items():
        if isinstance(v, bool):
            cfg[k] = bool(cfg.get(k, v))
            continue
        try:
            liczba = int(cfg.get(k, v))
        except (TypeError, ValueError):
            log.warning("Wartosc %s nie jest liczba - biore domyslna", k)
            cfg[k] = v
            continue
        dol, gora = LIMITY.get(k, (liczba, liczba))
        if not dol <= liczba <= gora:
            log.warning("Wartosc %s=%s poza zakresem %s-%s - przycinam", k, liczba, dol, gora)
        cfg[k] = min(max(liczba, dol), gora)
    return cfg


# --- autostart ------------------------------------------------------------

def polecenie_autostartu():
    if FROZEN:
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return f'"{pythonw}" "{os.path.join(KATALOG_PROGRAMU, "przypominacz.py")}"'


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


# --- stan uzytkownika i systemu ---------------------------------------------

def sekundy_bezczynnosci():
    """Ile sekund bez ruchu myszy i klawiatury w calej sesji Windows."""
    import ctypes

    class OSTATNIE_WEJSCIE(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = OSTATNIE_WEJSCIE()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    teraz = ctypes.windll.kernel32.GetTickCount()
    # Licznik tikow przekreca sie po ~49 dniach pracy systemu.
    return ((teraz - info.dwTime) % 2 ** 32) / 1000.0


def mozna_przeszkadzac():
    """False w prezentacji, pelnym ekranie, trybie skupienia i przy zablokowanym ekranie."""
    import ctypes
    stan = ctypes.c_int()
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(stan)) != 0:
            return True  # nie wiemy, co sie dzieje - lepiej przypomniec
    except (AttributeError, OSError):
        return True
    return stan.value == 5  # QUNS_ACCEPTS_NOTIFICATIONS


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
    byl_nieobecny = 0.0  # najdluzsza bezczynnosc w trwajacej wlasnie nieobecnosci

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
        self.ostatni_tik = time.time()

        napraw_autostart()

        self.ikona = pystray.Icon(APP_NAME, IKONA_AKTYWNA, APP_NAME, self.zbuduj_menu())
        threading.Thread(target=self.ikona.run, daemon=True).start()

        self.root.after(200, self.tik)

    # --- liczniki ---
    # Liczymy do terminu wg zegara, nie przez odejmowanie sekund w kazdym tiku.
    # Licznik tikow gubil caly czas uspienia komputera i dryfowal ~27 s/godzine.
    def reset_wody(self):
        self.woda_do = time.time() + self.cfg["wodaMinuty"] * 60

    def reset_przerwy(self):
        self.przerwa_do = time.time() + self.cfg["przerwaMinuty"] * 60

    @property
    def woda_sek(self):
        return max(0, int(round(self.woda_do - time.time())))

    @property
    def przerwa_sek(self):
        return max(0, int(round(self.przerwa_do - time.time())))

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

        teraz = time.time()
        odstep = teraz - self.ostatni_tik
        self.ostatni_tik = teraz

        if odstep > PROG_WZNOWIENIA:
            # Proces stal: uspienie, hibernacja albo przestawiony zegar.
            # Nie wyrzucamy zaleglych przypomnien - zaczynamy odliczanie od nowa.
            log.info("Przerwa w dzialaniu %.0f s - licze od nowa", odstep)
            self.reset_wody()
            self.reset_przerwy()
        elif self.pauza:
            # W pauzie terminy przesuwaja sie razem z zegarem, wiec nie zapadaja.
            self.woda_do += odstep
            self.przerwa_do += odstep
        elif self.nieobecny(odstep):
            pass  # czas nieobecnosci nie liczy sie do przypomnien
        else:
            if teraz >= self.woda_do:
                self.wyzwol(self.przypomnij_wode, self.reset_wody, "woda_do")
            if teraz >= self.przerwa_do:
                self.wyzwol(self.pokaz_przerwe, self.reset_przerwy, "przerwa_do")

        stan = "PAUZA" if self.pauza else f"woda {self.fmt(self.woda_sek)} | przerwa {self.fmt(self.przerwa_sek)}"
        self.ikona.title = f"{APP_NAME} - {stan}"
        self.root.after(1000, self.tik)

    def nieobecny(self, odstep):
        """Czy uzytkownika nie ma przy komputerze - wtedy liczniki stoja.

        Przypominanie o wodzie pustemu krzeslu nie ma sensu, a po powrocie
        uzytkownik dostawal alarm w pierwszej minucie pracy.
        """
        if not self.cfg["bezczynnoscWlaczona"]:
            return False

        bezczynny = sekundy_bezczynnosci()
        if bezczynny >= self.cfg["bezczynnoscMinuty"] * 60:
            self.woda_do += odstep
            self.przerwa_do += odstep
            self.byl_nieobecny = max(self.byl_nieobecny, bezczynny)
            return True

        if self.byl_nieobecny:
            # Odejscie dluzsze niz przerwa jest przerwa - nie zaganiamy do kolejnej.
            if self.byl_nieobecny >= self.cfg["przerwaDlugoscMinut"] * 60:
                log.info("Nieobecnosc %.0f min - licze przerwe jako zrobiona",
                         self.byl_nieobecny / 60)
                self.reset_przerwy()
            self.byl_nieobecny = 0.0
        return False

    def wyzwol(self, akcja, reset, termin):
        """Wywoluje przypomnienie albo odklada je, jesli teraz nie wypada."""
        if self.cicha_pora():
            reset()
            return
        if self.cfg["szanujPelnyEkran"] and not mozna_przeszkadzac():
            # Prezentacja, gra, rozmowa wideo: odkladamy, nie gubimy.
            setattr(self, termin, time.time() + ODROCZENIE)
            return
        reset()
        akcja()

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

        win = tk.Toplevel(self.root)
        self.okno_ustawien = win
        win.title(f"{APP_NAME} - ustawienia")
        win.configure(bg=TLO)
        win.attributes("-topmost", True)
        win.resizable(False, False)

        szer, wys = 420, 530
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
        etykiety = {}

        def pole(wiersz, etykieta, klucz):
            dol, gora = LIMITY[klucz]
            etykiety[klucz] = etykieta
            tk.Label(siatka, text=etykieta, bg=TLO, fg=OPIS, font=("Segoe UI", 10),
                     anchor="w").grid(row=wiersz, column=0, sticky="w", pady=5)
            v = tk.StringVar(value=str(self.cfg[klucz]))
            zmienne[klucz] = v
            tk.Spinbox(siatka, from_=dol, to=gora, textvariable=v, width=6, justify="center",
                       font=("Segoe UI", 10), relief="flat", bg=POLE, fg=TEKST,
                       buttonbackground=PRZYCISK, insertbackground=TEKST).grid(
                row=wiersz, column=1, sticky="e", pady=5)

        siatka.columnconfigure(0, weight=1)
        pole(0, "Woda co ile minut", "wodaMinuty")
        pole(1, "Przerwa co ile minut", "przerwaMinuty")
        pole(2, "Dlugosc przerwy (minuty)", "przerwaDlugoscMinut")
        pole(3, "Drzemka - odloz o (minuty)", "drzemkaMinuty")

        dzwiek = tk.BooleanVar(value=self.cfg["dzwiek"])
        cisza = tk.BooleanVar(value=self.cfg["cichaPoraWlaczona"])
        for wiersz, (txt, var) in enumerate([("Dzwiek przy przypomnieniach", dzwiek),
                                             ("Cicha pora (bez przypomnien)", cisza)], start=4):
            tk.Checkbutton(siatka, text=txt, variable=var, bg=TLO, fg=OPIS, selectcolor=POLE,
                           activebackground=TLO, activeforeground=TEKST, font=("Segoe UI", 10),
                           anchor="w", highlightthickness=0, bd=0).grid(
                row=wiersz, column=0, columnspan=2, sticky="w", pady=3)

        pole(6, "Cicha pora od godziny", "cichaPoraOd")
        pole(7, "Cicha pora do godziny", "cichaPoraDo")

        bezczynnosc = tk.BooleanVar(value=self.cfg["bezczynnoscWlaczona"])
        pelny_ekran = tk.BooleanVar(value=self.cfg["szanujPelnyEkran"])
        for wiersz, (txt, var) in enumerate(
                [("Wstrzymaj liczenie, gdy odchodze od komputera", bezczynnosc),
                 ("Nie przerywaj prezentacji i pelnego ekranu", pelny_ekran)], start=8):
            tk.Checkbutton(siatka, text=txt, variable=var, bg=TLO, fg=OPIS, selectcolor=POLE,
                           activebackground=TLO, activeforeground=TEKST, font=("Segoe UI", 10),
                           anchor="w", highlightthickness=0, bd=0).grid(
                row=wiersz, column=0, columnspan=2, sticky="w", pady=3)

        pole(10, "Nieobecnosc liczy sie po (minuty)", "bezczynnoscMinuty")

        blad = tk.Label(win, text="", bg=TLO, fg=BLAD, font=("Segoe UI", 9), wraplength=360)
        blad.pack(pady=(8, 0))

        def zapisz():
            nowy = dict(self.cfg)
            for klucz, v in zmienne.items():
                dol, gora = LIMITY[klucz]
                try:
                    liczba = int(v.get())
                except ValueError:
                    blad.config(text="Wszystkie pola musza byc liczbami.")
                    return
                if not dol <= liczba <= gora:
                    # Spinbox ogranicza strzalki, ale nie wpisywanie z klawiatury.
                    blad.config(text=f"{etykiety[klucz]}: dozwolone {dol}-{gora}, "
                                     f"a wpisano {liczba}.")
                    return
                nowy[klucz] = liczba
            nowy["dzwiek"] = dzwiek.get()
            nowy["cichaPoraWlaczona"] = cisza.get()
            nowy["bezczynnoscWlaczona"] = bezczynnosc.get()
            nowy["szanujPelnyEkran"] = pelny_ekran.get()

            if not zapisz_config(nowy):
                blad.config(text="Nie udalo sie zapisac ustawien - szczegoly w pliku log.")
                return

            # Liczniki zerujemy tylko dla interwalu, ktory faktycznie sie zmienil:
            # zmiana samego dzwieku nie moze kasowac 29 minut odliczania do wody.
            stary = self.cfg
            self.cfg = wczytaj_config()
            if self.cfg["wodaMinuty"] != stary["wodaMinuty"]:
                self.reset_wody()
            if self.cfg["przerwaMinuty"] != stary["przerwaMinuty"]:
                self.reset_przerwy()
            zamknij()
            self.powiadom("Ustawienia zapisane",
                          f"Woda co {self.cfg['wodaMinuty']} min, przerwa co {self.cfg['przerwaMinuty']} min.")

        ramka = tk.Frame(win, bg=TLO)
        ramka.pack(pady=(14, 0))
        tk.Button(ramka, text="Anuluj", width=14, font=("Segoe UI", 10), relief="flat",
                  bg=PRZYCISK, fg=TEKST, command=zamknij).pack(side="left", padx=6)
        tk.Button(ramka, text="Zapisz", width=14, font=("Segoe UI", 10), relief="flat",
                  bg=AKCENT, fg=TEKST, command=zapisz).pack(side="left", padx=6)

        tk.Label(win, text=f"wersja {__version__}", bg=TLO, fg=PRZYCISK,
                 font=("Segoe UI", 8)).pack(side="bottom", pady=6)

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
        win.configure(bg=TLO)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", lambda: self.zamknij_przerwe(win))

        szer, wys = 460, 260
        x = (win.winfo_screenwidth() - szer) // 2
        y = (win.winfo_screenheight() - wys) // 3
        win.geometry(f"{szer}x{wys}+{x}+{y}")

        tk.Label(win, text="Czas na przerwe", bg=TLO, fg=TEKST,
                 font=("Segoe UI", 20, "bold")).pack(pady=(26, 4))
        tk.Label(win, text="Wstan, rozciagnij sie, odwroc wzrok od ekranu.",
                 bg=TLO, fg=OPIS, font=("Segoe UI", 11)).pack()

        pozostalo = [self.cfg["przerwaDlugoscMinut"] * 60]
        zegar = tk.Label(win, text=self.fmt(pozostalo[0]), bg=TLO, fg=AKCENT,
                         font=("Segoe UI", 40, "bold"))
        zegar.pack(pady=10)

        ramka = tk.Frame(win, bg=TLO)
        ramka.pack(pady=(4, 0))
        tk.Button(ramka, text=f"Odloz o {self.cfg['drzemkaMinuty']} min", width=18,
                  font=("Segoe UI", 10), relief="flat", bg=PRZYCISK, fg=TEKST,
                  command=lambda: self.drzemka(win)).pack(side="left", padx=6)
        tk.Button(ramka, text="Zamknij", width=14, font=("Segoe UI", 10), relief="flat",
                  bg=AKCENT, fg=TEKST,
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
        # Samo podniesienie okna. focus_force() wyrywal fokus w trakcie pisania,
        # a spacja albo Enter trafialy wtedy w przycisk "Zamknij".
        win.lift()

    def zamknij_przerwe(self, win):
        self.okno_przerwy = None
        try:
            win.destroy()
        except tk.TclError:
            pass

    def drzemka(self, win):
        self.przerwa_do = time.time() + self.cfg["drzemkaMinuty"] * 60
        self.zamknij_przerwe(win)

    def start(self):
        self.root.mainloop()


def juz_uruchomiony():
    """Jedna instancja na sesje uzytkownika.

    Przestrzen Local, nie Global: Global jest wspolna dla calej maszyny, wiec
    drugi zalogowany uzytkownik nie moglby uruchomic programu u siebie.
    """
    import ctypes
    uchwyt = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\PrzypominaczMutex")
    blad = ctypes.windll.kernel32.GetLastError()
    if not uchwyt:
        log.warning("Nie udalo sie utworzyc mutexu (blad %s) - pomijam kontrole", blad)
        return False
    return blad == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    uruchom_logowanie()
    if juz_uruchomiony():
        log.info("Program juz dziala - koncze te instancje")
        sys.exit(0)
    migruj_stary_config()
    Przypominacz().start()
