"""
文件保存模块
支持 txt / md 格式，单章保存和章节合并
"""

import os
import re
import logging
from pathlib import Path

from scraper import ChapterContent

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """清理文件名：去除不合法字符"""
    # 替换 Windows 不允许的字符
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # 去除首尾空白和点号
    name = name.strip(". \t\n")
    # 截断过长文件名
    if len(name) > 200:
        name = name[:200]
    return name


def _format_chapter_md(chapter: ChapterContent) -> str:
    """将章节格式化为 Markdown"""
    lines = []
    lines.append(f"# {chapter.title}")
    if chapter.author:
        lines.append(f"\n> 作者：{chapter.author}")
    lines.append(f"\n{chapter.content}")
    return "\n".join(lines)


def _format_chapter_txt(chapter: ChapterContent) -> str:
    """将章节格式化为纯文本"""
    lines = []
    lines.append(chapter.title)
    lines.append("=" * 40)
    if chapter.author:
        lines.append(f"作者：{chapter.author}")
        lines.append("-" * 40)
    lines.append(chapter.content)
    return "\n".join(lines)


def save_chapter(
    chapter: ChapterContent,
    output_dir: str,
    fmt: str = "txt",
) -> str:
    """保存单个章节到文件

    Args:
        chapter: 章节内容
        output_dir: 输出目录
        fmt: 文件格式 "txt" 或 "md"

    Returns:
        保存的文件路径
    """
    os.makedirs(output_dir, exist_ok=True)

    filename = _sanitize_filename(chapter.title)
    ext = ".md" if fmt == "md" else ".txt"
    filepath = os.path.join(output_dir, filename + ext)

    # 避免文件名冲突
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(output_dir, f"{filename}_{counter}{ext}")
        counter += 1

    if fmt == "md":
        content = _format_chapter_md(chapter)
    else:
        content = _format_chapter_txt(chapter)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"已保存: {filepath}")
    return filepath


def save_merged(
    chapters: list[ChapterContent],
    output_dir: str,
    novel_title: str,
    fmt: str = "txt",
) -> str:
    """合并所有章节保存为单个文件

    Args:
        chapters: 章节列表
        output_dir: 输出目录
        novel_title: 小说名称
        fmt: 文件格式 "txt" 或 "md"

    Returns:
        保存的文件路径
    """
    os.makedirs(output_dir, exist_ok=True)

    filename = _sanitize_filename(novel_title)
    ext = ".md" if fmt == "md" else ".txt"
    filepath = os.path.join(output_dir, filename + "_合并" + ext)

    parts = []
    for i, chapter in enumerate(chapters, 1):
        if fmt == "md":
            parts.append(_format_chapter_md(chapter))
        else:
            parts.append(_format_chapter_txt(chapter))

    separator = "\n\n" + ("=" * 60) + "\n\n" if fmt == "txt" else "\n\n---\n\n"
    merged = separator.join(parts)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(merged)

    logger.info(f"已合并保存: {filepath}")
    return filepath


def save_chapters(
    chapters: list[ChapterContent],
    output_dir: str,
    novel_title: str,
    fmt: str = "txt",
    merge: bool = False,
) -> list[str]:
    """保存章节（自动选择合并或分开保存）

    Args:
        chapters: 章节列表
        output_dir: 输出目录
        novel_title: 小说名称
        fmt: 文件格式 "txt" 或 "md"
        merge: 是否合并为一个文件

    Returns:
        保存的文件路径列表
    """
    if merge:
        path = save_merged(chapters, output_dir, novel_title, fmt)
        return [path]
    else:
        paths = []
        for chapter in chapters:
            path = save_chapter(chapter, output_dir, fmt)
            paths.append(path)
        return paths
