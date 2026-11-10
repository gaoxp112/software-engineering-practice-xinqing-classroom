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

表中三个演示账号只用于本地实验，正式使用前请在“账号设置”中修改密码。数据库中的其余样例账户及反馈均为生成数据，不应当作为真实教学数据使用。

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
- AI 视频工作器可从短视频抽帧，在本机识别人脸表情，按置信度过滤并写入选定课堂
- 所有写操作使用 POST 和 CSRF 校验；密码使用 Werkzeug 哈希保存；数据库查询使用参数化 SQL

## AI 视频一键演示

安装 `requirements.txt` 中的依赖并准备 FFmpeg（在 PATH 中，或放到 `.venv\Scripts\ffmpeg.exe`），然后双击 `run_video_demo.bat`。在文件对话框里选择 `docs/demo-videos/` 中的任意 MP4。脚本默认选择最近开始的开放课堂，在本机 CPU 上完成推理，并将通过阈值的匿名结果写入该课堂。若要手动选课堂，在项目目录运行 `.\run_video_demo.bat --choose-session`。

脚本在随机本地端口启动演示服务。分析结束后，用管理员账号登录自动打开的「情绪数据」页，查看 `AI` 来源和置信度。确认后回到命令窗口按 Enter 关闭临时服务，记录保存在项目数据库里。

默认每约 3.3 秒抽一帧，最多 60 帧，每帧取画面中最大的人脸，分类分数达到 0.65 才入库。模型权重随项目放在 `models/`，本地模式无需联网或配置密钥。脚本把模型的七类表情映射到学生打卡的六类，命令窗口同时显示原始表情和映射后的类别。映射用于课堂记录归类，置信度来自原始表情预测。完整映射见 [AI 集成说明](docs/ai-integration.md)。

如需使用原来的外部视觉服务，运行 `.\run_video_demo.bat --env ..\judge.env.example`。该模式会向配置的服务发送抽取帧。API 密钥保存在项目目录外，不随提交包分发。

## 本机摄像头实时识别

1. 双击 `start.bat`，在本机浏览器用教师账号登录，进入自己正在开放的课堂。
2. 在「实时情绪识别」里点击「开始识别」，面向电脑摄像头。页面实时预览画面，并在人脸框旁显示类别和置信度。预览旁显示最近一次课堂采样和已入库次数。
3. 点击「停止识别」或「结束课堂」，系统会释放摄像头。

OpenCV 从本机摄像头持续读取画面，每 3 秒选一帧在内存中推理。结果经过六类映射和 0.65 分数过滤后，作为匿名 AI 采样写入当前课堂。

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

`docs/requirements.md` 对照课件整理需求；`docs/architecture.md`、`docs/architecture-api.md` 说明 MVC、分层 API 与数据模型；`docs/api.md` 和 `/api/openapi.json` 给出接口契约；`docs/ai-integration.md` 说明 AI 边界与隐私约束；`docs/test-plan.md` 给出测试矩阵和定量指标；`docs/strict-validation.md` 提供逐页 PPT 验收结论；`docs/test-report.md` 记录本机测试结果；`docs/demo-video-script.md` 是最终屏幕演示拍摄流程。

运行功能测试和性能基准：

```powershell
python -m unittest discover -s tests -v
python tests\benchmark.py
```

最新视觉验收截图保存在 `docs/strict-audit/` 和 `docs/guidance-visual-qa/`，覆盖 1366×768 桌面端与 360×800 移动端的核心页面及指导书补充页面。
