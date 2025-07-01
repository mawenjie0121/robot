import pandas as pd
import re
import datetime
import os
import platform
from tabulate import tabulate
from tapdsdk.sdk import TapdAPIClient
from services.bugs.bugs_defect_analyzer import DefectAnalyzer
from services.bugs.tapd_bugs_fetcher import TapdBugsFetcher
import yaml
import matplotlib.pyplot as plt

# ========== 自动检测系统并设置中文字体 ==========
def set_chinese_font():
    system = platform.system()
    if system == 'Windows':
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    elif system == 'Darwin':
        plt.rcParams['font.sans-serif'] = ['Heiti SC', 'PingFang SC']
    else:
        plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False

set_chinese_font()
# ==============================================

class TapdBugReporter:
    def __init__(self,
                 client_id: str,
                 client_secret: str):
        """初始化缺陷报告生成器"""

        self.client_id = client_id
        self.client_secret = client_secret
        self.output_dir = "output_reports"
        os.makedirs(self.output_dir, exist_ok=True)

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
        self.defined_status = list(self.status_mapping.values()) + ["其他状态"]
        self.unresolved_status = ["新", "排查中", "接受/处理", "重新打开"]
        self.auto_keywords = ["自动化", "接口测试", "自动提单"]
        self.status_order = [
            "新", "排查中", "接受/处理", "重新打开",
            "已解决", "验证关闭", "排查关闭", "延期解决"
        ]

    def generate_report(
            self,
            version_report: str,
            workspace_id: int,
            save_excel: bool = True,
            include_prompt_advice: bool = False  # 新增参数
    ) -> tuple:
        global filename
        bugs_fetcher = TapdBugsFetcher(client_id=self.client_id, client_secret=self.client_secret)
        bugs = bugs_fetcher.fetch_bugs(
            version_report,
            workspace_id,
            include_prompt_advice=include_prompt_advice  # 传递参数
        )
        total = len(bugs)

        if total == 0:
            return "⚠️ 未发现符合要求的缺陷数据 / 版本号有误", " ", " "

        unresolved = sum(1 for b in bugs if b['status'] in self.unresolved_status)
        auto_bugs = sum(1 for b in bugs if any(kw in b['title'] for kw in self.auto_keywords))
        non_auto = total - auto_bugs

        # 先初始化所有状态为0
        status_counts = {status: 0 for status in self.status_order}
        status_counts["其他状态"] = 0
        unknown_status = []

        for bug in bugs:
            status = bug['status']
            if status in status_counts:
                status_counts[status] += 1
            else:
                unknown_status.append(status)
                status_counts["其他状态"] += 1

        # 按顺序生成状态表
        status_table = []
        for status in self.status_order:
            count = status_counts[status]
            status_table.append([status, count])
        if status_counts["其他状态"] > 0:
            status_table.append(["其他状态", status_counts["其他状态"]])


        # 输出缺陷状态统计图
        # status_table_dict = {item[0]: item[1] for item in status_table}

        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        # pic_name = f"TAPD缺陷报告_{version_report}_{timestamp}_"
        # pic_file = self.plot_status(
        #     status_table_dict,
        #     filename=pic_name,
        #     title=f"{version_report}缺陷统计",
        #     color='#ff4b5c'
        # )

        if unresolved > 0:
            unresolved_str = f'<font color="red">未解决缺陷：{unresolved} 个</font>（状态包含：{", ".join(self.unresolved_status)}）'
        else:
            unresolved_str = f'未解决缺陷：{unresolved} 个（状态包含：{", ".join(self.unresolved_status)}）'

        report = f"""# {version_report} 版本缺陷分析报告

📈 总体情况

- 总缺陷数：{total} 个
- {unresolved_str}
- 自动化缺陷：{auto_bugs} 个（标题含标识：{', '.join(self.auto_keywords)}）
- 常规缺陷：{non_auto} 个


"""
        report += "📋 状态分布\n"
        for status, count in status_table:
            report += f"·{status}：{count}  \n"

        if unknown_status:
            unique_unknown = list(set(unknown_status))
            report += f"\n⚠️ 发现未定义状态：{', '.join(unique_unknown)}\n"

        self._validate_data(bugs, total, unresolved, auto_bugs, status_counts)

        if save_excel:
            filename = self._save_to_excel(version_report, bugs, status_counts, total)

        analyzer = DefectAnalyzer()
        analyzer_res, unresolved_df_dict = analyzer.generate_assignee_report(bugs, filename)
        if(analyzer_res == "✅ 当前无未解决缺陷"):
            report += "\n\n 当前版本缺陷均完结"
        print(analyzer_res)

        return report, analyzer_res, unresolved_df_dict

    def _save_to_excel(self,
                       version: str,
                       data: list,
                       status_counts: dict,
                       total: int) -> str:
        safe_version = re.sub(r'[\\/*?:"<>|]', "_", version)
        # timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"TAPD缺陷报告_{safe_version}版本_各处理人负责缺陷数.xlsx"
        filepath = os.path.join(self.output_dir, filename)

        df_main = pd.DataFrame([{
            "缺陷ID": b['id'],
            "缺陷标题": b['title'],
            "当前状态": b['status'],
            "模块": b['module'],
            "严重程度": b['severity'],
            "发现版本": b['version_report'],
            "负责人": b['current_owner'],
            "创建人": b['reporter'],
            "创建时间": b['created'],
            "是否自动化": "是" if any(kw in b['title'] for kw in self.auto_keywords) else "否"
        } for b in data])

        df_status = pd.DataFrame({
            "状态": list(status_counts.keys()),
            "数量": list(status_counts.values())
        }).query("数量 > 0")

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df_main.to_excel(writer, sheet_name='缺陷明细', index=False)
            df_status.to_excel(
                writer,
                sheet_name='状态分布',
                index=False,
                startrow=2,
                header=False
            )
            ws_status = writer.sheets['状态分布']
            ws_status.cell(1, 1, "状态分布统计")
            ws_status.cell(2, 1, "状态")
            ws_status.cell(2, 2, "数量")
            for col in ['A', 'B']:
                ws_status.column_dimensions[col].width = 20

        return filepath

    def _validate_data(self,
                       data: list,
                       total: int,
                       unresolved: int,
                       auto: int,
                       status_counts: dict):
        assert len(data) == total, f"数据总数不一致（预期：{total}，实际：{len(data)}）"
        actual_auto = sum(1 for b in data if any(kw in b['title'] for kw in self.auto_keywords))
        assert auto == actual_auto, f"自动化计数错误（预期：{auto}，实际：{actual_auto}）"
        status_total = sum(status_counts.values())
        assert status_total == total, f"状态总数不一致（预期：{total}，实际：{status_total}）"
        calc_unresolved = sum(status_counts[status] for status in self.unresolved_status)
        assert unresolved == calc_unresolved, f"未解决数错误（预期：{unresolved}，实际：{calc_unresolved}）"

    def plot_status(self, data: dict,
                    filename: str,
                    title: str = "缺陷状态分布统计",
                    color: str = '#ff4b5c',
                    figsize: tuple = (10, 6)) -> str:
        import matplotlib.pyplot as plt
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax = plt.subplots(figsize=figsize)
        # 用 self.status_order
        labels = self.status_order
        values = [data.get(label, 0) for label in labels]
        bars = ax.bar(labels, values, color=color, edgecolor='white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.4)
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2.,
                    height + 0.5,
                    f'{height}',
                    ha='center',
                    va='bottom',
                    fontsize=9)
        ax.set_ylim(0, max(values) * 1.2 if values and max(values) > 0 else 1)
        ax.set_xlabel('问题状态', fontsize=12, labelpad=10)
        ax.set_ylabel('数量统计', fontsize=12, labelpad=10)
        ax.set_title(title, fontsize=15, pad=20)
        plt.xticks(rotation=45, ha='right')

        if filename:
            save_name = f"{filename}问题状态分布统计图.png"
            save_path = os.path.join(self.output_dir, save_name)
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        plt.tight_layout()
        plt.close()
        return save_path