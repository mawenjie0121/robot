# my_scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import sys
import io
import logging

from services.bug2story.bug2story_data_fetcher import fetch_all_stories
from services.bug2story.tapd_bug2story_href import TapdBug2StoryHrefFetcher
from services.bugs.tapd_version_defect_comparison_generator import TapdVersionDefectComparisonGenerator
from services.tapd_client import TAPDHandler
from src.wecom_bot_svr import RspTextMsg


def run_defect_report():
    generator = TapdVersionDefectComparisonGenerator()
    workspace_id = 20428244
    version_list = [
        "TRTC 2.0（TRTC 11.5）",
        "liteAV 11.6版本（2.0）",
        "liteAV 11.7版本（2.0）",
        "liteAV 11.8（2.0）",
        "liteAV 11.9（2.0）",
        "liteAV 12.0（2.0）",
        "liteAV 12.1（2.0）",
        "liteAV 12.2（2.0）",
        "liteAV 12.3（2.0）",
        "liteAV 12.4（2.0）",
        "liteAV 12.5（2.0）",
        "liteAV 12.6（2.0）",
    ]
    output_dir = "dif_version_bug_compare"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "不同版本缺陷统计对比报表_数据工作日10-18点整点更新.xlsx")

    # 静默输出
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    root_logger = logging.getLogger()
    old_level = root_logger.level
    old_handlers = root_logger.handlers.copy()
    root_logger.setLevel(logging.CRITICAL + 1)
    root_logger.handlers = []
    try:
        cos_url = generator.generate_defect_report(workspace_id, version_list, output_file=output_file)
    except Exception as e:
        print("定时任务执行失败：", e)
        cos_url = None
    finally:
        sys.stdout = old_stdout
        root_logger.setLevel(old_level)
        root_logger.handlers = old_handlers

    print("定时任务执行完成，文件已保存：", output_file)

def start_scheduler():
    scheduler = BackgroundScheduler()
    trigger = CronTrigger(day_of_week='mon-fri', hour='8', minute=0, second=0)
    scheduler.add_job(run_defect_report, trigger, id='defect_report_job', replace_existing=True)
    scheduler.start()
    print("定时任务已启动：工作日8整点执行")
    # 立即先跑一次
    # run_defect_report()
    return scheduler



import json
import sys
import io
import logging

def handle_export_story_cron(server, chat_id_json_path="bug2story_task.json"):
    """
    定时任务专用，chat_id 从 json 文件读取
    """
    try:
        # 1. 读取 chat_id
        with open(chat_id_json_path, "r", encoding="utf-8") as f:
            chat_id_data = json.load(f)
        # 假设 json 结构为 {"chat_id": "xxxx"} 或 {"chat_ids": ["id1", "id2"]}
        if "chat_id" in chat_id_data:
            chat_ids = [chat_id_data["chat_id"]]
        elif "chat_ids" in chat_id_data:
            chat_ids = chat_id_data["chat_ids"]
        else:
            raise ValueError("bug2story_task.json 格式错误，需包含 chat_id 或 chat_ids 字段")

        # 2. 拉取TAPD需求，生成Excel
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            handler = TAPDHandler(
                client_id="bugtrack_notify",
                client_secret="922DEEF8-BF8D-C548-8986-BB63EFA137E6"
            )
            base_params = {
                "workspace_id": 20428244,
                "name": "【Bug转需求】",
                "fields": "id,name,status,owner,creator,created,modified",
                "order": "created desc",
                "created": ">2023-12-31"
            }
            excel_path, owners, empty_owner_list = fetch_all_stories(handler, base_params)
        finally:
            sys.stdout = old_stdout

        # 3. 构造@人列表
        mention_str = " ".join([f"<@{uid}>" for uid in owners])

        fetcher = TapdBug2StoryHrefFetcher()
        href_story = fetcher.get_story_list_href(
            workspace_id=20428244,
            name_contains="bug转需求",
            status="新|已排期|开发中|产品体验中|规划中|评审中|测试中|待排期|初评|测试评审|待规划|已评审|待测试|待验收",
            owner="当前登录用户"
        )

        text = (
            "【bug转需求类需求晾晒】请相关负责人尽快处理。\n"
            f"详情见附件Excel，或点击查看：[点击查看自己所负责的需求]({href_story})\n"
            f"{mention_str}"
        )

        # 4. 发送Excel和markdown到所有 chat_id
        for chat_id in chat_ids:
            server.send_file(chat_id, excel_path)
            server.send_markdown(chat_id, text)

            # 针对没有处理人的需求，单独@创建人并发消息
            if empty_owner_list:
                msg_lines = []
                for item in empty_owner_list:
                    try:
                        bug_id, title, creator = item.split("_", 2)
                    except Exception:
                        continue
                    msg_lines.append(f"需求【{title}】(ID:{bug_id}) 暂无负责人，请 <@{creator}> 关注处理。")
                if msg_lines:
                    msg = "以下需求暂无负责人：\n" + "\n".join(msg_lines)
                    server.send_markdown(chat_id, msg)

        # 5. 返回简单文本
        ret = RspTextMsg()
        return ret

    except Exception as e:
        logging.exception("定时任务需求导出推送失败")
        ret = RspTextMsg()
        ret.content = f"❌ 定时任务需求导出推送失败：{str(e)}"
        return ret

