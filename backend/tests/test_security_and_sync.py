import hashlib
import unittest

import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.auth import _SALT, hash_password, verify_password
from app.api.deps import create_access_token
from app.config import get_settings
from app.models import Base, Group, GroupMember, Job, User
from app.services.excel_import_service import _upsert_jobs, import_job_items
from app.services.group_service import active_membership, ensure_user_default_group


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


class FeishuUpsertTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_second_snapshot_updates_and_deactivates_missing_jobs(self):
        first = [
            {"source": "feishu", "source_id": "a", "company": "A", "title": "分析", "location": "上海"},
            {"source": "feishu", "source_id": "b", "company": "B", "title": "产品", "location": "杭州"},
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


if __name__ == "__main__":
    unittest.main()

