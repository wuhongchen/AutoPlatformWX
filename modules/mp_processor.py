from openai import OpenAI
from config import Config
import time
import re
import os

class DeepMPProcessor:
    """
    公众号深度增强处理器 (MP-Deep-Pro)
    目标：结构化、专业深度、完全原创长文
    """
    
    def __init__(self, api_key=None, base_url=None, feishu_client=None):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_ENDPOINT.replace("/chat/completions", "")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.feishu = feishu_client  # 用于下载飞书内部图片

    # --- 阶段一：逻辑结构分析 (Structure Analyzer) ---
    def _get_analysis_prompt(self, content):
        return f"""
你是一位深耕行业十年的顶级科技媒体主编。请对以下内容进行深度解构，为后续原创长文提供逻辑支架。

**待分析内容（节选）:**
{content}

**请严格输出 JSON 结构:**
{{
  "core_topic": "一句话概括文章核心议题",
  "technical_principles": "深入浅出解析其背后的核心技术或商业逻辑",
  "key_facts": ["核心事实1", "核心数据2"],
  "narrative_logic": ["逻辑起点", "冲突点", "深度挖掘", "行动建议"]
}}
"""

    # --- 阶段二：完全原创长文写作 (Original Deep Writer) ---
    def _get_generation_prompt(self, analysis, image_count):
        img_hint = "\n".join([f"  - [IMAGE_{i}]" for i in range(image_count)]) if image_count else "  - (本次抓取无原文配图)"
        return f"""
你是一位获过奖的深度特稿记者，擅长撰写逻辑严密、细节丰满的公众号原创长文。

**本文创作蓝图（来自主编分析）：**
{analysis}

**你可以使用的图片资源（请在正文中通过占位符调用）：**
{img_hint}

**【写作铁律：拒绝平庸，追求行业纵深】**
1. **内容饱满**：严禁简单的文字搬运。必须加入行业纵深对比、底层逻辑推演以及趋势预判。
2. **场景驱动**：用具体的“业务场景”带入，确保内容具有实战参考价值。
3. **【必须插图】**：请务必在正文的章节过渡处、核心观点解析后，插入图片占位符 `[IMAGE_N]`。至少插入 3-5 张图（如果资源充足的话）。
4. **字数与容量**：目标 1500-2500 字。内容必须扎实。
5. **去 AI 套语**：语言带有一个顶级记者的主观洞察力。不要说“总之”、“综上所述”等 AI 常用词。

**视觉排版规范（必须直接写在 HTML 标签的 style 属性中）：**
- **导读区**：使用 `<section style="background:#f8f9fa; border-radius:12px; padding:25px; margin:30px 0; border:1px solid #e9ecef;">`。
- **正文段落**：使用 `<p style="line-height:1.8; margin-bottom:20px; color:#333; text-align:justify;">`。
- **H2 章节**：使用 `<h2 style="font-size:1.4em; color:#1a1a1a; padding-bottom:10px; border-bottom:3px solid #007aff; margin-top:40px; margin-bottom:20px; display:inline-block;">`。
- **引用/点评**：使用 `<blockquote style="color:#555; background:#fffaf0; border-left:6px solid #f39c12; padding:20px; margin:30px 0; border-radius:4px;">`。
- **总结区**：使用 `<section style="background:linear-gradient(135deg, #2c3e50 0%, #34495e 100%); color:#fff; padding:35px; border-radius:15px; margin-top:50px;">`。

**文章组织结构：**
[导读区] -> [引言] -> [H2 实战分析] -> (适当位置插入 [IMAGE_N]) -> [总结区]

**注意：**
- 标题请放在第一行，带上 `【标题：...】` 标记。
- 直接输出微信公众号 HTML 源码，不要 Markdown，不要解释文字。
"""

    def process(self, url, scraped_data, publisher=None):
        """
        publisher: 可选传入 WeChatPublisher 实例，用于将正文图片上传到微信素材库
        """
        image_urls = scraped_data.get('images', [])
        
        # ── 阶段一：结构分析 ──────────
        print(f"🔍 [MP-Deep] 阶段一：主编进行深度结构分析...")
        raw_excerpt = scraped_data['content_raw'][:2000]
        analysis_resp = self.client.chat.completions.create(
            model=Config.VOLC_ARK_MODEL_ID or "doubao-seed-2-0-pro-260215",
            messages=[{"role": "user", "content": self._get_analysis_prompt(raw_excerpt)}]
        )
        analysis_map = analysis_resp.choices[0].message.content
        
        # ── 阶段二：完全原创写作 ─────────
        print(f"🖋️ [MP-Deep] 阶段二：完全原创深度长文写作 (temperature=0.92)...")
        gen_resp = self.client.chat.completions.create(
            model=Config.VOLC_ARK_MODEL_ID or "doubao-seed-2-0-pro-260215",
            messages=[{"role": "user", "content": self._get_generation_prompt(analysis_map, len(image_urls))}],
            max_tokens=4000,
            temperature=0.92
        )
        
        content_raw_output = gen_resp.choices[0].message.content
        print(f"   📊 原始生成长度: {len(content_raw_output)} 字符")
        
        # 清理 Markdown 代码块标记
        content_cleaned = re.sub(r'```(?:html|markdown)?\n?', '', content_raw_output, flags=re.IGNORECASE)
        content_cleaned = content_cleaned.replace('```', '').strip()
        
        # ── 阶段三：图片处理 ───────
        image_mapping = self._upload_images_to_wechat(image_urls, publisher)
        
        # 替换占位符
        final_content = self._post_process_content(content_cleaned, image_mapping)
        print(f"   📊 后处理后长度: {len(final_content)} 字符")
        
        # 提取标题
        title = self._get_pure_title(content_cleaned)
        
        return {
            "full_content": final_content,
            "title": title,
            "analysis": analysis_map
        }

    def _upload_images_to_wechat(self, image_urls, publisher):
        """将原文图片下载后上传至微信素材库，返回 {index: wechat_url} 映射"""
        if not publisher or not image_urls:
            return {}
        
        import requests as req
        
        if not publisher.token:
            publisher._get_token()
        if not publisher.token:
            print("   ⚠️ 微信 token 获取失败，图片将使用原文外链")
            return {i: url for i, url in enumerate(image_urls)}
        
        wechat_mapping = {}
        MIN_IMG_SIZE    = 5 * 1024   # 小于 5KB 的装饰性小图直接跳过
        max_upload_count = 12
        uploaded = 0
        
        print(f"   📸 开始处理图片，共 {len(image_urls)} 张...")
        for i, src_url in enumerate(image_urls):
            if uploaded >= max_upload_count: break
            
            try:
                img_content = None
                if str(src_url).startswith("feishu://") and self.feishu:
                    img_content = self.feishu._download_image(src_url)
                else:
                    r = req.get(src_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                    if r.status_code == 200:
                        img_content = r.content
                
                if not img_content or len(img_content) < MIN_IMG_SIZE:
                    continue
                
                # 使用 WeChatPublisher 里的新方法
                wx_url = publisher.upload_article_image(img_content)
                if wx_url:
                    wechat_mapping[i] = wx_url
                    uploaded += 1
                    print(f"      [{i+1}] ✅ 上传成功 → 微信 CDN")
                
                time.sleep(0.2)
            except Exception as e:
                print(f"      [{i+1}] ⚠️ 异常: {e}")
        
        return wechat_mapping

    def _post_process_content(self, text, image_mapping):
        """根据映射替换 [IMAGE_N] 并清除冗余标题行"""
        processed = text
        
        # 1. 移除内容体中的标题标记行 (这些用于提取 title 字段，不应出现在最终正文内)
        processed = re.sub(r'^【标题：.*?】\s*\n?', '', processed, flags=re.MULTILINE)
        processed = re.sub(r'^[标题|Title][:：].*?\n?', '', processed, flags=re.MULTILINE)
        processed = re.sub(r'^#[#\s]+.*?\n?', '', processed, flags=re.MULTILINE) # 移除可能的 Markdown H1/H2 标题行
        
        # 2. 移除 AI 可能产生的“导读”字样或空行开头
        processed = processed.lstrip()

        # 3. 替换占位符
        for i, url in image_mapping.items():
            placeholder = f"[IMAGE_{i}]"
            img_html = (
                f'<div style="text-align:center;margin:30px 0;">'
                f'<img src="{url}" style="max-width:100%;border-radius:8px;'
                f'box-shadow:0 4px 20px rgba(0,0,0,0.12);">'
                f'</div>'
            )
            processed = processed.replace(placeholder, img_html)
        
        # 4. 兜底：清除剩下的占位符
        processed = re.sub(r'\[IMAGE_\d+\]', '', processed)
        return processed.strip()

    def _get_pure_title(self, text):
        """提取纯净标题，强力清除 AI 痕迹"""
        try:
            # 基础清理
            text = re.sub(r'^【AI改后稿】\s*', '', text)
            text = re.sub(r'^[标题|Title][:：]\s*', '', text)
            
            patterns = [
                r"【标题：(.*?)】",
                r"标题：(.*?)\n",
                r"标题:(.*?)\n",
                r"## (.*?)\n",
                r"<h1[^>]*>(.*?)</h1>",
                r"<h2[^>]*>(.*?)</h2>"
            ]
            for p in patterns:
                match = re.search(p, text, re.IGNORECASE)
                if match:
                    t = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                    t = re.sub(r'^【AI改后稿】\s*', '', t)
                    if t and len(t) > 3:
                        return t
            
            # 如果没找到标记，取前几行非 HTML 的文字
            lines = text.split('\n')
            for line in lines[:10]:
                line = line.strip()
                if not line or line.startswith('<'): continue
                clean = re.sub(r'\[IMAGE_\d+\]', '', line).replace('#', '').strip()
                clean = re.sub(r'<[^>]+>', '', clean).strip()
                clean = re.sub(r'^【AI改后稿】\s*', '', clean)
                if clean and len(clean) > 5:
                    return clean
                    
            return "深度视角 | 行业精选"
        except Exception:
            return "深度视角 | 行业精选"

class WeChatFormatter:
    """自动将飞书导出的干瘪 HTML 注入具有高级呼吸感的微信公众号排版样式"""
    @staticmethod
    def deep_optimize_format(html_content):
        import re
        
        # 0. 内容清洗：强力移除开头可能出现的重复标题行
        # 匹配格式如：【标题：xxx】、标题：xxx、Title: xxx、# 标题 等
        # 注意只处理开头的几行，避免误删正文内容
        lines = html_content.split('\n')
        cleaned_lines = []
        found_content = False
        for line in lines:
            line_strip = line.strip()
            if not found_content:
                # 匹配标题模式
                is_title = (
                    re.match(r'^【.*?标题.*?】', line_strip) or 
                    re.match(r'^[标题|Title|文章标题][:：]', line_strip) or
                    re.match(r'^<h[12][^>]*>.*?</h[12]>', line_strip) or # 移除开头的 H1/H2
                    re.match(r'^#+\s+', line_strip)
                )
                if is_title:
                    continue
                if line_strip: # 遇到第一个非空且非标题的内容行
                    found_content = True
            cleaned_lines.append(line)
        
        html_content = '\n'.join(cleaned_lines).strip()

        # 1. 基础段落 (提供呼吸感和舒适的护眼行高)
        p_style = "margin-top: 15px; margin-bottom: 15px; font-size: 16px; line-height: 1.8; color: #3f3f3f; text-align: justify; letter-spacing: 0.8px; word-break: break-all;"
        html_content = re.sub(r'<p>', f'<p style="{p_style}">', html_content)
        
        # 2. 一级和二级标题 (添加醒目左边界带或渐变背景)
        h2_style = "font-size: 20px; color: #1a1a1a; padding-bottom: 8px; border-bottom: 2px solid #e1e7f0; margin-top: 45px; margin-bottom: 20px; line-height: 1.6; font-weight: bold; border-left: 5px solid #2b5cff; padding-left: 12px; display: block;"
        html_content = re.sub(r'<h[12]>', f'<h2 style="{h2_style}">', html_content)
        html_content = re.sub(r'</h[12]>', '</h2>', html_content)
        
        # 3. 三级标题
        h3_style = "font-size: 17px; color: #2c3e50; margin-top: 30px; margin-bottom: 15px; font-weight: bold; line-height: 1.6; padding-left: 8px; position: relative;"
        html_content = re.sub(r'<h3>', f'<h3 style="{h3_style}"><span style="color:#2b5cff; margin-right:5px;">▪</span>', html_content)
        
        # 4. 引用块 (导读/金句区域)
        blockquote_style = "margin: 25px 0; padding: 18px 22px; background-color: #f7f9fa; border-left: 4px solid #2c3e50; font-size: 15px; color: #5a6b7c; border-radius: 6px; line-height: 1.8; box-shadow: 0 1px 4px rgba(0,0,0,0.03);"
        html_content = re.sub(r'<blockquote>', f'<blockquote style="{blockquote_style}">', html_content)
        
        # 5. 加粗字体强化
        b_style = "font-weight: bold; color: #b83b5e;"
        html_content = re.sub(r'<b>', f'<b style="{b_style}">', html_content)
        html_content = re.sub(r'<strong>', f'<strong style="{b_style}">', html_content)
        
        # 6. 列表样式
        li_style = "margin-bottom: 10px; font-size: 16px; line-height: 1.8; color: #3f3f3f;"
        html_content = re.sub(r'<li>', f'<li style="{li_style}">', html_content)
        ul_style = "padding-left: 25px; margin-top: 10px; margin-bottom: 20px;"
        html_content = re.sub(r'<ul>', f'<ul style="{ul_style}">', html_content)
        html_content = re.sub(r'<ol>', f'<ol style="{ul_style}">', html_content)
        
        # 将整个内容包裹在一个优化过的公众号视觉容器中
        wrapper_style = "font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif; padding: 15px 18px; max-width: 677px; margin: 0 auto; background-color: #ffffff; overflow-wrap: break-word;"
        return f'<section style="{wrapper_style}">\n{html_content}\n</section>'

    @staticmethod
    def optimize_title(title):
        import re
        clean_title = re.sub(r'^【AI改后稿】\s*', '', title)
        clean_title = re.sub(r'^[标题|Title|文章标题][:：]\s*', '', clean_title)
        clean_title = re.sub(r'^#+\s*', '', clean_title)
        clean_title = clean_title.strip()
        # 尽量缩短多余的部分
        if len(clean_title) > 60:
            clean_title = clean_title.split('：')[0].split('|')[0]
        return clean_title

