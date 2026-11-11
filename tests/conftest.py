# -*- coding: utf-8 -*-
"""Wspolne przybory testowe: izolacja danych, bezokienkowy egzemplarz aplikacji."""

import os
import queue
import sys
import time
import tkinter as tk

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import przypominacz as p  # noqa: E402


@pytest.fixture
def dane(tmp_path, monkeypatch):
    """Konfiguracja w katalogu tymczasowym - testy nie dotykaja profilu uzytkownika."""
    monkeypatch.setattr(p, "DANE_DIR", str(tmp_path))
    monkeypatch.setattr(p, "CONFIG_PATH", str(tmp_path / "config.json"))
    return tmp_path


@pytest.fixture
def katalog_bez_zapisu(tmp_path):
    """Katalog z odebranym prawem zapisu - imituje Program Files albo dysk sieciowy."""
    ro = tmp_path / "ro"
    ro.mkdir()
    os.system(f'icacls "{ro}" /deny "%USERNAME%":(W) >nul 2>&1')
    yield ro
    os.system(f'icacls "{ro}" /remove:d "%USERNAME%" >nul 2>&1')


@pytest.fixture(scope="session")
def _tk():
    """Jedno okno glowne na caly przebieg - Tk nie znosi wielokrotnego tworzenia."""
    r = tk.Tk()
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def root(_tk):
    yield _tk
    for okno in _tk.winfo_children():      # sprzatamy okna po tescie
        try:
            okno.destroy()
        except tk.TclError:
            pass


@pytest.fixture
def app(dane, root, monkeypatch):
    """Aplikacja bez ikony w trayu i bez prawdziwych powiadomien."""
    a = p.Przypominacz.__new__(p.Przypominacz)
    a.cfg = p.wczytaj_config()
    a.pauza = False
    a.kolejka = queue.Queue()
    a.okno_przerwy = a.okno_ustawien = None
    a.root = root
    a.zdarzenia = []
    a.powiadomienia = []

    class Ikona:
        title = ""
        icon = None

        def notify(self, tresc, tytul):
            a.powiadomienia.append((tytul, tresc))

        def stop(self):
            a.zdarzenia.append("stop ikony")

    a.ikona = Ikona()
    a.reset_wody()
    a.reset_przerwy()
    a.ostatni_tik = time.time()
    # tik nie planuje kolejnego tiku - test wywoluje go recznie
    monkeypatch.setattr(root, "after", lambda *args, **kw: None)
    return a
