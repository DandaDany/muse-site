#!/usr/bin/env python3
"""
動畫影片字幕提取工具

兩種模式：
  1. OCR 模式（--ocr）：影片已有硬字幕（中文燒錄在畫面中），用 Claude Vision 直接辨識
  2. 音訊模式（預設）：辨識日文音軌，再用 Claude API 翻譯成中文
"""

import argparse
import base64
import os
import re
import sys
import tempfile
from pathlib import Path

import anthropic
import ffmpeg
from tqdm import tqdm


def format_timecode(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ─── 音訊模式（Whisper + Claude 翻譯）────────────────────────────────────────

def _get_ffmpeg_bin() -> str:
    """優先使用系統 ffmpeg，fallback 到 imageio-ffmpeg"""
    import shutil
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        print("錯誤：找不到 ffmpeg，請安裝 ffmpeg 或執行 pip install imageio[ffmpeg]", file=sys.stderr)
        sys.exit(1)


def extract_audio(video_path: str, output_path: str) -> None:
    """從影片提取 16kHz 單聲道 WAV"""
    ffmpeg_bin = _get_ffmpeg_bin()
    ret = os.system(f'"{ffmpeg_bin}" -i "{video_path}" -ac 1 -ar 16000 -f wav "{output_path}" -y -loglevel error')
    if ret != 0:
        print("音軌提取失敗", file=sys.stderr)
        sys.exit(1)


def transcribe_japanese(audio_path: str, model_size: str = "medium") -> list[dict]:
    """Whisper 辨識日文，回傳帶時間碼的片段"""
    import whisper
    print(f"載入 Whisper 模型 ({model_size})...")
    model = whisper.load_model(model_size)
    print("辨識日文語音中...")
    result = model.transcribe(audio_path, language="ja", task="transcribe", verbose=False)
    return [
        {"start": seg["start"], "end": seg["end"], "japanese": seg["text"].strip()}
        for seg in result["segments"]
    ]


def translate_to_chinese(segments: list[dict], batch_size: int = 20) -> list[dict]:
    """Claude API 批次翻譯日文 → 繁體中文"""
    client = anthropic.Anthropic()
    translated = []
    batches = [segments[i:i + batch_size] for i in range(0, len(segments), batch_size)]
    print(f"翻譯中（共 {len(segments)} 行，分 {len(batches)} 批）...")

    for batch in tqdm(batches, unit="批"):
        lines = "\n".join(f"{i + 1}. {seg['japanese']}" for i, seg in enumerate(batch))
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": (
                    "以下是動畫字幕的日文台詞，請翻譯成流暢自然的繁體中文。\n"
                    "保持角色語氣與情感。\n"
                    "只輸出翻譯結果，格式「編號. 中文翻譯」，不要說明。\n\n"
                    f"{lines}"
                ),
            }],
        )
        result_lines = {}
        for line in msg.content[0].text.strip().splitlines():
            if ". " in line:
                num_str, _, text = line.strip().partition(". ")
                try:
                    result_lines[int(num_str)] = text.strip()
                except ValueError:
                    pass
        for i, seg in enumerate(batch):
            translated.append({**seg, "chinese": result_lines.get(i + 1, seg["japanese"])})

    return translated


# ─── OCR 模式（Claude Vision 辨識硬字幕）────────────────────────────────────

def extract_frames(video_path: str, output_dir: str, fps: float = 2.0) -> list[tuple[float, str]]:
    """每秒截 fps 張，回傳 (時間秒, 路徑) 列表"""
    ffmpeg_bin = _get_ffmpeg_bin()
    pattern = os.path.join(output_dir, "frame_%05d.jpg")
    ret = os.system(f'"{ffmpeg_bin}" -i "{video_path}" -vf "fps={fps}" "{pattern}" -y -loglevel error')
    if ret != 0:
        print("截圖失敗", file=sys.stderr)
        sys.exit(1)

    frames = []
    for p in sorted(Path(output_dir).glob("frame_*.jpg")):
        num = int(re.search(r'frame_(\d+)', p.name).group(1))
        t = num / fps
        frames.append((t, str(p)))
    return frames


def ocr_subtitles(frames: list[tuple[float, str]], batch_size: int = 12) -> list[tuple[float, str]]:
    """
    用 Claude Vision 辨識每張截圖底部的字幕文字。
    回傳 (時間秒, 字幕文字) 列表，空字幕為 ""。
    """
    client = anthropic.Anthropic()
    results: dict[int, str] = {}
    total = len(frames)

    batches = [frames[i:i + batch_size] for i in range(0, total, batch_size)]
    print(f"OCR 辨識中（共 {total} 張，分 {len(batches)} 批）...")

    for batch_idx, batch in enumerate(tqdm(batches, unit="批")):
        content = []
        for local_i, (t, path) in enumerate(batch):
            global_i = batch_idx * batch_size + local_i + 1
            img_data = base64.standard_b64encode(Path(path).read_bytes()).decode()
            content.append({"type": "text", "text": f"[{global_i}] 時間={format_timecode(t)}"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img_data},
            })

        content.append({
            "type": "text",
            "text": (
                "以上是動畫截圖。請辨識每張圖片底部的字幕文字。\n"
                "沒有字幕或字幕與上一張完全相同時回答「無」。\n"
                "格式：「[編號] 文字」，每行一個，不要說明。"
            ),
        })

        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )

        for line in msg.content[0].text.strip().splitlines():
            m = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
            if m:
                idx = int(m.group(1))
                text = m.group(2).strip()
                results[idx] = "" if text == "無" else text

    return [(t, results.get(i + 1, "")) for i, (t, _) in enumerate(frames)]


def merge_subtitle_segments(frame_results: list[tuple[float, str]], fps: float) -> list[dict]:
    """將連續相同字幕的截圖合併為一個片段"""
    segments = []
    prev_text = None
    seg_start = None
    interval = 1.0 / fps

    for t, text in frame_results:
        if text != prev_text:
            if prev_text:
                segments.append({"start": seg_start, "end": t - interval, "chinese": prev_text})
            seg_start = t if text else None
            prev_text = text

    if prev_text and seg_start is not None:
        last_t = frame_results[-1][0]
        segments.append({"start": seg_start, "end": last_t, "chinese": prev_text})

    return segments


# ─── 輸出 ─────────────────────────────────────────────────────────────────────

def write_output(segments: list[dict], output_path: str, bilingual: bool = False) -> None:
    lines = []
    for seg in segments:
        start = format_timecode(seg["start"])
        end = format_timecode(seg["end"])
        if bilingual and "japanese" in seg:
            lines.append(f"{start} --> {end}")
            lines.append(f"[日] {seg['japanese']}")
            lines.append(f"[中] {seg['chinese']}")
            lines.append("")
        else:
            lines.append(f"{start} --> {end}  {seg['chinese']}")

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n完成！輸出檔案：{output_path}")


# ─── 主程式 ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="動畫影片字幕提取工具（OCR 硬字幕 / 日文語音辨識）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式說明：
  預設       日文音軌 → Whisper 辨識 → Claude 翻譯中文
  --ocr      影片畫面已有中文硬字幕 → Claude Vision OCR 直接提取

範例：
  python transcribe.py video.mp4                    # 音訊辨識模式
  python transcribe.py video.mp4 --ocr              # OCR 硬字幕模式
  python transcribe.py video.mp4 --ocr --fps 3      # 每秒 3 張提高精準度
  python transcribe.py video.mp4 -o subtitles.txt   # 指定輸出檔名
  python transcribe.py video.mp4 --model large      # 使用大模型
  python transcribe.py video.mp4 --bilingual        # 雙語模式
        """,
    )
    parser.add_argument("input", help="輸入影片路徑")
    parser.add_argument("-o", "--output", help="輸出檔案路徑（預設：輸入檔名.txt）")
    parser.add_argument("--ocr", action="store_true", help="OCR 模式：辨識畫面中的硬字幕")
    parser.add_argument(
        "--fps", type=float, default=2.0,
        help="OCR 模式每秒截圖數（預設 2，數字越大越精準但越慢）",
    )
    parser.add_argument(
        "--model", choices=["tiny", "base", "small", "medium", "large"], default="medium",
        help="Whisper 模型大小（音訊模式用，預設 medium）",
    )
    parser.add_argument("--bilingual", action="store_true", help="雙語模式：同時輸出日文原文與中文")
    parser.add_argument("--no-translate", action="store_true", help="只辨識日文，不翻譯（音訊模式）")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"錯誤：找不到檔案 {input_path}", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY") and not args.no_translate:
        print("錯誤：請先設定 ANTHROPIC_API_KEY 環境變數", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or input_path.with_suffix(".txt").name

    with tempfile.TemporaryDirectory() as tmpdir:
        if args.ocr:
            print(f"OCR 模式：提取截圖（{args.fps} fps）...")
            frames = extract_frames(str(input_path), tmpdir, fps=args.fps)
            print(f"截圖完成，共 {len(frames)} 張")
            frame_results = ocr_subtitles(frames)
            segments = merge_subtitle_segments(frame_results, fps=args.fps)
            print(f"辨識出 {len(segments)} 個字幕片段")
        else:
            audio_path = os.path.join(tmpdir, "audio.wav")
            print(f"提取音軌：{input_path}")
            extract_audio(str(input_path), audio_path)
            segments = transcribe_japanese(audio_path, model_size=args.model)
            print(f"辨識完成，共 {len(segments)} 個片段")

            if args.no_translate:
                for seg in segments:
                    seg["chinese"] = seg["japanese"]
            else:
                segments = translate_to_chinese(segments)

        write_output(segments, output_path, bilingual=args.bilingual)


if __name__ == "__main__":
    main()
