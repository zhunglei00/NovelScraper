# NovelScraper - 小说正文提取器

从 [cool18.com](https://www.cool18.com/bbs4/index.php) 提取小说正文内容，保存为 TXT 或 Markdown 文件。

## 功能

- **正文提取** — 输入网址，自动识别页面格式（帖子页 / 书库页），提取小说正文，去除水印、标签等非正文内容
- **多章节抓取** — 自动发现同域名下的其他章节链接，逐个抓取
- **章节排序** — 支持拖拽排序、按标题排序、按文件名排序、自然排序（第2章 < 第10章）
- **章节删除** — 去掉不需要的章节
- **保存格式** — TXT / Markdown
- **保存模式** — 单章分开保存 / 全部合并到一个文件
- **独立 EXE** — 打包为单文件可执行程序，无需安装 Python，U 盘即插即用

## 使用方式

### GUI 模式（推荐）

```bash
python main.py
```

或直接双击 `NovelScraper.exe`（在 [dist](https://github.com/zhunglei00/NovelScraper/releases) 下载）。

1. 输入小说页面 URL
2. 点击 **抓取当前页** 或 **抓取全部章节**
3. 在章节列表中排序、删除不需要的章节
4. 点击 **保存**，选择保存目录和格式

### CLI 模式

```bash
# 抓取单个页面
python main.py --url "https://www.cool18.com/bbs4/index.php?app=forum&act=threadview&tid=14567282"

# 抓取全部章节，合并保存为 Markdown
python main.py --url "https://www.cool18.com/bbs4/index.php?app=forum&act=threadview&tid=14567282" --merge --format md

# 指定输出目录和请求间隔
python main.py --url "..." --output ./novels --delay 2.0 --depth 2
```

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--url, -u` | 小说页面 URL | — |
| `--format, -f` | 保存格式：`txt` / `md` | `txt` |
| `--merge, -m` | 合并所有章节到一个文件 | 分开保存 |
| `--output, -o` | 输出目录 | 当前目录 |
| `--delay, -d` | 请求间隔秒数 | `1.0` |
| `--depth` | 链接发现深度 | `1` |
| `--gui` | 启动 GUI 模式 | 无 URL 时自动启用 |

## 项目结构

```
NovelScraper/
├── main.py             # 主程序入口（CLI + GUI 启动器）
├── scraper.py          # 核心抓取模块（网页下载 + 正文提取）
├── chapter_finder.py   # 章节链接发现模块（同域名采集）
├── saver.py            # 文件保存模块（txt/md，单章/合并）
├── gui.py              # tkinter 桌面 GUI 界面
└── .gitignore
```

## 支持的页面格式

| 页面类型 | URL 特征 | 正文位置 |
|----------|----------|----------|
| 帖子页 | `act=threadview` | `<div id="content-section">` → `<pre>` |
| 书库页 | `act=bookview` | `<td class="show_content">` → `<pre>` |

## 依赖

- Python 3.10+
- requests
- beautifulsoup4
- lxml
- tkinter（Python 自带）

```bash
pip install requests beautifulsoup4 lxml
```

## 打包为 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "NovelScraper" main.py
```

生成的 `NovelScraper.exe` 在 `dist/` 目录下，可直接双击运行，无需 Python 环境。

## License

MIT
