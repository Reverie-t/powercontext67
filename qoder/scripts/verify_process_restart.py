"""以真实 HTTP 请求验证完整应用进程重启；所有数据均为独立合成样例。"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def verify(output: Path | None = None):
    project = Path(__file__).resolve().parents[1]
    checks = []
    with tempfile.TemporaryDirectory(prefix="research-weekly-acceptance-") as directory:
        data = Path(directory)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"

        def call(path, method="GET", payload=None, expected=200):
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            request = Request(base_url + path, data=body, method=method,
                              headers={"Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=30) as response:
                    assert response.status == expected
                    return json.load(response)
            except HTTPError as error:
                if expected == error.code:
                    return json.load(error)
                raise

        def start():
            environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            log = (data / "process.log").open("ab")
            process = subprocess.Popen(
                [sys.executable, str(project / "src/server.py"), "--port", str(port), "--data-dir", str(data / "state")],
                stdout=log, stderr=log, env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log.close()
                    raise RuntimeError("验收服务启动失败，请检查依赖和启动命令")
                try:
                    call("/api/health")
                    return process, log
                except (URLError, TimeoutError):
                    time.sleep(0.1)
            process.terminate()
            process.wait(timeout=15)
            log.close()
            raise TimeoutError("验收服务启动超时")

        def stop(process, log):
            process.terminate()
            process.wait(timeout=15)
            log.close()

        process, log = start()
        try:
            a = call("/api/projects", "POST", {"name": "合成样例：混合检索", "direction": "科研笔记检索", "preferences": "中文；先列量化结果"})["project"]
            b = call("/api/projects", "POST", {"name": "合成样例：图像标注", "direction": "仅属于项目B", "preferences": "仅属于项目B的偏好"})["project"]

            def record(day, kind, text):
                return call("/api/records", "POST", {"project_id": a["id"], "date": day, "record_type": kind, "content": text})["record"]

            record("2026-10-20", "experiment", "合成基线 Recall@10 为0.74，尚未做显著性检验")
            task = record("2026-10-23", "plan", "扩大查询集并按长度分组")
            pending = record("2026-10-24", "plan", "对照检查长查询失败样例")
            record("2026-11-30", "plan", "未来任务不得泄漏到历史周报")
            record("2026-10-27", "experiment", "整理了实验工具链的配置")
            record("2026-10-28", "experiment", "合成查询集扩充至200条，尚未完成长度分组")

            def generate():
                return call("/api/reports/generate", "POST", {"project_id": a["id"], "week_start": "2026-10-26", "week_end": "2026-11-01"})["report"]

            report = generate()
            references = report["memory_refs"]
            assert {m["artifact_id"] for m in references if m["type"] == "todo"} == {task["memory_artifact_id"], pending["memory_artifact_id"]}
            assert "0.74" not in report["markdown"] and "未来任务不得泄漏" not in report["markdown"]
            assert report["markdown"].index("200条") < report["markdown"].index("实验工具链")
            checks.extend(["无关键词任务及偏好按真实类型召回", "本周与未来日期隔离", "PowerContext偏好实际改变量化结果排序"])
            preference = next(m for m in references if m["type"] == "preference")
            changed = call("/api/preferences", "PUT", {"project_id": a["id"], "artifact_id": preference["artifact_id"], "revision": preference["revision"], "new_text": "先列量化结果；标明合成数据与来源"})["result"]
            completed = call("/api/tasks/complete", "POST", {"project_id": a["id"], "artifact_id": task["memory_artifact_id"], "revision": task["memory_revision"]})["result"]
            assert changed["revision"] == 2 and completed["revision"] == 2
            assert completed["kind"] == "completed-task"
            checks.append("偏好更新及任务完成保存为真实PowerContext新版本")
            other = call(f"/api/projects/{b['id']}/memory")["memories"]
            assert other and all("查询" not in m["text"] and "量化" not in m["text"] for m in other)
            checks.append("项目记忆隔离且结果非空")
            call("/api/reports/generate", "POST", {"project_id": a["id"], "week_start": "2026-11-01", "week_end": "2026-10-26"}, expected=400)
            checks.append("错误日期范围被拒绝")
        finally:
            stop(process, log)

        process, log = start()
        try:
            restored = generate()
            references = restored["memory_refs"]
            assert {m["artifact_id"] for m in references if m["type"] == "todo"} == {pending["memory_artifact_id"]}
            assert any(m["type"] == "preference" and m["revision"] == 2 and "合成数据" in m["text"] for m in references)
            assert "扩大查询集并按长度分组" not in restored["markdown"]
            state = call(f"/api/projects/{a['id']}/memory")["memories"]
            assert any(m["artifact_id"] == task["memory_artifact_id"] and m["kind"] == "completed-task" and m["revision"] == 2 for m in state)
            call("/api/preferences", "PUT", {"project_id": a["id"], "artifact_id": preference["artifact_id"], "revision": 1, "new_text": "旧版本不能覆盖当前偏好"}, expected=400)
            checks.extend(["终止完整应用进程后仍读取真实记忆新版本", "已完成任务不再继承且待办仍保留", "过期版本更新被拒绝"])
            result = {"status": "passed", "synthetic_data": True, "python": sys.version.split()[0], "powercontext": importlib.metadata.version("powercontext"), "checks": checks, "memory_refs_after_restart": references, "completed_task": completed}
            if output is not None:
                output.mkdir(parents=True, exist_ok=True)
                (output / "process-restart.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                (output / "week-two.md").write_text(restored["markdown"], encoding="utf-8")
            return result
        finally:
            stop(process, log)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="保存真实验证输出和第二周周报的目录")
    arguments = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(verify(arguments.output), ensure_ascii=False, indent=2))
