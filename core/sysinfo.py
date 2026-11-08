"""系统信息采集：操作系统、CPU、内存、磁盘、显卡、网卡。"""

import os
import platform
import socket
import subprocess
import sys
import time

import psutil

CREATE_NO_WINDOW = 0x08000000


def human_size(n):
    """字节数转成人类可读字符串。"""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def human_duration(seconds):
    """秒数转成「X 天 X 小时 X 分钟」。"""
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes and not days:
        parts.append(f"{minutes} 分钟")
    return " ".join(parts) if parts else "不到 1 分钟"


def _powershell(command, timeout=15):
    """执行一条 PowerShell 命令，返回标准输出；失败返回空串。"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _cpu_name():
    """从注册表读 CPU 型号，比 platform.processor() 精确。"""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return name.strip()
    except Exception:
        return platform.processor() or "未知处理器"


_gpu_cache = None


def _gpu_names():
    """查询显卡型号，结果缓存（硬件不会变）。"""
    global _gpu_cache
    if _gpu_cache is None:
        text = _powershell("(Get-CimInstance Win32_VideoController).Name")
        _gpu_cache = [line.strip() for line in text.splitlines() if line.strip()]
    return _gpu_cache


def _os_info():
    wv = sys.getwindowsversion()
    # Windows 11 内核构建号从 22000 起
    name = "Windows 11" if wv.build >= 22000 else "Windows 10"
    try:
        edition = platform.win32_edition()
    except Exception:
        edition = ""
    return {
        "name": name,
        "edition": edition or "",
        "version": f"{wv.major}.{wv.minor}.{wv.build}",
        "arch": platform.machine(),
    }


def _cpu_info():
    freq = psutil.cpu_freq()
    return {
        "name": _cpu_name(),
        "physical": psutil.cpu_count(logical=False) or 0,
        "logical": psutil.cpu_count(logical=True) or 0,
        "current_mhz": round(freq.current) if freq else 0,
        "max_mhz": round(freq.max) if freq else 0,
    }


def _memory_info():
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    return {
        "total": vm.total,
        "used": vm.used,
        "free": vm.available,
        "percent": vm.percent,
        "swap_total": sm.total,
        "swap_used": sm.used,
    }


def _disk_info():
    disks = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append({
            "device": part.device,
            "mount": part.mountpoint,
            "fstype": part.fstype,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": usage.percent,
        })
    return disks


def _network_info():
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    result = []
    for name, addr_list in addrs.items():
        if name.lower().startswith(("lo", "loopback")):
            continue
        stat = stats.get(name)
        if stat is not None and not stat.isup:
            continue
        ip = mac = ""
        for a in addr_list:
            if a.family == socket.AF_INET and not a.address.startswith("127."):
                ip = a.address
            elif a.family == psutil.AF_LINK:
                mac = a.address
        if not ip:
            continue
        result.append({
            "name": name,
            "ip": ip,
            "mac": mac,
            "speed": stat.speed if stat else 0,
        })
    return result


def get_system_info():
    """汇总所有系统信息，供前端一次性拉取。"""
    boot = psutil.boot_time()
    return {
        "os": _os_info(),
        "hostname": socket.gethostname(),
        "user": os.environ.get("USERNAME", ""),
        "cpu": _cpu_info(),
        "memory": _memory_info(),
        "disks": _disk_info(),
        "gpus": _gpu_names(),
        "network": _network_info(),
        "boot_time": boot,
        "uptime": human_duration(time.time() - boot),
        "python": platform.python_version(),
    }
