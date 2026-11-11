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

# Paleta w jednym miejscu. Kontrasty policzone wzgledem TLA wg WCAG:
# TEKST 14.9:1, OPIS 7.9:1, PRZYGASZONY 4.7:1, BLAD 5.3:1, AKCENT 4.7:1 (element
# nietekstowy), bialy napis na AKCENT_PRZYCISK 5.3:1.
TLO = "#1b2838"
TEKST = "#ffffff"
OPIS = "#a8c0d6"
PRZYGASZONY = "#7f93a6"
AKCENT = "#3498db"
AKCENT_PRZYCISK = "#1f6391"
POLE = "#2c3e50"
PRZYCISK = "#34495e"
LINIA = "#2c3e50"
BLAD = "#ef7566"

# Skala rozmiarow pisma - zamiast przypadkowych wartosci w kazdym miejscu.
PISMO = ("Segoe UI", 10)
PISMO_MALE = ("Segoe UI", 9)
PISMO_SEKCJA = ("Segoe UI", 9, "bold")
PISMO_NAGLOWEK = ("Segoe UI", 16, "bold")
PISMO_HERO = ("Segoe UI", 20, "bold")
PISMO_ZEGAR = ("Segoe UI", 40, "bold")

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


# --- wyglad okien ----------------------------------------------------------

def rozjasnij(kolor, o=0.10):
    """Jasniejszy wariant koloru na stan pod kursorem."""
    r, g, b = (int(kolor[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(min(255, round(k + (255 - k) * o)) for k in (r, g, b))


_ikona_okna = None


def ustaw_ikone_okna(okno):
    """Bez tego okna pokazuja domyslne pioro Tk zamiast ikony programu."""
    global _ikona_okna
    try:
        from PIL import ImageTk
        if _ikona_okna is None:
            _ikona_okna = ImageTk.PhotoImage(IKONA_AKTYWNA)
        okno.iconphoto(False, _ikona_okna)
    except Exception as e:
        log.debug("Nie udalo sie ustawic ikony okna: %s", e)


def ciemny_pasek_tytulu(okno):
    """Jasny pasek tytulu nad ciemnym oknem wyglada jak pomylka - prosimy o ciemny."""
    try:
        import ctypes
        okno.update_idletasks()
        uchwyt = ctypes.windll.user32.GetParent(okno.winfo_id())
        wlacz = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 w nowszych Windows, 19 w starszych
        for atrybut in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    uchwyt, atrybut, ctypes.byref(wlacz), ctypes.sizeof(wlacz)) == 0:
                return
    except Exception as e:
        log.debug("Nie udalo sie przyciemnic paska tytulu: %s", e)


def dopasuj_wysokosc(okno, szer):
    """Wysokosc z zawartosci, a nie wpisana na sztywno.

    Przy wpisanej wysokosci dolozenie jednego wiersza wypycha przyciski poza
    ekran, a przy innym skalowaniu pisma dzieje sie to samo bez zmian w kodzie.
    """
    okno.update_idletasks()
    wys = okno.winfo_reqheight()
    x = (okno.winfo_screenwidth() - szer) // 2
    y = max(0, (okno.winfo_screenheight() - wys) // 3)
    okno.geometry(f"{szer}x{wys}+{x}+{y}")


def przygotuj_okno(okno, tytul, szer, wys, zamknij):
    """Wspolny szkielet obu okien: tytul, ikona, pozycja, Escape."""
    okno.title(tytul)
    okno.configure(bg=TLO)
    okno.attributes("-topmost", True)
    okno.resizable(False, False)
    okno.protocol("WM_DELETE_WINDOW", zamknij)
    okno.bind("<Escape>", lambda _: zamknij())
    x = (okno.winfo_screenwidth() - szer) // 2
    y = (okno.winfo_screenheight() - wys) // 3
    okno.geometry(f"{szer}x{wys}+{x}+{y}")
    ustaw_ikone_okna(okno)
    ciemny_pasek_tytulu(okno)


def przycisk(rodzic, tekst, polecenie, glowny=False):
    """Przycisk ze stanem pod kursorem i widoczna obwodka przy obsludze klawiatura."""
    tlo = AKCENT_PRZYCISK if glowny else PRZYCISK
    return tk.Button(rodzic, text=tekst, command=polecenie, font=PISMO,
                     relief="flat", bd=0, bg=tlo, fg=TEKST,
                     activebackground=rozjasnij(tlo), activeforeground=TEKST,
                     cursor="hand2", padx=16, pady=7,
                     highlightthickness=2, highlightbackground=TLO, highlightcolor=AKCENT)


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
            pystray.MenuItem("Zrób przerwę teraz", lambda: self.kolejka.put("przerwa")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pauza", lambda: self.kolejka.put("pauza"), checked=lambda i: self.pauza),
            pystray.MenuItem("Ustawienia...", lambda: self.kolejka.put("config")),
            pystray.MenuItem("Autostart — ustawienia Windows", lambda: self.kolejka.put("startupapps"))
            if MSIX else
            pystray.MenuItem("Uruchamiaj z Windows", lambda: self.kolejka.put("autostart"),
                             checked=lambda i: autostart_wlaczony()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Zakończ", lambda: self.kolejka.put("koniec")),
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
                self.powiadom("Błąd", f"{cmd}: {e}")

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
                self.powiadom("Nie udało się zmienić autostartu", str(e))
                return
            if autostart_wlaczony() == wlacz:
                self.powiadom("Autostart " + ("włączony" if wlacz else "wyłączony"),
                              "Program będzie startował razem z Windows." if wlacz
                              else "Program nie będzie już startował razem z Windows.")
            else:
                self.powiadom("Autostart bez zmian",
                              "Windows nie przyjął wpisu — sprawdź ustawienia zabezpieczeń.")
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
        self.powiadom("Czas na wodę", "Wypij szklankę wody — nawodnij się i wróć do pracy.")

    # --- okno ustawien ---
    def pokaz_ustawienia(self):
        if self.okno_ustawien is not None and self.okno_ustawien.winfo_exists():
            self.okno_ustawien.lift()
            self.okno_ustawien.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.okno_ustawien = win

        def zamknij():
            self.okno_ustawien = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        przygotuj_okno(win, f"{APP_NAME} - ustawienia", 440, 560, zamknij)

        tk.Label(win, text="Ustawienia", bg=TLO, fg=TEKST,
                 font=PISMO_NAGLOWEK).pack(pady=(16, 10))

        siatka = tk.Frame(win, bg=TLO)
        siatka.pack(padx=28, fill="x")
        siatka.columnconfigure(0, weight=1)

        zmienne = {}
        etykiety = {}

        def sekcja(wiersz, tytul):
            """Naglowek grupy - 11 wierszy pod rzad czyta sie zle."""
            ramka = tk.Frame(siatka, bg=TLO)
            ramka.grid(row=wiersz, column=0, columnspan=2, sticky="ew", pady=(12, 4))
            tk.Label(ramka, text=tytul.upper(), bg=TLO, fg=PRZYGASZONY,
                     font=PISMO_SEKCJA).pack(side="left")
            tk.Frame(ramka, bg=LINIA, height=1).pack(side="left", fill="x",
                                                     expand=True, padx=(10, 0), pady=(2, 0))

        def pole(wiersz, etykieta, klucz):
            dol, gora = LIMITY[klucz]
            etykiety[klucz] = etykieta
            tk.Label(siatka, text=etykieta, bg=TLO, fg=OPIS, font=PISMO,
                     anchor="w").grid(row=wiersz, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=str(self.cfg[klucz]))
            zmienne[klucz] = v
            tk.Spinbox(siatka, from_=dol, to=gora, textvariable=v, width=5, justify="center",
                       font=PISMO, relief="flat", bd=0, bg=POLE, fg=TEKST,
                       buttonbackground=PRZYCISK, insertbackground=TEKST,
                       readonlybackground=POLE, highlightthickness=1,
                       highlightbackground=LINIA, highlightcolor=AKCENT).grid(
                row=wiersz, column=1, sticky="e", pady=3, ipady=2)

        def przelacznik(wiersz, tekst, zmienna):
            tk.Checkbutton(siatka, text=tekst, variable=zmienna, bg=TLO, fg=OPIS,
                           selectcolor=POLE, activebackground=TLO, activeforeground=TEKST,
                           font=PISMO, anchor="w", cursor="hand2",
                           highlightthickness=1, highlightbackground=TLO,
                           highlightcolor=AKCENT, bd=0).grid(
                row=wiersz, column=0, columnspan=2, sticky="w", pady=1)

        dzwiek = tk.BooleanVar(value=self.cfg["dzwiek"])
        cisza = tk.BooleanVar(value=self.cfg["cichaPoraWlaczona"])
        bezczynnosc = tk.BooleanVar(value=self.cfg["bezczynnoscWlaczona"])
        pelny_ekran = tk.BooleanVar(value=self.cfg["szanujPelnyEkran"])

        sekcja(0, "Przypomnienia")
        pole(1, "Woda co ile minut", "wodaMinuty")
        pole(2, "Przerwa co ile minut", "przerwaMinuty")
        pole(3, "Długość przerwy (minuty)", "przerwaDlugoscMinut")
        pole(4, "Drzemka — odłóż o (minuty)", "drzemkaMinuty")
        przelacznik(5, "Dźwięk przy przypomnieniach", dzwiek)

        sekcja(6, "Cisza")
        przelacznik(7, "Cicha pora (bez przypomnień)", cisza)
        pole(8, "Cicha pora od godziny", "cichaPoraOd")
        pole(9, "Cicha pora do godziny", "cichaPoraDo")

        sekcja(10, "Gdy Cię nie ma")
        przelacznik(11, "Wstrzymaj liczenie, gdy odchodzę od komputera", bezczynnosc)
        przelacznik(12, "Nie przerywaj prezentacji i pełnego ekranu", pelny_ekran)
        pole(13, "Nieobecność liczy się po (minuty)", "bezczynnoscMinuty")

        blad = tk.Label(win, text="", bg=TLO, fg=BLAD, font=PISMO_MALE, wraplength=380)
        blad.pack(pady=(10, 0))

        def zapisz(*_):
            nowy = dict(self.cfg)
            for klucz, v in zmienne.items():
                dol, gora = LIMITY[klucz]
                try:
                    liczba = int(v.get())
                except ValueError:
                    blad.config(text="Wszystkie pola muszą być liczbami.")
                    return
                if not dol <= liczba <= gora:
                    # Spinbox ogranicza strzałki, ale nie wpisywanie z klawiatury.
                    blad.config(text=f"{etykiety[klucz]}: dozwolone {dol}-{gora}, "
                                     f"a wpisano {liczba}.")
                    return
                nowy[klucz] = liczba
            nowy["dzwiek"] = dzwiek.get()
            nowy["cichaPoraWlaczona"] = cisza.get()
            nowy["bezczynnoscWlaczona"] = bezczynnosc.get()
            nowy["szanujPelnyEkran"] = pelny_ekran.get()

            if not zapisz_config(nowy):
                blad.config(text="Nie udało się zapisać ustawień — szczegóły w pliku log.")
                return

            # Liczniki zerujemy tylko dla interwału, który faktycznie się zmienił:
            # zmiana samego dźwięku nie może kasować 29 minut odliczania do wody.
            stary = self.cfg
            self.cfg = wczytaj_config()
            if self.cfg["wodaMinuty"] != stary["wodaMinuty"]:
                self.reset_wody()
            if self.cfg["przerwaMinuty"] != stary["przerwaMinuty"]:
                self.reset_przerwy()
            zamknij()
            self.powiadom("Ustawienia zapisane",
                          f"Woda co {self.cfg['wodaMinuty']} min, "
                          f"przerwa co {self.cfg['przerwaMinuty']} min.")

        ramka = tk.Frame(win, bg=TLO)
        ramka.pack(pady=(14, 0))
        przycisk(ramka, "Anuluj", zamknij).pack(side="left", padx=6)
        zapisz_btn = przycisk(ramka, "Zapisz", zapisz, glowny=True)
        zapisz_btn.pack(side="left", padx=6)

        tk.Label(win, text=f"wersja {__version__}", bg=TLO, fg=PRZYGASZONY,
                 font=PISMO_MALE).pack(side="bottom", pady=(8, 12))

        win.bind("<Return>", zapisz)
        dopasuj_wysokosc(win, 440)
        win.lift()
        win.focus_force()
        zapisz_btn.focus_set()

    # --- okno przerwy ---
    def pokaz_przerwe(self):
        if self.okno_przerwy is not None and self.okno_przerwy.winfo_exists():
            return
        if self.cfg["dzwiek"]:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

        win = tk.Toplevel(self.root)
        self.okno_przerwy = win
        przygotuj_okno(win, f"{APP_NAME} - przerwa", 480, 300,
                       lambda: self.zamknij_przerwe(win))

        tk.Label(win, text="Czas na przerwę", bg=TLO, fg=TEKST,
                 font=PISMO_HERO).pack(pady=(28, 6))
        tk.Label(win, text="Wstań, rozciągnij się, odwróć wzrok od ekranu.",
                 bg=TLO, fg=OPIS, font=("Segoe UI", 11)).pack()

        pozostalo = [self.cfg["przerwaDlugoscMinut"] * 60]
        zegar = tk.Label(win, text=self.fmt(pozostalo[0]), bg=TLO, fg=AKCENT,
                         font=PISMO_ZEGAR)
        zegar.pack(pady=(14, 2))
        tk.Label(win, text="Okno zamknie się samo.", bg=TLO, fg=PRZYGASZONY,
                 font=PISMO_MALE).pack()

        ramka = tk.Frame(win, bg=TLO)
        ramka.pack(pady=(16, 24))
        # Oba przyciski sa drugorzedne: akcent nalezy do zegara, a nie do pomijania przerwy.
        przycisk(ramka, f"Odłóż o {self.cfg['drzemkaMinuty']} min",
                 lambda: self.drzemka(win)).pack(side="left", padx=6)
        przycisk(ramka, "Zamknij", lambda: self.zamknij_przerwe(win)).pack(side="left", padx=6)

        def odliczaj():
            if not win.winfo_exists():
                return
            pozostalo[0] -= 1
            if pozostalo[0] <= 0:
                zegar.config(text="0:00")
                if self.cfg["dzwiek"]:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                self.zamknij_przerwe(win)
                self.powiadom("Przerwa zakończona", "Możesz wracać do pracy.")
                return
            zegar.config(text=self.fmt(pozostalo[0]))
            win.after(1000, odliczaj)

        dopasuj_wysokosc(win, 480)
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
