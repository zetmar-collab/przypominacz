# -*- coding: utf-8 -*-
"""Odliczanie, uspienie komputera, pauza i cicha pora."""

import datetime as dt
import time

import pytest

import przypominacz as p


def test_termin_liczony_od_zegara(app):
    app.cfg["wodaMinuty"] = 30
    app.reset_wody()
    assert abs((app.woda_do - time.time()) - 1800) < 0.05
    assert 1799 <= app.woda_sek <= 1800


def test_przypomnienie_po_uplywie_terminu(app):
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    app.woda_do = time.time() - 1
    app.tik()
    assert app.zdarzenia == ["woda"]


def test_uspienie_nie_wyrzuca_zaleglych_przypomnien(app):
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    app.pokaz_przerwe = lambda: app.zdarzenia.append("przerwa")
    app.ostatni_tik = time.time() - 3600      # godzina hibernacji
    app.tik()
    assert app.zdarzenia == []                 # zadnej lawiny po wybudzeniu
    assert 1700 < app.woda_sek <= 1800         # liczniki od nowa


def test_krotka_zadyszka_nie_jest_uznana_za_uspienie(app):
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    app.woda_do = time.time() - 1
    app.ostatni_tik = time.time() - 5          # 5 s < PROG_WZNOWIENIA
    app.tik()
    assert app.zdarzenia == ["woda"]


def test_pauza_nie_zjada_czasu(app):
    app.pauza = True
    app.woda_do = time.time() + 70             # 30 s juz uplynelo
    app.ostatni_tik = time.time() - 30
    app.tik()
    assert 99 <= app.woda_sek <= 101           # nadal ~100 s jak przed pauza


def test_pauza_nie_wyzwala_przypomnien(app):
    app.przypomnij_wode = lambda: app.zdarzenia.append("woda")
    app.pauza = True
    app.woda_do = time.time() - 100
    app.tik()
    assert app.zdarzenia == []


def test_drzemka_przesuwa_przerwe(app):
    app.cfg["drzemkaMinuty"] = 5
    app.drzemka(type("Okno", (), {"destroy": lambda s: None})())
    assert 295 <= app.przerwa_sek <= 300
    assert app.okno_przerwy is None


def test_format_czasu():
    assert p.Przypominacz.fmt(0) == "0:00"
    assert p.Przypominacz.fmt(59) == "0:59"
    assert p.Przypominacz.fmt(600) == "10:00"


@pytest.mark.parametrize("godzina, cisza", [
    (21, False), (22, True), (23, True), (0, True), (6, True), (7, False), (12, False)])
def test_cicha_pora_przez_polnoc(app, monkeypatch, godzina, cisza):
    app.cfg.update(cichaPoraWlaczona=True, cichaPoraOd=22, cichaPoraDo=7)

    class Zegar(dt.datetime):
        @classmethod
        def now(cls):
            return dt.datetime(2026, 1, 1, godzina, 0)

    monkeypatch.setattr(p, "datetime", Zegar)
    assert app.cicha_pora() is cisza


@pytest.mark.parametrize("godzina, cisza", [(8, False), (9, True), (16, True), (17, False)])
def test_cicha_pora_w_obrebie_doby(app, monkeypatch, godzina, cisza):
    app.cfg.update(cichaPoraWlaczona=True, cichaPoraOd=9, cichaPoraDo=17)

    class Zegar(dt.datetime):
        @classmethod
        def now(cls):
            return dt.datetime(2026, 1, 1, godzina, 0)

    monkeypatch.setattr(p, "datetime", Zegar)
    assert app.cicha_pora() is cisza


def test_cicha_pora_wylaczona(app):
    app.cfg["cichaPoraWlaczona"] = False
    assert app.cicha_pora() is False
