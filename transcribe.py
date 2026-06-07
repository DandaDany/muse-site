#!/usr/bin/env python3
"""
動畫影片日文字幕提取工具
輸入：影片檔案（日文音軌）
輸出：純文字時間碼 + 中文字幕
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

import anthropic
import ffmpeg
import whisper
from tqdm import tqdm


def format_timecode(seconds: float) -> str:
    """將秒數轉換為 HH:MM:SS 格式"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def extract_audio(video_path: str, output_path: str) -> None:
    """從影片中提取音軌為 WAV 格式"""
    try:
        (
            ffmpeg
            .input(video_path)
            .output(output_path, ac=1, ar=16000, format="wav")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        print(f"音軌提取失敗: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)


def transcribe_japanese(audio_path: str, model_size: str = "medium") -> list[dict]:
    """使用 Whisper 辨識日文音軌，回傳帶時間碼的片段"""
    print(f"載入 Whisper 模型 ({model_size})...")
    model = whisper.load_model(model_size)

    print("辨識日文語音中...")
    result = model.transcribe(
        audio_path,
        language="ja",
        task="transcribe",
        verbose=False,
    )

    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "japanese": seg["text"].strip(),
        })
    return segments


def translate_to_chinese(segments: list[dict], batch_size: int = 20) -> list[dict]:
    """使用 Claude API 將日文片段翻譯成中文（分批處理以節省 API 呼叫次數）"""
    client = anthropic.Anthropic()

    translated = []
    batches = [segments[i:i + batch_size] for i in range(0, len(segments), batch_size)]

    print(f"翻譯日文字幕中（共 {len(segments)} 行，分 {len(batches)} 批）...")
    for batch in tqdm(batches, unit="批"):
        lines = "\n".join(
            f"{i + 1}. {seg['japanese']}"
            for i, seg in enumerate(batch)
        )

        message = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "以下是動畫字幕的日文台詞，請將每一行翻譯成流暢自然的繁體中文。\n"
                        "保持動畫角色的說話語氣與情感。\n"
                        "請只輸出翻譯結果，格式為「編號. 中文翻譯」，不要加任何說明。\n\n"
                        f"{lines}"
                    ),
                }
            ],
        )

        response_text = message.content[0].text.strip()
        translated_lines = {}
        for line in response_text.splitlines():
            line = line.strip()
            if not line:
                continue
            # 解析「1. 翻譯內容」格式
            if ". " in line:
                num_str, _, text = line.partition(". ")
                try:
                    num = int(num_str.strip())
                    translated_lines[num] = text.strip()
                except ValueError:
                    pass

        for i, seg in enumerate(batch):
            chinese = translated_lines.get(i + 1, seg["japanese"])
            translated.append({**seg, "chinese": chinese})

    return translated


def write_output(segments: list[dict], output_path: str, include_japanese: bool = False) -> None:
    """將結果寫出為純文字時間碼格式"""
    lines = []
    for seg in segments:
        start = format_timecode(seg["start"])
        end = format_timecode(seg["end"])
        if include_japanese:
            lines.append(f"{start} --> {end}")
            lines.append(f"[日] {seg['japanese']}")
            lines.append(f"[中] {seg['chinese']}")
            lines.append("")
        else:
            lines.append(f"{start} --> {end}  {seg['chinese']}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    print(f"\n完成！輸出檔案：{output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="動畫影片日文 → 中文時間碼字幕工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python transcribe.py video.mp4
  python transcribe.py video.mp4 -o subtitles.txt
  python transcribe.py video.mp4 --model large --bilingual
  python transcribe.py audio.wav --audio-only
        """,
    )
    parser.add_argument("input", help="輸入影片或音訊檔案路徑")
    parser.add_argument("-o", "--output", help="輸出檔案路徑（預設：輸入檔名.txt）")
    parser.add_argument(
        "--model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="medium",
        help="Whisper 模型大小（預設：medium）",
    )
    parser.add_argument(
        "--bilingual",
        action="store_true",
        help="雙語模式：同時輸出日文原文與中文翻譯",
    )
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="輸入為純音訊檔案，跳過音軌提取步驟",
    )
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="只辨識日文，不進行翻譯",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"錯誤：找不到檔案 {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or input_path.with_suffix(".txt").name

    with tempfile.TemporaryDirectory() as tmpdir:
        if args.audio_only:
            audio_path = str(input_path)
        else:
            audio_path = os.path.join(tmpdir, "audio.wav")
            print(f"提取音軌：{input_path}")
            extract_audio(str(input_path), audio_path)

        segments = transcribe_japanese(audio_path, model_size=args.model)
        print(f"辨識完成，共 {len(segments)} 個片段")

        if args.no_translate:
            # 只輸出日文
            for seg in segments:
                seg["chinese"] = seg["japanese"]
        else:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("警告：未設定 ANTHROPIC_API_KEY，跳過翻譯步驟", file=sys.stderr)
                for seg in segments:
                    seg["chinese"] = seg["japanese"]
            else:
                segments = translate_to_chinese(segments)

        write_output(segments, output_path, include_japanese=args.bilingual)


if __name__ == "__main__":
    main()
