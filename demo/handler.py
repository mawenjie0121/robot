from wecom_bot_svr import WecomBotServer, RspTextMsg, RspMarkdownMsg, ReqMsg

import base64
import hashlib
import sys
import io
import os
import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from services.bug2story.bug2story_data_fetcher import fetch_all_stories
from services.bug2story.tapd_bug2story_href import TapdBug2StoryHrefFetcher
from services.bugs.tapd_bugs_herf import TapdBugsHrefFetcher
from services.bugs.tapd_bugs_reporter import TapdBugReporter
from my_scheduler import run_defect_report
# 启动定时任务
from my_scheduler import start_scheduler
from services.tapd_client import TAPDHandler
from services.bugs.tapd_bugs_statistics import TapdBugStatistics
from services.util import utils

import re
from data_store import set_bugtrack, get_bugtrack, update_bugtrack, delete_bugtrack

def handle_bug_report(content, req_msg, server, client_id, client_secret):
    try:
        version_report = content[len('bug report'):].strip()
        if not version_report:
            ret = RspTextMsg()
            ret.content = "请指定版本号，例如：bug report liteAV 12.6（2.0） 或 bug report liteAV 12.6（2.0）|20428244"
            return ret
        workspace_id = 20428244
        if '|' in version_report:
            version_part, workspace_part = version_report.split('|', 1)
            version_report = version_part.strip()
            workspace_id = workspace_part.strip()
            try:
                workspace_id = int(workspace_id)
            except Exception:
                ret = RspTextMsg()
                ret.content = f"❌ 项目空间id格式错误，请输入数字，例如：bug report liteAV 12.6（2.0）|20428244"
                return ret
        if not version_report:
            ret = RspTextMsg()
            ret.content = "请指定版本号，例如：bug report liteAV 12.6（2.0）"
            return ret

        reporter = TapdBugReporter(client_id=client_id, client_secret=client_secret)
        fetcher = TapdBugsHrefFetcher(client_id=client_id, client_secret=client_secret)

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        root_logger = logging.getLogger()
        old_level = root_logger.level
        old_handlers = root_logger.handlers.copy()
        root_logger.setLevel(logging.CRITICAL + 1)
        root_logger.handlers = []
        try:
            analysis_report, analyzer_res, _ = reporter.generate_report(
                version_report=version_report,
                workspace_id=workspace_id,
                save_excel=True
            )

            href_bugs_all = fetcher.get_bug_list_href(
                version_report=version_report,
                workspace_id=workspace_id,
                show_fields="title,current_owner,status,custom_field_one",
            )
            href_bugs_un = fetcher.get_bug_list_href(
                version_report=version_report,
                workspace_id=workspace_id,
                status="新|排查中|接受/处理|重新打开",
                show_fields="title,current_owner,status,custom_field_one",
            )
            href_owner = fetcher.get_bug_list_href(
                version_report=version_report,
                workspace_id=workspace_id,
                status="新|排查中|接受/处理|重新打开",
                show_fields="title,current_owner,status,custom_field_one",
                owner="当前登录用户"
            )
            analysis_report += "\n\n📊 " + version_report + "版本: TAPD链接 缺陷列表过滤条件：已拒绝和确认关闭不统计，严重程度为建议和提示不进行统计。"
            analysis_report += f"\n ①当前版本全部bug 👉 [点击查看所有bug]({href_bugs_all})"
            analysis_report += f"\n ②当前版本未解决bug 👉 [点击查看未解决bug]({href_bugs_un})"
            analysis_report += f"\n ③当前版本你所负责的bug 👉 [点击查看自己负责缺陷]({href_owner})"
        finally:
            sys.stdout = old_stdout
            root_logger.setLevel(old_level)
            root_logger.handlers = old_handlers

        ret = RspMarkdownMsg()
        if len(analysis_report) > 3000:
            ret.content = analysis_report[:3000] + "\n\n...(内容过长已截断)"
        else:
            ret.content = analysis_report
        server.send_markdown(req_msg.chat_id, ret.content)

        # 发送图片
        if os.path.exists(analyzer_res):
            base64_img, md5_img = file_to_base64_and_md5(analyzer_res)
            server.send_encoded_image(req_msg.chat_id, base64_img, md5_img)

        return RspTextMsg()
    except Exception as e:
        traceback.print_exc()
        ret = RspTextMsg()
        ret.content = f"❌ 报告生成失败：{str(e)}"
        return ret

def async_send_image(server, chat_id, img_filename):
    if os.path.exists(img_filename):
        base64_img, md5_img = file_to_base64_and_md5(img_filename)
        server.send_encoded_image(chat_id, base64_img, md5_img)

def parse_bug_statistics_args(version_report):
    """
    支持无序参数解析，返回 version_report, workspace_id, include_prompt_advice, threshold
    """
    workspace_id = 20428244
    include_prompt_advice = False
    threshold = 0  # 默认阈值
    version = None

    # 拆分参数
    parts = [p.strip() for p in version_report.split('|') if p.strip()]
    for p in parts:
        if p.startswith('@'):
            try:
                threshold = int(p[1:])
            except Exception:
                raise ValueError("❌ @后面请跟数字，例如 |@8")
        elif p.isdigit():
            workspace_id = int(p)
        elif p.lower() == "true":
            include_prompt_advice = True
        elif p.lower() == "false":
            include_prompt_advice = False
        else:
            # 认为是版本号
            version = p

    if not version:
        raise ValueError("请指定版本号，例如：bug statistics liteAV 12.6（2.0）")

    return version, workspace_id, include_prompt_advice, threshold

def handle_bug_statistics(content, req_msg, server, client_id, client_secret):
    try:
        if content.startswith('bug statistics😈'):
            severity_mode = "3level"
            version_report = content[len('bug statistics😈'):].strip()
        else:
            severity_mode = "2level"
            version_report = content[len('bug statistics'):].strip()

        if not version_report:
            ret = RspTextMsg()
            ret.content = "请指定版本号，例如：bug statistics liteAV 12.6（2.0） 或 bug statistics liteAV 12.6（2.0）|20428244"
            return ret

        # 新参数解析
        try:
            version_report, workspace_id, include_prompt_advice, threshold = parse_bug_statistics_args(version_report)
        except Exception as e:
            ret = RspTextMsg()
            ret.content = str(e)
            return ret

        reporter = TapdBugReporter(client_id=client_id, client_secret=client_secret)
        fetcher = TapdBugsHrefFetcher(client_id=client_id, client_secret=client_secret)

        # 定义两个耗时任务
        def report_task():
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            root_logger = logging.getLogger()
            old_level = root_logger.level
            old_handlers = root_logger.handlers.copy()
            root_logger.setLevel(logging.CRITICAL + 1)
            root_logger.handlers = []
            try:
                analysis_report, analyzer_res, unresolved_df_dict = reporter.generate_report(
                    version_report=version_report,
                    workspace_id=workspace_id,
                    save_excel=True,
                    include_prompt_advice=include_prompt_advice
                )
                if analysis_report == "⚠️ 未发现符合要求的缺陷数据 / 版本号有误":
                    return analysis_report, " ", " "

                # 并发获取三个 href
                with ThreadPoolExecutor() as href_executor:
                    future_all = href_executor.submit(
                        fetcher.get_bug_list_href,
                        version_report=version_report,
                        workspace_id=workspace_id,
                        show_fields="title,current_owner,status,custom_field_one",
                        include_prompt_advice=include_prompt_advice
                    )
                    future_un = href_executor.submit(
                        fetcher.get_bug_list_href,
                        version_report=version_report,
                        workspace_id=workspace_id,
                        status="新|排查中|接受/处理|重新打开",
                        show_fields="title,current_owner,status,custom_field_one",
                        include_prompt_advice=include_prompt_advice
                    )
                    future_owner = href_executor.submit(
                        fetcher.get_bug_list_href,
                        version_report=version_report,
                        workspace_id=workspace_id,
                        status="新|排查中|接受/处理|重新打开",
                        show_fields="title,current_owner,status,custom_field_one",
                        owner="当前登录用户",
                        include_prompt_advice=include_prompt_advice
                    )
                    href_bugs_all = future_all.result()
                    href_bugs_un = future_un.result()
                    href_owner = future_owner.result()

                if include_prompt_advice:
                    analysis_report += (
                        f"\n\n📊 {version_report}版本TAPD链接 缺陷列表过滤条件："
                        "已拒绝和确认关闭不统计，严重程度全选。"
                    )
                else:
                    analysis_report += (
                        f"\n\n📊 {version_report}版本TAPD链接 缺陷列表过滤条件："
                        "已拒绝和确认关闭不统计，严重程度为建议和提示不进行统计。"
                    )
                analysis_report += f"\n ①当前版本全部bug 👉 [点击查看所有bug]({href_bugs_all})"
                analysis_report += f"\n ②当前版本未解决bug 👉 [点击查看未解决bug]({href_bugs_un})"
                analysis_report += f"\n ③当前版本你所负责的bug 👉 [点击查看自己负责缺陷]({href_owner})"
                return analysis_report, analyzer_res, unresolved_df_dict
            finally:
                sys.stdout = old_stdout
                root_logger.setLevel(old_level)
                root_logger.handlers = old_handlers

        def statistics_task():
            statistics = TapdBugStatistics(client_id=client_id, client_secret=client_secret)
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            root_logger = logging.getLogger()
            old_level = root_logger.level
            old_handlers = root_logger.handlers.copy()
            root_logger.setLevel(logging.CRITICAL + 1)
            root_logger.handlers = []
            try:
                analysis_report = statistics.generate_statistics(
                    version_report=version_report,
                    workspace_id=workspace_id,
                    severity_mode=severity_mode
                )
                img_filename = utils.excel_to_colored_screenshot(
                    analysis_report,
                    f"output_statistics/{workspace_id}_分析图.png"
                )
                return img_filename
            finally:
                sys.stdout = old_stdout
                root_logger.setLevel(old_level)
                root_logger.handlers = old_handlers

        # 并发执行两个主任务
        with ThreadPoolExecutor() as executor:
            future_report = executor.submit(report_task)
            future_stats = executor.submit(statistics_task)

            # 在并发任务之后添加以下代码
            from collections import defaultdict

            # 从future_report任务获取结果
            analysis_report, analyzer_res, unresolved_df_dict = future_report.result()
            if analysis_report == "⚠️ 未发现符合要求的缺陷数据 / 版本号有误":
                ret = RspMarkdownMsg()
                ret.content = f"⚠️ 未发现符合要求的缺陷数据 / 版本号有误"
                return ret

            # 创建用于计数的字典
            owner_count = defaultdict(int)

            if unresolved_df_dict != " ":
                # 处理unresolved_df_dict字典排序（当值为整数时）
                sorted_unresolved_dict = dict(
                    sorted(
                        unresolved_df_dict.items(),
                        key=lambda x: -x[1]  # 直接取负值实现降序排列
                    )
                )

                # 处理unresolved_df_dict字典（负责人分布统计）
                for owner_str, count in sorted_unresolved_dict.items():
                    # 去除分号并拆分多人负责的情况
                    owners = [o.strip() for o in owner_str.rstrip(';').split(';') if o.strip()]

                    # 如果是单个人负责
                    if len(owners) == 1:
                        owner_count[owners[0]] += count
                    # 如果是多个人共同负责
                    else:
                        # 每个人分得相同的缺陷数
                        for owner in owners:
                            owner_count[owner] += count

                # 找出超过阈值的负责人
                over_threshold_owners = set()
                for owner, count in owner_count.items():
                    if count >= threshold:
                        over_threshold_owners.add(owner)

                # 生成@字符串
                if over_threshold_owners:
                    mention_str = " ".join([f"<@{o}>" for o in over_threshold_owners])
                    if threshold == 0:
                        mention_msg = f"\n请对应处理人进行处理: {mention_str}"
                    else:
                        mention_msg = f"\n未解决缺陷>={threshold}个的处理人，请对应处理人进行处理: {mention_str}"

                    # 添加到返回内容中
                    if len(analysis_report) + len(mention_msg) > 3000:
                        # 如果内容太长，分开发送
                        server.send_text(req_msg.chat_id, mention_msg)
                    else:
                        analysis_report = analysis_report + "\n\n" + mention_msg

            # 然后继续发送markdown内容
            ret = RspMarkdownMsg()
            if len(analysis_report) > 3000:
                ret.content = analysis_report[:3000] + "\n\n...(内容过长已截断)"
            else:
                ret.content = analysis_report
            server.send_markdown(req_msg.chat_id, ret.content)

            # 异步发第一张图片
            if analyzer_res and os.path.exists(analyzer_res) and server is not None:
                threading.Thread(target=async_send_image, args=(server, req_msg.chat_id, analyzer_res)).start()

            # 等待统计图片任务完成，异步发第二张图片
            img_filename = future_stats.result()
            if img_filename and os.path.exists(img_filename) and server is not None:
                threading.Thread(target=async_send_image, args=(server, req_msg.chat_id, img_filename)).start()

        return RspTextMsg()
    except Exception as e:
        traceback.print_exc()
        ret = RspTextMsg()
        ret.content = f"❌ 统计报告生成失败：请查看是否是版本号或项目空间ID出错"
        return ret

def handle_version_compare_report(req_msg, server, client_id, client_secret):
    try:
        file_path = "dif_version_bug_compare/不同版本缺陷统计对比报表_数据工作日10-18点整点更新.xlsx"
        if not os.path.exists(file_path):
            ret = RspTextMsg()
            ret.content = "❌ 文件不存在，请稍后再试。"
            return ret
        server.send_file(req_msg.chat_id, file_path)
        ret = RspTextMsg()
        ret.content = "✅ 文件已发送，请查收。请注意数据时效性,数据工作日10-18点整点更新!"
        return ret
    except Exception as e:
        traceback.print_exc()
        ret = RspTextMsg()
        ret.content = f"❌ 文件发送失败：{str(e)}"
        return ret

def file_to_base64_and_md5(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
        b64 = base64.b64encode(data).decode()
        md5 = hashlib.md5(data).hexdigest()
    return b64, md5

def handle_simple_bugtrack_command(content, req_msg, server, client_id, client_secret):
    # 存/insert
    m = re.match(r"(存|insert)\s*[\[【]([^\]】]+)[\]】]\s+(.+)", content, re.IGNORECASE)
    if m:
        tag = m.group(2).strip()
        value = m.group(3).strip()
        ok = set_bugtrack(tag, value)
        ret = RspTextMsg()
        if ok:
            ret.content = f"已存储 [{tag}]。"
        else:
            ret.content = f"[{tag}] 已存在，不能重复存储。"
        return ret

    # 查/select
    m = re.match(r"(查|select)\s*[\[【]([^\]】]+)[\]】]", content, re.IGNORECASE)
    if m:
        tag = m.group(2).strip()
        value = get_bugtrack(tag)
        ret = RspTextMsg()
        if value is not None:
            ret.content = f"[{tag}] 的内容：\n{value}"
        else:
            ret.content = f"未找到 [{tag}]。"
        return ret

    # 改/update
    m = re.match(r"(改|update)\s*[\[【]([^\]】]+)[\]】]\s+(.+)", content, re.IGNORECASE)
    if m:
        tag = m.group(2).strip()
        value = m.group(3).strip()
        ok = update_bugtrack(tag, value)
        ret = RspTextMsg()
        if ok:
            ret.content = f"[{tag}] 已更新。"
        else:
            ret.content = f"[{tag}] 不存在，无法更新。"
        return ret

    # 删/delete
    m = re.match(r"(删|delete)\s*[\[【]([^\]】]+)[\]】]", content, re.IGNORECASE)
    if m:
        tag = m.group(2).strip()
        ok = delete_bugtrack(tag)
        ret = RspTextMsg()
        if ok:
            ret.content = f"[{tag}] 已删除。"
        else:
            ret.content = f"[{tag}] 不存在，无法删除。"
        return ret

    return None

import yaml

def add_group_permission(chat_id, client_id, client_secret, config_path):
    # 读取现有配置
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if "groups" not in config:
        config["groups"] = {}
    # 添加或更新群聊配置
    config["groups"][chat_id] = {
        "client_id": client_id,
        "client_secret": client_secret
    }
    # 写回配置文件
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True)
    return True