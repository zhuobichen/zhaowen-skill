# -*- coding: utf-8 -*-
r"""阶段3：关闭 VAD 强制转写抽查，看"非静音"到底是语音还是音乐/噪音。
用法:
  <AudioTranscriber venv python> force_transcribe.py <audio> <out.md> [limit_seconds]
  limit_seconds=0 表示全量。
判读：连贯中文=有效；循环固定字幕/logprob极确定=音乐；乱码词+logprob<-2.5=幻觉无效。
"""
import os, sys, time, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import faster_whisper

MODEL = os.environ.get(
    "WHISPER_MODEL",
    r"C:\Users\Administrator\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120",
)
audio = sys.argv[1]
out = sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0

print("加载模型...", flush=True)
m = faster_whisper.WhisperModel(MODEL, device="cpu", compute_type="int8")
kw = {"language": "zh", "vad_filter": False}   # 关键：关闭 VAD
if limit:
    kw["clip_timestamps"] = f"0,{limit}"
print("强制转写", ("前%d秒" % limit) if limit else "全量", flush=True)
t0 = time.time()
segs, info = m.transcribe(audio, **kw)
segs = list(segs)
print("完成: %d 段, 耗时 %.0fs" % (len(segs), time.time() - t0), flush=True)

with open(out, "w", encoding="utf-8") as f:
    f.write(f"# 强制转写（VAD关闭）：{os.path.basename(audio)}\n")
    f.write(f"时长 {info.duration:.0f}s，识别 {len(segs)} 段\n\n")
    for s in segs:
        f.write(f"[{s.start:7.1f}-{s.end:7.1f}] p={s.avg_logprob:.2f} {s.text}\n")
text = " ".join(s.text for s in segs)
han = len(re.findall(r"[\u4e00-\u9fff]", text))
avg = round(sum(s.avg_logprob for s in segs) / len(segs), 2) if segs else "n/a"
print("写出:", out, " 汉字数:", han, " 平均logprob:", avg, flush=True)
