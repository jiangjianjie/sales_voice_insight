import asyncio
import json
import sys
import time
from pathlib import Path
import codecs

# 设置控制台编码为UTF-8
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

from services.asr_enhancer import AsrTextEnhancerService
from config import SYSTEM_CONTENT_ASR, GEMINI_MESSAGE


async def test_asr_enhancer():
    """测试 AsrTextEnhancerService 的音频文本切分和优化功能"""

    # 准备输出目录
    output_dir = Path(r"C:\Users\jjyao4\Desktop\长会话切分\音频切分结果")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("AsrTextEnhancerService 测试 - 长会话音频文本优化")
    print("=" * 80)

    # 测试数据
    audio_url = "https://icase.xfyun.cn/uploadfile/importVoice/13441/1775699249847/slice/2026_03_23_13_37_551_9060.mp3"
    text_file = r"C:\Users\jjyao4\Desktop\长会话切分\test_text2.txt"

    # 读取文本数据
    print(f"\n[1/5] 读取原始文本数据")
    print(f"  文本文件: {text_file}")

    try:
        with open(text_file, "r", encoding="gbk") as f:
            content = f.read()
        speech_list = json.loads(content)
        print(f"  ✓ 成功读取 {len(speech_list)} 条记录")
    except Exception as e:
        print(f"  ✗ 读取失败: {e}")
        return

    # 统计信息
    total_duration_ms = speech_list[-1]["endTime"]
    total_duration_s = total_duration_ms / 1000
    total_duration_hours = total_duration_s / 3600

    print(f"\n原始数据统计:")
    print(f"  - 总句数: {len(speech_list)}")
    print(f"  - 总时长: {total_duration_hours:.2f} 小时 ({total_duration_s:.0f} 秒)")
    print(f"  - 音频URL: {audio_url}")

    # 保存原始数据
    with open(output_dir / "test_asr_original.json", "w", encoding="utf-8") as f:
        json.dump(speech_list, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 原始数据已保存: test_asr_original.json")

    # 创建服务实例
    print(f"\n[2/5] 初始化 AsrTextEnhancerService")
    service = AsrTextEnhancerService(
        system_message=SYSTEM_CONTENT_ASR,
        model=GEMINI_MESSAGE["model"],
        api_key=GEMINI_MESSAGE["key"],
        base_url=GEMINI_MESSAGE["url"]
    )
    print(f"  ✓ 服务初始化完成")
    print(f"  - 模型: {GEMINI_MESSAGE['model']}")
    print(f"  - API URL: {GEMINI_MESSAGE['url']}")

    # 执行优化
    print(f"\n[3/5] 执行音频文本切分和优化")
    print(f"  开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = time.time()

    try:
        result = await service.enhance(audio_url, speech_list)
        elapsed_time = time.time() - start_time

        print(f"  ✓ 优化完成")
        print(f"  - 耗时: {elapsed_time:.1f} 秒 ({elapsed_time/60:.1f} 分钟)")
        print(f"  - 输入 tokens: {result['input_tokens']}")
        print(f"  - 输出 tokens: {result['output_tokens']}")

    except Exception as e:
        print(f"  ✗ 优化失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 分析结果
    print(f"\n[4/5] 分析优化结果")
    enhanced_speech_list = result["speech_list"]

    print(f"  - 优化后句数: {len(enhanced_speech_list)}")
    print(f"  - 原始句数: {len(speech_list)}")
    print(f"  - 句数变化: {len(enhanced_speech_list) - len(speech_list):+d}")

    # 检查时间戳连续性
    if enhanced_speech_list:
        first_time = enhanced_speech_list[0]["beginTime"]
        last_time = enhanced_speech_list[-1]["endTime"]
        print(f"  - 首句时间戳: {first_time} ms")
        print(f"  - 末句时间戳: {last_time} ms")
        print(f"  - 时间戳范围: {first_time/1000:.1f}s - {last_time/1000:.1f}s")

    # 保存优化后的数据
    print(f"\n[5/5] 保存结果")

    # 保存完整结果（JSON格式）
    with open(output_dir / "test_asr_enhanced.json", "w", encoding="utf-8") as f:
        json.dump(enhanced_speech_list, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 优化后数据已保存: test_asr_enhanced.json")

    # 保存可读格式（对比用）
    def format_speech_list(speech_list, filename):
        """将 speech_list 格式化为可读文本"""
        lines = []
        role_map = {0: "销售", 1: "客户"}
        for item in speech_list:
            begin_s = item["beginTime"] / 1000
            end_s = item["endTime"] / 1000
            role = role_map.get(item.get("role"), "未知")
            text = item.get("text", "")
            lines.append(f"[{begin_s:.3f}s - {end_s:.3f}s] {role}: {text}")

        with open(output_dir / filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    format_speech_list(speech_list, "test_asr_original_readable.txt")
    print(f"  ✓ 原始可读文本已保存: test_asr_original_readable.txt")

    format_speech_list(enhanced_speech_list, "test_asr_enhanced_readable.txt")
    print(f"  ✓ 优化可读文本已保存: test_asr_enhanced_readable.txt")

    # 生成对比报告
    report = []
    report.append("=" * 80)
    report.append("AsrTextEnhancerService 测试报告")
    report.append("=" * 80)
    report.append(f"\n测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"音频URL: {audio_url}")
    report.append(f"\n原始数据:")
    report.append(f"  - 总句数: {len(speech_list)}")
    report.append(f"  - 总时长: {total_duration_hours:.2f} 小时")
    report.append(f"\n优化结果:")
    report.append(f"  - 优化后句数: {len(enhanced_speech_list)}")
    report.append(f"  - 句数变化: {len(enhanced_speech_list) - len(speech_list):+d}")
    report.append(f"  - 处理耗时: {elapsed_time:.1f} 秒 ({elapsed_time/60:.1f} 分钟)")
    report.append(f"  - 输入 tokens: {result['input_tokens']}")
    report.append(f"  - 输出 tokens: {result['output_tokens']}")
    report.append(f"\n时间戳验证:")
    report.append(f"  - 原始首句: {speech_list[0]['beginTime']} ms")
    report.append(f"  - 原始末句: {speech_list[-1]['endTime']} ms")
    report.append(f"  - 优化首句: {enhanced_speech_list[0]['beginTime']} ms")
    report.append(f"  - 优化末句: {enhanced_speech_list[-1]['endTime']} ms")

    # 抽样对比（前5句和后5句）
    report.append(f"\n前5句对比:")
    for i in range(min(5, len(speech_list))):
        orig = speech_list[i]
        enh = enhanced_speech_list[i] if i < len(enhanced_speech_list) else None
        report.append(f"\n  原始 #{i+1}: [{orig['beginTime']/1000:.1f}s] {orig.get('text', '')}")
        if enh:
            report.append(f"  优化 #{i+1}: [{enh['beginTime']/1000:.1f}s] {enh.get('text', '')}")
        else:
            report.append(f"  优化 #{i+1}: (无对应句子)")

    report.append(f"\n后5句对比:")
    for i in range(max(0, len(speech_list) - 5), len(speech_list)):
        orig = speech_list[i]
        enh_idx = i - len(speech_list) + len(enhanced_speech_list)
        enh = enhanced_speech_list[enh_idx] if 0 <= enh_idx < len(enhanced_speech_list) else None
        report.append(f"\n  原始 #{i+1}: [{orig['beginTime']/1000:.1f}s] {orig.get('text', '')}")
        if enh:
            report.append(f"  优化 #{enh_idx+1}: [{enh['beginTime']/1000:.1f}s] {enh.get('text', '')}")
        else:
            report.append(f"  优化: (无对应句子)")

    report.append("\n" + "=" * 80)
    report.append("测试完成")
    report.append("=" * 80)

    report_text = "\n".join(report)
    print(f"\n{report_text}")

    # 保存报告
    with open(output_dir / "test_asr_report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n✓ 测试报告已保存: test_asr_report.txt")

    print(f"\n所有文件已保存到: {output_dir}")


if __name__ == "__main__":
    asyncio.run(test_asr_enhancer())
