from pathlib import Path

import cv2
import numpy as np

from emotion_checker.moods import EXPRESSION_TO_MOOD


MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
LABELS = ("angry", "disgust", "fearful", "happy", "neutral", "sad", "surprised")
# Landmark template and input normalization from the OpenCV Zoo model demo.
FACE_LANDMARKS = np.float32([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041],
])
INPUT_SIZE = (112, 112)


class LocalExpressionModel:
    def __init__(self):
        detector_weights = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
        expression_weights = MODEL_DIR / "facial_expression_recognition_mobilefacenet_2022july.onnx"
        # Loading buffers also supports Windows project paths with non-ASCII characters.
        self.detector = cv2.FaceDetectorYN.create(
            "onnx", np.frombuffer(detector_weights.read_bytes(), np.uint8), None, (320, 320), 0.8,
        )
        self.classifier = cv2.dnn.readNetFromONNX(np.frombuffer(expression_weights.read_bytes(), np.uint8))

    def analyze_image(self, image):
        height, width = image.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(image)
        if faces is None:
            return {"face_detected": False, "emotion": "unknown", "confidence": 0.0}

        face = max(faces, key=lambda detection: detection[2] * detection[3])
        box = [int(value) for value in face[:4]]
        landmarks = face[4:14].reshape(5, 2)
        transform, _ = cv2.estimateAffinePartial2D(landmarks, FACE_LANDMARKS, method=cv2.LMEDS)
        if transform is None:
            return {"face_detected": True, "emotion": "unknown", "confidence": 0.0, "box": box}

        aligned = cv2.warpAffine(image, transform, INPUT_SIZE)
        blob = cv2.dnn.blobFromImage(aligned, 1 / 127.5, INPUT_SIZE, (127.5,) * 3, swapRB=True)
        self.classifier.setInput(blob, "data")
        logits = self.classifier.forward("label").ravel()
        label_index = int(logits.argmax())
        expression = LABELS[label_index]
        scores = np.exp(logits - logits.max())
        return {
            "face_detected": True,
            "emotion": expression,
            "mood": EXPRESSION_TO_MOOD[expression],
            "confidence": float(scores[label_index] / scores.sum()),
            "box": box,
        }
