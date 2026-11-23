"""
统一 LLM 调用层 —— 所有模块共用此接口

API Key 读取顺序：
  1. 环境变量 MD2BOOK_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY
  2. config/default.yaml 的 ai.api_key
  3. 环境变量 MD2BOOK_API_BASE / MD2BOOK_MODEL 可覆盖 base 与模型名
"""
import json
import os
import urllib.request
import yaml
from pathlib import Path


class LLM:
    """统一的 LLM 调用封装"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / "config" / "default.yaml"
        cfg = {}
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        ai = cfg.get("ai", {})

        # Key：环境变量优先，避免把密钥写进文件
        self.api_key = (
            os.environ.get("MD2BOOK_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ai.get("api_key", "")
        )
        self.api_base = os.environ.get("MD2BOOK_API_BASE") or ai.get(
            "api_base", "https://api.deepseek.com/v1"
        )
        self.model = os.environ.get("MD2BOOK_MODEL") or ai.get("default_model", "deepseek-chat")
        self._temp = 0.55
        self._max_tok = 8000

        if not self.api_key:
            raise RuntimeError(
                "未找到 API Key。请任选其一：\n"
                "  1) 设置环境变量 MD2BOOK_API_KEY\n"
                "  2) 在 config/default.yaml 的 ai.api_key 里填写"
            )

    def call(
        self,
        system: str,
        prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """单次 LLM 调用，返回文本"""
        data = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature or self._temp,
                "max_tokens": max_tokens or self._max_tok,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
