import os
from typing import List, Dict, Tuple, Set, Any

from pandas import DataFrame
import pandas as pd
import datetime

def fetch_all_stories(handler, base_params: Dict, limit=200) -> tuple[DataFrame, set[Any], list[Any]]:
    """
    分页获取全部数据并处理状态映射
    :param handler: TAPD处理器实例
    :param base_params: 基础查询参数
    :param limit: 每页数量
    :return: (excel文件路径, 负责人集合, owner为空的需求列表)
    """
    all_data = []
    page = 1

    # ===== 分页获取数据 =====
    while True:
        params = {**base_params, "page": page, "limit": limit}
        response = handler.get_stories(params)

        if response.get("status") != 1 or not response.get("data"):
            break

        all_data.extend(response["data"])

        if len(response['data']) < limit:
            print(f"共获取 {len(all_data)} 条数据")
            break

        page += 1

    # ===== 数据清洗 =====
    stories = [item["Story"] for item in all_data]



    workspace_id = params["workspace_id"]
    status_mapping = handler.get_status_options(workspace_id)


    # ===== 需要统计的状态 =====
    in_process_states = {
        '新', '已排期', '开发中', '规划中',
        '待排期', '初评',
        '待规划'
    }

    # ===== 处理每个需求的字段，并过滤 =====
    filtered_stories = []
    owners_set = set()
    empty_owner_list = []  # 新增：用于记录owner为空的需求

    for story in stories:
        # 处理负责人和时间字段
        story["owner"] = "\n".join(story["owner"].strip(';').split(';'))
        story["created"] = story["created"][:10]
        story["modified"] = story["modified"][:10]

        # ===== 核心逻辑：状态字段映射 =====
        original_status = str(story.get("status", ""))  # 强制转换为字符串

        if original_status == "planning":
            mapped_status = status_mapping.get("planning", original_status)
        else:
            # 尝试解析为数字状态码
            try:
                status_num = int(original_status)
                key = f"status_{status_num}"
                mapped_status = status_mapping.get(key, original_status)
            except ValueError:
                # 非数字状态码直接查询映射表
                mapped_status = status_mapping.get(original_status, original_status)

        story["status"] = mapped_status

        # ===== 只保留 in_process_states 的需求 =====
        if story["status"] in in_process_states:
            # 检查owner是否为空
            if not story["owner"].strip():
                # 拼接成 id_title_创建人
                empty_owner_list.append(f"{story['id']}_{story['name']}_{story['creator']}")
            else:
                # 收集负责人（去重，分割后加入集合）
                for owner in story["owner"].split('\n'):
                    if owner.strip():
                        owners_set.add(owner.strip())
            # 收集导出数据
            filtered_stories.append({
                "ID": story["id"],
                "需求名称": story["name"],
                "状态": story["status"],
                "负责人": story["owner"],
                "创建人": story["creator"],
                "创建时间": story["created"],
                "修改时间": story["modified"]
            })

    # ===== 保存为Excel =====
    df = pd.DataFrame(filtered_stories)

    timestamp = datetime.datetime.now().strftime("%m%d")

    output_dir = "story"
    os.makedirs(output_dir, exist_ok=True)

    excel_filename = f"TAPD_bug转需求_共{len(filtered_stories)}条_{timestamp}.xlsx"
    excel_filepath = os.path.join(output_dir, excel_filename)
    # df.to_excel(excel_filepath, index=False, engine="openpyxl")
    # print(f"\n数据已保存至：{excel_filepath}")

    # return excel_filepath, owners_set, empty_owner_list  # 返回Excel路径、负责人集合、owner为空的需求列表
    return df, owners_set, empty_owner_list  # 返回Excel路径、负责人集合、owner为空的需求列表