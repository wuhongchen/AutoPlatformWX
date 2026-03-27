import os
import json
import requests
import time
import hmac
import hashlib
import tempfile
import base64
from datetime import datetime

from modules.prompts import ROLES, DEFAULT_ROLE
from modules.models import MODEL_POOL, DEFAULT_MODEL

class ContentProcessor:
    def __init__(self, volc_ak=None, volc_sk=None):
        self.volc_ak = volc_ak
        self.volc_sk = volc_sk

    def rewrite(self, article_data, role_key=DEFAULT_ROLE, model_key=DEFAULT_MODEL):
        """调用 LLM 进行角色化改写"""
        # 获取模型配置
        model_cfg = MODEL_POOL.get(model_key, MODEL_POOL[DEFAULT_MODEL])
        api_key = model_cfg.get("api_key")
        endpoint = model_cfg.get("endpoint")
        model_name = model_cfg.get("model")

        if not api_key:
            print(f"⚠️ 未配置 [{model_key}] 的 API 密钥，将跳过 AI 改写。")
            return {
                'title': article_data['title'],
                'content': article_data['content_html'],
                'digest': article_data['content_raw'][:100] + "...",
                'originality': 0
            }
            
        role = ROLES.get(role_key, ROLES[DEFAULT_ROLE])
        print(f"🤖 正在调用 AI [{model_cfg['name']}] 使用 [{role['name']}] 角色进行改写...")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": role['system_prompt']},
                {"role": "user", "content": f"请改写以下文章：\n标题：{article_data['title']}\n作者：{article_data['author']}\n内容：{article_data['content_raw']}"}
            ],
            "temperature": 0.7
        }
        
        # 诊断日志
        masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "无效密钥"
        print(f"   [诊断] 调用模型: {model_name} | Endpoint: {endpoint}")
        print(f"   [诊断] 密钥校验: {masked_key}")

        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=180)
            result = resp.json()
            if 'choices' in result:
                ai_text = result['choices'][0]['message']['content']
                return {
                    'title': article_data['title'], 
                    'content': ai_text,
                    'digest': article_data['content_raw'][:100] + "...",
                    'originality': 85
                }
            print(f"❌ AI 改写请求失败 (HTTP {resp.status_code}): {result}")
        except Exception as e:
            print(f"❌ AI 改写异常: {e}")

        return {
            'title': article_data['title'],
            'content': article_data['content_html'],
            'digest': article_data['content_raw'][:100] + "...",
            'originality': 0
        }

    def _first_non_empty_env(self, *keys):
        for key in keys:
            val = (os.getenv(key) or "").strip()
            if val:
                return val
        return ""

    def _normalize_api_base(self, endpoint):
        raw = str(endpoint or "").strip().rstrip("/")
        if not raw:
            return ""
        for suffix in ["/chat/completions", "/v1/chat/completions", "/responses", "/v1/responses"]:
            if raw.endswith(suffix):
                return raw[: -len(suffix)]
        return raw

    def _resolve_ark_image_endpoint(self):
        explicit = self._first_non_empty_env("ARK_IMAGE_GENERATE_ENDPOINT")
        if explicit:
            return explicit
        base = self._first_non_empty_env("ARK_IMAGE_ENDPOINT", "VOLC_ARK_ENDPOINT", "LLM_ENDPOINT")
        base = self._normalize_api_base(base)
        if not base:
            return ""
        return f"{base}/images/generations"

    def _save_temp_image_bytes(self, image_bytes, prefix):
        temp_file = os.path.join(tempfile.gettempdir(), f"{prefix}_{int(time.time() * 1000)}.jpg")
        with open(temp_file, "wb") as f:
            f.write(image_bytes)
        return temp_file

    def _save_image_from_url(self, image_url, prefix):
        try:
            resp = requests.get(image_url, timeout=30)
            resp.raise_for_status()
            return self._save_temp_image_bytes(resp.content, prefix)
        except Exception as e:
            print(f"   ⚠️ 图片 URL 下载失败: {e}")
            return None

    def _generate_cover_with_ark(self, prompt):
        """调用火山方舟图片生成（OpenAI 兼容 images API）。"""
        api_key = self._first_non_empty_env("ARK_IMAGE_API_KEY", "VOLC_ARK_API_KEY", "LLM_API_KEY")
        endpoint = self._resolve_ark_image_endpoint()
        model = self._first_non_empty_env("ARK_IMAGE_MODEL", "VOLC_ARK_IMAGE_MODEL") or "doubao-seedream-5-0-260128"
        size = (os.getenv("ARK_IMAGE_SIZE") or "1280x720").strip()
        response_format = (os.getenv("ARK_IMAGE_RESPONSE_FORMAT") or "b64_json").strip()

        if not api_key or not endpoint:
            print("   ℹ️ 方舟生图配置不完整（ARK_IMAGE_API_KEY / ARK_IMAGE_ENDPOINT），跳过。")
            return None

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "prompt": prompt, "size": size, "n": 1}
        if response_format:
            payload["response_format"] = response_format

        print(f"   🖼️ 尝试方舟生图: model={model}")

        def _post_image_gen(req_payload):
            try:
                resp = requests.post(endpoint, headers=headers, json=req_payload, timeout=90)
                body = resp.json()
                return resp.status_code, body
            except Exception as e:
                print(f"   ⚠️ 方舟生图请求异常: {e}")
                return -1, {}

        status, result = _post_image_gen(payload)
        if (status >= 400 or not result) and "response_format" in payload:
            retry_payload = dict(payload)
            retry_payload.pop("response_format", None)
            status, result = _post_image_gen(retry_payload)

        if status >= 400 or not isinstance(result, dict):
            print(f"   ⚠️ 方舟生图失败: status={status}, result={result}")
            return None

        data_items = result.get("data")
        if not isinstance(data_items, list) and isinstance(result.get("result"), dict):
            data_items = result.get("result", {}).get("data")
        if not isinstance(data_items, list):
            data_items = result.get("images")

        if not isinstance(data_items, list) or not data_items:
            print(f"   ⚠️ 方舟生图响应缺少图片数据: {result}")
            return None

        first = data_items[0]
        if isinstance(first, dict):
            if first.get("b64_json"):
                try:
                    image_bytes = base64.b64decode(first["b64_json"])
                    temp_file = self._save_temp_image_bytes(image_bytes, "ark_img")
                    print(f"   ✨ 方舟生图完成: {temp_file}")
                    return temp_file
                except Exception as e:
                    print(f"   ⚠️ 方舟 b64 解析失败: {e}")
            if first.get("image_base64"):
                try:
                    image_bytes = base64.b64decode(first["image_base64"])
                    temp_file = self._save_temp_image_bytes(image_bytes, "ark_img")
                    print(f"   ✨ 方舟生图完成: {temp_file}")
                    return temp_file
                except Exception as e:
                    print(f"   ⚠️ 方舟 image_base64 解析失败: {e}")
            if first.get("url"):
                temp_file = self._save_image_from_url(first["url"], "ark_img")
                if temp_file:
                    print(f"   ✨ 方舟生图完成: {temp_file}")
                    return temp_file
        elif isinstance(first, str) and first.startswith("http"):
            temp_file = self._save_image_from_url(first, "ark_img")
            if temp_file:
                print(f"   ✨ 方舟生图完成: {temp_file}")
                return temp_file

        print(f"   ⚠️ 方舟生图未解析到可用图片: {result}")
        return None

    def _generate_cover_with_jimeng(self, prompt):
        """用 Python 原生实现调用火山引擎即梦生成封面"""
        if not self.volc_ak or not self.volc_sk:
            print("   ℹ️ 未配置即梦 VOLCENGINE_AK/SK，跳过。")
            return None

        try:
            # --- 签名配置 ---
            service = "cv"
            region = "cn-beijing"
            host = "open.volcengineapi.com"
            action = "JimengT2IV31SubmitTask"
            version = "2024-06-06"
            
            payload = {
                "req_key": "jimeng_t2i_v31",
                "prompt": prompt,
                "model_version": "v3.1",
                "width": 1280,
                "height": 720,
                "count": 1
            }
            body = json.dumps(payload, separators=(',', ':'))
            
            now = datetime.utcnow()
            dt = now.strftime("%Y%m%dT%H%M%SZ")
            date = dt[:8]
            
            def sign(key, msg):
                return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

            def get_signature_key(key, date, region, service):
                k_date = sign(key.encode("utf-8"), date)
                k_region = sign(k_date, region)
                k_service = sign(k_region, service)
                k_signing = sign(k_service, "request")
                return k_signing

            hashed_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
            canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\nx-content-sha256:{hashed_payload}\nx-date:{dt}\n"
            signed_headers = "content-type;host;x-content-sha256;x-date"
            canonical_request = f"POST\n/\nAction={action}&Version={version}\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
            credential_scope = f"{date}/{region}/{service}/request"
            string_to_sign = f"HMAC-SHA256\n{dt}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
            
            signing_key = get_signature_key(self.volc_sk, date, region, service)
            signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
            authorization = f"HMAC-SHA256 Credential={self.volc_ak}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
            
            headers = {
                "Authorization": authorization,
                "Content-Type": "application/json; charset=utf-8",
                "X-Date": dt,
                "X-Content-Sha256": hashed_payload,
                "Host": host
            }
            
            url = f"https://{host}/?Action={action}&Version={version}"
            resp = requests.post(url, headers=headers, data=body, timeout=30).json()
            
            if "Result" in resp and "data" in resp["Result"]:
                task_id = resp["Result"]["data"]["task_id"]
                print(f"   任务已提交! TaskId: {task_id}")
                return self._poll_result(task_id, dt, date, credential_scope)
            
            print(f"   生图提交失败: {resp}")
        except Exception as e:
            print(f"   生图流程异常: {e}")
            
        return None

    def generate_cover(self, prompt):
        """封面生图路由：auto 优先方舟，失败回退即梦。"""
        print(f"🎨 正在生成封面图: {prompt}")

        provider = (os.getenv("COVER_IMAGE_PROVIDER") or "auto").strip().lower()
        if provider in {"auto", "ark", "volc_ark"}:
            cover_path = self._generate_cover_with_ark(prompt)
            if cover_path:
                return cover_path
            if provider in {"ark", "volc_ark"}:
                return None

        cover_path = self._generate_cover_with_jimeng(prompt)
        if cover_path:
            return cover_path

        print("   ⚠️ 封面生图未成功（方舟与即梦均不可用）")
        return None

    def _poll_result(self, task_id, dt, date, credential_scope):
        """轮询查询结果"""
        print(f"   ⏳ 正在轮询生成结果...")
        query_action = "JimengT2IV31GetResult"
        host = "open.volcengineapi.com"
        
        for _ in range(30):
            time.sleep(2)
            try:
                payload = {"req_key": "jimeng_t2i_v31", "task_id": task_id}
                body = json.dumps(payload, separators=(',', ':'))
                hashed_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
                
                canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\nx-content-sha256:{hashed_payload}\nx-date:{dt}\n"
                signed_headers = "content-type;host;x-content-sha256;x-date"
                canonical_request = f"POST\n/\nAction={query_action}&Version=2024-06-06\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
                string_to_sign = f"HMAC-SHA256\n{dt}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
                
                def sign(k, m): return hmac.new(k, m.encode("utf-8"), hashlib.sha256).digest()
                k_date = sign(self.volc_sk.encode("utf-8"), date)
                k_region = sign(k_date, "cn-beijing")
                k_service = sign(k_region, "cv")
                signing_key = sign(k_service, "request")
                
                signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
                authorization = f"HMAC-SHA256 Credential={self.volc_ak}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
                
                headers = {
                    "Authorization": authorization,
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Date": dt,
                    "X-Content-Sha256": hashed_payload,
                    "Host": host
                }
                
                url = f"https://{host}/?Action={query_action}&Version=2024-06-06"
                resp = requests.post(url, headers=headers, data=body, timeout=20).json()
                
                if "Result" in resp:
                    result_data = resp["Result"]
                    if result_data and "data" in result_data and result_data["data"]:
                        status = result_data["data"].get("status")
                        if status == "done":
                            images = result_data["data"].get("binary_data_base64", [])
                            if images:
                                temp_file = os.path.join(tempfile.gettempdir(), f"jimeng_{task_id}.jpg")
                                with open(temp_file, "wb") as f:
                                    f.write(base64.b64decode(images[0]))
                                print(f"   ✨ 生图完成: {temp_file}")
                                return temp_file
                        elif status == "failed":
                            print(f"   ❌ 任务失败: {result_data.get('message')}")
                            return None
                    else:
                        print(f"   ⚠️ 轮询响应异常: {resp}")
            except Exception as e:
                print(f"   轮询查询异常: {e}")
        return None

if __name__ == "__main__":
    processor = ContentProcessor()
    article = {'title': '测试文章', 'content_raw': '这是一段测试内容' * 10}
    res = processor.rewrite(article)
    print(f"结果: {res['title']}")
