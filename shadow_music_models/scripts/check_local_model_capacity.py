from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.runtime_assessment import SystemProfile, assess_runtime


def _run_powershell_json(command: str):
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    )
    text = (result.stdout or "").strip()
    return json.loads(text) if text else {}


def _to_gb(value) -> float:
    try:
        return round(int(value) / (1024 ** 3), 1)
    except (TypeError, ValueError):
        return 0.0


def collect_system_profile() -> SystemProfile:
    computer = _run_powershell_json(
        "Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory,Model | ConvertTo-Json -Compress"
    )
    cpu = _run_powershell_json(
        "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress"
    )
    gpu_items = _run_powershell_json(
        "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
    )
    mem_counter = _run_powershell_json(
        "Get-Counter '\\Memory\\Available MBytes' | Select-Object -ExpandProperty CounterSamples | Select-Object CookedValue | ConvertTo-Json -Compress"
    )

    if isinstance(gpu_items, dict):
        gpu_list = [gpu_items]
    else:
        gpu_list = gpu_items or []

    preferred_gpu = next(
        (item for item in gpu_list if "intel" not in str(item.get("Name") or "").lower() and "virtual" not in str(item.get("Name") or "").lower()),
        None,
    )
    if preferred_gpu is None and gpu_list:
        preferred_gpu = gpu_list[-1]
    preferred_gpu = preferred_gpu or {}

    available_ram_gb = 0.0
    if isinstance(mem_counter, dict):
        available_ram_gb = round(float(mem_counter.get("CookedValue") or 0) / 1024, 1)

    return SystemProfile(
        model=str(computer.get("Model") or "").strip(),
        cpu_name=str(cpu.get("Name") or "").strip(),
        cpu_cores=int(cpu.get("NumberOfCores") or 0),
        cpu_threads=int(cpu.get("NumberOfLogicalProcessors") or 0),
        total_ram_gb=_to_gb(computer.get("TotalPhysicalMemory")),
        available_ram_gb=available_ram_gb,
        gpu_name=str(preferred_gpu.get("Name") or "").strip(),
        gpu_vram_gb=_to_gb(preferred_gpu.get("AdapterRAM")),
    )


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="检查本机是否适合承载 Shadow Music 计划里的本地模型。")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    profile = collect_system_profile()
    report = assess_runtime(profile)

    print("=== 本机概况 ===")
    print(f"机型：{profile.model or '-'}")
    print(f"CPU：{profile.cpu_name or '-'} | {profile.cpu_cores} 核 / {profile.cpu_threads} 线程")
    print(f"内存：总计 {profile.total_ram_gb} GB | 当前可用约 {profile.available_ram_gb} GB")
    print(f"显卡：{profile.gpu_name or '-'} | 显存/共享显存识别值约 {profile.gpu_vram_gb} GB")

    print("\n=== 模型承载建议 ===")
    for item in report["recommendations"]:
        print(f"- {item['component']}：{item['status']}。{item['note']}")

    print("\n=== 建议路线 ===")
    for step in report["best_path"]:
        print(f"- {step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
