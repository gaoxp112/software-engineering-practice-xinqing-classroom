# AI Integration

The teacher starts recognition from an open classroom dashboard. The camera
worker reads the local webcam with OpenCV and runs the bundled ONNX models on the
CPU. YuNet locates faces, and the MobileFaceNet model classifies the expression
of the largest detected face after alignment.

The dashboard shows the live preview, face box, mapped category and confidence.
About every three seconds, the worker stores a sample with a confidence of at
least 0.65 as an anonymous AI record for the current classroom. The record
contains the mapped category and the original expression score.

| Model expression | Classroom category |
| --- | --- |
| `happy` 开心 | `happy` 开心 |
| `neutral` 中性 | `calm` 平静 |
| `surprised` 惊讶 | `confused` 困惑 |
| `sad` 悲伤 | `tired` 疲惫 |
| `fearful` 害怕 | `anxious` 焦虑 |
| `angry` 生气 | `anxious` 焦虑 |
| `disgust` 厌恶 | `distracted` 分心 |

The independent `POST /api/ai/emoji-results` endpoint supports AI result ingestion
through the following contract:

- a separate `X-AI-Service-Token`, never a student or teacher session token;
- a configurable confidence threshold (`EMOTION_AI_THRESHOLD`, default 0.6);
- six classroom categories for AI and manual records, with earlier AI records mapped on upgrade;
- `source=AI`, timestamp, confidence, classroom session, and device ID;
- anonymous records when no `user_id` is provided;
- no raw image, video, or face embedding persistence;
- rejected rows and counts in the response for retry/error logging.

## Bundled model sources

The weights come from OpenCV Zoo commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`.

- `face_detection_yunet_2023mar.onnx`, MIT, copyright 2020 Shiqi Yu. [YuNet source](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet)
- `facial_expression_recognition_mobilefacenet_2022july.onnx`, Apache 2.0. The OpenCV Zoo inference demo credits the Shenzhen Institute of Artificial Intelligence and Robotics for Society (2022). [Expression model source](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/facial_expression_recognition)

License texts are included in `models/`.
