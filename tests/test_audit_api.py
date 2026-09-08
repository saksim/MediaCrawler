# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests\test_audit_api.py
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

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.main import app
from api.routers import data
from api.schemas import CrawlerStartRequest
from api.services.crawler_manager import CrawlerManager


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/crawler/status", "/api/crawler/logs", "/api/data/files", "/api/env/check"])
async def test_remote_api_requests_require_authentication(monkeypatch, path):
    monkeypatch.delenv("MEDIACRAWLER_API_TOKEN", raising=False)
    transport = httpx.ASGITransport(app=app, client=("198.51.100.8", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://crawler.example") as client:
        response = await client.get(path)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_remote_token_and_local_same_origin_access(monkeypatch):
    monkeypatch.setenv("MEDIACRAWLER_API_TOKEN", "test-only-token")
    transport = httpx.ASGITransport(app=app, client=("198.51.100.8", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://crawler.example") as client:
        assert (await client.get("/api/crawler/status")).status_code == 401
        response = await client.get("/api/crawler/status", headers={"Authorization": "Bearer test-only-token"})
        assert response.status_code == 200
    monkeypatch.delenv("MEDIACRAWLER_API_TOKEN")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8080") as client:
        assert (await client.get("/api/crawler/status", headers={"Origin": "http://localhost:8080"})).status_code == 200
        assert (await client.get("/api/crawler/status", headers={"Origin": "https://untrusted.example"})).status_code == 403
        assert (await client.get("/api/crawler/status", headers={"Host": "rebound.example"})).status_code == 403


@pytest.mark.parametrize("path", ["/api/ws/logs", "/api/ws/status"])
def test_cross_origin_websocket_is_rejected(monkeypatch, path):
    monkeypatch.delenv("MEDIACRAWLER_API_TOKEN", raising=False)
    async def local_client(scope, receive, send):
        scope["client"] = ("127.0.0.1", 1234)
        await app(scope, receive, send)

    with TestClient(local_client, base_url="http://localhost") as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path, headers={"Origin": "https://untrusted.example"}):
                pytest.fail("Untrusted WebSocket was accepted")


@pytest.mark.asyncio
async def test_cookie_is_not_in_command_or_logs_and_reaches_child(monkeypatch):
    manager = CrawlerManager()
    secret = "sessionid=example-secret; token=another-secret"
    request = CrawlerStartRequest(platform="xhs", cookies=secret)
    process = Mock()
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr("subprocess.Popen", spawn)
    monkeypatch.setattr(manager, "_read_output", AsyncMock())
    assert await manager.start(request)
    await manager._read_task
    assert secret not in " ".join(spawn.call_args.args[0])
    assert "--cookies" not in spawn.call_args.args[0]
    assert spawn.call_args.kwargs["env"]["MEDIACRAWLER_COOKIES"] == secret
    assert all("example-secret" not in entry.message for entry in manager.logs)
    assert all("another-secret" not in entry.message for entry in manager.logs)
    entry = manager._create_log_entry("server echoed example-secret and another-secret")
    assert entry.message == "server echoed [REDACTED] and [REDACTED]"
    assert "example-secret" not in repr(request)


@pytest.mark.asyncio
async def test_cli_reads_cookie_from_environment_without_exposing_help(monkeypatch, capsys):
    import config
    from cmd_arg import parse_cmd
    original = {name: value for name, value in vars(config).items() if name.isupper()}
    monkeypatch.setenv("MEDIACRAWLER_COOKIES", "sessionid=env-only-secret")
    try:
        await parse_cmd(["--platform", "xhs", "--lt", "cookie"])
        assert config.COOKIES == "sessionid=env-only-secret"
        with pytest.raises(SystemExit) as exit_info:
            await parse_cmd(["--help"])
        assert exit_info.value.code == 0
        assert "env-only-secret" not in capsys.readouterr().out
        await parse_cmd(["--platform", "xhs", "--cookies", "explicit=value"])
        assert config.COOKIES == "explicit=value"
    finally:
        for name, value in original.items():
            setattr(config, name, value)


@pytest.mark.asyncio
async def test_jsonl_results_can_be_listed_counted_previewed_and_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    result_dir = tmp_path / "xhs" / "jsonl"
    result_dir.mkdir(parents=True)
    output = result_dir / "results.jsonl"
    output.write_text('{"id": "1", "text": "中文"}\n\n{"id": "2"}\n', encoding="utf-8")
    files = (await data.list_data_files())["files"]
    assert len(files) == 1
    assert files[0]["record_count"] == 2
    assert (await data.get_data_stats())["by_type"] == {"jsonl": 1}
    preview = await data.get_file_content("xhs/jsonl/results.jsonl", limit=1)
    assert preview == {"data": [{"id": "1", "text": "中文"}], "total": 2}
    assert (await data.download_file("xhs/jsonl/results.jsonl")).path == output


@pytest.mark.asyncio
async def test_invalid_jsonl_reports_bad_input(tmp_path, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    (tmp_path / "broken.jsonl").write_text('{"id": 1}\ninvalid\n', encoding="utf-8")
    with pytest.raises(HTTPException) as error:
        await data.get_file_content("broken.jsonl")
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_untrusted_request_cannot_start_or_stop_a_process(monkeypatch):
    from api.services import crawler_manager
    monkeypatch.delenv("MEDIACRAWLER_API_TOKEN", raising=False)
    start = AsyncMock()
    stop = AsyncMock()
    monkeypatch.setattr(crawler_manager, "start", start)
    monkeypatch.setattr(crawler_manager, "stop", stop)
    transport = httpx.ASGITransport(app=app, client=("198.51.100.8", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8080") as client:
        assert (await client.post("/api/crawler/start", json={"platform": "xhs"})).status_code == 403
        assert (await client.post("/api/crawler/stop")).status_code == 403
    start.assert_not_awaited()
    stop.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 1001])
async def test_jsonl_preview_limit_is_validated(monkeypatch, limit):
    monkeypatch.delenv("MEDIACRAWLER_API_TOKEN", raising=False)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8080") as client:
        response = await client.get("/api/data/files/results.jsonl", params={"limit": limit})
    assert response.status_code == 422
