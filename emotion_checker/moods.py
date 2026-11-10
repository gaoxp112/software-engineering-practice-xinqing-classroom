MOODS = {
    "happy": {"emoji": "😄", "label": "开心", "score": 3},
    "calm": {"emoji": "🙂", "label": "平静", "score": 2},
    "confused": {"emoji": "😕", "label": "困惑", "score": -1},
    "tired": {"emoji": "😴", "label": "疲惫", "score": -2},
    "anxious": {"emoji": "😟", "label": "焦虑", "score": -3},
    "distracted": {"emoji": "🥱", "label": "分心", "score": -2},
}

EXPRESSION_TO_MOOD = {
    "angry": "anxious",
    "disgust": "distracted",
    "fearful": "anxious",
    "happy": "happy",
    "neutral": "calm",
    "sad": "tired",
    "surprised": "confused",
}
