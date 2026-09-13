// JudgmentOverlay.swift -- fullscreen judge-facing HUD for SFS AI.
//
// Runs a small local TCP listener (127.0.0.1:47822 by default) and
// renders whatever OverlayState JSON arrives, newline-delimited, from
// pilot_loop.py's overlay_state.py client. Runs as a borderless,
// click-through, always-on-top panel that stays visible even when
// Spaceflight Simulator is running in true macOS fullscreen (its own
// Space) -- the .fullScreenAuxiliary collection behavior below is what
// makes that possible; without it this window would just vanish the
// moment the game goes fullscreen.
//
// 2026-09-13 LATER SAME DAY: switched from polling a JSON file on disk
// to being a TCP server the Python side pushes to directly (Christian's
// explicit request -- file I/O polling adds lag, same reasoning as this
// project's own TCP rewrite for game commands, ~9x faster than the old
// file-protocol). This app is the long-lived side across a whole demo
// session, so it makes sense for it to be the listener; pilot_loop.py
// connects as a client fresh each flight.
//
// Single-file, no Xcode project needed -- build with:
//   swiftc -O JudgmentOverlay.swift -o JudgmentOverlay
// Run with (defaults to port 47822 and the LAST screen in
// NSScreen.screens if no argument given):
//   ./JudgmentOverlay [--port N] [--screen N]

import SwiftUI
import AppKit
import CoreGraphics
import Network
import Combine

// MARK: - Data model (mirrors overlay_state.py's JSON output exactly)

struct OverlayOption: Codable, Identifiable {
    var id: String { label }
    let label: String
    let value: Double
}

struct Judgment: Codable, Identifiable {
    var id: String { name }
    let name: String
    let label: String
    let question: String
    let options: [OverlayOption]
    let chosen: String?
    let confidence: Double
    let accepted: Bool
    let band: String
    let reason: String?
    let relevant: Bool
    let threshold: Double
}

struct Commanded: Codable {
    let throttle: Double
    let turn_axis: Double
}

struct OverlayState: Codable {
    let status: String
    let cycle_id: Int?
    let t: Double?
    let phase: String?
    let commanded: Commanded?
    let watchdog_tag: String?
    let judgments: [Judgment]?
    let written_at: Double?
}

// MARK: - TCP server

/// Accepts connections on 127.0.0.1:port and parses newline-delimited
/// JSON (NDJSON) OverlayState objects out of whatever arrives, calling
/// `onState` on the main queue for each one. Multiple sequential
/// connections are fine (a new `pilot_loop.py` process each flight) --
/// each gets its own receive loop and buffer.
final class OverlayTCPServer {
    private var listener: NWListener?
    private let port: NWEndpoint.Port
    private let onState: (OverlayState) -> Void
    private let decoder = JSONDecoder()

    init(port: UInt16, onState: @escaping (OverlayState) -> Void) {
        self.port = NWEndpoint.Port(rawValue: port)!
        self.onState = onState
        start()
    }

    private func start() {
        do {
            let params = NWParameters.tcp
            let l = try NWListener(using: params, on: port)
            l.newConnectionHandler = { [weak self] connection in
                self?.handle(connection)
            }
            l.stateUpdateHandler = { state in
                fputs("JudgmentOverlay: TCP listener state: \(state)\n", stderr)
            }
            l.start(queue: .main)
            listener = l
            fputs("JudgmentOverlay: TCP listening on 127.0.0.1:\(port)\n", stderr)
        } catch {
            fputs("JudgmentOverlay: failed to start TCP listener: \(error)\n", stderr)
        }
    }

    private func handle(_ connection: NWConnection) {
        connection.stateUpdateHandler = { state in
            if case .failed = state { connection.cancel() }
        }
        connection.start(queue: .main)
        receive(on: connection, buffer: Data())
    }

    private func receive(on connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            guard let self = self else { return }
            var buf = buffer
            if let data = data, !data.isEmpty {
                buf.append(data)
                // NDJSON -- split on newline, decode each complete line.
                while let nlRange = buf.range(of: Data([0x0A])) {
                    let line = buf.subdata(in: buf.startIndex..<nlRange.lowerBound)
                    buf.removeSubrange(buf.startIndex..<nlRange.upperBound)
                    if let decoded = try? self.decoder.decode(OverlayState.self, from: line) {
                        self.onState(decoded)
                    }
                }
            }
            if isComplete || error != nil {
                connection.cancel()
                return
            }
            self.receive(on: connection, buffer: buf)
        }
    }
}

// MARK: - Store

final class OverlayStateStore: ObservableObject {
    @Published var state: OverlayState?
    @Published var stale: Bool = false

    private var server: OverlayTCPServer?
    private var staleTimer: Timer?

    init(port: UInt16) {
        server = OverlayTCPServer(port: port) { [weak self] newState in
            self?.state = newState
            self?.stale = false
        }
        // Periodic staleness check -- if the last received state gets
        // old (connection dropped mid-flight, process died without a
        // final write), fall back to a visibly "STALE" indicator rather
        // than silently showing frozen data forever.
        staleTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            guard let self = self, let writtenAt = self.state?.written_at else { return }
            self.stale = (Date().timeIntervalSince1970 - writtenAt) > 3.0
        }
    }
}

// MARK: - Palette + scale

let hudGreen = Color(red: 0.35, green: 1.0, blue: 0.45)
let hudDim = Color(red: 0.30, green: 0.55, blue: 0.33)
let hudRed = Color(red: 1.0, green: 0.35, blue: 0.35)
let hudYellow = Color(red: 0.95, green: 0.85, blue: 0.3)

// Overall HUD scale -- Christian's explicit request, 1.5x the original
// size. Applied by scaling every real font/frame/spacing value directly
// (via the s() helper below), NOT via a SwiftUI .scaleEffect() transform
// -- scaleEffect rasterizes the already-laid-out view and stretches the
// bitmap, which is exactly what caused the blurry/glitchy text on the
// first 1.9x attempt. Scaling the real values keeps text crisp because
// it's laid out and rendered at its true final size.
let uiScale: CGFloat = 1.5
func s(_ v: CGFloat) -> CGFloat { v * uiScale }

// MARK: - UI

struct BarRow: View {
    let option: OverlayOption
    let isChosen: Bool

    var body: some View {
        HStack(spacing: s(6)) {
            Text(option.label)
                .font(.system(size: s(10), weight: isChosen ? .bold : .regular, design: .monospaced))
                .foregroundColor(isChosen ? hudGreen : hudDim)
                .frame(width: s(120), alignment: .leading)
                .lineLimit(1)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Rectangle().fill(Color.white.opacity(0.06))
                    Rectangle()
                        .fill(isChosen ? hudGreen : hudDim)
                        .frame(width: max(2, geo.size.width * CGFloat(min(max(option.value, 0), 1))))
                }
            }
            .frame(height: s(9))
            Text(String(format: "%.2f", option.value))
                .font(.system(size: s(9), design: .monospaced))
                .foregroundColor(hudDim)
                .frame(width: s(32), alignment: .trailing)
        }
    }
}

struct JudgmentPanel: View {
    let judgment: Judgment

    var tagColor: Color {
        switch judgment.band {
        case "reject", "miss": return hudRed
        case "caution": return hudYellow
        default: return hudGreen
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: s(4)) {
            HStack {
                Text(judgment.label)
                    .font(.system(size: s(11), weight: .bold, design: .monospaced))
                    .padding(.horizontal, s(6)).padding(.vertical, s(2))
                    .background(tagColor.opacity(0.22))
                    .overlay(RoundedRectangle(cornerRadius: s(3)).stroke(tagColor, lineWidth: 1))
                    .foregroundColor(tagColor)
                if !judgment.relevant {
                    Text("N/A THIS PHASE")
                        .font(.system(size: s(8), weight: .bold, design: .monospaced))
                        .foregroundColor(hudDim)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 0) {
                    Text(judgment.accepted ? "ACCEPT" : "REJECT")
                        .font(.system(size: s(9), weight: .bold, design: .monospaced))
                        .foregroundColor(tagColor)
                    Text(String(format: "confidence %.2f / threshold %.2f", judgment.confidence, judgment.threshold))
                        .font(.system(size: s(8), design: .monospaced))
                        .foregroundColor(hudDim)
                }
            }
            if !judgment.options.isEmpty {
                // Bold always marks the HIGHEST bar, computed directly
                // from the values shown -- not the `chosen` field, which
                // for throttle_score is a rounded continuous score and
                // can legitimately disagree with which bucket actually
                // has the most probability mass (Christian's explicit
                // bug report: bold wasn't always on the tallest bar).
                let highlightLabel = judgment.options.max(by: { $0.value < $1.value })?.label
                ForEach(judgment.options.prefix(6)) { opt in
                    BarRow(option: opt, isChosen: opt.label == highlightLabel)
                }
            } else if let chosen = judgment.chosen {
                Text(chosen)
                    .font(.system(size: s(11), weight: .bold, design: .monospaced))
                    .foregroundColor(hudGreen)
            }
        }
        .padding(s(8))
        .background(Color.black.opacity(0.75))
        .overlay(RoundedRectangle(cornerRadius: s(4)).stroke(Color.white.opacity(0.08)))
        // Grey out (not hide) whichever of LAUNCH/THROTTLE doesn't apply
        // to the current phase -- Christian's explicit request, so
        // judges see the full panel set at all times, not panels
        // popping in/out as phase changes.
        .opacity(judgment.relevant ? 1.0 : 0.4)
        .saturation(judgment.relevant ? 1.0 : 0.3)
    }
}

struct StatusDot: View {
    let active: Bool
    @State private var pulse = false

    var body: some View {
        Circle()
            .fill(active ? hudGreen : Color.gray)
            .frame(width: s(9), height: s(9))
            .opacity(active ? (pulse ? 1.0 : 0.4) : 1.0)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                    pulse = true
                }
            }
    }
}

struct OverlayRootView: View {
    @ObservedObject var store: OverlayStateStore

    var statusLabel: String {
        guard let st = store.state else { return "NO SIGNAL" }
        if store.stale { return "STALE" }
        return st.status == "active" ? "tsAI ACTIVE" : "tsAI ENDED"
    }

    var statusColor: Color {
        guard let st = store.state, !store.stale else { return hudDim }
        return st.status == "active" ? hudGreen : hudDim
    }

    var body: some View {
        VStack(alignment: .leading, spacing: s(8)) {
            HStack(spacing: s(8)) {
                StatusDot(active: store.state?.status == "active" && !store.stale)
                Text(statusLabel)
                    .font(.system(size: s(13), weight: .bold, design: .monospaced))
                    .foregroundColor(statusColor)
                Spacer()
                if let cid = store.state?.cycle_id {
                    Text("CYCLE \(cid)")
                        .font(.system(size: s(11), design: .monospaced))
                        .foregroundColor(hudDim)
                }
            }
            if let phase = store.state?.phase {
                Text("PHASE \(phase)")
                    .font(.system(size: s(10), design: .monospaced))
                    .foregroundColor(hudDim)
            }
            if let cmd = store.state?.commanded {
                Text(String(format: "THROTTLE %.2f   TURN %.2f", cmd.throttle, cmd.turn_axis))
                    .font(.system(size: s(10), design: .monospaced))
                    .foregroundColor(hudDim)
            }
            if let tag = store.state?.watchdog_tag {
                Text("WATCHDOG \(tag)")
                    .font(.system(size: s(10), design: .monospaced))
                    .foregroundColor(tag == "LIVE" ? hudGreen : hudYellow)
            }

            Rectangle().fill(Color.white.opacity(0.12)).frame(height: 1)

            Text("JUDGMENTS")
                .font(.system(size: s(10), weight: .bold, design: .monospaced))
                .foregroundColor(hudDim)

            ForEach(store.state?.judgments ?? []) { j in
                JudgmentPanel(judgment: j)
            }
        }
        .padding(s(12))
        .frame(width: s(420), alignment: .leading)
        .background(Color.black.opacity(0.58))
        .cornerRadius(s(6))
    }
}

// MARK: - App bootstrap (non-activating, joins fullscreen spaces)

final class OverlayPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)  // no Dock icon, never steals focus/Space

let allScreens = NSScreen.screens
for (i, sc) in allScreens.enumerated() {
    fputs("JudgmentOverlay: screen \(i): \(sc.localizedName) frame=\(sc.frame)\n", stderr)
}

// Argument parsing: --port N (TCP listen port, default 47822 --
// matches overlay_state.py's OVERLAY_PORT) and --screen N (see below).
// NSScreen.main tracks whatever screen currently has focus/the key
// window, which is NOT reliably the monitor SFS is running on in a
// multi-monitor setup -- so this never uses NSScreen.main. Default
// heuristic: if there's more than one screen, assume the LAST one in
// NSScreen.screens is the secondary monitor SFS is on (common case);
// pass --screen N to override using the indices printed above.
var screenIndexArg: Int? = nil
var portArg: UInt16? = nil
var cliArgs = Array(CommandLine.arguments.dropFirst())
var argIdx = 0
while argIdx < cliArgs.count {
    if cliArgs[argIdx] == "--screen", argIdx + 1 < cliArgs.count, let idx = Int(cliArgs[argIdx + 1]) {
        screenIndexArg = idx
        argIdx += 2
    } else if cliArgs[argIdx] == "--port", argIdx + 1 < cliArgs.count, let p = UInt16(cliArgs[argIdx + 1]) {
        portArg = p
        argIdx += 2
    } else {
        argIdx += 1
    }
}

let targetScreen: NSScreen
if let idx = screenIndexArg, idx >= 0, idx < allScreens.count {
    targetScreen = allScreens[idx]
} else if allScreens.count > 1 {
    targetScreen = allScreens.last!
} else if let first = allScreens.first {
    targetScreen = first
} else {
    fputs("JudgmentOverlay: no screens found\n", stderr)
    exit(1)
}
fputs("JudgmentOverlay: using screen frame=\(targetScreen.frame)\n", stderr)

// Content is s(420) wide + s(12)*2 padding baked into that frame already
// -- give the window itself real breathing room beyond that so nothing
// clips at the edge.
let contentWidth: CGFloat = s(420)
let panelWidth: CGFloat = contentWidth + s(40)
let panelHeight: CGFloat = targetScreen.frame.height - 80
let originX: CGFloat = targetScreen.frame.origin.x + 24
let originY: CGFloat = targetScreen.frame.origin.y + 40

let panel = OverlayPanel(
    contentRect: NSRect(x: originX, y: originY, width: panelWidth, height: panelHeight),
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered,
    defer: false
)
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = false
// This level + collectionBehavior combination is what lets a small
// utility window stay visible on top of an app running in true macOS
// fullscreen (its own Space) -- without .fullScreenAuxiliary the window
// simply disappears the instant SFS goes fullscreen.
panel.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.maximumWindow)))
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
panel.ignoresMouseEvents = true   // click-through -- never steals game input
panel.isFloatingPanel = true
panel.hidesOnDeactivate = false

let store = OverlayStateStore(port: portArg ?? 47822)
let hosting = NSHostingView(rootView: OverlayRootView(store: store))
hosting.frame = panel.contentView!.bounds
hosting.autoresizingMask = [.width, .height]
panel.contentView = hosting

panel.orderFrontRegardless()
app.run()
