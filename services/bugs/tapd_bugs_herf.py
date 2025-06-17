import os
import yaml
import requests
from typing import Optional, Dict

class TapdBugsHrefFetcher:
    def __init__(self,
                 client_id: str,
                 client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.url = "http://apiv2.tapd.woa.com/bugs/filter_to_query_token"

    def get_bug_list_href(
        self,
        version_report: str,
        workspace_id: int,
        severity: Optional[str] = None,
        show_fields: Optional[str] = None,
        block_type: Optional[str] = None,
        owner: Optional[str] = None,
        status: str = "新|排查中|接受/处理|已解决|验证关闭|延期解决|重新打开|排查关闭|已关闭",
        include_prompt_advice: bool = False,  # 新增参数
    ) -> str:
        """
        获取缺陷列表 href
        :param version_report: 版本报告
        :param workspace_id: 项目ID
        :param severity: 严重程度
        :param show_fields: 显示字段
        :param block_type: 分组字段
        :param owner: 负责人过滤
        :param status: 状态过滤
        :param include_prompt_advice: 是否包含prompt/advice
        :return: href 链接
        """
        # 根据 include_prompt_advice 设置 severity
        if severity is None:
            if include_prompt_advice:
                severity = "fatal|normal|serious|prompt|advice"
            else:
                severity = "fatal|normal|serious"

        # 组装 filter_dict
        filter_dict = {
            "version_report": version_report,
            "severity": severity,
            "status": status,
        }
        if owner:
            filter_dict["owner"] = owner

        # 只保留有值的filter
        filter_dict = {k: v for k, v in filter_dict.items() if v}

        # 组装data
        data = {
            "workspace_id": workspace_id,
        }
        for k, v in filter_dict.items():
            data[f"filter[{k}]"] = v
        if show_fields:
            data["show_fields"] = show_fields
        if block_type:
            data["block_type"] = block_type

        # 发请求
        resp = requests.post(
            self.url,
            data=data,
            auth=(self.client_id, self.client_secret),
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

if __name__ == "__main__":
    fetcher = TapdBugsHrefFetcher()
    href = fetcher.get_bug_list_href(
        version_report="liteAV 12.6（2.0）",
        workspace_id=20428244,
        # status="new|unconfirmed",
        show_fields="title,current_owner,status,custom_field_one",
        owner="CSIG质量部/云平台产品质量中心",
        # block_type="current_owner",
        include_prompt_advice=True
    )
    print("缺陷列表链接:", href)