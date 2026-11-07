import Foundation
import ReplayKit
import CoreImage
import UIKit

/// Broadcast Upload Extension target only. Not a complete app target.
/// Requires matching App Group entitlement with the host app.
final class SampleHandler: RPBroadcastSampleHandler {
    private let appGroup = "group.example.lastzscanner"
    private let context = CIContext()
    private let queue = DispatchQueue(label: "lastz.broadcast.encoder", qos: .utility)
    private var lastCaptureTime: CFTimeInterval = 0
    private var uploadInFlight = false

    override func broadcastStarted(withSetupInfo setupInfo: [String : NSObject]?) {
        lastCaptureTime = 0
    }

    override func broadcastFinished() {
        // ReplayKit terminates this extension after broadcast stops.
    }

    override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer,
                                      with sampleBufferType: RPSampleBufferType) {
        guard sampleBufferType == .video,
              CMSampleBufferIsValid(sampleBuffer),
              let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let timestamp = CACurrentMediaTime()
        // Initial 1 frame per second target; tune only after physical device tests.
        guard timestamp - lastCaptureTime >= 1.0, !uploadInFlight else { return }
        lastCaptureTime = timestamp
        uploadInFlight = true

        CVPixelBufferRetain(buffer)
        queue.async { [weak self] in
            guard let self else { CVPixelBufferRelease(buffer); return }
            defer { CVPixelBufferRelease(buffer) }
            let defaults = UserDefaults(suiteName: self.appGroup)
            guard let base = defaults?.string(forKey: "endpoint"),
                  let token = defaults?.string(forKey: "token"),
                  let state = defaults?.string(forKey: "state"),
                  let url = URL(string: base + "/v1/frames") else {
                self.uploadInFlight = false
                return
            }
            let ciImage = CIImage(cvPixelBuffer: buffer)
            let extent = ciImage.extent
            let scale = min(1.0, 960.0 / max(extent.width, extent.height))
            let resized = ciImage.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
            guard let cgImage = self.context.createCGImage(resized, from: resized.extent),
                  let data = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.55) else {
                self.uploadInFlight = false
                return
            }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 8
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            request.setValue("image/jpeg", forHTTPHeaderField: "Content-Type")
            request.setValue(state, forHTTPHeaderField: "X-LastZ-State")
            URLSession.shared.uploadTask(with: request, from: data) { [weak self] _, _, _ in
                self?.uploadInFlight = false
            }.resume()
        }
    }
}
