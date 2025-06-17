import xlsx2html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import time
from PIL import Image
import io


def excel_to_colored_screenshot(excel_path, output_png, sheet_name="Sheet1") -> str:
    """保留单元格颜色的截图方案"""
    temp_html = os.path.splitext(output_png)[0] + "_temp.html"

    try:
        # 生成原始HTML（保留颜色）
        xlsx2html.xlsx2html(excel_path, temp_html, sheet=sheet_name)

        # 添加基础样式（不覆盖颜色）
        # 添加基础样式（不覆盖颜色）
        with open(temp_html, "r+", encoding="utf-8") as f:
            content = f.read()
            enhanced_html = content.replace('<head>', '''<head>
                <meta charset="UTF-8">
                <style>
                    body {
                        margin: 0;
                        padding: 5px;
                        background: white !important;
                    }
                    table {
                        border-collapse: collapse;
                        font-family: Calibri, 'Microsoft YaHei', Arial, sans-serif;
                        font-size: 14px;
                        table-layout: auto;
                    }
                    td, th {
                        padding: 2px 6px;
                        min-width: 60px;
                        border: 1px solid #d4d4d4;
                        white-space: nowrap;
                        vertical-align: middle;
                        height: 20px !important;
                        font-size: 14px !important;  /* 关键：强制字号一致 */
                        text-align: left;
                    }
                    tr {
                        height: 20px !important;
                        min-height: 20px !important;
                        max-height: 20px !important;
                    }
                </style>''')
            f.seek(0)
            f.write(enhanced_html)
            f.truncate()

        # 配置浏览器
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--force-device-scale-factor=1.2")
        chrome_options.add_argument("--hide-scrollbars")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(f"file://{os.path.abspath(temp_html)}")

        # 等待渲染
        time.sleep(0.2)

        # 动态计算完整尺寸
        js = """
        var body = document.body,
            html = document.documentElement;
        return {
            width: Math.max(body.scrollWidth, html.scrollWidth),
            height: Math.max(body.scrollHeight, html.scrollHeight)
        };"""
        content_size = driver.execute_script(js)

        driver.set_window_size(
            int(content_size['width'] + 10),
            int(content_size['height'] * 1.6 + 10)
        )

        # 获取截图并优化
        full_screenshot = driver.get_screenshot_as_png()
        driver.quit()

        img = Image.open(io.BytesIO(full_screenshot))
        img = img.crop((5, 5, img.width - 5, img.height - 5))
        img.save(output_png, quality=100)

        print(f"✅ 带颜色截图已保存到：{os.path.abspath(output_png)}")

        return output_png

    except Exception as e:
        print(f"❌ 错误：{str(e)}")
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)

def excel_to_colored_screenshot2(excel_path, output_png, sheet_name="Sheet1") -> str:
    """保留单元格颜色的截图方案"""
    temp_html = os.path.splitext(output_png)[0] + "_temp.html"

    try:
        # 生成原始HTML（保留颜色）
        xlsx2html.xlsx2html(excel_path, temp_html, sheet=sheet_name)

        # 添加基础样式（不覆盖颜色）
        # 添加基础样式（不覆盖颜色）
        with open(temp_html, "r+", encoding="utf-8") as f:
            content = f.read()
            enhanced_html = content.replace('<head>', '''<head>
                <meta charset="UTF-8">
                <style>
                    body {
                        margin: 0;
                        padding: 5px;
                        background: white !important;
                    }
                    table {
                        border-collapse: collapse;
                        font-family: Calibri, 'Microsoft YaHei', Arial, sans-serif;
                        font-size: 14px;
                        table-layout: auto;
                    }
                    td, th {
                        padding: 2px 6px;
                        min-width: 60px;
                        border: 1px solid #d4d4d4;
                        white-space: nowrap;
                        vertical-align: middle;
                        height: 20px !important;
                        font-size: 14px !important;  /* 关键：强制字号一致 */
                        text-align: left;
                    }
                    tr {
                        height: 20px !important;
                        min-height: 20px !important;
                        max-height: 20px !important;
                    }
                </style>''')
            f.seek(0)
            f.write(enhanced_html)
            f.truncate()

        # 配置浏览器
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--force-device-scale-factor=1.2")
        chrome_options.add_argument("--hide-scrollbars")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(f"file://{os.path.abspath(temp_html)}")

        # 等待渲染
        time.sleep(0.2)

        # 动态计算完整尺寸
        js = """
        var body = document.body,
            html = document.documentElement;
        return {
            width: Math.max(body.scrollWidth, html.scrollWidth),
            height: Math.max(body.scrollHeight, html.scrollHeight)
        };"""
        content_size = driver.execute_script(js)

        driver.set_window_size(
            int(content_size['width'] * 1.3 + 10),
            int(content_size['height'] * 1.8 + 10)
        )

        # 获取截图并优化
        full_screenshot = driver.get_screenshot_as_png()
        driver.quit()

        img = Image.open(io.BytesIO(full_screenshot))
        img = img.crop((5, 5, img.width - 5, img.height - 5))
        img.save(output_png, quality=100)

        print(f"✅ 带颜色截图已保存到：{os.path.abspath(output_png)}")

        return output_png

    except Exception as e:
        print(f"❌ 错误：{str(e)}")
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)


if __name__ == '__main__':
    excel_to_colored_screenshot(
        excel_path="../../liteAV 12.6（2.0）_2025-05-16 11:32:59_bug统计报表.xlsx",
        output_png="colored_screenshot.png"
    )