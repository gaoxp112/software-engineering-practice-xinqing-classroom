# -*- coding: utf-8 -*-
from pathlib import Path
import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = DOCS / "表情符号课堂情绪检查器系统结题报告.docx"
IMG = DOCS / "guidance-visual-qa" / "current"

ACCENT = "0F766E"
TEXT = "1F2937"
MUTED = "5B6470"
LIGHT = "EEF2F2"
BORDER = "D7DEE2"


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color=BORDER, size="6"):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_cell_text(cell, text, bold=False, color=TEXT, size=9.2):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.05
    r = p.add_run(str(text).strip())
    r.bold = bold
    r.font.name = "Microsoft YaHei"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    r.font.size = Pt(size)
    r.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def add_page_field(paragraph):
    run = paragraph.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._r.addnext(fld)


def configure(doc):
    sec = doc.sections[0]
    sec.top_margin = Cm(1.9)
    sec.bottom_margin = Cm(1.8)
    sec.left_margin = Cm(2.0)
    sec.right_margin = Cm(2.0)
    sec.header_distance = Cm(0.8)
    sec.footer_distance = Cm(0.8)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(TEXT)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.18

    title_style = styles["Title"]
    title_style.font.name = "Microsoft YaHei"
    title_style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    title_style.font.size = Pt(26)
    title_style.font.bold = True
    title_style.font.color.rgb = RGBColor.from_string(TEXT)
    title_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_style.paragraph_format.space_after = Pt(8)

    for name, size, color, before, after in [
        ("Heading 1", 15, TEXT, 13, 6),
        ("Heading 2", 12.5, ACCENT, 10, 4),
        ("Heading 3", 11, TEXT, 8, 3),
    ]:
        st = styles[name]
        st.font.name = "Microsoft YaHei"
        st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = RGBColor.from_string(color)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True

    for name, size, color in [("Report Caption", 9, MUTED), ("Report Meta", 10.5, MUTED)]:
        if name not in styles:
            styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st = styles[name]
        st.font.name = "Microsoft YaHei"
        st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        st.font.size = Pt(size)
        st.font.color.rgb = RGBColor.from_string(color)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.line_spacing = 1.1

    header = sec.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header_run = header.add_run("心晴课堂 · 软件工程实践结题报告")
    header_run.font.name = "Microsoft YaHei"
    header_run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    header_run.font.size = Pt(8.5)
    header_run.font.color.rgb = RGBColor.from_string(MUTED)
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = footer.add_run("2026 年 11 月 3 日  ·  第 ")
    fr.font.size = Pt(8.5)
    fr.font.color.rgb = RGBColor.from_string(MUTED)
    add_page_field(footer)
    fr2 = footer.add_run(" 页")
    fr2.font.size = Pt(8.5)
    fr2.font.color.rgb = RGBColor.from_string(MUTED)


def add_title_page(doc):
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph(style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("表情符号课堂情绪检查器系统")
    r.bold = True
    r.font.name = "Microsoft YaHei"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    r.font.size = Pt(26)
    r.font.color.rgb = RGBColor.from_string(TEXT)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p2.add_run("结题报告")
    r.bold = True
    r.font.name = "Microsoft YaHei"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    r.font.size = Pt(19)
    r.font.color.rgb = RGBColor.from_string(ACCENT)
    doc.add_paragraph()
    for label, value in [("课程", "软件工程实践"), ("系统名称", "心晴课堂"), ("报告日期", "2026 年 11 月 3 日")]:
        p = doc.add_paragraph(style="Report Meta")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(f"{label}：{value}")
    doc.add_paragraph()
    box = doc.add_table(rows=1, cols=1)
    box.alignment = WD_TABLE_ALIGNMENT.CENTER
    box.autofit = False
    box.columns[0].width = Cm(13.8)
    cell = box.cell(0, 0)
    set_cell_shading(cell, "F3F7F6")
    set_cell_border(cell, color="B9D7D2", size="8")
    set_cell_text(cell, "结题结论  ·  学生、教师、管理员功能及视频 AI 抽帧分析和匿名入库流程均已完成本地验收；24 项自动化测试全部通过。现场演示仍需可用的视觉 API 配置、网络和录制视频。", size=10.5)
    doc.add_page_break()


def add_picture(doc, path, caption, width):
    if not path.exists():
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width))
    cap = doc.add_paragraph(style="Report Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.keep_together = True
    cap.add_run(caption)


def add_markdown_table(doc, rows):
    if not rows:
        return
    ncols = len(rows[0])
    table = doc.add_table(rows=1, cols=ncols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for i, val in enumerate(rows[0]):
        set_cell_shading(hdr.cells[i], ACCENT)
        set_cell_text(hdr.cells[i], val, bold=True, color="FFFFFF", size=9)
        set_cell_border(hdr.cells[i], color="FFFFFF", size="4")
    for row in rows[1:]:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            if i < len(cells):
                set_cell_text(cells[i], val, size=8.8)
                set_cell_border(cells[i])
                if len(table.rows) % 2 == 0:
                    set_cell_shading(cells[i], "F8FAFA")
    doc.add_paragraph().paragraph_format.space_after = Pt(1)


def parse_md_table(lines, start):
    rows = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        vals = [x.strip() for x in lines[i].strip().strip("|").split("|")]
        if not all(re.fullmatch(r"[-: ]+", v or " ") for v in vals):
            rows.append(vals)
        i += 1
    return rows, i


def add_intro_summary(doc, draft):
    # The first abstract is a concise, report-style executive summary.
    h = doc.add_paragraph("摘要", style="Heading 1")
    summary = ("本实验面向课堂反馈不及时、学生感受难以持续记录的问题，设计并实现“心晴课堂”表情符号课堂情绪检查器。系统采用 Flask、SQLite、Jinja2 与原生 CSS/JavaScript，提供学生、教师、管理员三类角色的浏览器端功能。学生可以加入课堂、选择六类情绪、补充说明、匿名提交并查询个人历史；教师可以创建与结束课堂、查看课堂反馈和统计；管理员可以维护用户与课堂名单、按条件查看数据并导出 CSV。系统同时提供 REST API、独立 AI 服务认证、AI 结果置信度过滤与匿名入库能力。\n\n截至 2026 年 11 月 3 日，演示数据库包含 17 个用户、13 个课堂、223 条情绪记录和 155 条课堂参与关系。24 项自动化测试全部通过。新增的视频工作器使用 FFmpeg 抽帧，经外部视觉 API 进行人脸判断和情绪分类，再将达到阈值的结果写入指定课堂；模拟视觉服务集成测试和真实 API 隔离数据库验证均完成。项目提供三段 10 秒 AI 生成的虚构成年人物案例视频及一键演示脚本。演示需要可用的 API 配置与网络；抽取帧会发送给第三方服务，系统不保存原始视频或帧图像。")
    for para in summary.split("\n\n"):
        doc.add_paragraph(para)
    p = doc.add_paragraph(style="Report Meta")
    p.add_run("关键词：课堂反馈；情绪检查；修改版 MVC；角色权限；REST API；响应式界面")


def main():
    draft_path = DOCS / "final-report-draft.md"
    draft = draft_path.read_text(encoding="utf-8")
    lines = draft.splitlines()
    doc = Document()
    configure(doc)
    add_title_page(doc)
    add_intro_summary(doc, draft)

    inserted_flow = False
    i = next((idx for idx, row in enumerate(lines) if row.startswith("## 1 项目背景与目标")), 0)
    paragraph_buf = []

    def flush():
        nonlocal paragraph_buf
        if paragraph_buf:
            text = " ".join(x.strip() for x in paragraph_buf).strip()
            if text:
                doc.add_paragraph(text)
        paragraph_buf = []

    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.startswith("课程：") or line.startswith("系统名称：") or line.startswith("报告日期："):
            flush(); i += 1; continue
        if line.startswith("# "):
            flush(); i += 1; continue
        if line.startswith("## "):
            flush()
            title = line[3:].strip()
            doc.add_paragraph(title, style="Heading 1")
            if title == "5 核心功能与使用画面" and not inserted_flow:
                add_picture(doc, IMG / "login-desktop.png", "图 1 统一登录入口（桌面端）：学生、教师、管理员共用浏览器入口，角色权限由服务端校验。", 6.15)
                inserted_flow = True
            i += 1; continue
        if line.startswith("### "):
            flush()
            title = line[4:].strip()
            doc.add_paragraph(title, style="Heading 2")
            i += 1; continue
        if line.startswith("【建议插图"):
            flush()
            if "学生课堂页面" in line:
                add_picture(doc, IMG / "student-dashboard-desktop.png", "图 2 学生课堂列表（桌面端）：多课堂卡片同时展示课程、教师、课堂代码、个人提交次数和“记录感受”入口。", 6.15)
            elif "情绪提交页面" in line:
                add_picture(doc, ROOT / "docs" / "guidance-visual-qa" / "desktop-03-checkin.png", "图 3 情绪提交页面（桌面端）：六类情绪、补充说明、匿名选项与提交动作；图中英文备注为视觉测试输入，不是固定产品文案。", 6.15)
            elif "教师课堂管理" in line:
                add_picture(doc, IMG / "teacher-sessions-latest.png", "图 4 教师课堂管理（桌面端）：多个课堂按卡片列出，并可进入对应看板；该图证明多课堂管理，不单独证明创建表单字段。", 6.15)
            elif "管理员统计概览" in line:
                add_picture(doc, IMG / "admin-overview-desktop.png", "图 5 管理员统计概览（桌面端）：图中 156 条反馈对应 2026-10-20 至 2026-10-27 日期筛选，不是数据库全部 223 条记录。", 6.15)
            elif "课堂安排" in line:
                add_picture(doc, IMG / "admin-sessions-desktop.png", "图 6 管理员课堂安排（桌面端）：班级、教室、教师、状态、参与人数与名单管理入口集中呈现。", 6.15)
            elif "移动端画面" in line:
                add_picture(doc, IMG / "student-dashboard-mobile.png", "图 7 学生课堂列表（360 px 移动端）：导航折叠、卡片单列排列，主要操作仍保持清楚的触控区域。", 2.65)
            elif "AI 视频记录" in line:
                add_picture(doc, IMG / "admin-records-ai-desktop.png", "图 8 管理端 AI 视频分析结果：记录页显示情绪来源和模型自报置信度；该画面来自隔离测试数据库。", 6.15)
            i += 1; continue
        if line.startswith("|"):
            flush()
            rows, i = parse_md_table(lines, i)
            add_markdown_table(doc, rows)
            continue
        if re.match(r"^\d+\. ", line) or line.startswith("- "):
            flush()
            p = doc.add_paragraph(style="List Number" if re.match(r"^\d+\. ", line) else "List Bullet")
            p.add_run(re.sub(r"^\d+\. |^- ", "", line))
            i += 1; continue
        paragraph_buf.append(line)
        i += 1
    flush()

    # Keep the report's material index easy to scan at the end.
    doc.add_paragraph("交付说明", style="Heading 1")
    doc.add_paragraph("本报告与源代码、数据库初始化脚本、测试报告、视觉验收截图、运行说明和 AI 案例视频共同构成本地实验交付。最终还需录制屏幕演示视频，并按课程平台要求提交项目材料。")
    doc.core_properties.title = "表情符号课堂情绪检查器系统结题报告"
    doc.core_properties.subject = "软件工程实践"
    doc.core_properties.author = "软件工程实践课程项目"
    doc.core_properties.keywords = "课堂反馈, 情绪检查, 软件工程实践"
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
