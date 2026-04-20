import asyncio
import logging
from utils.llm_client import async_multimodal_infer
from utils.audio_utils import dialogue_to_json
from utils.audio_splitter import split_audio_and_text
from config import USER_CONTENT_ASR


class AsrTextEnhancerService:

    def __init__(self, system_message, model=None, api_key=None, base_url=None,
                 logger=None, request_id=""):
        self.system_message = system_message
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.logger = logger
        self.request_id = request_id

    def _log(self, msg, level=logging.INFO):
        if self.logger:
            self.logger.log(level, f"[{self.request_id}] {msg}")

    # ===============================
    # 1 主流程
    # ===============================
    async def enhance(self, audio_url, speech_list):

        # 1. 按时长切分音频和文本（<=1h 不切分，>1h 按小时数切分，最多6段）
        self._log("开始音频文本切分")
        parts = await split_audio_and_text(
            audio_url=audio_url,
            segments=speech_list,
            time_unit="ms",
            audio_format="mp3",
            logger=self.logger,
            request_id=self.request_id
        )
        self._log(f"切分完成，共 {len(parts)} 段，开始并发多模态推理")

        # 2. 并发调用多模态模型，每段独立分析
        tasks = [self._infer_part(part) for part in parts]
        part_results = await asyncio.gather(*tasks)

        # 3. 按段序号顺序合并结果，恢复每句的全局时间戳
        merged_speech_list = []
        total_input_tokens = 0
        total_output_tokens = 0

        for part, (speech_list_part, input_token, output_token) in zip(parts, part_results):
            offset_ms = part["time_range"]["begin_ms"]
            self._log(f"第 {part['part_index'] + 1} 段合并: offset={offset_ms}ms, "
                      f"句数={len(speech_list_part)}, "
                      f"input_tokens={input_token}, output_tokens={output_token}")

            for item in speech_list_part:
                merged_speech_list.append({
                    "beginTime": item["beginTime"] + offset_ms,
                    "endTime":   item["endTime"]   + offset_ms,
                    "role":      item["role"],
                    "text":      item["text"]
                })

            total_input_tokens  += input_token
            total_output_tokens += output_token

        self._log(f"全部合并完成: 总句数={len(merged_speech_list)}, "
                  f"total_input_tokens={total_input_tokens}, total_output_tokens={total_output_tokens}")

        return {
            "speech_list":    merged_speech_list,
            "input_tokens":   total_input_tokens,
            "output_tokens":  total_output_tokens
        }

    # ===============================
    # 2 单段推理
    # ===============================
    async def _infer_part(self, part):
        """对单段音频+文本调用多模态模型，返回 (speech_list, input_token, output_token)"""

        part_index = part.get("part_index", "?")
        self._log(f"第 {part_index + 1} 段推理开始: "
                  f"时间范围={part['time_range']['begin_ms']}ms - {part['time_range']['end_ms']}ms")

        asr_text = USER_CONTENT_ASR.replace("**ANALYSIS_TEXT**", part["formatted_text"])

        content, input_token, output_token = await async_multimodal_infer(
            system_message=self.system_message,
            asr_text=asr_text,
            audio_base64=part["audio_base64"],
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            logger=self.logger,
            request_id=self.request_id
        )

        if content is None:
            self._log(f"第 {part_index + 1} 段推理失败: 所有重试均未返回内容", level=logging.ERROR)
            raise RuntimeError(f"第 {part_index} 段模型推理失败：所有重试均未返回内容")

        self._log(f"第 {part_index + 1} 段推理完成: input_tokens={input_token}, output_tokens={output_token}")

        # 将模型返回的对话文本解析为 JSON，beginTime/endTime 为段内相对毫秒
        speech_list_part = dialogue_to_json(content)
        self._log(f"第 {part_index + 1} 段解析完成: 解析句数={len(speech_list_part)}")

        return speech_list_part, input_token, output_token
