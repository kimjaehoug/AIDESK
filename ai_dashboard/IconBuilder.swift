import Cocoa

let folder = URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("AppIcon.iconset")
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
                                      bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                      colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        bitmap.size = NSSize(width: pixels, height: pixels)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
        let n = CGFloat(pixels)
        let rect = NSRect(x: n * 0.045, y: n * 0.045, width: n * 0.91, height: n * 0.91)
        let card = NSBezierPath(roundedRect: rect, xRadius: n * 0.22, yRadius: n * 0.22)
        NSGradient(starting: NSColor(calibratedRed: 0.41, green: 0.32, blue: 0.88, alpha: 1),
                   ending: NSColor(calibratedRed: 0.17, green: 0.14, blue: 0.40, alpha: 1))!.draw(in: card, angle: -60)
        let star = NSBezierPath()
        star.move(to: NSPoint(x: n * 0.5, y: n * 0.81))
        star.curve(to: NSPoint(x: n * 0.81, y: n * 0.5), controlPoint1: NSPoint(x: n * 0.55, y: n * 0.57), controlPoint2: NSPoint(x: n * 0.60, y: n * 0.55))
        star.curve(to: NSPoint(x: n * 0.5, y: n * 0.19), controlPoint1: NSPoint(x: n * 0.60, y: n * 0.45), controlPoint2: NSPoint(x: n * 0.55, y: n * 0.43))
        star.curve(to: NSPoint(x: n * 0.19, y: n * 0.5), controlPoint1: NSPoint(x: n * 0.45, y: n * 0.43), controlPoint2: NSPoint(x: n * 0.40, y: n * 0.45))
        star.curve(to: NSPoint(x: n * 0.5, y: n * 0.81), controlPoint1: NSPoint(x: n * 0.40, y: n * 0.55), controlPoint2: NSPoint(x: n * 0.45, y: n * 0.57))
        NSColor(calibratedWhite: 0.98, alpha: 1).setFill()
        star.fill()
        NSGraphicsContext.restoreGraphicsState()
        let name = "icon_\(size)x\(size)" + (scale == 2 ? "@2x" : "") + ".png"
        try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent(name))
    }
}
