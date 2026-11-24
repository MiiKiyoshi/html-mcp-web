"""The fonts the browser tests were written with, given to a Windows or macOS runner of the CI.

The tests measure pages set in the browser's generic families, and Ubuntu 24.04 sets them, once
its packages are installed, in Noto Serif for serif, Noto Sans for sans-serif and DejaVu Sans
Mono for monospace. On Linux the workflow installs those packages. Here the same fonts are taken
from Debian's packages of the same versions, installed for the system, and named in Firefox's
defaults, which every profile it starts reads: the tests' own and the server's checks and
prints. Run by the CI as python -m tests.fonts."""

import hashlib
import io
import os
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

from tests.firefox import FIREFOX

# Each package, its digest, and the files it holds of each family's four faces.
PACKAGES = {
    "https://deb.debian.org/debian/pool/main/f/fonts-noto/fonts-noto-core_20201225-1_all.deb":
        ("58f4f0bb6720f919f92096b3508e1412a0f1544424ade6c5b5bf1eb694dd64ba", "usr/share/fonts/truetype/noto/",
         [f"{family}-{face}.ttf" for family in ("NotoSerif", "NotoSans")
          for face in ("Regular", "Bold", "Italic", "BoldItalic")]),
    "https://deb.debian.org/debian/pool/main/f/fonts-dejavu/fonts-dejavu-mono_2.37-8_all.deb":
        ("3003e98a5debfdeadc7040a7f715fe9fe6fb67f68deacf6049b54e30f07fc014", "usr/share/fonts/truetype/dejavu/",
         [f"DejaVuSansMono{face}.ttf" for face in ("", "-Bold", "-Oblique", "-BoldOblique")]),
}
FAMILIES = {"serif": "Noto Serif", "sans-serif": "Noto Sans", "monospace": "DejaVu Sans Mono"}


def unpack(url: str, digest: str, folder: str, names: list[str]) -> dict[str, bytes]:
    """The named files of a Debian package: an ar archive whose data.tar.xz holds them."""
    with urllib.request.urlopen(url, timeout=120) as response:
        package = response.read()
    if hashlib.sha256(package).hexdigest() != digest:
        sys.exit(f"{url} is not the package it was: its digest changed")
    at = 8  # past "!<arch>\n"
    while at < len(package):
        name, size = package[at:at + 16].decode().strip(), int(package[at + 48:at + 58])
        if name.rstrip("/") == "data.tar.xz":
            with tarfile.open(fileobj=io.BytesIO(package[at + 60:at + 60 + size]), mode="r:xz") as data:
                return {name: data.extractfile(f"./{folder}{name}").read() for name in names}
        at += 60 + size + size % 2
    sys.exit(f"{url} holds no data.tar.xz")


def install(name: str, data: bytes) -> None:
    if sys.platform == "darwin":
        target = Path.home() / "Library" / "Fonts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return
    import ctypes
    import winreg

    target = Path(os.environ["WINDIR"], "Fonts", name)
    target.write_bytes(data)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                        0, winreg.KEY_SET_VALUE) as fonts:
        winreg.SetValueEx(fonts, f"{Path(name).stem} (TrueType)", 0, winreg.REG_SZ, name)
    ctypes.windll.gdi32.AddFontResourceW(str(target))


def firefox_defaults() -> Path:
    """The folder of default preferences Firefox reads at every start, beside its program, or
    in a Mac application's Resources. Homebrew's firefox on the PATH is a script that runs the
    application's program, which it names."""
    program = Path(FIREFOX).resolve()
    if sys.platform == "darwin" and program.parent.name != "MacOS":
        script = program.read_text(encoding="utf-8")
        named = re.search(r"(/[^'\"\s]*?\.app)/Contents/MacOS/firefox", script)
        if named is None:
            sys.exit(f"{program} names no Firefox application:\n{script[:1000]}")
        program = Path(named.group(1), "Contents", "MacOS", "firefox")
    resources = program.parent.parent / "Resources" if program.parent.name == "MacOS" else program.parent
    return resources / "defaults" / "pref"


if __name__ == "__main__":
    if FIREFOX is None or sys.platform not in ("darwin", "win32"):
        sys.exit("run on a Windows or macOS runner that has Firefox")
    for url, (digest, folder, names) in PACKAGES.items():
        for name, data in unpack(url, digest, folder, names).items():
            install(name, data)
    if sys.platform == "win32":
        import ctypes

        # Programs started from now on see the new fonts.
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)
    defaults = firefox_defaults()
    defaults.mkdir(parents=True, exist_ok=True)
    (defaults / "test-fonts.js").write_text("".join(
        f'pref("font.name.{generic}.{group}", "{family}");\n'
        for generic, family in FAMILIES.items() for group in ("x-western", "x-unicode")), encoding="utf-8")
    print(f"Fonts installed and named in {defaults / 'test-fonts.js'}: "
          + ", ".join(f"{generic} {family}" for generic, family in FAMILIES.items()))
