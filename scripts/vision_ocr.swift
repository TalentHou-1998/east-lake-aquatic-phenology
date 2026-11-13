#!/usr/bin/env swift

import Foundation
import ImageIO
import Vision

struct OCRLine: Codable {
    let text: String
    let confidence: Float
}

struct OCRResult: Codable {
    let text: String
    let lines: [OCRLine]
    let languages: [String]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

guard CommandLine.arguments.count == 2 else {
    fail("usage: vision_ocr.swift IMAGE_PATH")
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fail("cannot decode image: \(imageURL.path)")
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let supported = (try? request.supportedRecognitionLanguages()) ?? []
let preferred = ["zh-Hans", "zh-Hant", "en-US"].filter { supported.contains($0) }
if !preferred.isEmpty {
    request.recognitionLanguages = preferred
}

do {
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])
    let lines: [OCRLine] = (request.results ?? []).compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        return OCRLine(text: candidate.string, confidence: candidate.confidence)
    }
    let result = OCRResult(
        text: lines.map(\.text).joined(separator: "\n"),
        lines: lines,
        languages: preferred
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.withoutEscapingSlashes]
    FileHandle.standardOutput.write(try encoder.encode(result))
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    fail("vision OCR failed: \(error)")
}
