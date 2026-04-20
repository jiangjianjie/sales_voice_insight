import asyncio
import json
import sys
from pathlib import Path

# 设置控制台编码为UTF-8
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

from utils.audio_splitter import split_audio_and_text


async def test_real_case():
    """测试真实案例"""

    # 准备输出目录
    output_dir = Path(r"C:\Users\jjyao4\Desktop\长会话切分\音频切分结果")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("真实案例测试 - 音频文本切分")
    print("=" * 60)

    # 音频和文本URL
    audio_url = "https://icase.xfyun.cn/uploadfile/13582/H00PBB3KZ00F66/audio/1776051427543_fdccc8de244141b39ccc32441ddeb510.mp3"
    text_file = r"C:\Users\jjyao4\Desktop\长会话切分\test_text.txt"

    # 读取文本数据（使用GBK编码）
    print(f"\n读取文本文件: {text_file}")
    try:
        with open(text_file, "r", encoding="gbk") as f:
            content = f.read()
        segments = json.loads(content)
        print(f"✓ 成功读取 {len(segments)} 条文本记录")
    except Exception as e:
        print(f"✗ 读取失败: {e}")
        return

    # 统计信息
    total_duration_ms = segments[-1]["endTime"]
    total_duration_s = total_duration_ms / 1000
    total_duration_hours = total_duration_s / 3600

    print(f"\n数据统计:")
    print(f"  - 总句数: {len(segments)}")
    print(f"  - 总时长: {total_duration_hours:.2f} 小时 ({total_duration_s:.0f} 秒)")
    print(f"  - 最后一句时间戳: {total_duration_ms} ms")

    # 保存原始数据（UTF-8编码）
    with open(output_dir / "original_segments.json", "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 原始数据已保存: original_segments.json")

    # 执行切分
    print(f"\n开始切分处理...")
    print(f"  音频URL: {audio_url}")

    try:
        results = await split_audio_and_text(
            audio_url=audio_url,
            segments=segments,
            time_unit="ms",
            audio_format="mp3"
        )

        print(f"\n✓ 切分完成，共生成 {len(results)} 段")

        # 保存切分详细信息
        split_info = {
            "audio_url": audio_url,
            "total_duration_ms": total_duration_ms,
            "total_duration_hours": round(total_duration_hours, 2),
            "num_parts": len(results),
            "parts": []
        }

        # 处理每一段结果
        for part in results:
            part_idx = part["part_index"]
            time_range = part["time_range"]
            formatted_text = part["formatted_text"]
            audio_b64 = part["audio_base64"]

            duration_s = (time_range['end_ms'] - time_range['begin_ms']) / 1000

            print(f"\n--- 第 {part_idx + 1} 段 ---")
            print(f"  时间范围: {time_range['begin_ms']/1000:.1f}s - {time_range['end_ms']/1000:.1f}s")
            print(f"  时长: {duration_s:.1f}s ({duration_s/60:.1f}分钟)")
            print(f"  文本行数: {len(formatted_text.splitlines())}")
            print(f"  音频大小: {len(audio_b64)/1024:.1f} KB (base64)")

            # 保存音频文件
            import base64
            audio_filename = f"part_{part_idx + 1}_audio.mp3"
            with open(output_dir / audio_filename, "wb") as f:
                f.write(base64.b64decode(audio_b64))
            print(f"  ✓ 音频已保存: {audio_filename}")

            # 保存格式化文本
            text_filename = f"part_{part_idx + 1}_text.txt"
            with open(output_dir / text_filename, "w", encoding="utf-8") as f:
                f.write(formatted_text)
            print(f"  ✓ 文本已保存: {text_filename}")

            # 记录切分信息
            split_info["parts"].append({
                "part_index": part_idx,
                "time_range_ms": time_range,
                "duration_seconds": round(duration_s, 1),
                "duration_minutes": round(duration_s / 60, 1),
                "text_lines": len(formatted_text.splitlines()),
                "audio_file": audio_filename,
                "text_file": text_filename,
                "audio_size_kb": round(len(audio_b64) / 1024, 1)
            })

        # 保存切分详细信息
        with open(output_dir / "split_info.json", "w", encoding="utf-8") as f:
            json.dump(split_info, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 切分详细信息已保存: split_info.json")

        # 生成汇总报告
        report = []
        report.append("=" * 60)
        report.append("音频文本切分测试报告")
        report.append("=" * 60)
        report.append(f"\n音频URL: {audio_url}")
        report.append(f"总时长: {total_duration_hours:.2f} 小时 ({total_duration_s:.0f} 秒)")
        report.append(f"切分段数: {len(results)} 段")
        report.append(f"\n各段详情:")

        for info in split_info["parts"]:
            report.append(f"\n第 {info['part_index'] + 1} 段:")
            report.append(f"  时间: {info['time_range_ms']['begin_ms']/1000:.1f}s - {info['time_range_ms']['end_ms']/1000:.1f}s")
            report.append(f"  时长: {info['duration_minutes']:.1f} 分钟")
            report.append(f"  文本行数: {info['text_lines']}")
            report.append(f"  音频文件: {info['audio_file']} ({info['audio_size_kb']} KB)")
            report.append(f"  文本文件: {info['text_file']}")

        report.append("\n" + "=" * 60)
        report.append("测试完成！")
        report.append("=" * 60)

        report_text = "\n".join(report)
        print(f"\n{report_text}")

        # 保存报告
        with open(output_dir / "report.txt", "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"\n✓ 测试报告已保存: report.txt")

        print(f"\n所有文件已保存到: {output_dir}")

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_real_case())
