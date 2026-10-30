# Prüfstand – iTunesRemote 0.1.0

Datum: 28.10.2026. Umgebung: macOS 27 auf Apple Silicon, Python 3.14.3, Swift 6.4 und Node 23.3.0.

Aktualisiert am 29.10.2026 für Build 19 mit dauerhafter Bewertungswarteschlange und automatischer Batch-Verarbeitung.

## Wiederholungsprüfung für die GitHub-Veröffentlichung am 30.10.2026

Der unveränderte App-Quellstand von Version 0.1.0, Build 19 wurde erneut geprüft. `make test` besteht mit 185 Python-Tests, Ruff ohne Befund und TypeScript ohne Typfehler. `make qa` erstellt den Webproduktionsbuild erfolgreich und besteht mit allen 26 Playwright-Prüfungen. Der bekannte Starlette-Hinweis zum künftig empfohlenen Testclient `httpx2` bleibt bestehen.

Ein erster Lauf innerhalb der eingeschränkten Sandbox scheiterte bei fünf Python-Netzwerkprüfungen und beim Start des Browser-Testservers an gesperrten lokalen Ports (`Operation not permitted`). Die vollständige Wiederholung mit den benötigten Rechten besteht. Die Tests verwenden weiterhin ausschließlich getrennte Demo- oder simulierte Daten.

Die Veröffentlichung ergänzt eine englische README, erhält die ausführliche deutsche Anleitung unter `README.de.md` und übernimmt die PolyForm-Noncommercial-Lizenz aus den bestehenden Mac-Projekten. Die beiden veröffentlichten Screenshots wurden im erfolgreichen Browserlauf neu erzeugt und visuell geprüft; sie zeigen die Demobibliothek. Der native App-Build und die Paket-, Signatur- sowie Diagnoseprüfungen wurden für diese Dokumentationsänderung nicht erneut ausgeführt; deren nachfolgend dokumentierter Stand stammt vom 29.10.2026. Persönliche Bewertungen wurden nicht verändert.

## Bestanden

| Prüfung | Ergebnis |
| --- | --- |
| `make test` | Ruff ohne Befund, 185 Python-Tests bestanden, einschließlich Bewertungswarteschlange, Wiederaufnahme nach Neustarts, Signaturauswahl, nativem Dienstneustart, Bewertungsnormalisierung, Passwortbeständigkeit, kompilierter Swift-Fortschrittsprüfung und echter LAN-Verbindung; TypeScript ohne Typfehler |
| Produktionsbuild der Weboberfläche | Vite-Build erfolgreich; alle Dateien lokal im App-Paket |
| `npm run test:e2e` in `web/` | 26 Playwright-Tests mit isoliertem Chrome-Profil bestanden |
| Suche in 50.000 synthetischen Titeln | Getestete Suche einschließlich Sortierung und erster Seite unter 300 ms |
| Eigenständiger App-Build | SwiftUI-Host, gebündelte Python-Laufzeit und Weboberfläche erfolgreich erstellt |
| Signatur | `codesign --verify --deep --strict` erfolgreich; App und Hilfsprozess mit derselben Apple-Development-Identität signiert |
| Signaturbeständigkeit | Geänderte Kopien von App und Hilfsprozess mit unterschiedlichen Codehashes erfüllen gegenseitig dieselben Identitätsanforderungen |
| Pakettest | Native Framework-Bindings und Datenschutzhinweise aus dem Paket geladen |
| Pakettest des Dienstes | HTTP, Zugriffsschutz, Webdateien und Rücklesen einer Demobewertung erfolgreich |
| Pakettest des Hosts | Dienststart, native Berechtigungsabfrage im Demomodus und geschützter Passwortabruf über `URLSession` erfolgreich, ohne einen Benutzer-Tab zu öffnen |
| Lebenszyklus | Dienst beendet sich nach Ende des Hosts; keine weiterlaufende Testsitzung erforderlich |
| Hängediagnose | Echter Mac-Host erfasst automatisch den absichtlich nicht antwortenden Test-Hilfsprozess; Ziel-PID und private Dateirechte bestätigt |
| API-Vertrag | Export im Projekt und im App-Paket stimmen mit der API-Definition überein |

Die Python-Tests prüfen unter anderem Session- und Bearerzugänge, Tokenablauf und Widerruf, Host-/Origin-/CSRF-Schutz, native Clients ohne Browsercookies, Konflikte und doppelte Schreibaufträge, geerbte Albumsterne, veraltete Snapshots, fehlende Metadaten, nicht über Automation erreichbare Titel und zusammengefasste Aktualisierungen mehrerer Clients.

Die Browserprüfungen decken Suche, Speichern und Entfernen von Bewertungen, Albumsterne, Gerätezugänge, Dunkelmodus, eine Ansicht mit 320 Pixeln Breite und getrennte Touch-Ziele von mindestens 44 × 44 Pixeln ab. Desktop-, Mobil-, Touch- und Dunkelansichten wurden als Screenshots erzeugt und visuell geprüft. Sie liegen unter `build/qa-*.png`.

Ein Hinweis bleibt im Python-Testlauf: Starlette empfiehlt für seinen Testclient künftig `httpx2` anstelle von `httpx`. Der bestehende Testlauf besteht; der Testclient ist kein Bestandteil der ausgelieferten App.

## Ergänzung: Berechtigungen

Die neuen Tests prüfen getrennte Ergebnisse für Medienzugriff und Automation, abgelehnte Freigaben und Zeitüberschreitungen mit simulierten nativen Objekten. Die Freigabeprüfung verändert keine Sterne. Ein Gerätezugang kann keine lokalen Systemdialoge auslösen. Die zusätzliche Browserprüfung bestätigt die manuelle Aktion in der Demooberfläche.

Der Pakettest bestätigt die neue Anfrage über den Mac-Host und dessen Ergebnisverarbeitung. Er nutzt ausschließlich den Demomodus. Die App besitzt eine gespeicherte Option für die Abfrage beim Öffnen sowie manuelle Aktionen in App, Menüleiste und Weboberfläche.

Build 6 trennt Freigabeprüfung und Import. Der Mac-Host nutzt `MusicAuthorization.currentStatus` und fordert die Medienfreigabe nur bei unbestimmtem Status über MusicKit an. Der Dienst prüft `ITLibrary` mit verzögertem Laden sowie Automation über die öffentliche Apple-Events-Vorprüfung. Die Prüfung liest keine Titel oder Playlists. Tests bestätigen die verzögerte Initialisierung ohne Datenabfrage, Fehler bei nicht verfügbarem Zugriff sowie die Automation-Vorprüfung und das Freigeben ihres nativen Deskriptors. Weitere Tests prüfen, dass eine Freigabe keinen Import startet und der Import seinen Fortschritt sowie Fehler getrennt meldet.

Bei der Fehlerdiagnose zeigte die zuvor laufende App beide Freigaben als verfügbar. Der vorhandene persönliche SQLite-Index enthielt 51.375 Titel; ausgelesen wurden ausschließlich Gesamtzahl und letzter Synchronisationszeitpunkt. Im bisherigen Ablauf hielt der vollständige Import die Berechtigungsanzeige offen. Echte Bewertungen wurden nicht geändert.

Der echte Host aus Build 6 wurde nach dem Entsperren gestartet und manuell geprüft. Nach **Berechtigungen anfordern** zeigte das App-Fenster innerhalb weniger Sekunden **Bibliothekszugriff ist verfügbar. Automation für die Musik-App ist verfügbar.** Der Status blieb **Bereit · Nur dieser Mac**. Der gespeicherte Schalter für die Abfrage beim Öffnen blieb ausgeschaltet. Die frühere, während des Imports offene Berechtigungsanzeige wurde damit im aktuellen Fenster nicht mehr beobachtet.

Der Dienst bedient zusätzlich den nativen Cocoa-Runloop, während asyncio den HTTP-Dienst betreibt. Ein Test mit der echten `NSOperationQueue.mainQueue()` bestätigt die Zustellung nativer Rückrufe. Wegen der Ad-hoc-Signatur kann ein neuer Build erneut macOS-Freigaben benötigen.

## Ergänzung: Hinzufügedatum

Die Sortierung bietet „Hinzugefügt: neueste zuerst“ und „Hinzugefügt: älteste zuerst“. Das Datum stammt aus `ITLibMediaItem.addedDate`; Titel ohne Datum stehen in beiden Richtungen am Ende. Die API unterstützt dafür `sort=addedDate` beziehungsweise `sort=addedDateAsc` und liefert das nullable Feld `addedDate`.

Die Weboberfläche zeigt das Datum als Spalte „Hinzugefügt“ und in den Titeldetails im Format `TT.MM.JJJJ`. Auf kleinen Bildschirmen und bei Touchbedienung steht es unter dem Titel. Die Darstellung verwendet die lokale Zeitzone des Browsers; fehlende oder ungültige Datumswerte erscheinen als `—`. Die aktualisierte Liste sowie die Details bei Desktop- und Mobilgröße wurden visuell geprüft (`build/qa-added-date.png`, `build/qa-mobile.png`, `build/qa-added-date-details.png`, `build/qa-added-date-details-mobile.png`). Alle acht bestehenden Browserprüfungen und die TypeScript-Prüfung bestehen weiterhin.

Tests prüfen die native Datumsübernahme mit simulierten Objekten, fehlende Daten, unterschiedliche Zeitzonen, gleiche Zeitpunkte, stabile Seitennavigation sowie die Kombination mit Suche, Bewertung und Playlistfilter. Ein vorhandener Cache wird ohne Verlust der Titel oder Bewertungen erweitert; die nächste Bibliotheksaktualisierung ergänzt verfügbare Datumswerte.

Die Browserprüfung bestätigt beide Richtungen und überlauffreie Ansichten bei 320 und 390 Pixeln. Die neue Desktopansicht wurde unter `build/qa-added-date.png` visuell geprüft. Der neu gebaute Dienst bestätigt beide Sortierungen auch im Pakettest mit isolierten Demodaten. Die persönliche Bibliothek wurde für diese Prüfungen nicht verwendet.

## Ergänzung: Cache und Hintergrundimport (Build 7)

Der Mac-Host startet den Import mit `background: true` und öffnet die Weboberfläche nach der unmittelbaren Startbestätigung. Ein vorhandener Index steht dadurch schon während des Imports bereit. Schreibgeschützte Cache-Verbindungen mit eigenen SQLite-Lesetransaktionen halten Suche, Filter, Sortierung, Seitenwechsel und Auftragsabfragen unabhängig vom nativen Worker nutzbar. Mehrere Clients teilen sich den laufenden Import. Die Oberfläche übernimmt neue Titel und Playlists nach dem Abgleich; Fehler lassen den gespeicherten Stand stehen. Bewertungen und Moduswechsel pausieren während des Imports, Cover werden anschließend wieder geladen.

Bewertungen lösen keinen Vollimport mehr aus. Die Prüfung der Hauptbibliotheks-ID erfolgt über ScriptingBridge ohne Titelabfrage; die Titelauflösung prüft diese ID nochmals vor Lesen und Schreiben. Konflikterkennung, Rücklesen und Wiederholungsschutz bleiben erhalten.

Automatisierte Tests blockieren einen simulierten Import und bestätigen schnelle Cache-Abfragen, gemeinsame Importe, Importfehler, erhaltene beziehungsweise abgelaufene Cursor, konsistente Lesetransaktionen und den Start aus einem vorhandenen Cache. Weitere Tests bestätigen erfolgreiche Bewertungen ohne erneuten Import, abgewiesene Bibliothekswechsel und Konflikte ohne Schreibzugriff. Simulierte native Objekte prüfen die Bibliotheks-ID ohne Titelabfrage sowie den erneuten ID-Abgleich bei der Titelauflösung. Die zwei zusätzlichen Browserprüfungen decken Suche und Sortierung während eines Imports, die Freigabe der Bewertungen nach Abschluss sowie die Fehleranzeige bei weiterhin nutzbarem Cache ab. Die Desktopanzeige wurde anhand von `build/qa-background-import.png` visuell geprüft.

Die neuen Abläufe wurden mit Demo- und simulierten Daten geprüft. Laufzeit und Bibliotheks-ID-Abgleich mit der persönlichen Musikbibliothek wurden für diese Änderung nicht live geprüft; persönliche Bewertungen wurden nicht verändert.

## Ergänzung: Veraltete Fortschrittsanzeige (Build 8)

Die Live-Diagnose bestätigte „Playlists: 37 von 37“ mit aktivem Fortschrittsindikator, obwohl der Bibliotheks-Worker bereits untätig und der SQLite-Index aktualisiert war. Geprüft wurden Prozessstapel, Gesamtzahl und letzter Abgleich des vorhandenen Index; persönliche Bewertungen wurden nicht verändert. Der genaue Grund für die ausgebliebene beziehungsweise überholte Abschlussanzeige im bisherigen Ereignisstrom wurde nicht nachgewiesen.

Der Dienst hält nun die letzte Fortschrittsmeldung mit fortlaufender Sequenz im Status bereit. Der Mac-Host liest diesen Status alle zwei Sekunden unabhängig von den Ereignismeldungen. Veraltete und doppelte Ereignisse können neuere Zustände nicht überschreiben; eine Statusantwort kann eine ausgebliebene Abschlussmeldung nachholen. Vorbereitung, Bewertungsabgleich, Suchindex, Playlist-Speicherung und Abschluss erhalten eigene Anzeigen. Die Indexzähler beginnen bei null und melden tatsächliche Schreibfortschritte.

Die Tests kompilieren die echte Swift-Zustandslogik und prüfen die Wiederherstellung nach einer fehlenden Abschlussmeldung sowie verspätete, doppelte und fehlerhafte Zustände. Python-Tests prüfen die Sequenz auch über Moduswechsel, Indexzähler und den Fortschrittsstatus während langsamer sowie fehlgeschlagener Importe. Browser- und Paketprüfungen bestehen weiterhin. Beim Neustart wurde im neuen App-Fenster „Bereit · Nur dieser Mac“ bestätigt; ein erneuter vollständiger Import der persönlichen Bibliothek wurde nicht durchgehend live beobachtet.

## Ergänzung: Medienfreigabe beim Verbinden (Build 9)

Normale Verbindungsversuche prüfen die Medienfreigabe nun vor jedem Öffnen und Neuladen der Bibliothek. Bei unbestimmtem Status antwortet der Dienst mit `MEDIA_PERMISSION_REQUIRED`, bei Ablehnung oder Einschränkung mit `MEDIA_ACCESS_DENIED`, ohne eine Freigabe anzufordern. Die Weboberfläche zeigt diese Fehler auch dann unmittelbar an, wenn der Hintergrundversuch schon vor der ersten Statusabfrage beendet wurde.

Die Medienanfrage läuft ausschließlich über die ausdrückliche Berechtigungsaktion beziehungsweise die aktivierte Startabfrage. Statusprüfung, Anfrage und Bibliothekszugriff gehören zum selben Hilfsprozess; der Host stellt keine zweite MusicKit-Anfrage mehr. Bereits entschiedene Freigaben werden nicht erneut angefragt. Der Python-Dienst nutzt dafür die öffentliche, inzwischen zugunsten der Swift-API von MusicKit als veraltet markierte StoreKit-Schnittstelle. Die erforderliche PyObjC-Bindung ist als Abhängigkeit und im Paket festgehalten.

Zusätzliche Tests prüfen unbestimmten, erlaubten, abgelehnten und eingeschränkten Zugriff, den ausdrücklichen Erstaufruf, erneute Statusprüfungen nach Widerruf sowie mehrfaches Verbinden über Adapter und HTTP ohne Initialisierung oder Neuladen der nativen Bibliothek. Der neue Browsertest bestätigt, dass mehrfaches Verbinden keinen Berechtigungsaufruf sendet und ausschließlich der entsprechende Einstellungsbutton die Anfrage auslöst. Der Pakettest prüft die echte Statusabfrage aus dem gebündelten Dienst, ohne einen Dialog auszulösen. Echte macOS-Zustimmungsdialoge wurden bei dieser Änderung nicht automatisiert angenommen; die persönliche Bibliothek wurde nicht verändert.

Die bestehende Ad-hoc-Signatur bleibt eine Grenze: Neue Codeversionen können die von macOS gespeicherte Freigabe verlieren. Die neuen Prüfungen verhindern daraus entstehende automatische Dialoge beim normalen Verbinden; eine über Neubauten stabile App-Identität benötigt weiterhin eine feste Signaturidentität. Nach einem Neubau muss die vorherige Menüleisten-App vollständig beendet werden.

## Ergänzung: Importdiagnose (Build 10)

Der frühere Sammelschritt „Bibliotheksdaten vorbereiten“ ist in native Aufräumarbeiten, titel- und playlistweises Kopieren sowie Vorbereitung des Bewertungsabgleichs aufgeteilt. Titelkopien und Suchdatenaufbereitung melden abgeschlossene Blöcke von 1.000 Titeln. Weitere Phasen markieren native Freigabeprüfung, Öffnen, Neuladen, Abfragen, Inhaltsvergleich, Indexersetzung und Speichern. Die Mac-App zeigt laufende Gesamt- und Schrittzeit, die Zeit seit der letzten Fortschrittsmeldung und gegebenenfalls ausbleibende Statusantworten an. Sie bietet einen Button zum Öffnen des Protokollordners und zeigt ihre Buildnummer.

`import.log` hält je Import eine Kennung sowie Zeit, Build, PID, Worker, Phase, Zähler und Laufzeiten fest. Phasenabschlüsse enthalten deren Dauer; alle zehn Sekunden wird während eines Imports ein Lebenszeichen geschrieben. Ab 30 Sekunden ohne echte Fortschrittsmeldung wird höchstens einmal pro Minute der Python-Aufrufstapel des Import-Workers erfasst. Drei rotierende Dateien von etwa 2 MiB begrenzen das Log. Der Logger übernimmt weder Bibliotheksinhalte noch Quellzeilen, lokale Variablen, Anfrageinhalte oder Exceptiontexte. Fehler werden als Typ, Aufrufstellen und gegebenenfalls öffentlicher Fehlercode protokolliert.

Falls selbst der Python-Dienst nicht mehr antwortet, startet der Mac-Host nach mindestens 15 Sekunden ohne Statusantwort eine kurze `/usr/bin/sample`-Aufnahme ausschließlich seines eigenen Hilfsprozesses. Der letzte Bericht steht in `import-native.sample.txt`, Werkzeugmeldungen in `import-native.log`. Beide Dateien werden beim nächsten Versuch ersetzt und wie das Anwendungslog mit `0600` angelegt. Kann macOS die Aufnahme nicht ausführen, meldet die App dies mit Verweis auf die Werkzeugausgabe.

Fünf neue Python-Tests prüfen fortlaufende und eingefrorene Zeitwerte, nicht zurückgesetzte Stillstandszeiten bei Lebenszeichen, begrenzte Stackaufnahmen des richtigen Threads, fehlende private Inhalte im Log, Rotation und Dateirechte, das Beenden des Monitors sowie die Unabhängigkeit kopierter Snapshots bei geteilten Referenzen. Die kompilierte Swift-Prüfung deckt Zeit- und Stillstandsanzeigen einschließlich lokal fortlaufender Zeit ab. Der Pakettest bestätigt die zusätzlichen API-Felder und das echte Importlog. Der separate Diagnosetest mit dem echten Mac-Host und absichtlich nicht antwortendem Test-Hilfsprozess bestätigte die automatische native Aufnahme des richtigen Prozesses mit privaten Dateirechten. Die persönliche Bibliothek wurde dafür nicht verwendet; die Ursache des konkret gemeldeten Stillstands bleibt bis zur nächsten Diagnose offen.

## Ergänzung: Webzugriff im lokalen Netzwerk (Build 11)

Der Dienst bindet standardmäßig an `0.0.0.0`. Die Host-Freigabe enthält weiterhin nur Loopback und die beim Start erkannten privaten IPv4-Schnittstellenadressen mit dem tatsächlichen Port. `--host 127.0.0.1` begrenzt den Dienst auf diesen Mac. Die Bereitschaftsmeldung enthält LAN-Adressen ohne Anmeldecode. Die Mac-App zeigt diese Adressen an und erzeugt auf Knopfdruck einen kopierbaren, einmaligen Anmeldelink mit 60 Sekunden Laufzeit. Host und Hilfsprozess enthalten aktualisierte Beschreibungen für die lokale Netzwerkfreigabe.

Fünf zusätzliche Python-Tests prüfen Schnittstellenerkennung, fehlende Schnittstellen, Host-/Origin-/CSRF-Prüfungen unter einer LAN-Adresse, ausschließlich lokale TCP-Bindung und Anmeldung sowie bestätigte Demobewertung über die echte private IPv4-Schnittstelle dieses Macs. Der Pakettest bestätigt LAN-Verbindung, ausgelieferte Webdateien, abgewiesenen anonymen Bibliothekszugriff, Codeaustausch und Cookie-Zugriff mit der gebündelten Laufzeit. Der native Host startet und beendet seinen Hilfsprozess weiterhin und erzeugt Browseranmeldungen erfolgreich über `URLSession`.

Die Weboberfläche verwendet für Schreibaufträge `crypto.getRandomValues`, da `crypto.randomUUID` über unverschlüsseltes LAN-HTTP nicht verfügbar ist. Eine zusätzliche Browserprüfung bestätigt Speichern und Entfernen einer Demobewertung bei fehlendem `randomUUID`. Bei der Gesamtprüfung wurde außerdem ein Rennen beim Abschluss eines Hintergrundimports behoben: Die Playlists werden vor der Statusänderung übernommen, damit die dadurch ausgelöste Effektbereinigung das Ergebnis nicht verwirft. Alle 14 Browserprüfungen bestehen einschließlich der parallel ergänzten Fortschrittsanzeige.

Die Verbindung verwendet HTTP ohne Verschlüsselung. HTTPS, Bonjour und eine native iPad-App bleiben offen. Ein Zugriff von einem separaten physischen Gerät und die Netzwerk-/Firewall-Freigaben auf diesem Gerät wurden nicht geprüft. Die neuen LAN-Bedienelemente der Mac-App konnten wegen des gesperrten Macs nicht live bedient werden; Swift-Kompilierung und nativer Pakettest bestehen. Die persönliche Musikbibliothek wurde für diese Netzwerkprüfungen nicht verwendet.

## Ergänzung: Fortschrittsanzeige im Web (Build 12)

Die Weboberfläche zeigt dieselben Importphasen und Zähler wie die Mac-App, dazu Gesamtzeit, Schrittzeit und die Zeit seit der letzten Fortschrittsmeldung. Ein Balken bezieht sich ausschließlich auf den aktuellen Arbeitsschritt und erscheint nur bei bekannter Gesamtzahl. Der Bereich bleibt nach Abschluss oder Fehler sichtbar. Während eines laufenden Imports aktualisiert sich der Status jede Sekunde; der lokale Zeitzähler läuft auch bei einer ausbleibenden Antwort weiter. Nicht mehr aktuelle Statuswerte und längerer Stillstand werden mit einem Verweis auf die Diagnoseprotokolle gekennzeichnet. Die laufenden Sekunden werden nicht über die Live-Ansage vorgelesen.

Eine gemeinsame Testdatei vergleicht die Phasentexte des Web-Clients mit der echten, kompilierten Swift-Anzeige. Weitere Browserprüfungen bestätigen weiterlaufende Zeiten bei einer angehaltenen Statusantwort, eingefrorene Zeiten nach Abschluss, den ersten Import ohne Cache oder Zeitangaben, weiterhin nutzbare Suche sowie die aktive Anzeige im Dunkelmodus. Ansichten mit 320 und 390 Pixeln bleiben ohne horizontalen Überlauf. Die Fortschrittsanzeige wurde anhand von `build/qa-web-progress.png`, `build/qa-web-progress-mobile.png` und `build/qa-web-progress-dark.png` visuell geprüft. Alle 16 Browserprüfungen, 117 Python-Tests, Ruff und die TypeScript-Prüfung bestehen.

Die neue Anzeige nutzt den vorhandenen Statusendpunkt; Import-, Bewertungs- und Freigabelogik wurden dafür nicht geändert. Die Prüfungen verwenden Demo- oder simulierte Fortschrittsdaten, keine persönliche Bibliothek.

## Ergänzung: Dauerhaftes Webpasswort (Build 13)

Ein zufälliges Passwort mit 24 Zeichen ersetzt die bisher angebotenen Einmallinks. Es wird beim ersten Dienststart in der bestehenden `auth.sqlite3` unter Application Support angelegt. Neustarts, neue interne Hostschlüssel und App-Updates verwenden denselben gespeicherten Wert. Die Migration erhält bestehende Sitzungen und Gerätezugänge. Die Datenbank enthält die lesbare Passwortkopie für die Mac-App und erhält Dateirechte `0600`; der übergeordnete Datenordner bleibt `0700`. Das App-Paket enthält kein installationsspezifisches Passwort.

Im App-Fenster lässt sich das Webpasswort anzeigen, verbergen und kopieren; die Menüleiste bietet eine Kopieraktion. Netzwerkadressen enthalten keine Anmeldegeheimnisse mehr. Die Webseite zeigt eine Passwortanmeldung, verwendet anschließend eine zwölf Stunden gültige Cookie-Sitzung und bietet Abmelden an. Der Passwortabruf bleibt dem privaten Hostschlüssel der Mac-App vorbehalten. Browsercookies und Gerätezugänge dürfen ihn nicht verwenden. Anmeldung benötigt einen passenden Origin und unterliegt der bestehenden Begrenzung auf 30 Anmeldeversuche je Minute. Schreibaktionen behalten den CSRF-Schutz. Die alten Bootstrap-Endpunkte bleiben als interne Kompatibilitätsschnittstelle bestehen.

15 zusätzliche Python-Prüffälle bestätigen Beständigkeit nach Neustart mit neuem Hostschlüssel und geänderter Buildkennung, Migration alter Datenbanken, erhaltene Sitzungen und Geräte, Dateirechte, falsche oder ungültige Passwörter, geschützten Passwortabruf, Origin-/CSRF-Schutz, Abmelden, erneute Anmeldung und die Begrenzung der Anmeldeversuche. Der echte LAN-Test verwendet jetzt ebenfalls das Passwort. Alle 132 Python-Tests, Ruff und TypeScript bestehen.

Alle 17 Browserprüfungen melden sich mit dem Passwort an. Ein neuer Ablauf prüft Abmelden, einen falschen Versuch, erneute Anmeldung sowie eine beim Neuladen erhaltene Sitzung. Die neue Anmeldeseite wurde bei Desktopgröße und 320 Pixeln anhand von `build/qa-password-login.png` und `build/qa-password-login-mobile.png` visuell geprüft. Beide Ansichten bleiben ohne horizontalen Überlauf.

Der Pakettest bestätigt die Passwortanmeldung über die echte LAN-Schnittstelle, dasselbe Passwort nach Neustart der gebündelten Laufzeit mit neuem Hostschlüssel und geänderter Buildkennung sowie den geschützten Abruf durch den echten Swift-Host. Build und Signaturprüfung bestehen. Der Diagnosetest mit angepasstem Testdienst bestätigt weiterhin die native Aufnahme eines blockierenden Hilfsprozesses. Die Tests verwenden ausschließlich Demo- oder simulierte Daten. Ein Zugriff von einem zweiten physischen Gerät sowie die neuen Passwort-Kopieraktionen im nativen App-Fenster wurden nicht live bedient.

Die Verbindung verwendet weiterhin HTTP ohne Verschlüsselung, einschließlich der Passwortübertragung. Das Passwort bleibt erhalten, solange die Anwendungsdaten aufbewahrt werden; ein gelöschter oder anderer Datenordner erhält ein neues Passwort.

## Ergänzung: Bewertung beim ersten Speichern (Build 14)

Import und Automation konnten null Sterne bei unterschiedlichem Kennzeichen für berechnete Bewertungen als `none` beziehungsweise `album` liefern. Die daraus gebildeten Revisionen unterschieden sich, obwohl beide Werte denselben unbewerteten Zustand beschrieben. Der erste Speicherversuch endete dann mit `RATING_CONFLICT`; erst der zweite verwendete die zurückgeladene Revision. Ein vorhandener persönlicher Index enthielt neben unbewerteten Titeln auch einen übernommenen Nullwert mit Herkunft `album`. Diese Beobachtung ist mit dem Fehlerablauf vereinbar, beweist für sich allein aber nicht dessen Ursprung in der laufenden Musik-App.

Der native Adapter verwendet jetzt beim Import und beim Rücklesen dieselbe Herkunftsbestimmung: Null Sterne erhalten immer `none`. Der Dienst akzeptiert zusätzlich alte Nullstern-Revisionen mit Herkunft `album`, damit vorhandene Caches sofort nutzbar bleiben. Änderungen des Zahlenwerts und Wechsel zwischen eigener und geerbter Bewertung mit Sternen bleiben Konflikte. Schreibprüfung, Rücklesen, Bibliotheksabgleich und Wiederholungsschutz bleiben erhalten.

19 zusätzliche Python-Prüffälle decken beide nativen Kennzeichen mit und ohne Sterne, Importrevisionen, das erste Speichern mit simulierten nativen Musikobjekten, alte Cache-Revisionen und weiterhin abgewiesene echte Änderungen ab. Die gezielten Regressionen schlugen vor der Korrektur fehl und bestehen danach. `make test` besteht mit 151 Python-Tests, Ruff und TypeScript. Alle 17 Browserprüfungen, Produktionsbuild, Signaturprüfung und Pakettest einschließlich bestätigter Demobewertung bestehen ebenfalls. Netzwerk- und Browserprüfungen benötigten eine Ausführung außerhalb der Sandbox, da diese das Binden lokaler Ports verweigerte.

Die persönliche Bibliothek wurde nicht verändert. Ein ausschließlich lesender Live-Vergleich wurde vor jedem Titelzugriff durch die dialogfreie Automation-Vorprüfung des Entwicklungsprozesses mit Status `-1744` gestoppt. Der vollständige Schreibablauf wurde deshalb mit Demo- und simulierten nativen Daten geprüft. Zur Verwendung von Build 14 muss eine noch laufende ältere Menüleisten-App vollständig beendet und die neue App gestartet werden.

## Ergänzung: Freigaben über Updates und fester Port (Build 15)

Die bisherige Ad-hoc-Signatur besaß eine an den jeweiligen Codehash gebundene Identitätsanforderung. Der Build verwendet jetzt die vorhandene gültige Apple-Development-Identität für Host, Hilfsprozess und dessen gebündelten nativen Code. `.local/signing.json` hält den öffentlichen Zertifikatfingerabdruck und die Identitätsanforderungen von App und Hilfsprozess fest; private Schlüssel verbleiben im Schlüsselbund. Künftige Builds müssen dieselbe Identität und dieselben Anforderungen verwenden. Ein fehlendes Zertifikat oder eine veränderte Identitätsanforderung führt zum Abbruch. Ad-hoc ist nur über die ausdrückliche Testoption `--identity -` möglich und ersetzt die gespeicherte Zertifikatswahl nicht.

Eine neue Buildnummer löst keine zusätzliche Berechtigungsanfrage aus. Der vorhandene Startschalter bleibt maßgeblich. Beim einmaligen Wechsel von Ad-hoc zur Zertifikatsignatur kann macOS nochmals eine Freigabe verlangen. Danach ist die notwendige stabile Codeidentität für die Zuordnung über Updates vorhanden. Die Änderung setzt keine macOS-Freigaben zurück und verändert keine Datenschutzdatenbank. Grundlage ist Apples Beschreibung der [Codeidentität und Freigaben](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements/).

Der Dienst und damit die Mac-App verwenden standardmäßig Port **8765**, auch nach Neustarts und Updates. `ITUNESREMOTE_PORT` beziehungsweise ein vorrangiges `--port` erlauben eine ausdrückliche Abweichung; Port `0` bleibt für isolierte Tests verfügbar. Ein belegter Port beendet den Start mit `PORT_IN_USE` und einer verständlichen Meldung auch im App-Fenster. Die App wartet beim Dienstneustart bis zu zehn Sekunden auf das Ende des bisherigen Prozesses, bevor sie denselben Port erneut öffnet.

Die zusätzlichen Prüfungen bestätigen die Auswahl und Wiederverwendung eines Zertifikats, den Abbruch bei fehlender Identität, unveränderte Anforderungen für beide Komponenten, Portvorgaben und Überschreibungen, den Fehler bei belegtem Port sowie erhaltene Browseranmeldung bei einem Neustart mit derselben Adresse. Eine kompilierte Prüfung des tatsächlichen Swift-Dienstcontrollers startet einen isolierten Testdienst, der seinen Port beim Beenden absichtlich verzögert freigibt, und bestätigt danach denselben Port mit einem neuen Dienstprozess. `scripts/smoke_signing.py` ändert Kopien beider echten App-Komponenten, signiert sie erneut und prüft unterschiedliche Codehashes, identische Anforderungen sowie die gegenseitige Erfüllung der alten und neuen Anforderungen. Dieser Test und der Pakettest mit Apple-Development-Signatur bestehen. Die vollständige Prüfung umfasst 167 Python-Tests, Ruff, TypeScript und 17 Browserprüfungen.

Persönliche Bewertungen wurden nicht geändert. Der tatsächliche Übergang einer vom Nutzer erteilten macOS-Freigabe über zwei aufeinanderfolgende zertifikatsignierte Produktupdates wurde nicht automatisiert bedient; nachgewiesen ist die dafür erforderliche beständige Signaturidentität. Der Build bleibt für lokale Entwicklung vorgesehen und ist nicht notarisiert.

## Ergänzung: Automatische Statusabfragen ohne Vollimport (Build 16)

Der Bewertungsauftrag selbst änderte bereits nur den betroffenen Titel. Die Weboberfläche rief jedoch alle 30 Sekunden und bei Rückkehr zum sichtbaren Tab zusätzlich `/library/refresh` mit `ifStale: true` auf. Nach 30 Sekunden seit dem letzten Import konnte dies erneut die gesamte Musikbibliothek einlesen und Bewertungen währenddessen sperren.

Die regelmäßigen Abfragen lesen jetzt ausschließlich `/status` aus dem gespeicherten Index. Änderungen anderer Clients und der Abschluss laufender Importe werden weiterhin erkannt. Vollimporte erfolgen beim App-Start, ausdrücklichen Verbinden oder manuellen Aktualisieren. Externe Änderungen in Musik erscheinen nach dem nächsten manuellen Import. Die API-Option `ifStale` bleibt für ausdrücklich angeforderte Importe verfügbar.

Der neue Browser-Regressionstest speichert eine Bewertung, lässt zwei Abfrageintervalle verstreichen und simuliert die Rückkehr zum Tab. Vor der Korrektur beobachtete er drei automatische Importanfragen; danach keine. Anschließend bestätigt er weiterhin die manuelle Aktualisierung und entfernt seine Demobewertung. Alle 18 Browserprüfungen sowie 32 gezielte Python-Tests zu Bewertungen und Hintergrundimporten bestehen. TypeScript und Produktionsbuild sind erfolgreich. Build 16 wurde mit der gespeicherten Apple-Development-Identität erstellt; die tiefe Signaturprüfung und der isolierte Pakettest einschließlich LAN-Zugriff, Demobewertung und nativem Host bestehen.

Die Prüfungen verwendeten ausschließlich Demo- oder simulierte Bibliotheksdaten. Persönliche Bewertungen wurden nicht verändert. Zum Übernehmen die bisherige Menüleisten-App vollständig beenden, Build 16 starten und geöffnete Browserseiten neu laden.

## Ergänzung: Sofortige Bewertungsanzeige (Build 17)

Gewählte Sterne erscheinen sofort in der Titelliste und den Titeldetails. Beim Entfernen einer eigenen Bewertung verschwindet diese ebenfalls unmittelbar. Der Ladekreis und die Sperre für weitere Änderungen desselben Titels bleiben während des Speicherns erhalten. Erst die bestätigte Antwort liefert die Erfolgsmeldung und den endgültigen Wert; dabei können geerbte Albumsterne wieder erscheinen.

Die vorläufige Anzeige liegt getrennt von bestätigten Titeldaten und Bewertungsrevisionen. Sie bleibt beim Suchen oder Sortieren während eines laufenden Schreibauftrags sichtbar. Bei Speicherfehlern erscheint wieder der bestätigte Wert, bei Konflikten der vom Dienst zurückgegebene aktuelle Titel. Ein zurückgebliebener Hoverwert kann die bestätigte oder zurückgesetzte Bewertung nach einem Klick nicht mehr verdecken.

Drei zusätzliche Browserprüfungen decken eine gezielt zurückgehaltene Speicheranfrage, die sofortige Anzeige in Liste und Details, Sortieren während des Speicherns, sofortiges Entfernen sowie Rücksetzen bei Fehlern und Übernahme eines Konfliktwerts ab. Vor der Korrektur scheiterte die Prüfung der unmittelbaren Sternauswahl. Danach bestehen alle 21 Browserprüfungen. Vorhandene Tests warten bei entfernten Bewertungen zusätzlich auf das Ende des Speicherns, bevor sie ihren Dialog schließen. Die Ansicht mit ausstehender Bewertung wurde anhand von `build/qa-pending-rating.png` visuell geprüft.

TypeScript, Webproduktionsbuild, App-Build mit beständiger Apple-Development-Signatur, tiefe Signaturprüfung und isolierter Pakettest bestehen. Die gebündelten Webdateien stimmen mit dem geprüften Webbuild überein. Die Prüfungen verwendeten Demo- oder simulierte Daten; persönliche Bewertungen wurden nicht verändert.

## Ergänzung: Wartezeit beim Speichern (Build 18)

Im bisherigen Ablauf durchlief jede Prüfung der Hauptbibliothek alle Playlists und fragte deren `specialKind` einzeln ab. Ein erfolgreicher Bewertungsauftrag wiederholte dies für den Bibliotheksabgleich, die Konfliktprüfung, das Schreiben und das Rücklesen. Zusätzlich wurde der betroffene Titel beim Rücklesen erneut über seine Persistent-ID gesucht. Nach der bestätigten Speicherung hielt die Weboberfläche den Ladekreis bis zum Ende weiterer Status- und Playlistabfragen aktiv.

Der native Adapter verwendet jetzt die im installierten Musik-Wörterbuch definierten `libraryPlaylists()` einer Quelle. Er prüft weiterhin eine eindeutig erkannte Hauptbibliothek und ihre Persistent-ID. Der gefilterte Titel wird mit `get()` zu einer festen Objektreferenz aufgelöst. Schreiben und Rücklesen verwenden dieselbe Referenz; vor dem Rücklesen wird die aktive Bibliothek nochmals geprüft. Fehler beim Auflösen des Titels, fehlende Freigaben, ein Bibliothekswechsel und eine von Musik nicht übernommene Bewertung liefern weiterhin keinen bestätigten Erfolg. Die Optimierung folgt Apples Hinweisen zur Vermeidung einzeln abgefragter Elemente und wiederholt ausgewerteter Referenzen ([Apple: Scripting-Bridge-Leistung](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/ScriptingBridgeConcepts/ImproveScriptingBridgePerf/ImproveScriptingBridgePerf.html)). Die Erzeugung gebundener `libraryPlaylists`-Referenzen wurde mit der installierten Musik-Schnittstelle ohne Abruf von Bibliothekswerten geprüft.

Die Weboberfläche beendet die Speicheranzeige unmittelbar mit der bestätigten Antwort. Weitere Status- und Playlistabfragen laufen unabhängig im Hintergrund. Sieben zusätzliche Python-Prüffälle decken den entfallenen Durchlauf aller Playlists, eine einzige Titelauflösung im Schreib- und Rückleseaufruf, fehlgeschlagene Auflösung mit und ohne Freigabefehler, einen Bibliothekswechsel nach dem Schreiben sowie eine fehlende oder mehrdeutige Hauptbibliothek ab. Der neue Browsertest hält die nachgelagerte Statusantwort zurück und bestätigt dennoch den beendeten Speichervorgang und erneut verfügbare Sterne. Die gezielten Regressionen für Playlistdurchlauf, Titelauflösung und verzögerte Statusantwort schlugen vor der Korrektur fehl.

`make test` besteht mit 174 Python-Tests, Ruff und TypeScript. Alle 22 Browserprüfungen, Webproduktionsbuild, App-Build mit der bestehenden Signaturidentität und tiefe Signaturprüfung bestehen. Der isolierte Pakettest bestätigt Dienst, LAN-Verbindung, Webdateien, Demobewertung und nativen Host. Die gebündelten Webdateien stimmen mit dem geprüften Webbuild überein.

Der Nutzer beobachtete zuvor ungefähr zwei bis fünf Sekunden. Die tatsächliche neue Speicherdauer mit seiner persönlichen Musikbibliothek wurde nicht gemessen; die Prüfungen verwendeten Demo- oder simulierte Daten. Persönliche Bewertungen wurden nicht verändert.

## Ergänzung: Dauerhafte Bewertungswarteschlange (Build 19)

Bewertungen lassen sich ohne Warten kurz hintereinander eingeben und sofort wieder ändern. Die gewählten Sterne erscheinen unmittelbar. Der Browser puffert noch nicht bestätigte Übertragungen lokal und sendet bis zu 25 Änderungen zusammen. Der Mac nimmt sie über einen vom Musik-Worker getrennten Executor dauerhaft in `rating-queue.sqlite3` an. Er sammelt neue Eingaben kurz und verarbeitet anschließend Batches mit höchstens 20 Aufträgen auf dem bestehenden nativen Worker. Jeder Titel behält seine Bibliotheks-, Konflikt- und Rückleseprüfung.

Noch wartende Entscheidungen derselben Sitzung für denselben Titel werden zusammengefasst. Eine monotone Auswahlzeit verhindert, dass ältere verzögert eintreffende Entscheidungen neuere ersetzen. Während eines bereits laufenden Schreibens gewählte Folgebewertungen werden nach dessen Bestätigung an die eigene bestätigte Revision angeschlossen; fremde Änderungen werden weiterhin als Konflikt abgewiesen. Ein Moduswechsel ist erst nach ausstehenden Aufträgen möglich. Importe pausieren die Verarbeitung. Fehlgeschlagene Aufträge bleiben sichtbar und werden nicht automatisch wiederholt; andere Bewertungen laufen weiter. Fortschritt bleibt als feste Anzeige auch beim Scrollen sichtbar. Betroffene Titel werden bei Fehlern aufgelistet.

Angenommene Aufträge laufen bei geschlossenem Browser weiter und überstehen App-Neustarts. Noch nicht vom Mac angenommene Eingaben benötigen zum erneuten Übertragen eine geöffnete Seite derselben Adresse. Verlorene Antworten verwenden dieselbe Anfrage-ID. Der Abgleich mit dem bestehenden Operationsjournal verhindert eine doppelte Speicherung bereits abgeschlossener Aufträge und ein blindes Wiederholen unklarer unterbrochener Schreibvorgänge. Fehlt nach Ablauf einer Sitzung eine erreichbare Bestätigung, fordert die Oberfläche zur Prüfung auf. Vorübergehende Fehler beim Lesen oder Abschließen der Warteschlange werden erneut versucht; ein bereits erhaltenes Musik-Ergebnis wird dabei nur noch im Journal gespeichert.

Elf zusätzliche Python-Prüffälle bestätigen schnelle Annahme und weiterhin verfügbare Suche bei blockiertem Musik-Worker, Zusammenfassen schneller Eingaben, nachlaufende Bewertungen desselben Titels, veraltete Übertragungen, getrennte Eigentümer, atomare Annahme und Wiederholungsschutz, Konflikte, Neustart-Wiederaufnahme bei unberührten beziehungsweise bereits bestätigten und unklaren Aufträgen, erhaltene Fehler sowie Wiederholung nur des Journalabschlusses bei vorübergehenden Datenbankfehlern. Die gezielten Warteschlangenprüfungen bestehen erneut nach der abschließenden Absicherung gegen Verwerfen bereits laufender Aufträge.

Vier zusätzliche Browserprüfungen bestätigen schnelle Bewertungsfolgen, Wiederaufnahme nach Neuladen, Speicherung nach Schließen des Tabs und den Verlust einer Annahmeantwort mit Wiederverwendung derselben ID nach Neuladen. Vorhandene Prüfungen bestätigen weiterhin sofortige Anzeige, Fehler und Konflikte; sie berücksichtigen nun die während des Speicherns bedienbaren Sterne. Die Desktop- und 320-Pixel-Ansicht der Warteschlange wurden anhand von `build/qa-rating-queue.png` und `build/qa-rating-queue-mobile.png` visuell geprüft.

`make test` besteht mit 185 Python-Tests, Ruff und TypeScript. Alle 26 Browserprüfungen, Webproduktionsbuild, App-Build mit unveränderter Signaturidentität und tiefe Signaturprüfung bestehen. Der erweiterte Pakettest bestätigt zusätzlich zwei über die gebündelte Warteschlange gespeicherte Demobewertungen und die Dateirechte `0600`. Gebündelte Webdateien und beide exportierten API-Verträge stimmen mit den geprüften Quellen überein. Die Prüfungen verwendeten Demo- oder simulierte Daten; persönliche Bewertungen wurden nicht verändert.

## Artefakte

- `dist/iTunesRemote.app`: eigenständig startbare Mac-App, rund 27 MB.
- `dist/iTunesRemote-0.1.0-arm64.zip`: gepackte App, rund 13 MB.
- `dist/build-info.json`: Version, Architektur, Mindestversion und Signaturstatus.
- `api/openapi.json`: versionierter Vertrag für Web und spätere native Clients.

Der konkrete Build benötigt **Apple Silicon und macOS 26.0 oder neuer**. Das Paket ist **nicht mit Developer ID signiert und nicht notarisiert**. Die Mindestversion folgt der hier gebündelten Python-Laufzeit; ältere macOS-Versionen wurden nicht geprüft.

## Noch nicht nachgewiesen beziehungsweise noch nicht umgesetzt

Die automatischen Tests verwenden getrennte Demo- oder simulierte Bibliotheksobjekte. Die persönliche Musikbibliothek wurde durch diese Tests weder gelesen noch verändert. Die Live-Prüfung öffnete die echte Bibliothek lesend und bestätigte beide Freigaben. Bei einem App-Start wurde außerdem die getrennte Importanzeige mit Playlistfortschritt beobachtet. Die individuelle Cloudbibliothek, echte Cover und Bewertungsänderungen in der persönlichen Musik-App wurden nicht systematisch geprüft. Persönliche Bewertungen wurden nicht geändert.

Webzugriff über private IPv4-Adressen im WLAN oder LAN ist über HTTP und ein dauerhaftes Webpasswort umgesetzt. Bonjour, ein HTTPS-Zertifikats- und automatischer Kopplungsprozess für echte iPads, eine native iPad-Oberfläche, Wiedergabe, Sammelbewertungen und Rückgängig gehören zu späteren Ausbaustufen. Die gemeinsame API und native Gerätezugänge sind vorhanden.
