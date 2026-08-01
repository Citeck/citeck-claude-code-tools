#!/usr/bin/env python3
"""Create a reviewable surface inventory from common Citeck backend/frontend patterns."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


MAPPING = re.compile(
    r"@(Get|Post|Put|Delete|Patch)Mapping\s*(?:\((.*?)\))?",
    re.S,
)
REQUEST_MAPPING = re.compile(r"@RequestMapping\s*\((.*?)\)", re.S)
CONFIG_PROPERTIES = re.compile(
    r"@ConfigurationProperties\s*\(\s*(?:(?:prefix|value)\s*=\s*)?[\"']([^\"']+)"
)
SCHEDULED = re.compile(r"@Scheduled\s*\((.*?)\)", re.S)
HTTP_STRING = re.compile(r"[\"'](/(?:gateway/[^\"']+|api/[^\"']+))[\"']")
QUOTED_PATH = re.compile(r"[\"'](/[^\"']*)[\"']")
REQUEST_METHOD = re.compile(r"RequestMethod\.([A-Z]+)")


@dataclass(frozen=True, order=True)
class Surface:
    kind: str
    source: str
    operation: str
    capability: str

    @property
    def surface_id(self) -> str:
        value = f"{self.kind}\0{self.source}\0{self.operation}".encode()
        digest = hashlib.sha1(value).hexdigest()[:10].upper()
        return f"SURF-{self.kind.upper()}-{digest}"


def compact(value: str) -> str:
    return " ".join(value.split())[:300]


def join_paths(prefix: str, path: str) -> str:
    if not prefix:
        return path or "/"
    if not path:
        return prefix
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"


def following_symbol(text: str, end: int) -> str:
    tail = text[end : end + 500]
    match = re.search(
        r"(?:fun\s+([A-Za-z_]\w*)|"
        r"(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\],.? ]+\s+([A-Za-z_]\w*))\s*\(",
        tail,
    )
    if match:
        return match.group(1) or match.group(2)
    return f"line-{text.count(chr(10), 0, end) + 1}"


def discover_file(repo: Path, path: Path) -> set[Surface]:
    relative = path.relative_to(repo).as_posix()
    text = path.read_text(errors="replace")
    result: set[Surface] = set()

    if path.suffix in {".kt", ".java"}:
        request_mappings = list(REQUEST_MAPPING.finditer(text))
        base_path = ""
        for mapping in request_mappings:
            detail = mapping.group(1)
            path_match = QUOTED_PATH.search(detail)
            if path_match and "RequestMethod." not in detail:
                base_path = path_match.group(1)
                break
        for match in MAPPING.finditer(text):
            method = match.group(1).upper()
            detail = compact(match.group(2) or "")
            path_match = QUOTED_PATH.search(detail)
            operation = join_paths(base_path, path_match.group(1) if path_match else "")
            result.add(Surface("rest", relative, f"{method} {operation}", path.stem))
        for match in request_mappings:
            detail = compact(match.group(1))
            method_match = REQUEST_METHOD.search(detail)
            if method_match:
                path_match = QUOTED_PATH.search(detail)
                operation = join_paths(base_path, path_match.group(1) if path_match else "")
                result.add(Surface("rest", relative, f"{method_match.group(1)} {operation}", path.stem))
        for match in CONFIG_PROPERTIES.finditer(text):
            result.add(Surface("config", relative, match.group(1), path.stem))
        for match in SCHEDULED.finditer(text):
            operation = f"{compact(match.group(1))} @ {following_symbol(text, match.end())}"
            result.add(Surface("scheduler", relative, operation, path.stem))
        if "/tools/" in f"/{relative}" and path.stem.endswith("Tool"):
            result.add(Surface("tool", relative, path.stem, path.stem))
        if "ExternalTask" in path.stem or "ExternalTaskHandler" in text:
            result.add(Surface("external-task", relative, path.stem, path.stem))

    if path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        for match in HTTP_STRING.finditer(text):
            result.add(Surface("ui-api", relative, match.group(1), path.stem))

    model_markers = (
        "/resources/eapps/artifacts/model/type/",
        "/resources/eapps/artifacts/model/aspect/",
    )
    if path.suffix in {".yml", ".yaml"} and any(marker in f"/{relative}" for marker in model_markers):
        result.add(Surface("model", relative, path.stem, path.stem))
    return result


def discover(repo: Path) -> list[Surface]:
    surfaces: set[Surface] = set()
    roots = [repo / "src" / "main", repo / "frontend" / "src"]
    if not any(root.is_dir() for root in roots):
        roots.append(repo / "src")
    visited: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path in visited:
                continue
            visited.add(path)
            if path.suffix not in {".kt", ".java", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml"}:
                continue
            surfaces.update(discover_file(repo, path))
    return sorted(surfaces)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    surfaces = discover(repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "surface_id",
                "kind",
                "source",
                "operation",
                "capability",
                "included",
                "case_ids",
                "exclusion_reason",
                "owner",
            )
        )
        for surface in surfaces:
            writer.writerow(
                (
                    surface.surface_id,
                    surface.kind,
                    surface.source,
                    surface.operation,
                    surface.capability,
                    "yes",
                    "",
                    "-",
                    "UNASSIGNED",
                )
            )
    print(f"Discovered {len(surfaces)} surfaces in {repo}; review {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
