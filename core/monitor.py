"""实时性能数据：CPU、内存、磁盘 IO、网络速率、TOP 进程。"""

import time

import psutil

# 上一次采样值，用于把累计量换算成每秒速率
_prev = {}
# pid -> Process，复用对象才能拿到有效的进程 CPU 百分比
_proc_cache = {}


def _rate(key, current, now):
    """根据两次采样算每秒增量。"""
    prev = _prev.get(key)
    _prev[key] = (current, now)
    if prev is None:
        return 0.0
    elapsed = now - prev[1]
    if elapsed <= 0:
        return 0.0
    return max(0.0, (current - prev[0]) / elapsed)


def _top_processes(limit):
    """按 CPU 占用排序的进程列表。

    psutil 的进程 CPU 百分比必须复用同一个 Process 对象、两次调用之间才有值，
    因此这里按 pid 缓存对象。
    """
    global _proc_cache
    cores = psutil.cpu_count() or 1
    rows = []
    fresh = {}
    for proc in psutil.process_iter(["pid", "name"]):
        pid = proc.info["pid"]
        cached = _proc_cache.get(pid)
        if cached is None:
            cached = proc
            try:
                cached.cpu_percent()
            except Exception:
                pass
        fresh[pid] = cached
        try:
            cpu = cached.cpu_percent()
            mem_pct = cached.memory_percent()
            rss = cached.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        rows.append({
            "pid": pid,
            "name": proc.info["name"] or "未知进程",
            "cpu": round(cpu / cores, 1),
            "mem": round(mem_pct, 1),
            "rss": rss,
        })
    _proc_cache = fresh
    rows.sort(key=lambda r: (r["cpu"], r["mem"]), reverse=True)
    return rows[:limit]


def _temperatures():
    """尝试读温度传感器；Windows 通常读不到，返回空列表。"""
    try:
        sensors = psutil.sensors_temperatures()
    except Exception:
        return []
    result = []
    for chip, entries in (sensors or {}).items():
        for entry in entries:
            if entry.current is not None:
                result.append({
                    "label": entry.label or chip,
                    "current": round(entry.current, 1),
                })
    return result


def get_stats(proc_limit=12):
    """采集一次实时性能快照。"""
    now = time.time()

    per_core = psutil.cpu_percent(interval=None, percpu=True)
    cpu_total = sum(per_core) / len(per_core) if per_core else 0.0
    freq = psutil.cpu_freq()

    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()

    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()

    read_rate = _rate("disk_read", disk_io.read_bytes, now) if disk_io else 0.0
    write_rate = _rate("disk_write", disk_io.write_bytes, now) if disk_io else 0.0
    up_rate = _rate("net_up", net_io.bytes_sent, now) if net_io else 0.0
    down_rate = _rate("net_down", net_io.bytes_recv, now) if net_io else 0.0

    return {
        "timestamp": now,
        "cpu": {
            "total": round(cpu_total, 1),
            "per_core": [round(x, 1) for x in per_core],
            "current_mhz": round(freq.current) if freq else 0,
            "max_mhz": round(freq.max) if freq else 0,
        },
        "memory": {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
        },
        "swap": {
            "total": sm.total,
            "used": sm.used,
            "percent": sm.percent,
        },
        "disk": {
            "read_rate": read_rate,
            "write_rate": write_rate,
            "total_read": disk_io.read_bytes if disk_io else 0,
            "total_write": disk_io.write_bytes if disk_io else 0,
        },
        "network": {
            "up_rate": up_rate,
            "down_rate": down_rate,
            "total_sent": net_io.bytes_sent if net_io else 0,
            "total_recv": net_io.bytes_recv if net_io else 0,
        },
        "temperatures": _temperatures(),
        "processes": _top_processes(proc_limit),
    }
