"""不依赖 USB 和界面的系统信息采集。"""

from dataclasses import dataclass
import math
import os
import re
import shlex
import subprocess
import time

import psutil


_GPU_IDENTITY_RETRY_SECONDS = 60


@dataclass(frozen=True)
class SystemSnapshot:
    cpu_brand: str = "Unknown"
    cpu_model: str = "Unknown"
    cpu_temp: float = None
    cpu_percent: float = None
    cpu_freq: float = None
    gpu_brand: str = "Unknown"
    gpu_model: str = "Unknown"
    gpu_temp: float = None


class SystemMonitor:
    """采集动态指标，并缓存不常变化的硬件型号。"""

    def __init__(self):
        self._cpu_identity = None
        self._gpu_identity = None
        self._gpu_retry_at = 0

    def sample(self):
        try:
            temperatures = psutil.sensors_temperatures()
        except Exception:
            temperatures = {}

        if self._cpu_identity is None:
            self._cpu_identity = _detect_cpu_identity()
        now = time.monotonic()
        detect_gpu = self._gpu_identity is None or (
            self._gpu_identity[0] == "Unknown" and now >= self._gpu_retry_at
        )
        nvidia_gpu = None
        if detect_gpu or self._gpu_identity[0] == "NVIDIA":
            nvidia_gpu = _read_nvidia_gpu()
        if detect_gpu:
            self._gpu_identity = _detect_gpu_identity(temperatures, nvidia_gpu)
            if self._gpu_identity[0] == "Unknown":
                self._gpu_retry_at = now + _GPU_IDENTITY_RETRY_SECONDS

        cpu_percent = None
        cpu_freq = None
        try:
            cpu_percent = _normalize_percent(psutil.cpu_percent(interval=0.1))
        except Exception:
            pass

        try:
            frequency = psutil.cpu_freq()
            if frequency:
                cpu_freq = _normalize_frequency(frequency.current)
        except Exception:
            pass

        cpu_brand, cpu_model = self._cpu_identity
        gpu_brand, gpu_model = self._gpu_identity
        return SystemSnapshot(
            cpu_brand=cpu_brand,
            cpu_model=cpu_model,
            cpu_temp=_read_cpu_temperature(temperatures),
            cpu_percent=cpu_percent,
            cpu_freq=cpu_freq,
            gpu_brand=gpu_brand,
            gpu_model=gpu_model,
            gpu_temp=_read_gpu_temperature(temperatures, gpu_brand, nvidia_gpu),
        )


def _detect_cpu_identity():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
            match = re.search(r"model name\s*:\s*(.+)", cpuinfo.read())
    except OSError:
        match = None

    if not match:
        return "Unknown", "Unknown"

    return _normalize_cpu_identity(match.group(1))


def _detect_gpu_identity(temperatures, nvidia_gpu=None):
    if nvidia_gpu:
        return "NVIDIA", nvidia_gpu[0]

    identities = _read_pci_gpu_identities()
    preferred_brands = []
    if any(key in temperatures for key in ("amdgpu", "radeon")):
        preferred_brands.append("AMD")
    if "nouveau" in temperatures:
        preferred_brands.append("NVIDIA")
    if any(key in temperatures for key in ("i915", "xe")):
        preferred_brands.append("Intel")

    for brand in preferred_brands:
        identity = next((item for item in identities if item[0] == brand), None)
        if identity:
            return identity
    return identities[0] if identities else ("Unknown", "Unknown")


def _read_pci_gpu_identities():
    output = _run_command(["lspci", "-mm", "-D"], timeout=5)
    return _parse_pci_gpu_identities(output or "")


def _parse_pci_gpu_identities(output):
    identities = []
    display_classes = {
        "VGA compatible controller",
        "3D controller",
        "Display controller",
    }
    for line in output.splitlines():
        try:
            fields = shlex.split(line)
        except ValueError:
            continue
        if len(fields) < 4 or fields[1] not in display_classes:
            continue

        vendor, device = fields[2], fields[3]
        if "NVIDIA" in vendor:
            brand = "NVIDIA"
        elif "AMD" in vendor or "ATI" in vendor:
            brand = "AMD"
        elif "Intel" in vendor:
            brand = "Intel"
        else:
            continue
        identities.append((brand, _normalize_gpu_model(device, brand)))
    return identities


def _read_nvidia_gpu():
    output = _run_first_line(
        [
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=2,
    )
    if not output:
        return None

    name, separator, temperature = output.partition(",")
    model = _normalize_gpu_model(name, "NVIDIA")
    if not model:
        return None
    return model, _normalize_temperature(temperature.strip()) if separator else None


def _read_cpu_temperature(temperatures):
    k10temp = temperatures.get("k10temp", [])
    value = _temperature_by_label(k10temp, ("Tdie", "Tctl"))
    if value is not None:
        return value
    value = _highest_temperature(k10temp)
    if value is not None:
        return value

    coretemp = temperatures.get("coretemp", [])
    package = [
        sensor
        for sensor in coretemp
        if (sensor.label or "").lower().startswith(("package", "physical id"))
    ]
    return _highest_temperature(package or coretemp)


def _read_gpu_temperature(temperatures, brand, nvidia_gpu=None):
    if brand == "NVIDIA":
        if nvidia_gpu and nvidia_gpu[1] is not None:
            return nvidia_gpu[1]
        sensors = temperatures.get("nouveau", [])
        value = _temperature_by_label(sensors, ("GPU core", "GPU"))
        return value if value is not None else _first_temperature(sensors)
    if brand == "AMD":
        sensors = temperatures.get("amdgpu", []) or temperatures.get("radeon", [])
        value = _temperature_by_label(sensors, ("edge", "GPU"))
        return value if value is not None else _first_temperature(sensors)
    if brand == "Intel":
        sensors = temperatures.get("xe", []) or temperatures.get("i915", [])
        value = _temperature_by_label(sensors, ("GPU",))
        return value if value is not None else _first_temperature(sensors)
    return None


def _normalize_cpu_identity(full_name):
    name = re.sub(r"\s+", " ", (full_name or "").strip())
    if not name:
        return "Unknown", "Unknown"

    if re.search(r"\bAMD\b", name, re.I):
        brand = "AMD"
        name = re.sub(r"^AMD\s+", "", name, flags=re.I)
        name = re.sub(r"\s+(?:w/|with)\s+Radeon.*$", "", name, flags=re.I)
        name = re.sub(r"\s+\d+-Cores?(?:\s+Processor)?$", "", name, flags=re.I)
        name = re.sub(r"\s+Processor$", "", name, flags=re.I)
    elif re.search(r"\bIntel\b", name, re.I):
        brand = "Intel"
        name = re.sub(r"^\d+(?:st|nd|rd|th)\s+Gen\s+", "", name, flags=re.I)
        name = re.sub(r"^Intel(?:\(R\))?\s+", "", name, flags=re.I)
        name = re.sub(r"\b(?:Intel(?:\(R\))?\s+)", "", name, flags=re.I)
        name = re.sub(r"\((?:R|TM)\)", "", name, flags=re.I)
        name = re.sub(r"\bCPU\b\s*", "", name, flags=re.I)
        name = re.sub(r"\s+@\s+.*$", "", name)
    else:
        return "Unknown", name
    return brand, re.sub(r"\s+", " ", name).strip() or "Unknown"


def _normalize_gpu_model(model, brand):
    model = re.sub(r"\s+", " ", (model or "").strip())
    candidates = re.findall(r"\[([^]]+)]", model)
    if candidates:
        model = candidates[-1].strip()
    model = re.sub(r"^(?:NVIDIA\s+)?(?:GeForce\s+)?", "", model, flags=re.I)
    model = re.sub(r"^Intel(?:\(R\))?\s+", "", model, flags=re.I)
    if brand == "AMD":
        model = re.sub(r"^Radeon\s+(?=RX\b)", "", model, flags=re.I)
        ambiguous = re.match(r"^(RX\s+\d{4})\s+.+/.+$", model, re.I)
        if ambiguous:
            model = f"{ambiguous.group(1)} SERIES"
    return model or brand


def _temperature_by_label(sensors, labels):
    for label in labels:
        for sensor in sensors:
            if (sensor.label or "").lower() == label.lower():
                value = _normalize_temperature(sensor.current)
                if value is not None:
                    return value
    return None


def _first_temperature(sensors):
    for sensor in sensors:
        value = _normalize_temperature(sensor.current)
        if value is not None:
            return value
    return None


def _highest_temperature(sensors):
    values = [_normalize_temperature(sensor.current) for sensor in sensors]
    values = [value for value in values if value is not None]
    return max(values, default=None)


def _normalize_temperature(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not -100 <= value <= 200:
        return None
    return round(value, 1)


def _normalize_percent(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return round(value, 1)


def _normalize_frequency(value_mhz):
    try:
        value_mhz = float(value_mhz)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value_mhz) or not 0 <= value_mhz <= 100_000:
        return None
    return round(value_mhz / 1000, 2)


def _run_first_line(command, timeout):
    output = _run_command(command, timeout)
    if not output:
        return None
    return output.splitlines()[0].strip() or None


def _run_command(command, timeout):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()
