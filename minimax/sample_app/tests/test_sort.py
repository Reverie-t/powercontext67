"""回归测试：排序行为必须保持。"""

import unittest

from sample_app.tasks import sort_tasks


class SortTasksTest(unittest.TestCase):
    def test_sort_priority_then_name(self) -> None:
        tasks = [
            {"name": "b", "priority": 1, "status": "open"},
            {"name": "a", "priority": 2, "status": "done"},
            {"name": "c", "priority": 1, "status": "open"},
        ]
        result = sort_tasks(tasks)
        self.assertEqual([item["name"] for item in result], ["a", "b", "c"])

    def test_sort_does_not_mutate_input(self) -> None:
        tasks = [
            {"name": "b", "priority": 1, "status": "open"},
            {"name": "a", "priority": 2, "status": "done"},
        ]
        sort_tasks(tasks)
        self.assertEqual([item["name"] for item in tasks], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
