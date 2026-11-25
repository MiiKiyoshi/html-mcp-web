"""The fonts the browser tests were written with, given to a Windows or macOS runner of the CI.

The tests measure pages set in the browser's generic families: Noto Serif for serif, Noto Sans
for sans-serif and DejaVu Sans Mono for monospace. Every Chrome a test starts, its own and each
one the package starts for it, names them in its profile (pin_fonts), on every system. On Linux
the workflow installs them as Ubuntu's packages. Here the same fonts are taken from Debian's
packages of the same versions and installed for this user alone, which needs no administrator:
on macOS in ~/Library/Fonts, on Windows in the user's own font folder, registered under the
user's key. Run by the CI as python -m tests.fonts."""

import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

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
# Chrome's settings of the generic families, for every script: the standard face, which a page
# that names none is set in, is the serif one.
FONTS = {"standard": FAMILIES["serif"], "serif": FAMILIES["serif"],
         "sansserif": FAMILIES["sans-serif"], "fixed": FAMILIES["monospace"]}


def pin_fonts(folder: str) -> None:
    """Name the generic families in a new Chrome profile's preferences, which it reads as it
    starts."""
    fonts = {generic: {"Zyyy": family} for generic, family in FONTS.items()}
    Path(folder, "Default").mkdir(exist_ok=True)
    Path(folder, "Default", "Preferences").write_text(json.dumps({"webkit": {"webprefs": {"fonts": fonts}}}),
                                                       encoding="utf-8")


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

    target = Path(os.environ["LOCALAPPDATA"], "Microsoft", "Windows", "Fonts", name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    # A font of one user's is registered with its full path, under that user's key.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                            0, winreg.KEY_SET_VALUE) as fonts:
        winreg.SetValueEx(fonts, f"{Path(name).stem} (TrueType)", 0, winreg.REG_SZ, str(target))
    ctypes.windll.gdi32.AddFontResourceW(str(target))


if __name__ == "__main__":
    if sys.platform not in ("darwin", "win32"):
        sys.exit("run on a Windows or macOS runner")
    for url, (digest, folder, names) in PACKAGES.items():
        for name, data in unpack(url, digest, folder, names).items():
            install(name, data)
    if sys.platform == "win32":
        import ctypes

        # Programs started from now on see the new fonts.
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)
    print("Fonts installed for this user: " + ", ".join(f"{generic} {family}" for generic, family in FAMILIES.items()))
