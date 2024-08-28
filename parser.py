# -*- coding: utf-8 -*-
# 作者：陳凱
# 電子郵件：chenkai0210@hotmail.com
# 日期：2023-09
# 描述：這個腳本的目的是解析PDF。將PDF結構化成，文字，圖片，表格和參考。

import pandas as pd  # 用於結構化表格
import fitz   # PyMuPDF PDF相關操作
import PyPDF2  # PDF相關操作
from typing import List


class Text:
    """文本類，用於封裝提取的文本內容 """

    def __init__(self,
                 title: str = None,
                 section: dict = {},
                 summary: str = None):
        """
        參數:
        - title: str，文本標題
        - section: dict, key:章節名稱 value:章節文字內容
        - summary: str,  摘要
        """
        self.title = title
        self.section = section
        self.summary = summary


class PDFImage:
    """圖片類，用於封裝提取的圖片信息 """

    def __init__(self,
                 title: str,
                 image_data: object,
                 page_num: int):
        """
        參數:
        - title: str，圖片標題
        - image_data: 圖片數據的表示形式，可以是字節流、文件路徑等
        - page_num: int: 圖片所在頁數
        """
        self.title = title
        self.image_data = image_data
        self.page_num = page_num


class Table:
    """表格類，用於封裝提取的表格信息 """

    def __init__(self,
                 title: str,
                 table_data: pd.DataFrame,
                 page_num: int):
        """
        參數:
        - title: str，表格標題
        - table_data: 表格數據，可以是 Pandas DataFrame 等形式
        - page_num: int: 表格所在頁數
        """
        self.title = title
        self.table_data = table_data
        self.page_num = page_num


class Reference:
    """參考文獻類，用於封裝提取的參考文獻信息 """

    def __init__(self, ref: str):
        """
        參數:
        - ref: str，參考文獻
        """
        self.ref = ref


class PDFOutliner:
    """
    該類用於獲取給定PDF的所有章節的標題
    該類對下面的代碼做了一些修改，核心算法來自下面倉庫
    https://github.com/beaverden/pdftoc/tree/main
    """

    def __init__(self):
        self.titles = []  # 每一個章節的標題

    def get_tree_pages(self, root, info, depth=0, titles=[]):
        """
            Recursively iterate the outline tree
            Find the pages pointed by the outline item
            and get the assigned physical order id
            Decrement with padding if necessary
        """
        if isinstance(root, dict):
            page = root['/Page'].get_object()
            t = root['/Title']
            title = t
            if isinstance(t, PyPDF2.generic.ByteStringObject):
                title = t.original_bytes.decode('utf8')
            title = title.strip()
            title = title.replace('\n', '')
            title = title.replace('\r', '')
            page_num = info['all_pages'].get(id(page), 0)
            if page_num == 0:
                # TODO: logging
                print('Not found page number for /Page!', page)
            elif page_num < info['padding']:
                page_num = 0
            else:
                page_num -= info['padding']
            str_val = '%-5d' % page_num
            str_val += '\t' * depth
            str_val += title + '\t' + '%3d' % page_num
            self.titles.append(title)
            return
        for elem in root:
            self.get_tree_pages(elem, info, depth+1)

    def recursive_numbering(self, obj, info):
        """
            Recursively iterate through all the pages in order and 
            assign them a physical order number
        """
        if obj['/Type'] == '/Page':
            obj_id = id(obj)
            if obj_id not in info['all_pages']:
                info['all_pages'][obj_id] = info['current_page_id']
            info['current_page_id'] += 1
            return
        elif obj['/Type'] == '/Pages':
            for page in obj['/Kids']:
                self.recursive_numbering(page.get_object(), info)

    def create_text_outline(self, pdf_path, page_number_padding):
        # print('Running the script for [%s] with padding [%d]' % (pdf_path, page_number_padding))
        # creating an object
        titles = []
        with open(pdf_path, 'rb') as file:
            fileReader = PyPDF2.PdfReader(file)

            info = {
                'all_pages': {},
                'current_page_id': 1,
                'padding': page_number_padding
            }

            pages = fileReader.trailer['/Root']['/Pages'].get_object()
            self.recursive_numbering(pages, info)
            # for page_num, page in enumerate(pages['/Kids']):
            #    page_obj = page.getObject()
            #    all_pages[id(page_obj)] = page_num + 1
            self.get_tree_pages(fileReader.outline, info, 0, titles)
        return


class PDFParser:
    """PDF 解析器類，用於提取 PDF 中的文本、圖片、表格和參考文獻信息 """

    def __init__(self, pdf_path: str):
        """
        參數:
        - pdf_path: str，PDF 文件的路徑
        """
        self.pdf_path = pdf_path
        self.doc = fitz.open(self.pdf_path)  # PyMuPDF fitz.Document
        self.text = Text()   # text: Text, 文字內容
        self.images = []     # list, 所有圖片（PDFImage）
        self.tables = []     # list, 所有表格（Table）
        self.references = []  # list, 所有參考（Reference）

    def extract_title(self):
        """
        獲取pdf標題
        """
        doc = self.doc
        first_page = doc.load_page(0)  # 獲取第一頁
        # 提取第一頁的文本內容
        text = first_page.get_text()
        # 按行拆分文本內容
        lines = text.split('\n')
        # 獲取第一行文本
        first_line = lines[0].strip()
        self.text.title = first_line
        return

    def extract_sections_content(self,
                                 doc: fitz.Document,
                                 section_titles: List[str]):
        """
        根據章節名稱列表提取PDF中各章節的文字內容。
        參數：
        - pdf_file: 包含章節的PDF文件路徑。
        - section_titles: 包含所有章節名稱的列表。

        返回值：
        - 一個字典，鍵是章節名稱，值是該章節的文字內容。
        """
        sections_content = {}  # 存儲章節名稱和內容的字典
        # 獲取所有章節名稱
        filtered_section_titles = [PDFParser.remove_leading_digits(
            title).strip() for title in section_titles]
        # 對於每一個章節名稱，遍歷所有文字行，如果文字行內包含了該章節的名稱則加下去將文字行加入到該章節文字內容中
        # 如果文字行包含了下一個章節的名稱則停止將文字行加入到該章節文字內容中
        for i, section_title in enumerate(filtered_section_titles):
            section_found = False
            section_content = ""
            scan_page = True
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                for line in page_text.split('\n'):
                    # 如果找到了下一章的標題則跳出
                    if i+1 < len(filtered_section_titles) and filtered_section_titles[i+1].lower() in line.lower():
                        scan_page = False
                        break
                    if section_title.lower() in line.lower():
                        section_found = True
                    elif section_found:
                        # 如果找到了目標標題，開始獲取章節內容
                        section_content += line + "\n"
                if not scan_page:
                    break

            if section_found:
                sections_content[section_titles[i]] = section_content

        return sections_content

    @staticmethod
    def remove_leading_digits(text: str):
        """
        刪除輸入文字開頭的數字。
        """
        while text and text[0].isdigit():
            text = text[1:]  # 刪除第一個字符
        return text

    def extract_text(self):
        """
        提取PDF中的文本內容
        """
        # 1 獲取標題
        self.extract_title()
        # 2 獲取章節名稱
        outliner = PDFOutliner()
        outliner.create_text_outline(self.pdf_path, 0)
        # 3 獲取對應章節下的文字內容
        self.text.section = self.extract_sections_content(
            self.doc, outliner.titles)
        return

    def extract_images(self, fig_caption_start: str = 'Figure'):
        """
        提取 PDF 中的圖片信息: 圖片和圖片的標題
        fig_caption_start: str，圖片標題開始詞
        """
        doc = self.doc

        for page_num in range(len(doc)):
            page = doc[page_num]
            # 提取頁面文本塊
            blocks = page.get_text('blocks')
            # 通過計算文本塊與圖片的距離來匹配圖片和對應的標題，
            # 文本塊有特定的開始詞開始且距離（歐氏距離）離圖片最近的文本塊的文字為當前圖片的標題
            for img in page.get_images(full=True):
                xref = img[0]
                base_image = doc.extract_image(xref)
                x0, y0, x1, y2 = page.get_image_rects(xref)[0]
                related_text = "untitled"
                min_dist = float('inf')
                for block in blocks:
                    block_x0, block_y0, block_x1, block_y1, block_text = block[:5]
                    if block_text.strip().startswith(fig_caption_start):
                        # 計算歐式距離
                        dist = (x0 - block_x0)**2 + (y0 - block_y0)**2
                        if dist < min_dist:
                            min_dist = dist
                            related_text = block_text.strip()

                image_data = base_image["image"]
                image = PDFImage(related_text, image_data, page_num)
                self.images.append(image)

    def extract_tables(self, tab_caption_start: str = 'Table'):
        """
        提取 PDF 中的表格信息
        tab_caption_start: str, 表格標題開始詞
        """
        doc = self.doc
        for num in range(len(doc)):
            page = doc[num]
            # 提取頁面文本塊
            blocks = page.get_text('blocks')
            # 提取表格
            tables = page.find_tables()
            # 通過計算文本塊與表格的距離來匹配圖片和對應的標題，
            # 文本塊有特定的開始詞且距離（歐氏距離）離表格最近的文本塊的文字為當前圖片的標題
            for table in tables:
                x0, y0, x1, y2 = table.bbox
                df = table.to_pandas()
                related_text = "untitled"
                min_dist = float('inf')
                for block in blocks:
                    block_x0, block_y0, block_x1, block_y1, block_text = block[:5]
                    if block_text.strip().startswith(tab_caption_start):
                        # 計算歐式距離
                        dist = (x0 - block_x0)**2 + (y0 - block_y0)**2
                        if dist < min_dist:
                            min_dist = dist
                            related_text = block_text.strip()
                self.tables.append(Table(title=related_text,
                                         table_data=df,
                                         page_num=num))

    def extract_references(self):
        """
        提取 PDF 中的參考文獻信息
        """
        doc = self.doc
        page_num = len(doc)
        ref_list = []
        for num, page in enumerate(doc):
            content = page.get_text('blocks')
            for pc in content:
                txt_blocks = list(pc[4:-2])
                txt = ''.join(txt_blocks)
                if 'References' in txt or 'REFERENCES' in txt or 'referenCes' in txt:
                    ref_num = [i for i in range(num, page_num)]
                    for rpn in ref_num:
                        ref_page = doc[rpn]
                        ref_content = ref_page.get_text('blocks')
                        for refc in ref_content:
                            txt_blocks = list(refc[4:-2])
                            ref_list.extend(txt_blocks)
        index = 0
        for i, ref in enumerate(ref_list):
            if 'References' in ref or 'REFERENCES' in ref or 'referenCes' in ref:
                index = i
                break
        if index + 1 < len(ref_list):
            index += 1
        self.references = [Reference(ref.replace('\n', ''))
                           for ref in ref_list[index:] if len(ref) > 10]
