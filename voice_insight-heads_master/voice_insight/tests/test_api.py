import pandas as pd
import requests
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


def process_one(row, output_dir, api_url):
    record_id = str(row["录音ID"]).strip()
    audio_url = row["录音文件url"]
    text_url = row["录音文本url"]

    try:
        print(f"开始处理: {record_id}")

        # ===== 下载 speech_list =====
        text_resp = requests.get(text_url, timeout=30)
        text_resp.raise_for_status()
        speech_list = json.loads(text_resp.text)

        # ===== 调用接口 =====
        payload = {
            "audio_url": audio_url,
            "speech_list": speech_list
        }

        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=1800
        )

        result_json = json.loads(response.text)

        # ===== 保存结果 =====
        output_file = os.path.join(output_dir, f"{record_id}.txt")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(result_json, ensure_ascii=False, indent=2))

        print(f"完成: {record_id}")

    except Exception as e:
        print(f"失败: {record_id} -> {e}")
        error_file = os.path.join(output_dir, f"{record_id}_error.txt")
        with open(error_file, "w", encoding="utf-8") as f:
            f.write(str(e))


def batch_asr_request():
    excel_path = r"C:\Users\jjyao4\Desktop\长会话切分\效果测试\理想6条普通话录音导出url.xlsx"
    output_dir = r"C:\Users\jjyao4\Desktop\长会话切分\效果测试\优化结果"
    api_url = "http://172.31.241.58:8898/api/v1/multimodal/infer/asr"

    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_excel(excel_path)

    # ===== 并发线程数（建议 5~10）=====
    max_workers = 10

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_one, row, output_dir, api_url)
            for _, row in df.iterrows()
        ]

        for future in as_completed(futures):
            future.result()  # 捕获异常


if __name__ == "__main__":
    batch_asr_request()
