import Foundation

struct LibraryProgress: Decodable {
    let stage: String
    let completed: Int
    let total: Int
    let sequence: Int
    var elapsedSeconds: Double? = nil
    var stageElapsedSeconds: Double? = nil
    var idleSeconds: Double? = nil

    var active: Bool { stage != "done" && stage != "failed" }

    var message: String {
        switch stage {
        case "opening": return "Musikbibliothek wird geöffnet …"
        case "permission-check": return "Medienfreigabe wird geprüft …"
        case "native-open": return "Musikschnittstelle öffnet die Bibliothek …"
        case "native-reload": return "Musikschnittstelle lädt die Bibliothek neu …"
        case "native-playlists": return "Playlistübersicht wird abgerufen …"
        case "native-tracks": return total > 0 ? "Titeleinträge abrufen: \(completed.formatted()) von \(total.formatted())" : "Titeleinträge werden abgerufen …"
        case "tracks": return "Titel einlesen: \(completed.formatted()) von \(total.formatted())"
        case "playlists": return "Playlists einlesen: \(completed.formatted()) von \(total.formatted())"
        case "preparing": return "Bibliotheksdaten werden vorbereitet …"
        case "native-cleanup": return "Native Bibliotheksobjekte werden aufgeräumt …"
        case "snapshot-tracks": return "Titeldaten kopieren: \(completed.formatted()) von \(total.formatted())"
        case "snapshot-playlists": return "Playlistdaten kopieren: \(completed.formatted()) von \(total.formatted())"
        case "rating-index": return "Bewertungsabgleich wird vorbereitet …"
        case "ratings": return "Bewertungen abgleichen: \(completed.formatted()) von \(total.formatted())"
        case "indexing": return "Suchindex aufbauen: \(completed.formatted()) von \(total.formatted()) Titeln"
        case "index-serialize": return "Suchdaten vorbereiten: \(completed.formatted()) von \(total.formatted()) Titeln"
        case "index-signature": return "Bibliotheksstände werden verglichen …"
        case "index-reset": return "Alter Suchindex wird ersetzt …"
        case "index-playlists": return "Playlists speichern: \(completed.formatted()) von \(total.formatted())"
        case "saving": return "Bibliotheksstand wird gespeichert …"
        case "done": return "\(total.formatted()) Titel geladen"
        case "failed": return "Aktualisierung fehlgeschlagen. Der gespeicherte Stand bleibt erhalten."
        default: return "Bibliothek wird aktualisiert …"
        }
    }
}

struct LibraryStatus: Decodable {
    struct Failure: Decodable { let message: String }
    let refreshing: Bool
    let progress: LibraryProgress?
    let error: Failure?
}

struct LibraryProgressState {
    private(set) var sequence = 0
    private(set) var loading = false
    private(set) var message = ""
    private var telemetry: LibraryProgress?
    private var receivedAt = Date()

    @discardableResult
    mutating func apply(_ progress: LibraryProgress) -> Bool {
        guard progress.sequence > sequence else { return false }
        sequence = progress.sequence
        loading = progress.active
        message = progress.message
        telemetry = progress
        receivedAt = Date()
        return true
    }

    @discardableResult
    mutating func apply(_ status: LibraryStatus) -> Bool {
        if let progress = status.progress {
            guard progress.sequence >= sequence else { return false }
            sequence = progress.sequence
            message = progress.message
            telemetry = progress
            receivedAt = Date()
            if status.refreshing && !progress.active {
                message = "Bibliotheksabgleich wird gestartet …"
            } else if !status.refreshing && progress.active {
                message = status.error?.message ?? "Bibliotheksabgleich beendet."
            }
        } else {
            guard sequence == 0 else { return false }
        }
        loading = status.refreshing
        return true
    }

    func diagnosticText(at date: Date = Date()) -> String {
        guard let progress = telemetry, let elapsed = progress.elapsedSeconds,
              let stageElapsed = progress.stageElapsedSeconds, let idle = progress.idleSeconds else { return "" }
        let delta = loading ? max(0, date.timeIntervalSince(receivedAt)) : 0
        var text = "Gesamt: \(Self.duration(elapsed + delta)) · Schritt: \(Self.duration(stageElapsed + delta))"
        if loading {
            text += "\nLetzte Fortschrittsmeldung vor \(Self.duration(idle + delta))."
            if idle + delta >= 30 { text += " Details stehen im Importprotokoll." }
        }
        return text
    }

    private static func duration(_ seconds: Double) -> String {
        let value = max(0, Int(seconds))
        return value >= 60 ? "\(value / 60) min \(value % 60) s" : "\(value) s"
    }
}
