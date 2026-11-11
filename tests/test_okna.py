# -*- coding: utf-8 -*-
"""Okna przerwy i ustawien."""

import tkinter as tk

import przypominacz as p


def przyciski(okno):
    wynik = []
    def chodz(w):
        for dziecko in w.winfo_children():
            if dziecko.winfo_class() == "Button":
                wynik.append(dziecko)
            chodz(dziecko)
    chodz(okno)
    return wynik


def pola_liczbowe(okno):
    wynik = []
    def chodz(w):
        for dziecko in w.winfo_children():
            if dziecko.winfo_class() == "Spinbox":
                wynik.append(dziecko)
            chodz(dziecko)
    chodz(okno)
    return wynik


def test_okno_przerwy_odlicza(app):
    app.cfg["przerwaDlugoscMinut"] = 5
    app.cfg["dzwiek"] = False
    app.pokaz_przerwe()
    app.root.update()
    etykiety = [w for w in app.okno_przerwy.winfo_children() if w.winfo_class() == "Label"]
    assert any(w.cget("text") == "5:00" for w in etykiety)
    assert app.okno_przerwy.attributes("-topmost") == 1


def test_drugie_wywolanie_nie_tworzy_drugiego_okna(app):
    app.cfg["dzwiek"] = False
    app.pokaz_przerwe()
    pierwsze = app.okno_przerwy
    app.pokaz_przerwe()
    assert app.okno_przerwy is pierwsze


def test_zamkniecie_czysci_uchwyt(app):
    app.cfg["dzwiek"] = False
    app.pokaz_przerwe()
    app.zamknij_przerwe(app.okno_przerwy)
    assert app.okno_przerwy is None


def test_okno_ustawien_pokazuje_biezace_wartosci(app):
    app.cfg["wodaMinuty"] = 25
    app.pokaz_ustawienia()
    app.root.update()
    assert pola_liczbowe(app.okno_ustawien)[0].get() == "25"


def test_ustawienia_nie_otwieraja_sie_dwa_razy(app):
    app.pokaz_ustawienia()
    pierwsze = app.okno_ustawien
    app.pokaz_ustawienia()
    assert app.okno_ustawien is pierwsze


def test_zapis_ustawien_trafia_do_pliku(app):
    app.pokaz_ustawienia()
    app.root.update()
    pole = pola_liczbowe(app.okno_ustawien)[0]
    pole.delete(0, "end")
    pole.insert(0, "12")
    [b for b in przyciski(app.okno_ustawien) if b.cget("text") == "Zapisz"][0].invoke()
    app.root.update()
    assert p.wczytaj_config()["wodaMinuty"] == 12
    assert app.okno_ustawien is None


def test_tekst_zamiast_liczby_jest_odrzucany(app):
    app.pokaz_ustawienia()
    app.root.update()
    pole = pola_liczbowe(app.okno_ustawien)[0]
    pole.delete(0, "end")
    pole.insert(0, "abc")
    [b for b in przyciski(app.okno_ustawien) if b.cget("text") == "Zapisz"][0].invoke()
    app.root.update()
    assert app.okno_ustawien is not None          # okno zostaje otwarte
    czerwone = [w for w in app.okno_ustawien.winfo_children()
                if w.winfo_class() == "Label" and w.cget("fg") == p.BLAD]
    assert czerwone and czerwone[0].cget("text")  # widoczny komunikat bledu


def test_wartosc_powyzej_zakresu_jest_odrzucana(app):
    """Spinbox ogranicza strzalki, ale wpisac z klawiatury mozna cokolwiek."""
    app.pokaz_ustawienia()
    app.root.update()
    pole = pola_liczbowe(app.okno_ustawien)[0]      # woda co ile minut, max 600
    pole.delete(0, "end")
    pole.insert(0, "99999")
    [b for b in przyciski(app.okno_ustawien) if b.cget("text") == "Zapisz"][0].invoke()
    app.root.update()
    assert app.okno_ustawien is not None
    assert p.wczytaj_config()["wodaMinuty"] != 99999


def test_zmiana_samego_dzwieku_nie_zeruje_licznikow(app):
    """29 minut odliczania nie moze przepasc przez przelaczenie dzwieku."""
    app.cfg["wodaMinuty"] = 30
    app.reset_wody()
    app.woda_do -= 1740                              # zostalo 60 s do wody
    przed = app.woda_sek
    app.pokaz_ustawienia()
    app.root.update()
    pole_wyboru = [w for w in app.okno_ustawien.winfo_children()[1].winfo_children()
                   if w.winfo_class() == "Checkbutton"][0]
    pole_wyboru.invoke()                             # przelaczamy sam dzwiek
    [b for b in przyciski(app.okno_ustawien) if b.cget("text") == "Zapisz"][0].invoke()
    app.root.update()
    assert abs(app.woda_sek - przed) <= 2            # licznik nietkniety


def test_zmiana_interwalu_zeruje_wlasciwy_licznik(app):
    app.cfg.update(wodaMinuty=30, przerwaMinuty=60)
    app.reset_wody(); app.reset_przerwy()
    app.przerwa_do -= 3000                           # zostalo 600 s do przerwy
    przerwa_przed = app.przerwa_sek
    app.pokaz_ustawienia()
    app.root.update()
    pole = pola_liczbowe(app.okno_ustawien)[0]
    pole.delete(0, "end"); pole.insert(0, "10")      # zmieniamy tylko wode
    [b for b in przyciski(app.okno_ustawien) if b.cget("text") == "Zapisz"][0].invoke()
    app.root.update()
    assert 595 <= app.woda_sek <= 600                # woda przeliczona od nowa
    assert abs(app.przerwa_sek - przerwa_przed) <= 2  # przerwa nietknieta
