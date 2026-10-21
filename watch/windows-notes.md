# Windows 部署备注（本地新增，非上游）

上游是 macOS 视角写的；这一页记录在 Windows + 中文路径环境里实际跑通需要处理的事。

## 依赖

- `ffmpeg` / `ffprobe`（Gyan 或 BtbN 静态构建，无需安装）
- `yt-dlp`（`pip install -U yt-dlp`，落在 `%APPDATA%\Python\Python311\Scripts`）
- 可选：本地 WhisperX（无字幕视频用）

## PATH 与 TEMP

Windows 上全局 PATH 可能写不进去（HKCU 不可写时 `setx` / 注册表都失败）。用一个外壳脚本补环境最省事：

```bat
set "TOOLS=D:\path\to\tools"
set "PATH=%TOOLS%\ffmpeg;%APPDATA%\Python\Python311\Scripts;%PATH%"
set "TEMP=%TOOLS%\_tmp"
set "TMP=%TOOLS%\_tmp"
python "%~dp0skills\watch\scripts\watch.py" %*
```

`TEMP` 必须可写：不可写时 `uv` 建环境会炸在 `uv-trampoline-*.exe`（os error 5），运行时也可能因临时目录失败。

## WhisperX 安装

```powershell
python "$SKILL_DIR\scripts\setup.py" --install-whisperx --detail efficient
```

- **前置检查**：`setup.py` 会先 `shutil.which('ffmpeg')` / `('yt-dlp')`，缺一个就直接退出 2 并打印安装命令。所以先把 PATH 补好。
- **uv 缓存目录**必须可写：默认 `D:\dev-cache\uv` 之类在受限机器上会被拒，设 `UV_CACHE_DIR` 指向可写盘。
- **体积**：约 3.7 GB（torch CPU wheel 590 MB + 92 个包 + small 模型 464 MB）。
- 装完写 `WATCH_WHISPERX_BIN`、`SETUP_COMPLETE=true` 到 `~/.config/watch/.env` 并生成 `.deps-ok` 哨兵；缺哨兵时运行期会拒绝启动。

## Silero VAD 离线补丁（重要）

whisperx 3.8.6 的 `whisperx/vads/silero.py` 在初始化时调用：

```python
torch.hub.load(repo_or_dir='snakers4/silero-vad', ...)
```

这一步会访问 `github.com`。网络不通时会直接抛异常；更隐蔽的情况是**误报「No active speech found in audio」**，让你以为视频没声音。

补丁（失败时回退到已预热的本地缓存）：

```python
try:
    self.vad_pipeline, vad_utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                                  model='silero_vad', force_reload=False,
                                                  onnx=False, trust_repo=True)
except Exception:
    cached = Path(torch.hub.get_dir()) / 'snakers4_silero-vad_master'
    if not (cached / 'hubconf.py').is_file():
        raise
    self.vad_pipeline, vad_utils = torch.hub.load(repo_or_dir=str(cached), source='local',
                                                  model='silero_vad', onnx=False, trust_repo=True)
```

**重装/升级 whisperx 会丢**，需要重打。

## 已知行为

- **纯音乐视频**会被 Silero 判成「无语音」（VAD 是为人声训练的），不是 bug。
- **中文口播**：`small` 模型可用，但会出现繁简混排与专名错字。要更准可在 `~/.config/watch/.env` 设 `WATCH_WHISPERX_LANGUAGE=zh`，或换 `large-v3`（2.9 GB，峰值内存约 6 GB，需重跑安装器预热）。
- **有原生字幕的视频不走转写**：`--detail transcript` 直接吃字幕，连视频都不用下载。
- **B 站**：元数据/下载/字幕都通；YouTube 在受限网络下不可达。
