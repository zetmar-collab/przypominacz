# -*- coding: utf-8 -*-
"""Generuje zasob wersji dla PyInstallera z __version__ w przypominacz.py.

Dzieki temu wlasciwosci pliku exe pokazuja numer wersji i jest on zgodny
z wersja w manifescie MSIX - bez przepisywania go recznie w trzech miejscach.
"""

import os
import re
import sys

KATALOG = os.path.dirname(os.path.abspath(__file__))


def wersja_z_kodu():
    tekst = open(os.path.join(KATALOG, "przypominacz.py"), encoding="utf-8").read()
    dopasowanie = re.search(r'__version__\s*=\s*"([\d.]+)"', tekst)
    if not dopasowanie:
        sys.exit("nie znalazlem __version__ w przypominacz.py")
    return dopasowanie.group(1)


SZABLON = '''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({a}, {b}, {c}, 0),
    prodvers=({a}, {b}, {c}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "041504b0",
        [StringStruct("CompanyName", "Marek Zettel"),
         StringStruct("FileDescription", "Przypominacz - woda i przerwy od komputera"),
         StringStruct("FileVersion", "{w}"),
         StringStruct("InternalName", "Przypominacz"),
         StringStruct("LegalCopyright", "(c) 2026 Marek Zettel. Licencja MIT."),
         StringStruct("OriginalFilename", "Przypominacz.exe"),
         StringStruct("ProductName", "Przypominacz"),
         StringStruct("ProductVersion", "{w}")])
    ]),
    VarFileInfo([VarStruct("Translation", [1045, 1200])])
  ]
)
'''


def main():
    wersja = wersja_z_kodu()
    a, b, c = (wersja.split(".") + ["0", "0"])[:3]
    os.makedirs(os.path.join(KATALOG, "build"), exist_ok=True)
    sciezka = os.path.join(KATALOG, "build", "wersja.txt")
    with open(sciezka, "w", encoding="utf-8") as f:
        f.write(SZABLON.format(a=a, b=b, c=c, w=wersja))
    print(f"wersja {wersja} -> {sciezka}")
    return wersja


if __name__ == "__main__":
    main()
