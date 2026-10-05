"""语音活动检测（用于轨道顺序判定）/ VAD, used to tell stems apart.

这里只需要一件事：**算出一条轨里有多少语音**。门面用它判断「哪条轨是主体人声」——
这是本插件最容易出错、后果最难发现的一步（判反了就把「去掉主体人声」做成了
「去掉背景人声」）。

⚠️ 两条从 ASR 插件那边继承来的教训，直接抄在这里（`Agentic_ASR_Module/docs/issues/003`）：

1. Silero VAD **必须分块喂**：整段一次性 `accept_waveform` 会严重漏检
   （同一段 5.6 s 人声，整段喂只报 0.31 s，分块喂报 4.39 s）；
2. **必须边喂边 `pop()`**：内部是环形缓冲，喂满后早先的语音段会被挤掉。

模型缺失时回退到能量 VAD，保证功能不因少一个模型文件而失效。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from agentic_separate.core.logging import get_logger

log = get_logger("audio.vad")


def _merge(intervals: list[tuple[float, float]], gap: float
           ) -> list[tuple[float, float]]:
    if not intervals:
        return []
    out = [list(sorted(intervals)[0])]
    for start, end in sorted(intervals)[1:]:
        if start - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [(float(s), float(e)) for s, e in out]


class SpeechRatioDetector:
    """算语音占比 / compute the speech ratio of a signal."""

    def __init__(self, model_path: str | Path | None = None, sample_rate: int = 16000,
                 threshold: float = 0.5) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._vad = None
        self._tried = False

    @property
    def backend(self) -> str:
        return "silero" if (self.model_path and self.model_path.is_file()) else "energy"

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        if not (self.model_path and self.model_path.is_file()):
            log.debug("VAD 模型缺失，用能量法 / falling back to the energy method")
            return
        try:
            import sherpa_onnx

            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = str(self.model_path)
            config.silero_vad.threshold = float(self.threshold)
            config.silero_vad.min_silence_duration = 0.25
            config.silero_vad.min_speech_duration = 0.25
            config.sample_rate = self.sample_rate
            config.num_threads = 1
            config.provider = "cpu"
            if not config.validate():
                raise ValueError("VadModelConfig.validate() 返回 False")
            self._vad = sherpa_onnx.VoiceActivityDetector(
                config, buffer_size_in_seconds=300)
        except Exception as exc:  # noqa: BLE001
            log.warning("Silero VAD 初始化失败，用能量法 / init failed: %s", exc)
            self._vad = None

    def ratio(self, samples: np.ndarray, sample_rate: int) -> float:
        """语音占比（0~1）/ fraction of the audio that is speech."""
        mono = _to_mono_16k(samples, sample_rate, self.sample_rate)
        if mono.size == 0:
            return 0.0
        self._ensure()
        if self._vad is not None:
            try:
                return self._silero_ratio(mono)
            except Exception as exc:  # noqa: BLE001
                log.warning("Silero 推理失败，用能量法 / runtime failed: %s", exc)
        return self._energy_ratio(mono)

    def _silero_ratio(self, mono: np.ndarray) -> float:
        self._vad.reset()
        sr = self.sample_rate
        covered = 0.0
        raw: list[tuple[float, float]] = []

        def drain() -> None:
            while not self._vad.empty():
                seg = self._vad.front
                start = float(seg.start) / sr
                raw.append((start, start + len(seg.samples) / sr))
                self._vad.pop()

        for i in range(0, mono.size, 512):
            self._vad.accept_waveform(mono[i:i + 512])
            drain()
        self._vad.flush()
        drain()
        for s, e in _merge(raw, 0.25):
            covered += e - s
        return float(min(1.0, covered / (mono.size / sr)))

    def _energy_ratio(self, mono: np.ndarray) -> float:
        """零依赖回退 / dependency-free fallback（帧能量 + 自适应阈值）."""
        sr = self.sample_rate
        frame, hop = max(1, int(0.025 * sr)), max(1, int(0.010 * sr))
        if mono.size < frame:
            return 0.0
        n = 1 + (mono.size - frame) // hop
        idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
        rms = np.sqrt(np.mean(np.square(mono[idx].astype(np.float64)), axis=1) + 1e-12)
        thresh = max(float(np.percentile(rms, 10)) * 3.162, 1e-4)
        voiced = rms > thresh
        # 把连续有声帧折算成时间
        covered = float(voiced.sum()) * hop / sr
        return float(min(1.0, covered / (mono.size / sr)))


def _to_mono_16k(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """降到单声道；采样率不符时用线性插值（这里只判占比，精度要求不高）。"""
    data = np.asarray(samples, dtype=np.float32)
    mono = data.mean(axis=1) if data.ndim > 1 else data
    if src_sr == dst_sr or mono.size == 0:
        return np.ascontiguousarray(mono, dtype=np.float32)
    n_out = int(round(mono.size * dst_sr / src_sr))
    if n_out <= 1:
        return np.zeros(0, dtype=np.float32)
    x_old = np.linspace(0.0, 1.0, mono.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_new, x_old, mono).astype(np.float32)


__all__ = ["SpeechRatioDetector"]
