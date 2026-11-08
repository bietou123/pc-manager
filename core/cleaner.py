"""垃圾清理：扫描并清理临时文件、缓存、回收站等。

安全原则：
- 只清理明确安全的目录，不碰用户文档、图片、下载等个人数据
- 扫描只统计不删除，交给用户确认
- 删除失败（被占用、无权限）的文件跳过而不是中断
"""

import fnmatch
import os
import subprocess

CREATE_NO_WINDOW = 0x08000000

TARGETS = [
    {
        "key": "temp_user",
        "name": "用户临时文件",
        "desc": "程序运行时产生的临时文件，可安全删除",
        "paths": [r"%TEMP%"],
    },
    {
        "key": "temp_system",
        "name": "系统临时文件",
        "desc": "Windows 系统临时目录",
        "paths": [r"C:\Windows\Temp"],
        "admin": True,
    },
    {
        "key": "prefetch",
        "name": "预读取文件",
        "desc": "加快程序启动的缓存，删除后系统会自动重建",
        "paths": [r"C:\Windows\Prefetch"],
        "admin": True,
    },
    {
        "key": "update_cache",
        "name": "Windows 更新缓存",
        "desc": "已安装更新残留的安装包",
        "paths": [r"C:\Windows\SoftwareDistribution\Download"],
        "admin": True,
    },
    {
        "key": "crash_dumps",
        "name": "崩溃转储文件",
        "desc": "程序崩溃时生成的调试文件",
        "paths": [r"%LOCALAPPDATA%\CrashDumps"],
    },
    {
        "key": "thumb_cache",
        "name": "缩略图缓存",
        "desc": "资源管理器的图片缩略图缓存",
        "paths": [r"%LOCALAPPDATA%\Microsoft\Windows\Explorer"],
        "pattern": "thumbcache_*.db",
    },
    {
        "key": "d3d_cache",
        "name": "显卡着色器缓存",
        "desc": "DirectX 着色器编译缓存，删除后游戏首次运行会稍慢",
        "paths": [r"%LOCALAPPDATA%\D3DSCache"],
    },
    {
        "key": "recycle_bin",
        "name": "回收站",
        "desc": "已删除但尚未清空的文件",
        "special": "recycle",
    },
]

_RECYCLE_DRIVES = "CDEFGH"


def _expand(path):
    return os.path.expandvars(path)


def _scan_path(path, pattern=None):
    """统计目录下的文件数量与总大小。"""
    path = _expand(path)
    if not os.path.isdir(path):
        return 0, 0
    total = 0
    count = 0
    if pattern:
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                        total += entry.stat().st_size
                        count += 1
                except OSError:
                    continue
        except OSError:
            return 0, 0
        return total, count
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
                count += 1
            except OSError:
                continue
    return total, count


def _scan_recycle():
    """统计各盘回收站占用。"""
    total = 0
    count = 0
    for letter in _RECYCLE_DRIVES:
        root = f"{letter}:\\$Recycle.Bin"
        if not os.path.isdir(root):
            continue
        for base, _dirs, files in os.walk(root, onerror=lambda e: None):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(base, name))
                    count += 1
                except OSError:
                    continue
    return total, count


def _clean_path(path, pattern=None):
    """删除目录内容，返回 (释放字节, 删除数, 跳过数)。"""
    path = _expand(path)
    if not os.path.isdir(path):
        return 0, 0, 0
    targets = []
    if pattern:
        try:
            for entry in os.scandir(path):
                if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                    targets.append(entry.path)
        except OSError:
            return 0, 0, 0
    else:
        for base, _dirs, files in os.walk(path, onerror=lambda e: None):
            for name in files:
                targets.append(os.path.join(base, name))
    freed = deleted = skipped = 0
    for file_path in targets:
        try:
            size = os.path.getsize(file_path)
            os.remove(file_path)
            freed += size
            deleted += 1
        except OSError:
            skipped += 1
    if not pattern:
        # 顺手清掉被腾空的目录
        for base, dirs, _files in os.walk(path, topdown=False, onerror=lambda e: None):
            for name in dirs:
                try:
                    os.rmdir(os.path.join(base, name))
                except OSError:
                    pass
    return freed, deleted, skipped


def _clean_recycle():
    freed, count = _scan_recycle()
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
            capture_output=True,
            timeout=120,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return 0, 0
    return freed, count


def list_targets():
    """返回可清理项目清单（不含大小）。"""
    return [
        {
            "key": t["key"],
            "name": t["name"],
            "desc": t["desc"],
            "admin": t.get("admin", False),
        }
        for t in TARGETS
    ]


def scan(keys=None):
    """扫描各清理项占用空间，返回明细与合计。"""
    selected = set(keys) if keys else None
    items = []
    total_bytes = 0
    total_files = 0
    for t in TARGETS:
        if selected is not None and t["key"] not in selected:
            continue
        if t.get("special") == "recycle":
            size, count = _scan_recycle()
        else:
            size = count = 0
            for p in t["paths"]:
                s, c = _scan_path(p, t.get("pattern"))
                size += s
                count += c
        items.append({
            "key": t["key"],
            "name": t["name"],
            "desc": t["desc"],
            "size": size,
            "files": count,
            "admin": t.get("admin", False),
        })
        total_bytes += size
        total_files += count
    return {"items": items, "total_size": total_bytes, "total_files": total_files}


def clean(keys):
    """清理指定项，返回释放量与失败统计。"""
    selected = set(keys or [])
    results = []
    total_freed = total_deleted = total_skipped = 0
    for t in TARGETS:
        if t["key"] not in selected:
            continue
        if t.get("special") == "recycle":
            freed, count = _clean_recycle()
            deleted, skipped = count, 0
        else:
            freed = deleted = skipped = 0
            for p in t["paths"]:
                f, d, s = _clean_path(p, t.get("pattern"))
                freed += f
                deleted += d
                skipped += s
        results.append({
            "key": t["key"],
            "name": t["name"],
            "freed": freed,
            "deleted": deleted,
            "skipped": skipped,
        })
        total_freed += freed
        total_deleted += deleted
        total_skipped += skipped
    return {
        "results": results,
        "total_freed": total_freed,
        "total_deleted": total_deleted,
        "total_skipped": total_skipped,
    }
