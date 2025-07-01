from wecom_bot_svr import WecomBotServer, RspTextMsg, RspMarkdownMsg, ReqMsg
from wecom_bot_svr.req_msg import TextReqMsg

import traceback
import sys
import logging
import re


from bug2story_handler import handle_export_story, parse_bug2story_args, add_bug2story_task, run_bug2story_once, \
    start_bug2story_scheduler
from handler import (
    handle_bug_report, handle_bug_statistics,
    handle_version_compare_report, handle_simple_bugtrack_command, add_group_permission
)

# 启动其他定时任务
from my_scheduler import start_scheduler


# 全局集合用于去重，防止重复处理同一条消息
processed_msg_ids = set()

BUG2STORY_JSON_PATH = "bug2story_task.json"

import yaml
import os

# 获取当前文件的上一级目录（demo/）
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录
root_dir = os.path.dirname(current_dir)
# 拼接 config.yaml 路径
config_path = os.path.join(root_dir, "services", "config", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

group_configs = config.get("groups", {})

def is_group_configured(chat_id):
    return chat_id in group_configs

def get_group_config(chat_id):
    return group_configs.get(chat_id, {})


# ========== 帮助信息 ==========

def help_md():
    return """### Help 列表
- at机器人+指令+参数

- 功能一 ：查看整体缺陷分析报告
    - 查看终端大重构空间指定版本的缺陷分析报告：@bug追踪 bug report 版本号
    - 查看其他空间指定版本的缺陷分析报告：@bug追踪 bug report 版本号|项目空间id

- 功能二 ：查看整体缺陷统计报告
    - 使用示例 bug statistics😈 liteAV 12.6（2.0）|20428244|True
    - 查看终端大重构空间指定版本的缺陷统计：@bug追踪 bug statistics 版本号
    - 查看其他空间指定版本的缺陷统计：@bug追踪 bug statistics 版本号|项目空间id
    - 严重程度筛选，传递|True |False 参数  True：严重程度全选， Fasle：严重程度为建议、提示不进行统计
    - 如需将 致命与严重分开 可 @bug追踪 bug statistics😈 版本号

- 功能三 ：查看不同系统版本bug对比: @bug追踪 版本缺陷对比报告

- 功能四 ：sql风格指令存删改查文本数据 指令+tag+内容: @bug追踪 insert [tag] 这是一条tag标签下的文本信息

- 功能五 ：需求列表（bug转需求类）筛选
    - 查看近期“bug转需求”类需求列表：@bug追踪 bug转需求通知
    - 可选参数说明（顺序灵活）：
        - 数字：返回条数（默认10）
        - asc/desc：按创建时间正/倒序（默认按创建时间正序）
        - 日期：筛选起始日期（格式YYYY-MM-DD，默认2024-01-01）
    - 必填参数：
        - 项目空间id，作为最后一个参数
    - 示例用法：
        - @bug追踪 bug转需求通知 20428244               # 最近的10条，默认时间
        - @bug追踪 bug转需求通知 12 20428244            # 最近12条
        - @bug追踪 bug转需求通知 12 asc 20428244        # 12条，按时间升序
        - @bug追踪 bug转需求通知 12 desc 2024-05-01 20428244  # 12条，降序，起始时间2024-05-01
        - @bug追踪 bug转需求通知 asc 2024-06-01 20428244      # 10条，升序，起始时间2024-06-01
        - @bug追踪 bug转需求通知 2024-06-01 20428244          # 10条，降序，起始时间2024-06-01
- 功能六 ：bug转需求通知定时任务开启
    - 在你需要推送的群中，@bug追踪 bug转需求定时通知 项目空间id
    - 示例用法：
        - @bug追踪 bug转需求定时通知 10 asc 2024-01-01 "0 11-18 \\* \\* \\*" 70109736
    - 参数可配置，在功能5的基础上，额外参数 cron表达式 "0 11-18 \\* \\* \\*" -> 每天11-18点定时推送
- 其他功能敬请期待
"""

def handle_help():
    ret = RspMarkdownMsg()
    ret.content = help_md()
    return ret

# ========== 消息处理 ==========
def msg_handler(req_msg: ReqMsg, server: WecomBotServer):
    msg_id = getattr(req_msg, "msg_id", None)
    if msg_id and msg_id in processed_msg_ids:
        return RspTextMsg()
    if msg_id:
        processed_msg_ids.add(msg_id)

    chat_id = getattr(req_msg, "chat_id", None)

    # 先处理“配置权限”指令
    if req_msg.msg_type == 'text' and isinstance(req_msg, TextReqMsg):
        content = req_msg.content.strip()
        if content.startswith("配置权限"):
            m = re.match(r"配置权限\s+client_id=(\S+)\s+client_secret=(\S+)", content)
            ret = RspTextMsg()
            if not m:
                ret.content = "格式错误，请用：配置权限 client_id=xxx client_secret=yyy"
                return ret
            client_id, client_secret = m.group(1), m.group(2)
            add_group_permission(chat_id, client_id, client_secret, config_path)
            # 重新加载 group_configs
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            global group_configs
            group_configs = config.get("groups", {})
            ret.content = "权限配置成功！"
            return ret

    # 判断权限
    if not is_group_configured(chat_id):
        ret = RspTextMsg()
        ret.content = "请配置应用权限，链接：https://iwiki.woa.com/p/4015266215"
        return ret

    # 获取当前群的 client_id, client_secret
    group_cfg = get_group_config(chat_id)
    client_id = group_cfg.get('client_id')
    client_secret = group_cfg.get('client_secret')

    if req_msg.msg_type == 'text' and isinstance(req_msg, TextReqMsg):
        content = req_msg.content.strip()
        if content == 'help':
            help = help_md()  # 你把上面那段 markdown 文档内容放到这个函数里返回
            server.send_markdown(req_msg.chat_id, help)
            ret = RspTextMsg()
            return ret
        elif content.startswith('bug report'):
            return handle_bug_report(content, req_msg, server, client_id, client_secret)
        elif content.startswith('bug statistics') or content.startswith('bug statistics😈'):
            return handle_bug_statistics(content, req_msg, server, client_id, client_secret)
        elif content == '版本缺陷对比报告' and server is not None:
            return handle_version_compare_report(req_msg, server, client_id, client_secret)
        elif content.startswith('bug转需求定时通知'):
            max_count, ascending, created, workspace_id, cron_expr = parse_bug2story_args(content.replace('定时', ''))
            if workspace_id is None:
                ret = RspTextMsg()
                ret.content = "请在命令最后加上 workspace_id（如：bug转需求定时通知 10 asc 2024-06-01 \"0 10-23 * * *\" 123456789），workspace_id 必填。"
                return ret

            ok, msg, params = add_bug2story_task(chat_id, max_count, ascending, created, workspace_id, client_id,
                                                 client_secret, cron_expr)
            if params:
                run_bug2story_once(server, chat_id, params)
            reload_bug2story_scheduler(server)
            server.send_markdown(chat_id, msg)
            ret = RspTextMsg()
            return ret
        elif content.startswith('bug转需求通知'):
            max_count, ascending, created, workspace_id, _ = parse_bug2story_args(content)
            if workspace_id is None:
                ret = RspTextMsg()
                ret.content = "请在命令最后加上 workspace_id（如：bug转需求通知 10 asc 2024-06-01 123456789），workspace_id 必填。"
                return ret
            return handle_export_story(req_msg, server, max_count=max_count, ascending=ascending, created=created,
                                       workspace_id=workspace_id, client_id=client_id, client_secret=client_secret)
        elif re.match(r"^(存|查|改|删|insert|select|update|delete)\s*[\[【]", content, re.IGNORECASE):
            rsp = handle_simple_bugtrack_command(content, req_msg, server, client_id, client_secret)
            if rsp is not None:
                return rsp

    ret = RspTextMsg()
    ret.content = f'具体功能请 @bug追踪help'
    return ret

def event_handler(req_msg):
    ret = RspMarkdownMsg()
    if hasattr(req_msg, "event_type") and req_msg.event_type == 'add_to_chat':
        ret.content = f'群会话ID: {req_msg.chat_id}\n请配置应用权限，链接：https://iwiki.woa.com/p/4015266215\n查询用法请回复: help'
    return ret

# ========== 定时任务 reload 逻辑 ==========


from apscheduler.schedulers import SchedulerNotRunningError

def reload_bug2story_scheduler(server):
    global global_scheduler
    if global_scheduler:
        try:
            if global_scheduler.running:
                global_scheduler.shutdown(wait=False)
        except SchedulerNotRunningError:
            # 调度器未运行，忽略
            pass
    global_scheduler = start_bug2story_scheduler(server)

# ========== 主程序入口 ==========
def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        print("Uncaught exception:", exc_type, exc_value)
        traceback.print_tb(exc_traceback)

    sys.excepthook = handle_exception

    token = 'xxx'
    aes_key = 'xxxxx'
    corp_id = ''
    host = '0.0.0.0'
    port = 5001
    bot_key = 'f0488436-460f-xxxx-a180-1c98aa1104a2'
    bot_name = 'bug追踪'

    start_scheduler()  # 其他定时任务

    server = WecomBotServer(
        bot_name, host, port, path='/wecom_bot',
        token=token, aes_key=aes_key, corp_id=corp_id, bot_key=bot_key
    )

    # 启动 bug2story 定时任务
    global global_scheduler
    global_scheduler = start_bug2story_scheduler(server)

    server.set_message_handler(lambda req_msg: msg_handler(req_msg, server))
    server.set_event_handler(event_handler)
    server.run()

if __name__ == '__main__':
    main()