from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from shipyard.planning import PlanStore, ProjectPlan


class ProjectPlanTest(unittest.TestCase):
    def test_project_plan_from_model_payload_normalizes_tickets(self) -> None:
        plan = ProjectPlan.from_model_payload(
            "request-1",
            {
                "project_name": "Sketch CRM",
                "summary": "A small CRM from a sketch.",
                "tech_stack": ["Flask", "SQLite"],
                "assumptions": ["Brand-new repo"],
                "tickets": [
                    {
                        "title": "Bootstrap app",
                        "description": "Create the initial app.",
                        "file_path": "app.py",
                    }
                ],
            },
        )

        self.assertEqual(plan.request_id, "request-1")
        self.assertEqual(plan.project_name, "Sketch CRM")
        self.assertEqual(plan.tickets[0].id, "T001")
        self.assertEqual(plan.tickets[0].file_paths, ["app.py"])

    def test_project_plan_from_model_payload_adds_fallback_ticket(self) -> None:
        plan = ProjectPlan.from_model_payload("request-1", {"project_name": "Empty"})

        self.assertEqual(len(plan.tickets), 1)
        self.assertEqual(plan.tickets[0].id, "T001")


class PlanStoreTest(unittest.TestCase):
    def test_approve_plan_writes_tickets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            inbox_dir = Path(tmp_dir)
            chat_id = 123
            request_id = "request-1"
            request_dir = inbox_dir / str(chat_id) / request_id
            request_dir.mkdir(parents=True)

            plan = ProjectPlan.from_model_payload(
                request_id,
                {
                    "project_name": "Ship It",
                    "tickets": [
                        {
                            "id": "T001",
                            "title": "Bootstrap",
                            "description": "Create files.",
                            "file_paths": ["README.md"],
                        }
                    ],
                },
            )
            store = PlanStore(inbox_dir)

            store.save_plan(chat_id, plan)
            approved = store.approve_plan(chat_id, request_id)

            self.assertIsNotNone(approved.approved_at)
            self.assertTrue((request_dir / "plan.json").exists())
            self.assertTrue((request_dir / "tickets.json").exists())


if __name__ == "__main__":
    unittest.main()
