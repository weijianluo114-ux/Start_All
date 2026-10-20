# -*- coding: utf-8 -*-
"""重建桌面快捷方式，指向当前构建的 exe。

由 scripts/build.bat 在构建完成后自动调用；也可手动执行：

    python scripts/update_shortcut.py "E:\\othersoftware\\start_all_app\\LaunchForge-master\\一键多启_v1.6.1.exe"

退出码：0 成功或无需处理（未装 pywin32 时跳过），1 失败。
"""
import os
import sys

NAME = "一键多启.lnk"


def main():
    if len(sys.argv) < 2:
        print("[快捷方式] 用法: python scripts/update_shortcut.py <exe路径>")
        return 2

    exe = os.path.abspath(sys.argv[1])
    if not os.path.exists(exe):
        print("[快捷方式] 目标不存在，跳过：%s" % exe)
        return 1

    try:
        from win32com.client import Dispatch
    except ImportError:
        print("[快捷方式] 未安装 pywin32，跳过自动更新（pip install pywin32 后可启用）")
        return 0

    shell = Dispatch("WScript.Shell")
    try:
        desktop = shell.SpecialFolders("Desktop")
    except Exception:
        desktop = ""
    if not desktop or not os.path.isdir(desktop):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

    lnk_path = os.path.join(desktop, NAME)
    try:
        lnk = shell.CreateShortCut(lnk_path)
        lnk.TargetPath = exe
        lnk.WorkingDirectory = os.path.dirname(exe)
        lnk.IconLocation = exe + ",0"
        lnk.Description = "一键多启 - 多预设启动器"
        lnk.Save()
    except Exception as e:
        print("[快捷方式] 创建失败：%s" % e)
        return 1

    check = shell.CreateShortCut(lnk_path)
    ok = os.path.normcase(check.TargetPath) == os.path.normcase(exe)
    print("[快捷方式] %s" % lnk_path)
    print("[快捷方式] 指向：%s（校验%s）" % (check.TargetPath, "通过" if ok else "失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
