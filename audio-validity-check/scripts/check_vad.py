# -*- coding: utf-8 -*-
r"""阶段2：Silero VAD 判定一段音频里有没有真实语音（vs 音乐/噪音）。
用法:
  set PYTHONPATH=C:\Users\Administrator\.cache\torch\hub\snakers4_silero-vad_master
  <whisperx-venv-python> check_vad.py <16k mono wav>
输出 JSON: dur / segments / speech_s / ratio / max_seg / first
"""
import sys, os, json, wave
import torch, numpy as np

def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return torch.from_numpy(a), sr

def main():
    hub = os.environ.get("SILERO_HUB", r"C:\Users\Administrator\.cache\torch\hub\snakers4_silero-vad_master")
    model, utils = torch.hub.load(repo_or_dir=hub, model="silero_vad",
                                  source="local", onnx=False, trust_repo=True)
    gst = utils[0]
    wav, sr = read_wav(sys.argv[1])
    dur = len(wav) / sr
    ts = gst(wav, model, threshold=0.5, min_speech_duration_ms=350,
             min_silence_duration_ms=400, sampling_rate=sr)
    speech = sum((t["end"] - t["start"]) / sr for t in ts)
    print(json.dumps({
        "dur": round(dur, 1),
        "segments": len(ts),
        "speech_s": round(speech, 1),
        "ratio": round(speech / dur, 4) if dur else 0,
        "max_seg": round(max([(t["end"]-t["start"])/sr for t in ts], default=0), 1),
        "first": [{"s": round(t["start"]/sr, 1), "e": round(t["end"]/sr, 1)} for t in ts[:3]],
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
