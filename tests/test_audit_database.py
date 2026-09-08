# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests\test_audit_database.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.engine import make_url

from database import db_session
from database.mongodb_store_base import MongoDBStoreBase


@pytest.mark.parametrize("db_type,settings", [
    ("db", db_session.mysql_db_config),
    ("postgres", db_session.postgres_db_config),
])
def test_database_credentials_are_not_parsed_as_url_delimiters(monkeypatch, db_type, settings):
    monkeypatch.setitem(settings, "user", "crawler@team")
    monkeypatch.setitem(settings, "password", "p@ss/word:#?%")
    monkeypatch.setattr(db_session, "_engines", {})
    factory = Mock()
    monkeypatch.setattr(db_session, "create_async_engine", factory)
    db_session.get_async_engine(db_type)
    url = make_url(factory.call_args.args[0])
    assert url.username == settings["user"]
    assert url.password == settings["password"]
    assert url.host == settings["host"]
    assert url.database == settings["db_name"]


@pytest.mark.asyncio
async def test_mongodb_failed_write_reaches_the_caller(monkeypatch):
    store = MongoDBStoreBase("xhs")
    collection = Mock(update_one=AsyncMock(side_effect=OSError("database unavailable")))
    monkeypatch.setattr(store, "get_collection", AsyncMock(return_value=collection))
    with pytest.raises(OSError, match="database unavailable"):
        await store.save_or_update("contents", {"note_id": "1"}, {"title": "test"})


@pytest.mark.asyncio
async def test_mongodb_successful_upsert_retains_its_contract(monkeypatch):
    store = MongoDBStoreBase("xhs")
    collection = Mock(update_one=AsyncMock())
    monkeypatch.setattr(store, "get_collection", AsyncMock(return_value=collection))
    assert await store.save_or_update("contents", {"note_id": "1"}, {"title": "test"}) is True
    collection.update_one.assert_awaited_once_with({"note_id": "1"}, {"$set": {"title": "test"}}, upsert=True)


@pytest.mark.asyncio
async def test_mongodb_platform_store_does_not_log_false_success(monkeypatch):
    from store.xhs._store_impl import XhsMongoStoreImplement
    from tools import utils
    store = XhsMongoStoreImplement()
    monkeypatch.setattr(store.mongo_store, "get_collection", AsyncMock(side_effect=OSError("offline")))
    log = Mock()
    monkeypatch.setattr(utils.logger, "info", log)
    with pytest.raises(OSError, match="offline"):
        await store.store_content({"note_id": "1", "title": "example"})
    assert not any("Saved note" in str(call) for call in log.call_args_list)


@pytest.mark.asyncio
async def test_sqlite_url_and_write_work_with_reserved_path_characters(tmp_path, monkeypatch):
    from sqlalchemy import text
    monkeypatch.setitem(db_session.sqlite_db_config, "db_path", str(tmp_path / "data #1.db"))
    monkeypatch.setattr(db_session, "_engines", {})
    engine = db_session.get_async_engine("sqlite")
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE notes (id INTEGER PRIMARY KEY)"))
            await connection.execute(text("INSERT INTO notes VALUES (1)"))
            result = await connection.execute(text("SELECT id FROM notes"))
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()
