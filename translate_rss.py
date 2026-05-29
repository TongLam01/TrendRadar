#!/usr/bin/env python3
"""
TrendRadar 免费翻译后处理脚本
- 解析 RSS HTML 报告
- 检测英文标题 → Google 免费翻译成中文
- 输出带中文翻译的 HTML
- 零 API key 依赖
"""

import sys
import re
import os
from pathlib import Path
from html.parser import HTMLParser


class RSSTitleParser(HTMLParser):
    """解析 RSS HTML，提取每个 rss-item 的标题"""

    def __init__(self):
        super().__init__()
        self.items = []        # [(char_start, char_end, title_text, feed_name)]
        self.current_item = None
        self.current_title = ""
        self.current_feed = ""
        self.in_title = False
        self.in_feed = False
        self.char_pos = 0
        self.title_start = 0
        self._tag_stack = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        self._tag_stack.append(tag)

        if "feed-name" in cls:
            self.in_feed = True
        elif "rss-title" in cls:
            self.in_title = True
            self.title_start = self.char_pos

    def handle_endtag(self, tag):
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

        # 离开 feed-name: 抓到了当前 feed 名
        if tag in ("div", "span") and self.in_feed:
            self.in_feed = False

        # 离开 rss-title: 抓到了标题内容
        if tag in ("div", "a") and self.in_title:
            self.in_title = False
            if self.current_title.strip():
                self.items.append((
                    self.title_start,
                    self.char_pos,
                    self.current_title.strip(),
                    self.current_feed
                ))
            self.current_title = ""

    def handle_data(self, data):
        self.char_pos += len(data)
        if self.in_feed:
            self.current_feed += data
        if self.in_title:
            self.current_title += data


def is_english(text: str) -> bool:
    """判断文本是否主要为英文（ASCII > 50%）"""
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.5


def translate_text(text: str) -> str:
    """使用 deep-translator (Google 免费后端) 翻译"""
    from deep_translator import GoogleTranslator
    try:
        result = GoogleTranslator(source='en', target='zh-CN').translate(text)
        return result
    except Exception as e:
        # Google 翻译可能限制频率，返回原文
        return f"[翻译失败: {str(e)[:50]}...]"


def process_html(html_path: str, output_path: str) -> int:
    """处理 HTML 文件，为英文标题添加中文翻译"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    parser = RSSTitleParser()
    parser.feed(html)

    # 筛选需要翻译的英文标题
    to_translate = [(s, e, t, fn) for s, e, t, fn in parser.items if is_english(t)]
    if not to_translate:
        print("没有需要翻译的英文标题")
        return 0

    print(f"发现 {len(to_translate)} 条英文标题，开始翻译...")

    # 从后往前插入，避免偏移量变化
    for i, (start, end, title, feed_name) in enumerate(reversed(to_translate)):
        zh = translate_text(title)
        # 在 </a> 或 </div> 后面插入中文翻译
        insert_pos = end
        # 找到合适的插入点（</a> 之后）
        snippet = html[max(0, end-30):end+30]
        if "</a>" in snippet[:30]:
            insert_pos = end  # </a> 闭合标签后

        # 构建翻译标签
        zh_tag = f'<div class="rss-title-zh" style="font-size:13px;color:#666;margin-top:2px;">🇨🇳 {zh}</div>\n'
        html = html[:insert_pos] + zh_tag + html[insert_pos:]

        if (len(to_translate) - i) % 5 == 0:
            print(f"  进度: {len(to_translate) - i}/{len(to_translate)}")

    # 写回
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"翻译完成，保存至: {output_path}")
    return len(to_translate)


def main():
    # 默认路径（GitHub Actions 环境）
    base = Path(os.environ.get("TRENDRADAR_OUTPUT", "output"))

    # 查找最新的 RSS HTML
    html_dir = base / "html" / "latest"
    if not html_dir.exists():
        # 尝试直接找 rss 报告
        candidates = list(base.glob("rss_*.html")) + list(base.glob("html/**/*.html"))
        if not candidates:
            print("未找到 HTML 报告文件")
            return 1
        html_path = str(max(candidates, key=lambda p: p.stat().st_mtime))
    else:
        # 优先 incremental，其次 daily
        for mode in ["incremental", "daily", "current"]:
            p = html_dir / f"{mode}.html"
            if p.exists():
                html_path = str(p)
                break
        else:
            # fallback
            candidates = list(html_dir.glob("*.html"))
            if not candidates:
                print(f"未找到 HTML 文件: {html_dir}")
                return 1
            html_path = str(candidates[0])

    output_path = html_path.replace(".html", "_zh.html")
    count = process_html(html_path, output_path)

    if count > 0:
        print(f"\n完成！翻译了 {count} 条标题。")
        print(f"原文: {html_path}")
        print(f"译文: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
