<p align="center">
  <img src="design/visual-assets/v2/branding/aredoko-readme-banner.png" alt="Aredoko banner" width="100%" />
</p>

<h1 align="center">Aredoko (あれどこ)</h1>

<p align="center">
  <strong>Find files whose names you forgot—from what you still remember.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%20x64-0078D6?logo=windows&logoColor=white" alt="Windows x64" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2ea44f" alt="MIT License" /></a>
  <a href="https://ko-fi.com/jakymikudev"><img src="https://img.shields.io/badge/Ko--fi-Support%20Aredoko-FF5E5B?logo=ko-fi&logoColor=white" alt="Support on Ko-fi" /></a>
</p>

<p align="center">
  <strong>English</strong> | <a href="README.ja.md">日本語 (Japanese)</a>
</p>

---

**Aredoko** is a local-first Windows desktop app for searching, viewing, and organizing your images, books/doujinshi, videos, and audio files in one place.

Start immediately with fast filename and tag search—no AI setup required. When you need deeper recall, enable optional local AI search to find files using vague natural-language queries (such as *"illustration of a blue night sky"*), visual cues, video scenes, or audio moments.

## Why Aredoko?

- **Local-First & Private** — Everything runs on your PC. Your files, metadata, and search queries are never uploaded to external servers.
- **Non-Destructive** — Original files remain strictly read-only. Tags, shelves, favorites, and reading positions are saved separately in a local catalog (`%LOCALAPPDATA%\Aredoko`).
- **AI Is Completely Optional** — Standard search, browsing, viewing, and organization work out of the box without a GPU. AI models and runtimes are never downloaded without your explicit action.
- **Isolated Runtime** — The base Python runtime fetched on first launch is kept in an app-dedicated folder and does not modify any existing Python installation on your system.

## Features

- **Search**
  - Search immediately by filename and tags across multiple registered folders.
  - Optional local AI search covering image appearance, book covers & indexed pages, video scenes (with timestamp matching), audio content & video audio tracks, and filename/tag semantics.
  - Find visually or sonically similar items directly from an existing file.
- **View & Play**
  - Built-in viewer and media player for images (including animated GIF/WebP/APNG), books/archives (CBZ/ZIP and image folders with spread direction and reading position restore), videos, and audio.
  - Jump directly to matched pages or exact video/audio timestamps from search results.
  - Optionally configure double-click to open files in your default Windows apps.
- **Organize & Protect**
  - Manage libraries with tags, shelves, favorites, exclusion rules, and batch editing.
  - Create live backups from inside the app and verify restores to a new destination without overwriting your active library.

## Getting Started

> **Note:** Public release packages are currently in preparation. Once published, Windows x64 archives will be available on [GitHub Releases](https://github.com/jakymiku/Aredoko/releases).

1. Download the latest Windows x64 archive from [GitHub Releases](https://github.com/jakymiku/Aredoko/releases).
2. **Extract the entire ZIP archive** (keep `Aredoko.exe` together with all bundled folders) and launch `Aredoko.exe`. On first launch, follow the prompt to download the isolated base Python runtime.
3. Add the folders you want to manage and choose **Fetch item list only** (`アイテム一覧だけ取得`) to start searching by filename and tags immediately.
4. *(Optional)* To use AI search, open **Settings → Setup & First Run** (`設定 → 使い方・初回設定`) to automatically set up the AI runtime (CPU or CUDA) and models, restart Aredoko, and build AI indexes for your folders.

For detailed usage instructions and troubleshooting, see the [User Guide (Japanese)](docs/user-guide.md).

## Requirements & Notes

| Item | Details |
| --- | --- |
| **OS** | Windows 10 / 11 (x64) |
| **UI Language** | Primarily Japanese (English overview is maintained in this README) |
| **Unsigned Binaries** | Release builds are not code-signed. If Windows **Smart App Control** is set to *On (Enforcement)*, launching `Aredoko.exe` may be blocked. |
| **Optional AI Storage** | Auto-setup downloads up to ~4.5 GB and needs ~15 GB of free disk space during installation. After verification, ~3 GB of wheel cache can be cleared from **Settings → Storage & Cache**. |

## Feedback & Bug Reports

Found a bug or have a feature suggestion? Please open an issue on [GitHub Issues](https://github.com/jakymiku/Aredoko/issues).  
When reporting an issue, including the version and environment summary from **Settings → Diagnostics** (`設定 → 診断情報`) helps a lot.

## Support

Aredoko is free and open-source under the MIT License. If you find it useful and want to support ongoing development, optional tips are always appreciated:

<a href="https://ko-fi.com/jakymikudev"><img src="https://img.shields.io/badge/Support%20on-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support on Ko-fi" /></a>

## License

Aredoko itself is released under the [MIT License](LICENSE).  
For bundled FFmpeg and other third-party components, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (and `THIRD_PARTY_LICENSES` included in release ZIP packages).