# -*- coding: utf-8 -*-
"""Autostart - obszar, ktory juz raz zawiodl u uzytkownika."""

import winreg

import pytest

import przypominacz as p

KLUCZ_TESTOWY = r"Software\PrzypominaczTest\Run"


@pytest.fixture
def rejestr(monkeypatch):
    monkeypatch.setattr(p, "RUN_KEY", KLUCZ_TESTOWY)
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, KLUCZ_TESTOWY)
    yield
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KLUCZ_TESTOWY)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\PrzypominaczTest")
    except OSError:
        pass


def test_wlaczenie_i_wylaczenie(rejestr):
    assert p.autostart_wlaczony() is False
    p.ustaw_autostart(True)
    assert p.autostart_wlaczony() is True
    p.ustaw_autostart(False)
    assert p.wpis_autostartu() is None


def test_powtorne_wylaczenie_nie_rzuca(rejestr):
    p.ustaw_autostart(False)
    p.ustaw_autostart(False)


def test_wpis_rozpoznawany_mimo_innego_zapisu(rejestr):
    """Inne cudzyslowy i wielkosc liter to nadal nasz wpis."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, p.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, p.APP_NAME, 0, winreg.REG_SZ,
                          p.polecenie_autostartu().strip('"').upper())
    assert p.autostart_wlaczony() is True


def test_naprawa_wpisu_po_przeniesieniu_programu(rejestr):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, p.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, p.APP_NAME, 0, winreg.REG_SZ, r'"D:\stara\sciezka\Przypominacz.exe"')
    p.napraw_autostart()
    assert p.wpis_autostartu() == p.polecenie_autostartu()


def test_naprawa_nie_tworzy_wpisu_gdy_autostart_wylaczony(rejestr):
    p.napraw_autostart()
    assert p.wpis_autostartu() is None


def test_w_pakiecie_msix_naprawa_nie_dotyka_rejestru(rejestr, monkeypatch):
    """W pakiecie autostartem zarzadza Windows, nie my."""
    monkeypatch.setattr(p, "MSIX", True)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, p.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, p.APP_NAME, 0, winreg.REG_SZ, "cudzy wpis")
    p.napraw_autostart()
    assert p.wpis_autostartu() == "cudzy wpis"
