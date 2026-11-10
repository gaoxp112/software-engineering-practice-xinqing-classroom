# 心晴课堂：情绪检查软件系统

这是依据《软件工程实践》示例项目要求实现的本地 Web 系统。系统采用 Flask + SQLite + Jinja2 + 原生 CSS/JavaScript，体现修改版 MVC 结构，支持学生、教师和管理员三类角色。

## 快速运行

```powershell
# 在 emotion-checker 项目目录运行
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.bat
```

浏览器打开 `http://127.0.0.1:5000`。安装依赖后也可以直接双击 `start.bat`。

首次启动时，系统会生成 `instance/emotion_checker.sqlite3` 和基础演示数据。可使用以下账号登录。

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 学生 | `student` | `Student123!` |
| 教师 | `teacher` | `Teacher123!` |
| 管理员 | `admin` | `Admin123!` |

表中账号用于本地演示。可通过「账号设置」修改密码。

需要展示多名师生和多堂课时，在项目目录按顺序运行以下命令生成样例数据。

```powershell
.\.venv\Scripts\python.exe scripts\seed_sample_data.py
.\.venv\Scripts\python.exe scripts\expand_sample_classrooms.py
```

## 功能范围

- 学生/教师注册、登录、退出、改密、加入课堂、提交六类情绪、补充说明、匿名提交、查看个人情绪变化和历史
- 教师创建或预约自己的课堂，生成课堂代码，查看情绪变化与教学建议，按学生和时间筛选课堂反馈明细，导出本课堂 CSV
- 管理员维护用户账号，按课程、班级和日期筛选情绪图表与明细，导出当前筛选结果
- 管理员提前安排课堂名单，也可为教师代排课堂。学生首页显示自己的预约课堂，到达上课时间后即可提交反馈
- 教师可在课堂看板使用本机摄像头实时识别情绪，查看人脸框与分类结果，并将达标采样匿名计入课堂统计
- 所有写操作使用 POST 和 CSRF 校验；密码使用 Werkzeug 哈希保存；数据库查询使用参数化 SQL

## 本机摄像头实时识别

1. 双击 `start.bat`，在本机浏览器用教师账号登录，进入自己正在开放的课堂。
2. 在「实时情绪识别」里点击「开始识别」，面向电脑摄像头。页面实时预览画面，并在人脸框旁显示类别和置信度。预览旁显示最近一次课堂采样和已入库次数。
3. 点击「停止识别」或「结束课堂」，系统会释放摄像头。

OpenCV 在本机持续读取摄像头画面并运行随项目提供的模型。预览实时更新，每约 3 秒将一次达到 0.65 置信度阈值的采样匿名写入当前课堂。类别映射见 [AI 集成说明](docs/ai-integration.md)。

## 目录

```text
emotion-checker/
├─ run.py                 # 开发服务器入口
├─ start.bat              # Waitress 本机启动
├─ requirements.txt
├─ emotion_checker/
│  ├─ __init__.py         # 应用工厂、错误处理
│  ├─ db.py               # SQLite schema 与演示数据
│  ├─ security.py         # CSRF、登录和角色保护
│  ├─ auth.py             # 注册、登录、改密
│  ├─ main.py             # 课堂加入、情绪打卡、历史
│  ├─ teacher.py          # 教师课堂管理与导出
│  ├─ admin.py            # 管理员统计、用户和导出
│  ├─ templates/          # Jinja2 页面
│  └─ static/             # 响应式样式和交互
├─ tests/                 # unittest 集成测试
└─ docs/                  # 实验需求、架构、测试和报告
```

## 实验交付

`docs/requirements.md` 对照课件整理需求；`docs/architecture.md`、`docs/architecture-api.md` 说明 MVC、分层 API 与数据模型；`docs/api.md` 和 `/api/openapi.json` 给出接口契约；`docs/ai-integration.md` 说明摄像头识别和六类情绪映射；`docs/test-plan.md` 给出测试矩阵和定量指标；`docs/strict-validation.md` 提供逐页 PPT 验收结论；`docs/test-report.md` 记录本机测试结果；`docs/demo-video-script.md` 是最终屏幕演示拍摄流程。

运行功能测试和性能基准：

```powershell
python -m unittest discover -s tests -v
python tests\benchmark.py
```

最新视觉验收截图保存在 `docs/strict-audit/` 和 `docs/guidance-visual-qa/`，覆盖 1366×768 桌面端与 360×800 移动端的核心页面及指导书补充页面。
