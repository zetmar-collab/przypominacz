# Przypominacz

Mała aplikacja w zasobniku systemowym (tray), która przypomina o piciu wody
i o 5-minutowej przerwie od komputera.

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
- Jedna instancja naraz, cicha pora (opcjonalnie).

## Instalacja

Pobierz **`Przypominacz.exe`** z zakładki
[Releases](https://github.com/zetmar-collab/przypominacz/releases) — to
pojedynczy plik, nie wymaga Pythona ani instalatora. Dwuklik i ikona ląduje
w trayu.

Autostart włączasz w menu trayu (**Uruchamiaj z Windows**) — dodaje wpis do
`HKCU\...\CurrentVersion\Run` i potwierdza to powiadomieniem. Exe można trzymać
gdziekolwiek (`config.json` tworzy się obok niego); po przeniesieniu pliku
program sam naprawia wpis autostartu przy najbliższym uruchomieniu.

Nie trzeba (i nie warto) wrzucać niczego do folderu Autostart ręcznie —
jeśli tam wcześniej trafił skrót, włączenie autostartu z menu go usuwa, żeby
program nie startował dwa razy. **Nie kopiuj tam `config.json`** — Windows
„uruchamia" wszystko z tego folderu, więc plik ustawień otworzy się przy
każdym logowaniu w Notatniku.

> Windows SmartScreen może ostrzec przy pierwszym uruchomieniu — exe nie jest
> podpisany certyfikatem. „Więcej informacji" → „Uruchom mimo to".

## Ustawienia

Prawy klik na ikonę → **Ustawienia…** Okienko ma pola na wszystkie opcje,
przycisk **Zapisz** od razu je stosuje (liczniki startują od nowa), **Anuluj**
porzuca zmiany. Wartości lądują w `config.json` obok exe:

| Klucz | Znaczenie | Domyślnie |
|---|---|---|
| `wodaMinuty` | co ile minut przypomnienie o wodzie | 30 |
| `przerwaMinuty` | co ile minut przerwa | 60 |
| `przerwaDlugoscMinut` | długość przerwy | 5 |
| `drzemkaMinuty` | o ile odkłada przycisk „Odłóż" | 5 |
| `dzwiek` | dźwięk przy powiadomieniach | true |
| `cichaPoraWlaczona` | wyciszenie w godzinach nocnych | false |
| `cichaPoraOd` / `cichaPoraDo` | zakres cichej pory (godziny) | 22 / 7 |

Plik można też edytować ręcznie, ale wtedy zmiany wejdą dopiero po restarcie
aplikacji — okienko jest wygodniejsze.

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
  `winsound` i `winreg` ze standardowej biblioteki — tylko Windows,
- jedna instancja pilnowana nazwanym mutexem,
- autostart: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → `Przypominacz`.

## Licencja

MIT — patrz [LICENSE](LICENSE).
