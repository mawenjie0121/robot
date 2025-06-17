import requests
from typing import Optional, Union
from datetime import datetime

# 默认处理中状态
DEFAULT_IN_PROCESS_STATES = (
    '新', '已排期', '开发中', '产品体验中', '规划中',
    '评审中', '测试中', '待排期', '初评', '测试评审',
    '待规划', '已评审', '待测试', '待验收'
)

class TapdBug2StoryHrefFetcher:
    def __init__(self, api_user: str = '', api_password: str = ''):
        self.api_user = api_user
        self.api_password = api_password
        self.url = "http://apiv2.tapd.woa.com/stories/filter_to_query_token"

    def get_story_list_href(
        self,
        workspace_id: int,
        name_contains: Optional[str] = None,
        status: Optional[Union[str, set]] = None,
        owner: Optional[str] = None,
        show_fields: Optional[str] = None,
        block_type: Optional[str] = None,
        custom_field_one: Optional[str] = None,
        order: str = "created desc",
        story_id: Optional[str] = None,
        created: Optional[str] = None,
    ) -> str:
        """
        获取需求列表 href
        :param created: 时间区间字符串，如 '>2025-03-07 00:00,<2025-06-05 23:53:00'
        """
        filter_dict = {}
        if name_contains:
            filter_dict["name"] = name_contains
        if status:
            # 支持 set 或 str
            if isinstance(status, set):
                filter_dict["status"] = "|".join(status)
            else:
                filter_dict["status"] = status
        if owner:
            filter_dict["owner"] = owner
        if custom_field_one:
            filter_dict["custom_field_one"] = custom_field_one
        if story_id:
            filter_dict["id"] = story_id
        if created:
            filter_dict["created"] = created

        data = {
            "workspace_id": workspace_id,
            "order": order
        }
        for k, v in filter_dict.items():
            data[f"filter[{k}]"] = v
        if show_fields:
            data["show_fields"] = show_fields

        resp = requests.post(
            self.url,
            data=data,
            auth=(self.api_user, self.api_password),
            timeout=10
        )
        try:
            resp_json = resp.json()
        except Exception:
            raise Exception(f"接口返回非JSON: {resp.text}")

        if resp_json.get("status") == 1:
            return resp_json["data"]["href"]
        else:
            raise Exception(f"获取 href 失败: {resp_json}")

def get_now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def build_created_filter(start_time: str, end_time: Optional[str] = None) -> str:
    if not end_time:
        end_time = get_now_str()
    # TAPD格式要求 >起始,<结束
    return f">{start_time} 00:00:00,<{end_time}"

if __name__ == "__main__":
    # 请替换为实际的api_user和api_password
    fetcher = TapdBug2StoryHrefFetcher(api_user="your_user", api_password="your_password")

    # 示例：获取需求列表链接
    start_time = "2024-01-01"
    created = build_created_filter(start_time)
    href_story = fetcher.get_story_list_href(
        workspace_id=20428244,
        name_contains="bug转需求",
        status="|".join(DEFAULT_IN_PROCESS_STATES),
        created=created
    )
    print("需求列表链接:", href_story)