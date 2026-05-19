"""
GUI 界面模块 - tkinter 桌面应用
支持章节拖拽排序、按文件名排序
"""

import os
import re
import threading
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from scraper import extract_content, ChapterContent
from chapter_finder import find_chapter_links, find_chapter_links_recursive
from saver import save_chapters, _sanitize_filename

logger = logging.getLogger(__name__)


class _DragSortListbox(tk.Listbox):
    """支持拖拽排序的 Listbox

    拖拽逻辑：鼠标按下选中项 → 拖动到目标位置 → 松开完成移动
    """

    def __init__(self, master, on_order_changed=None, **kwargs):
        super().__init__(master, **kwargs)
        self._drag_index = None
        self._on_order_changed = on_order_changed

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event):
        """鼠标按下：记录起始拖拽索引"""
        self._drag_index = self.nearest(event.y)
        self.selection_clear(0, tk.END)
        self.selection_set(self._drag_index)

    def _on_drag(self, event):
        """鼠标拖动：实时显示插入位置"""
        if self._drag_index is None:
            return
        target = self.nearest(event.y)
        if target == self._drag_index:
            return
        # 移动项目
        item = self.get(self._drag_index)
        self.delete(self._drag_index)
        self.insert(target, item)
        self.selection_clear(0, tk.END)
        self.selection_set(target)
        self._drag_index = target

    def _on_release(self, event):
        """鼠标松开：完成拖拽，通知排序变更"""
        if self._drag_index is not None and self._on_order_changed:
            self._on_order_changed()
        self._drag_index = None


class NovelScraperApp:
    """小说抓取器 GUI 应用"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("小说正文提取器 - Cool18")
        self.root.geometry("950x780")
        self.root.minsize(800, 650)

        # 状态变量
        self._running = False
        self._stop_requested = False
        self._chapters: list[ChapterContent] = []

        self._build_ui()

    def _build_ui(self):
        """构建界面"""
        # === 顶部：URL 输入区 ===
        input_frame = ttk.LabelFrame(self.root, text="输入网址", padding=8)
        input_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(input_frame, text="URL:").pack(side=tk.LEFT)
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(input_frame, textvariable=self.url_var, width=70)
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        url_entry.bind("<Return>", lambda e: self._on_fetch_single())

        # === 中间：选项区 ===
        option_frame = ttk.LabelFrame(self.root, text="选项", padding=8)
        option_frame.pack(fill=tk.X, padx=10, pady=5)

        # 格式选择
        fmt_frame = ttk.Frame(option_frame)
        fmt_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(fmt_frame, text="保存格式:").pack(side=tk.LEFT)
        self.fmt_var = tk.StringVar(value="txt")
        ttk.Radiobutton(fmt_frame, text="TXT", variable=self.fmt_var, value="txt").pack(
            side=tk.LEFT, padx=5
        )
        ttk.Radiobutton(fmt_frame, text="MD", variable=self.fmt_var, value="md").pack(
            side=tk.LEFT, padx=5
        )

        # 保存模式
        mode_frame = ttk.Frame(option_frame)
        mode_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(mode_frame, text="保存模式:").pack(side=tk.LEFT)
        self.merge_var = tk.StringVar(value="merge")
        ttk.Radiobutton(
            mode_frame, text="合并", variable=self.merge_var, value="merge"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(
            mode_frame, text="分章", variable=self.merge_var, value="split"
        ).pack(side=tk.LEFT, padx=5)

        # 递归深度
        depth_frame = ttk.Frame(option_frame)
        depth_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(depth_frame, text="链接发现深度:").pack(side=tk.LEFT)
        self.depth_var = tk.IntVar(value=1)
        ttk.Spinbox(
            depth_frame, from_=1, to=5, textvariable=self.depth_var, width=3
        ).pack(side=tk.LEFT, padx=5)

        # 请求延迟
        delay_frame = ttk.Frame(option_frame)
        delay_frame.pack(side=tk.LEFT)
        ttk.Label(delay_frame, text="请求间隔(秒):").pack(side=tk.LEFT)
        self.delay_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(
            delay_frame,
            from_=0.5,
            to=10,
            increment=0.5,
            textvariable=self.delay_var,
            width=4,
        ).pack(side=tk.LEFT, padx=5)

        # === 按钮区 ===
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self.fetch_btn = ttk.Button(
            btn_frame, text="抓取当前页", command=self._on_fetch_single
        )
        self.fetch_btn.pack(side=tk.LEFT, padx=5)

        self.fetch_all_btn = ttk.Button(
            btn_frame, text="抓取全部章节", command=self._on_fetch_all
        )
        self.fetch_all_btn.pack(side=tk.LEFT, padx=5)

        self.save_btn = ttk.Button(
            btn_frame, text="保存", command=self._on_save, state=tk.DISABLED
        )
        self.save_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(
            btn_frame, text="停止", command=self._on_stop, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 进度条
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=5)

        # === 中部：章节列表 + 排序控制 ===
        chapter_frame = ttk.LabelFrame(
            self.root, text="章节列表（拖拽排序 / 按钮排序）", padding=5
        )
        chapter_frame.pack(fill=tk.BOTH, padx=10, pady=5, expand=True)

        # 排序按钮行
        sort_bar = ttk.Frame(chapter_frame)
        sort_bar.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(sort_bar, text="排序:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(sort_bar, text="↑ 上移", width=8, command=self._on_move_up).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(sort_bar, text="↓ 下移", width=8, command=self._on_move_down).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(
            sort_bar, text="按标题排序", width=12, command=self._on_sort_by_title
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            sort_bar, text="按文件名排序", width=12, command=self._on_sort_by_filename
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            sort_bar, text="自然排序", width=10, command=self._on_sort_natural
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            sort_bar, text="删除选中", width=10, command=self._on_delete_selected
        ).pack(side=tk.RIGHT, padx=2)

        # 拖拽排序列表
        list_container = ttk.Frame(chapter_frame)
        list_container.pack(fill=tk.BOTH, expand=True)

        self.chapter_listbox = _DragSortListbox(
            list_container,
            on_order_changed=self._on_drag_order_changed,
            height=8,
            selectmode=tk.SINGLE,
            font=("Microsoft YaHei UI", 10),
            activestyle="none",
        )
        list_scrollbar = ttk.Scrollbar(
            list_container, orient=tk.VERTICAL, command=self.chapter_listbox.yview
        )
        self.chapter_listbox.config(yscrollcommand=list_scrollbar.set)
        self.chapter_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 点击选中时预览
        self.chapter_listbox.bind("<<ListboxSelect>>", self._on_chapter_selected)

        # === 下部：日志 + 预览 并排 ===
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.BOTH, padx=10, pady=(5, 10), expand=True)

        # 日志区
        log_frame = ttk.LabelFrame(bottom_frame, text="日志", padding=5)
        log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=8, state=tk.DISABLED, wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 预览区
        preview_frame = ttk.LabelFrame(
            bottom_frame, text="内容预览（选中章节）", padding=5
        )
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self.preview_text = scrolledtext.ScrolledText(
            preview_frame, height=8, state=tk.DISABLED, wrap=tk.WORD
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True)

    # === 章节列表管理 ===

    def _refresh_chapter_list(self):
        """根据 self._chapters 刷新列表显示"""
        self.chapter_listbox.delete(0, tk.END)
        for i, ch in enumerate(self._chapters, 1):
            self.chapter_listbox.insert(tk.END, f"  {i:>3d}. {ch.title}")

    def _sync_chapters_from_list(self):
        """根据列表框的当前顺序重建 self._chapters

        列表项格式为 "  1. 标题"，需要提取标题来匹配章节。
        """
        new_order: list[ChapterContent] = []
        for i in range(self.chapter_listbox.size()):
            text = self.chapter_listbox.get(i)
            # 提取标题部分（跳过序号）
            title = re.sub(r"^\s*\d+\.\s*", "", text)
            # 在 _chapters 中按标题匹配
            for ch in self._chapters:
                if ch.title == title and ch not in new_order:
                    new_order.append(ch)
                    break
        # 如果匹配不完整（理论上不应发生），保留未匹配的
        if len(new_order) != len(self._chapters):
            remaining = [ch for ch in self._chapters if ch not in new_order]
            new_order.extend(remaining)
        self._chapters = new_order
        self._refresh_chapter_list()

    def _on_drag_order_changed(self):
        """拖拽排序完成回调"""
        self._sync_chapters_from_list()

    def _on_chapter_selected(self, event):
        """选中章节时预览内容"""
        sel = self.chapter_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self._chapters):
            self._set_preview(self._chapters[idx].content)

    def _on_move_up(self):
        """上移选中项"""
        sel = self.chapter_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        idx = sel[0]
        self._chapters[idx - 1], self._chapters[idx] = (
            self._chapters[idx],
            self._chapters[idx - 1],
        )
        self._refresh_chapter_list()
        self.chapter_listbox.selection_set(idx - 1)

    def _on_move_down(self):
        """下移选中项"""
        sel = self.chapter_listbox.curselection()
        if not sel or sel[0] == self.chapter_listbox.size() - 1:
            return
        idx = sel[0]
        self._chapters[idx], self._chapters[idx + 1] = (
            self._chapters[idx + 1],
            self._chapters[idx],
        )
        self._refresh_chapter_list()
        self.chapter_listbox.selection_set(idx + 1)

    def _on_sort_by_title(self):
        """按标题字母排序"""
        self._chapters.sort(key=lambda ch: ch.title)
        self._refresh_chapter_list()
        self._log("已按标题排序")

    def _on_sort_by_filename(self):
        """按文件名排序（使用 saver 的文件名生成逻辑）"""
        self._chapters.sort(key=lambda ch: _sanitize_filename(ch.title))
        self._refresh_chapter_list()
        self._log("已按文件名排序")

    def _on_sort_natural(self):
        """自然排序：提取标题中的数字按数值排序

        例如 "第2章" < "第10章"（而非字典序 "第10章" < "第2章"）
        """

        def natural_key(ch: ChapterContent) -> list:
            # 将标题拆分为数字和非数字段
            parts = re.split(r"(\d+)", ch.title)
            result = []
            for p in parts:
                if p.isdigit():
                    result.append(int(p))
                else:
                    result.append(p.lower())
            return result

        self._chapters.sort(key=natural_key)
        self._refresh_chapter_list()
        self._log("已按自然排序（数字按数值大小排序）")

    def _on_delete_selected(self):
        """删除选中章节"""
        sel = self.chapter_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要删除的章节")
            return
        idx = sel[0]
        title = self._chapters[idx].title
        if messagebox.askyesno("确认删除", f"删除章节: {title[:50]}?"):
            self._chapters.pop(idx)
            self._refresh_chapter_list()
            self._log(f"已删除: {title[:50]}")

    # === 日志与预览 ===

    def _log(self, msg: str):
        """向日志区输出消息"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _set_preview(self, text: str):
        """设置预览内容"""
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", text[:5000])
        self.preview_text.config(state=tk.DISABLED)

    def _set_running(self, running: bool):
        """切换运行状态"""
        self._running = running
        self._stop_requested = False
        state_running = tk.DISABLED if running else tk.NORMAL
        state_idle = tk.NORMAL if running else tk.DISABLED
        self.fetch_btn.config(state=state_running)
        self.fetch_all_btn.config(state=state_running)
        self.stop_btn.config(state=state_idle)

    # === 操作回调 ===

    def _on_fetch_single(self):
        """抓取当前页面"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入网址")
            return

        self._set_running(True)
        self._log(f"正在抓取: {url}")

        def worker():
            try:
                content = extract_content(url, delay=0)
                if content:
                    self._chapters = [content]
                    self._log(
                        f"✓ 抓取成功: {content.title} (内容长度: {len(content.content)})"
                    )
                    self._set_preview(content.content)
                    self.root.after(0, self._refresh_chapter_list)
                    self.save_btn.config(state=tk.NORMAL)
                else:
                    self._log("✗ 抓取失败，无法提取正文内容")
            except Exception as e:
                self._log(f"✗ 错误: {e}")
            finally:
                self._set_running(False)

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_all(self):
        """抓取全部章节"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入网址")
            return

        self._chapters = []
        self._set_running(True)

        depth = self.depth_var.get()
        delay = self.delay_var.get()

        def worker():
            try:
                # 第一步：先抓取当前页
                self._log(f"正在抓取入口页: {url}")
                first_chapter = extract_content(url, delay=0)
                if first_chapter:
                    self._chapters.append(first_chapter)
                    self._log(f"✓ 入口页抓取成功: {first_chapter.title}")

                # 第二步：发现章节链接
                self._log(f"正在发现章节链接 (深度={depth})...")
                if depth <= 1:
                    links = find_chapter_links(url)
                else:
                    links = find_chapter_links_recursive(
                        url, max_depth=depth, delay=delay
                    )

                if not links:
                    self._log("未发现其他章节链接，仅保存当前页内容")
                    if first_chapter:
                        self._set_preview(first_chapter.content)
                    self.root.after(0, self._refresh_chapter_list)
                    self.save_btn.config(state=tk.NORMAL)
                    return

                self._log(f"发现 {len(links)} 个章节链接")

                # 第三步：逐个抓取
                self.progress["maximum"] = len(links)
                self.progress["value"] = 0

                for i, link in enumerate(links):
                    if self._stop_requested:
                        self._log("已停止抓取")
                        break

                    self._log(f"[{i + 1}/{len(links)}] 正在抓取: {link.title[:40]}...")
                    content = extract_content(link.url, delay=delay)
                    if content:
                        self._chapters.append(content)
                        self._log(f"  ✓ {content.title} (长度: {len(content.content)})")
                    else:
                        self._log(f"  ✗ 抓取失败: {link.title[:40]}")

                    self.progress["value"] = i + 1
                    # 实时刷新列表
                    self.root.after(0, self._refresh_chapter_list)

                if self._chapters:
                    self._set_preview(self._chapters[-1].content)
                    self.save_btn.config(state=tk.NORMAL)

                self._log(f"抓取完成，共 {len(self._chapters)} 章")

            except Exception as e:
                self._log(f"✗ 错误: {e}")
            finally:
                self._set_running(False)
                self.progress["value"] = 0

        threading.Thread(target=worker, daemon=True).start()

    def _on_save(self):
        """保存文件"""
        if not self._chapters:
            messagebox.showwarning("提示", "没有可保存的内容")
            return

        # 选择保存目录
        output_dir = filedialog.askdirectory(title="选择保存目录")
        if not output_dir:
            return

        fmt = self.fmt_var.get()
        merge = self.merge_var.get() == "merge"

        # 小说名称取第一章标题
        novel_title = self._chapters[0].title if self._chapters else "小说"
        novel_title = re.split(r"（|\(|\d+-\d+", novel_title)[0].strip()

        try:
            paths = save_chapters(
                chapters=self._chapters,
                output_dir=output_dir,
                novel_title=novel_title,
                fmt=fmt,
                merge=merge,
            )
            self._log(f"保存完成，共 {len(paths)} 个文件:")
            for p in paths:
                self._log(f"  → {p}")
            messagebox.showinfo(
                "保存成功", f"已保存 {len(paths)} 个文件到:\n{output_dir}"
            )
        except Exception as e:
            self._log(f"保存失败: {e}")
            messagebox.showerror("保存失败", str(e))

    def _on_stop(self):
        """停止抓取"""
        self._stop_requested = True
        self._log("正在停止...")


def run_gui():
    """启动 GUI"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    root = tk.Tk()
    app = NovelScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
