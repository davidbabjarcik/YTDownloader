# YT Downloader

Desktopová aplikácia pre **Windows, macOS a Linux** (Python + PySide6 + yt-dlp + FFmpeg) na sťahovanie hudby a videa
z **YouTube, SoundCloudu a Spotify**, jednotlivé skladby aj celé playlisty a albumy.
**Najvyššia dostupná kvalita → konverzia → názov súboru → tagy → vložený cover → hotový MP3/M4A/FLAC/MP4.**

> Používaj len na obsah, ktorý smieš sťahovať (vlastný, licencovaný, Creative Commons…). Sťahovanie
> chráneného obsahu môže porušovať podmienky služieb alebo autorské právo vo tvojej krajine.

## Stiahnutie hotovej appky

Každý push do `main` spustí GitHub Actions (záložka **Actions** → posledný beh → **Artifacts**):

| Systém | Súbor | Spustenie |
| --- | --- | --- |
| Windows 10/11 x64 | `YTDownloader-<verzia>-windows-x64.zip` | rozbaľ, spusti `YTDownloader.exe` (priečinok `bin` nechaj vedľa neho). SmartScreen: *Ďalšie informácie → Spustiť aj tak* |
| macOS (Apple Silicon) | `YTDownloader-<verzia>-macos-arm64.zip` | rozbaľ, presuň `YTDownloader.app` do Aplikácií. Prvé spustenie: pravý klik → **Otvoriť** |
| Linux x64 | `YTDownloader-<verzia>-linux-x64.tar.gz` | `tar xzf …` a spusti `YTDownloader/YTDownloader` |

Tag `v*` (napr. `git tag v1.1.0 && git push --tags`) navyše vytvorí **GitHub Release** so všetkými tromi súbormi.

Na Macu a Linuxe si appka pri prvom štarte sama stiahne yt-dlp a FFmpeg (asi 100 MB, raz) do
`~/Library/Application Support/YTDownloader/bin` (Mac) alebo `~/.config/YTDownloader/bin` (Linux).
Ak ich už máš z Homebrew (`brew install yt-dlp ffmpeg`) alebo z balíčkov, použije tie.

> macOS appka nie je podpísaná u Apple. Ak ju macOS blokuje („poškodená“ / „neznámy vývojár“):
> `xattr -dr com.apple.quarantine /Applications/YTDownloader.app`

## Vývoj

```
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Testy (potrebujú `ffmpeg` v PATH; GUI test beží bez okna):
```
python tests/test_naming.py
python tests/test_pipeline.py
python tests/test_sources.py
QT_QPA_PLATFORM=offscreen python tests/test_gui.py      # Windows: set QT_QPA_PLATFORM=offscreen
```

Vlastný build: Windows `build.bat`, macOS/Linux `./build.sh` (oba volajú `build.py`, výsledok je v `dist/`).

## Použitie
1. Vlož odkaz (aj viac naraz, každý na nový riadok; funguje drag & drop a detekcia schránky) → **ANALYZE**.
   - YouTube: video alebo playlist (`&list=` sa berie ako playlist)
   - SoundCloud: skladba alebo set/playlist (`soundcloud.com/…`, `on.soundcloud.com/…`)
   - Spotify: skladba, album alebo playlist (`open.spotify.com/…`)
2. Playlist: zobrazí sa zoznam s checkboxmi (Select all / vybrané). Už stiahnuté sú označené **✓ downloaded** a nezaškrtnuté.
3. Vyber Audio/Video → Format → Quality → Filename → Output folder → **DOWNLOAD**. Video ide len pri YouTube.
4. Pred štartom sa opýta na naming pattern (vypnuteľné v Settings). Priebeh je vo fronte (Queue), s Cancel/Retry.
5. Po dokončení: **Download completed** + **Open folder**.

### Naming template
Premenné `{title} {artist} {album} {year} {genre} {track} {id}`, napr. `{artist} - {title} ({year})` alebo pre albumy `{track}. {title}`.
Nepovolené znaky `\ / : * ? " < > |` sa nahradia/odstránia (aj na Macu/Linuxe, aby sa súbory dali skopírovať na Windows / USB),
prázdne časti (chýbajúci rok/interpret) sa zahodia.

## Spotify
Zvuk zo Spotify je chránený (DRM), takže sa zo Spotify nesťahuje. Appka zo Spotify prečíta zoznam skladieb, názvy,
interpretov, album, rok a cover, potom nájde rovnakú skladbu na **YouTube Music** (záloha: bežný YouTube) a stiahne
tú. Zhoda sa kontroluje podľa dĺžky skladby (±8 %) a názvu; live/cover/remix/sped up verzie majú nižšiu prioritu.
Tagy a cover v hotovom súbore sú zo Spotify.

- **Bez prihlásenia** (predvolené): skladby, albumy a playlisty, ale playlist ukáže **max. 100 skladieb**.
- **Celé playlisty**: na [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) si vytvor
  bezplatnú appku a jej *Client ID* + *Client Secret* vlož do Settings → Spotify. Uložia sa len lokálne v `settings.json`.

## História stiahnutých
Každý úspešne stiahnutý súbor sa zapíše do `history.jsonl` (zvlášť audio a video). Pri ďalšom analyzovaní playlistu sú
už stiahnuté skladby označené a nezaškrtnuté, takže sa stiahnu len nové. Dajú sa zaškrtnúť ručne. Pri jednej skladbe sa
appka opýta, či ju chceš stiahnuť znova. Settings → Downloads: vypnutie a **Clear history** (súbory na disku ostanú).

## Tagy, žáner a triedenie do priečinkov
- Do **každého tagu** (MP3/M4A/FLAC/MP4) sa zapíše komentár `www DaveeB YT Downloader` (Settings → Organization & tags: text sa dá zmeniť alebo vypnúť).
- **Žáner** sa určí automaticky: 1) údaj zo zdroja (YouTube, SoundCloud), 2) MusicBrainz (voliteľné, posiela sa interpret + názov skladby), 3) kľúčové slová v tagoch/názve, 4) inak priečinok `Unsorted` (názov sa dá zmeniť). Do tagu sa zapisuje len ak zapneš *Also write the genre into the tag*.
- **Triedenie** je variabilné: v hlavnom okne *Sort into folders* (No folders, Genre, Genre / Artist, Artist, Artist / Album, Year, Genre / Year alebo vlastná šablóna, napr. `{genre}/{year}/{artist}`). Predvolená hodnota je v Settings. Premenné: `{genre} {artist} {album} {year}`, `/` vytvára vnorené priečinky.
- Albumy (Spotify, SoundCloud sety) dostanú aj **číslo skladby** a názov albumu.

## Architektúra
```
main.py                 vstupný bod, téma, globálny handler chýb
build.py                build pre aktuálny systém (PyInstaller); build.bat / build.sh ho volajú
app/
  settings.py paths.py models.py     konfigurácia, cesty (podľa OS), dátové typy
  sources.py                         rozpoznanie odkazov YouTube / SoundCloud / Spotify
  spotify.py                         Spotify: zoznam skladieb + tagy, hľadanie zhody na YouTube
  archive.py                         história stiahnutých (history.jsonl)
  naming.py errors.py                šablóny názvov, preklad chýb yt-dlp/ffmpeg
  deps.py                            hľadanie / sťahovanie yt-dlp a FFmpeg (Windows, macOS, Linux)
  ytdlp.py                           wrapper nad yt-dlp (analýza, hľadanie, príkaz, progress)
  thumbnails.py tagger.py            cover (JPEG, orez na štvorec), ID3/MP4/FLAC tagy (mutagen)
  pipeline.py                        jeden job: (nájdi) → stiahni → konvertuj → tagy → premenuj (bez Qt)
  jobs.py                            fronta, paralelizmus, cancel/retry, zápis do histórie (Qt)
  ui/                                hlavné okno, queue, settings, dialógy, téma
.github/workflows/build.yml          testy + buildy pre 3 systémy + release
```
Core (bez Qt) je oddelený od GUI, takže ho možno testovať a neskôr použiť aj inde (napr. webové rozhranie).

## Prečo takto
- **Python + PySide6**: yt-dlp, mutagen a Pillow sú natívne v Pythone; PySide6 dáva moderné GUI na všetkých troch systémoch. Electron/Tauri by znamenali pridať Node/Rust a stále spúšťať yt-dlp ako proces.
- **yt-dlp ako samostatný program** (nie knižnica): dá sa aktualizovať (Settings → *Update yt-dlp*) bez nového buildu – YouTube sa mení často; cancel = zabitie procesu (aj s ffmpeg).
- **Windows: `.exe` + priečinok `bin`** namiesto jedného 200 MB `--onefile`: rýchly štart a aktualizovateľný yt-dlp. **Mac/Linux**: nástroje sa stiahnu pri prvom štarte do používateľského priečinka (do podpísaného `.app` sa nezapisuje).
- **Spotify bez kľúčov**: verejná stránka Spotify (embed) nepotrebuje účet; vlastné API kľúče sú len voliteľné rozšírenie.
- **Tagy vlastným kódom (mutagen)**: spoľahlivý ID3v2.3 + APIC cover (Windows ho zobrazí), rovnaká cesta pre MP3/M4A/FLAC.
- **Kvalita**: audio sa berie z najlepšieho streamu (`bestaudio`); MP3 sa kóduje max. 320 kbps. Nižší zdroj sa nepredstiera ako lepší – po Analyze sa zobrazí reálny zdroj a voliteľne *Never encode MP3 above source quality*. M4A berie natívny AAC stream bez re-encode; FLAC je len bezstratový kontajner (zdroj je stratový).

## Riešenie problémov
- *Age restricted / Private / „not a bot“*: Settings → Advanced → Custom arguments: `--cookies-from-browser firefox`.
- *FFmpeg not found*: Settings → Check / install components.
- *Spotify: „Not found on YouTube“*: skladba na YouTube nie je, alebo sa dĺžka líši o viac ako 8 % (napr. iná verzia).
- Logy a nastavenia: Windows `%APPDATA%\YTDownloader\`, macOS `~/Library/Application Support/YTDownloader/`,
  Linux `~/.config/YTDownloader/` (`app.log`, `settings.json`, `history.jsonl`).
