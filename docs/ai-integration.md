# AI Integration Boundary

The video worker uses FFmpeg to sample a recorded video and runs the bundled
OpenCV Zoo ONNX models on the CPU. YuNet detects faces. The worker aligns the
largest face in each frame and uses the MobileFaceNet-based Progressive Teacher
model to classify its expression. It filters the top softmax score before sending
only the result to `POST /api/ai/emoji-results` on the local Flask server.

The local worker logs both the original expression (`emotion`) and the mapped
classroom category (`mood`). It stores the mapped category with the original
expression score. The mapping is a project convention for grouping results.

| Model expression | Classroom category |
| --- | --- |
| `happy` 开心 | `happy` 开心 |
| `neutral` 中性 | `calm` 平静 |
| `surprised` 惊讶 | `confused` 困惑 |
| `sad` 悲伤 | `tired` 疲惫 |
| `fearful` 害怕 | `anxious` 焦虑 |
| `angry` 生气 | `anxious` 焦虑 |
| `disgust` 厌恶 | `distracted` 分心 |

The boundary enforces:

- a separate `X-AI-Service-Token`, never a student or teacher session token;
- a configurable confidence threshold (`EMOTION_AI_THRESHOLD`, default 0.6);
- six classroom categories for AI and manual records, with earlier AI records mapped on upgrade;
- `source=AI`, timestamp, confidence, classroom session, and device ID;
- anonymous records when no `user_id` is provided;
- no raw image, video, or face embedding persistence;
- rejected rows and counts in the response for retry/error logging.

The model classifies visible expressions. Lighting, occlusion, pose, and
expression differences can affect the result. Its score is uncalibrated, and
categories such as confusion and distraction require separate labeled data and
validation if added to a future classifier.

## Bundled model sources

The weights come from OpenCV Zoo commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`.

- `face_detection_yunet_2023mar.onnx`, MIT, copyright 2020 Shiqi Yu. [YuNet source](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet)
- `facial_expression_recognition_mobilefacenet_2022july.onnx`, Apache 2.0. The OpenCV Zoo inference demo credits the Shenzhen Institute of Artificial Intelligence and Robotics for Society (2022). [Expression model source](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/facial_expression_recognition)

License texts are included in `models/`.
