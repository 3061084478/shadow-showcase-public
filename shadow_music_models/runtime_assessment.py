from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class SystemProfile:
    model: str
    cpu_name: str
    cpu_cores: int
    cpu_threads: int
    total_ram_gb: float
    available_ram_gb: float
    gpu_name: str
    gpu_vram_gb: float


def assess_runtime(profile: SystemProfile) -> Dict[str, object]:
    has_dedicated_gpu = "nvidia" in profile.gpu_name.lower() or "rtx" in profile.gpu_name.lower()
    recommendations: List[Dict[str, str]] = []

    recommendations.append(
        {
            "component": "当前规则版 SongTagger",
            "status": "可用",
            "note": "你这台机器跑当前规则版模型没有压力。",
        }
    )
    recommendations.append(
        {
            "component": "当前规则版 PlaylistAnalyzer",
            "status": "可用",
            "note": "当前是聚合加受约束文案生成，不依赖本地大模型。",
        }
    )

    if profile.total_ram_gb >= 16 and profile.available_ram_gb >= 3.5:
        qwen8b_status = "可尝试"
        qwen8b_note = "建议只尝试 GGUF 量化版 Qwen 7B/8B，并用 llama.cpp 或 Ollama 走 CPU 推理，速度会偏慢。"
    else:
        qwen8b_status = "不建议"
        qwen8b_note = "当前可用内存偏紧，8B 文本模型会明显拖慢系统。"
    recommendations.append(
        {
            "component": "Qwen 7B/8B 文本模型",
            "status": qwen8b_status,
            "note": qwen8b_note,
        }
    )

    recommendations.append(
        {
            "component": "Qwen 14B 文本模型",
            "status": "不建议",
            "note": "16GB 内存且无独显的前提下，14B 本地推理空间太紧，体验会很差。",
        }
    )

    if has_dedicated_gpu and profile.gpu_vram_gb >= 10:
        vl_status = "可尝试"
        vl_note = "显存足够时可以评估 7B 视觉模型。"
    else:
        vl_status = "不建议"
        vl_note = "你当前没有可用独显，Qwen2.5-VL-7B 本地落地不现实。"
    recommendations.append(
        {
            "component": "Qwen2.5-VL-7B",
            "status": vl_status,
            "note": vl_note,
        }
    )

    recommendations.append(
        {
            "component": "BGE-M3",
            "status": "勉强可试",
            "note": "CPU 上可以跑，但不适合作为首发方案。更建议先上更小的 embedding 模型，或先保留规则版。",
        }
    )

    best_path = [
        "先继续用当前规则版 SongTagger 和 PlaylistAnalyzer 打通真实采集闭环。",
        "第一个真正引入的本地模型，优先放在模型二文本生成，建议从 Qwen 4B/7B/8B GGUF 量化版开始。",
        "模型一先不要急着上视觉模型，封面情绪先继续留空或走简单规则。",
        "等后面如果你换到带独显的机器，再考虑 Qwen2.5-VL-7B 和更大的文本模型。",
    ]

    return {
        "summary": {
            "has_dedicated_gpu": has_dedicated_gpu,
            "total_ram_gb": profile.total_ram_gb,
            "available_ram_gb": profile.available_ram_gb,
        },
        "recommendations": recommendations,
        "best_path": best_path,
    }
