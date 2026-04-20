import re
import aiohttp
import json
import asyncio
from config import MODEL_CALL_SEMAPHORE

# ==== 工具函数 ====

# 检查判断输入的文本是否为中文
def is_chinese_utf8(text: str):
    """
    检查文本是否为主要UTF-8中文内容，
    且符合“销售/顾问/客服 等 vs 顾客/客户/用户 等”的对话格式。
    返回 (bool, text)，若符合要求则返回 (True, 原文本)，否则 (False, "")
    """
    if not text or not isinstance(text, str):
        return False, ""

    # UTF-8 编码检查
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False, "文本格式不符合utf-8标准"

    # UTF-8 编码检查
    if len(text) > 50000:
        return False, "对话文本长度超过5万字"

    # 中文比例检查
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chinese_chars) <= 10:
        return False, "中文占比过少"

    # 兼容多种销售与顾客称呼
    seller_roles = r'(销售顾问|销售员|销售|顾问|客服|接待|经理|工作人员)'
    buyer_roles  = r'(顾客|客户|用户|消费者|车主|先生|女士)'

    # 必须至少包含一种销售端和顾客端角色
    if not re.search(seller_roles + r'：', text) or not re.search(buyer_roles + r'：', text):
        return False, "必须至少包含一种销售端和顾客端角色"

    # 检查销售与顾客是否交替出现（多轮结构）
    dialogue_pattern = re.compile(fr'({seller_roles}：.*?{buyer_roles}：.*?)+', re.S)
    if not dialogue_pattern.search(text):
        return False, "文本至少需要包含两个角色的多轮对话"

    # 至少两轮（销售端和顾客端各至少出现两次）
    if len(re.findall(seller_roles + r'：', text)) < 2 or len(re.findall(buyer_roles + r'：', text)) < 2:
        return False, "对话轮次过少，不足以进行对话分析"

    return True, text

def extract_task_fields(json_data: dict):
    """参数校验与提取"""
    if "task_text" not in json_data:
        raise ValueError("缺少参数 task_text")
    task_text = json_data["task_text"]
    status, error_text = is_chinese_utf8(task_text)
    if not isinstance(task_text, str) or not status:
        _, error_text = is_chinese_utf8(task_text)
        raise ValueError(f"{error_text}")
    return task_text

def has_key_anywhere(data, target_keys):
    """
    在任意层级递归查找多个 key
    :param data: 任意 JSON 结构（dict / list）
    :param target_keys: 要查找的 key 列表，例如 ["status", "message"]
    :return: True 如果所有 key 都存在，否则 False
    """
    found_keys = set()

    def _search(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k in target_keys:
                    found_keys.add(k)
                _search(v)
        elif isinstance(d, list):
            for item in d:
                _search(item)

    _search(data)
    return all(k in found_keys for k in target_keys)

# 异步请求deepseek方法
# 流式返回，根据火山云反馈，在一些思维链较长的场景中，流式返回接口稳定性更高，不易出现接口超时现象
async def async_get_deepseek_stream(system_message, user_message, logger, model=None, api_key=None, base_url=None,
                                    key_list=None, max_retries=3):
    """异步流式调用大模型并返回完整拼接内容（优化版）"""
    payload = json.dumps({
        "model": model,
        "stream": True,
        "thinking": {"type": "enabled"},
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
    })

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    content = ""
    input_token = 0
    output_token = 0

    for attempt in range(max_retries):
        try:
            async with MODEL_CALL_SEMAPHORE:
                async with aiohttp.ClientSession() as session:
                    async with session.post(base_url, headers=headers, data=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                        response.raise_for_status()

                        data_json = {}  # ✅ 提前定义，防止未定义异常
                        line_count = 0

                        async for raw_line in response.content:
                            line = raw_line.decode("utf-8", errors="ignore").strip()
                            line_count += 1

                            # 跳过空行或非data开头
                            if not line or not line.startswith("data:"):
                                continue

                            data = line[len("data:"):].strip()
                            if data == "[DONE]":
                                break

                            try:
                                data_json = json.loads(data)

                                # ✅ 保护性访问，防止list index out of range
                                choices = data_json.get("choices", [])
                                if not isinstance(choices, list) or len(choices) == 0:
                                    # 某些chunk只有状态信息，无delta内容
                                    continue

                                delta = choices[0].get("delta", {})
                                if not isinstance(delta, dict):
                                    continue

                                content_piece = delta.get("content", "")
                                if content_piece:
                                    content += content_piece

                            except json.JSONDecodeError:
                                logger(f"[警告] 第{line_count}行 JSON解析失败: {line[:120]}")
                            except Exception as e:
                                logger(f"[异常] 第{line_count}行解析流式数据出错: {e}")

                        # ✅ 安全获取 usage 信息
                        usage = data_json.get("usage") or {}
                        input_token = usage.get("prompt_tokens", 0)
                        output_token = usage.get("completion_tokens", 0)

                        # 检查大模型是否按要求返回了所有关键字段信息
                        if has_key_anywhere(json.loads(content), key_list) and key_list:
                            return content, input_token, output_token
                        elif key_list is None:
                            return content, input_token, output_token
                        else:
                            logger(f"模型返回异常 (尝试 {attempt + 1}/{max_retries})")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(30)
                            else:
                                logger("达到最大重试次数，返回默认结果")

        except asyncio.TimeoutError:
            logger(f"[警告] 请求超时 (第 {attempt + 1}/{max_retries} 次)")
            if attempt < max_retries - 1:
                await asyncio.sleep(10)
            else:
                logger(f"[错误] 达到最大重试次数，返回空结果")
        except aiohttp.ClientError as e:
            logger(f"[网络错误] 第 {attempt + 1} 次尝试失败: {e}")
            await asyncio.sleep(5)
        except Exception as e:
            logger(f"[错误] {e}")
            break

    return content, input_token, output_token


async def async_get_deepseek(system_message, user_message, logger, model=None, api_key=None, base_url=None, key_list=None, max_retries=3):
    """异步版本的模型推理请求"""
    payload = json.dumps({
        "model": model,
        "stream": False,
        "thinking": {
            "type": "disabled"
        },
        "response_format": {
            "type": "json_object"
        },
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
    })
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    content = None  # 大模型输出结果
    input_token = 0  # 大模型输入消耗token数
    output_token = 0  # 大模型输出消耗token数

    for attempt in range(max_retries):
        try:
            async with MODEL_CALL_SEMAPHORE:
                async with aiohttp.ClientSession() as session:
                    async with session.post(base_url, headers=headers, data=payload) as response:
                        response.raise_for_status()
                        response_text = await response.text()
                        response_json = json.loads(response_text)

                        if response_json.get("code", [{}]) == '0':
                            content = response_json.get("choices", [{}])[0].get("message", {}).get("content", {})
                            usage = response_json.get("usage", {})
                            input_token = usage.get("prompt_tokens", 0)
                            output_token = usage.get("completion_tokens", 0)

                            # 检查大模型是否按要求返回了所有关键字段信息
                            if has_key_anywhere(json.loads(content), key_list) and key_list:
                                return content, input_token, output_token
                            elif key_list is None:
                                return content, input_token, output_token
                            else:
                                logger(f"模型返回异常 (尝试 {attempt + 1}/{max_retries})")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(10)
                                else:
                                    logger("达到最大重试次数，返回默认结果")
        except Exception as e:
            logger(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(10)
            else:
                logger("达到最大重试次数，返回默认结果")

    return content, input_token, output_token


##################################调用多模态模型进行音频理解分析#######################################
async def async_multimodal_infer(
        system_message,
        asr_text,
        audio_base64,
        model=None,
        api_key=None,
        base_url=None,
        audio_format="mp3",
        temperature=0.05,
        max_retries=3,
        logger=None,
        request_id=""
):
    """
    异步多模态推理

    Returns
    -------
    content : str
        模型原始输出
    input_token : int
    output_token : int
    """
    import logging
    import time

    def _log(msg, level=logging.INFO):
        if logger:
            logger.log(level, f"[{request_id}] {msg}")

    audio_size_kb = len(audio_base64) / 1024
    text_len = len(asr_text)
    _log(f"多模态推理开始: model={model}, audio_size={audio_size_kb:.1f}KB, "
         f"text_len={text_len}, temperature={temperature}, max_retries={max_retries}")

    content = None
    input_token = 0
    output_token = 0

    for attempt in range(max_retries):
        payload = json.dumps({
            "model": model,
            "temperature": temperature,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": asr_text
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_base64,
                                "format": audio_format
                            }
                        }
                    ]
                }
            ]
        })

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            _log(f"发起请求 (第 {attempt + 1}/{max_retries} 次): url={base_url}")
            t0 = time.time()

            async with MODEL_CALL_SEMAPHORE:

                async with aiohttp.ClientSession() as session:

                    async with session.post(
                        base_url,
                        headers=headers,
                        data=payload
                    ) as response:

                        response.raise_for_status()

                        response_text = await response.text()
                        elapsed = time.time() - t0
                        _log(f"收到响应: status={response.status}, 耗时={elapsed:.2f}s, "
                             f"响应大小={len(response_text) / 1024:.1f}KB")

                        response_json = json.loads(response_text)

                        if "choices" in response_json:

                            content = response_json["choices"][0]["message"]["content"]

                            usage = response_json.get("usage", {})
                            input_token = usage.get("prompt_tokens", 0)
                            output_token = usage.get("completion_tokens", 0)

                            _log(f"推理成功: input_tokens={input_token}, output_tokens={output_token}, "
                                 f"output_len={len(content)}")
                            return content, input_token, output_token
                        else:
                            _log(f"响应中无 choices 字段 (第 {attempt + 1}/{max_retries} 次): "
                                 f"keys={list(response_json.keys())}", level=logging.WARNING)

        except aiohttp.ClientResponseError as e:
            _log(f"HTTP错误 (第 {attempt + 1}/{max_retries} 次): status={e.status}, message={e.message}",
                 level=logging.ERROR)
            if attempt < max_retries - 1:
                await asyncio.sleep(30)
                # model = GEMINI_MESSAGE_T["model"]
            else:
                _log("达到最大重试次数，返回空结果", level=logging.ERROR)

        except aiohttp.ClientError as e:
            _log(f"网络错误 (第 {attempt + 1}/{max_retries} 次): {e}", level=logging.ERROR)
            if attempt < max_retries - 1:
                await asyncio.sleep(30)
                # model = GEMINI_MESSAGE_T["model"]
            else:
                _log("达到最大重试次数，返回空结果", level=logging.ERROR)

        except Exception as e:
            _log(f"请求异常 (第 {attempt + 1}/{max_retries} 次): {e}", level=logging.ERROR)
            if attempt < max_retries - 1:
                await asyncio.sleep(30)
                # model = GEMINI_MESSAGE_T["model"]
            else:
                _log("达到最大重试次数，返回空结果", level=logging.ERROR)

    _log(f"多模态推理结束: content={'有内容' if content else '空'}, "
         f"input_tokens={input_token}, output_tokens={output_token}")
    return content, input_token, output_token


