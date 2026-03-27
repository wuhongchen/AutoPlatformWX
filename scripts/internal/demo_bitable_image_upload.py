import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import Config
from modules.feishu import FeishuBitable


def parse_args():
    parser = argparse.ArgumentParser(
        description="Demo: 上传图片到飞书多维表格附件字段（支持 URL / 本地文件）"
    )
    parser.add_argument(
        "--table",
        default=Config.FEISHU_INSPIRATION_TABLE,
        help="目标表名（默认读取 FEISHU_INSPIRATION_TABLE）",
    )
    parser.add_argument("--table-id", default="", help="目标 table_id（传入后优先于 --table）")
    parser.add_argument("--record-id", default="", help="更新已有记录 ID；不传则新建记录")
    parser.add_argument("--field", default="图片", help="附件字段名（默认：图片）")
    parser.add_argument(
        "--image-url",
        action="append",
        default=[],
        help="图片 URL，可重复传多次",
    )
    parser.add_argument(
        "--image-path",
        action="append",
        default=[],
        help="本地图片路径，可重复传多次",
    )
    parser.add_argument("--title", default="", help="新建记录时可选标题")
    return parser.parse_args()


def resolve_table_id(feishu, table_id, table_name):
    if table_id:
        return table_id
    return feishu.get_table_id_by_name(table_name)


def load_local_image(path):
    with open(path, "rb") as f:
        return f.read()


def upload_images(feishu, image_urls, image_paths):
    tokens = []

    for url in image_urls:
        print(f"🌐 上传远程图片: {url}")
        token = feishu.upload_image(url, parent_node=None, force_docx=False)
        if token:
            tokens.append({"file_token": token})
            print(f"   ✅ 成功: {token}")
        else:
            print("   ❌ 失败: URL 图片上传失败")

    for path in image_paths:
        abs_path = os.path.abspath(path)
        print(f"📁 上传本地图片: {abs_path}")
        if not os.path.exists(abs_path):
            print("   ❌ 失败: 文件不存在")
            continue
        try:
            img_content = load_local_image(abs_path)
            token = feishu.upload_image_content(img_content, parent_node=None, is_docx=False)
            if token:
                tokens.append({"file_token": token})
                print(f"   ✅ 成功: {token}")
            else:
                print("   ❌ 失败: 本地图片上传失败")
        except Exception as e:
            print(f"   ❌ 失败: {e}")

    return tokens


def main():
    load_dotenv()
    load_dotenv(os.path.join(PROJECT_ROOT, "../mp-draft-push/.env"))
    args = parse_args()

    if not Config.FEISHU_APP_ID or not Config.FEISHU_APP_SECRET or not Config.FEISHU_APP_TOKEN:
        print("❌ 缺少飞书配置，请先补齐 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_APP_TOKEN")
        sys.exit(1)

    if not args.image_url and not args.image_path:
        print("❌ 请至少提供一个 --image-url 或 --image-path")
        sys.exit(1)

    feishu = FeishuBitable(Config.FEISHU_APP_ID, Config.FEISHU_APP_SECRET, Config.FEISHU_APP_TOKEN)
    table_id = resolve_table_id(feishu, args.table_id, args.table)
    if not table_id:
        print(f"❌ 找不到目标表: {args.table}")
        sys.exit(1)

    cols = feishu.get_table_columns(table_id)
    if args.field not in cols:
        print(f"❌ 目标字段不存在: {args.field}")
        print(f"   当前字段: {', '.join(cols)}")
        sys.exit(1)

    tokens = upload_images(feishu, args.image_url, args.image_path)
    if not tokens:
        print("❌ 没有任何图片上传成功，结束。")
        sys.exit(1)

    if args.record_id:
        success = feishu.update_record(table_id, args.record_id, {args.field: tokens})
        if not success:
            print("❌ 更新记录失败")
            sys.exit(1)
        print(f"✅ 更新成功: table_id={table_id}, record_id={args.record_id}, images={len(tokens)}")
        return

    title = args.title or f"图片上传 Demo {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    fields = {args.field: tokens}
    if "标题" in cols:
        fields["标题"] = title

    success = feishu.add_record(table_id, fields)
    if not success:
        print("❌ 新建记录失败")
        sys.exit(1)

    print(f"✅ 新建记录成功: table_id={table_id}, images={len(tokens)}")


if __name__ == "__main__":
    main()
