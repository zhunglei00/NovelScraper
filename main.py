"""
小说正文提取器 - 主程序入口
从 cool18.com 提取小说正文内容，保存成 txt 或 md 文件

使用方式：
  GUI 模式:  python main.py
  CLI 模式:  python main.py --url <URL> [--format txt|md] [--merge] [--output <DIR>]
"""

import sys
import argparse
import logging

from scraper import extract_content
from chapter_finder import find_chapter_links
from saver import save_chapters


def cli_mode(args):
    """命令行模式"""
    url = args.url
    fmt = args.format
    merge = args.merge
    output = args.output or "."
    delay = args.delay
    depth = args.depth

    chapters = []

    # 抓取入口页
    print(f"正在抓取: {url}")
    first = extract_content(url, delay=0)
    if first:
        chapters.append(first)
        print(f"  ✓ {first.title} (长度: {len(first.content)})")
    else:
        print("  ✗ 入口页抓取失败")
        return

    # 发现章节链接
    print(f"正在发现章节链接 (深度={depth})...")
    if depth <= 1:
        links = find_chapter_links(url)
    else:
        from chapter_finder import find_chapter_links_recursive

        links = find_chapter_links_recursive(url, max_depth=depth, delay=delay)

    if links:
        print(f"发现 {len(links)} 个章节链接")
        for i, link in enumerate(links, 1):
            print(f"  [{i}/{len(links)}] {link.title[:50]}")
            content = extract_content(link.url, delay=delay)
            if content:
                chapters.append(content)
                print(f"    ✓ (长度: {len(content.content)})")
            else:
                print(f"    ✗ 抓取失败")

    # 保存
    if chapters:
        novel_title = chapters[0].title.split("（")[0].split("(")[0].strip()
        paths = save_chapters(chapters, output, novel_title, fmt, merge)
        print(f"\n保存完成，共 {len(paths)} 个文件:")
        for p in paths:
            print(f"  → {p}")
    else:
        print("没有抓取到任何内容")


def main():
    parser = argparse.ArgumentParser(description="小说正文提取器 - Cool18")
    parser.add_argument("--url", "-u", help="小说页面 URL")
    parser.add_argument(
        "--format",
        "-f",
        choices=["txt", "md"],
        default="txt",
        help="保存格式 (默认: txt)",
    )
    parser.add_argument(
        "--merge", "-m", action="store_true", help="合并所有章节到一个文件"
    )
    parser.add_argument("--output", "-o", help="输出目录 (默认: 当前目录)")
    parser.add_argument(
        "--delay", "-d", type=float, default=1.0, help="请求间隔秒数 (默认: 1.0)"
    )
    parser.add_argument("--depth", type=int, default=1, help="链接发现深度 (默认: 1)")
    parser.add_argument("--gui", action="store_true", help="启动 GUI 模式")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.gui or not args.url:
        # GUI 模式
        from gui import run_gui

        run_gui()
    else:
        cli_mode(args)


if __name__ == "__main__":
    main()
