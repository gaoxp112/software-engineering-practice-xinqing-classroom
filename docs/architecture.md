# 系统设计

## 1. 架构

浏览器和 REST 请求由 Flask Blueprint 控制器接收。Service 处理账号、课堂、名单、情绪提交和统计规则，并控制写入事务。Repository 使用参数化 SQL 访问 SQLite。页面经 Jinja2 渲染，JavaScript 更新摄像头预览、统计图和教学建议。

```text
HTML / REST -> Blueprint Controller -> services.py -> repository.py -> SQLite
                     |
                     +-> Jinja2 / JSON
```

## 2. 数据模型

- `users`：账号、角色、状态和密码哈希。
- `courses`：课程名称和授课教师，同一教师的同名课程共用一条记录。
- `class_sessions`：通过 `course_id` 外键关联课程，保存课堂代码、开放状态和时间。
- `session_participants`：课堂与用户的多对多参与关系。
- `checkins`：用户在课堂中的情绪、说明、匿名标记和时间。允许同一用户在同一课堂重复提交，以保留情绪变化。

## 3. 权限边界

学生和教师只能查看自己的历史；教师只能查看自己创建的课堂；管理员可访问全局数据。匿名提交仍保存提交者关系以支持本人历史，但教师视图和教师导出显示“匿名同学”。

## 4. 关键路由

`/login`、`/register`、`/settings`、`/dashboard`、`/join`、`/checkin/<id>`、`/history`、`/teacher/sessions`、`/teacher/sessions/<id>`、`/admin/`、`/admin/users`、`/admin/records` 及对应 CSV 导出路由。

