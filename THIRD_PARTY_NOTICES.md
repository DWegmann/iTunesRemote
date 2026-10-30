# Drittanbieter und Referenz

Der ursprüngliche Projektcode steht unter der [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0). Required Notice: Copyright 2026 Dominic Wegmann. Drittanbieterkomponenten und deren Lizenztexte behalten ihre eigenen Lizenzen; die nichtkommerzielle Beschränkung dieses Projekts schränkt deren unabhängige Rechte nicht ein.

iTunesRemote verwendet React, React DOM, Scheduler und Lucide für die Weboberfläche sowie Starlette, Uvicorn, AnyIO, Click, h11, idna, typing_extensions und PyObjC für den lokalen Dienst. Die App enthält außerdem eine Python-Laufzeit und den PyInstaller-Bootloader. Die jeweiligen Lizenztexte werden beim App-Build in `Contents/Resources/ThirdPartyNotices` abgelegt. Entwicklerwerkzeuge verbleiben in der Projektumgebung.

Die Architektur mit iTunesLibrary für Lesezugriffe und ScriptingBridge für Änderungen orientiert sich an [ravishchawla/apple-music-mcp](https://github.com/ravishchawla/apple-music-mcp), geprüfter Commit `7fa71f2a870af9ef5a9d3aac74f45f459257f7bf`. Die Implementierung in diesem Projekt wurde eigenständig geschrieben; Quellcode der Referenz wurde nicht kopiert. Deren README nennt MIT als Lizenz.

Apple, macOS, iTunes, Apple Music und iPad sind Marken ihrer jeweiligen Inhaber. Die App verwendet installierte Apple-Systemframeworks; diese werden nicht in das Paket kopiert.
