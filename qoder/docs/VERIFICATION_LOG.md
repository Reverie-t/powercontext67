# 实际验证记录

验证日期：2026-10-28。所有研究内容为合成样例，不是用户真实数据或提效统计。环境为 Windows、Python 3.11.9、PowerContext 1.4.1；直接依赖版本固定在 requirements.txt 中。

## 自动验收

在 `qoder/` 目录激活独立虚拟环境后运行：

```bash
python -m pytest tests/test_acceptance.py -v
python tests/test_acceptance.py
python scripts/verify_process_restart.py --output docs/evidence
```

真实 Qoder 会话运行的 15 项 pytest 测试全部通过，直接运行测试脚本附带的服务重启验证也通过。完整 HTTP 进程验证使用全新临时数据目录，终止应用进程后，再用新进程读取同一 SQLite 数据；9 项具体检查见 [process-restart.json](evidence/process-restart.json)。

该验证检查无关键词偏好和任务的真实类型召回、量化排序、历史与未来日期隔离、偏好与完成任务的新版本、项目隔离、错误日期、完整进程重启后的恢复及过期版本更新拒绝。实际生成的周报见 [week-two.md](evidence/week-two.md)。

## 真实浏览器流程

使用本机 Chrome，以 1440×1000 和 390×844 两个视口执行实际操作：创建两个项目、跨标签保存记录、编辑偏好、标记任务完成、生成和编辑周报、下载 Markdown。验证了界面项目与写入项目一致、用户 HTML 按文本显示、保存和下载内容一致、手机无横向溢出，且未发生页面脚本错误。

检查结果：[browser-acceptance.json](evidence/browser-acceptance.json)。截图：[桌面周报](evidence/report-desktop-full.png)、[记忆证据](evidence/memory-desktop.png)、[手机周报](evidence/report-mobile-full.png)。下载的实际文件：[browser-export.md](evidence/browser-export.md)。

## 技术作用与边界

应用用 PowerContext 实际保存和读取偏好、计划和完成状态，并使用真实制品 ID、revision 和 If-Match 更新内容。完成任务以 `kind=completed-task` 的新版本保存；记忆生命周期仍为 active，表示该完成记录本身仍有效。偏好更新后保留同一制品身份，新版本用于下一次周报。

当前为无需模型密钥的规则整理模式，支持量化结果优先排序；其他自由文本偏好供人工检查。完整应用在本地运行，公开 Qoder Sites 网站提供介绍、合成流程演示与实际运行截图；网页中的合成步骤演示没有连接 PowerContext。
