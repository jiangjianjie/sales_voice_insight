import json
import logging
import time
import tornado.web
from utils.base_handler import BaseHandler
from services.asr_enhancer import AsrTextEnhancerService
from config import SYSTEM_CONTENT_ASR, GEMINI_MESSAGE

MAX_RETRY = 3

class MultimodalInferAsrTextHandler(BaseHandler):

    async def post(self):

        start_time = time.time()

        try:
            req = json.loads(self.request.body)
            audio_url = req.get("audio_url")
            speech_list = req.get("speech_list")

            # 参数校验
            if not audio_url:
                self.log_message("请求参数缺少 audio_url", level=logging.WARNING)
                self.write({"code": 400, "msg": "缺少参数 audio_url"})
                return
            if not speech_list or not isinstance(speech_list, list):
                self.log_message("请求参数缺少或格式错误 speech_list", level=logging.WARNING)
                self.write({"code": 400, "msg": "缺少参数 speech_list 或格式错误"})
                return

            self.log_message(f"请求参数: audio_url={audio_url[:80]}{'...' if len(audio_url) > 80 else ''}, "
                             f"speech_list 条数={len(speech_list)}")

            service = AsrTextEnhancerService(
                system_message=SYSTEM_CONTENT_ASR,
                model=GEMINI_MESSAGE["model"],
                api_key=GEMINI_MESSAGE["key"],
                base_url=GEMINI_MESSAGE["url"],
                logger=self.logger,
                request_id=self.request_id
            )

            result = await service.enhance(audio_url, speech_list)

            spend_time = time.time() - start_time
            self.log_message(f"请求处理完成: 耗时={spend_time:.2f}s, "
                             f"输出句数={len(result.get('speech_list', []))}, "
                             f"input_tokens={result.get('input_tokens', 0)}, "
                             f"output_tokens={result.get('output_tokens', 0)}")

            self.write({"code": 0, "msg": "success", "data": result})

        except Exception as e:
            spend_time = time.time() - start_time
            self.log_message(f"请求处理异常: 耗时={spend_time:.2f}s, error={e}", level=logging.ERROR)
            self.write({"code": 500, "msg": str(e)})
