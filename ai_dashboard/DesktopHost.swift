import Cocoa
import WebKit

final class DeskWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}
final class DragArea: NSView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .openHand) }
    override func mouseDown(with event: NSEvent) { window?.performDrag(with: event) }
}
final class Host: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    var window: DeskWindow!
    var web: WKWebView!
    var embedded = !CommandLine.arguments.contains("--foreground")
    var backend: Process?
    var startupLog: URL?
    var startupErrorShown = false
    var pinned = UserDefaults.standard.bool(forKey: "AI Desk Pinned")
    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu(title: "AI Desk")
        appMenu.addItem(withTitle: "AI Desk 종료", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let editItem = NSMenuItem(title: "편집", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "편집")
        for (title, action, key) in [("잘라내기", "cut:", "x"), ("복사", "copy:", "c"), ("붙여넣기", "paste:", "v"), ("모두 선택", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        editItem.submenu = editMenu
        menu.addItem(editItem)
        NSApp.mainMenu = menu
        if let urlText = CommandLine.arguments.dropFirst().first(where: { $0.hasPrefix("http://127.0.0.1:") }), let url = URL(string: urlText) {
            createWindow(url: url, foreground: CommandLine.arguments.contains("--foreground"))
        } else { startBackend() }
    }
    func createWindow(url: URL, foreground: Bool) {
        embedded = !foreground
        let screen = NSScreen.main!.visibleFrame
        let width = min(1160.0, screen.width - 100)
        let height = min(770.0, screen.height - 80)
        let frame = NSRect(x: screen.midX-width/2, y: screen.midY-height/2, width: width, height: height)
        window = DeskWindow(contentRect: frame, styleMask: [.borderless, .resizable], backing: .buffered, defer: false)
        window.title = "AI Desk · Desktop"
        window.minSize = NSSize(width: min(960, screen.width - 40), height: min(620, screen.height - 40))
        window.setFrameUsingName("AI Desk Desktop")
        // Saved monitor positions can be outside a different Mac's display.
        let target = NSScreen.screens.first(where: { $0.visibleFrame.intersects(window.frame) })?.visibleFrame ?? screen
        window.minSize = NSSize(width: min(960, target.width - 24), height: min(620, target.height - 24))
        var restored = window.frame
        restored.size.width = min(max(window.minSize.width, restored.width), target.width - 24)
        restored.size.height = min(max(window.minSize.height, restored.height), target.height - 24)
        restored.origin.x = min(max(restored.minX, target.minX + 12), target.maxX - restored.width - 12)
        restored.origin.y = min(max(restored.minY, target.minY + 12), target.maxY - restored.height - 12)
        window.setFrame(restored, display: false)
        window.setFrameAutosaveName("AI Desk Desktop")
        window.isReleasedWhenClosed = false
        window.backgroundColor = .clear
        window.isOpaque = false
        window.hasShadow = false
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "desktop")
        web = WKWebView(frame: NSRect(origin: .zero, size: window.contentLayoutRect.size), configuration: configuration)
        web.navigationDelegate = self
        web.autoresizingMask = [.width, .height]
        web.setValue(false, forKey: "drawsBackground")
        // Keep the drag surface above WebKit's internal rendering views.
        let content = NSView(frame: web.frame)
        window.contentView = content
        content.addSubview(web)
        let drag = DragArea(frame: NSRect(x: 24, y: content.bounds.height-89, width: max(40, content.bounds.width-524), height: 65))
        drag.autoresizingMask = [.width, .minYMargin]
        content.addSubview(drag)
        place()
        web.load(URLRequest(url: url))
        window.orderFrontRegardless()
    }
    func startBackend() {
        let bundle = Bundle.main.bundleURL
        let resources = bundle.appendingPathComponent("Contents/Resources")
        let runtime = bundle.appendingPathComponent("Contents/Frameworks/Python.framework/Versions/3.14")
        let data = ProcessInfo.processInfo.environment["AI_DESK_DATA"].map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/AI Desk")
        do {
            try FileManager.default.createDirectory(at: data, withIntermediateDirectories: true)
            let log = data.appendingPathComponent("runtime.log")
            if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
            startupLog = log
            let errorLog = try FileHandle(forWritingTo: log)
            try errorLog.seekToEnd()
            let process = Process(), output = Pipe()
            process.executableURL = runtime.appendingPathComponent("Resources/Python.app/Contents/MacOS/Python")
            process.arguments = ["-s", "-B", resources.appendingPathComponent("server.py").path, "--headless"]
            process.currentDirectoryURL = resources
            var environment = ProcessInfo.processInfo.environment.filter { !$0.key.hasPrefix("PYTHON") }
            environment["PYTHONHOME"] = runtime.path
            environment["PYTHONNOUSERSITE"] = "1"
            environment["PYTHON_JIT"] = "0"
            environment["LANG"] = "en_US.UTF-8"
            process.environment = environment
            process.standardOutput = output
            process.standardError = errorLog
            process.terminationHandler = { [weak self] p in
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    if self.window == nil { self.startupFailed("실행을 시작하지 못했습니다. AI Desk가 이미 실행 중이면 기존 창을 열어 주세요.") }
                    else { NSApp.terminate(nil) }
                }
            }
            backend = process
            try process.run()
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                var bytes = Data()
                while bytes.count < 10000 {
                    let next = output.fileHandleForReading.readData(ofLength: 1)
                    if next.isEmpty { break }
                    if next[0] == 10 { break }
                    bytes.append(next)
                }
                guard let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                      let text = object["url"] as? String, let url = URL(string: text), url.host == "127.0.0.1" else {
                    DispatchQueue.main.async { self?.startupFailed("시작 응답을 읽지 못했습니다. 실행 기록을 확인해 주세요.") }
                    return
                }
                DispatchQueue.main.async { self?.createWindow(url: url, foreground: object["foreground"] as? Bool ?? true) }
            }
        } catch { startupFailed("실행을 시작하지 못했습니다. 앱을 응용 프로그램 폴더로 다시 복사해 주세요.") }
    }
    func startupFailed(_ text: String) {
        guard !startupErrorShown else { return }
        startupErrorShown = true
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "AI Desk를 열 수 없습니다"
        alert.informativeText = text + (startupLog.map { "\n\n실행 기록: " + $0.path } ?? "")
        alert.addButton(withTitle: "닫기")
        alert.runModal()
        NSApp.terminate(nil)
    }
    func applicationWillTerminate(_ notification: Notification) {
        if let process = backend, process.isRunning { process.terminate(); process.waitUntilExit() }
    }
    func place() {
        window.level = pinned ? .floating : embedded ? NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.desktopIconWindow)) + 1) : .normal
        window.collectionBehavior = embedded ? [.canJoinAllSpaces, .stationary, .ignoresCycle] : []
        window.hidesOnDeactivate = false
        window.ignoresMouseEvents = false
        if !embedded || pinned { NSApp.activate(ignoringOtherApps: true); window.makeKeyAndOrderFront(nil) }
        print("AI_DESK_NATIVE_LAYER=\(window.level.rawValue)")
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let command = message.body as? String else { return }
        if command == "togglePlacement" {
            embedded.toggle(); place()
            syncState()
        } else if command == "togglePin" {
            pinned.toggle(); UserDefaults.standard.set(pinned, forKey: "AI Desk Pinned"); place(); syncState()
        } else if command.hasPrefix("openURL:"), let url = URL(string: String(command.dropFirst(8))), let scheme = url.scheme, ["https", "http"].contains(scheme) {
            NSWorkspace.shared.open(url)
        } else if command == "focusInput" {
            NSApp.activate(ignoringOtherApps: true)
            window.makeKey()
            window.makeFirstResponder(web)
        } else if command == "quit" { NSApp.terminate(nil) }
    }
    func syncState() {
        web.evaluateJavaScript("setDesktopState(\(embedded ? "true" : "false"),\(pinned ? "true" : "false"))", completionHandler: nil)
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { syncState() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        guard window != nil else { return true }
        embedded = false
        place()
        syncState()
        return true
    }
}
let app = NSApplication.shared
let delegate = Host()
app.setActivationPolicy(.regular)
app.delegate = delegate
app.run()
