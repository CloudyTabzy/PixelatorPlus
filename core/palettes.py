"""Built-in retro palettes for the LUT quantization mode.

Palette tables are rebuilt from well-known public definitions rather than the
extracted PixelatorPlus binaries (which are not shipped with this add-on):

  - AMIGA          Deluxe Paint 4 (Amiga) default 32 colors ("dpaint-32c", Lospec)
  - APPLE2_LORES   Apple II lo-res 15 colors (Lospec "Apple II"; the two hardware
                   grays are identical on real hardware, so 15 unique colors)
  - APPLE2_HIRES   Apple II hi-res 6 colors, derived from the documented YIQ
                   values (Wikipedia: Apple II graphics) via the NTSC matrix
  - ATARI2600      Atari 2600 NTSC palette (Lospec "Atari 2600 NTSC"; 127 colors
                   as published — the source omits the final entry of luma row 7)
  - C64            Commodore 64 "Colodore" 16 colors (Pepto's calibrated set)
  - NES            NES 2C02 54 colors (Lospec "Nintendo Entertainment System")
  - GAMEBOY        Game Boy DMG 4 shades (light -> dark)
  - GAMEBOY_COLOR  curated 32-color GBC presentation palette; every color is
                   valid RGB555 hardware color (the GBC has no universal fixed
                   palette)
  - MASTER_SYSTEM  Sega Master System 6-bit RGB cube (64 colors)
  - WEB            Web-safe 216-color cube

Add-on extras beyond the original filter's palette set:

  - ZX_SPECTRUM    ZX Spectrum 15 colors (Lospec "ZX Spectrum"; levels 0/D8/FF
                   per channel, black shared between normal and bright)
  - AMSTRAD_CPC    Amstrad CPC 27-color cube, levels 0/128/255 per channel
  - MSX            TMS9918 15 colors (Lospec "MSX"; transparent color 0 skipped)
  - VIC20          VIC-20 16 colors (Lospec "VIC-20")
  - CGA            CGA 16 colors (EGA default set, incl. brown AA5500)
  - BBC_MICRO      BBC Micro 8 colors (pure 00/FF cube corners)
  - SNES           curated 32-color SNES presentation palette; every color is
                   valid RGB555 hardware color (the SNES selects colors from a
                   32,768-color master space)
  - GENESIS        Sega Genesis/Mega Drive 9-bit color: 3-bit-per-channel
  - APPLE_IIGS     Apple IIGS 12-bit color: 4-bit-per-channel
  - PICO8          PICO-8 16 colors (Lexaloffle, Lospec "PICO-8")
  - TIC80          TIC-80 16 colors; TIC-80 adopted GrafxKid's Sweetie-16, so
                   this is the same color set (TIC-80 source: demos/palette.lua)
  - DB32           DawnBringer 32 (Lospec "dawnbringer-32")
  - RESURRECT64    Resurrect 64 by Kerrie Lake (Lospec "resurrect-64")
  - ENDESGA32      Endesga 32 (Lospec "endesga-32")
  - ENDESGA16      Endesga 16 (Lospec "endesga-16")
  - SWEETIE16      Sweetie 16 by GrafxKid (Lospec "sweetie-16")
  - GRAYSCALE_2/4/8/16  Evenly spaced gray ramps (generated)

`resolve(name)` returns ("palette", float32 (N, 3) in 0..1) for explicit
palettes, or ("reduce", bits_per_channel) for bit-depth reducers.
"""

import numpy as np

_HEX = {
    "AMIGA": [
        "000000", "a0a0a0", "ec0000", "a80000", "dc8800", "fcec00", "88fc00", "008800",
        "00b864", "00dcdc", "00a8fc", "0074cc", "0000fc", "7400fc", "cc00ec", "cc0088",
        "642000", "ec5420", "a85420", "fccca8", "303030", "444444", "545454", "646464",
        "747474", "888888", "989898", "a8a8a8", "cccccc", "dcdcdc", "ececec", "fcfcfc",
    ],
    "APPLE2_LORES": [
        "000000", "515c16", "843d52", "ea7d27", "514888", "e85def", "f5b7c9", "006752",
        "00c82c", "919191", "c9d199", "00a6f0", "98dbc9", "c8c1f7", "ffffff",
    ],
    # Derived from the documented hi-res YIQ values (green 0.5/0/-1, purple 0.5/0/1,
    # orange 0.5/1/0, blue 0.5/-1/0) through the NTSC YIQ->RGB matrix, clamped to gamut.
    "APPLE2_HIRES": [
        "000000", "00ff00", "ff00ff", "ff3a00", "00c5ff", "ffffff",
    ],
    "ATARI2600": [
        "000000", "444400", "702800", "841800", "880000", "78005c", "480078", "140084",
        "000088", "00187c", "002c5c", "00402c", "003c00", "143800", "2c3000", "442800",
        "404040", "646410", "844414", "983418", "9c2020", "8c2074", "602090", "302098",
        "1c209c", "1c3890", "1c4c78", "1c5c48", "205c20", "345c1c", "4c501c", "644818",
        "6c6c6c", "848424", "985c28", "ac5030", "b03c3c", "a03c88", "783ca4", "4c3cac",
        "3840b0", "3854a8", "386890", "387c64", "407c40", "507c38", "687034", "846830",
        "909090", "a0a034", "ac783c", "c06848", "c05858", "b0589c", "8c58b8", "6858c0",
        "505cc0", "5070bc", "5084ac", "509c80", "5c9c5c", "6c9850", "848c4c", "a08444",
        "b0b0b0", "b8b840", "bc8c4c", "d0805c", "d07070", "c070b0", "a070cc", "7c70d0",
        "6874d0", "6888cc", "689cc0", "68b494", "74b474", "84b468", "9ca864", "b89c58",
        "c8c8c8", "d0d050", "cca05c", "e09470", "e08888", "d084c0", "b484dc", "9488e0",
        "7c8ce0", "7c9cdc", "7cb4d4", "7cd0ac", "8cd08c", "9ccc7c", "b4c078", "d0b46c",
        "dcdcdc", "e8e85c", "dcb468", "eca880", "eca0a0", "dc9cd0", "c49cec", "a8a0ec",
        "90a4ec", "90b4ec", "90cce8", "90e4c0", "ececec", "a4e4a4", "b4e490", "ccd488",
        "e8cc7c", "fcfc68", "fcbc94", "fcb4b4", "ecb0e0", "d4b0fc", "bcb4fc", "a4b8fc",
        "a4c8fc", "a4e0fc", "a4fcd4", "b8fcb8", "c8fca4", "e0ec9c", "fce08c",
    ],
    "C64": [
        "000000", "ffffff", "813338", "75cec8", "8e3c97", "56ac4d", "2e2c9b", "edf171",
        "8e5029", "553800", "c46c71", "4a4a4a", "7b7b7b", "a9ff9f", "706deb", "b2b2b2",
    ],
    "NES": [
        "000000", "fcfcfc", "f8f8f8", "bcbcbc", "7c7c7c", "a4e4fc", "3cbcfc", "0078f8",
        "0000fc", "b8b8f8", "6888fc", "0058f8", "0000bc", "d8b8f8", "9878f8", "6844fc",
        "4428bc", "f8b8f8", "f878f8", "d800cc", "940084", "f8a4c0", "f85898", "e40058",
        "a80020", "f0d0b0", "f87858", "f83800", "a81000", "fce0a8", "fca044", "e45c10",
        "881400", "f8d878", "f8b800", "ac7c00", "503000", "d8f878", "b8f818", "00b800",
        "007800", "b8f8b8", "58d854", "00a800", "006800", "b8f8d8", "58f898", "00a844",
        "005800", "00fcfc", "00e8d8", "008888", "004058", "f8d8f8", "787878",
    ],
    "GAMEBOY": [
        "e0f8d0", "88c070", "346856", "081820",
    ],
    # --- Hardware palettes (add-on extras) ----------------------------------
    "ZX_SPECTRUM": [
        "000000", "0000d8", "0000ff", "d80000", "ff0000", "d800d8", "ff00ff", "00d800",
        "00ff00", "00d8d8", "00ffff", "d8d800", "ffff00", "d8d8d8", "ffffff",
    ],
    "MSX": [
        "000000", "cacaca", "ffffff", "b75e51", "d96459", "fe877c", "cac15e", "ddce85",
        "3ca042", "40b64a", "73ce7c", "5955df", "7e75f0", "64daee", "b565b3",
    ],
    "VIC20": [
        "000000", "ffffff", "ff0000", "ffff00", "00ff00", "00ffff", "0000ff", "ff00ff",
        "ff8000", "ffc080", "ff8080", "ffff80", "80ff80", "80ffff", "8080ff", "ff80ff",
    ],
    "CGA": [
        "000000", "0000aa", "00aa00", "00aaaa", "aa0000", "aa00aa", "aa5500", "aaaaaa",
        "555555", "5555ff", "55ff55", "55ffff", "ff5555", "ff55ff", "ffff55", "ffffff",
    ],
    "BBC_MICRO": [
        "000000", "ff0000", "00ff00", "ffff00", "0000ff", "ff00ff", "00ffff", "ffffff",
    ],
    # --- Community/fantasy palettes (add-on extras) -------------------------
    "PICO8": [
        "000000", "1d2b53", "7e2553", "008751", "ab5236", "5f574f", "c2c3c7", "fff1e8",
        "ff004d", "ffa300", "ffec27", "00e436", "29adff", "83769c", "ff77a8", "ffccaa",
    ],
    # TIC-80 adopted GrafxKid's Sweetie-16 as its default palette.
    "TIC80": [
        "1a1c2c", "5d275d", "b13e53", "ef7d57", "ffcd75", "a7f070", "38b764", "257179",
        "29366f", "3b5dc9", "41a6f6", "73eff7", "f4f4f4", "94b0c2", "566c86", "333c57",
    ],
    "DB32": [
        "000000", "222034", "45283c", "663931", "8f563b", "df7126", "d9a066", "eec39a",
        "fbf236", "99e550", "6abe30", "37946e", "4b692f", "524b24", "323c39", "3f3f74",
        "306082", "5b6ee1", "639bff", "5fcde4", "cbdbfc", "ffffff", "9badb7", "847e87",
        "696a6a", "595652", "76428a", "ac3232", "d95763", "d77bba", "8f974a", "8a6f30",
    ],
    "RESURRECT64": [
        "2e222f", "3e3546", "625565", "966c6c", "ab947a", "694f62", "7f708a", "9babb2",
        "c7dcd0", "ffffff", "6e2727", "b33831", "ea4f36", "f57d4a", "ae2334", "e83b3b",
        "fb6b1d", "f79617", "f9c22b", "7a3045", "9e4539", "cd683d", "e6904e", "fbb954",
        "4c3e24", "676633", "a2a947", "d5e04b", "fbff86", "165a4c", "239063", "1ebc73",
        "91db69", "cddf6c", "313638", "374e4a", "547e64", "92a984", "b2ba90", "0b5e65",
        "0b8a8f", "0eaf9b", "30e1b9", "8ff8e2", "323353", "484a77", "4d65b4", "4d9be6",
        "8fd3ff", "45293f", "6b3e75", "905ea9", "a884f3", "eaaded", "753c54", "a24b6f",
        "cf657f", "ed8099", "831c5d", "c32454", "f04f78", "f68181", "fca790", "fdcbb0",
    ],
    "ENDESGA32": [
        "be4a2f", "d77643", "ead4aa", "e4a672", "b86f50", "733e39", "3e2731", "a22633",
        "e43b44", "f77622", "feae34", "fee761", "63c74d", "3e8948", "265c42", "193c3e",
        "124e89", "0099db", "2ce8f5", "ffffff", "c0cbdc", "8b9bb4", "5a6988", "3a4466",
        "262b44", "181425", "ff0044", "68386c", "b55088", "f6757a", "e8b796", "c28569",
    ],
    "ENDESGA16": [
        "e4a672", "b86f50", "743f39", "3f2832", "9e2835", "e53b44", "fb922b", "ffe762",
        "63c64d", "327345", "193d3f", "4f6781", "afbfd2", "ffffff", "2ce8f4", "0484d1",
    ],
    "SWEETIE16": [
        "1a1c2c", "5d275d", "b13e53", "ef7d57", "ffcd75", "a7f070", "38b764", "257179",
        "29366f", "3b5dc9", "41a6f6", "73eff7", "f4f4f4", "94b0c2", "566c86", "333c57",
    ],
}

# Curated presentation palettes for systems whose hardware has a large RGB555
# master space rather than one canonical game-wide palette. Values are stored
# as integer RGB555 triplets (0..31), then converted to exact representable
# display colors below. They are deliberately compact and high-contrast so
# the named modes produce a visible retro look while remaining hardware-valid.
_RGB555 = {
    "GAMEBOY_COLOR": [
        (1, 2, 6), (3, 5, 12), (4, 10, 16), (2, 14, 13),
        (7, 21, 16), (11, 28, 18), (18, 31, 20), (28, 31, 18),
        (31, 27, 10), (31, 19, 5), (30, 10, 4), (23, 4, 5),
        (15, 3, 10), (9, 3, 15), (5, 7, 20), (4, 13, 26),
        (7, 22, 31), (15, 29, 31), (26, 31, 31), (10, 6, 4),
        (17, 8, 4), (25, 13, 6), (31, 18, 12), (31, 12, 21),
        (31, 20, 25), (24, 9, 24), (18, 12, 30), (12, 18, 30),
        (7, 10, 13), (15, 16, 18), (23, 23, 23), (31, 31, 30),
    ],
    "SNES": [
        (1, 1, 4), (4, 4, 12), (7, 7, 18), (11, 10, 25),
        (16, 7, 18), (24, 8, 18), (31, 12, 17), (31, 20, 12),
        (28, 27, 13), (20, 25, 10), (10, 20, 10), (4, 14, 12),
        (4, 19, 24), (5, 12, 25), (10, 9, 22), (15, 14, 27),
        (19, 18, 24), (24, 24, 27), (31, 31, 30), (11, 5, 3),
        (18, 8, 4), (24, 13, 6), (29, 18, 12), (31, 24, 17),
        (30, 27, 21), (13, 8, 7), (19, 12, 8), (24, 18, 11),
        (7, 10, 13), (12, 16, 18), (18, 22, 23), (27, 29, 28),
    ],
}

# Reducer-style builtins: (kind, bits_per_channel). These remain available
# internally for the other bit-depth-oriented hardware modes.
_REDUCERS = {
    # --- Hardware reducers (add-on extras) ----------------------------------
    "GENESIS": 3,
    "APPLE_IIGS": 4,
}

BUILTIN_NAMES = (
    "AMIGA", "APPLE2_LORES", "APPLE2_HIRES", "ATARI2600", "C64", "NES",
    "GAMEBOY", "GAMEBOY_COLOR", "MASTER_SYSTEM", "WEB",
    # Hardware hex palettes
    "ZX_SPECTRUM", "AMSTRAD_CPC", "MSX", "VIC20", "CGA", "BBC_MICRO",
    # Hardware reducers
    "SNES", "GENESIS", "APPLE_IIGS",
    # Community/fantasy palettes
    "PICO8", "TIC80", "DB32", "RESURRECT64", "ENDESGA32", "ENDESGA16", "SWEETIE16",
    # Grayscale ramps
    "GRAYSCALE_2", "GRAYSCALE_4", "GRAYSCALE_8", "GRAYSCALE_16",
)


def _hex_to_float(hex_list):
    rgb = np.array(
        [[int(h[i : i + 2], 16) for i in (0, 2, 4)] for h in hex_list],
        dtype=np.float32,
    )
    return rgb / 255.0


def _rgb555_to_float(values):
    return (np.asarray(values, dtype=np.float32) / 31.0).astype(np.float32)


def _cube(levels):
    g = np.meshgrid(levels, levels, levels, indexing="ij")
    return (np.stack([g[0].ravel(), g[1].ravel(), g[2].ravel()], axis=-1) / 255.0).astype(np.float32)


def resolve(name):
    """-> ("palette", float32 (N,3)) or ("reduce", bits). Raises KeyError if unknown."""
    name = name.upper()
    if name in _HEX:
        return "palette", _hex_to_float(_HEX[name])
    if name in _RGB555:
        return "palette", _rgb555_to_float(_RGB555[name])
    if name in _REDUCERS:
        return "reduce", _REDUCERS[name]
    if name == "MASTER_SYSTEM":
        return "palette", _cube([0, 85, 170, 255])
    if name == "WEB":
        return "palette", _cube([0, 51, 102, 153, 204, 255])
    if name == "AMSTRAD_CPC":
        return "palette", _cube([0, 128, 255])
    if name.startswith("GRAYSCALE_"):
        n = int(name.split("_")[1])
        v = (np.linspace(0.0, 255.0, n) / 255.0).astype(np.float32)
        return "palette", np.repeat(v[:, None], 3, axis=1)
    raise KeyError(f"unknown builtin palette: {name}")
