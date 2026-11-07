import SwiftUI
import ReplayKit

/// Prototype host screen. Add to the main iOS app target, not the extension.
/// Set your real App Group and extension bundle identifier before building.
struct ScannerView: View {
    private let appGroup = "group.example.lastzscanner"
    private let broadcastExtensionBundleID = "com.example.LastZBroadcast"

    @State private var endpoint = ""
    @State private var accessToken = ""
    @State private var stateNumber = "406"
    @State private var info = "방송을 시작한 뒤 Last Z로 이동하세요."
    @State private var events: [ScannerEvent] = []

    var body: some View {
        NavigationStack {
            Form {
                Section("실시간 화면 연결") {
                    TextField("HTTPS 서버 주소 (예: https://scanner.example.com)", text: $endpoint)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    SecureField("스캐너 접속 토큰", text: $accessToken)
                    TextField("현재 서버 번호", text: $stateNumber)
                        .keyboardType(.numberPad)
                    Button("연결 정보 저장") { saveSettings() }
                    BroadcastPicker(extensionID: broadcastExtensionBundleID)
                        .frame(height: 48)
                    Text(info).font(.footnote)
                }
                Section("최근 후보 (실제 탐지 서버 연결 필요)") {
                    Button("결과 새로고침") {
                        Task { await refreshEvents() }
                    }
                    ForEach(events) { event in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(event.kind == "yellow_truck_candidate" ? "노란 트럭 후보" : event.kind)
                                .font(.headline)
                            Text("서버 \(event.state) · \(event.detectedAt)")
                                .font(.caption)
                            Text("추가 검증 전 후보 — S급 확정 아님")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                Section {
                    Text("게임 조작과 DM 발송은 자동으로 수행하지 않습니다. 화면 공유는 iOS가 제공하는 방식으로 직접 시작/종료합니다.")
                        .font(.footnote)
                }
            }
            .navigationTitle("Last Z Scanner")
        }
        .onAppear {
            let defaults = UserDefaults(suiteName: appGroup)
            endpoint = defaults?.string(forKey: "endpoint") ?? ""
            stateNumber = defaults?.string(forKey: "state") ?? "406"
        }
    }

    private func saveSettings() {
        guard endpoint.hasPrefix("https://"), URL(string: endpoint) != nil else {
            info = "HTTPS 주소를 입력하세요."
            return
        }
        guard !accessToken.isEmpty else {
            info = "접속 토큰을 입력하세요."
            return
        }
        let defaults = UserDefaults(suiteName: appGroup)
        defaults?.set(endpoint.trimmingCharacters(in: CharacterSet(charactersIn: "/")), forKey: "endpoint")
        defaults?.set(accessToken, forKey: "token")
        defaults?.set(stateNumber, forKey: "state")
        info = "설정을 저장했습니다. 방송 버튼에서 화면 공유를 시작하세요."
    }

    @MainActor private func refreshEvents() async {
        let saved = UserDefaults(suiteName: appGroup)
        guard let base = saved?.string(forKey: "endpoint"),
              let token = saved?.string(forKey: "token"),
              let url = URL(string: base + "/v1/events") else {
            info = "먼저 연결 정보를 저장하세요."
            return
        }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            events = try JSONDecoder().decode(EventsResponse.self, from: data).events
            info = "최근 탐지 후보 갱신 완료"
        } catch {
            info = "결과 수신 실패: \(error.localizedDescription)"
        }
    }
}

private struct EventsResponse: Decodable {
    let events: [ScannerEvent]
}

private struct ScannerEvent: Decodable, Identifiable {
    let id: String
    let kind: String
    let state: String
    let detectedAt: String
}

private struct BroadcastPicker: UIViewRepresentable {
    let extensionID: String

    func makeUIView(context: Context) -> RPSystemBroadcastPickerView {
        let view = RPSystemBroadcastPickerView(frame: .zero)
        view.preferredExtension = extensionID
        view.showsMicrophoneButton = false
        return view
    }
    func updateUIView(_ uiView: RPSystemBroadcastPickerView, context: Context) {}
}
