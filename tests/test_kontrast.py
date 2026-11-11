# -*- coding: utf-8 -*-
"""Kontrast palety wg WCAG 2.1 - zeby nie zgubic go przy kolejnej zmianie kolorow."""

import pytest

import przypominacz as p


def luminancja(kolor):
    kolor = kolor.lstrip("#")
    kanaly = []
    for i in (0, 2, 4):
        c = int(kolor[i:i + 2], 16) / 255
        kanaly.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * kanaly[0] + 0.7152 * kanaly[1] + 0.0722 * kanaly[2]


def kontrast(pierwszy, drugi):
    a, b = luminancja(pierwszy), luminancja(drugi)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# (opis, kolor pisma, tlo, wymagany kontrast)
PARY = [
    ("tekst glowny", p.TEKST, p.TLO, 4.5),
    ("opisy pol", p.OPIS, p.TLO, 4.5),
    ("tekst przygaszony", p.PRZYGASZONY, p.TLO, 4.5),
    ("komunikat bledu", p.BLAD, p.TLO, 4.5),
    ("napis na przycisku glownym", p.TEKST, p.AKCENT_PRZYCISK, 4.5),
    ("napis na przycisku drugim", p.TEKST, p.PRZYCISK, 4.5),
    ("tekst w polu liczbowym", p.TEKST, p.POLE, 4.5),
    ("zegar (element nietekstowy)", p.AKCENT, p.TLO, 3.0),
]


@pytest.mark.parametrize("opis, pismo, tlo, wymog", PARY, ids=[x[0] for x in PARY])
def test_kontrast_palety(opis, pismo, tlo, wymog):
    wynik = kontrast(pismo, tlo)
    assert wynik >= wymog, f"{opis}: {wynik:.2f}:1, wymagane {wymog}:1"


def test_jasniejszy_wariant_na_stan_pod_kursorem():
    """Stan pod kursorem musi byc widocznie jasniejszy, ale nie bialy."""
    for kolor in (p.PRZYCISK, p.AKCENT_PRZYCISK):
        jasniejszy = p.rozjasnij(kolor, 0.10)
        assert luminancja(jasniejszy) > luminancja(kolor)
        assert kontrast(p.TEKST, jasniejszy) >= 4.5
