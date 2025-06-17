from typing import Optional, List, Any
import pandas as pd
from tabulate import tabulate
import os
import math

from services.util import utils
from services.util.utils import excel_to_colored_screenshot2


class DefectAnalyzer:
    def __init__(self):
        self.unresolved_status = ["新", "排查中", "接受/处理", "重新打开"]

    def generate_assignee_report(self, data, filename) -> str | tuple[str, Any]:
        try:
            df = pd.DataFrame([{
                "缺陷ID": b['id'],
                "缺陷标题": b['title'],
                "当前状态": b['status'],
                "模块": b['module'],
                "严重程度": b['severity'],
                "发现版本": b['version_report'],
                "负责人": b['current_owner'],
                "创建人": b['reporter'],
                "创建时间": b['created'],
                "是否自动化": "是" if any(kw in b['title'] for kw in ["自动化", "接口测试", "自动提单"]) else "否"
            } for b in data])

            df['负责人'] = (
                df['负责人']
                .astype(str)
                .str.strip()
                .apply(lambda x: x if x == '' else (x if x.endswith(';') else x + ';'))
            )

            # 过滤未解决缺陷
            mask = df['当前状态'].isin(self.unresolved_status)
            unresolved_df = df[mask]

            if unresolved_df.empty:
                return "✅ 当前无未解决缺陷", " "

            # 统计处理人分布
            assignee_stats = (
                unresolved_df['负责人']
                .value_counts()
                .reset_index(name='缺陷数')
                .rename(columns={'index': '处理人'})
            )

            # 统计总数
            total = len(unresolved_df)

            # 记录负责人为空的缺陷
            nan_assignee_df = unresolved_df[unresolved_df['负责人'].isna()]
            # 只保留缺陷id、缺陷title、创建人
            # 假设你的表格这三列分别叫 '缺陷id', '缺陷title', '创建人'
            # 如果实际列名不同，请自行修改
            nan_assignee_info = nan_assignee_df[['缺陷ID', '缺陷标题', '创建人']]

            # 生成分析文件路径
            base_name = os.path.splitext(filename)[0]
            report_path = f"{base_name}_分析结果.xlsx"

            # 保存到Excel（传递总数和负责人为空的缺陷信息）
            self._save_analysis_report(assignee_stats, report_path, total=total, nan_assignee_info=nan_assignee_info)

            # 统计处理人分布并转换为字典
            assignee_counts = unresolved_df['负责人'].value_counts()
            result_dict = assignee_counts.to_dict()

            return os.path.splitext(report_path)[0] + ".png", result_dict

        except FileNotFoundError:
            return "⚠️ 文件未找到，请确认路径", " "
        except KeyError as e:
            return f"❌ 缺少必要列：{str(e)}", " "
        except Exception as e:
            return f"❌ 发生意外错误：{str(e)}", " "

    def _save_analysis_report(self, data: pd.DataFrame, save_path: str, max_cols: int = 4, total: int = None,
                              nan_assignee_info: pd.DataFrame = None):
        import math
        import pandas as pd
        import openpyxl
        from openpyxl.styles import Alignment, Border, Side
        import os

        # 你的截图函数，确保已定义或导入
        # from your_module import excel_to_colored_screenshot
        # 或直接在本文件定义

        def get_balanced_shape(n, max_cols=4):
            cols = min(max_cols, max(1, round(math.sqrt(n) / 1.5)))
            rows = math.ceil(n / cols)
            return rows, cols

        def reshape_for_excel(df, max_cols=4):
            n = len(df)
            rows, cols = get_balanced_shape(n, max_cols)
            fill = pd.DataFrame([['', '']] * (rows * cols - n), columns=df.columns)
            df2 = pd.concat([df, fill], ignore_index=True)
            blocks = []
            for c in range(cols):
                blocks.append(df2.iloc[c * rows:(c + 1) * rows].reset_index(drop=True))
            result = pd.concat(blocks, axis=1)
            new_columns = []
            for i in range(cols):
                new_columns += ['处理人', '缺陷数']
            result.columns = new_columns
            return result

        # 确保“缺陷数”是数字
        data['缺陷数'] = pd.to_numeric(data['缺陷数'], errors='coerce').fillna(0).astype(int)

        reshaped = reshape_for_excel(data, max_cols)
        reshaped.to_excel(save_path, sheet_name='处理人分布', index=False)

        # 用openpyxl追加内容
        import openpyxl
        wb = openpyxl.load_workbook(save_path)
        ws = wb['处理人分布']

        # 插入总计行（在最上面插入一行）
        ws.insert_rows(1)
        ws['A1'] = f'未处理bug总计：{total if total is not None else data["缺陷数"].sum()}'

        # 合并第一行所有单元格并居中
        max_col = ws.max_column
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')

        # 设置列宽（处理人20，缺陷数10）
        for i in range(1, max_col + 1):
            col_letter = openpyxl.utils.get_column_letter(i)
            if (i % 2) == 1:
                ws.column_dimensions[col_letter].width = 20  # 处理人
            else:
                ws.column_dimensions[col_letter].width = 10  # 缺陷数

        # 加边框+内容居中
        thin = Side(border_style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=max_col):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(horizontal='center', vertical='center')

        # 负责人为空的缺陷，拼接成字符串
        nan_rows = []
        if nan_assignee_info is not None and not nan_assignee_info.empty:
            for idx, row in nan_assignee_info.iterrows():
                s = f"ID：{row['缺陷ID']}_创建人：{row['创建人']}"
                nan_rows.append(s)

        # 找到最后一行
        last_row = ws.max_row
        # 跳过一行
        append_start_row = last_row + 2

        if nan_rows:
            # 标题行合并
            ws.merge_cells(start_row=append_start_row - 1, start_column=1, end_row=append_start_row - 1,
                           end_column=max_col)
            cell = ws.cell(row=append_start_row - 1, column=1, value="负责人为空的缺陷：")
            cell.alignment = Alignment(horizontal='left', vertical='center')
            cell.border = border

            # 每一条内容合并
            for i, s in enumerate(nan_rows):
                row_idx = append_start_row + i
                ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=max_col)
                cell = ws.cell(row=row_idx, column=1, value=s)
                cell.alignment = Alignment(horizontal='left', vertical='center')
                cell.border = border

        wb.save(save_path)

        # === 新增：生成带颜色的PNG截图 ===
        try:
            output_png = os.path.splitext(save_path)[0] + ".png"
            excel_to_colored_screenshot2(
                excel_path=save_path,
                output_png=output_png,
                sheet_name="处理人分布"
            )
        except Exception as e:
            print(f"生成PNG截图失败：{e}")

    def _format_split_table(self, data: List) -> str:
        """生成双栏式控制台表格（保持原有逻辑）"""
        mid = len(data) // 2 + len(data) % 2
        table_data = []
        for i in range(mid):
            row = []
            # 左栏
            if i < len(data[:mid]):
                row.extend(data[i])
            else:
                row.extend(['', ''])
            # 右栏
            if i < len(data[mid:]):
                row.extend(data[mid:][i])
            table_data.append(row)

        # 添加总计行
        total = sum(x[1] for x in data)
        table_data.append(['总计', total, '总计', total])

        return tabulate(
            table_data,
            headers=['处理人', '缺陷数', '处理人', '缺陷数'],
            tablefmt='grid',
            stralign='center'
        )

# 使用示例
if __name__ == "__main__":
    analyzer = DefectAnalyzer()
    result = analyzer.generate_assignee_report('/Users/lovecyx/PycharmProjects/bugtrack_notify/output_reports/TAPD缺陷报告_liteAV 12.6（2.0）_共135条_20250527_163940.xlsx')
    print(result)