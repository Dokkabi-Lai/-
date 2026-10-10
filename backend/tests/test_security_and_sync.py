import datetime as dt
import hashlib
import io
import unittest

import jwt
import openpyxl
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import joinedload, selectinload, sessionmaker

from app.api.auth import _SALT, hash_password, verify_password
from app.api.deps import create_access_token
from app.api.home import _deadline_notifications
from app.api.applications import (
    _serialize_app,
    advance_stage,
    application_dashboard,
    decline_application,
    rollback_stage,
    update_workflow,
)
from app.api.todos import create_todo, query_todos, update_todo
from app.config import get_settings
from app.models import Application, ApplicationStage, Base, Group, GroupMember, Job, Todo, User, _ensure_default_group, _migrate_db
from app.services.excel_import_service import _upsert_jobs, import_job_items
from app.services.application_import_service import (
    import_application_rows,
    parse_application_import_file,
)
from app.services.group_service import active_membership, ensure_user_default_group, ensure_user_personal_group
from app.services.stage_service import is_assessment_stage, is_interview_stage


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


class BulkApplicationImportTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(username="bulk-user", email="bulk@example.com", password_hash="x")
        self.db.add(self.user)
        self.db.flush()
        self.group = Group(name="批量投递测试", owner_id=self.user.id)
        self.db.add(self.group)
        self.db.flush()
        self.job = Job(
            group_id=self.group.id,
            created_by_id=self.user.id,
            source="manual",
            source_id="existing-import-job",
            company="匹配公司",
            title="产品经理",
        )
        self.db.add(self.job)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_import_matches_jobs_creates_missing_jobs_and_skips_duplicates(self):
        rows = [
            {"company": "匹配公司", "title": "产品经理", "applied_at": "2030-09-01"},
            {"company": "匹配 公司", "title": "产品经理", "applied_at": "2030/09/01"},
            {"company": "新增公司", "title": "数据分析", "applied_at": "2030年9月2日"},
        ]

        result = import_application_rows(self.db, self.user, self.group, rows)

        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["matched_jobs"], 1)
        self.assertEqual(result["created_jobs"], 1)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(self.db.query(Job).filter(Job.group_id == self.group.id).count(), 2)
        self.assertEqual(self.db.query(Application).filter(Application.user_id == self.user.id).count(), 2)
        self.assertEqual(self.db.query(ApplicationStage).count(), 14)
        matched_app = self.db.query(Application).filter(Application.company == "匹配公司").one()
        self.assertEqual(matched_app.job_id, self.job.id)

        repeated = import_application_rows(self.db, self.user, self.group, rows)
        self.assertEqual(repeated["imported"], 0)
        self.assertEqual(repeated["duplicates"], 3)

    def test_csv_file_is_parsed_with_chinese_headers(self):
        rows = parse_application_import_file(
            "公司名称,岗位名称,投递时间\n示例公司,运营岗,2030-10-02\n".encode("utf-8"),
            "applications.csv",
        )

        self.assertEqual(rows[0]["company"], "示例公司")
        self.assertEqual(rows[0]["title"], "运营岗")
        self.assertEqual(rows[0]["applied_at"], "2030-10-02")

    def test_xlsx_file_is_parsed_with_excel_date(self):
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(["公司名字", "投递岗位", "投递日期"])
        worksheet.append(["表格公司", "策略岗位", dt.datetime(2030, 10, 3, 9, 30)])
        content = io.BytesIO()
        workbook.save(content)
        workbook.close()

        rows = parse_application_import_file(content.getvalue(), "applications.xlsx")

        self.assertEqual(rows[0]["company"], "表格公司")
        self.assertEqual(rows[0]["title"], "策略岗位")
        self.assertEqual(rows[0]["applied_at"], dt.datetime(2030, 10, 3, 9, 30))


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

    def test_calendar_source_can_only_create_one_linked_todo(self):
        user = User(username="calendar-todo", email="calendar-todo@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        app = Application(
            user_id=user.id,
            company="日程公司",
            title="产品岗",
            status="进行中",
            current_stage="一面",
        )
        self.db.add(app)
        self.db.flush()
        stage = ApplicationStage(
            application_id=app.id,
            stage="一面",
            status="current",
            scheduled_at=dt.datetime(2030, 9, 1, 10, 0),
        )
        self.db.add(stage)
        self.db.commit()

        payload = {
            "title": "准备 日程公司 - 一面",
            "category": "面试准备",
            "due_at": "2030-09-01T10:00",
            "source_type": "calendar_stage",
            "source_id": stage.id,
        }
        first = create_todo(payload, self.db, user)
        second = create_todo(payload, self.db, user)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.db.query(Todo).filter(Todo.user_id == user.id).count(), 1)


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
                ("投递", "简历筛选", "测评", "一面", "二面", "HR面", "Offer"),
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

        self.assertEqual(stats["by_status"], {"进行中": 2, "已淘汰": 1, "已拒绝": 0, "已完成": 1})
        self.assertEqual(stats["by_stage"]["简历筛选"], 1)
        self.assertEqual(stats["by_stage"]["测评"], 1)
        self.assertEqual(stats["funnel"], {"投递": 4, "简历筛选": 4, "测评": 2, "面试": 1, "Offer": 1})

    def test_ai_interview_counts_as_assessment_not_interview(self):
        user = User(username="ai-stage-user", email="ai-stage@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        app = Application(
            user_id=user.id,
            company="AI流程公司",
            title="算法岗",
            status="进行中",
            current_stage="AI面",
        )
        self.db.add(app)
        self.db.flush()
        self.db.add_all([
            ApplicationStage(application_id=app.id, stage="投递", position=0, status="completed"),
            ApplicationStage(application_id=app.id, stage="AI面", position=1, status="current"),
            ApplicationStage(application_id=app.id, stage="一面", position=2, status="pending"),
            ApplicationStage(application_id=app.id, stage="Offer", position=3, status="pending"),
        ])
        self.db.commit()

        stats = application_dashboard(self.db, user)

        self.assertTrue(is_assessment_stage("AI 面"))
        self.assertFalse(is_interview_stage("AI面"))
        self.assertEqual(stats["by_stage"]["测评"], 1)
        self.assertEqual(stats["by_stage"]["面试"], 0)
        self.assertEqual(stats["funnel"]["测评"], 1)
        self.assertEqual(stats["funnel"]["面试"], 0)

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

    def test_custom_workflow_is_ordered_and_advances_per_application(self):
        user = User(username="workflow-user", email="workflow@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        app = Application(
            user_id=user.id,
            company="流程公司",
            title="产品岗",
            status="进行中",
            current_stage="投递",
        )
        self.db.add(app)
        self.db.flush()
        self._add_stages(app, ["completed", "pending", "pending", "pending", "pending", "pending", "pending"])
        self.db.commit()

        ids = {stage.stage: stage.id for stage in app.stages}
        names = ["投递", "评测", "简历筛选", "AI面", "群面", "测评", "一面", "二面", "HR面", "Offer"]
        payload = [{"id": ids[name], "stage": name} for name in names if name in ids]
        payload.insert(1, {"stage": "评测"})
        payload.insert(3, {"stage": "AI面"})
        payload.insert(4, {"stage": "群面"})

        updated = update_workflow(app.id, {"stages": payload}, self.db, user)

        self.assertEqual([stage["stage"] for stage in updated["stages"]], names)
        self.assertEqual(updated["current_stage"], "评测")
        self.assertEqual(
            [stage["position"] for stage in updated["stages"]],
            list(range(len(names))),
        )

        advanced = advance_stage(app.id, self.db, user)
        self.assertEqual(advanced["current_stage"], "简历筛选")
        self.assertEqual(advanced["stages"][1]["status"], "completed")

    def test_workflow_cannot_delete_a_stage_with_history(self):
        user = User(username="workflow-history", email="workflow-history@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        app = Application(
            user_id=user.id,
            company="历史公司",
            title="运营岗",
            status="进行中",
            current_stage="简历筛选",
        )
        self.db.add(app)
        self.db.flush()
        self._add_stages(app, ["completed", "current", "pending", "pending", "pending", "pending", "pending"])
        self.db.commit()
        ids = {stage.stage: stage.id for stage in app.stages}
        without_application_stage = [
            {"id": stage_id, "stage": name}
            for name, stage_id in ids.items()
            if name != "投递"
        ]

        with self.assertRaises(HTTPException) as context:
            update_workflow(app.id, {"stages": without_application_stage}, self.db, user)
        self.assertEqual(context.exception.status_code, 400)

    def test_decline_is_separate_from_company_rejection(self):
        user = User(username="decline-user", email="decline@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        app = Application(
            user_id=user.id,
            company="主动拒绝公司",
            title="产品岗",
            status="进行中",
            current_stage="一面",
        )
        self.db.add(app)
        self.db.flush()
        self.db.add_all([
            ApplicationStage(application_id=app.id, stage="投递", position=0, status="completed"),
            ApplicationStage(application_id=app.id, stage="一面", position=1, status="current"),
            ApplicationStage(application_id=app.id, stage="Offer", position=2, status="pending"),
        ])
        self.db.commit()

        payload = decline_application(app.id, {"stage": "一面"}, self.db, user)
        stats = application_dashboard(self.db, user)

        self.assertEqual(payload["status"], "已拒绝")
        self.assertEqual(payload["rejected_stage"], "一面")
        self.assertEqual(stats["by_status"]["已拒绝"], 1)
        self.assertEqual(stats["by_status"]["进行中"], 0)

    def test_rollback_clears_later_schedule_details_and_linked_todo(self):
        user = User(username="rollback-user", email="rollback@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        app = Application(
            user_id=user.id,
            company="回退公司",
            title="算法岗",
            status="进行中",
            current_stage="二面",
        )
        self.db.add(app)
        self.db.flush()
        screening = ApplicationStage(
            application_id=app.id, stage="简历筛选", position=0, status="completed"
        )
        first = ApplicationStage(
            application_id=app.id, stage="一面", position=1, status="completed"
        )
        second = ApplicationStage(
            application_id=app.id,
            stage="二面",
            position=2,
            status="current",
            scheduled_at=dt.datetime(2030, 10, 10, 10, 0),
            location="会议室 A",
            form="现场",
            notes="准备案例",
            feedback="沟通顺利",
        )
        offer = ApplicationStage(
            application_id=app.id,
            stage="Offer",
            position=3,
            status="pending",
            deadline_at=dt.datetime(2030, 10, 15, 18, 0),
            schedule_type="deadline",
            notes="确认薪资",
        )
        self.db.add_all([screening, first, second, offer])
        self.db.flush()
        self.db.add_all([
            Todo(user_id=user.id, title="准备二面", source_type="calendar_stage", source_id=second.id),
            Todo(user_id=user.id, title="确认 Offer", source_type="calendar_stage", source_id=offer.id),
        ])
        self.db.commit()

        payload = rollback_stage(app.id, {"stage": "一面"}, self.db, user)
        self.db.expire_all()
        cleared_second = self.db.get(ApplicationStage, second.id)
        cleared_offer = self.db.get(ApplicationStage, offer.id)

        self.assertEqual(payload["current_stage"], "一面")
        self.assertIsNone(cleared_second.scheduled_at)
        self.assertIsNone(cleared_second.location)
        self.assertIsNone(cleared_second.form)
        self.assertIsNone(cleared_second.notes)
        self.assertIsNone(cleared_second.feedback)
        self.assertIsNone(cleared_offer.deadline_at)
        self.assertEqual(cleared_offer.schedule_type, "exact")
        self.assertEqual(
            self.db.query(Todo).filter(Todo.user_id == user.id).count(),
            0,
        )

    def test_migration_only_renames_untouched_legacy_default_workflow(self):
        user = User(username="migration-user", email="migration@example.com", password_hash="x")
        self.db.add(user)
        self.db.flush()
        untouched = Application(
            user_id=user.id,
            company="默认流程公司",
            title="产品岗",
            status="已淘汰",
            current_stage="笔试",
            rejected_stage="笔试",
        )
        customized = Application(
            user_id=user.id,
            company="自定义流程公司",
            title="运营岗",
            status="进行中",
            current_stage="笔试",
        )
        self.db.add_all([untouched, customized])
        self.db.flush()
        legacy_names = ["投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer"]
        self.db.add_all([
            ApplicationStage(application_id=untouched.id, stage=name, position=index, status="pending")
            for index, name in enumerate(legacy_names)
        ])
        custom_names = ["投递", "AI面", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer"]
        self.db.add_all([
            ApplicationStage(application_id=customized.id, stage=name, position=index, status="pending")
            for index, name in enumerate(custom_names)
        ])
        self.db.commit()

        _migrate_db(self.db.get_bind())
        self.db.expire_all()

        untouched_names = [
            row.stage for row in self.db.query(ApplicationStage)
            .filter(ApplicationStage.application_id == untouched.id)
            .order_by(ApplicationStage.position).all()
        ]
        custom_names_after = [
            row.stage for row in self.db.query(ApplicationStage)
            .filter(ApplicationStage.application_id == customized.id)
            .order_by(ApplicationStage.position).all()
        ]
        migrated_untouched = self.db.get(Application, untouched.id)
        migrated_customized = self.db.get(Application, customized.id)
        self.assertEqual(untouched_names[2], "测评")
        self.assertEqual(migrated_untouched.current_stage, "测评")
        self.assertEqual(migrated_untouched.rejected_stage, "测评")
        self.assertIn("笔试", custom_names_after)
        self.assertIn("AI面", custom_names_after)
        self.assertEqual(migrated_customized.current_stage, "笔试")


if __name__ == "__main__":
    unittest.main()
