import io
import logging
import sys
from datetime import datetime
from functools import partial
from typing import List, Any

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services.bug2story.bug2story_data_fetcher import fetch_all_stories
from services.bug2story.tapd_bug2story_href import TapdBug2StoryHrefFetcher
from services.tapd_client import TAPDHandler
from src.wecom_bot_svr import RspTextMsg


def get_now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_created_filter(start_time: str, end_time: str = None) -> str:
    if not end_time:
        end_time = get_now_str()
    # TAPD格式要求 >起始,<结束
    return f">{start_time} 00:00:00,<{end_time}"


def truncate_str_cn(s: str, max_len: int) -> str:
    """按单位长度（中文2，英文1）截断字符串，超出加..."""
    count = 0
    result = ''
    for ch in s:
        width = 2 if ord(ch) > 127 else 1
        if count + width > max_len:
            result += '...'
            break
        result += ch
        count += width
    return result


def gen_story_list_text_batches_from_excel(
    df: pd.DataFrame,
    workspace_id: int,
    max_count: int = 10,
    ascending: bool = True,
    start_time: str = "2024-01-01",
    batch_size: int = 12,
    client_id: str = "",
    client_secret: str = ""
) -> List[str]:
    """将需求列表DataFrame分批生成可发送的文本内容"""
    df = df[df['需求名称'].notnull()]
    df = df.sort_values(by='创建时间', ascending=ascending)
    fetcher = TapdBug2StoryHrefFetcher(client_id, client_secret)
    created = build_created_filter(start_time)
    all_href_story = fetcher.get_story_list_href(
        workspace_id=workspace_id,
        name_contains="bug转需求",
        status="新|已排期|开发中|规划中|初评|待排期|待规划",
        created=created
    )
    order_text = "正序" if ascending else "倒序"
    header = (
        f"**请各负责人关注 bug转需求 问题：优先解决严重单**\n"
        f"👇 以下为{start_time}以来 按创建时间{order_text}的 未结束需求\n"
        f"[需求列表视图(详情)]({all_href_story})\n"
    )

    lines = []
    for idx, row in enumerate(df.head(max_count).itertuples(), 1):
        name = str(row.需求名称)
        prefix = "【Bug转需求】"
        if name.startswith(prefix):
            name = name[len(prefix):]
        name = truncate_str_cn(name, 60)
        status = str(row.状态)
        owner = str(row.负责人).replace('\n', '').replace(';', '')
        owner_short = owner.split()[0] if owner else ""
        story_id = getattr(row, 'ID', None)
        href = ""
        if story_id:
            try:
                href = fetcher.get_story_list_href(
                    workspace_id=workspace_id,
                    story_id=str(story_id),
                    created=created
                )
            except Exception:
                href = ""
        view_str = f"[查看]({href})" if href else "查看"
        lines.append(f"• 需求{idx} {name} `({status} {owner_short})` {view_str}")

    # 分批
    batches = []
    total = len(lines)
    for i in range(0, total, batch_size):
        batch_lines = lines[i:i + batch_size]
        if i == 0:
            batch_text = header + "\n" + "\n".join(batch_lines)
        else:
            batch_text = "\n".join(batch_lines)
        batches.append(batch_text)

    # 最后加上“查看更多”链接
    if len(df) > max_count:
        batches[-1] += (
            f"\n ...... \n\n[需求数量较多，点击前往查看全部 'bug转需求类' 需求]({all_href_story})\n"
        )

    # owner链接和@信息只加在最后一批
    owner_href_story = fetcher.get_story_list_href(
        workspace_id=workspace_id,
        name_contains="bug转需求",
        status="新|已排期|开发中|规划中|初评|待排期|待规划",
        owner="当前登录用户"
    )
    owners = set()
    for owner in df['负责人']:
        if pd.isna(owner):
            continue
        for o in str(owner).replace('\n', ' ').replace(';', ' ').split():
            if o:
                owners.add(o)
    mention_str = " ".join([f"<@{o}>" for o in owners])
    batches[-1] += f"\n[点击查看自己负责的需求👍]({owner_href_story})\n\n{mention_str}"

    return batches


def handle_export_story(
    req_msg: Any,
    server: Any,
    client_id: str,
    client_secret: str,
    workspace_id: int,
    max_count: int = 10,
    ascending: bool = False,
    created: str = "2024-01-01"
) -> RspTextMsg:
    try:
        # 捕获stdout，防止第三方库打印干扰
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            handler = TAPDHandler(
                client_id=client_id,
                client_secret=client_secret
            )
            base_params = {
                "workspace_id": workspace_id,
                "name": "【Bug转需求】",
                "fields": "id,name,status,owner,creator,created,modified",
                "order": "created desc",
                "created": f">{created}"
            }
            df, owners, empty_owner_list = fetch_all_stories(handler, base_params)
        finally:
            sys.stdout = old_stdout

        # 分批生成文本并发送
        batches = gen_story_list_text_batches_from_excel(
            df,
            workspace_id=workspace_id,
            max_count=max_count,
            ascending=ascending,
            start_time=created,
            batch_size=12,
            client_id=client_id,
            client_secret=client_secret
        )
        for batch in batches:
            server.send_markdown(req_msg.chat_id, batch)

        # 处理无负责人的需求
        fetcher = TapdBug2StoryHrefFetcher(client_id, client_secret)
        if empty_owner_list:
            msg_lines = []
            for item in empty_owner_list:
                try:
                    bug_id, title, creator = item.split("_", 2)
                except Exception:
                    continue
                href = fetcher.get_story_list_href(
                    workspace_id=workspace_id,
                    story_id=str(bug_id)
                )
                msg_lines.append(
                    f"\n\n【{title}】([ID:{bug_id}]({href})) 暂无负责人，请创建人 <@{creator}> 关注处理，点击ID进入详情页。"
                )
            if msg_lines:
                msg = "以下需求暂无负责人：\n" + "\n".join(msg_lines)
                server.send_markdown(req_msg.chat_id, msg)

        return RspTextMsg()

    except Exception as e:
        logging.exception("需求导出推送失败")
        ret = RspTextMsg()
        ret.content = f"❌ 需求导出推送失败：{str(e)}"
        return ret




# ========== 定时任务相关 ==========

import os
import json
from datetime import datetime

def parse_cron_time(cron_expr):
    """
    解析cron表达式，返回中文描述。
    支持格式：分 时 日 月 周
    例子：
    - "0 10-18 * * *" -> "每天10点到18点整点执行"
    - "0 10-18 * * 1-5" -> "工作日10点到18点整点执行"
    - "*/5 * * * *" -> "每5分钟执行"
    - "*/10 11-18 * * *" -> "每天11点到18点每10分钟执行"
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return "未知时间"

    minute, hour, day, month, weekday = parts

    # 解析分钟
    if minute == '*':
        minute_str = "每分钟"
    elif minute.startswith('*/'):
        interval = minute[2:]
        minute_str = f"每{interval}分钟"
    else:
        minute_str = f"{minute.zfill(2)}分"

    # 解析小时
    if hour == '*':
        hour_str = "每小时"
    elif '-' in hour:
        start_hour, end_hour = hour.split('-', 1)
        hour_str = f"{int(start_hour)}点到{int(end_hour)}点"
    else:
        hour_str = f"{hour.zfill(2)}点"

    # 解析星期
    if weekday == '*':
        weekday_str = "每天"
    elif weekday in ['1-5', '1,2,3,4,5']:
        weekday_str = "工作日"
    elif weekday in ['0', '7']:
        weekday_str = "周日"
    else:
        days_map = {
            '0': '周日', '1': '周一', '2': '周二', '3': '周三',
            '4': '周四', '5': '周五', '6': '周六', '7': '周日'
        }
        days = []
        for part in weekday.split(','):
            if '-' in part:
                start, end = part.split('-')
                start, end = int(start), int(end)
                days.extend([days_map.get(str(d), f"周{d}") for d in range(start, end+1)])
            else:
                days.append(days_map.get(part, f"周{part}"))
        weekday_str = "、".join(days)

    # 组合描述
    # 判断是否是整点（分钟为0）
    if minute == '0':
        time_desc = f"{hour_str}整点"
    else:
        time_desc = f"{hour_str}{minute_str}"

    # 处理特殊情况
    if minute.startswith('*/'):
        if hour == '*':
            # 例如每5分钟执行，不考虑小时和星期限制
            return f"{minute_str}执行"
        else:
            # 例如 "*/10 11-18 * * *"
            return f"{weekday_str}{hour_str}{minute_str}执行"

    return f"{weekday_str}{time_desc}执行"

def add_bug2story_task(chat_id, max_count=10, ascending=True, created=None, workspace_id=None,
                       client_id=None, client_secret=None, cron="0 19 * * *",
                       json_path="bug2story_task.json"):
    global param_dict
    default_config = {
        "created": created or datetime.now().strftime("%Y-%m-%d"),
        "max_count": max_count,
        "ascending": ascending,
        "workspace_id": workspace_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "schedule": {
            "cron": cron  # 这里用传入的cron参数
        }
    }
    try:
        # 先判断文件是否存在且非空
        if not os.path.exists(json_path) or os.path.getsize(json_path) == 0:
            param_dict = {}
        else:
            with open(json_path, "r", encoding="utf-8") as f:
                try:
                    param_dict = json.load(f)
                except json.JSONDecodeError:
                    return False, f"添加定时任务失败: {json_path} 文件内容不是合法JSON。", None

        is_update = chat_id in param_dict
        param_dict[chat_id] = default_config

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(param_dict, f, ensure_ascii=False, indent=2)

        cron_expr = default_config['schedule']['cron']
        time_str = parse_cron_time(cron_expr)

        order_str = "正序" if default_config['ascending'] else "倒序"
        base_msg = (
            f"将于{time_str}推送。\n"
            f"推送内容：自{default_config['created']}以来，"
            f"按创建时间{order_str}，"
            f"未结束的“bug转需求”需求，"
            f"最多{default_config['max_count']}条。"
        )
        if is_update:
            msg = "定时任务已更新，" + base_msg
        else:
            msg = "定时任务已添加，" + base_msg

        return True, msg, default_config
    except Exception as e:
        return False, f"添加定时任务失败: {e}", None

def run_bug2story_once(server, chat_id, params):
    class DummyReqMsg:
        pass
    req_msg = DummyReqMsg()
    req_msg.chat_id = chat_id

    created = params.get("created", "2024-01-01")
    max_count = int(params.get("max_count", 10))
    ascending = bool(params.get("ascending", False))
    workspace_id = params.get("workspace_id")
    client_id = params.get("client_id")
    client_secret = params.get("client_secret")

    handle_export_story(
        req_msg, server,
        max_count=max_count,
        ascending=ascending,
        created=created,
        workspace_id=workspace_id,
        client_id=client_id,
        client_secret=client_secret
    )

def run_bug2story_task_from_file(server, chat_id, json_path):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            param_dict = json.load(f)
        params = param_dict.get(chat_id)
        print(f"当前参数: {params}")
        if not params:
            print(f"[{datetime.now()}] chat_id={chat_id} 未找到配置，跳过")
            return
        run_bug2story_once(server, chat_id, params)
        print(f"[{datetime.now()}] bug2story定时任务已执行，chat_id={chat_id}")
    except Exception as e:
        print(f"定时任务执行失败: {e}")

def start_bug2story_scheduler(server, json_path="bug2story_task.json"):
    try:
        if not os.path.exists(json_path) or os.path.getsize(json_path) == 0:
            param_dict = {}
        else:
            with open(json_path, "r", encoding="utf-8") as f:
                param_dict = json.load(f)
    except FileNotFoundError:
        param_dict = {}
    except json.JSONDecodeError:
        print(f"警告：{json_path} 文件内容不是合法JSON，已忽略。")
        param_dict = {}
    scheduler = BackgroundScheduler()
    for chat_id, params in param_dict.items():
        schedule = params.get("schedule", {})
        cron_expr = schedule.get("cron", "0 18 * * *")  # 默认每天18:00
        trigger = CronTrigger.from_crontab(cron_expr)
        job_id = f"bug2story_report_job_{chat_id}"
        scheduler.add_job(
            partial(run_bug2story_task_from_file, server, chat_id, json_path),
            trigger,
            id=job_id,
            replace_existing=True
        )
        print(f"已为chat_id={chat_id}注册定时任务，cron={cron_expr}")
    scheduler.start()
    print("所有定时任务已启动")
    return scheduler

# ========== bug2story参数解析 ==========

import shlex
import re

def parse_bug2story_args(content):
    max_count = 10
    ascending = True
    created = "2024-01-01"
    workspace_id = None
    cron_expr = None

    parts = shlex.split(content)
    args = parts[1:] if parts and parts[0].startswith('bug转需求通知') else parts

    # workspace_id 是最后一个参数，且是纯数字且长度大于6
    if args and args[-1].isdigit() and len(args[-1]) > 6:
        workspace_id = int(args[-1])
        args = args[:-1]
    else:
        workspace_id = None  # 必须有workspace_id

    # cron 表达式是倒数第一个参数（现在是最后一个了），但因为 workspace_id 已经去掉了，cron 就是最后一个参数
    if args:
        cron_expr = args[-1]
        args = args[:-1]
    else:
        cron_expr = "0 19 * * *"  # 默认cron

    # created 日期如果存在且格式正确，取最后一个参数
    if args and re.match(r'^\d{4}-\d{2}-\d{2}$', args[-1]):
        created = args[-1]
        args = args[:-1]

    # 解析剩余参数
    for arg in args:
        if arg.isdigit():
            max_count = int(arg)
        elif arg.lower() == 'asc':
            ascending = True
        elif arg.lower() == 'desc':
            ascending = False

    return max_count, ascending, created, workspace_id, cron_expr