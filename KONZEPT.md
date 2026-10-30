# iTunesRemote – Konzept für eine Mac-App mit Weboberfläche

Stand des Konzepts: 27.10.2026 · Seit 28.10.2026 existiert die erste Implementierung. Den tatsächlich gelieferten Umfang und die aktuellen Grenzen beschreibt die [README](README.de.md). Dieses Konzept enthält auch spätere Ausbaustufen.

## 1. Empfehlung

iTunesRemote läuft als kleine Menüleisten-App auf dem Mac. Sie stellt eine lokale Weboberfläche bereit, in der Nutzer ihre Musikbibliothek durchsuchen, nach Bewertungen filtern und einzelne Titel bewerten. Die Bewertungen werden direkt in Apples Musik-App gespeichert.

Empfohlen wird eine **SwiftUI-App mit gebündeltem Python-Dienst und einer Weboberfläche aus React und TypeScript**. Der Dienst übernimmt das Lesen und Schreiben über die von der Referenz verwendeten macOS-Schnittstellen. So lässt sich deren Ansatz weiterverwenden, während Installation, Berechtigungen und Startverhalten zu einer normalen Mac-App werden.

**Eine spätere native iPad-App ist als weiterer Client derselben API vorgesehen.** Geschäftslogik, Bewertungsregeln und Bibliothekszugriff liegen deshalb von Beginn an im Mac-Dienst. Weboberfläche und iPad-App erhalten dieselben Datenmodelle und Fehlerzustände. Die iPad-App benötigt weder eine eingebettete Weboberfläche noch einen eigenen Bibliotheksadapter.

Die erste Version arbeitet im Browser desselben Macs. Der versionierte API-Vertrag wird bereits dafür festgelegt. Zugriff vom iPhone, iPad oder einem weiteren Rechner im WLAN und die native iPad-App folgen als gesonderter Ausbau. Diese Priorisierung ist eine Annahme dieses Konzepts und kann vor der Umsetzung geändert werden.

## 2. Ziel und Umfang

Mit „iTunes-Bibliothek“ ist die auf dem Mac vorhandene, gegebenenfalls aus iTunes übernommene Bibliothek der heutigen Musik-App gemeint. Eine Unterstützung der alten iTunes-App auf älteren macOS-Versionen ist zunächst nicht vorgesehen.

Der typische Ablauf:

1. iTunesRemote starten und Bibliothekszugriff erlauben.
2. Über „Weboberfläche öffnen“ den Browser starten.
3. „Ohne eigene Bewertung“ oder eine Playlist auswählen.
4. Einen Titel suchen, bei Bedarf am Mac anhören und mit einem bis fünf Sternen bewerten.
5. Die bestätigte Bewertung erscheint im Browser und in der Musik-App.

Bibliotheksmetadaten und Zugangsdaten bleiben lokal. Die App benötigt kein eigenes Apple-Konto und kein eigenes Apple-Music-Abonnement für lokale Titel. Die Verfügbarkeit von Cloudtiteln hängt weiterhin von der Musik-App und dem vorhandenen Konto ab. Die App selbst erhält keine Apple-Anmeldedaten.

Nicht Bestandteil der ersten Version: Musikstreaming zum Browser, mehrere Benutzerkonten, automatische Bewertungen, Musikimport, Löschen von Titeln oder Bearbeiten von Audiodateien. Ton kommt bei einer Wiedergabefunktion vom Mac beziehungsweise dessen gewähltem Audioausgang.

## 3. Funktionen

| Bereich | Erste Version | Späterer Ausbau |
| --- | --- | --- |
| Bibliothek | Titel, Interpret, Album, Genre, Jahr, Dauer und Sterne anzeigen | Albumansicht, zusätzliche Metadaten |
| Suche | Titel, Interpret und Album durchsuchen; Sortierung und Seitennavigation | Erweiterte Suchabfragen |
| Filter | Ohne eigene Bewertung, ein bis fünf Sterne, Playlist | Gespeicherte Filter, Bewertungsstatistik |
| Bewertung | Ganze Sterne setzen, eigene Bewertung entfernen, Speicherstatus anzeigen | Mehrfachauswahl und Sammelbewertung mit Vorschau |
| Aktualisierung | Bibliotheksimport beim Start und manuell; regelmäßige Abfrage des gespeicherten Stands bei geöffneter Oberfläche | Feinere Erkennung externer Änderungen |
| Mac-App | Dienst starten, Status, Browser öffnen, Berechtigungen erklären, beenden | Optionaler Start bei Anmeldung |
| Anhören | Optional nach erfolgreichem Bibliotheks- und Bewertungsprototyp | Wiedergabesteuerung und Bewertungsmodus mit „Nächster Titel“ |
| Weitere Geräte | Schnittstellen dafür vorbereiten | WLAN-Zugriff mit Gerätekopplung und HTTPS |
| Native iPad-App | Gemeinsamen API-Vertrag, Datenmodelle und Versionsregeln festlegen | Eigene iPad-Oberfläche auf derselben API |

Das Kernziel bleibt auch ohne Wiedergabesteuerung vollständig nutzbar: Bibliothek ansehen und Titel bewerten.

## 4. Oberfläche und Bedienung

Die Weboberfläche orientiert sich an einer kompakten Musikverwaltung: klare Typografie, helle und dunkle Darstellung, wenige sichtbare Aktionen.

| Bereich | Inhalt und Verhalten |
| --- | --- |
| Navigation links | Alle Titel, ohne eigene Bewertung, bewertete Titel, Playlists |
| Kopfbereich | Suche, Trefferzahl, Sortierung, Bibliothek aktualisieren |
| Hauptbereich | Titelzeilen mit Interpret, Album, Dauer und direkt bedienbaren Sternen |
| Titeldetails | Vollständige Metadaten, Bewertungsherkunft, Verfügbarkeit und Speicherfehler |
| Statusbereich | Zeitpunkt der letzten Aktualisierung und Verbindung zum Mac |

Auf kleinen Bildschirmen werden Titelzeilen zu Karten. Titel, Interpret und Sterne bleiben sichtbar; weitere Metadaten stehen in den Details. Alle wesentlichen Aktionen funktionieren mit Tastatur und Touch. Zustände erhalten Textbeschriftungen und sind nicht allein durch Farbe erkennbar.

Ein Sternklick zeigt die Auswahl unmittelbar an und merkt sie in einem dauerhaften Puffer vor. Weitere Bewertungen bleiben möglich, auch für denselben Titel. Noch wartende Änderungen desselben Titels werden zur letzten Auswahl zusammengefasst; der Mac arbeitet sie anschließend automatisch in Batches ab. Ein erneuter Klick auf denselben Stern löscht nichts; dafür gibt es „Eigene Bewertung entfernen“. Während des Schreibens erscheint ein Ladekreis, danach die Speicherbestätigung. Eine feste Statusanzeige hält die Zahl ausstehender Änderungen auch beim Scrollen sichtbar. Fehler bleiben mit den betroffenen Titeln erhalten und können nach Prüfung durch erneutes Bewerten oder Verwerfen behandelt werden.

Wird ein Titel im Filter „Ohne eigene Bewertung“ bewertet, bleibt die Zeile bis zum Abschluss der Aktion sichtbar. Danach aktualisiert sich die Liste ohne Sprung an den Anfang.

## 5. Bewertungsmodell

Die Oberfläche setzt ein bis fünf ganze Sterne. Der Adapter übersetzt diese in `20`, `40`, `60`, `80` und `100`; `0` entfernt die explizite Titelbewertung. Dieses Mapping verwendet auch die Referenz. Deren `set_rating` meldet allerdings den angeforderten Wert zurück, ohne die erfolgreiche Übernahme nachzulesen. Für iTunesRemote gehört eine tatsächliche Rückleseprüfung zum Speichervorgang. [Quellcode: music_control.py](https://github.com/ravishchawla/apple-music-mcp/blob/7fa71f2a870af9ef5a9d3aac74f45f459257f7bf/music_control.py)

**Eigene Titelbewertung und geerbte Albumwertung müssen getrennt bleiben.** Apple dokumentiert, dass ein unbewerteter Titel die Bewertung seines Albums anzeigen kann. `isRatingComputed` kennzeichnet diesen Fall. Solche Titel gehören weiterhin in „Ohne eigene Bewertung“ und erhalten den Hinweis „Vom Album übernommen“. Nach dem Entfernen einer eigenen Bewertung können die Albumsterne erneut erscheinen. [Apple: isRatingComputed](https://developer.apple.com/documentation/ituneslibrary/itlibmediaitem/isratingcomputed)

Vorhandene Zwischenwerte bleiben beim Lesen erhalten. Die App rundet sie nicht stillschweigend und schreibt sie erst nach einer bewussten Bewertungsaktion um. Favoritenstatus und Sterne sind getrennte Eigenschaften; Favoriten sind für das Kernprodukt nicht erforderlich.

Eine Aktion „Rückgängig“ kann die vorherige eigene Bewertung wiederherstellen. Vorher wird geprüft, ob der Titel inzwischen anderweitig geändert wurde. Bei einem Konflikt zeigt die Oberfläche den aktuellen Wert an, statt ihn ungefragt zu überschreiben.

## 6. Technische Architektur

Die Komponenten haben klar begrenzte Aufgaben:

| Komponente | Aufgabe | Vorgeschlagene Technik |
| --- | --- | --- |
| Mac-App | Menüleiste, Einstellungen, Dienstlebenszyklus, Browserstart | Swift und SwiftUI |
| Weboberfläche | Darstellung, Suche, Filter und Bewertungsaktionen | React, TypeScript; lokal ausgelieferte Build-Dateien |
| Spätere iPad-App | Bibliothek und Bewertungen über die gemeinsame API bedienen | Swift und SwiftUI; Netzwerkzugriff über `URLSession` |
| Webdienst | Statische Dateien, REST-API, Sitzungen, Eingabeprüfung | Python, Starlette und Uvicorn |
| Bibliotheksadapter | Metadaten und Playlists lesen | PyObjC und `iTunesLibrary.framework` |
| Schreibadapter | Titel eindeutig auflösen, Bewertung schreiben und prüfen | PyObjC und ScriptingBridge zur Musik-App |
| Lokaler Index | Suche, Sortierung, Seitennavigation und bestätigte Änderungen | SQLite; bei Bedarf FTS5 |

Der Browser und später die iPad-App sprechen ausschließlich mit der REST-API des Mac-Dienstes. Dieser verwendet gemeinsame Bibliotheks- und Bewertungsdienste. API-Antworten enthalten Daten, keine HTML-Fragmente oder browserspezifischen Zustände. Ein MCP-Endpunkt ist für beide Oberflächen nicht erforderlich; er könnte später dieselben Dienste als zusätzlicher Zugang nutzen.

Die Python-Laufzeit und alle Abhängigkeiten werden mit der App ausgeliefert. Anwender benötigen weder Terminal noch Homebrew, Python-Installation oder laufende Paketdownloads. Die Referenz nutzt bereits Starlette und Uvicorn; zusätzliche Frameworks sind für die REST-Erweiterung zunächst nicht nötig. [Referenz: requirements.txt](https://github.com/ravishchawla/apple-music-mcp/blob/7fa71f2a870af9ef5a9d3aac74f45f459257f7bf/requirements.txt)

Der SwiftUI-Prozess startet und überwacht den Dienst. Ein zufälliges internes Startgeheimnis und eine lokale Bereitschaftsmeldung stellen sicher, dass die App ihren eigenen Dienst öffnet. Ein belegter Port führt zu einem anderen freien Port. Beenden der Mac-App beendet auch deren Dienst. Ein Absturz erzeugt eine sichtbare Fehlermeldung und eine begrenzte Neustartmöglichkeit.

Die Framework-Zugriffe laufen über einen dedizierten, serialisierten Worker. HTTP-Anfragen warten asynchron darauf. Suchanfragen greifen auf den Index zu und lösen keinen vollständigen Framework-Reload pro Tastendruck aus. Der Bedarf an Runloop und Threadbindung wird im technischen Prototyp geprüft.

Als vorläufiges Produktziel gilt macOS 14 oder neuer. Unterstützte macOS-Versionen und Prozessorarchitekturen werden erst nach Prüfung der gebündelten Laufzeit zugesagt.

## 7. Daten und Aktualisierung

Die Musik-App bleibt die Quelle für Bibliotheksdaten und Bewertungen. SQLite enthält einen erneuerbaren Index sowie nötige lokale Einstellungen und Änderungsinformationen. Ein Verlust des Index darf keine Bewertungen in Music löschen.

Ein Titel erhält mindestens:

| Feld | Bedeutung |
| --- | --- |
| `libraryScope`, `id` | Bibliothekskontext und Persistent-ID als 16-stellige Hex-Zeichenfolge |
| `title`, `artist`, `album`, `genre`, `year`, `durationSeconds` | Metadaten |
| `ratingRaw`, `ratingOrigin` | Originalwert `0–100`; Herkunft `none`, `user` oder `album` |
| `ratingRevision` | Lokale Revision zur Erkennung veralteter Browseraktionen |
| `ratingCapability` | `unknown`, `writable` oder `unavailable`, mit Grund und Prüfzeitpunkt |
| `snapshotRevision`, `lastSyncedAt` | Stand der Bibliothek |

Persistent-IDs werden nie als JavaScript-Zahlen übertragen: 64-Bit-Werte können dort Genauigkeit verlieren. Titel mit gleichem Namen bleiben getrennte Datensätze. Playlists werden über IDs adressiert; die Referenz verwendet hierfür teilweise Namen. Bei einem Bibliothekswechsel werden Index, Cursor und ausstehende Aktionen dem neuen Kontext zugeordnet; alte Aktionen dürfen keine neuen Titel treffen. [Referenz: music_library.py](https://github.com/ravishchawla/apple-music-mcp/blob/7fa71f2a870af9ef5a9d3aac74f45f459257f7bf/music_library.py)

Beim Start wird die Bibliothek eingelesen. Weitere Importe erfolgen beim ausdrücklichen Verbinden oder manuellen Aktualisieren. Die Weboberfläche fragt alle 30 Sekunden bei sichtbarem Tab sowie bei Rückkehr zum Tab ausschließlich den gespeicherten Status ab; während eines laufenden Imports erfolgt die Abfrage jede Sekunde. Änderungen anderer Clients werden aus dem gemeinsamen Index übernommen. Bewertungen und Statusabfragen lösen keinen Vollimport aus. Externe Änderungen in Musik erscheinen nach dem nächsten manuellen Import. Mehrere gleichzeitige Importanfragen teilen sich einen Abruf. Ein fehlgeschlagenes `reloadData()` darf keinen vollständigen Index durch vermeintlich leere Daten ersetzen. Apple dokumentiert dafür einen booleschen Rückgabewert. [Apple: reloadData](https://developer.apple.com/documentation/ituneslibrary/itlibrary/reloaddata())

Nach einer Bewertung liest der Schreibadapter den tatsächlichen Wert aus Music zurück. Der Index übernimmt den bestätigten Wert sofort. Ein noch veralteter ITLibrary-Snapshot darf diesen Wert nicht unmittelbar zurücksetzen; die Bestätigung bleibt bis zum Abgleich kenntlich.

Die Weboberfläche puffert noch nicht übertragene Entscheidungen lokal unter der jeweiligen Server-, Modus- und Bibliothekskennung. Der Mac bestätigt ihre dauerhafte Annahme in einer eigenen privaten SQLite-Warteschlange unabhängig vom nativen Worker. Er verarbeitet angenommene Aufträge auch bei geschlossenem Browser und nach einem App-Neustart weiter. Während eines Imports pausiert die Übertragung nach Musik. Pro Titel und Sitzung wird nur die letzte noch wartende Entscheidung ausgeführt; ältere verspätete Übertragungen dürfen sie nicht ersetzen. Folgebewertungen dürfen ausschließlich an bereits bestätigte eigene Änderungen anschließen. Fremde Änderungen bleiben Konflikte. Unklare unterbrochene Schreibaufträge werden anhand ihres Journals geprüft und nicht blind wiederholt. Erst das bestätigte Rücklesen zählt als Speicherung in Musik.

Schreibaufträge werden serialisiert und doppelte Anfragen mit derselben `requestId` zusammengeführt. Vor einer Änderung wird die aktuelle Bewertung mit der erwarteten Version verglichen. Gegen gleichzeitige Änderungen direkt in Music ist das kein atomarer Schutz; Rücklesen und erneuter Abgleich bleiben erforderlich.

Bei einem Timeout ist das Ergebnis zunächst unklar. Die App liest den Zustand nach und wiederholt keinen Schreibauftrag blind. Beim erneuten Verbinden werden unklare Vorgänge zuerst abgeglichen.

## 8. Vorgeschlagene API

Die Weboberfläche und API kommen vom selben Ursprung. Die spätere iPad-App nutzt dieselben Endpunkte über HTTPS. Alle Bibliotheks- und Schreibzugriffe benötigen eine gültige Browser- oder Gerätesitzung.

Die API beginnt mit `/api/v1`. Ein mit der Implementierung gepflegter OpenAPI-Vertrag beschreibt Anfragen, Antworten, Authentisierung und Fehler. Daraus lassen sich TypeScript- und Swift-Modelle beziehungsweise Clients erzeugen. Zusätzliche optionale Felder dürfen bestehende Clients nicht brechen; inkompatible Änderungen erhalten eine neue Hauptversion. Die Mac-App muss die letzte veröffentlichte iPad-App weiterhin unterstützen, bis eine angekündigte Übergangsfrist endet.

| Methode und Pfad | Aufgabe |
| --- | --- |
| `GET /api/v1/status` | Dienst-, Berechtigungs- und Synchronisationsstatus |
| `GET /api/v1/capabilities` | Serverkennung, unterstützte API-Versionen und verfügbare Funktionen |
| `GET /api/v1/playlists` | Playlists mit IDs und Anzahl der Musiktitel |
| `GET /api/v1/tracks?query=…&rating=unrated&playlistId=…&sort=…&cursor=…&limit=100` | Gefilterte, sortierte Titelseite |
| `GET /api/v1/tracks/{id}` | Titel und aktuelle Bewertungsfähigkeit |
| `PUT /api/v1/tracks/{id}/rating` | Sterne setzen oder eigene Bewertung entfernen |
| `GET /api/v1/requests/{requestId}` | Ergebnis eines eigenen Schreibauftrags nach Verbindungsabbruch abfragen |
| `POST /api/v1/rating-queue` | Bewertungen dauerhaft zur automatischen Batch-Verarbeitung annehmen |
| `GET /api/v1/rating-queue` | Eigene ausstehende Aufträge und angefragte Ergebnisse abrufen |
| `POST /api/v1/rating-queue/{id}/dismiss` | Eigenen noch wartenden oder fehlgeschlagenen Auftrag verwerfen |
| `POST /api/v1/library/refresh` | Aktualisierung anstoßen und deren Zustand zurückgeben |

Bewertungsanfragen enthalten `libraryScope`, `stars` als Ganzzahl `0–5`, `expectedRevision` und `requestId`. Die Antwort enthält den nachgelesenen Wert, die Herkunft und eine neue Revision. Eingaben, IDs, Sortierfelder und Seitengrößen werden serverseitig geprüft.

Cursor binden sich an Suchparameter und Snapshot-Version. Wechselt diese, fordert der Server eine neue erste Seite an. Eine feste Zweitsortierung nach ID verhindert eine zufällige Reihenfolge gleichnamiger Titel.

Fehler erhalten eindeutige Codes, etwa `MEDIA_ACCESS_DENIED`, `AUTOMATION_DENIED`, `TRACK_NOT_SCRIPTABLE`, `RATING_CONFLICT` oder `WRITE_UNCONFIRMED`. Ein nicht erreichbarer Titel darf nicht als fehlende Berechtigung ausgegeben werden. Neue oder unbekannte Fehler bleiben als solche erkennbar.

### 8.1 Vertrag für die spätere iPad-App

**Verbindung:** Der Mac bleibt Server und Quelle der Bibliothek. Die iPad-App findet ihn nach aktivierter Netzfreigabe über einen fest definierten Bonjour-Dienst; alternativ übernimmt sie die Adresse per QR-Code oder manueller Eingabe. Eine dauerhafte Serverkennung identifiziert den Mac unabhängig von wechselnden IP-Adressen und Ports. Eine gefundene Adresse allein begründet noch kein Vertrauen.

**Kopplung und Anmeldung:** Ein neuer Client wird in einem zeitlich begrenzten Kopplungsfenster ausdrücklich am Mac bestätigt. Danach erhält die native App eigene, widerrufbare Gerätezugänge. Kurzlebige Zugriffstokens werden als `Authorization: Bearer …` gesendet; ein rotierender Erneuerungsnachweis liegt im iPad-Schlüsselbund. Ablauf, Erneuerung und Widerruf gehören zum API-Vertrag. Die Mac-App zeigt gekoppelte Geräte und kann einzelne Zugänge einschließlich ihrer Erneuerungsnachweise sperren. Browser behalten ihre Cookie-Sitzung; beide Zugangsarten unterliegen denselben Berechtigungen.

**Gemeinsame Semantik:** IDs, Revisionen und Cursor sind undurchsichtige Zeichenfolgen; Zeitpunkte werden als ISO-8601-Werte in UTC übertragen. Fehlende Werte und unbekannte neue Statuswerte sind ausdrücklich definiert. Die Fähigkeitenabfrage meldet etwa, ob Schreiben und Wiedergabe verfügbar sind. Eine ältere iPad-App kann weiterhin lesen, wenn zusätzliche Funktionen hinzukommen. Eine nicht unterstützte API-Version erzeugt einen verständlichen Aktualisierungshinweis.

**Abgleich:** Web und iPad erhalten dieselben bestätigten Bewertungen. Zunächst fragt ein aktiver Client die Snapshot-Revision in begrenzten Abständen ab und lädt bei Änderungen seine sichtbaren Daten neu. Nach App-Rückkehr oder Verbindungsabbruch erfolgt immer ein neuer Abgleich. Eine spätere Ereignisschnittstelle kann Aktualisierungen beschleunigen; ihre Meldungen ersetzen nicht den erneuten Datenabruf. Konflikte zwischen Browser, iPad und Music nutzen dieselben Revisionsprüfungen.

**Unterbrochene Verbindung:** Die iPad-App darf zuletzt geladene Titel als veralteten, lokal gespeicherten Stand anzeigen. Neue Bewertungen benötigen in der ersten iPad-Version eine Verbindung zum Mac. Ein bereits abgesendeter Auftrag wird nach Wiederverbindung über seine `requestId` geprüft. Ergebnisse werden dafür zeitlich begrenzt und der jeweiligen Sitzung beziehungsweise dem Gerät zugeordnet aufbewahrt. Ist das Ergebnis nicht mehr vorhanden, wird der aktuelle Titelzustand vor einem neuen Schreibversuch abgeglichen.

**Netzwerkfreigabe:** Die iPad-App erklärt den lokalen Netzwerkzugriff über `NSLocalNetworkUsageDescription` und deklariert den verwendeten Bonjour-Dienst über `NSBonjourServices`. Diese Freigabe und die gerätebezogene Kopplung sind getrennte Schritte. Der HTTPS-Prototyp muss auch mit `URLSession` und den Anforderungen von App Transport Security funktionieren. Der konkrete Zertifikatsweg bleibt vor der Umsetzung der Netzfreigabe zu prüfen. [Apple: Lokaler Netzwerkzugriff](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy), [Apple: Sichere Netzwerkverbindungen](https://developer.apple.com/documentation/security/preventing-insecure-network-connections)

## 9. Zugriff, Berechtigungen und Auslieferung

Standardmäßig lauscht der Dienst ausschließlich auf Loopback. Die Mac-App öffnet den Browser mit einem kurzlebigen Einmalcode im URL-Fragment. Die Seite tauscht ihn gegen eine Sitzung und entfernt ihn sofort aus der sichtbaren Adresse. Dauerhafte Schlüssel stehen weder in der URL noch im Browser-Speicher oder in Protokollen.

Auch lokal wird der Host geprüft. Browserzugriffe benötigen eine Sitzung, bei Schreibaktionen zusätzlich eine Prüfung von Ursprung und CSRF-Schutz sowie ein passendes JSON-Format. Cookies sind `HttpOnly` und `SameSite=Strict`; bei HTTPS zusätzlich `Secure`. Native iPad-Anfragen authentisieren sich stattdessen ausdrücklich mit ihrem Gerätetoken; ein fehlender Browser-Origin ist keine Freigabe für einen anonymen Zugriff. Die API verlangt auch vom nativen Client keine Browsercookies. Inhalte werden ohne externe Skripte ausgeliefert, Metadaten als Text gerendert und eine restriktive Content Security Policy gesetzt. Damit kann ein manipulierter Titelname keinen Browsercode ausführen.

Für Bibliothekszugriffe benötigt die App `NSAppleMusicUsageDescription` und die Zustimmung des Nutzers. Für Apple Events gehören `NSAppleEventsUsageDescription` und beim Hardened Runtime das Entitlement `com.apple.security.automation.apple-events` zur Planung. Der Einrichtungsdialog erklärt Lesen und Bewerten getrennt; eine verweigerte Automationsfreigabe soll das reine Durchsehen nicht blockieren. [Apple: ITLibrary](https://developer.apple.com/documentation/ituneslibrary/itlibrary), [Apple: Apple-Events-Nutzung](https://developer.apple.com/documentation/bundleresources/information-property-list/nsappleeventsusagedescription), [Apple: Entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.automation.apple-events)

Die erste Auslieferung erfolgt als signierte und notarisierte App außerhalb des Mac App Store. Welche Identität macOS für einen gebündelten Python-Helfer bei den Freigaben anzeigt, ist ausdrücklich ein Prüfpunkt. Das Konzept verspricht noch keine durchgehend auf die SwiftUI-App lautenden Berechtigungsdialoge. Ein App-Store-Vertrieb erfordert eine eigene Sandbox-Prüfung. [Apple: Sandboxing und Automation](https://developer.apple.com/library/archive/qa/qa1888/_index.html)

**WLAN-Ausbau:** ausdrücklicher Schalter in der Mac-App, echte Bestätigung eines neuen Geräts am Mac, begrenzte Kopplungsversuche, widerrufbare Sitzungen und HTTPS. Ein auf Safari und in einer nativen iPad-App praktikabler Zertifikats- und Vertrauensweg muss vorher prototypisch nachgewiesen werden. Eine Zertifikatswarnung wegzuklicken ist kein fertiger Einrichtungsprozess. Lokale Netzwerkberechtigungen sind auch auf den unterstützten macOS-Versionen zu prüfen. Ruhezustand oder Beenden des Macs unterbrechen den Zugriff; Weboberfläche und iPad-App zeigen das an.

Der OAuth-Shim der Referenz wird nicht als Gerätekopplung übernommen: Er genehmigt Anfragen automatisch. Sein Code prüft zudem die ausgegebene Tokenlaufzeit nicht im späteren Zugriffspfad. Für einen freigegebenen Webzugang ist eine tatsächliche Geräteautorisierung erforderlich. [Referenz: server.py](https://github.com/ravishchawla/apple-music-mcp/blob/7fa71f2a870af9ef5a9d3aac74f45f459257f7bf/server.py)

## 10. Was die Referenz liefert

Geprüfter Stand: Commit [`7fa71f2a870af9ef5a9d3aac74f45f459257f7bf`](https://github.com/ravishchawla/apple-music-mcp/tree/7fa71f2a870af9ef5a9d3aac74f45f459257f7bf).

| Bestandteil | Nutzen | Nötige Anpassung |
| --- | --- | --- |
| `music_library.py` | Lesen, Metadaten, Suche und ID-Format | Rohbewertungen und Herkunft ergänzen; Index, Seitennavigation und Reload-Fehler behandeln |
| `music_control.py` | Exakte Titelsuche, Bewertung und optionale Wiedergabe | Rücklesen, Konflikte, Zeitlimits und differenzierte Fehler ergänzen |
| `server.py` | Vorbild für lokalen Dienst und vorhandene Bibliotheksfunktionen | Webdateien, REST-API und eigene Sitzungsverwaltung ergänzen |
| `requirements.txt` | Ausgangspunkt für Python-Abhängigkeiten | Versionen und Builds reproduzierbar festlegen |
| `tests/` | Kleine Prüfungen für IDs, Umrechnung, Suche und Serialisierung | Tests für Schreibfehler, Herkunft, Synchronisation und App-Paket ergänzen |

Die Referenz wählt ersatzweise die größte Playlist, wenn sie die Hauptbibliothek nicht findet. Für Schreibzugriffe sollte diese Heuristik durch eine eindeutige Erkennung oder einen erklärten Fehler ersetzt werden. Die vorhandenen Sperren schützen vor allem die Initialisierung; sie ersetzen keine Serialisierung aller Framework-Zugriffe. Das sind Befunde der Codeprüfung, keine auf diesem Mac reproduzierten Laufzeitfehler.

Die README bezeichnet das Projekt als MIT-lizenziert. Im geprüften Dateibaum liegt keine separate `LICENSE`-Datei. Vor einer Codeübernahme sollten vollständiger Lizenztext und Urhebervermerk geklärt und in die App übernommen werden. Das Konzept selbst kopiert keinen Implementierungscode. [Referenz: Lizenzangabe](https://github.com/ravishchawla/apple-music-mcp/blob/7fa71f2a870af9ef5a9d3aac74f45f459257f7bf/README.md#license)

## 11. Grenzen und offene Nachweise

Die Referenz beschreibt Cloudtitel, die über ITLibrary sichtbar sind, über ihren ScriptingBridge-Zugriff aber nicht gefunden werden. Das ist eine dokumentierte Grenze dieses Ansatzes und keine pauschale Aussage, dass jeder Cloudtitel unbewertbar ist. Die App ermittelt die Fähigkeit je Titel; ein Cloudmerkmal allein schaltet Sterne nicht ab. Scheitert die Auflösung, zeigt sie den konkreten Grund und gegebenenfalls einen Hinweis auf das Laden in Music. [Referenz: Fehlerbehebung](https://github.com/ravishchawla/apple-music-mcp/blob/7fa71f2a870af9ef5a9d3aac74f45f459257f7bf/README.md#troubleshooting)

Ein Bibliothekswechsel, gelöschte Titel, doppelte Playlistnamen und verzögerte Snapshots gehören in die Erprobung. Vollständige Cloudabdeckung und die Weitergabe von Bewertungen durch Apples eigene Cloud-Synchronisation werden nicht zugesagt. Die geplante iPad-App bezieht ihre Bewertungen direkt aus der gemeinsamen Mac-API.

Direktes Lesen oder Verändern der internen Music-Datenbank ist nicht vorgesehen. Die App nutzt die genannten Frameworks und die Automationsschnittstelle.

## 12. Umsetzungsfolge und Abnahme

**Schritt 1 – Machbarkeit im echten App-Paket.** Signierte Minimal-App mit gebündelter Laufzeit bauen. Lokale Titel und Playlists lesen, eine ausdrücklich ausgewählte Bewertung setzen, zurücklesen und wiederherstellen. Geerbte Albumsterne, verweigerte Berechtigungen, beendete Musik-App und repräsentative Cloudtitel prüfen. Die angezeigte Berechtigungsidentität dokumentieren. Erst danach den gewählten Paketaufbau festlegen.

**Schritt 2 – Kernprodukt.** Dienstlebenszyklus, Index, versionierte REST-API mit OpenAPI-Vertrag, Webliste, Suche, Filter, Sterne und Speicherstatus umsetzen. Den Vertrag mit einem zusätzlichen Client ohne Browsercookies prüfen, bevor eine iPad-Oberfläche entsteht. Bewertungsänderungen direkt in Music und in zwei Browserfenstern gegeneinander prüfen. Ein Dienstabsturz darf keine falsche Erfolgsmeldung erzeugen.

**Schritt 3 – Bedienung und Auslieferung.** Responsive Darstellung, Tastaturbedienung, verständliche Fehler, Installationspaket und Neustartverhalten fertigstellen. Optional Wiedergabe und Rückgängig ergänzen. Auf einem Mac ohne Entwicklerinstallation testen.

**Schritt 4 – WLAN und iPad-Anbindung.** Zertifikatsweg, Bonjour-Erkennung, Gerätekopplung, Tokenerneuerung und Widerruf mit einem kleinen nativen iPad-Testclient auf echtem Gerät prüfen. Fehlende Netzwerkfreigabe und Wechsel der Mac-Adresse testen. Erst nach bestandener Prüfung Netzfreigabe anbieten. Eine vollständige iPad-App kann anschließend auf dem bereits geprüften Vertrag entstehen.

Geplante Abnahmekriterien:

- Alle vom Adapter gelieferten Musiktitel sind über die Seitennavigation erreichbar; gleiche Namen führen nicht zu Verwechslungen.
- Filter und Anzeige unterscheiden eigene, fehlende und geerbte Bewertungen korrekt.
- Jede erfolgreiche Bewertungsantwort beruht auf Rücklesen; Fehler und unklare Ergebnisse bleiben sichtbar.
- Ein Klick auf einen Titel bewertet ausschließlich dessen ID im passenden Bibliothekskontext.
- Ungültige Sterne, fremde Ursprünge und nicht autorisierte Schreibzugriffe werden abgewiesen.
- Suche und Sortierung liefern mit 50.000 synthetischen Titeln nach Indexaufbau unter definierten Testbedingungen Ergebnisse in höchstens 300 ms. Das ist ein zu messendes Ziel, kein bereits bestätigter Leistungswert.
- Installieren und Starten funktionieren ohne separat installiertes Python oder Homebrew.
- Ein nativer Testclient kann ohne Browsercookies dieselben Titel lesen und Bewertungen setzen; bestehende Webclients bleiben funktionsfähig.
- Gleichzeitige Änderungen aus Web und iPad, Rückkehr aus dem Hintergrund und unklare Schreibaufträge werden ohne blindes Überschreiben abgeglichen.
- Ein widerrufenes Gerät kann weder Daten abrufen noch Tokens erneuern; eine bereits veröffentlichte Clientversion bleibt innerhalb ihrer zugesagten API-Version kompatibel.

## 13. Prüfstand dieses Konzepts

Die folgenden Angaben beschreiben die Konzeptphase vom 27.10.2026. Für die anschließende Implementierung gelten die Prüfungen und Grenzen der README.

Durchgeführt wurden die Prüfung von README, `music_library.py`, `music_control.py`, `server.py`, `requirements.txt`, den drei vorhandenen Testdateien und dem Dateibaum am oben genannten Commit sowie der Abgleich zentraler Schnittstellen mit Apple-Dokumentation. Der lokale Projektordner enthielt zu Beginn keinen Code.

Die Ergänzung zur iPad-Anbindung berücksichtigt Apples Dokumentation zu lokalem Netzwerkzugriff und App Transport Security. Der API-Vertrag einschließlich OpenAPI-Beschreibung und nativer Testclient sind geplante Bestandteile der Umsetzung; sie wurden mit diesem Konzept noch nicht implementiert.

Nicht durchgeführt wurden ein Build, das Ausführen der Referenztests, Zugriffe auf die persönliche Musikbibliothek, echte Bewertungsänderungen oder Messungen. Der lokale Pfad zur `Music.sdef` war in der Ausführungsumgebung nicht vorhanden. Aussagen zu tatsächlicher Cloudabdeckung, Berechtigungszuordnung und Paketkompatibilität bleiben deshalb offen.
