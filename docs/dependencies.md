# Dependencies and code provenance

The library source is a new implementation. The imported applications are behavior references; they have no license files, and their source must not be copied into this package. They remain unchanged Git submodules and must not be included in release archives.

The library uses MIT licensing. Optional dependencies retain their own licenses. Installing a provider extra does not change those dependencies' license terms.

The following package metadata was inspected during implementation:

| Dependency | Checked version | Reported license |
|---|---|---|
| yt-dlp | 2026.8.19 | Unlicense |
| httpx | 0.28.1 | BSD-3-Clause |
| yt-dlp-ejs | 0.8.0 | Unlicense AND MIT AND ISC |
| mutagen, installed by yt-dlp's default extra | 1.48.1 | GPL-2.0-or-later |
| pycryptodomex, installed by yt-dlp's default extra | 3.23.0 | BSD, Public Domain |

FFmpeg, ffprobe and a supported JavaScript runtime are installed separately; they are not bundled in the library wheel. Their licenses depend on the selected distributions/builds. In particular, do not describe every installed dependency or tool as MIT-licensed.

Before publishing a new version, inspect the lockfile and dependency license changes, build the wheel and source archive, and verify that neither includes the imported projects, private credentials, downloaded media or validation responses. GitHub release automation prepares artifacts; publishing and GitHub Pages deployment must be deliberately triggered.
