import Foundation

@main
struct LibraryProgressTests {
    static func main() throws {
        if CommandLine.arguments.count > 1 {
            struct ProgressCase: Decodable { let stage: String; let message: String; let total: Int? }
            let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
            let cases = try JSONDecoder().decode([ProgressCase].self, from: data)
            for item in cases {
                let progress = LibraryProgress(stage: item.stage, completed: 3, total: item.total ?? 7, sequence: 1)
                assert(progress.message == item.message, "Progress contract mismatch: \(item.stage)")
            }
        }
        var state = LibraryProgressState()
        let playlists = LibraryProgress(stage: "playlists", completed: 37, total: 37, sequence: 2)
        assert(state.apply(playlists))
        assert(state.loading)
        assert(state.message.contains("37 von 37"))

        let preparing = LibraryProgress(stage: "preparing", completed: 0, total: 51375, sequence: 3)
        assert(state.apply(preparing))
        assert(!state.apply(playlists))
        assert(state.message == "Bibliotheksdaten werden vorbereitet …")

        let done = LibraryProgress(stage: "done", completed: 51375, total: 51375, sequence: 4)
        // Recover when the pipe never delivered the final progress message.
        assert(state.apply(LibraryStatus(refreshing: false, progress: done, error: nil)))
        assert(!state.loading)
        assert(state.message == "\(51375.formatted()) Titel geladen")
        assert(!state.apply(playlists))
        assert(!state.loading)

        let opening = LibraryProgress(stage: "opening", completed: 0, total: 0, sequence: 5)
        assert(state.apply(opening))
        assert(!state.apply(LibraryStatus(refreshing: false, progress: done, error: nil)))
        assert(state.loading)

        let indexing = LibraryProgress(stage: "indexing", completed: 1000, total: 51375, sequence: 6)
        assert(state.apply(indexing))
        assert(state.message == "Suchindex aufbauen: \(1000.formatted()) von \(51375.formatted()) Titeln")
        assert(state.apply(LibraryStatus(refreshing: false, progress: indexing, error: nil)))
        assert(!state.loading)
        assert(state.message == "Bibliotheksabgleich beendet.")
        assert(!state.apply(indexing))
        assert(!state.loading)

        let failed = LibraryProgress(stage: "failed", completed: 0, total: 0, sequence: 7)
        let failure = LibraryStatus.Failure(message: "Simulierter Fehler")
        assert(state.apply(LibraryStatus(refreshing: false, progress: failed, error: failure)))
        assert(!state.loading)
        assert(state.message.contains("fehlgeschlagen"))
        state = LibraryProgressState()
        assert(state.apply(LibraryStatus(refreshing: false, progress: nil, error: nil)))
        assert(!state.loading)

        let body = Data(#"{"refreshing":false,"progress":{"stage":"done","completed":51375,"total":51375,"sequence":8},"error":null}"#.utf8)
        let status = try JSONDecoder().decode(LibraryStatus.self, from: body)
        assert(state.apply(status))
        assert(state.sequence == 8)
        assert(!state.loading)

        let diagnosticsBody = Data(#"{"refreshing":true,"progress":{"stage":"native-cleanup","completed":0,"total":51375,"sequence":9,"elapsedSeconds":91,"stageElapsedSeconds":45,"idleSeconds":35},"error":null}"#.utf8)
        let diagnosticStatus = try JSONDecoder().decode(LibraryStatus.self, from: diagnosticsBody)
        assert(state.apply(diagnosticStatus))
        assert(state.message == "Native Bibliotheksobjekte werden aufgeräumt …")
        assert(state.diagnosticText().contains("Gesamt: 1 min 31 s"))
        assert(state.diagnosticText().contains("Schritt: 45 s"))
        assert(state.diagnosticText().contains("Importprotokoll"))
        let later = state.diagnosticText(at: Date().addingTimeInterval(10))
        assert(later.contains("Gesamt: 1 min 41 s"))
        assert(later.contains("Schritt: 55 s"))
    }
}
