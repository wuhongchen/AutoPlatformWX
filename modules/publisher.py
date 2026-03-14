import requests
import json
import os
import tempfile
import re

class WeChatPublisher:
    def __init__(self, appid, secret, author='W'):
        self.appid = appid
        self.secret = secret
        self.author = author
        self.token = None

    def _get_token(self):
        """获取 access_token"""
        print("🔑 获取微信 access_token...")
        url = f'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={self.appid}&secret={self.secret}'
        try:
            resp = requests.get(url, timeout=30).json()
            if 'access_token' in resp:
                self.token = resp['access_token']
                return True
            print(f"❌ 获取 token 失败：{resp}")
            return False
        except Exception as e:
            print(f"❌ 获取 token 异常：{e}")
            return False

    def upload_from_url(self, url):
        """从 URL 下载并上传素材"""
        if not url:
            return None
        print(f"📷 从 URL 下载封面: {url}")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                f.write(resp.content)
                temp_path = f.name
            
            media_id = self.upload_material(temp_path)
            try:
                os.unlink(temp_path)
            except:
                pass
            return media_id
        except Exception as e:
            print(f"❌ 从 URL 上传失败: {e}")
            return None

    def upload_material(self, media_path, media_type='image'):
        """上传素材并获取 media_id"""
        if not self.token and not self._get_token():
            return None
            
        print(f"📤 上传素材: {media_path}")
        url = f'https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={self.token}&type={media_type}'
        try:
            with open(media_path, 'rb') as f:
                files = {'media': (os.path.basename(media_path), f)}
                resp = requests.post(url, files=files, timeout=60).json()
                
            if 'media_id' in resp:
                return resp['media_id']
            print(f"❌ 上传失败: {resp}")
            return None
        except Exception as e:
            print(f"❌ 上传异常: {e}")
            return None

    def upload_article_image(self, image_bytes, is_retry=False):
        """上传文章正文内的图片（不占用永久素材额度），返回微信 URL。带自动 Token 重试机制。"""
        if not self.token and not self._get_token():
            return None
            
        print(f"📤 上传正文图片至微信服务器...")
        url = f'https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={self.token}'
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                f.write(image_bytes)
                temp_path = f.name
                
            with open(temp_path, 'rb') as f:
                files = {'media': (os.path.basename(temp_path), f)}
                resp = requests.post(url, files=files, timeout=60).json()
                
            try:
                os.unlink(temp_path)
            except:
                pass
                
            if 'url' in resp:
                return resp['url']
                
            # 处理 Token 过期报错 (errcode 42001 / 40001)
            err_code = resp.get('errcode')
            if err_code in [40001, 42001] and not is_retry:
                print(f"⚠️ Token 过期失效，正在重新获取...")
                self.token = None # 清除失效 Token
                if self._get_token():
                    # 重新拉一次并递归
                    return self.upload_article_image(image_bytes, is_retry=True)

            print(f"❌ 正文图片上传失败: {resp}")
            return None
        except Exception as e:
            print(f"❌ 正文图片上传异常: {e}")
            return None

    def publish_draft(self, title, content_html, digest, thumb_media_id):
        """创建草稿"""
        if not self.token and not self._get_token():
            return None
            
        # 微信标题限制 64 字节
        title_bytes = title.encode('utf-8')
        print(f"🔍 检查标题: '{title}' (长度: {len(title)}, 字节数: {len(title_bytes)})")
        
        safe_title = title_bytes[:64].decode('utf-8', 'ignore')
        if len(safe_title) < len(title):
            print(f"⚠️ 标题超过 64 字节，已自动截断: {safe_title}")

        print(f"📝 创建草稿: {safe_title}")
        url = f'https://api.weixin.qq.com/cgi-bin/draft/add?access_token={self.token}'
        payload = {
            "articles": [{
                "title": safe_title,
                "content": content_html,
                "digest": digest,
                "author": self.author,
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1,
                "only_fans_can_comment": 0
            }]
        }
        
        try:
            # 【核心修复】使用 ensure_ascii=False 避免中文被转义成 \uXXXX 导致字节数暴增
            json_data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            resp = requests.post(
                url, 
                data=json_data,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=30
            ).json()
            
            if 'media_id' in resp:
                return resp['media_id']
            print(f"❌ 创建草稿失败: {resp}")
            return None
        except Exception as e:
            print(f"❌ 创建草稿异常: {e}")
            return None

if __name__ == "__main__":
    # 测试代码 (需要实际密钥)
    pass
