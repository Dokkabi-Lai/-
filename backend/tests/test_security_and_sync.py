import datetime as dt
import hashlib
import unittest

import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import joinedload, selectinload, sessionmaker

from app.api.auth import _SALT, hash_password, verify_password
from app.api.deps import create_access_token
from app.api.home import _deadline_notifications
from app.api.applications import _serialize_app, application_dashboard
from app.api.todos import create_todo, query_todos, update_todo
from app.config import get_settings
from app.models import Application, ApplicationStage, Base, Group, GroupMember, Job, User, _ensure_default_group
from app.services.excel_import_service import _upsert_jobs, import_job_items
from app.services.group_service import active_membership, ensure_user_default_group, ensure_user_personal_group


class AuthenticationTests(unittest.TestCase):
    def test_bcrypt_password_and_wrong_password(self):
        encoded = hash_password("StrongPass123")
        self.assertTrue(encoded.startswith("$2"))
        self.assertEqual(verify_password("StrongPass123", encoded), (True, False))
        self.assertEqual(verify_password("wrong-password", encoded), (False, False))

    def test_legacy_password_requests_upgrade(self):
        legacy = hashlib.sha256((_SALT + "OldPass123").encode()).hexdigest()
        self.assertEqual(verify_password("OldPass123", legacy), (True, True))

    def test_access_token_is_signed_and_rejects_tampering(self):
        token = create_access_token(42)
        settings = get_settings()
        payload = jwt.decode(token, settings.app.jwt_secret, algorithms=["HS256"])
        self.assertEqual(payload["sub"], "42")
        with self.assertRaises(jwt.PyJWTError):
            jwt.decode(token[:-2] + "xx", settings.app.jwt_secret, algorithms=["HS256"])


class JobUpsertTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_second_snapshot_updates_and_deactivates_missing_jobs(self):
        first = [
            {"source": "excel", "source_id": "a", "company": "A", "title": "分析", "location": "上海"},
            {"source": "excel", "source_id": "b", "company": "B", "title": "产品", "location": "杭州"},
        ]
        result = _upsert_jobs(self.db, first, deactivate_missing=True)
        self.assertEqual(result["created"], 2)

        second = [{**first[0], "title": "高级分析"}]
        result = _upsert_jobs(self.db, second, deactivate_missing=True)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["deactivated"], 1)
        rows = self.db.query(Job).order_by(Job.source_id).all()
        self.assertTrue(rows[0].is_active)
        self.assertFalse(rows[1].is_active)

    def test_same_source_job_is_isolated_between_groups(self):
        user = User(username="group-owner", email="owner@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        group_a = Group(name="A", owner_id=user.id)
        group_b = Group(name="B", owner_id=user.id)
        self.db.add_all([group_a, group_b])
        self.db.flush()
        item = {"source_id": "same", "company": "同一公司", "title": "同一岗位"}
        import_job_items([item], db=self.db, source_label="manual", group_id=group_a.id, created_by_id=user.id)
        import_job_items([item], db=self.db, source_label="manual", group_id=group_b.id, created_by_id=user.id)
        self.assertEqual(self.db.query(Job).filter(Job.group_id == group_a.id).count(), 1)
        self.assertEqual(self.db.query(Job).filter(Job.group_id == group_b.id).count(), 1)
        source_ids = {row.source_id for row in self.db.query(Job).all()}
        self.assertEqual(len(source_ids), 2)


class DeadlineNotificationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_exam_deadline_is_prioritized_and_job_deadline_is_included(self):
        today = dt.date.today()
        user = User(username="deadline-user", email="deadline@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        group = Group(name="提醒测试组", owner_id=user.id)
        self.db.add(group)
        self.db.flush()
        self.db.add(Job(
            group_id=group.id,
            source="manual",
            source_id="deadline-job",
            company="测试公司",
            title="产品岗位",
            close_date=dt.datetime.combine(today + dt.timedelta(days=3), dt.time.min),
        ))
        app = Application(
            user_id=user.id,
            company="笔试公司",
            title="数据岗",
            status="已投递",
            current_stage="笔试",
        )
        self.db.add(app)
        self.db.flush()
        self.db.add(ApplicationStage(
            application_id=app.id,
            stage="笔试",
            status="current",
            schedule_type="deadline",
            deadline_at=dt.datetime.combine(today + dt.timedelta(days=1), dt.time(23, 59)),
        ))
        self.db.commit()

        items = _deadline_notifications(self.db, user, group, today)

        self.assertEqual(items[0]["kind"], "exam_deadline")
        self.assertEqual(items[0]["days_left"], 1)
        self.assertIn("job_deadline", {item["kind"] for item in items})


class TodoTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_todos_are_personal_and_completion_is_persisted(self):
        first_user = User(username="todo-first", email="todo-first@example.com", password_hash="x")
        second_user = User(username="todo-second", email="todo-second@example.com", password_hash="x")
        self.db.add_all([first_user, second_user])
        self.db.flush()

        created = create_todo({
            "title": "完成在线测评",
            "category": "评测",
            "due_at": "2030-09-01T18:00",
        }, self.db, first_user)
        create_todo({
            "title": "准备一面自我介绍",
            "category": "面试准备",
            "due_at": "2030-08-31T10:00",
        }, self.db, first_user)
        create_todo({"title": "另一个账号的任务"}, self.db, second_user)

        completed = update_todo(created["id"], {"is_done": True}, self.db, first_user)

        self.assertTrue(completed["is_done"])
        self.assertIsNotNone(completed["completed_at"])
        first_user_todos = query_todos(self.db, first_user.id)
        self.assertEqual(len(first_user_todos), 2)
        self.assertEqual(first_user_todos[0].title, "准备一面自我介绍")
        self.assertTrue(first_user_todos[1].is_done)
        self.assertEqual(
            [todo.title for todo in query_todos(self.db, second_user.id)],
            ["另一个账号的任务"],
        )
        self.assertEqual(len(query_todos(self.db, first_user.id, include_done=False)), 1)


class GroupMembershipTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_new_user_joins_default_group(self):
        user = User(username="new-user", email="new@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        group = ensure_user_default_group(self.db, user)
        self.db.commit()
        membership = active_membership(self.db, user.id, group.id)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, "owner")
        self.assertEqual(user.active_group_id, group.id)

    def test_existing_shared_group_is_not_filled_with_new_users(self):
        owner = User(username="old-owner", email="old-owner@example.com", password_hash="x")
        new_user = User(username="later-user", email="later@example.com", password_hash="x")
        self.db.add_all([owner, new_user])
        self.db.flush()
        shared = Group(
            name="原有秋招群",
            description="原有群组说明",
            owner_id=owner.id,
            is_system=True,
        )
        self.db.add(shared)
        self.db.flush()
        self.db.add(GroupMember(group_id=shared.id, user_id=owner.id, role="owner"))
        self.db.commit()

        _ensure_default_group(self.db.get_bind())

        members = self.db.query(GroupMember).filter(GroupMember.group_id == shared.id).all()
        self.assertEqual([member.user_id for member in members], [owner.id])
        self.assertEqual(shared.name, "原有秋招群")
        self.assertEqual(shared.description, "原有群组说明")
        self.assertIsNone(new_user.active_group_id)

        personal = ensure_user_personal_group(self.db, new_user)
        self.db.commit()
        self.assertFalse(personal.is_system)
        self.assertEqual(personal.name, "我的岗位库")
        self.assertEqual(new_user.active_group_id, personal.id)
        self.assertIsNotNone(active_membership(self.db, new_user.id, personal.id))


class ApplicationAnalyticsTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def _add_stages(self, app, statuses):
        self.db.add_all([
            ApplicationStage(application_id=app.id, stage=stage, status=status)
            for stage, status in zip(
                ("投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer"),
                statuses,
            )
        ])

    def test_dashboard_uses_actual_stage_records(self):
        user = User(username="analytics-user", email="analytics@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()

        screening = Application(
            user_id=user.id,
            company="筛选公司",
            title="分析岗",
            status="进行中",
            current_stage="投递",  # 故意保留旧缓存值
        )
        written = Application(
            user_id=user.id,
            company="笔试公司",
            title="产品岗",
            status="进行中",
            current_stage="简历筛选",
        )
        rejected = Application(
            user_id=user.id,
            company="淘汰公司",
            title="运营岗",
            status="已淘汰",
            current_stage="投递",
            rejected_stage="简历筛选",
        )
        offer = Application(
            user_id=user.id,
            company="Offer公司",
            title="开发岗",
            status="已完成",
            current_stage="HR面",
        )
        self.db.add_all([screening, written, rejected, offer])
        self.db.flush()
        self._add_stages(screening, ["completed", "current", "pending", "pending", "pending", "pending", "pending"])
        self._add_stages(written, ["completed", "completed", "current", "pending", "pending", "pending", "pending"])
        self._add_stages(rejected, ["completed", "skipped", "pending", "pending", "pending", "pending", "pending"])
        self._add_stages(offer, ["completed", "completed", "completed", "completed", "completed", "completed", "completed"])
        self.db.commit()

        stats = application_dashboard(self.db, user)

        self.assertEqual(stats["by_status"], {"进行中": 2, "已淘汰": 1, "已完成": 1})
        self.assertEqual(stats["by_stage"]["简历筛选"], 1)
        self.assertEqual(stats["by_stage"]["笔试"], 1)
        self.assertEqual(stats["funnel"], {"投递": 4, "简历筛选": 4, "笔试": 2, "面试": 1, "Offer": 1})

    def test_application_serializes_job_library_url(self):
        user = User(username="link-user", email="link@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        job = Job(
            source="manual",
            source_id="link-job",
            company="链接公司",
            title="数据岗",
            url="https://jobs.example.com/link-job",
        )
        self.db.add(job)
        self.db.flush()
        app = Application(
            user_id=user.id,
            job_id=job.id,
            company=job.company,
            title=job.title,
        )
        self.db.add(app)
        self.db.flush()
        stages = [ApplicationStage(application_id=app.id, stage="投递", status="completed")]
        self.db.add_all(stages)
        self.db.commit()
        row = self.db.query(Application).options(
            joinedload(Application.job),
            selectinload(Application.stages),
        ).filter(Application.id == app.id).one()

        payload = _serialize_app(row)

        self.assertEqual(payload["job_url"], "https://jobs.example.com/link-job")


if __name__ == "__main__":
    unittest.main()
