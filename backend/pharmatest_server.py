#!/usr/bin/env python3
"""Tiny TOML-backed leaderboard API for PharmaTest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import tomllib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


DEFAULT_STATE = Path.home() / "pharmatest" / "scores.toml"
STATE_PATH = Path(os.environ.get("PHARMATEST_SCORES", DEFAULT_STATE))
FORFATTNING_STATE_PATH = Path(
    os.environ.get("FORFATTNING_SCORES", STATE_PATH.with_name("forfattning-scores.toml"))
)
GALENIK_STATE_PATH = Path(
    os.environ.get("GALENIK_SCORES", STATE_PATH.with_name("galenik-scores.toml"))
)
FARMAKOGNOSI_STATE_PATH = Path(
    os.environ.get("FARMAKOGNOSI_SCORES", STATE_PATH.with_name("farmakognosi-scores.toml"))
)
INTERAKTIONER_STATE_PATH = Path(
    os.environ.get("INTERAKTIONER_SCORES", STATE_PATH.with_name("interaktioner-scores.toml"))
)
DOSLAB_STATE_PATH = Path(
    os.environ.get("DOSLAB_SCORES", STATE_PATH.with_name("doslab-scores.toml"))
)
PUNGDJUR_STATE_PATH = Path(
    os.environ.get("PUNGDJUR_SCORES", STATE_PATH.with_name("pungdjur-scores.toml"))
)
HAJAR_STATE_PATH = Path(
    os.environ.get("HAJAR_SCORES", STATE_PATH.with_name("hajar-scores.toml"))
)
PORT = int(os.environ.get("PHARMATEST_PORT", "8798"))
MAX_BODY = 4096
MAX_SCORES = 100
PUBLIC_LIMIT = 20
LOCK = threading.RLock()
NAME_CHARS = re.compile(r"^[\w .'-]+$", re.UNICODE)


def clean_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Namn saknas")
    name = " ".join(value.strip().split())
    if not 1 <= len(name) <= 24:
        raise ValueError("Namnet måste vara 1–24 tecken")
    if not NAME_CHARS.fullmatch(name):
        raise ValueError("Namnet innehåller otillåtna tecken")
    return name


def clean_result(score: Any, total: Any) -> tuple[int, int]:
    if isinstance(score, bool) or isinstance(total, bool):
        raise ValueError("Ogiltigt resultat")
    if not isinstance(score, int) or not isinstance(total, int):
        raise ValueError("Resultatet måste vara heltal")
    if not 1 <= total <= 100 or not 0 <= score <= total:
        raise ValueError("Ogiltigt resultat")
    return score, total


def load_scores(path: Path = STATE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    scores = data.get("scores", [])
    if not isinstance(scores, list):
        raise ValueError("scores.toml har ogiltigt format")
    return scores


def rank_key(entry: dict[str, Any]) -> tuple[float, int, int, str]:
    return (-float(entry["percent"]), -int(entry["score"]), -int(entry["total"]), str(entry["created_at"]))


def public_scores(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(scores, key=rank_key)[:PUBLIC_LIMIT]
    return [
        {
            "rank": index + 1,
            "name": entry["name"],
            "score": entry["score"],
            "total": entry["total"],
            "percent": entry["percent"],
            "created_at": entry["created_at"],
        }
        for index, entry in enumerate(ranked)
    ]


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def write_scores(scores: list[dict[str, Any]], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["version = 1", ""]
    for entry in scores:
        lines.extend(
            [
                "[[scores]]",
                f"name = {toml_string(str(entry['name']))}",
                f"score = {int(entry['score'])}",
                f"total = {int(entry['total'])}",
                f"percent = {float(entry['percent']):.2f}",
                f"created_at = {toml_string(str(entry['created_at']))}",
                "",
            ]
        )
    payload = "\n".join(lines)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix="scores.", suffix=".tmp", delete=False) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def save_result(name_value: Any, score_value: Any, total_value: Any, path: Path = STATE_PATH) -> dict[str, Any]:
    name = clean_name(name_value)
    score, total = clean_result(score_value, total_value)
    entry = {
        "name": name,
        "score": score,
        "total": total,
        "percent": round(score / total * 100, 2),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LOCK:
        scores = load_scores(path)
        same_name = [item for item in scores if str(item.get("name", "")).casefold() == name.casefold()]
        accepted = not same_name or rank_key(entry) < rank_key(sorted(same_name, key=rank_key)[0])
        if accepted:
            scores = [item for item in scores if str(item.get("name", "")).casefold() != name.casefold()]
            scores.append(entry)
            scores = sorted(scores, key=rank_key)[:MAX_SCORES]
            write_scores(scores, path)
        board = public_scores(scores)
    rank = next((item["rank"] for item in board if item["name"].casefold() == name.casefold()), None)
    return {"ok": True, "accepted": accepted, "rank": rank, "leaderboard": board}


class Handler(BaseHTTPRequestHandler):
    server_version = "PharmaTest/1.0"

    def log_message(self, message: str, *args: Any) -> None:
        print(f"{self.address_string()} - {message % args}", flush=True)

    def json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            self.json_response(200, {"ok": True})
            return
        score_path = {
            "/api/pharmatest/leaderboard": STATE_PATH,
            "/api/forfattning/leaderboard": FORFATTNING_STATE_PATH,
            "/api/galenik/leaderboard": GALENIK_STATE_PATH,
            "/api/farmakognosi/leaderboard": FARMAKOGNOSI_STATE_PATH,
            "/api/interaktioner/leaderboard": INTERAKTIONER_STATE_PATH,
            "/api/doslab/leaderboard": DOSLAB_STATE_PATH,
            "/api/pungdjur/leaderboard": PUNGDJUR_STATE_PATH,
            "/api/hajar/leaderboard": HAJAR_STATE_PATH,
        }.get(path)
        if score_path is not None:
            try:
                with LOCK:
                    board = public_scores(load_scores(score_path))
                self.json_response(200, {"ok": True, "leaderboard": board})
            except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
                self.log_error("could not load scores: %s", error)
                self.json_response(500, {"ok": False, "error": "Topplistan kunde inte läsas"})
            return
        self.json_response(404, {"ok": False, "error": "Hittades inte"})

    def do_POST(self) -> None:  # noqa: N802
        score_path = {
            "/api/pharmatest/scores": STATE_PATH,
            "/api/forfattning/scores": FORFATTNING_STATE_PATH,
            "/api/galenik/scores": GALENIK_STATE_PATH,
            "/api/farmakognosi/scores": FARMAKOGNOSI_STATE_PATH,
            "/api/interaktioner/scores": INTERAKTIONER_STATE_PATH,
            "/api/doslab/scores": DOSLAB_STATE_PATH,
            "/api/pungdjur/scores": PUNGDJUR_STATE_PATH,
            "/api/hajar/scores": HAJAR_STATE_PATH,
        }.get(urlsplit(self.path).path)
        if score_path is None:
            self.json_response(404, {"ok": False, "error": "Hittades inte"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= MAX_BODY:
                raise ValueError("Ogiltig datamängd")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Ogiltig JSON")
            result = save_result(payload.get("name"), payload.get("score"), payload.get("total"), score_path)
            self.json_response(200, result)
        except (ValueError, json.JSONDecodeError) as error:
            self.json_response(400, {"ok": False, "error": str(error)})
        except (OSError, tomllib.TOMLDecodeError) as error:
            self.log_error("could not save score: %s", error)
            self.json_response(500, {"ok": False, "error": "Resultatet kunde inte sparas"})


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "scores.toml"
        first = save_result("Ada", 9, 10, path)
        assert first["accepted"] and first["rank"] == 1
        weaker = save_result("ada", 8, 10, path)
        assert not weaker["accepted"]
        stronger = save_result("Ada", 20, 20, path)
        assert stronger["accepted"] and stronger["rank"] == 1
        save_result("Lin", 19, 20, path)
        board = public_scores(load_scores(path))
        assert [entry["name"] for entry in board] == ["Ada", "Lin"]
        assert len(load_scores(path)) == 2
        try:
            save_result("<script>", 10, 10, path)
            raise AssertionError("unsafe name accepted")
        except ValueError:
            pass
    print("self-test ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"PharmaTest leaderboard listening on 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
