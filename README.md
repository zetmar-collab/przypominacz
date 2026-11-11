# Przypominacz

Mała aplikacja w zasobniku systemowym (tray), która przypomina o piciu wody
i o 5-minutowej przerwie od komputera.

[![Sklep Windows](https://img.shields.io/badge/Sklep_Windows-pobierz-0078D4?style=for-the-badge&logo=microsoftstore&logoColor=white)](https://apps.microsoft.com/detail/9NWV99ZZVJ4Z)
[![Licencja MIT](https://img.shields.io/badge/licencja-MIT-green?style=for-the-badge)](LICENSE)

## Co potrafi

- **Woda** — co 30 min (domyślnie) powiadomienie Windows + dźwięk.
- **Przerwa** — co 60 min (domyślnie) okno na wierzchu z odliczaniem 5 minut,
  z przyciskami „Odłóż o 5 min" i „Zamknij".
- **Menu w trayu** (prawy klik na ikonę kropli):
  - podgląd czasu do najbliższego przypomnienia,
  - „Przypomnij o wodzie teraz" / „Zrób przerwę teraz",
  - Pauza (ikona szarzeje),
  - **Ustawienia…** — okienko z polami (bez grzebania w pliku),
  - „Uruchamiaj z Windows" (przełącznik autostartu),
  - Zakończ.
- **Nie przeszkadza, gdy nie powinien:**
  - odejście od komputera wstrzymuje liczniki, a dłuższa nieobecność liczy się
    jako przerwa — po powrocie nie wita Cię alarm;
  - prezentacja, gra i pełny ekran odraczają przypomnienie zamiast je wycinać;
  - cicha pora wycisza wszystko w wybranych godzinach.
- Jedna instancja na sesję użytkownika.

## Instalacja

**Zalecane — Sklep Windows:**
[apps.microsoft.com/detail/9NWV99ZZVJ4Z](https://apps.microsoft.com/detail/9NWV99ZZVJ4Z)
Instalacja jednym kliknięciem, automatyczne aktualizacje, podpis Microsoftu
(bez ostrzeżenia SmartScreen). Autostart w wersji ze Sklepu włączony jest
domyślnie — wyłączysz go w *Ustawienia → Aplikacje → Uruchamianie*, a menu
trayu prowadzi wprost do tego ekranu.

**Alternatywnie — pojedynczy plik:** pobierz `Przypominacz.exe` z zakładki
[Releases](https://github.com/zetmar-collab/przypominacz/releases). Nie wymaga
Pythona ani instalatora — dwuklik i ikona ląduje w trayu. Ta wersja nie jest
podpisana certyfikatem, więc przy pierwszym uruchomieniu Windows SmartScreen
może ostrzec („Więcej informacji" → „Uruchom mimo to").

W wersji z pliku exe autostart włączasz w menu trayu (**Uruchamiaj z Windows**) —
dodaje wpis do `HKCU\...\CurrentVersion\Run` i potwierdza to powiadomieniem.
Exe można trzymać gdziekolwiek, także w katalogu tylko do odczytu; po
przeniesieniu pliku program sam naprawia wpis autostartu przy najbliższym
uruchomieniu.

Nie trzeba (i nie warto) wrzucać niczego do folderu Autostart ręcznie —
jeśli tam wcześniej trafił skrót, włączenie autostartu z menu go usuwa, żeby
program nie startował dwa razy. **Nie kopiuj tam `config.json`** — Windows
„uruchamia" wszystko z tego folderu, więc plik ustawień otworzy się przy
każdym logowaniu w Notatniku.

## Ustawienia

Prawy klik na ikonę → **Ustawienia…** Okienko ma pola na wszystkie opcje,
przycisk **Zapisz** od razu je stosuje, **Anuluj** porzuca zmiany. Zmiana
interwału zeruje tylko ten jeden licznik — przełączenie dźwięku nie kasuje
rozpoczętego odliczania.

Ustawienia i log obu wersji leżą w **`%LOCALAPPDATA%\Przypominacz\`**
(`config.json`, `przypominacz.log`). Ustawienia z wersji sprzed 1.2, które
leżały obok pliku exe, przenoszą się tam same przy pierwszym uruchomieniu.

| Klucz | Znaczenie | Domyślnie |
|---|---|---|
| `wodaMinuty` | co ile minut przypomnienie o wodzie | 30 |
| `przerwaMinuty` | co ile minut przerwa | 60 |
| `przerwaDlugoscMinut` | długość przerwy | 5 |
| `drzemkaMinuty` | o ile odkłada przycisk „Odłóż" | 5 |
| `dzwiek` | dźwięk przy powiadomieniach | true |
| `cichaPoraWlaczona` | wyciszenie w godzinach nocnych | false |
| `cichaPoraOd` / `cichaPoraDo` | zakres cichej pory (godziny) | 22 / 7 |
| `bezczynnoscWlaczona` | wstrzymaj liczniki, gdy nie ma Cię przy komputerze | true |
| `bezczynnoscMinuty` | po ilu minutach bez myszy i klawiatury uznać nieobecność | 5 |
| `szanujPelnyEkran` | odraczaj przypomnienia w prezentacji i pełnym ekranie | true |

Wartości spoza dozwolonego zakresu są przycinane przy wczytywaniu, a uszkodzony
plik odkładany jako `config.json.uszkodzony` — program startuje na domyślnych
zamiast nie wstać wcale.

Plik można też edytować ręcznie, ale wtedy zmiany wejdą dopiero po restarcie
aplikacji — okienko jest wygodniejsze.

## Diagnostyka

Gdy coś nie działa, zajrzyj do `%LOCALAPPDATA%\Przypominacz\przypominacz.log`.
Zapisują się tam start programu z numerem wersji, nieudane zapisy ustawień,
uszkodzony plik konfiguracji, wykryte wybudzenie komputera oraz każdy
nieobsłużony wyjątek.

## Wersja MSIX (Sklep Windows)

```powershell
.\Zbuduj-msix.ps1            # -> Przypominacz.msix (niepodpisany, do Partner Center)
.\Zbuduj-msix.ps1 -Podpisz   # + podpis certyfikatem testowym do instalacji lokalnej
```

Do Partner Center wysyłasz **pakiet niepodpisany** — Sklep podpisuje go sam
kluczem wydawcy. Dane tożsamości siedzą w [AppxManifest.xml](AppxManifest.xml)
(`Identity/Name`, `Identity/Publisher`, `PublisherDisplayName`); przy każdej
kolejnej wysyłce podnieś `Identity/Version` (czwarty człon zostaw jako `0`).

W pakiecie aplikacja zachowuje się inaczej w dwóch miejscach, bo tego wymaga
model MSIX:

- **ustawienia** trafiają do `%LOCALAPPDATA%\Przypominacz\config.json` —
  katalog instalacji pakietu jest tylko do odczytu,
- **autostart** to `windows.startupTask` z manifestu (włączony domyślnie),
  a nie wpis w rejestrze — użytkownik steruje nim w *Ustawienia → Aplikacje →
  Uruchamianie*. Menu trayu pokazuje wtedy skrót do tego ekranu zamiast
  własnego przełącznika.

Logotypy pakietu generuje [Zrob-assety.py](Zrob-assety.py) z tej samej kropli,
co ikona w trayu — folder `Assets` nie jest trzymany w repo.

## Testy

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

53 testy pokrywają wczytywanie i zapis ustawień (w tym katalog bez prawa
zapisu i uszkodzony JSON), odliczanie wobec zegara, wybudzenie komputera,
pauzę, cichą porę, autostart w rejestrze oraz oba okna.

## Budowanie ze źródeł

Wymagany Python 3.10+ na Windows (testowane na 3.13 z python.org).

```powershell
git clone https://github.com/zetmar-collab/przypominacz.git
cd przypominacz
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Zbuduj-exe.ps1
```

Gotowy `Przypominacz.exe` ląduje w katalogu projektu. Można też odpalić bez
budowania: `.\.venv\Scripts\pythonw.exe przypominacz.py`.

Techniczne szczegóły:

- czysty Python + `tkinter` (okna), `pystray` (tray), `Pillow` (ikona),
  `winsound`, `winreg` i `ctypes` ze standardowej biblioteki — tylko Windows,
- odliczanie do terminu wg zegara, więc uśpienie komputera nie gubi czasu,
- jedna instancja pilnowana mutexem w przestrzeni `Local` (per sesja),
- numer wersji pochodzi z `__version__` i trafia do zasobów exe oraz manifestu,
- autostart: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → `Przypominacz`.

## Licencja

MIT — patrz [LICENSE](LICENSE).
