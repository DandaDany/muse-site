# muse-site

動畫影片日文字幕辨識與中文翻譯工具。

## 功能

- 從影片檔案（MP4、MKV、AVI 等）提取音軌
- 使用 OpenAI Whisper 辨識日文語音
- 使用 Claude API 翻譯成繁體中文
- 輸出純文字時間碼格式

## 安裝

需要先安裝 [FFmpeg](https://ffmpeg.org/download.html)。

```bash
pip install -r requirements.txt
```

## 設定 API 金鑰

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## 使用方式

```bash
# 基本用法
python transcribe.py video.mp4

# 指定輸出檔名
python transcribe.py video.mp4 -o subtitles.txt

# 使用較大模型提升辨識精準度
python transcribe.py video.mp4 --model large

# 雙語模式（同時輸出日文原文與中文翻譯）
python transcribe.py video.mp4 --bilingual

# 只辨識日文，不翻譯
python transcribe.py video.mp4 --no-translate

# 輸入為純音訊檔案
python transcribe.py audio.wav --audio-only
```

## 輸出格式

```
00:00:05 --> 00:00:10  這是翻譯後的中文字幕
00:00:11 --> 00:00:15  下一行字幕內容
```

雙語模式（`--bilingual`）：

```
00:00:05 --> 00:00:10
[日] これは字幕です
[中] 這是字幕

00:00:11 --> 00:00:15
[日] 次の字幕
[中] 下一行字幕
```

## Whisper 模型選擇

| 模型 | 速度 | 精準度 | 建議用途 |
|------|------|--------|---------|
| tiny | 最快 | 較低 | 快速測試 |
| base | 快 | 普通 | 一般用途 |
| small | 中等 | 良好 | 推薦入門 |
| medium | 稍慢 | 高 | **預設，平衡** |
| large | 慢 | 最高 | 最佳品質 |
