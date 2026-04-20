import json
import re


def ms_to_timestamp(ms):
    """毫秒 -> HH:MM:SS.mmm"""
    seconds = ms // 1000
    milliseconds = ms % 1000

    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    return f"{h:02d}:{m:02d}:{s:02d}.{milliseconds:03d}"


def timestamp_to_ms(timestamp):
    """HH:MM:SS.mmm -> 毫秒"""

    if "." in timestamp:
        time_part, ms_part = timestamp.split(".")
        milliseconds = int(ms_part)
    else:
        time_part = timestamp
        milliseconds = 0

    h, m, s = map(int, time_part.split(":"))

    total_ms = (h * 3600 + m * 60 + s) * 1000 + milliseconds

    return total_ms


# ===============================
# JSON -> 文本
# ===============================
def json_to_dialogue(json_data):
    lines = []

    for item in json_data:
        timestamp = ms_to_timestamp(item["beginTime"])

        role = "客户" if item["role"] == 1 else "销售"

        text = item["text"]

        lines.append(f"[{timestamp}] {role}：{text}")

    return "\n".join(lines)


# ===============================
# 文本 -> JSON
# ===============================
def dialogue_to_json(dialogue_text):
    result = []

    pattern = r"\[(\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)\]\s*(客户|销售)[：:]\s*(.*)"

    for line in dialogue_text.splitlines():

        match = re.match(pattern, line.strip())

        if not match:
            continue

        timestamp, role, text = match.groups()

        begin_time = timestamp_to_ms(timestamp)

        role_id = 1 if role == "客户" else 0

        result.append({
            "beginTime": begin_time,
            "endTime": begin_time,
            "role": role_id,
            "text": text
        })

    return result
