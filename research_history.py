"""연구 소스 체크포인트와 명시적 파일 재사용. 연구 성공 판정과 독립적으로 동작한다."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


class HistoryError(RuntimeError):
    pass


MAX_BYTES = 5 * 1024 * 1024
SUFFIXES = {".py", ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".sh"}
EXCLUDED_DIRS = {".git", ".claude", ".codex", "results", "data", "datasets", "hf_cache", "logs",
                 "eval_samples", "eval_results", "__pycache__", ".venv"}
SECRET = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-ant-|hf_)[A-Za-z0-9_-]{20,}"
                    rb"|(?i:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[\"'][A-Za-z0-9_/-]{16,}[\"']")


def git(repo, *args, env=None, data=None):
    settings = {**(os.environ if env is None else env), "GIT_LITERAL_PATHSPECS": "1"}
    result = subprocess.run(["git", *args], cwd=repo, input=data, capture_output=True, env=settings)
    if result.returncode:
        raise HistoryError(f"git {args[0]} 실패: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def text_git(repo, *args, **kwargs):
    return git(repo, *args, **kwargs).decode().strip()


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def path_reason(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or str(path) != name or "\n" in name:
        return "안전하지 않은 상대 경로"
    if any(p in EXCLUDED_DIRS for p in path.parts):
        return "데이터·결과·도구 설정 경로"
    if re.search(r"(?i)(^\.env(?:$|\.)|^id_rsa|^id_ed25519|(?:secret|credential).*\.(?:json|ya?ml|txt|ini)$|^tokens?\.)", path.name):
        return "비밀정보 가능 파일명"
    if path.suffix not in SUFFIXES and path.name not in {".gitignore", "Makefile"}:
        return "자동 저장 소스 확장자 아님"
    return ""


def content_reason(data):
    if len(data) > MAX_BYTES:
        return "5MB 초과"
    if b"\0" in data:
        return "바이너리"
    if SECRET.search(data):
        return "비밀정보 패턴 감지"
    return ""


def safe_target(repo, name):
    reason = path_reason(name)
    target = repo / name
    if reason or not target.resolve().is_relative_to(repo.resolve()):
        raise HistoryError(f"허용되지 않은 소스 경로: {name} ({reason or '외부 경로'})")
    if any(p.is_symlink() for p in [target, *target.parents] if p != repo and p.is_relative_to(repo)):
        raise HistoryError(f"symlink 경로 거부: {name}")
    return target


def listed(repo, *args):
    return {p.decode() for p in git(repo, *args, "-z").split(b"\0") if p}


def source_state(repo):
    names = listed(repo, "ls-files", "--cached", "--others", "--exclude-standard")
    files, excluded = {}, {}
    for name in sorted(names):
        reason = path_reason(name)
        if not reason:
            try:
                target = safe_target(repo, name)
                if not target.exists():
                    continue
                if not target.is_file():
                    reason = "일반 파일 아님"
                elif target.stat().st_size > MAX_BYTES:
                    reason = "5MB 초과"
                else:
                    data = target.read_bytes()
                    reason = content_reason(data)
                    if not reason:
                        files[name] = {"hash": hashlib.sha256(data).hexdigest(),
                                       "executable": bool(target.stat().st_mode & 0o111)}
            except HistoryError as e:
                reason = str(e)
        if reason:
            excluded[name] = reason
    return files, excluded


def begin(repo, run_dir):
    """실행 전에 한 번만 소유 범위를 고정. 기존 미커밋·staged 변경은 자동 커밋하지 않는다."""
    path = run_dir / "code_baseline.json"
    if path.exists():
        pending = load(run_dir / "checkpoint_pending.json")
        if pending:
            _finish_transaction(repo, run_dir, pending)
        baseline = load(path)
        latest = load(run_dir / "checkpoint.json") or baseline
        if (text_git(repo, "symbolic-ref", "HEAD") != baseline["branch"] or
                text_git(repo, "rev-parse", "HEAD") != latest["sha"]):
            raise HistoryError("재개 전 브랜치/HEAD가 변경됐습니다. 구현 전에 코드 버전을 확인하세요.")
        return baseline
    files, excluded = source_state(repo)
    protected = (listed(repo, "diff", "--name-only", "HEAD") |
                 listed(repo, "ls-files", "--others", "--exclude-standard"))
    baseline = {"sha": text_git(repo, "rev-parse", "HEAD"),
                "branch": text_git(repo, "symbolic-ref", "HEAD"),
                "files": files, "protected_paths": sorted(protected), "excluded": excluded}
    save(path, baseline)
    return baseline


def _finish_transaction(repo, run_dir, tx):
    """commit/ref 갱신 중 중단돼도 동일 커밋으로 복구한다. index의 다른 경로는 건드리지 않는다."""
    branch = text_git(repo, "symbolic-ref", "HEAD")
    head = text_git(repo, "rev-parse", "HEAD")
    if branch != tx["branch"] or head not in {tx["parent"], tx["sha"]}:
        raise HistoryError("체크포인트 복구 중 브랜치/HEAD 변경 감지. 덮어쓰지 않습니다.")
    if head == tx["parent"]:
        git(repo, "update-ref", tx["branch"], tx["sha"], tx["parent"])
    # ref 이동 후 index는 이전 HEAD 상태일 수 있다. 예상 밖 staged 변경은 보존하고 중단한다.
    for name in tx["paths"]:
        actual = git(repo, "ls-files", "--stage", "-z", "--", name).decode()
        old = tx["index_before"][name]
        entry = git(repo, "ls-tree", "-z", tx["sha"], "--", name)
        desired = ""
        if entry:
            descriptor, _ = entry.split(b"\t", 1)
            mode, _, oid = descriptor.decode().split()
            desired = f"{mode} {oid} 0\t{name}\0"
        if actual not in {old, desired}:
            raise HistoryError(f"체크포인트 복구 중 index 변경 감지: {name}")
    git(repo, "reset", "-q", tx["sha"], "--", *tx["paths"])
    git(repo, "update-ref", tx["ref"], tx["sha"])
    save(run_dir / "checkpoints" / f"{tx['sequence']:03d}.json", tx)
    save(run_dir / "checkpoint.json", tx)
    (run_dir / "checkpoint_pending.json").unlink(missing_ok=True)
    return tx


def checkpoint(repo, run_dir, iteration, reason):
    """검증과 무관하게 이번 작업의 변경을 저장. 별도 index로 unrelated staged 변경을 보존한다."""
    pending = load(run_dir / "checkpoint_pending.json")
    if pending:
        _finish_transaction(repo, run_dir, pending)
    baseline = load(run_dir / "code_baseline.json")
    if not baseline:
        raise HistoryError("실행 전 코드 소유 범위 기록이 없습니다. 기존 변경을 임의 커밋하지 않습니다.")
    if text_git(repo, "symbolic-ref", "HEAD") != baseline["branch"]:
        raise HistoryError("실행 중 브랜치 변경 감지. 체크포인트를 중단합니다.")
    latest = load(run_dir / "checkpoint.json")
    head = text_git(repo, "rev-parse", "HEAD")
    if head != (latest or baseline)["sha"]:
        raise HistoryError("실행 중 외부 커밋 감지. 자동 커밋하지 않습니다.")
    files, excluded = source_state(repo)
    imported = set((load(run_dir / "reuse_manifest.json") or {}).get("files", {}))
    protected = (set(baseline["protected_paths"]) - imported) | listed(repo, "diff", "--cached", "--name-only")
    dirty = listed(repo, "diff", "--name-only", "HEAD") | listed(repo, "ls-files", "--others", "--exclude-standard")
    changed = {p for p in set(files) | set(baseline["files"]) if files.get(p) != baseline["files"].get(p)}
    blocked = {p: "실행 전 사용자 변경 또는 외부 staged 변경" for p in changed & protected}
    excluded.update(blocked)
    selected = sorted((changed | imported) - protected - set(excluded))
    # 이전 부분 체크포인트에서 저장한 경로가 원래 내용으로 돌아간 경우도 포함한다.
    if latest:
        selected = sorted(set(selected) | (set(latest["owned_paths"]) - protected - set(excluded)))
    sequence = len(list((run_dir / "checkpoints").glob("*.json"))) + 1
    meta = {"sha": head, "before_sha": baseline["sha"], "branch": baseline["branch"],
            "reason": reason, "state": "unreviewed", "excluded_files": excluded,
            "unpreserved_paths": sorted(((changed | dirty) & set(excluded)) | protected),
            "owned_paths": selected, "paths": [], "sequence": sequence}
    if selected:
        with tempfile.TemporaryDirectory(prefix="research-index-") as directory:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index"), "GIT_LITERAL_PATHSPECS": "1"}
            git(repo, "read-tree", head, env=env)
            # 커밋에도 없고 작업 폴더에서도 사라진 파일은 pathspec에 포함하지 않는다.
            tracked = listed(repo, "ls-files", "--cached")
            stageable = [p for p in selected if p in files or p in tracked]
            if stageable:
                git(repo, "add", "-A", "--", *stageable, env=env)
            tree = text_git(repo, "write-tree", env=env)
            if tree != text_git(repo, "rev-parse", "HEAD^{tree}"):
                paths = sorted(listed(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", head, tree))
                sha = text_git(repo, "commit-tree", tree, "-p", head, "-m",
                               f"[checkpoint iter_{iteration:03d}] {reason} (미검증)", env=env)
                meta.update(sha=sha, parent=head, paths=paths,
                            ref=f"refs/research-checkpoints/iter-{iteration:03d}/{sequence:03d}",
                            index_before={p: git(repo, "ls-files", "--stage", "-z", "--", p).decode() for p in paths})
                save(run_dir / "checkpoint_pending.json", meta)
                return _finish_transaction(repo, run_dir, meta)
    # 빈 커밋은 만들지 않는다. 결과와 연결할 SHA 및 제외 사유는 남긴다.
    save(run_dir / "checkpoint.json", meta)
    return meta


def resolve_assets(repo, assets):
    """모델이 지정한 경로·출처를 모두 사전 검증. 디렉터리·ref 표현식·symlink는 받지 않는다."""
    resolved = {}
    for asset in assets:
        sha = asset.get("source_commit", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise HistoryError("reuse_assets.source_commit은 전체 40자리 commit SHA여야 합니다.")
        if text_git(repo, "cat-file", "-t", sha) != "commit":
            raise HistoryError("재사용 출처가 commit이 아닙니다.")
        if not asset.get("reason", "").strip() or not asset.get("required_checks") or not asset.get("paths"):
            raise HistoryError("재사용 이유·파일 목록·필수 검증 조건이 필요합니다.")
        for name in asset["paths"]:
            safe_target(repo, name)
            if name in resolved:
                raise HistoryError(f"재사용 대상 중복: {name}")
            entry = git(repo, "ls-tree", "-z", sha, "--", name).split(b"\0")[0]
            if not entry:
                raise HistoryError(f"재사용 원본 파일 없음: {sha}:{name}")
            descriptor, actual = entry.split(b"\t", 1)
            mode, kind, oid = descriptor.decode().split()
            if actual.decode() != name or kind != "blob" or mode not in {"100644", "100755"}:
                raise HistoryError(f"재사용 대상은 일반 소스 파일이어야 합니다: {name}")
            if int(text_git(repo, "cat-file", "-s", oid)) > MAX_BYTES:
                raise HistoryError(f"재사용 파일 크기 초과: {name}")
            data = git(repo, "cat-file", "blob", oid)
            if content_reason(data):
                raise HistoryError(f"재사용 파일 제외: {name} ({content_reason(data)})")
            resolved[name] = {"source_commit": sha, "blob": oid, "data": data,
                              "mode": mode, "reason": asset["reason"], "required_checks": asset["required_checks"]}
    return resolved


def prepare_assets(repo, run_dir, assets):
    """충돌 시 어떤 파일도 덮어쓰지 않는다. 완료 marker가 있으면 재개 시 수정본을 원복하지 않는다."""
    marker = run_dir / "reuse_manifest.json"
    prior = load(marker)
    if prior:
        if prior["requested"] != assets:
            raise HistoryError("재사용 준비 후 계획이 변경됐습니다. 새 반복으로 재계획하세요.")
        missing = [name for name in prior["files"] if not safe_target(repo, name).is_file()]
        if missing:
            raise HistoryError(f"준비된 재사용 파일이 누락됨: {missing}")
        return prior
    resolved = resolve_assets(repo, assets)
    for name, source in resolved.items():
        target = safe_target(repo, name)
        if target.exists() and (not target.is_file() or target.read_bytes() != source["data"] or
                                bool(target.stat().st_mode & 0o111) != (source["mode"] == "100755")):
            raise HistoryError(f"재사용 파일 충돌: {name}. 기존 파일을 덮어쓰지 않습니다.")
        if any(p.exists() and not p.is_dir() for p in target.parents if p != repo and p.is_relative_to(repo)):
            raise HistoryError(f"재사용 상위 경로 충돌: {name}")
    for name, source in resolved.items():
        target = safe_target(repo, name)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(source["data"])
            target.chmod(0o755 if source["mode"] == "100755" else 0o644)
    result = {"requested": assets, "state": "pending_validation",
              "files": {name: {k: v for k, v in source.items() if k != "data"} for name, source in resolved.items()}}
    save(marker, result)
    return result
