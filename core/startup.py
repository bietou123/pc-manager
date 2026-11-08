"""启动项管理：注册表 Run 键 + 启动文件夹。

禁用不是删除——把原始信息备份到本地 JSON，随时可以还原。
"""

import json
import os
import shutil
import winreg

RUN_LOCATIONS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU\\Run", "当前用户"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU\\RunOnce", "当前用户"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM\\Run", "所有用户"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM\\RunOnce", "所有用户"),
]


def _data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "PCManager")
    os.makedirs(path, exist_ok=True)
    return path


def _disabled_dir():
    path = os.path.join(_data_dir(), "disabled_items")
    os.makedirs(path, exist_ok=True)
    return path


def _disabled_file():
    return os.path.join(_data_dir(), "disabled_startup.json")


def _load_disabled():
    try:
        with open(_disabled_file(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_disabled(data):
    with open(_disabled_file(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _startup_folders():
    folders = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        folders.append((
            "user",
            os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup"),
        ))
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        folders.append((
            "common",
            os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs\Startup"),
        ))
    return folders


def _reg_entries():
    entries = []
    for hive, subkey, location, scope in RUN_LOCATIONS:
        try:
            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
        except OSError:
            continue
        try:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                entries.append({
                    "id": f"reg|{location}|{name}",
                    "name": name,
                    "command": value,
                    "location": location,
                    "scope": scope,
                    "enabled": True,
                    "kind": "registry",
                })
                index += 1
        finally:
            winreg.CloseKey(key)
    return entries


def _folder_entries():
    entries = []
    for scope_key, folder in _startup_folders():
        if not os.path.isdir(folder):
            continue
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            entries.append({
                "id": f"folder|{path}",
                "name": os.path.splitext(name)[0],
                "command": path,
                "location": "启动文件夹",
                "scope": "当前用户" if scope_key == "user" else "所有用户",
                "enabled": True,
                "kind": "folder",
            })
    return entries


def _disabled_entries():
    entries = []
    for item_id, info in _load_disabled().items():
        entries.append({
            "id": item_id,
            "name": info.get("name", item_id),
            "command": info.get("command", ""),
            "location": info.get("location", ""),
            "scope": info.get("scope", ""),
            "enabled": False,
            "kind": info.get("kind", "registry"),
        })
    return entries


def list_startup():
    """列出全部启动项（启用 + 已禁用）。"""
    enabled = _reg_entries() + _folder_entries()
    disabled = _disabled_entries()
    enabled.sort(key=lambda e: e["name"].lower())
    disabled.sort(key=lambda e: e["name"].lower())
    return {
        "enabled": enabled,
        "disabled": disabled,
        "total": len(enabled) + len(disabled),
    }


def disable(item_id):
    """禁用一个启动项（备份后移除）。"""
    data = _load_disabled()

    if item_id.startswith("reg|"):
        parts = item_id.split("|", 2)
        if len(parts) != 3:
            return {"ok": False, "error": "无效的启动项 ID"}
        location, name = parts[1], parts[2]
        for hive, subkey, loc, scope in RUN_LOCATIONS:
            if loc != location:
                continue
            try:
                key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
            except OSError as exc:
                return {"ok": False, "error": f"无法打开注册表（可能需要管理员权限）：{exc}"}
            try:
                value, vtype = winreg.QueryValueEx(key, name)
                winreg.DeleteValue(key, name)
            except OSError as exc:
                winreg.CloseKey(key)
                return {"ok": False, "error": str(exc)}
            winreg.CloseKey(key)
            data[item_id] = {
                "kind": "registry",
                "name": name,
                "command": value,
                "location": location,
                "scope": scope,
                "vtype": vtype,
            }
            _save_disabled(data)
            return {"ok": True}
        return {"ok": False, "error": "未找到对应的注册表位置"}

    if item_id.startswith("folder|"):
        path = item_id.split("|", 1)[1]
        if not os.path.isfile(path):
            return {"ok": False, "error": "文件不存在"}
        dest = os.path.join(_disabled_dir(), os.path.basename(path))
        try:
            shutil.move(path, dest)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        data[item_id] = {
            "kind": "folder",
            "name": os.path.splitext(os.path.basename(path))[0],
            "command": path,
            "location": "启动文件夹",
            "scope": "当前用户",
        }
        _save_disabled(data)
        return {"ok": True}

    return {"ok": False, "error": "未知的启动项类型"}


def enable(item_id):
    """还原一个被禁用的启动项。"""
    data = _load_disabled()
    info = data.get(item_id)
    if not info:
        return {"ok": False, "error": "没有找到禁用记录"}

    if info.get("kind") == "registry":
        location = info.get("location")
        for hive, subkey, loc, _scope in RUN_LOCATIONS:
            if loc != location:
                continue
            try:
                key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE)
            except OSError as exc:
                return {"ok": False, "error": f"无法写入注册表（可能需要管理员权限）：{exc}"}
            try:
                winreg.SetValueEx(
                    key, info["name"], 0,
                    info.get("vtype", winreg.REG_SZ),
                    info["command"],
                )
            except OSError as exc:
                winreg.CloseKey(key)
                return {"ok": False, "error": str(exc)}
            winreg.CloseKey(key)
            break
    elif info.get("kind") == "folder":
        source = os.path.join(_disabled_dir(), os.path.basename(info["command"]))
        if not os.path.isfile(source):
            return {"ok": False, "error": "备份文件已丢失"}
        try:
            shutil.move(source, info["command"])
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    data.pop(item_id, None)
    _save_disabled(data)
    return {"ok": True}
