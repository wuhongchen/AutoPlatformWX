import requests
import json
import logging
import time
import os
import subprocess
import re

class FeishuBitable:
    def __init__(self, app_id, app_secret, app_token):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.base_url = "https://open.feishu.cn/open-apis"
        self.token = None

    def _get_token(self, force=False):
        """获取 tenant_access_token"""
        # 如果已经有 token 且不是强制刷新，则直接返回
        if self.token and not force:
            return True
            
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        try:
            resp = requests.post(url, headers=headers, json=payload).json()
            if resp.get("code") == 0:
                self.token = resp.get("tenant_access_token")
                return True
            print(f"❌ 获取飞书 Token 失败: {resp}")
        except Exception as e:
            print(f"❌ 获取飞书 Token 异常: {e}")
        return False

    def list_tables(self):
        """列出多维表格中的所有数据表"""
        if not self._get_token():
            return []
        
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = requests.get(url, headers=headers).json()
            # 处理 Token 过期
            if resp.get("code") == 99991663:
                self._get_token(force=True)
                headers = {"Authorization": f"Bearer {self.token}"}
                resp = requests.get(url, headers=headers).json()
                
            if resp.get("code") == 0:
                return resp.get("data", {}).get("items", [])
            print(f"❌ 获取表格列表失败: {resp}")
        except Exception as e:
            print(f"❌ 获取表格列表异常: {e}")
        return []

    def list_records(self, table_id, filter_cond=None):
        """获取指定数据表的所有记录"""
        if not self._get_token():
            return {"items": []}
        
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"page_size": 100}
        if filter_cond:
            params["filter"] = filter_cond
            
        try:
            resp = requests.get(url, headers=headers, params=params).json()
            # 处理 Token 过期
            if resp.get("code") == 99991663:
                self._get_token(force=True)
                headers = {"Authorization": f"Bearer {self.token}"}
                resp = requests.get(url, headers=headers, params=params).json()

            if resp.get("code") == 0:
                return resp.get("data", {})
            print(f"❌ 获取记录失败: {resp}")
        except Exception as e:
            print(f"❌ 获取记录异常: {e}")
        return {"items": []}

    def add_record(self, table_id, fields):
        """向指定数据表添加一条记录"""
        return self.add_records(table_id, [fields])

    def add_records(self, table_id, records_fields_list):
        """批量向指定数据表添加记录 (优化 Bitable 性能)"""
        if not self.token and not self._get_token():
            return False
            
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        # 包装 payload
        records = [{"fields": f} for f in records_fields_list]
        payload = {"records": records}
        
        try:
            resp = requests.post(url, headers=headers, json=payload).json()
            if resp.get("code") == 0:
                print(f"✅ 成功批量添加 {len(records)} 条记录")
                return True
            print(f"❌ 批量添加记录失败: {resp}")
        except Exception as e:
            print(f"❌ 批量添加记录异常: {e}")
        return False

    def update_record(self, table_id, record_id, fields):
        """更新指定数据表的记录"""
        if not self.token and not self._get_token():
            return False
            
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {"fields": fields}
        try:
            resp = requests.put(url, headers=headers, json=payload).json()
            if resp.get("code") == 0:
                return True
            print(f"❌ 更新记录失败: {resp}")
        except Exception as e:
            print(f"❌ 更新记录异常: {e}")
        return False

    def get_record(self, table_id, record_id):
        """获取单条记录详情"""
        if not self.token and not self._get_token(): return None
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = requests.get(url, headers=headers).json()
            return resp.get('data', {}).get('record')
        except: return None

    def get_table_columns(self, table_id):
        """获取数据表的所有列名"""
        if not self.token and not self._get_token(): return []
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = requests.get(url, headers=headers).json()
            return [f['field_name'] for f in resp.get('data', {}).get('items', [])]
        except: return []

    def batch_delete_records(self, table_id, record_ids):
        """批量删除记录"""
        if not self.token and not self._get_token():
            return False
            
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_delete"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {"records": record_ids}
        try:
            resp = requests.post(url, headers=headers, json=payload).json()
            if resp.get("code") == 0:
                print(f"✅ 成功批量删除 {len(record_ids)} 条记录")
                return True
            print(f"❌ 批量删除记录失败: {resp}")
        except Exception as e:
            print(f"❌ 批量删除记录异常: {e}")
        return False

    def get_docx_content(self, document_id):
        """获取飞书文档内容并转换为 HTML/纯文本结构"""
        if not self.token and not self._get_token():
            return None
        
        # 1. 如果 document_id 长度符合 Wiki ID 特征，先尝试作为 Wiki 解析
        if len(document_id) >= 20: 
            headers = {"Authorization": f"Bearer {self.token}"}
            wiki_url = f"{self.base_url}/wiki/v2/spaces/get_node"
            params = {"token": document_id}
            try:
                wiki_resp = requests.get(wiki_url, headers=headers, params=params).json()
                if wiki_resp.get("code") == 0:
                    node = wiki_resp.get("data", {}).get("node", {})
                    if node.get("obj_type") == "docx":
                        print(f"🔗 已成功将 Wiki 节点解析为 docx 对象: {node.get('obj_token')}")
                        document_id = node.get("obj_token")
            except:
                pass

        print(f"📥 正在从飞书文档提取内容: {document_id}")
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # 1. 获取文档元数据（标题）
        doc_meta_url = f"{self.base_url}/docx/v1/documents/{document_id}"
        meta_resp = requests.get(doc_meta_url, headers=headers).json()
        if meta_resp.get("code") != 0:
            print(f"❌ 获取文档元数据失败: {meta_resp}")
            return None
        title = meta_resp["data"]["document"]["title"]
        
        # 2. 迭代获取所有块
        blocks = []
        page_token = ""
        while True:
            blocks_url = f"{self.base_url}/docx/v1/documents/{document_id}/blocks"
            params = {"page_size": 500} # 提升至 500 以加快长文档读取
            if page_token: params["page_token"] = page_token
            
            max_retry = 3
            for attempt in range(max_retry):
                resp = requests.get(blocks_url, headers=headers, params=params).json()
                code = resp.get("code", -1)
                
                if code == 0: 
                    items = resp.get("data", {}).get("items", [])
                    blocks.extend(items)
                    if len(blocks) % 100 == 0:
                        print(f"   📥 已获取 {len(blocks)} 个内容块...")
                    break
                
                # 99991400 = 频率过快
                if code == 99991400 and attempt < max_retry - 1:
                    wait = [5, 10, 15][attempt]
                    print(f"   ⏳ [飞书频率限制] 触发 QPS 限制，等待 {wait}s 后重试 ({attempt+1}/{max_retry-1})...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"❌ 获取文档块失败: {resp}")
                    return None # 失败直接返回 None，触发上层重采
            
            if resp.get("data", {}).get("has_more"):
                page_token = resp.get("data", {}).get("next_page_token")
            else:
                break
        
        print(f"   ✅ 内容提取完毕，共获得 {len(blocks)} 个内容块。")

        # 3. 将块转换为 HTML / MD 碎片
        html_list = []
        md_list = []
        raw_text_list = []
        images_list = []
        first_h1_text = None
        
        # 文本类 Block 的 KEY 映射
        TEXT_BLOCK_MAP = {
            2: "text", 3: "h1", 4: "h2", 5: "h3", 6: "h4", 7: "h5", 8: "h6", 9: "h9",
            12: "bullet", 13: "ordered", 14: "code", 15: "quote", 17: "todo", 19: "callout"
        }
        
        for block in blocks:
            b_type = block.get("block_type")
            
            # --- 处理文本类块 ---
            if b_type in TEXT_BLOCK_MAP:
                content_key = TEXT_BLOCK_MAP[b_type]
                data = block.get(content_key, {})
                elements = data.get("elements", [])
                
                block_html = ""
                block_md = ""
                block_text = ""
                
                # HTML 标签映射
                tag = {2: "p", 3: "h1", 4: "h2", 5: "h3", 12: "li", 13: "li", 14: "pre", 15: "blockquote", 19: "div"}.get(b_type, "p")
                # MD 前缀映射
                md_prefix = {3: "# ", 4: "## ", 5: "### ", 12: "* ", 13: "1. ", 15: "> ", 19: "💡 "}.get(b_type, "")

                for el in elements:
                    if "text_run" in el:
                        text = el["text_run"]["content"]
                        style = el["text_run"].get("text_element_style", {})
                        block_text += text
                        
                        m_text = text
                        if style.get("bold"): 
                            text = f"<b>{text}</b>"
                            m_text = f"**{m_text}**"
                        if style.get("italic"): 
                            text = f"<i>{text}</i>"
                            m_text = f"_{m_text}_"
                        if style.get("link"): 
                            text = f"<a href='{style['link']['url']}'>{text}</a>"
                            m_text = f"[{m_text}]({style['link']['url']})"
                        
                        block_html += text
                        block_md += m_text
                
                if block_html:
                    html_list.append(f"<{tag}>{block_html}</{tag}>")
                    md_list.append(f"{md_prefix}{block_md}")
                    raw_text_list.append(block_text)
                    if not first_h1_text and block_text.strip() and b_type in [2, 3]:
                        first_h1_text = block_text.strip()
            
            # --- 处理图片块 ---
            elif b_type in [11, 27]:
                img_data = block.get("image", {})
                img_token = img_data.get("file_token") or img_data.get("token")
                if img_token:
                    feishu_img_url = f"feishu://{img_token}"
                    html_list.append(f'<img src="{feishu_img_url}" />')
                    md_list.append(f"![image]({feishu_img_url})")
                    raw_text_list.append(f"[图片: {img_token}]")
                    images_list.append(feishu_img_url)

        # 4. 标题决策
        final_title = title.strip() if title else ""
        if (not final_title or "未命名" in final_title or len(final_title) < 2) and first_h1_text:
            final_title = first_h1_text[:100] # 截断

        return {
            'title': final_title or "未命名文章",
            'author': "飞书用户",
            'content_raw': "\n".join(raw_text_list),
            'content_html': "".join(html_list),
            'content_markdown': "\n\n".join(md_list),
            'images': images_list
        }

    def create_docx(self, title):
        """创建一个新的飞书文档并返回文档 ID"""
        if not self.token and not self._get_token():
            return None, None
            
        url = f"{self.base_url}/docx/v1/documents"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {"title": title}
        try:
            resp = requests.post(url, headers=headers, json=payload).json()
            if resp.get("code") == 0:
                doc_id = resp["data"]["document"]["document_id"]
                doc_url = f"https://www.feishu.cn/docx/{doc_id}"
                return doc_id, doc_url
            print(f"❌ 创建文档失败: {resp}")
        except Exception as e:
            print(f"❌ 创建文档异常: {e}")
        return None, None

    def append_docx_blocks(self, document_id, blocks):
        """三步走写入图片 + 批量写入文本块。
        
        图片正确流程（经实测验证）:
          Step A: POST {block_type:27, image:{}} → 拿 block_id
          Step B: upload(parent_type=docx_image, parent_node=block_id) → 拿 file_token
          Step C: PATCH {replace_image: {token: file_token}} → 图片正常显示
        """
        if not self.token and not self._get_token():
            return False
        
        # 确保云盘备份文件夹
        if not hasattr(self, '_asset_folder_token'):
            self._asset_folder_token = self.create_folder("采集备份图库") or ""
        
        # === 阶段一：下载所有图片内容（不触碰文档） ===
        print("📤 [阶段一] 下载图片素材...")
        preloaded = []
        drive_links = []
        
        for block in blocks:
            if block.get("block_type") == 27:
                src_url = block.get("image", {}).get("_src_url", "")
                img_content = self._download_image(src_url)
                if img_content:
                    _, drive_url = self.upload_file_to_drive(
                        img_content, self._asset_folder_token,
                        f"img_{int(time.time()*1000)}.jpg"
                    )
                    preloaded.append({"type": "image", "img": img_content, "drive": drive_url})
                    if drive_url:
                        drive_links.append(drive_url)
                else:
                    print(f"   ⚠️ 图片下载失败，跳过: {src_url[:50]}")
            else:
                preloaded.append({"type": "block", "block": block})
        
        img_count = sum(1 for p in preloaded if p["type"] == "image")
        print(f"📤 [阶段一完成] 成功下载 {img_count} 张图片")
        
        # === 阶段二：写入所有块 ===
        time.sleep(2.0)
        append_url = f"{self.base_url}/docx/v1/documents/{document_id}/blocks/{document_id}/children"
        patch_base  = f"{self.base_url}/docx/v1/documents/{document_id}/blocks"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        print("📝 [阶段二] 写入所有块...")
        for item in preloaded:
            if item["type"] == "image":
                img_content = item["img"]
                
                # Step A: 创建空 image block（必须带 "image": {} 字段）
                r_a = self._safe_post(append_url, headers, {
                    "children": [{"block_type": 27, "image": {}}], "index": -1
                })
                if r_a.get("code") != 0:
                    print(f"   ❌ [A] 建空 block 失败: {r_a.get('code')} {r_a.get('msg')}")
                    continue
                block_id = r_a["data"]["children"][0]["block_id"]
                
                # Step B: 上传图片，parent_node=block_id（不是 doc_id）
                file_token = self.upload_image_content(img_content, block_id, is_docx=True)
                if not file_token:
                    print(f"   ❌ [B] 图片上传失败")
                    continue
                
                # Step C: PATCH replace_image（不是 update_image）
                r_c = requests.patch(
                    f"{patch_base}/{block_id}", headers=headers,
                    json={"replace_image": {"token": file_token}}
                ).json()
                if r_c.get("code") == 0:
                    print(f"   ✅ 图片写入成功 block={block_id[:15]}...")
                else:
                    print(f"   ⚠️ [C] PATCH 失败: {r_c.get('code')} {r_c.get('msg')}")
            else:
                block = item["block"]
                b_type = block.get("block_type")
                clean = {k: v for k, v in block.items() if not k.startswith("_")}
                resp = self._safe_post(append_url, headers, {"children": [clean], "index": -1})
                if resp.get("code") == 0:
                    print(f"   ✅ 写入 type={b_type} 块")
                else:
                    print(f"   ⚠️ 写入 type={b_type} 失败: {resp.get('code')} {resp.get('msg')}")
            time.sleep(0.5)
        
        # 追加云盘备份链接（直接 POST，不重试，失败静默跳过）
        if drive_links:
            time.sleep(2)  # 等主内容写完后再写链接
        for drive_url in drive_links:
            try:
                r = requests.post(append_url, headers=headers, json={
                    "children": [{"block_type": 2, "text": {"elements": [{"text_run": {
                        "content": "🔗 [点击查看高清云盘原图]\n",
                        "text_element_style": {"italic": True, "link": {"url": drive_url},
                                              "underline": True, "text_color": "#1E90FF"}
                    }}]}}], "index": -1
                }, timeout=10).json()
                if r.get("code") == 0:
                    print(f"   ✅ 云盘备份链接写入")
                # 失败则静默跳过（不重试），避免限流卡死
            except Exception:
                pass
            time.sleep(1)
        
        return True




    def _download_image(self, url):
        """支持直接处理 Base64、通过网络下载、或从飞书云盘下载媒体"""
        if not url: return None
        
        # A. Base64
        if url.startswith("data:image"):
            import base64
            try:
                header, encoded = url.split(",", 1)
                return base64.b64decode(encoded)
            except: return None
            
        # B. 飞书内部素材
        if "feishu" in url.lower():
            file_token = None
            if url.startswith("feishu://"):
                file_token = url.replace("feishu://", "")
            else:
                patterns = [
                    r'file/([a-zA-Z0-9]{15,45})',   
                    r'file/(f-[a-zA-Z0-9_-]+)',     
                    r'asset/([a-zA-Z0-9_-]{15,55})'
                ]
                for p in patterns:
                    match = re.search(p, url)
                    if match:
                        file_token = match.group(1)
                        break
            
            if file_token:
                if not self.token and not self._get_token(): return None
                print(f"   🔍 飞书素材下载尝试: {file_token}")
                headers = {"Authorization": f"Bearer {self.token}"}
                # 优先尝试 medias 下载，不行再尝试 files
                for path in ["drive/v1/medias", "drive/v1/files"]:
                    try:
                        download_url = f"{self.base_url}/{path}/{file_token}/download"
                        resp = requests.get(download_url, headers=headers, timeout=30)
                        if resp.status_code == 200:
                            if b'<!DOCTYPE html>' not in resp.content[:200]:
                                return resp.content
                    except Exception as e:
                        print(f"Exception downloading {path}: {e}")
                        continue

        # C. 网络普通 URL (微信等高质量 UA 模拟)
        import random
        common_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
        strategies = [
            {"User-Agent": common_ua, "Referer": "https://mp.weixin.qq.com/"},
            {"User-Agent": common_ua, "Referer": "https://juejin.cn/"},
            {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"},
            {"User-Agent": common_ua}
        ]
        
        for headers in strategies:
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    # 只要大于 0 字节且不是 HTML 错误页
                    if len(resp.content) > 100:
                        if b'<!DOCTYPE html>' not in resp.content[:200]:
                            return resp.content
            except: continue
        
        return None

    def _safe_post(self, url, headers, json_payload, max_retry=3):
        """带指数退避重试的 POST，专门处理飞书文档写入的暂时性错误"""
        delays = [3, 6, 10]
        for attempt in range(max_retry):
            try:
                resp = requests.post(url, headers=headers, json=json_payload).json()
                code = resp.get("code", -1)
                if code == 0:
                    return resp
                # 99992402 = 系统繁忙/文档锁，可重试
                if code == 99992402 and attempt < max_retry - 1:
                    wait = delays[attempt]
                    print(f"   ⏳ [系统繁忙] 等待 {wait}s 后重试 ({attempt+1}/{max_retry-1})...")
                    time.sleep(wait)
                    continue
                return resp
            except Exception as e:
                if attempt < max_retry - 1:
                    time.sleep(delays[attempt])
                else:
                    return {"code": -1, "msg": str(e)}
        return {"code": -1, "msg": "max retries exceeded"}

    def _append_single_block_with_fallback(self, document_id, block, headers):
        """插入单个块，针对图片采用"实物展示 + 云盘备份"双保险模式"""
        url = f"{self.base_url}/docx/v1/documents/{document_id}/blocks/{document_id}/children"
        
        b_type = block.get("block_type")
        
        # block_type=27 为飞书文档正确图片块类型
        if b_type == 27:
            src_url = block.get("image", {}).get("_src_url")
            if not src_url: return False
            
            print(f"   📂 正在处理素材: {src_url[:40]}...")
            img_content = self._download_image(src_url)
            
            if not img_content:
                print(f"   ❌ 素材获取失败，跳过该图")
                return False

            try:
                # 1. 云盘物理备份
                if not hasattr(self, '_asset_folder_token'):
                    self._asset_folder_token = self.create_folder("采集备份图库") or ""
                drive_token, drive_url = self.upload_file_to_drive(img_content, self._asset_folder_token, f"img_{int(time.time()*1000)}.jpg")
                
                # 2. 上传 docx_image，获取 file_token，用 block_type=27 + file_token 插入
                docx_token = self.upload_image_content(img_content, document_id, is_docx=True)
                
                if docx_token:
                    # 关键：block_type=27，字段名 file_token
                    payload = {"children": [{"block_type": 27, "image": {"file_token": docx_token}}], "index": -1}
                    resp = self._safe_post(url, headers, payload)
                    if resp.get("code") == 0:
                        print(f"   ✅ [图片插入成功] file_token={docx_token}")
                    else:
                        print(f"   ⚠️ [图片插入失败] {resp.get('code')}: {resp.get('msg')}")
                
                # 3. 强制插入云盘备份链接（永久保险）
                if drive_url:
                    backup_payload = {
                        "children": [{"block_type": 2, "text": {"elements": [{"text_run": {
                            "content": f"🔗 [点击查看高清云盘原图]\n",
                            "text_element_style": {"italic": True, "link": {"url": drive_url}, "underline": True, "text_color": "#1E90FF"}
                        }}]}}], "index": -1
                    }
                    r_back = self._safe_post(url, headers, backup_payload)
                    if r_back.get("code") == 0:
                        print(f"   ✅ [云盘备份链接已插入]")
                    else:
                        print(f"   ❌ [备份链接插入失败] {r_back.get('code')}")
                return True
            except Exception as e:
                print(f"   ❌ 混合回填异常: {e}")
            return False

        # 普通文本 / 标题 Block 处理
        clean_block = {"block_type": b_type}
        if b_type == 2:
            clean_block["text"] = block.get("text")
        elif b_type in [3, 4, 5]:
            fname = f"heading{b_type-2}"
            clean_block[fname] = block.get(fname)
        else:
            clean_block = {k: v for k, v in block.items() if not k.startswith("_")}
        
        resp = self._safe_post(url, headers, {"children": [clean_block], "index": -1})
        return resp.get("code") == 0

    def html_to_docx_blocks(self, html_content, document_id=None):
        """将 HTML 转换为飞书 Docx 块结构。
        
        策略（适配微信 section 深层嵌套）：
        - 用 find_all 按文档顺序收集所有 img / h1~h3 / strong
        - 对"叶层文本容器"（section/span/p 中不包含其他 section/p/div 的节点）提取文本
        - 用文本 hash 去重，确保每条内容只出现一次
        - strong ≤40字 → H2标题；文本按换行切段
        """
        from bs4 import BeautifulSoup, NavigableString, Tag
        import re

        soup = BeautifulSoup(html_content, 'html.parser')
        blocks = []
        seen = set()         # 已处理节点的 id(tag)
        seen_text = set()    # 已添加文本的 hash

        def thash(t):
            return hash(t.strip()[:100]) if t else 0

        # 句子结束符（切段依据）
        SENT_END = re.compile(r"""([。！？!?…]+[\"'"）)】\s]*)""")
        MAX_PARA_LEN = 150   # 超过此长度尝试切段

        def split_sentences(text):
            """将长段按句号切成自然段，每段不超过 MAX_PARA_LEN 字"""
            if len(text) <= MAX_PARA_LEN:
                return [text]
            
            parts = SENT_END.split(text)
            # split 结果格式：['前文', '。', '后文', '！', ...]
            sentences = []
            i = 0
            while i < len(parts):
                chunk = parts[i]
                if i + 1 < len(parts) and SENT_END.match(parts[i+1]):
                    chunk += parts[i+1]
                    i += 2
                else:
                    i += 1
                chunk = chunk.strip()
                if chunk:
                    sentences.append(chunk)
            
            if not sentences:
                return [text]
            
            # 合并过短的句子（< 20字）到相邻句
            merged = []
            buf = ""
            for s in sentences:
                buf = (buf + s).strip()
                if len(buf) >= 40:   # 达到合理长度就输出
                    merged.append(buf)
                    buf = ""
            if buf:
                if merged:
                    merged[-1] += buf  # 尾部太短就并入前一段
                else:
                    merged.append(buf)
            return merged if merged else [text]

        def add_para(text, bold=False):
            """按换行切段 + 智能句子切分，去重后加入 blocks"""
            # 先按换行拆
            raw_lines = [l.strip() for l in re.split(r'\n+', text) if l.strip()]
            # 再按句子切分超长段
            lines = []
            for raw in raw_lines:
                lines.extend(split_sentences(raw))
            
            for line in lines:
                if not line.strip():
                    continue
                h = thash(line)
                if h in seen_text:
                    continue
                seen_text.add(h)
                if bold and len(line) <= 40:
                    blocks.append({"block_type": 4, "heading2": {
                        "elements": [{"text_run": {"content": line}}]
                    }})
                elif bold:
                    blocks.append({"block_type": 2, "text": {
                        "elements": [{"text_run": {"content": line,
                                      "text_element_style": {"bold": True}}}]
                    }})
                else:
                    blocks.append({"block_type": 2, "text": {
                        "elements": [{"text_run": {"content": line}}]
                    }})

        def is_text_leaf(tag):
            """节点不含 section/p/div 子节点，只含文本/span/strong/em/br/a"""
            TEXT_ONLY = {'span', 'strong', 'b', 'em', 'i', 'a', 'br', 'u', 'sub', 'sup'}
            for child in tag.children:
                if isinstance(child, Tag):
                    if child.name not in TEXT_ONLY:
                        return False
            return True

        def get_text_runs(tag):
            """将节点内的 HTML 元素递归解析为飞书 text_run 列表，支持加粗、斜体、链接、换行"""
            runs = []
            for child in tag.children:
                if isinstance(child, NavigableString):
                    content = str(child)
                    if content: # 即使是纯空格也保留，确保排版
                        runs.append({"text_run": {"content": content}})
                elif isinstance(child, Tag):
                    name = child.name
                    if name == 'br':
                        runs.append({"text_run": {"content": "\n"}})
                        continue
                        
                    # 递归获取子节点的 runs
                    child_runs = get_text_runs(child)
                    # 为子节点应用当前层的样式
                    for run in child_runs:
                        if 'text_run' in run:
                            style = run['text_run'].setdefault('text_element_style', {})
                            if name in ('strong', 'b'): style['bold'] = True
                            if name in ('em', 'i'): style['italic'] = True
                            if name == 'u': style['underline'] = True
                            if name == 'a' and child.get('href'):
                                style['link'] = {"url": child.get('href')}
                    runs.extend(child_runs)
            return runs

        def collect(tag):
            """深度遍历，按文档顺序输出 blocks"""
            if id(tag) in seen: return
            if not isinstance(tag, Tag) or not tag.name: return
            
            name = tag.name
            if name in ('script', 'style', 'head', 'meta', 'link'): return

            # ── 代码块 (Code Block) ──────────────────────────────────────────
            # 改进：增加对微信中常见的高亮容器识别
            is_code = name in ('pre', 'code')
            if not is_code and name == 'section' and ('code' in str(tag.get('class', '')).lower() or tag.find('code')):
                is_code = True
                
            if is_code:
                txt = tag.get_text().strip()
                if txt:
                    seen.add(id(tag))
                    lang = 1 # Plain Text
                    if any(x in txt.lower() for x in ['curl', 'bash', 'sh ', 'sudo', 'apt-get']): lang = 2 # Basic/Bash
                    elif any(x in txt for x in ['{', '}', 'import ', 'def ']): lang = 5 # JSON/JS/Python
                    
                    blocks.append({
                        "block_type": 14,
                        "code": {
                            "style": {"language": lang},
                            "elements": [{"text_run": {"content": txt}}]
                        }
                    })
                return

            # ── 图片 ─────────────────────────────────────────────────────────
            if name == 'img':
                src = tag.get('data-src') or tag.get('src', '')
                if src and (src.startswith('http') or src.startswith('feishu://')):
                    seen.add(id(tag))
                    blocks.append({"block_type": 27, "image": {"_src_url": src}})
                return

            # ── 标题 ─────────────────────────────────────────────────────────
            if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                txt = tag.get_text(strip=True)
                if txt:
                    # 如果标题内包含图片，则不把整个标题作为文本块，而是拆解
                    if tag.find('img'):
                        for child in tag.children: collect(child)
                        return
                    seen.add(id(tag))
                    level = int(name[1])
                    bt = max(3, min(level + 2, 11))
                    key = f"heading{max(1, min(level, 9))}"
                    blocks.append({"block_type": bt, key: {"elements": [{"text_run": {"content": txt}}]}})
                return

            # ── 特殊容器与引言 (Callout / Blocks) ──────────────────────────
            if name in ('p', 'div', 'section', 'li', 'blockquote', 'article'):
                cls = str(tag.get('class', '')).lower()
                
                # 识别 AI 专用排版容器
                is_guide = 'guide-box' in cls or '导读' in tag.get_text()[:20]
                is_summary = 'summary-box' in cls or '总结' in tag.get_text()[:20]
                
                # A. 导读/高亮容器 (Callout)
                if is_guide or is_summary:
                    txt = tag.get_text(strip=True)
                    if txt:
                        seen.add(id(tag))
                        blocks.append({
                            "block_type": 19,
                            "callout": {
                                "background_color": 12 if is_guide else 1,
                                "emoji_id": "ali_lightbulb" if is_guide else "ali_pencil", # 使用飞书标准 Emoji ID
                                "elements": [{"text_run": {"content": txt}}]
                            }
                        })
                    return

                # B. 引用块 (Quote)
                if name == 'blockquote' or 'quote' in cls:
                    runs = get_text_runs(tag)
                    if runs:
                        seen.add(id(tag))
                        # 将引用转换为普通文本段落或加粗文本
                        blocks.append({
                            "block_type": 2,
                            "text": {"elements": runs}
                        })
                    return

                # C. 通用段落与容器处理
                inner_assets = tag.find_all(['img', 'pre', 'code', 'h1', 'h2', 'h3'], recursive=False)
                if inner_assets or tag.find(['img', 'pre', 'code']) or not is_text_leaf(tag):
                    # 包含重要资产或其他段落容器，继续深挖
                    for child in tag.children:
                        collect(child)
                else:
                    runs = get_text_runs(tag)
                    if runs:
                        seen.add(id(tag))
                        blocks.append({"block_type": 2, "text": {"elements": runs}})
                return

            # ── 其他节点：继续递归 ──────────────────────────────────────────
            for child in tag.children:
                collect(child)

        # 执行
        root = soup.find('body') or soup
        for child in root.children:
            collect(child)

        return blocks, []



    def set_file_public(self, file_token):
        """将文件设置为公网可见，以便在内嵌预览中正常显示"""
        url = f"https://open.feishu.cn/open-apis/drive/v1/permissions/{file_token}/public"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "external_access_entity": "open",
            "security_entity": "anyone_can_view",
            "share_entity": "anyone"
        }
        try:
            requests.patch(url, headers=headers, json=payload)
        except: pass

    def set_tenant_manageable(self, token):
        """将文档设置为组织内获得链接的人可编辑 (针对 docx 显式指定 type)"""
        if not self.token and not self._get_token(): return
        # 关键：必须带上 ?type=docx，否则飞书会报错或静默失败
        url = f"https://open.feishu.cn/open-apis/drive/v1/permissions/{token}/public?type=docx"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        payload = {
            "link_share_entity": "tenant_editable",
            "external_access_entity": "open",
            "security_entity": "anyone_can_edit" # 关键：设置为可编辑
        }
        try:
            r_raw = requests.patch(url, headers=headers, json=payload)
            resp = r_raw.json()
            if resp.get("code") == 0:
                print(f"   🔓 [权限更新成功] 组织内获得链接的人可编辑")
            else:
                print(f"   ⚠️ [权限提权失败] Code: {resp.get('code')}, Msg: {resp.get('msg')}")
        except Exception as e:
            print(f"   ❌ 权限设置异常: {e}")

    def add_collaborator(self, token, member_id, role="full_access"):
        """为云文档添加特定的协作者权限 (针对 docx 显式指定 type)"""
        if not self.token and not self._get_token(): return False
        # 关键：必须带上 ?type=docx
        url = f"https://open.feishu.cn/open-apis/drive/v1/permissions/{token}/members?type=docx"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        # 识别 member_type: userid (官方参数是 userid, 而非 user)
        member_type = "userid"
        if "@" in member_id: member_type = "email"
        elif member_id.startswith("ou_"): member_type = "openid"
        
        payload = {
            "member_type": member_type,
            "member_id": member_id,
            "perm": role
        }
        try:
            r = requests.post(url, headers=headers, json=payload).json()
            if r.get("code") == 0:
                print(f"   👤 已成功将用户 {member_id[:8]}... 设为文档管理员")
                return True
            else:
                print(f"   ⚠️ 指派管理员失败: {r.get('msg')}")
        except: pass
        return False

    def upload_image(self, image_url, parent_node, force_docx=False):
        """上传图片到飞书并返回 file_token (复用下载逻辑)"""
        img_content = self._download_image(image_url)
        if not img_content: return None
        return self.upload_image_content(img_content, parent_node, is_docx=force_docx)

    def upload_image_content(self, img_content, parent_node, is_docx=False):
        """核心上传函数：接收二进制内容，自动检测文件格式"""
        import time, subprocess, os
        if not self.token and not self._get_token(): return None

        # 1. 格式检测与标准化
        mime_type = 'image/jpeg'
        ext = 'jpg'
        
        if img_content[:4] == b'\x89PNG':
            mime_type, ext = 'image/png', 'png'
        elif img_content[:2] in (b'\xff\xd8', b'\xff\xe0', b'\xff\xe1'):
            mime_type, ext = 'image/jpeg', 'jpg'
        elif img_content[:4] == b'RIFF' and b'WEBP' in img_content[8:16]:
            # WebP 转 PNG
            try:
                tmp_w = f"/tmp/wx_{int(time.time()*1000)}.webp"
                tmp_p = tmp_w.replace(".webp", ".png")
                with open(tmp_w, 'wb') as f: f.write(img_content)
                subprocess.run(["sips", "-s", "format", "png", tmp_w, "--out", tmp_p], capture_output=True)
                if os.path.exists(tmp_p) and os.path.getsize(tmp_p) > 100:
                    with open(tmp_p, 'rb') as f: img_content = f.read()
                    mime_type, ext = 'image/png', 'png'
            except: pass
        elif img_content[:4] == b'GIF8':
            mime_type, ext = 'image/gif', 'gif'

        p_type = 'docx_image' if is_docx else 'bitable_image'
        p_node = parent_node if is_docx else self.app_token
        file_name = f"img_{int(time.time())}.{ext}"
        upload_url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
        
        data = {
            'parent_type': p_type,
            'parent_node': p_node,
            'size': str(len(img_content)),
            'file_name': file_name
        }
        files = {'file': (file_name, img_content, mime_type)}
        
        try:
            r_resp = requests.post(upload_url, headers={"Authorization": f"Bearer {self.token}"}, data=data, files=files)
            r = r_resp.json()
            if r.get("code") == 0:
                ft = r["data"]["file_token"]
                print(f"   ✅ [媒体上传成功] Type: {p_type}, MIME: {mime_type}, Token: {ft}")
                if not is_docx: self.set_file_public(ft) 
                return ft
            else:
                print(f"   ❌ [媒体上传失败] Code: {r.get('code')}, Msg: {r.get('msg')}")
        except Exception as e:
            print(f"   ❌ [媒体上传异常] {e}")
        return None

    def get_table_id_by_name(self, table_name):
        """根据名称获取表格 ID"""
        tables = self.list_tables()
        if tables:
            for table in tables:
                if table.get("name") == table_name:
                    return table.get("table_id")
        return None

    def create_field(self, table_id, field_name, field_type=17):
        """在多维表格中创建新字段"""
        if not self.token and not self._get_token(): return False
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {"field_name": field_name, "type": field_type}
        try:
            resp = requests.post(url, headers=headers, json=payload).json()
            return resp.get("code") == 0
        except: return False

    def create_folder(self, folder_name, parent_folder_token=None):
        """在飞书云盘创建文件夹，并返回 folder_token"""
        if not self.token and not self._get_token(): return None
        url = "https://open.feishu.cn/open-apis/drive/v1/files/create_folder"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {"name": folder_name, "folder_token": parent_folder_token or ""}
        try:
            resp = requests.post(url, headers=headers, json=payload).json()
            if resp.get("code") == 0:
                return resp["data"]["token"]
            print(f"   ℹ️ 准备查找或复用已有的 '{folder_name}' 文件夹...")
        except: pass
        return None

    def upload_file_to_drive(self, content, folder_token, file_name):
        """将内容直接作为文件上传到飞书云盘文件夹"""
        print(f"   🔑 当前 Token 状态: {'已加载' if self.token else '空'}")
        if not self.token and not self._get_token():
             print("   ❌ Token 获取失败")
             return None, None
        
        upload_url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
        data = {
            'parent_type': 'explorer',
            'parent_node': folder_token,
            'size': str(len(content)),
            'file_name': file_name
        }
        files = {'file': (file_name, content, 'image/png')}
        print(f"   📤 正在上传到文件夹 {folder_token[:8]}... 文件名: {file_name}, 大小: {len(content)}")
        try:
            r_raw = requests.post(upload_url, headers={"Authorization": f"Bearer {self.token}"}, data=data, files=files)
            print(f"   📡 接口返回状态码: {r_raw.status_code}")
            r = r_raw.json()
            if r.get("code") == 0:
                ftoken = r["data"]["file_token"]
                self.set_file_public(ftoken)
                return ftoken, f"https://www.feishu.cn/file/{ftoken}"
            print(f"   ❌ 云盘上传接口报错: {r}")
        except Exception as e:
            print(f"   ❌ 云盘上传异常: {e}")
        return None, None
