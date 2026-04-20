import logging
import math
import aiohttp
import base64
import io
import os
import sys
import shutil
from typing import List, Dict, Optional
from pydub import AudioSegment
from pydub.utils import mediainfo

# Windows 本地开发环境：指定 ffmpeg 硬编码路径
if sys.platform == "win32":
    _FFMPEG_BIN = r"C:\Users\jjyao4\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
    if os.path.isdir(_FFMPEG_BIN):
        os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")
        AudioSegment.converter = os.path.join(_FFMPEG_BIN, "ffmpeg.exe")
        AudioSegment.ffmpeg = os.path.join(_FFMPEG_BIN, "ffmpeg.exe")
        AudioSegment.ffprobe = os.path.join(_FFMPEG_BIN, "ffprobe.exe")
# Linux/Mac：依赖系统 PATH 中的 ffmpeg（apt install ffmpeg 或 brew install ffmpeg）
else:
    if not shutil.which("ffmpeg"):
        raise EnvironmentError("ffmpeg 未找到，请先安装: apt install ffmpeg")


async def download_audio(audio_url: str, timeout_seconds: int = 1800) -> bytes:
    """
    从URL下载音频文件

    参数:
        audio_url: 音频文件URL
        timeout_seconds: 超时时间(秒)

    返回:
        音频字节数据
    """
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(audio_url) as resp:
            resp.raise_for_status()
            return await resp.read()


def get_audio_duration_from_segments(segments: List[Dict], time_unit: str = "ms") -> float:
    """
    从文本段落列表获取音频时长(秒)，取最后一句的 endTime

    参数:
        segments: 文本段落列表
        time_unit: 时间戳单位, "ms"=毫秒, "s"=秒

    返回:
        音频时长(秒)
    """
    if not segments:
        return 0.0
    last_end = segments[-1]["endTime"]
    return last_end / 1000.0 if time_unit == "ms" else last_end


def format_timestamp(ms: int) -> str:
    """
    将毫秒时间戳格式化为 [HH:MM:SS.mmm]

    参数:
        ms: 毫秒时间戳

    返回:
        格式化字符串，如 [00:36:44.283]
    """
    total_seconds = ms // 1000
    milliseconds = ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"[{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}]"


def format_segments_to_text(segments: List[Dict], time_unit: str = "ms") -> str:
    """
    将文本段落列表格式化为可读文本

    格式: [HH:MM:SS.mmm] 角色：文本

    参数:
        segments: 文本段落列表
        time_unit: 时间戳单位

    返回:
        格式化后的文本字符串
    """
    ROLE_MAP = {1: "客户", 0: "销售"}

    lines = []
    for seg in segments:
        begin_ms = seg["beginTime"] * 1000 if time_unit == "s" else seg["beginTime"]
        role_name = ROLE_MAP.get(seg.get("role"), "未知")
        text = seg.get("text", "")
        lines.append(f"{format_timestamp(int(begin_ms))} {role_name}：{text}")

    return "\n".join(lines)


SENTENCE_END_CHARS = {"。", "！", "？", "!", "?", "…", "~", "～"}


def _find_split_timestamps(
    segments: List[Dict],
    total_duration_ms: int,
    num_parts: int,
    time_unit: str = "ms"
) -> List[int]:
    """
    从句子结束时间戳中找到最接近均匀切分点的时间戳（向下查找）

    策略:
        1. 提取所有以句子结束标志结尾的段落 endTime 作为候选切分点
        2. 对每个理想切分位置，从候选集中选 <= 理想时间且最接近的（向下找）
        3. 若候选集为空，回退到全部段落

    参数:
        segments: 文本段落列表
        total_duration_ms: 音频总时长(毫秒)
        num_parts: 切分段数
        time_unit: 时间戳单位, "ms"=毫秒, "s"=秒

    返回:
        切分时间戳列表(毫秒), 长度为 num_parts - 1
    """
    def to_ms(t):
        return t * 1000 if time_unit == "s" else t

    # 提取句子结束候选点: (index, end_ms)
    sentence_end = [
        (idx, to_ms(seg["endTime"]))
        for idx, seg in enumerate(segments)
        if seg.get("text", "")[-1:] in SENTENCE_END_CHARS
    ]
    # 无句子结束标志时回退到全部段落
    candidates = sentence_end if sentence_end else [
        (idx, to_ms(seg["endTime"])) for idx, seg in enumerate(segments)
    ]

    ideal_interval_ms = total_duration_ms / num_parts
    split_timestamps = []
    used_indices = set()

    for i in range(1, num_parts):
        ideal_time_ms = ideal_interval_ms * i

        # 向下查找: 选择 <= ideal_time_ms 且最接近的候选点
        valid_candidates = [
            (idx, end_ms) for idx, end_ms in candidates
            if idx not in used_indices and end_ms <= ideal_time_ms
        ]

        if valid_candidates:
            best = max(valid_candidates, key=lambda c: c[1])  # 取时间最大的（最接近理想点）
            used_indices.add(best[0])
            split_timestamps.append(best[1])
        else:
            # 无向下候选时，回退到最近的（可能向上）
            fallback = min(
                ((idx, end_ms) for idx, end_ms in candidates if idx not in used_indices),
                key=lambda c: abs(c[1] - ideal_time_ms),
                default=None,
            )
            if fallback is not None:
                used_indices.add(fallback[0])
                split_timestamps.append(fallback[1])

    return sorted(split_timestamps)


def _split_segments_by_timestamps(
    segments: List[Dict],
    split_timestamps_ms: List[int],
    time_unit: str = "ms"
) -> List[List[Dict]]:
    """
    按时间戳将文本段落切分为多组（按 endTime 归属）

    参数:
        segments: 文本段落列表
        split_timestamps_ms: 切分时间戳列表(毫秒)
        time_unit: 时间戳单位

    返回:
        切分后的文本段落组列表
    """
    def to_ms(t):
        return t * 1000 if time_unit == "s" else t

    groups: List[List[Dict]] = [[] for _ in range(len(split_timestamps_ms) + 1)]

    for seg in segments:
        end_ms = to_ms(seg["endTime"])
        placed = False
        for i, ts in enumerate(split_timestamps_ms):
            if end_ms <= ts:
                groups[i].append(seg)
                placed = True
                break
        if not placed:
            groups[-1].append(seg)

    return groups


def _normalize_timestamps(
    groups: List[List[Dict]],
    boundaries_ms: List[int],
    time_unit: str = "ms"
) -> List[List[Dict]]:
    """
    将每组文本段落的时间戳修正为从 0 开始（相对于该段音频起始时间）

    参数:
        groups: 切分后的文本段落组列表
        boundaries_ms: 各段音频起始时间列表(毫秒), 长度与 groups 相同
        time_unit: 时间戳单位, 决定偏移量的换算方式

    返回:
        时间戳修正后的文本段落组列表
    """
    result = []
    for group, start_ms in zip(groups, boundaries_ms):
        # 将毫秒偏移量转换回原始时间单位
        offset = start_ms / 1000 if time_unit == "s" else start_ms
        normalized = [
            {**seg, "beginTime": seg["beginTime"] - offset, "endTime": seg["endTime"] - offset}
            for seg in group
        ]
        result.append(normalized)
    return result


def _export_audio_segment(
    audio: AudioSegment,
    start_ms: int,
    end_ms: int,
    fmt: str = "mp3"
) -> str:
    """
    截取音频片段并转为base64

    参数:
        audio: AudioSegment对象
        start_ms: 起始时间(毫秒)
        end_ms: 结束时间(毫秒)
        fmt: 导出格式

    返回:
        base64字符串
    """
    segment = audio[start_ms:end_ms]
    buf = io.BytesIO()
    segment.export(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def split_audio_and_text(
    audio_url: str,
    segments: List[Dict],
    time_unit: str = "ms",
    audio_format: str = "mp3",
    timeout_seconds: int = 1800,
    logger: Optional[logging.Logger] = None,
    request_id: str = ""
) -> List[Dict]:
    """
    根据音频时长对音频和文本进行切分，返回三元组列表

    规则:
        - 时长 <= 1小时: 不切分，直接返回完整音频base64 + 格式化文本
        - 时长 1-2小时: 在 1/2 处向下找句子切分为 2 段
        - 时长 2-3小时: 在 1/3、2/3 处向下找句子切分为 3 段
        - 以此类推，最长支持 6 小时（切分为 6 段）

    参数:
        audio_url: 音频文件URL
        segments: 文本段落列表, 格式:
            [{"beginTime": 90, "endTime": 750, "role": 1, "text": "嗯嗯。"}]
        time_unit: 文本时间戳单位, "ms"=毫秒(默认), "s"=秒
        audio_format: 音频格式, 默认 "mp3"
        timeout_seconds: 下载超时时间(秒)
        logger: 日志记录器, 为 None 时不输出日志
        request_id: 请求ID, 用于日志追踪

    返回:
        三元组列表, 每项格式:
        {
            "part_index": int,            # 段序号（从0开始）
            "audio_base64": str,          # 音频base64
            "time_range": {               # 该段时间范围(毫秒)
                "begin_ms": int,
                "end_ms": int
            },
            "formatted_text": str         # 格式化文本 [HH:MM:SS.mmm] 角色：内容
        }
    """
    def _log(msg, level=logging.INFO):
        if logger:
            logger.log(level, f"[{request_id}] {msg}")

    _log(f"音频文本切分开始: url={audio_url[:80]}{'...' if len(audio_url) > 80 else ''}, "
         f"segments={len(segments)}, time_unit={time_unit}, audio_format={audio_format}")

    # 1. 从文本获取时长
    duration_s = get_audio_duration_from_segments(segments, time_unit)
    duration_ms = int(duration_s * 1000)
    duration_hours = duration_s / 3600.0

    # 2. 计算切分段数: <=1h -> 1段, 1-2h -> 2段, ..., >6h -> 6段
    if duration_hours <= 1.0:
        num_parts = 1
    else:
        num_parts = min(math.ceil(duration_hours), 6)

    _log(f"音频总时长 {duration_hours:.2f}h ({duration_s:.0f}s, {duration_ms}ms), 决定切分为 {num_parts} 段")

    # 3. 只有一段，直接返回
    if num_parts == 1:
        _log(f"时长不超过1小时，不切分，开始下载音频")
        audio_bytes = await download_audio(audio_url, timeout_seconds)
        _log(f"音频下载完成: {len(audio_bytes) / 1024:.1f} KB")
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        formatted_text = format_segments_to_text(segments, time_unit)
        _log(f"切分完成: 1 段, 时间范围 0ms - {duration_ms}ms, 文本行数={len(formatted_text.splitlines())}")
        return [{
            "part_index": 0,
            "audio_base64": audio_b64,
            "time_range": {"begin_ms": 0, "end_ms": duration_ms},
            "formatted_text": formatted_text
        }]

    # 4. 找切分时间戳（向下查找）
    split_timestamps_ms = _find_split_timestamps(
        segments, duration_ms, num_parts, time_unit
    )
    _log(f"切分时间戳(ms): {split_timestamps_ms}")

    # 5. 切分文本
    text_groups = _split_segments_by_timestamps(
        segments, split_timestamps_ms, time_unit
    )
    for i, group in enumerate(text_groups):
        _log(f"文本第 {i + 1}/{num_parts} 组: {len(group)} 条句子")

    # 6. 修正各段文本时间戳（从 0 开始）
    boundaries_ms = [0] + split_timestamps_ms + [duration_ms]
    text_groups = _normalize_timestamps(text_groups, boundaries_ms[:-1], time_unit)

    # 7. 下载音频并切分
    _log(f"开始下载音频: {audio_url}")
    audio_bytes = await download_audio(audio_url, timeout_seconds)
    _log(f"音频下载完成: {len(audio_bytes) / 1024:.1f} KB, 开始切分音频")
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))

    result = []
    for i in range(num_parts):
        start_ms = boundaries_ms[i]
        end_ms = boundaries_ms[i + 1]
        audio_b64 = _export_audio_segment(audio, start_ms, end_ms, audio_format)
        formatted_text = format_segments_to_text(text_groups[i], time_unit)
        _log(f"第 {i + 1}/{num_parts} 段: {start_ms}ms - {end_ms}ms "
             f"({(end_ms - start_ms) / 1000:.1f}s), "
             f"文本行数={len(formatted_text.splitlines())}, "
             f"音频大小={len(audio_b64) / 1024:.1f} KB (base64)")
        result.append({
            "part_index": i,
            "audio_base64": audio_b64,
            "time_range": {"begin_ms": start_ms, "end_ms": end_ms},
            "formatted_text": formatted_text
        })

    _log(f"音频文本切分全部完成: 共 {len(result)} 段")
    return result

