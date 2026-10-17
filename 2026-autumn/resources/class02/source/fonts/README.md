# MiSans setup for optional generation

The figures and activity PDF use MiSans by Xiaomi. The supplied PNG/PDF/SVG outputs can be read without installing the font. Font software is obtained separately from [Xiaomi's MiSans download and licence page](https://hyperos.mi.com/font/en/download/); font binaries are not redistributed in this repository.

To regenerate figures or the activity PDF, obtain MiSans under its accompanying terms and place the unmodified static faces here as `MiSans-Regular.ttf` and `MiSans-Semibold.ttf`. These local dependency files are ignored by Git. The scripts register these exact files and reject substitution. Installing the same faces in the operating system also supplies MiSans to the optional HTML explorers.

Reference files used for the reviewed outputs:

| Face | SHA-256 |
|---|---|
| Regular | 9c120f0a849bc0aa5048daae2a3c0f6eecd828b5b33fce682a9622833f5feea6 |
| Semibold | 77c23f31ae124867778344970155a0c8d34a89897dedaab81aeee82ff00a4ce6 |

Check the locally obtained version if reproducing exact output bytes; a different official release can change text metrics. The numerical inputs and conversions are independent of font installation.
