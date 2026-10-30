import AppKit
import Combine
import Foundation
import Security
import SwiftUI

struct PermissionEntry: Decodable {
    let status: String
    let message: String
}

struct PermissionResult: Decodable {
    let media: PermissionEntry
    let automation: PermissionEntry
    let needsSettings: Bool
    let libraryError: PermissionFailure?
}

struct PermissionFailure: Decodable {
    let message: String
}

@MainActor
final class ServiceController: ObservableObject {
    static let shared = ServiceController()

    @Published var running = false
    @Published var starting = false
    @Published var error: String?
    @Published var demo = CommandLine.arguments.contains("--demo")
    @Published var opening = false
    @Published var networkURLs: [URL] = []
    @Published var networkMessage = ""
    @Published private(set) var webPassword = ""
    @Published var passwordVisible = false
    @Published var passwordMessage = ""
    @Published var requestingPermissions = false
    @Published var loadingLibrary = false
    @Published var libraryProgress = ""
    @Published var permissionResult: PermissionResult?
    @Published var requestPermissionsOnLaunch = (UserDefaults.standard.object(forKey: "requestPermissionsOnLaunch") as? Bool) ?? true {
        didSet { UserDefaults.standard.set(requestPermissionsOnLaunch, forKey: "requestPermissionsOnLaunch") }
    }
    private var process: Process?
    private var port: Int?
    private var hostKey = ""
    private var outputBuffer = ""
    private var generation = UUID()
    private var logHandle: FileHandle?
    private var statusTask: Task<Void, Never>?
    private var importProgress = LibraryProgressState()
    private var importLogURL: URL?
    private var lastStatusContact: Date?
    private var statusPollingStartedAt: Date?
    private var nativeSampleProcess: Process?
    private var lastNativeSampleAt: Date?
    @Published var nativeDiagnostic = ""

    var stateLabel: String {
        if starting { return "Dienst wird gestartet …" }
        if requestingPermissions { return "Berechtigungen werden angefragt …" }
        if loadingLibrary { return "Bibliothek wird im Hintergrund aktualisiert …" }
        return running ? (networkURLs.isEmpty ? "Bereit · Nur dieser Mac" : "Bereit · Lokales Netzwerk") : "Dienst beendet"
    }

    func start() {
        guard process == nil else { return }
        starting = true
        running = false
        error = nil
        port = nil
        opening = false
        networkURLs = []
        networkMessage = ""
        webPassword = ""
        passwordVisible = false
        passwordMessage = ""
        outputBuffer = ""
        importProgress = LibraryProgressState()
        lastStatusContact = nil
        statusPollingStartedAt = nil
        lastNativeSampleAt = nil
        nativeDiagnostic = ""
        let current = UUID()
        generation = current
        do {
            let executable = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/iTunesRemoteService.app/Contents/MacOS/iTunesRemoteService")
            guard FileManager.default.isExecutableFile(atPath: executable.path) else { throw HostError.serviceMissing }
            let support: URL
            if let override = ProcessInfo.processInfo.environment["ITUNESREMOTE_DATA_DIR"] {
                support = URL(fileURLWithPath: override, isDirectory: true)
            } else {
                support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
                    .appendingPathComponent("iTunesRemote", isDirectory: true)
            }
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            importLogURL = support.appendingPathComponent("import.log")
            var random = [UInt8](repeating: 0, count: 32)
            guard SecRandomCopyBytes(kSecRandomDefault, random.count, &random) == errSecSuccess else { throw HostError.random }
            hostKey = Data(random).base64EncodedString()
            let task = Process()
            task.executableURL = executable
            task.arguments = ["--data-dir", support.path, "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)] + (demo ? ["--demo"] : [])
            var environment = ProcessInfo.processInfo.environment
            environment["ITUNESREMOTE_HOST_KEY"] = hostKey
            environment["PYTHONUNBUFFERED"] = "1"
            environment["NO_PROXY"] = "127.0.0.1,localhost"
            environment["ITUNESREMOTE_APP_BUILD"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "development"
            task.environment = environment
            let output = Pipe()
            task.standardOutput = output
            let log = support.appendingPathComponent("service.log")
            FileManager.default.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600])
            logHandle = try FileHandle(forWritingTo: log)
            task.standardError = logHandle
            output.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard !data.isEmpty, let chunk = String(data: data, encoding: .utf8) else { return }
                Task { @MainActor in self?.receive(chunk, generation: current) }
            }
            task.terminationHandler = { [weak self] task in
                Task { @MainActor in
                    guard let self, self.generation == current else { return }
                    output.fileHandleForReading.readabilityHandler = nil
                    self.process = nil
                    self.running = false
                    self.starting = false
                    self.port = nil
                    self.networkURLs = []
                    self.networkMessage = ""
                    self.webPassword = ""
                    self.passwordVisible = false
                    self.passwordMessage = ""
                    self.requestingPermissions = false
                    self.loadingLibrary = false
                    self.statusTask?.cancel()
                    self.statusTask = nil
                    if task.terminationStatus != 0 && self.error == nil {
                        self.error = "Der Bibliotheksdienst wurde beendet. Du kannst ihn neu starten. Details stehen in service.log."
                    }
                }
            }
            process = task
            try task.run()
            Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(25))
                guard let self, self.generation == current, self.starting else { return }
                self.stop()
                self.error = "Der Dienst konnte nicht rechtzeitig gestartet werden. Bitte starte ihn erneut."
            }
        } catch {
            process = nil
            starting = false
            self.error = error.localizedDescription
        }
    }

    private func receive(_ chunk: String, generation current: UUID) {
        guard current == generation else { return }
        outputBuffer += chunk
        while let range = outputBuffer.range(of: "\n") {
            let line = String(outputBuffer[..<range.lowerBound])
            outputBuffer.removeSubrange(...range.lowerBound)
            guard let data = line.data(using: .utf8),
                  let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            if event["event"] as? String == "startup-error", let message = event["message"] as? String {
                error = message
                starting = false
                continue
            }
            if event["event"] as? String == "library-progress" {
                if let progress = try? JSONDecoder().decode(LibraryProgress.self, from: data),
                   importProgress.apply(progress) {
                    loadingLibrary = importProgress.loading
                    libraryProgress = importProgress.message
                }
                continue
            }
            guard event["event"] as? String == "ready", let port = event["port"] as? Int,
                  (1...65535).contains(port) else { continue }
            self.port = port
            networkURLs = (event["networkUrls"] as? [String] ?? []).compactMap { URL(string: $0) }
            starting = false
            running = true
            Task {
                do { try await loadWebPassword(generation: current) }
                catch {
                    if self.generation == current { self.passwordMessage = "Das Webpasswort konnte nicht geladen werden. Bitte starte den Dienst erneut." }
                }
            }
            startStatusUpdates(generation: current)
            if (requestPermissionsOnLaunch && !demo) || CommandLine.arguments.contains("--request-permissions") {
                requestPermissions(openAfterwards: true)
            } else if !demo {
                loadLibrary(openAfterwards: true)
            } else {
                openBrowser()
            }
        }
    }

    private func startStatusUpdates(generation current: UUID) {
        guard let port else { return }
        statusTask?.cancel()
        statusPollingStartedAt = Date()
        let key = hostKey
        statusTask = Task { [weak self] in
            let configuration = URLSessionConfiguration.ephemeral
            configuration.connectionProxyDictionary = [:]
            let session = URLSession(configuration: configuration)
            defer { session.invalidateAndCancel() }
            while !Task.isCancelled {
                do {
                    var request = URLRequest(url: URL(string: "http://127.0.0.1:\(port)/api/v1/status")!)
                    request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
                    request.timeoutInterval = 5
                    let (data, response) = try await session.data(for: request)
                    guard let self, self.generation == current, !Task.isCancelled else { return }
                    self.lastStatusContact = Date()
                    if (response as? HTTPURLResponse)?.statusCode == 200 {
                        let status = try JSONDecoder().decode(LibraryStatus.self, from: data)
                        if self.importProgress.apply(status) {
                            self.loadingLibrary = self.importProgress.loading
                            self.libraryProgress = self.importProgress.message
                            if let failure = status.error { self.error = failure.message }
                        }
                    }
                } catch {
                    if Task.isCancelled { return }
                    // A transient HTTP failure must not mark an unfinished import as complete.
                }
                guard let self, self.generation == current, !Task.isCancelled else { return }
                self.captureUnresponsiveService(generation: current)
                do { try await Task.sleep(for: .seconds(2)) }
                catch { return }
            }
        }
    }

    func importDiagnostics(at date: Date) -> String {
        var detail = importProgress.diagnosticText(at: date)
        if loadingLibrary || importProgress.loading, let contact = lastStatusContact ?? statusPollingStartedAt, date.timeIntervalSince(contact) >= 10 {
            detail += "\nSeit \(Int(date.timeIntervalSince(contact))) s keine Antwort des Dienstes."
        }
        if !nativeDiagnostic.isEmpty { detail += "\n" + nativeDiagnostic }
        return detail
    }

    func openImportLog() {
        guard let url = importLogURL, FileManager.default.fileExists(atPath: url.path) else { return }
        NSWorkspace.shared.open(url.deletingLastPathComponent())
    }

    private func captureUnresponsiveService(generation current: UUID) {
        let date = Date()
        guard loadingLibrary || importProgress.loading,
              let contact = lastStatusContact ?? statusPollingStartedAt,
              date.timeIntervalSince(contact) >= 15,
              lastNativeSampleAt.map({ date.timeIntervalSince($0) >= 60 }) ?? true,
              nativeSampleProcess == nil, let child = process, child.isRunning,
              let folder = importLogURL?.deletingLastPathComponent() else { return }
        lastNativeSampleAt = date
        let report = folder.appendingPathComponent("import-native.sample.txt")
        let messages = folder.appendingPathComponent("import-native.log")
        for file in [report, messages] {
            FileManager.default.createFile(atPath: file.path, contents: nil, attributes: [.posixPermissions: 0o600])
        }
        do {
            let log = try FileHandle(forWritingTo: messages)
            let sample = Process()
            sample.executableURL = URL(fileURLWithPath: "/usr/bin/sample")
            // Sample only our own helper, never Music or another user process.
            sample.arguments = [String(child.processIdentifier), "2", "10", "-file", report.path]
            sample.standardOutput = log
            sample.standardError = log
            sample.terminationHandler = { [weak self] result in
                Task { @MainActor in
                    log.closeFile()
                    try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: report.path)
                    guard let self, self.generation == current else { return }
                    self.nativeSampleProcess = nil
                    self.nativeDiagnostic = result.terminationStatus == 0
                        ? "Native Diagnose erstellt. Sie liegt im Protokollordner."
                        : "Native Diagnose nicht verfügbar. Details stehen in import-native.log."
                }
            }
            do { try sample.run() }
            catch { log.closeFile(); throw error }
            nativeSampleProcess = sample
            nativeDiagnostic = "Native Diagnose des Dienstes wird erstellt …"
        } catch {
            nativeDiagnostic = "Die native Diagnose konnte nicht gestartet werden."
        }
    }

    private func loadWebPassword(generation current: UUID) async throws {
        guard let port else { throw HostError.browser }
        let local = URL(string: "http://127.0.0.1:\(port)")!
        var request = URLRequest(url: local.appendingPathComponent("api/v1/auth/password"))
        request.setValue("Bearer \(hostKey)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 10
        let configuration = URLSessionConfiguration.ephemeral
        configuration.connectionProxyDictionary = [:]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let (data, response) = try await session.data(for: request)
        guard self.generation == current,
              (response as? HTTPURLResponse)?.statusCode == 200,
              let result = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let password = result["password"] as? String, !password.isEmpty else { throw HostError.browser }
        webPassword = password
    }

    func copyNetworkAddress(_ url: URL) {
        guard running, networkURLs.contains(url) else { return }
        NSPasteboard.general.clearContents()
        networkMessage = NSPasteboard.general.setString(url.absoluteString, forType: .string)
            ? "Netzwerkadresse kopiert. Auf dem anderen Gerät öffnen und mit dem Webpasswort anmelden."
            : "Die Netzwerkadresse konnte nicht kopiert werden."
    }

    func copyWebPassword() {
        guard running, !webPassword.isEmpty else { return }
        NSPasteboard.general.clearContents()
        passwordMessage = NSPasteboard.general.setString(webPassword, forType: .string)
            ? "Webpasswort kopiert."
            : "Das Webpasswort konnte nicht kopiert werden."
    }

    func openBrowser() {
        guard let port, running, !opening, !requestingPermissions else { return }
        opening = true
        let current = generation
        Task {
            defer { if self.generation == current { opening = false } }
            do {
                try await loadWebPassword(generation: current)
                let url = URL(string: "http://127.0.0.1:\(port)/")!
                if CommandLine.arguments.contains("--no-browser") {
                    // Exercise authenticated password retrieval without opening a user tab.
                    // Never print the password or the private host key.
                    print("{\"event\":\"ready\",\"port\":\(port),\"permissionCheck\":\(self.permissionResult != nil),\"passwordAvailable\":\(!webPassword.isEmpty)}")
                    fflush(stdout)
                } else if !NSWorkspace.shared.open(url) {
                    throw HostError.browser
                }
            } catch {
                guard self.generation == current else { return }
                self.error = "Die Weboberfläche konnte nicht geöffnet werden. Bitte versuche es erneut."
            }
        }
    }

    func requestPermissions(openAfterwards: Bool = false) {
        guard let port, running, !requestingPermissions, !loadingLibrary else { return }
        requestingPermissions = true
        permissionResult = nil
        error = nil
        let current = generation
        Task {
            defer { if self.generation == current { self.requestingPermissions = false } }
            do {
                let base = URL(string: "http://127.0.0.1:\(port)")!
                var request = URLRequest(url: base.appendingPathComponent("api/v1/permissions/request"))
                request.httpMethod = "POST"
                request.httpBody = Data("{}".utf8)
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("Bearer \(hostKey)", forHTTPHeaderField: "Authorization")
                // The system may wait for a consent dialog. The UI stays responsive.
                request.timeoutInterval = 330
                let configuration = URLSessionConfiguration.ephemeral
                configuration.connectionProxyDictionary = [:]
                let session = URLSession(configuration: configuration)
                defer { session.invalidateAndCancel() }
                let (data, response) = try await session.data(for: request)
                guard self.generation == current else { return }
                if (response as? HTTPURLResponse)?.statusCode == 200 {
                    permissionResult = try JSONDecoder().decode(PermissionResult.self, from: data)
                    if let failure = permissionResult?.libraryError { error = failure.message }
                } else {
                    let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                    let failure = result?["error"] as? [String: Any]
                    error = failure?["message"] as? String ?? "Die Berechtigungen konnten nicht geprüft werden. Bitte prüfe die Datenschutzeinstellungen."
                }
            } catch {
                guard self.generation == current else { return }
                self.error = "Die Berechtigungsabfrage hat noch keine Antwort geliefert. Bitte prüfe offene macOS-Dialoge und versuche es danach erneut."
            }
            guard self.generation == current else { return }
            requestingPermissions = false
            if openAfterwards {
                if permissionResult?.media.status == "granted" { loadLibrary(openAfterwards: true) }
                else { openBrowser() }
            }
        }
    }

    func loadLibrary(openAfterwards: Bool) {
        guard let port, running, !loadingLibrary else { return }
        loadingLibrary = true
        libraryProgress = "Musikbibliothek wird geöffnet …"
        let current = generation
        Task {
            do {
                var request = URLRequest(url: URL(string: "http://127.0.0.1:\(port)/api/v1/library/refresh")!)
                request.httpMethod = "POST"
                request.httpBody = Data("{\"background\":true}".utf8)
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("Bearer \(hostKey)", forHTTPHeaderField: "Authorization")
                request.timeoutInterval = 25
                let config = URLSessionConfiguration.ephemeral
                config.connectionProxyDictionary = [:]
                let session = URLSession(configuration: config)
                defer { session.invalidateAndCancel() }
                let (data, response) = try await session.data(for: request)
                guard self.generation == current else { return }
                if (response as? HTTPURLResponse)?.statusCode != 200 {
                    loadingLibrary = false
                    let envelope = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                    error = (envelope?["error"] as? [String: Any])?["message"] as? String ?? "Die Bibliothek konnte nicht geladen werden."
                }
            } catch {
                guard self.generation == current else { return }
                loadingLibrary = false
                self.error = "Das Einlesen wurde noch nicht bestätigt. Bitte prüfe den Fortschritt und versuche es bei Bedarf erneut."
            }
            guard self.generation == current else { return }
            if openAfterwards { openBrowser() }
        }
    }

    func restart(demo: Bool? = nil) {
        guard !starting else { return }
        let previous = process
        stop()
        if let demo { self.demo = demo }
        guard let previous, previous.isRunning else { start(); return }
        starting = true
        let current = generation
        Task {
            let deadline = Date().addingTimeInterval(10)
            while previous.isRunning {
                guard generation == current else { return }
                if Date() >= deadline {
                    process = previous
                    starting = false
                    error = "Der bisherige Dienst beendet sich noch. Bitte versuche den Neustart erneut."
                    return
                }
                try? await Task.sleep(for: .milliseconds(100))
            }
            guard generation == current else { return }
            starting = false
            start()
        }
    }

    func stop() {
        generation = UUID()
        statusTask?.cancel()
        statusTask = nil
        if nativeSampleProcess?.isRunning == true { nativeSampleProcess?.terminate() }
        nativeSampleProcess = nil
        let task = process
        process = nil
        if task?.isRunning == true { task?.terminate() }
        logHandle?.closeFile()
        logHandle = nil
        running = false
        starting = false
        port = nil
        opening = false
        networkURLs = []
        networkMessage = ""
        webPassword = ""
        passwordVisible = false
        passwordMessage = ""
        requestingPermissions = false
        permissionResult = nil
        loadingLibrary = false
        libraryProgress = ""
    }

    func permissions() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Media") {
            NSWorkspace.shared.open(url)
        }
    }

    func automationSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
            NSWorkspace.shared.open(url)
        }
    }

    enum HostError: LocalizedError {
        case resources, serviceMissing, random, browser
        var errorDescription: String? {
            switch self {
            case .resources, .serviceMissing: return "Der gebündelte Dienst fehlt. Bitte baue oder installiere die App erneut."
            case .random: return "Ein sicherer Startschlüssel konnte nicht erzeugt werden."
            case .browser: return "Die Weboberfläche konnte nicht geöffnet werden."
            }
        }
    }
}

@MainActor
final class ApplicationDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationWillTerminate(_ notification: Notification) { ServiceController.shared.stop() }
}

struct Dashboard: View {
    @ObservedObject var service: ServiceController
    private let accent = Color(red: 0.60, green: 0.24, blue: 0.30)

    var body: some View {
        ScrollView {
        VStack(spacing: 0) {
            ZStack {
                RoundedRectangle(cornerRadius: 21).fill(accent.gradient).frame(width: 78, height: 78)
                Image(systemName: "music.note").font(.system(size: 39, weight: .medium)).foregroundStyle(.white)
            }.padding(.bottom, 23)
            Text("iTunesRemote").font(.system(size: 29, weight: .semibold, design: .rounded))
            Text("Deine Musik. Deine Sterne.").foregroundStyle(.secondary).padding(.top, 7)
            HStack(spacing: 7) {
                if service.starting || service.requestingPermissions || service.loadingLibrary { ProgressView().controlSize(.small) }
                else { Circle().fill(service.running ? Color.green : Color.secondary).frame(width: 6, height: 6) }
                Text(service.stateLabel).font(.system(size: 12))
            }.padding(.top, 25)
            if !service.libraryProgress.isEmpty {
                Text(service.libraryProgress).font(.system(size: 11)).foregroundStyle(.secondary).padding(.top, 7)
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    let detail = service.importDiagnostics(at: context.date)
                    if !detail.isEmpty {
                        Text(detail).font(.system(size: 10)).monospacedDigit().foregroundStyle(.secondary)
                            .multilineTextAlignment(.center).padding(.top, 5)
                    }
                }
            }
            Button("Diagnoseprotokolle öffnen", action: service.openImportLog)
                .buttonStyle(.link).font(.system(size: 11)).disabled(!service.running).padding(.top, 9)
            Text("Build \(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?")")
                .font(.system(size: 10)).foregroundStyle(.secondary).padding(.top, 4)
            if let error = service.error {
                Text(error).font(.system(size: 12)).foregroundStyle(.red).multilineTextAlignment(.center).padding(.top, 14)
            }
            Button(action: service.openBrowser) {
                Label("Weboberfläche öffnen", systemImage: "arrow.up.forward.app")
                    .frame(maxWidth: .infinity).padding(.vertical, 7)
            }.buttonStyle(.borderedProminent).tint(accent).disabled(!service.running || service.opening || service.requestingPermissions).padding(.top, 25)
            if !service.networkURLs.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Lokales Netzwerk", systemImage: "network").font(.system(size: 12, weight: .semibold))
                    ForEach(service.networkURLs, id: \.absoluteString) { url in
                        Text(url.absoluteString).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                        Button("Netzwerkadresse kopieren") { service.copyNetworkAddress(url) }
                    }
                    Text(service.networkMessage.isEmpty ? "Adresse auf einem Gerät im selben WLAN oder LAN öffnen und mit dem Webpasswort anmelden." : service.networkMessage)
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                    Text("HTTP · Verbindung unverschlüsselt").font(.system(size: 10)).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(.top, 18)
            }
            VStack(alignment: .leading, spacing: 8) {
                Label("Webpasswort", systemImage: "key").font(.system(size: 12, weight: .semibold))
                Text(service.webPassword.isEmpty ? "Wird geladen …" : service.passwordVisible ? service.webPassword : String(repeating: "•", count: 24))
                    .font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                HStack {
                    Button(service.passwordVisible ? "Passwort verbergen" : "Passwort anzeigen") { service.passwordVisible.toggle() }
                    Button("Passwort kopieren", action: service.copyWebPassword)
                }.disabled(service.webPassword.isEmpty)
                Text(service.passwordMessage.isEmpty ? "Einmal erzeugt. Bleibt bei Neustarts und App-Updates gleich." : service.passwordMessage)
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(.top, 18)
            Button { service.requestPermissions() } label: {
                Label("Berechtigungen anfordern", systemImage: "hand.raised")
                    .frame(maxWidth: .infinity).padding(.vertical, 5)
            }.buttonStyle(.bordered).disabled(!service.running || service.requestingPermissions || service.loadingLibrary).padding(.top, 10)
            Toggle("Berechtigungen beim Öffnen anfordern", isOn: $service.requestPermissionsOnLaunch)
                .font(.system(size: 11)).padding(.top, 15)
            if let result = service.permissionResult {
                VStack(alignment: .leading, spacing: 7) {
                    Label(result.media.message, systemImage: result.media.status == "granted" ? "checkmark.circle" : "info.circle")
                    Label(result.automation.message, systemImage: result.automation.status == "granted" ? "checkmark.circle" : "info.circle")
                    if result.needsSettings {
                        Text("Nach einer Ablehnung kannst du die Freigabe in den Datenschutzeinstellungen ändern.")
                            .foregroundStyle(.secondary)
                    }
                }.font(.system(size: 11)).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 14)
            }
            HStack {
                Menu("Datenschutzeinstellungen") {
                    Button("Medien & Apple Music", action: service.permissions)
                    Button("Automation für Musik", action: service.automationSettings)
                }
                Spacer()
                Button("Dienst neu starten") { service.restart() }.disabled(service.starting || service.requestingPermissions)
            }.buttonStyle(.link).font(.system(size: 11)).padding(.top, 16)
            Divider().padding(.top, 25)
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "lock.shield").font(.system(size: 17))
                Text("Die Bibliothek bleibt auf deinem Mac. Weitere Geräte melden sich mit deinem Webpasswort im lokalen Netzwerk an. Die Mac-App muss dabei geöffnet bleiben.")
                    .font(.system(size: 11)).lineSpacing(3)
            }.foregroundStyle(.secondary).padding(.top, 20)
        }
        .padding(38)
        .frame(maxWidth: .infinity)
        }
        .frame(width: 430, height: 640)
        .onAppear { service.start() }
    }
}

@main
struct ITunesRemoteApp: App {
    @NSApplicationDelegateAdaptor(ApplicationDelegate.self) var delegate
    @StateObject private var service = ServiceController.shared

    var body: some Scene {
        WindowGroup("iTunesRemote") { Dashboard(service: service) }
            .windowResizability(.contentSize)
            .commands {
                CommandGroup(replacing: .newItem) {
                    Button("Weboberfläche öffnen", action: service.openBrowser).keyboardShortcut("o").disabled(!service.running || service.requestingPermissions)
                }
            }
        MenuBarExtra("iTunesRemote", systemImage: "music.note") {
            Text(service.stateLabel)
            Button("Weboberfläche öffnen", action: service.openBrowser).disabled(!service.running || service.requestingPermissions)
            if !service.networkURLs.isEmpty {
                Menu("Netzwerkadresse kopieren") {
                    ForEach(service.networkURLs, id: \.absoluteString) { url in
                        Button(url.absoluteString) { service.copyNetworkAddress(url) }
                    }
                }
            }
            Button("Webpasswort kopieren", action: service.copyWebPassword).disabled(service.webPassword.isEmpty)
            Divider()
            Button("Berechtigungen anfordern") { service.requestPermissions() }.disabled(!service.running || service.requestingPermissions)
            Toggle("Berechtigungen beim Öffnen anfordern", isOn: $service.requestPermissionsOnLaunch)
            Menu("Datenschutzeinstellungen öffnen") {
                Button("Medien & Apple Music", action: service.permissions)
                Button("Automation für Musik", action: service.automationSettings)
            }
            Button("Dienst neu starten") { service.restart() }.disabled(service.starting || service.requestingPermissions)
            Button("Mit Demodaten neu starten") { service.restart(demo: true) }.disabled(service.starting || service.requestingPermissions)
            Button("Mit Musikbibliothek neu starten") { service.restart(demo: false) }.disabled(service.starting || service.requestingPermissions)
            Divider()
            Button("iTunesRemote beenden") { NSApplication.shared.terminate(nil) }.keyboardShortcut("q")
        }
    }
}
