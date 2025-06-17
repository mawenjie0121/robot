from typing import Optional, List, Dict

from tapdsdk.sdk import TapdAPIClient
import yaml

import os



class TapdBugsFetcher:
    def __init__(self,
                 client_id: str,
                 client_secret: str):
        """初始化缺陷报告生成器"""
        self.sdk = TapdAPIClient(client_id=client_id, client_secret=client_secret)

        # 状态系统配置
        self.status_mapping = {
            "new": "新",
            "unconfirmed": "排查中",
            "in_progress": "接受/处理",
            "resolved": "已解决",
            "closed": "验证关闭",
            "postponed": "延期解决",
            "rejected": "已拒绝",
            "reopened": "重新打开",
            "acknowledged": "确认关闭",
            "feedback": "排查关闭"
        }

        self.severity_mapping = {
            "fatal": "致命",
            "serious": "严重",
            "normal": "一般",
            "prompt": "提示",
            "advice": "建议"
        }

        self.defined_status = list(self.status_mapping.values()) + ["其他状态"]
        self.unresolved_status = ["新", "排查中", "接受/处理", "重新打开"]
        self.auto_keywords = ["自动化", "接口测试", "自动提单"]

    def fetch_bugs(
            self,
            version_report: str,
            workspace_id: int,
            created_filter: str = ">2020-12-31",
            fields: str = "id,title,status,module,severity,version_report,current_owner,reporter,created,modified,custom_field_33",
            severity: str = None,
            include_prompt_advice: bool = False
    ) -> List[Dict]:
        if severity is None:
            if include_prompt_advice:
                severity = "fatal|normal|serious|prompt|advice"
            else:
                severity = "fatal|normal|serious"
        """获取缺陷数据（自动分页）"""
        all_bugs = []
        severity = severity
        created_filter = created_filter
        page = 1
        limit = 200

        try:
            while True:
                params = {
                    "workspace_id": workspace_id,
                    "fields": fields,
                    "version_report": version_report,
                    "created": created_filter,
                    "severity": severity,
                    "limit": limit,
                    "page": page,
                    "status": "new|unconfirmed|in_progress|resolved|closed|postponed|reopened|feedback",
                    "order": "created desc",
                }

                # 传参数调用SDK 获取bug的方法
                response = self.sdk.get_bugs(params)
                if response.get('status') != 1 or not response.get('data'):
                    break

                # 状态字段映射
                for bug in response['data']:
                    original_status = bug["Bug"].get("status", "")
                    original_severity = bug["Bug"].get("severity", "")
                    mapped_status = self.status_mapping.get(original_status, f"未知状态({original_status})")
                    mapped_severity = self.severity_mapping.get(original_severity, f"未知状态({original_severity})")
                    bug["Bug"]["status"] = mapped_status
                    bug["Bug"]["severity"] = mapped_severity

                all_bugs.extend(response['data'])

                if len(response['data']) < limit:
                    break
                page += 1

        except Exception as e:
            print(f"\n❌ 数据获取失败：{str(e)}")
            raise

        return [item["Bug"] for item in all_bugs]


