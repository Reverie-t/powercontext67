"""功能测试：按状态筛选。修改前因为函数还没实现而失败。"""

import unittest

from sample_app.tasks import filter_tasks


class FilterTasksTest(unittest.TestCase):
    def test_filter_exact_status(self) -> None:
        tasks = [
            {"name": "a", "priority": 2, "status": "open"},
            {"name": "b", "priority": 1, "status": "done"},
        ]
        result = filter_tasks(tasks, "open")
        self.assertEqual([item["name"] for item in result], ["a"])

    def test_blank_status_returns_all_in_order(self) -> None:
        tasks = [
            {"name": "a", "priority": 2, "status": "open"},
            {"name": "b", "priority": 1, "status": "done"},
        ]
        self.assertEqual(filter_tasks(tasks, None), tasks)
        self.assertEqual(filter_tasks(tasks, ""), tasks)

    def test_unknown_status_returns_empty(self) -> None:
        tasks = [{"name": "a", "priority": 1, "status": "open"}]
        self.assertEqual(filter_tasks(tasks, "archived"), [])

    def test_filter_does_not_mutate_input(self) -> None:
        tasks = [
            {"name": "a", "priority": 1, "status": "open"},
            {"name": "b", "priority": 1, "status": "done"},
        ]
        filter_tasks(tasks, "done")
        self.assertEqual([item["status"] for item in tasks], ["open", "done"])


if __name__ == "__main__":
    unittest.main()
