import requests
from bs4 import BeautifulSoup
import re
import os

class ContentCollector:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/'
        }

    def fetch(self, url):
        """抓取并提取文章内容"""
        print(f"📥 正在抓取: {url}")
        try:
            # 使用会话保持状态
            session = requests.Session()
            response = session.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
            
            # 如果 403，尝试二次请求 (简单绕过)
            if response.status_code == 403:
                 print(f"⚠️ 收到 403，尝试二次抓取...")
                 response = session.get(url, headers=self.headers, timeout=self.timeout)

            response.raise_for_status()
            response.encoding = response.apparent_encoding
            html = response.text
            
            # 针对微信公众号的简单处理
            if 'mp.weixin.qq.com' in url:
                return self._parse_wechat(html)
            else:
                return self._parse_generic(html)
        except Exception as e:
            print(f"❌ 抓取失败: {e}")
            return None

    def _parse_wechat(self, html):
        """解析微信公众号文章"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 提取标题 - 移除前后空白
        title_tag = soup.find('h1', class_='rich_media_title')
        title = title_tag.get_text(strip=True) if title_tag else "无标题"
        
        # 提取作者
        author_tag = soup.find('span', class_='rich_media_meta_text')
        author = author_tag.get_text(strip=True) if author_tag else "未知作者"
        
        # 提取正文
        content_div = soup.find('div', class_='rich_media_content')
        if not content_div:
            return None
            
        # 处理图片懒加载: 将 data-src 移动到 src
        images = []
        for img in content_div.find_all('img'):
            src = img.get('data-src') or img.get('src')
            if src:
                images.append(src)
                img['src'] = src
                # 移除可能导致不显示的样式
                if img.get('style'):
                    img['style'] = img['style'].replace('visibility: hidden', '').replace('opacity: 0', '')
        
        # 移除正文容器可能存在的隐藏样式
        if content_div.get('style'):
            content_div['style'] = content_div['style'].replace('visibility: hidden', '').replace('opacity: 0', '')
            
        # 提取 HTML 结构 (Inner HTML)
        content_html = "".join([str(item) for item in content_div.contents])
        
        # 提取纯文本
        content_text = content_div.get_text(separator='\n', strip=True)
        
        return {
            'title': title,
            'author': author,
            'content_raw': content_text,
            'content_html': content_html, # 这里现在是正文内部的 HTML
            'images': images
        }

    def _parse_generic(self, html):
        """解析通用网页文章 (基础实现)"""
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.string if soup.title else "无标题"
        
        # 寻找可能的正文容器
        body = soup.find('body')
        if not body:
            return None
            
        # A. 预先提取图片（优先保全）
        img_list = []
        for img in body.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original-src') or img.get('srcset')
            if not src: continue
            if ',' in src: src = src.split(',')[0].strip().split(' ')[0]
            
            # 跳过 Base64 和 极短地址
            if src.startswith('data:') or len(src) < 20: continue
            
            # 过滤明显的图标类（通过文件名后缀和关键词）
            low_src = src.lower()
            if '.svg' in low_src or '.ico' in low_src: continue
            
            # 排除常见的 UI 占位符关键词，但要谨慎
            essential_noises = ['/avatar/', '/icon/', 'placeholder', 'pixel.gif', 'loading.gif']
            if any(k in low_src for k in essential_noises): continue
            
            if src not in img_list:
                img_list.append(src)

        # B. 降噪处理
        noise_selectors = [
            'script', 'style', 'nav', 'footer', 'iframe', 'aside',
            '.nav', '.footer', '.sidebar', '.menu', '.ad', '.ads',
            '#footer', '#sidebar', '.comment', '.comments'
        ]
        # 注意：此处不再轻易删除 'header'，因为很多文章的标题和首图在 header 里
        for selector in noise_selectors:
            for tag in body.select(selector):
                tag.decompose()
            
        # C. 提取内容 HTML
        content_html = ""
        main_content = body.find('main') or body.find('article') or body.find('div', id='content') or body.find('div', class_='content')
        if main_content:
            content_html = str(main_content)
        else:
            content_html = "".join([str(item) for item in body.contents[:100]]) # 限制一下长度

        return {
            'title': title,
            'author': "未知",
            'content_raw': body.get_text(separator='\n', strip=True),
            'content_html': content_html,
            'images': img_list[:10] # 最多保留10张
        }

if __name__ == "__main__":
    # 测试代码
    collector = ContentCollector()
    res = collector.fetch("https://mp.weixin.qq.com/s/UhQSCacrzkyxrFp2uGgzjQ")
    if res:
        print(f"成功抓取: {res['title']}")
        print(f"作者: {res['author']}")
        print(f"图片数: {len(res['images'])}")
