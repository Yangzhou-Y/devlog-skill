# -*- coding: utf-8 -*-
"""各脚本共用的小工具：项目根定位、目录位置检查、证据链接处理。

不单独运行；由 check_log.py、relink.py、index_logs.py 等导入。
"""

import os
import re
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
EXTERNAL = ("http://", "https://", "mailto:", "ftp://")


def find_root(start):
    """项目根。

    顺序：最近的含 devlog/ 的祖先 > 放错位置的 docs/devlog 所在项目 > 含 .git 的
    祖先 > 起点本身。名为 docs 的目录不会被当成根，这样放进 docs/ 的日志目录能被
    识别为“放错位置”，而不是被当作另一个项目。
    """
    start = Path(start).resolve()
    chain = [start] + list(start.parents)
    misplaced_parent = None
    for p in chain:
        if (p / "devlog").is_dir():
            if p.name.lower() != "docs":
                return p
            misplaced_parent = misplaced_parent or p.parent
    if misplaced_parent:
        return misplaced_parent
    for p in chain:
        if (p / ".git").exists():
            return p
    return start


def misplaced_devlog(root):
    """返回放错位置的日志目录（docs/devlog），没有则返回 None。"""
    wrong = Path(root) / "docs" / "devlog"
    return wrong if wrong.is_dir() else None


def is_external(target):
    return target.startswith(EXTERNAL) or target.startswith("#")


def split_anchor(target):
    path, sep, anchor = target.partition("#")
    return path, (sep + anchor if sep else "")


def encode_link(path_text):
    """只转义会破坏 Markdown 链接的字符，中文保持原样。"""
    return path_text.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def resolve_target(base_dir, root, target):
    """解析链接目标，返回 (实际路径, 是否靠项目根兜底)。

    先按相对当前文件解析；失败时去掉开头的 ./ 与 ../，再按项目根解析。
    这样日志搬家（例如归档进 daily/2025/）后，链接可以被修复。
    """
    path, _ = split_anchor(target)
    path = unquote(path)
    if not path:
        return None, False
    direct = Path(base_dir) / path
    if direct.exists():
        return direct, False
    stripped = re.sub(r"^(?:\./|\.\./)+", "", path)
    if stripped:
        alt = Path(root) / stripped
        if alt.exists():
            return alt, True
    return None, False


def relative_link(base_dir, dest):
    rel = os.path.relpath(str(dest), str(base_dir)).replace("\\", "/")
    return encode_link(rel)


META_COMMENT_RE = re.compile(r"\A\s*<!--(.*?)-->[ \t]*\n?", re.S)


def _parse_kv(block):
    fm = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def meta_path_for(log_path):
    """某篇日志对应的元数据文件。

    日志在 devlog/ 下：devlog/.meta/<日期>.yml（所有层级共用一个目录）；
    否则放在日志同级的 .meta/ 里。元数据不出现在日志正文，预览时完全不可见。
    """
    log_path = Path(log_path)
    for p in log_path.parents:
        if p.name == "devlog":
            return p / ".meta" / (log_path.stem + ".yml")
    return log_path.parent / ".meta" / (log_path.stem + ".yml")


def split_inline_meta(text):
    """取出正文顶部的内联元数据（旧写法）：返回 (字典, 去掉元数据后的正文)。"""
    m = META_COMMENT_RE.match(text)
    if m:
        return _parse_kv(m.group(1)), text[m.end():].lstrip("\n")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return _parse_kv(text[3:end]), text[end + 4:].lstrip("\n")
    return {}, text


def parse_meta(text, path=None):
    """返回 (元数据字典, 正文)。

    优先读旁边的元数据文件；没有就兼容读正文顶部的内联写法
    （--- frontmatter 或 <!-- --> 注释块，不少预览器会把它们显示出来）。
    """
    inline, body = split_inline_meta(text)
    if path is not None:
        mp = meta_path_for(path)
        if mp.exists():
            data = _parse_kv(mp.read_text(encoding="utf-8"))
            data.update(inline)
            return data, body
    return inline, body


def strip_bold(s):
    """去掉标题文字两端的 ** 加粗标记。"""
    s = s.strip()
    if s.startswith("**") and s.endswith("**") and len(s) > 4:
        s = s[2:-2].strip()
    return s


def body_lines(text):
    """逐行产出 (行号, 行文本, 是否跳过)。元数据块与代码围栏内的行标记为跳过。"""
    lines = text.split("\n")
    first = lines[0].strip() if lines else ""
    in_front = first == "---"
    in_comment = first.startswith("<!--")
    in_fence = False
    for i, line in enumerate(lines):
        if in_comment:
            yield i, line, True
            if "-->" in line:
                in_comment = False
            continue
        if in_front:
            yield i, line, True
            if i > 0 and line.strip() == "---":
                in_front = False
            continue
        if FENCE_RE.match(line):
            in_fence = not in_fence
            yield i, line, True
            continue
        yield i, line, in_fence


def linkable_path(token, root):
    """反引号里的内容若是存在的项目内相对路径，返回 (路径, 锚点)，否则 None。"""
    if is_external(token) or re.match(r"^[A-Za-z]:[\\/]|^/", token):
        return None
    path, anchor = split_anchor(token)
    if not path:
        return None
    if "/" not in path and not re.search(r"\.\w{1,6}$", path):
        return None
    if (Path(root) / path).exists():
        return path, anchor
    return None


def is_link_label(line, match):
    """反引号片段是否已经是链接文字，如 [`a.log`](...)。"""
    before = line[:match.start()]
    after = line[match.end():]
    return before.endswith("[") and after.startswith("](")

