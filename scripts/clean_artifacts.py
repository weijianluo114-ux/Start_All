# -*- coding: utf-8 -*-
"""
清理构建残留：仓库根只保留当前版本的一个 exe。

背景（用户要求）：仓库根目录只允许存在**当前可用**的一个 exe。
历史版本由 GitHub Releases 保存，本地不再留重复或过期的可执行文件。
`build.bat` 里的批处理 `del` 在被占用时是静默失败的（v1.7.0 发布时就因此
残留了 v1.6.1），所以把清理做成脚本：能删的删掉，删不掉的明确指出并给原因。

清理对象（默认在仓库根）：
  1. `LaunchForge_v*.exe` —— 除 `--keep` 指定的那个之外全部删除
  2. `build/`、`dist/`     —— PyInstaller 中间产物与副本
  3. `*.spec`              —— PyInstaller 自动生成的配置

用法：
    python scripts/clean_artifacts.py --keep LaunchForge_v1.7.0.exe
    python scripts/clean_artifacts.py --dry-run          # 只看要删什么
"""
import argparse
import os
import re
import shutil
import sys

EXE_RE = re.compile(r'^LaunchForge_v(\d+(?:\.\d+)*)\.exe$', re.IGNORECASE)


def version_key(name):
    m = EXE_RE.match(name)
    if not m:
        return ()
    return tuple(int(x) for x in m.group(1).split('.'))


def find_exes(root):
    out = []
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isfile(path) and EXE_RE.match(name):
            out.append(path)
    return out


def locked_hint(path):
    """尽量指出是谁占用了文件；拿不到时给通用建议。"""
    try:
        import subprocess
        base = os.path.basename(path).lower()
        out = subprocess.run(['tasklist', '/fo', 'csv', '/nh'],
                             capture_output=True, timeout=10)
        text = out.stdout.decode('gbk', errors='ignore').lower()
        if base in text:
            return '该文件正在运行（请先关闭它再删除）'
    except Exception:
        pass
    return '文件被占用或权限不足（请关闭正在运行的实例后重试）'


def remove(path, dry_run):
    """删除文件或目录，返回 (是否成功, 说明)。"""
    if dry_run:
        return True, 'dry-run：未实际删除'
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
            return True, '已删除目录'
        os.remove(path)
        return True, '已删除'
    except Exception as e:
        return False, locked_hint(path) if os.path.isfile(path) else str(e)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description='清理仓库根的构建残留，只保留当前版本 exe')
    ap.add_argument('--root', default=root, help='仓库根目录（默认脚本上一级）')
    ap.add_argument('--keep', default=None,
                    help='要保留的 exe 文件名；省略时保留版本号最大的那个')
    ap.add_argument('--dry-run', action='store_true', help='只打印计划，不实际删除')
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    exes = find_exes(root)
    if not exes:
        print('[clean] 仓库根没有 LaunchForge_v*.exe，跳过 exe 清理')
        keep_name = args.keep
    else:
        if args.keep:
            keep_name = os.path.basename(args.keep)
            if not os.path.exists(os.path.join(root, keep_name)):
                print('[clean] 警告：--keep 指定的文件不存在：%s' % keep_name)
        else:
            keep_name = max(exes, key=lambda p: version_key(os.path.basename(p)))
            keep_name = os.path.basename(keep_name)
        print('[clean] 保留：%s' % keep_name)

    targets = []
    for path in exes:
        if os.path.basename(path).lower() != (keep_name or '').lower():
            targets.append(path)
    for name in ('build', 'dist'):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            targets.append(path)
    for name in os.listdir(root):
        if name.lower().endswith('.spec') and os.path.isfile(os.path.join(root, name)):
            targets.append(os.path.join(root, name))

    if not targets:
        print('[clean] 没有需要清理的残留')
        return 0

    failed = []
    for path in targets:
        ok, note = remove(path, args.dry_run)
        rel = os.path.relpath(path, root)
        if ok:
            print('[clean] %s → %s' % (rel, note))
        else:
            print('[clean] 失败：%s → %s' % (rel, note))
            failed.append(rel)

    if failed:
        print('[clean] 仍有 %d 项未删除：%s' % (len(failed), '、'.join(failed)))
        print('[clean] 处理方式：关闭正在运行的实例后重新执行本脚本')
        return 1

    print('[clean] 完成，仓库根只剩当前版本')
    return 0


if __name__ == '__main__':
    sys.exit(main())
