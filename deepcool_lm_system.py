"""不依赖 USB 和界面的系统信息采集。"""

from dataclasses import dataclass
import re
import subprocess

import psutil


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

    def sample(self):
        try:
            temperatures = psutil.sensors_temperatures()
        except Exception:
            temperatures = {}

        if self._cpu_identity is None:
            self._cpu_identity = _detect_cpu_identity()
        if self._gpu_identity is None:
            self._gpu_identity = _detect_gpu_identity(temperatures)

        cpu_percent = None
        cpu_freq = None
        try:
            cpu_percent = round(psutil.cpu_percent(interval=0.1), 1)
        except Exception:
            pass

        try:
            frequency = psutil.cpu_freq()
            if frequency:
                cpu_freq = round(frequency.current / 1000, 2)
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
            gpu_temp=_read_gpu_temperature(temperatures),
        )


def _detect_cpu_identity():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
            match = re.search(r"model name\s*:\s*(.+)", cpuinfo.read())
    except OSError:
        match = None

    if not match:
        return "Unknown", "Unknown"

    full_name = match.group(1).strip()
    if "AMD" in full_name:
        model = re.sub(r"^AMD\s+", "", full_name)
        model = re.sub(r"\s+\d+-Core.*$|\s+Processor.*$", "", model)
        return "AMD", model
    if "Intel" in full_name:
        model = re.sub(r"^Intel\(R\)\s+", "", full_name)
        model = re.sub(r"Core\(TM\)\s+", "Core ", model)
        model = re.sub(r"(Xeon|Pentium|Celeron)\(R\)\s+", r"\1 ", model)
        model = re.sub(r"\s+CPU.*$|\s+@.*$", "", model)
        return "Intel", model
    return "Unknown", full_name


def _detect_gpu_identity(temperatures):
    if "amdgpu" in temperatures:
        model = _read_amd_gpu_model()
        return "AMD", model or "Radeon"

    nvidia_model = _run_first_line(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        timeout=2,
    )
    if nvidia_model:
        model = re.sub(r"^(?:NVIDIA\s+)?(?:GeForce\s+)?", "", nvidia_model)
        model = re.sub(r"^(?:Quadro|Tesla)\s+", "", model)
        return "NVIDIA", model or "NVIDIA"

    if "nouveau" in temperatures:
        return "NVIDIA", "NVIDIA"
    if "i915" in temperatures:
        return "Intel", "Integrated"
    return "Unknown", "Unknown"


def _read_amd_gpu_model():
    output = _run_command(["lspci"], timeout=5)
    if not output:
        return None

    for line in output.splitlines():
        if not ("VGA" in line or "3D controller" in line):
            continue
        if "AMD" not in line and "ATI" not in line:
            continue
        if "[Radeon " in line:
            match = re.search(r"\[Radeon\s+([^]]+)]", line)
            if match:
                return match.group(1).strip()
        model = line.split("]")[-1].strip()
        model = re.sub(r"\[.*?]", "", model).strip()
        return re.sub(r"^Radeon\s+", "", model) or None
    return None


def _read_cpu_temperature(temperatures):
    k10temp = temperatures.get("k10temp", [])
    for sensor in k10temp:
        if sensor.label in {"Tctl", "Tdie"}:
            return round(sensor.current, 1)
    if k10temp:
        return round(k10temp[0].current, 1)

    coretemp = temperatures.get("coretemp", [])
    if coretemp:
        return round(coretemp[0].current, 1)
    return None


def _read_gpu_temperature(temperatures):
    amdgpu = temperatures.get("amdgpu", [])
    if amdgpu:
        return round(amdgpu[0].current, 1)

    value = _run_first_line(
        [
            "nvidia-smi",
            "--query-gpu=temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=2,
    )
    if value:
        try:
            return round(float(value), 1)
        except ValueError:
            pass
    return None


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
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()
