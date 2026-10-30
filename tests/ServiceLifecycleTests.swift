import Foundation

@main
struct ServiceLifecycleTests {
    @MainActor
    static func main() async throws {
        let service = ServiceController()
        service.requestPermissionsOnLaunch = false
        defer {
            service.stop()
            if let identifier = Bundle.main.bundleIdentifier {
                UserDefaults.standard.removePersistentDomain(forName: identifier)
            }
        }

        func waitUntilReady() async throws {
            let deadline = Date().addingTimeInterval(10)
            while !service.running || service.starting {
                assert(service.error == nil, service.error ?? "Unexpected startup error")
                assert(Date() < deadline, "Service did not become ready")
                try await Task.sleep(for: .milliseconds(50))
            }
        }

        service.start()
        try await waitUntilReady()
        let addresses = service.networkURLs
        assert(addresses.count == 1)
        service.restart()
        try await waitUntilReady()
        assert(service.error == nil)
        assert(service.networkURLs == addresses, "A restart changed the fixed port")
        let data = URL(fileURLWithPath: ProcessInfo.processInfo.environment["ITUNESREMOTE_DATA_DIR"]!)
        let launches = try String(contentsOf: data.appendingPathComponent("launches"), encoding: .utf8)
            .split(separator: "\n")
        assert(launches.count == 2, "Expected exactly two service instances")
        assert(launches[0] != launches[1])
        service.stop()
        try await Task.sleep(for: .seconds(1))
    }
}
