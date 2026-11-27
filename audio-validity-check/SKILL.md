---
name: audio-validity-check
description: >-
  严格判断一段录音里到底有没有"有效语音"（人讲话），而不是只有声音/音乐/噪音。
  用于决定录音能否拿去转写、原音频能否删除。三阶段：能量粗筛 → Silero VAD 神经网络判定 →
  关闭 VAD 强制转写看内容。核心教训来自一次真实误判：能量法把音乐音轨当成 7~16 分钟"语音"，
  差点删掉三份录音；Silero + 强制转写才识破循环歌词"字幕by索兰娅"。
  当用户说"这段录音有没有用""能不能删原音频""为什么转写出来是乱码/空""判断下哪些录音有效"时用。
user-invocable: true
---

# 录音有效性严格检测

**问题**：只在乎"录音里有没有人讲话"，不在乎"有没有声音"。音乐、空调、电流、键盘声都有能量，
但不是要转写的语音。判错会删掉真录音，或浪费几小时转一段音乐。

## 核心结论（先记住这个）

| 方法 | 判的是什么 | 可靠性 |
|---|---|---|
| 音量/RMS 采样 | 有没有声音 | ✗ 会被音乐/噪音骗，且采样会漏掉稀疏语音 |
| `ffmpeg silencedetect`（能量） | 有没有"非静音"段 | ✗ **只判声音不判语音**，音乐全被算成语音 |
| **Silero VAD** | 语音 vs 音乐/噪音（神经网络） | ✓ 主判据 |
| **关闭 VAD 强制转写** | 直接看 whisper 能听出什么 | ✓ 终审铁证 |

**只用能量法会翻车**：实测一份音乐音轨，`silencedetect` 报"7.4 分钟非静音"，Silero 判语音占比
0.5%，关闭 VAD 强制转写出来的是循环歌词"字幕by索兰娅"（logprob -0.02，极其确定）。

## 三阶段流程（按顺序，别跳）

### 阶段 1：能量粗筛（便宜，只用于排除真静音）

```bash
ffmpeg -hide_banner -v info -i <文件> -af silencedetect=noise=-35dB:d=0.5 -f null - 2>&1
```
- 若全文件 RMS = `-inf`、零交叉率 = 0、`silencedetect` 显示 100% 静音 → **真静音，直接判无效**。
- 否则进入阶段 2。**阶段 1 绝不能单独用来判"有语音"**（音乐会被算成满屏非静音）。

### 阶段 2：Silero VAD 神经网络判定（主判据）

参考项目：[snakers4/silero-vad](https://github.com/snakers4/silero-vad)（MIT，10k stars）。
它是训练来区分"语音 vs 噪音/音乐"的，输出每 32ms 的语音概率，支持阈值调优。
权威对比：[silero-vad 作者基准](https://github.com/amsehili/auditok/issues/32) 指出
WebRTC/能量法"擅长判静音但语音误报多"，Silero 面向语音检测。

本机运行（Windows / whisperx venv，已缓存模型）：
```powershell
$PY = "C:\Users\Administrator\.cache\watch\whisperx-venv\Scripts\python.exe"
$env:PYTHONPATH = "C:\Users\Administrator\.cache\torch\hub\snakers4_silero-vad_master"
```
脚本见 `scripts/check_vad.py`（用 `torch.hub.load(source="local")` + `wave` 读 wav，
**不要用 `read_audio`/torchaudio**——Windows 上常报 "Couldn't find appropriate backend"）。

判读（实测对照）：
- 真实会议录音：语音占比 **82–93%**，几百段
- 稀疏但有内容：占比 9%，但几百段语音 → **仍有效**，要转
- 音乐/噪音：占比 **0.2–1.5%**，最多几十段 → 疑似无效，进阶段 3

### 阶段 3：关闭 VAD 强制转写抽查（终审铁证）

仅在阶段 2 存疑时做。取前 20 分钟，**关闭 VAD 过滤**让 whisper 直接听全部音频，
看识别出的内容——这是唯一能看清"非静音到底是什么"的方法。

```python
segs, info = model.transcribe(audio, language="zh", vad_filter=False, clip_timestamps="0,1200")
```

判读：
- 连贯中文句子 → 有语音，保留
- 循环重复的固定字幕（如"字幕by索兰娅"，logprob -0.02 极确定）→ **音乐/视频音轨，无效**
- 反复乱码词 + 极低 logprob（-2.5 以下，如"0级紧密/黑木/点击打开"）→ **全是幻觉，无效**
- whisper 报 "No speech was recognized" → 与 Silero 一致，无效

脚本：`scripts/force_transcribe.py`（参数：音频、输出 md、只转前 N 秒）。
用能正常工作的 faster-whisper 环境（本机是 `D:\github_project\ZhaoWen_GitHub维护\AudioTranscriber\.venv`，
faster-whisper 1.2.1 + av 18.0.0；**不要用 watch 的 whisperx venv**，它的 av 与 faster-whisper 版本不匹配，
报 `open() got an unexpected keyword argument 'metadata_errors'`）。

## 关键教训（血泪）

1. **采样平均音量两边不讨好**：稀疏语音录音（静音占 84–92%）的 50 点采样会全落静音里，
   把真录音误判为"底噪"；而音乐录音的采样又有能量，被误判为"有语音"。**别用采样下结论。**
2. **"有能量"≠"有语音"**：音乐、电流、环境噪音都有能量。阶段 1 只用来排除真静音。
3. **强制转写要看内容不是看段数**：音乐音轨强制转写能出 70 段字，但全是循环歌词；
   看 `avg_logprob` 和文本是否连贯才能真正判断。
4. **多方法结论冲突时，用强制转写做终审**，不要靠猜。
5. **删原音频前必须三重确认**：本 skill 全流程 + 用户抽查样本 + 用户明确同意。
   small 模型本来就可能有损，删除一律走回收站，不永久删。

## 边界

- 只读分析：不改原音频、不删文件；删除由用户决定且走回收站。
- 需要 faster-whisper 环境 + Silero 缓存；首次运行可能要下载模型（约 2MB VAD / 数百 MB whisper）。
- 判定是概率性的：临界案例（低声耳语、极短语音）建议人工抽查样本再定。
