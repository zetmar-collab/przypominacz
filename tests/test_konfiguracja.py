# -*- coding: utf-8 -*-
"""Wczytywanie i zapis ustawien - sciezki, ktore juz raz zabily start programu."""

import json
import os

import przypominacz as p


def test_brak_pliku_tworzy_domyslny(dane):
    cfg = p.wczytaj_config()
    assert cfg["wodaMinuty"] == 30
    assert os.path.exists(p.CONFIG_PATH)


def test_uszkodzony_json_nie_wywraca_programu(dane):
    open(p.CONFIG_PATH, "w").write("{obciety plik")
    cfg = p.wczytaj_config()
    assert cfg == p.DEFAULTS
    # uszkodzony plik jest odlozony, a nie skasowany po cichu
    assert os.path.exists(p.CONFIG_PATH + ".uszkodzony")


def test_katalog_bez_prawa_zapisu_nie_wywraca_startu(dane, katalog_bez_zapisu, monkeypatch):
    monkeypatch.setattr(p, "DANE_DIR", str(katalog_bez_zapisu))
    monkeypatch.setattr(p, "CONFIG_PATH", str(katalog_bez_zapisu / "config.json"))
    cfg = p.wczytaj_config()          # nie moze rzucic PermissionError
    assert cfg == p.DEFAULTS
    assert p.zapisz_config(cfg) is False


def test_obce_klucze_i_zle_typy(dane):
    json.dump({"wodaMinuty": "piec", "nieznane": 1, "dzwiek": 0},
              open(p.CONFIG_PATH, "w"))
    cfg = p.wczytaj_config()
    assert cfg["wodaMinuty"] == 30     # tekst -> wartosc domyslna
    assert cfg["dzwiek"] is False      # 0 -> False
    assert cfg["nieznane"] == 1        # obcy klucz przechodzi, ale nic nie psuje


def test_wartosci_ujemne_i_zero_podnoszone_do_jedynki(dane):
    json.dump({"wodaMinuty": 0, "drzemkaMinuty": -5}, open(p.CONFIG_PATH, "w"))
    cfg = p.wczytaj_config()
    assert cfg["wodaMinuty"] == 1
    assert cfg["drzemkaMinuty"] == 1


def test_zapis_jest_atomowy(dane):
    assert p.zapisz_config(dict(p.DEFAULTS)) is True
    assert not os.path.exists(p.CONFIG_PATH + ".tmp")
    assert json.load(open(p.CONFIG_PATH, encoding="utf-8"))["wodaMinuty"] == 30


def test_migracja_ze_starej_lokalizacji(dane, tmp_path, monkeypatch):
    stary = tmp_path / "stary" / "config.json"
    stary.parent.mkdir()
    json.dump({"wodaMinuty": 17}, open(stary, "w"))
    monkeypatch.setattr(p, "STARY_CONFIG", str(stary))
    p.migruj_stary_config()
    assert p.wczytaj_config()["wodaMinuty"] == 17


def test_migracja_nie_nadpisuje_istniejacych_ustawien(dane, tmp_path, monkeypatch):
    json.dump({"wodaMinuty": 42}, open(p.CONFIG_PATH, "w"))
    stary = tmp_path / "stary.json"
    json.dump({"wodaMinuty": 17}, open(stary, "w"))
    monkeypatch.setattr(p, "STARY_CONFIG", str(stary))
    p.migruj_stary_config()
    assert p.wczytaj_config()["wodaMinuty"] == 42


def test_wartosci_poza_zakresem_sa_przycinane(dane):
    json.dump({"wodaMinuty": 99999, "cichaPoraOd": 99}, open(p.CONFIG_PATH, "w"))
    cfg = p.wczytaj_config()
    assert cfg["wodaMinuty"] == 600                 # gorny limit
    assert cfg["cichaPoraOd"] == 23
