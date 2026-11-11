# -*- coding: utf-8 -*-
"""Wykrywanie nieobecnosci i szanowanie pelnego ekranu."""

import time

import przypominacz as p


def test_odczyt_bezczynnosci_dziala(app):
    assert isinstance(p.sekundy_bezczynnosci(), float)
    assert p.sekundy_bezczynnosci() >= 0


def test_nieobecnosc_wstrzymuje_liczniki(app, monkeypatch):
    app.cfg.update(bezczynnoscWlaczona=True, bezczynnoscMinuty=5)
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    monkeypatch.setattr(p, "sekundy_bezczynnosci", lambda: 600)   # 10 min bez ruchu
    app.woda_do = time.time() + 70
    app.ostatni_tik = time.time() - 30
    app.tik()
    assert app.zdarzenia == []
    assert 99 <= app.woda_sek <= 101        # 30 s nieobecnosci nie zjadlo czasu


def test_powrot_po_dlugiej_nieobecnosci_liczy_przerwe_jako_zrobiona(app, monkeypatch):
    app.cfg.update(bezczynnoscWlaczona=True, bezczynnoscMinuty=5, przerwaDlugoscMinut=5,
                   przerwaMinuty=60)
    monkeypatch.setattr(p, "sekundy_bezczynnosci", lambda: 900)   # 15 min nieobecnosci
    app.ostatni_tik = time.time() - 1
    app.tik()
    app.przerwa_do = time.time() + 10                              # przerwa tuz-tuz
    monkeypatch.setattr(p, "sekundy_bezczynnosci", lambda: 0)      # wrocil
    app.ostatni_tik = time.time() - 1
    app.tik()
    assert app.przerwa_sek > 3000          # licznik przerwy wystartowal od nowa


def test_krotkie_odejscie_nie_kasuje_przerwy(app, monkeypatch):
    # nieobecnosc wykrywana po 5 min, ale przerwa trwa 10 - 6 min to za malo
    app.cfg.update(bezczynnoscWlaczona=True, bezczynnoscMinuty=5, przerwaDlugoscMinut=10)
    monkeypatch.setattr(p, "sekundy_bezczynnosci", lambda: 360)   # 6 min < dlugosc przerwy
    app.ostatni_tik = time.time() - 1
    app.tik()
    app.przerwa_do = time.time() + 100
    monkeypatch.setattr(p, "sekundy_bezczynnosci", lambda: 0)
    app.ostatni_tik = time.time() - 1
    app.tik()
    assert app.przerwa_sek <= 101          # przerwa nadal przed nami


def test_wylaczone_wykrywanie_nie_wstrzymuje_niczego(app, monkeypatch):
    app.cfg["bezczynnoscWlaczona"] = False
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    monkeypatch.setattr(p, "sekundy_bezczynnosci", lambda: 9999)
    app.woda_do = time.time() - 1
    app.tik()
    assert app.zdarzenia == ["woda"]


def test_pelny_ekran_odklada_przypomnienie(app, monkeypatch):
    app.cfg["szanujPelnyEkran"] = True
    app.cfg["bezczynnoscWlaczona"] = False
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    monkeypatch.setattr(p, "mozna_przeszkadzac", lambda: False)
    app.woda_do = time.time() - 1
    app.tik()
    assert app.zdarzenia == []                       # nie przeszkadzamy
    assert 55 <= app.woda_sek <= p.ODROCZENIE        # ale wrocimy za minute


def test_po_zakonczeniu_prezentacji_przypomnienie_wraca(app, monkeypatch):
    app.cfg.update(szanujPelnyEkran=True, bezczynnoscWlaczona=False)
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    monkeypatch.setattr(p, "mozna_przeszkadzac", lambda: False)
    app.woda_do = time.time() - 1
    app.tik()
    monkeypatch.setattr(p, "mozna_przeszkadzac", lambda: True)
    app.woda_do = time.time() - 1
    app.ostatni_tik = time.time()
    app.tik()
    assert app.zdarzenia == ["woda"]


def test_cicha_pora_ma_pierwszenstwo_przed_odroczeniem(app, monkeypatch):
    app.cfg.update(cichaPoraWlaczona=True, cichaPoraOd=0, cichaPoraDo=23,
                   szanujPelnyEkran=True, bezczynnoscWlaczona=False, wodaMinuty=30)
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    monkeypatch.setattr(p, "mozna_przeszkadzac", lambda: False)
    app.woda_do = time.time() - 1
    app.tik()
    assert app.zdarzenia == []
    assert app.woda_sek > p.ODROCZENIE     # pelny reset, nie odroczenie o minute
