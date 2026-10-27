# YT Downloader

Moderná Windows 10/11 aplikácia (Python + PySide6 + yt-dlp + FFmpeg) na sťahovanie YouTube audia/videa.
**Najvyššia dostupná kvalita → konverzia → názov súboru → ID3 metadata → vložený cover → hotový MP3/M4A/FLAC/MP4.**

> Používaj len na obsah, ktorý smieš sťahovať (vlastný, licencovaný, Creative Commons…). Sťahovanie
> chráneného obsahu môže porušovať podmienky YouTube alebo autorské právo vo tvojej krajine.

## Rýchly štart

### Hotový .exe
1. Spusti `build.bat` (potrebuješ Python 3.10+ v PATH). Vytvorí `dist\YTDownloader.exe` + `dist\bin\` + `dist\YTDownloader-portable.zip`.
2. Priečinok `bin` nechaj vedľa `.exe` (yt-dlp, ffmpeg, ffprobe). Ak chýba, aplikácia sa pri štarte ponúkne, že ho stiahne sama.

### Vývoj
```
py -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Testy: `python tests\test_naming.py`, `python tests\test_pipeline.py` (potrebuje ffmpeg v PATH),
`set QT_QPA_PLATFORM=offscreen && python tests\test_gui.py`.

## Použitie
1. Vlož URL (aj viac naraz, každá na nový riadok; funguje drag & drop a detekcia schránky) → **ANALYZE**.
2. Playlist: zobrazí sa zoznam s checkboxmi (Select all / vybrané).
3. Vyber Audio/Video → Format → Quality → Filename → Output folder → **DOWNLOAD**.
4. Pred štartom sa opýta na naming pattern (vypnuteľné v Settings). Priebeh je vo fronte (Queue), s Cancel/Retry.
5. Po dokončení: **Download completed** + **Open folder**.

### Naming template
Premenné `{title} {artist} {album} {year} {genre} {id}`, napr. `{artist} - {title} ({year})`.
Nepovolené znaky `\ / : * ? " < > |` sa nahradia/odstránia, prázdne časti (chýbajúci rok/interpret) sa zahodia.

## Architektúra
```
main.py                 vstupný bod, téma, globálny handler chýb
app/
  settings.py paths.py models.py     konfigurácia, cesty, dátové typy
  naming.py errors.py                šablóny názvov, preklad chýb yt-dlp/ffmpeg
  deps.py                            hľadanie / sťahovanie yt-dlp a FFmpeg
  ytdlp.py                           wrapper nad yt-dlp.exe (analýza, príkaz, progress)
  thumbnails.py tagger.py            cover (JPEG, orez na štvorec), ID3/MP4/FLAC tagy (mutagen)
  pipeline.py                        jeden job: stiahni → konvertuj → tagy → premenuj (bez Qt)
  jobs.py                            fronta, paralelizmus, cancel/retry (Qt)
  ui/                                hlavné okno, queue, settings, dialógy, téma
```
Core (bez Qt) je oddelený od GUI, takže ho možno testovať a neskôr nahradiť/rozšíriť (napr. iný zdroj ako YouTube).

## Prečo takto
- **Python + PySide6**: yt-dlp, mutagen a Pillow sú natívne v Pythone; PySide6 dáva moderné GUI, QSS dark/light tému a vlákna. Electron/Tauri by znamenali pridať Node/Rust a stále spúšťať yt-dlp ako proces.
- **yt-dlp.exe ako samostatný proces** (nie knižnica): dá sa aktualizovať (Settings → *Update yt-dlp*) bez nového buildu – YouTube sa mení často; cancel = zabitie procesu.
- **`.exe` + priečinok `bin`** namiesto jedného 200 MB `--onefile`: onefile by pri každom štarte rozbaľoval FFmpeg (pomalý štart) a yt-dlp by sa nedal aktualizovať. Je to stále portable (zip, bez inštalácie, bez Pythonu).
- **Tagy vlastným kódom (mutagen)**: spoľahlivý ID3v2.3 + APIC cover (Windows ho zobrazí), rovnaká cesta pre MP3/M4A/FLAC.
- **Kvalita**: audio sa berie z najlepšieho streamu (`bestaudio`); MP3 sa kóduje max. 320 kbps. Nižší zdroj sa nepredstiera ako lepší – po Analyze sa zobrazí reálny zdroj a voliteľne *Never encode MP3 above source quality*. M4A berie natívny AAC stream bez re-encode; FLAC je len bezstratový kontajner (zdroj je stratový).

## Tagy, žáner a triedenie do priečinkov
- Do **každého tagu** (MP3/M4A/FLAC/MP4) sa zapíše komentár `www DaveeB YT Downloader` (Settings → Organization & tags: text sa dá zmeniť alebo vypnúť).
- **Žáner** sa určí automaticky: 1) údaj z YouTube, 2) MusicBrainz (voliteľné, posiela sa interpret + názov skladby), 3) kľúčové slová v tagoch/názve videa, 4) inak priečinok `Unsorted` (názov sa dá zmeniť). Do tagu sa zapisuje len ak zapneš *Also write the genre into the tag*.
- **Triedenie** je variabilné: v hlavnom okne *Sort into folders* (No folders, Genre, Genre / Artist, Artist, Artist / Album, Year, Genre / Year alebo vlastná šablóna, napr. `{genre}/{year}/{artist}`). Predvolená hodnota je v Settings. Premenné: `{genre} {artist} {album} {year}`, `/` vytvára vnorené priečinky.

## Riešenie problémov
- *Age restricted / Private / „not a bot“*: Settings → Advanced → Custom arguments: `--cookies-from-browser firefox`.
- *FFmpeg not found*: Settings → Check / install components.
- Logy: `%APPDATA%\YTDownloader\app.log`, nastavenia: `%APPDATA%\YTDownloader\settings.json`.
- URL s `&list=` sa berie ako playlist (správanie yt-dlp).
