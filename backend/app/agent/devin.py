"""Devin v3 adapter behind AgentPort (DESIGN.md §3-4).

Maps our synchronous request/response seam onto Devin's async session:
one long-lived session per run; `next_action` sends the evidence message and
polls the message stream until a fenced ```json action block appears. The
orchestrator — not Devin — stays in control of the workflow; Devin is one
opaque reasoning node.

Env: DEVIN_API_KEY (cog_...), DEVIN_ORG_ID. Optional: DEVIN_BASE_URL,
DEVIN_MAX_ACU, DEVIN_MODE, DEVIN_POLL_S."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

import httpx
from pydantic import TypeAdapter, ValidationError

from app.agent import prompts
from app.agent.port import RunContext
from app.models import AgentRequest, DoneRequest, IterationReport

_ACTION = TypeAdapter(AgentRequest)
_FENCE = re.compile(r"```json\s*(.*?)```", re.DOTALL)

MAX_PROTOCOL_RETRIES = 2
MIN_MESSAGE_SPACING_S = 30.0  # documented per-session message rate limit


class DevinConfigError(RuntimeError):
    pass


class DevinAgent:
    def __init__(self) -> None:
        key = os.environ.get("DEVIN_API_KEY")
        org = os.environ.get("DEVIN_ORG_ID")
        if not key or not org:
            raise DevinConfigError("DEVIN_API_KEY and DEVIN_ORG_ID are required")
        base = os.environ.get("DEVIN_BASE_URL", "https://api.devin.ai")
        self._org_base = f"{base}/v3/organizations/{org}"
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}"}, timeout=60.0)
        self.poll_s = float(os.environ.get("DEVIN_POLL_S", "10"))
        self.session_id: str | None = None
        self._cursor: str | None = None
        self._seen: set[str] = set()  # processed message ids: end_cursor is
        # INCLUSIVE of the last item, so cursor-only polling re-delivers the
        # final message of each page — dedupe is mandatory (found live 2026-08-22)
        self._narration: list[str] = []
        self._last_send = 0.0
        self._session_url: str | None = None

    # ------------------------------------------------------------ AgentPort --

    async def start(self, ctx: RunContext) -> None:
        repo = os.environ.get("DEVIN_REPO") or None
        body = {
            "title": f"antenna-run {ctx.run_id}",
            "tags": ["antenna", ctx.run_id],
            "structured_output_schema": prompts.STRUCTURED_OUTPUT_SCHEMA,
            "structured_output_required": False,
        }
        if ctx.extract_mode == "agent" and ctx.blend_path:
            urls = [await self._upload(ctx.blend_path)]
            if ctx.sidecar_path:
                urls.append(await self._upload(ctx.sidecar_path))
            body["attachment_urls"] = urls
            # private repo + no GitHub integration -> inline the script instead
            body["prompt"] = prompts.extraction_prompt(
                ctx, repo, None if repo else prompts.script_source())
            self._narration.append(
                f"Uploaded {ctx.blend_path.name} to the session; the agent reads "
                f"the build file itself ({'repo skill' if repo else 'inlined script'}).")
        else:
            body["prompt"] = prompts.initial_prompt(ctx)
        if os.environ.get("DEVIN_MAX_ACU"):
            body["max_acu_limit"] = int(os.environ["DEVIN_MAX_ACU"])
        if os.environ.get("DEVIN_MODE"):
            body["devin_mode"] = os.environ["DEVIN_MODE"]
        if repo:
            body["repos"] = [repo]
        r = await self._request("POST", f"{self._org_base}/sessions", json=body)
        data = r.json()
        self.session_id = data["session_id"]
        self._session_url = data.get("url")
        self._last_send = time.monotonic()
        self._narration.append(
            f"Devin session started: {self._session_url or self.session_id}")

    async def brief(self, ctx: RunContext) -> None:
        await self._send(prompts.brief_message(ctx, ctx.meta.get("crosscheck", "")))

    async def _upload(self, path: Path) -> str:
        """POST /attachments (multipart `file`) -> pre-signed URL for
        `attachment_urls` (v3 docs, verified 2026-08-22)."""
        with path.open("rb") as f:
            r = await self._request(
                "POST", f"{self._org_base}/attachments",
                files={"file": (path.name, f, "application/octet-stream")},
                timeout=600.0)
        return r.json()["url"]

    async def next_action(self, report: IterationReport | None) -> AgentRequest:
        if report is not None:
            await self._send(prompts.report_message(report))
        for attempt in range(MAX_PROTOCOL_RETRIES + 1):
            action, err = await self._await_action()
            if action is not None:
                return action
            if attempt < MAX_PROTOCOL_RETRIES:
                await self._send(
                    f"Your last reply had no valid action ({err}). Reply with "
                    f"exactly one fenced ```json block per the protocol.")
        raise RuntimeError(f"agent protocol failure after retries: {err}")

    async def narrate(self) -> list[str]:
        out, self._narration = self._narration, []
        return out

    async def close(self, reason: str) -> dict | None:
        """Closing message, then wait briefly for Devin's structured_output
        (it updates on Devin's schedule; ~30-60 s after the done action in
        practice). The session is left alive for inspection in the Devin UI
        unless DEVIN_TERMINATE_ON_CLOSE=1 — an idle session burns no ACUs."""
        report = None
        try:
            if self.session_id:
                await self._send(
                    f"Run is being closed ({reason}). Update your structured "
                    f"output with final status. No further reply is needed.")
                for _ in range(int(os.environ.get("DEVIN_REPORT_POLLS", "6"))):
                    r = await self._request(
                        "GET", f"{self._org_base}/sessions/{self.session_id}")
                    so = r.json().get("structured_output")
                    if so and (so.get("status") == "concluded" or so.get("final")):
                        report = so
                        break
                    await asyncio.sleep(self.poll_s)
                if os.environ.get("DEVIN_TERMINATE_ON_CLOSE") == "1":
                    await self._request(
                        "DELETE", f"{self._org_base}/sessions/{self.session_id}")
        except Exception as e:
            self._narration.append(f"close: {e}")
        await self._http.aclose()
        return report

    # ------------------------------------------------------------- internals --

    async def _send(self, message: str) -> None:
        wait = MIN_MESSAGE_SPACING_S - (time.monotonic() - self._last_send)
        if wait > 0:
            await asyncio.sleep(wait)
        await self._request(
            "POST", f"{self._org_base}/sessions/{self.session_id}/messages",
            json={"message": message})
        self._last_send = time.monotonic()

    async def _await_action(self) -> tuple[AgentRequest | None, str]:
        """Poll messages until a devin-sourced message with a parsable action
        arrives, narrating everything else. Also watches session status."""
        err = "no reply"
        while True:
            for msg in await self._poll_messages():
                text = msg.get("message", "")
                action, this_err = self._parse_action(text)
                narration = _FENCE.sub("", text).strip()
                if narration:
                    self._narration.append(narration)
                if action is not None:
                    return action, ""
                if this_err:
                    err = this_err
            status = await self._status()
            if status in ("exit", "error"):
                return DoneRequest(
                    action="done", ranking=[],
                    rationale=f"session ended ({status}) without explicit done"
                ), ""
            await asyncio.sleep(self.poll_s)

    async def _poll_messages(self) -> list[dict]:
        params = {"first": 100}
        if self._cursor:
            params["after"] = self._cursor
        r = await self._request(
            "GET", f"{self._org_base}/sessions/{self.session_id}/messages",
            params=params)
        data = r.json()
        items = data.get("items", data if isinstance(data, list) else [])
        cursor = (data.get("end_cursor") if isinstance(data, dict) else None) or \
                 (data.get("page_info", {}).get("end_cursor")
                  if isinstance(data, dict) else None)
        if cursor:
            self._cursor = cursor
        fresh = []
        for m in items:
            mid = str(m.get("event_id") or m.get("id")
                      or f"{m.get('created_at')}-{hash(m.get('message',''))}")
            if mid in self._seen:
                continue
            self._seen.add(mid)
            if m.get("source") == "devin":
                fresh.append(m)
        return fresh

    async def _status(self) -> str:
        r = await self._request(
            "GET", f"{self._org_base}/sessions/{self.session_id}")
        return r.json().get("status", "running")

    def _parse_action(self, text: str) -> tuple[AgentRequest | None, str]:
        blocks = _FENCE.findall(text)
        err = ""
        for raw in reversed(blocks):  # last block wins if several
            try:
                return _ACTION.validate_python(json.loads(raw)), ""
            except (json.JSONDecodeError, ValidationError) as e:
                err = str(e)[:300]
        return None, err or "no json block found"

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        delay = 2.0
        for _ in range(6):
            r = await self._http.request(method, url, **kw)
            if r.status_code == 429:
                retry = float(r.headers.get("Retry-After", delay))
                await asyncio.sleep(min(retry, 60.0))
                delay = min(delay * 2, 60.0)
                continue
            if r.status_code >= 400:
                raise RuntimeError(
                    f"Devin API {r.status_code} on {method} {url.split('/v3/')[-1]}: "
                    f"{r.text[:300]}")
            return r
        raise RuntimeError(f"Devin API rate-limited after retries: {url}")
