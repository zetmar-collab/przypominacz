# -*- coding: utf-8 -*-
"""Robi zrzuty ekranu do listingu w Sklepie Windows (1366x768, katalog Zrzuty).

Otwiera kolejno okna aplikacji, wycina je z ekranu i sklada na ciemnym tle.
"""

import ctypes
import os
import sys
import tkinter as tk
from ctypes import wintypes

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import przypominacz as p  # noqa: E402

WYNIK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Zrzuty")
PLOTNO = (1366, 768)
TLO_GORA, TLO_DOL = (18, 30, 44), (10, 17, 26)


def tlo():
    """Delikatny pionowy gradient - okno aplikacji ma na czym stac."""
    img = Image.new("RGB", PLOTNO, TLO_GORA)
    for y in range(PLOTNO[1]):
        t = y / (PLOTNO[1] - 1)
        kolor = tuple(round(a + (b - a) * t) for a, b in zip(TLO_GORA, TLO_DOL))
        img.paste(kolor, (0, y, PLOTNO[0], y + 1))
    return img


def zrzut_okna(okno):
    """Przechwytuje same piksele okna (PrintWindow) - bez pulpitu i cudzych okien."""
    okno.update_idletasks()
    okno.update()
    hwnd = int(okno.wm_frame(), 16)

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    prostokat = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(prostokat))
    w = prostokat.right - prostokat.left
    h = prostokat.bottom - prostokat.top

    hdc_okna = user32.GetWindowDC(hwnd)
    hdc_pamiec = gdi32.CreateCompatibleDC(hdc_okna)
    bitmapa = gdi32.CreateCompatibleBitmap(hdc_okna, w, h)
    gdi32.SelectObject(hdc_pamiec, bitmapa)
    # PW_RENDERFULLCONTENT = 2 - dziala takze dla okien zaslonietych
    user32.PrintWindow(hwnd, hdc_pamiec, 2)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    naglowek = BITMAPINFOHEADER()
    naglowek.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    naglowek.biWidth, naglowek.biHeight = w, -h  # minus = od gory
    naglowek.biPlanes, naglowek.biBitCount = 1, 32
    bufor = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_pamiec, bitmapa, 0, h, bufor, ctypes.byref(naglowek), 0)

    gdi32.DeleteObject(bitmapa)
    gdi32.DeleteDC(hdc_pamiec)
    user32.ReleaseDC(hwnd, hdc_okna)
    return Image.frombuffer("RGB", (w, h), bufor, "raw", "BGRX", 0, 1)


def zloz(okno, nazwa, skala=1.0):
    wyciete = zrzut_okna(okno)
    if skala != 1.0:
        wyciete = wyciete.resize((round(wyciete.width * skala), round(wyciete.height * skala)),
                                 Image.LANCZOS)
    plotno = tlo()
    plotno.paste(wyciete, ((PLOTNO[0] - wyciete.width) // 2, (PLOTNO[1] - wyciete.height) // 2))
    sciezka = os.path.join(WYNIK, nazwa)
    plotno.save(sciezka)
    print("zapisano", sciezka)


def main():
    os.makedirs(WYNIK, exist_ok=True)
    app = p.Przypominacz.__new__(p.Przypominacz)
    app.cfg = p.wczytaj_config()
    app.cfg["dzwiek"] = False
    app.okno_przerwy = app.okno_ustawien = None
    app.root = tk.Tk()
    app.root.withdraw()
    app.woda_sek = app.przerwa_sek = 600
    app.powiadom = lambda *a: None

    app.pokaz_przerwe()
    zloz(app.okno_przerwy, "01-przerwa.png", 1.4)
    app.zamknij_przerwe(app.okno_przerwy)

    app.pokaz_ustawienia()
    zloz(app.okno_ustawien, "02-ustawienia.png", 1.3)
    app.okno_ustawien.destroy()

    app.root.destroy()


if __name__ == "__main__":
    main()
