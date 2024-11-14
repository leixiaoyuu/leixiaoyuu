import re
import os
import pandas as pd
import csv
from typing import List, Dict
import javalang
import openpyxl
from openpyxl.styles import Alignment
import logging

logger = logging.getLogger(__name__)

class JavaMethodExtractor:
    def __init__(self, java_code: str):
        self.java_code = java_code
        self.tree = None

    def parse(self):
        """解析Java代码"""
        try:
            self.tree = javalang.parse.parse(self.java_code)
            return True
        except Exception as e:
            print(f"解析错误: {e}")
            return False

    def extract_methods(self) -> List[Dict]:
        """提取所有方法的信息"""
        if not self.tree:
            if not self.parse():
                return []

        methods = []

        # 遍历语法树查找方法声明
        for path, node in self.tree.filter(javalang.tree.MethodDeclaration):
            # 解析包名
            package_name = self.tree.package.name if self.tree.package else "default"
            print("包路径：", package_name)

            # 查找当前方法所属的类或接口
            type_node = None
            for parent in reversed(path):
                if isinstance(parent, (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration)):
                    type_node = parent
                    break
            if type_node:
                type_name = type_node.name
                type_comment = type_node.documentation if type_node.documentation else ""
                full_declaration_name = f"{package_name}.{type_name}.{node.name}"

                method_info = {
                    'class_comment': type_comment,
                    'full_declaration_name': full_declaration_name,
                    'class_name': type_name,
                    'method_name': node.name,
                    'return_type': node.return_type.name if node.return_type else 'void',
                    'modifiers': list(node.modifiers),
                    'parameters': [
                        {
                            'type': param.type.name,
                            'name': param.name
                        } for param in node.parameters
                    ],
                    'node_comment': node.documentation if node.documentation else "",
                    'body': self._get_method_body(node),
                    'declaration': self._get_method_declaration(node)
                }
                methods.append(method_info)
            else:
                logger.warning("Method not found within a class or interface declaration")

        return methods

    def _get_method_body(self, method_node) -> str:
        """提取方法体的源代码"""
        # 获取方法体在原始代码中的位置
        start_position = method_node.position.line - 1 if method_node.position else 0
        lines = self.java_code.splitlines()

        # 简单的方法体提取逻辑
        body_lines = []
        brace_count = 0
        started = False
        in_multiline_comment = False

        for line in lines[start_position:]:
            if '{' in line and not started:
                started = True

            if started:
                # 检查是否进入或退出多行注释
                if '/*' in line:
                    in_multiline_comment = True
                    line = line[:line.index('/*')]  # 去掉多行注释开始部分

                if '*/' in line:
                    in_multiline_comment = False
                    line = line[line.index('*/') + 2:]  # 去掉多行注释结束部分

                if not in_multiline_comment:
                    # 检查行是否为单行注释且包含中文字符
                    if line.strip().startswith('//'):
                        comment_content = line.strip()[2:].strip()
                        if re.search(r'[\u4e00-\u9fff]', comment_content):
                            body_lines.append(line)
                    elif line.strip():
                        body_lines.append(line)
                        brace_count += line.count('{') - line.count('}')

                # 如果当前行包含多行注释的开始和结束，需要特殊处理
                if '/*' in line and '*/' in line:
                    comment_start = line.index('/*')
                    comment_end = line.index('*/')
                    if comment_start < comment_end:
                        line = line[:comment_start] + line[comment_end + 2:]
                        if line.strip():
                            body_lines.append(line)
                            brace_count += line.count('{') - line.count('}')

                if brace_count == 0:
                    break

        return '\n'.join(body_lines)


    def _get_method_declaration(self, method_node) -> str:
        """提取方法的完整声明"""
        start_line = method_node.position.line - 1 if method_node.position else 0
        start_column = method_node.position.column - 1 if method_node.position else 0
        lines = self.java_code.splitlines()

        # 找到方法声明的结束位置
        end_line = start_line
        end_column = start_column
        declaration_str = str(method_node).strip()
        current_char_index = 0

        while current_char_index < len(declaration_str):
            if end_column >= len(lines[end_line]):
                end_column = 0
                end_line += 1
                if end_line >= len(lines):
                    break
            if end_line >= len(lines):
                break
            if end_column < len(lines[end_line]):
                current_char = lines[end_line][end_column]
                if current_char == declaration_str[current_char_index]:
                    current_char_index += 1
                    end_column += 1
                else:
                    end_column += 1

        declaration_lines = []
        for i in range(start_line, end_line + 1):
            if i == start_line:
                if i < len(lines):
                    declaration_lines.append(lines[i][start_column:])
            elif i == end_line:
                if i < len(lines) and end_column <= len(lines[i]):
                    declaration_lines.append(lines[i][:end_column])
            else:
                if i < len(lines):
                    declaration_lines.append(lines[i])

        return '\n'.join(declaration_lines)


def remove_illegal_characters(s):
    # 使用正则表达式移除非法字符
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)


def write_to_excel(results, output_file):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Java Parse Results"

    sheet['A1'] = "分段内容"
    row = 2
    # 写入数据
    for content in results:
        cleaned_parse_result = remove_illegal_characters(content)
        sheet[f'A{row}'] = cleaned_parse_result
        row = row + 1

    # 设置列宽和自动换行
    for column in sheet.columns:
        column_letter = openpyxl.utils.get_column_letter(column[0].column)
        sheet.column_dimensions[column_letter].width = 30
        for cell in column:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(output_file)


def write_to_csv(results, output_file):
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['分段内容']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for content in results:
            cleaned_parse_result = remove_illegal_characters(content)
            writer.writerow({'分段内容': cleaned_parse_result})


def parse_main(root_dir, exclude_dirs, exclude_files, output_file, output_format):
    results = []
    for root, dirs, files in os.walk(root_dir):
        # 排除指定目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            if file.endswith('.java') and file not in exclude_files:
                file_path = os.path.join(root, file)

                with open(file_path, 'r', encoding='utf-8') as file:
                    # 获取文件内容
                    java_code = file.read()
                    # 创建解析器实例
                    extractor = JavaMethodExtractor(java_code)
                    # 提取方法信息
                    methods = extractor.extract_methods()
                    # 将单个方法体存入 results[]
                    for method in methods:
                        content = f"""- 绝对路径: {method['full_declaration_name']}
   - 类注释: 
   {method['class_comment']}
   - 类名: {method['class_name']}
   - 方法体及注释:
       {method['node_comment']}
   {method['body']}
   """
                        print(content)
                        print("-" * 50)
                        results.append(content)
    # 写入文件
    if output_format == 'excel':
        write_to_excel(results, f"{output_file}.xlsx")
    elif output_format == 'csv':
        write_to_csv(results, f"{output_file}.csv")


def convert_xlsx_to_csv(dir):
    """
    读取指定目录下的所有 XLSX 文件，并将其转换为 CSV 格式，文件名保持不变。

    :param dir: 指定的目录路径
    """
    # 确保目录存在
    if not os.path.exists(dir):
        print(f"目录 {dir} 不存在")
        return

    # 遍历目录中的所有文件
    for filename in os.listdir(dir):
        if filename.endswith('.xlsx'):
            # 构建完整的文件路径
            xlsx_file_path = os.path.join(dir, filename)
            csv_file_path = os.path.join(f'{dir}/csv', filename.replace('.xlsx', '.csv'))

            # 读取 XLSX 文件
            try:
                df = pd.read_excel(xlsx_file_path, engine='openpyxl')
                # 将 DataFrame 写入 CSV 文件
                df.to_csv(csv_file_path, index=False)
                print(f"已将 {xlsx_file_path} 转换为 {csv_file_path}")
            except Exception as e:
                print(f"转换 {xlsx_file_path} 时发生错误: {e}")



if __name__ == "__main__":
    root_dir = r'../datasets/HAIXIA_CODE/lt-parent'
    exclude_dirs = ['target', 'test', '.git', '.idea', 'resource']
    exclude_files = ['package-info.java']
    # folder_list = ['lt-tran', 'lt-base', 'lt-batch', 'lt-aplt']
    folder_list = ['lt-tran']
    for folder in folder_list:
        input_dir = os.path.join(root_dir, folder)
        input_dir = '../datasets/HAIXIA_CODE/lt-parent/lt-base/src/main/java/cn/sunline/ltts/busi/ltbase/ceti/temp'

        output_file = f'../file/HAIXIA/1031/{folder}-java-code'
        parse_main(input_dir, exclude_dirs, exclude_files, output_file, 'csv')

