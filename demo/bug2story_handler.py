import io
import logging
import sys
from datetime import datetime
from typing import List, Any

import pandas as pd

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