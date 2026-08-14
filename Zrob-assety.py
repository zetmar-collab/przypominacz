# -*- coding: utf-8 -*-
"""Generuje komplet logotypow MSIX (folder Assets) z tej samej kropli co ikona w trayu."""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from przypominacz import zrob_ikone  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Assets")
ZRODLO = zrob_ikone((41, 128, 185, 255)).resize((1024, 1024), Image.LANCZOS)

# Sklep wymaga StoreLogo + Square44x44 + Square150x150; reszta poprawia wyglad kafelkow.
KWADRATY = {
    "StoreLogo.png": 50,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square150x150Logo.png": 150,
    "Square310x310Logo.png": 310,
    # warianty dla paska zadan i listy aplikacji (bez podkladki systemowej)
    "Square44x44Logo.targetsize-16_altform-unplated.png": 16,
    "Square44x44Logo.targetsize-24_altform-unplated.png": 24,
    "Square44x44Logo.targetsize-32_altform-unplated.png": 32,
    "Square44x44Logo.targetsize-48_altform-unplated.png": 48,
    "Square44x44Logo.targetsize-256_altform-unplated.png": 256,
}


def kwadrat(rozmiar):
    """Kropla z niewielkim marginesem - Windows przycina logotypy przy krawedziach."""
    plotno = Image.new("RGBA", (rozmiar, rozmiar), (0, 0, 0, 0))
    margines = max(1, round(rozmiar * 0.08))
    bok = rozmiar - 2 * margines
    plotno.paste(ZRODLO.resize((bok, bok), Image.LANCZOS), (margines, margines))
    return plotno


def prostokat(szer, wys):
    plotno = Image.new("RGBA", (szer, wys), (0, 0, 0, 0))
    bok = round(wys * 0.72)
    ikona = ZRODLO.resize((bok, bok), Image.LANCZOS)
    plotno.paste(ikona, ((szer - bok) // 2, (wys - bok) // 2))
    return plotno


def main():
    os.makedirs(ASSETS, exist_ok=True)
    for nazwa, rozmiar in KWADRATY.items():
        kwadrat(rozmiar).save(os.path.join(ASSETS, nazwa))
    prostokat(310, 150).save(os.path.join(ASSETS, "Wide310x150Logo.png"))
    prostokat(620, 300).save(os.path.join(ASSETS, "SplashScreen.png"))
    print(f"Zapisano {len(KWADRATY) + 2} plikow w {ASSETS}")


if __name__ == "__main__":
    main()
