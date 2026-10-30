import AppKit

let destination = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let image = NSImage(size: NSSize(width: pixels, height: pixels))
        image.lockFocus()
        let p = CGFloat(pixels)
        let bounds = NSRect(x: p * 0.08, y: p * 0.08, width: p * 0.84, height: p * 0.84)
        let path = NSBezierPath(roundedRect: bounds, xRadius: p * 0.19, yRadius: p * 0.19)
        let gradient = NSGradient(starting: NSColor(red: 0.70, green: 0.31, blue: 0.37, alpha: 1), ending: NSColor(red: 0.44, green: 0.13, blue: 0.23, alpha: 1))!
        gradient.draw(in: path, angle: -45)
        if let symbol = NSImage(systemSymbolName: "music.note", accessibilityDescription: nil) {
            let config = NSImage.SymbolConfiguration(pointSize: p * 0.50, weight: .medium)
                .applying(NSImage.SymbolConfiguration(paletteColors: [.white]))
            let configured = symbol.withSymbolConfiguration(config)!
            let symbolSize = configured.size
            let target = NSRect(x: (p - symbolSize.width) / 2, y: (p - symbolSize.height) / 2, width: symbolSize.width, height: symbolSize.height)
            configured.draw(in: target)
        }
        image.unlockFocus()
        let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
        let name = "icon_\(size)x\(size)\(scale == 2 ? "@2x" : "").png"
        try bitmap.representation(using: .png, properties: [:])!.write(to: destination.appendingPathComponent(name))
    }
}
