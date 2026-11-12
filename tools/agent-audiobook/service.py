"""Libation v14.2.2 adapter. Native output is classified, never forwarded."""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import tempfile
import termios
import time
from urllib.parse import urlsplit

VERSION = "14.2.2"


class Error(Exception):
    def __init__(self, code, **details):
        self.code, self.details = code, details


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, missing=None):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Error("unsafe_symlink")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return missing
    except (OSError, ValueError, UnicodeError):
        raise Error("invalid_state")


def safe_tree(path, create=False):
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise Error("unsafe_symlink")
    # Resolve system path aliases, then reject links within the owned tree.
    path = path.resolve()
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise Error("directory_unavailable")
    for current, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            child = Path(current) / name
            if child.is_symlink():
                raise Error("unsafe_symlink")
    return path


def protect(path):
    path = safe_tree(path)
    os.chmod(path, 0o700)
    for current, dirs, files in os.walk(path):
        for name in dirs:
            os.chmod(Path(current) / name, 0o700)
        for name in files:
            os.chmod(Path(current) / name, 0o600)


def atomic(path, value):
    path = Path(path)
    parent = safe_tree(path.parent, create=True)
    if path.is_symlink():
        raise Error("unsafe_symlink")
    fd, pending = tempfile.mkstemp(prefix=".pending-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


@contextmanager
def lock(path):
    safe_tree(Path(path).parent, create=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Error("operation_in_progress")
        yield
    finally:
        os.close(fd)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(raw, fallback="engine_failed"):
    text = raw.lower()
    if any(word in text for word in ("mfa", "captcha", "one-time", "two-step")):
        return "authentication_action_required"
    if any(word in text for word in ("authentication failed", "authentication required", "authenticationexception", "login is required", "expired session", "expired token", "decrypt existingaccesstoken")):
        return "authentication_required"
    if "saving as plaintext" in text or "failed to encrypt" in text:
        return "native_encryption_failed"
    return fallback


def execute(argv, env=None, timeout=None):
    process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    return process.returncode, (stdout + stderr).decode("utf-8", errors="replace")


def program(override, name):
    candidate = os.environ.get(override) or name
    return shutil.which(candidate)


def inspect_audio(path, row, fmt, allow_no_chapters=False, deep=False, timeout=None):
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        raise Error("missing_or_empty_audio")
    before = path.stat()
    ffprobe = program("AGENT_FFPROBE_BIN", "ffprobe")
    if not ffprobe:
        raise Error("missing_ffprobe")
    code, raw = execute([ffprobe, "-v", "error", "-show_format", "-show_streams",
                         "-show_chapters", "-of", "json", str(path)], timeout=timeout)
    try:
        info = json.loads(raw)
        duration = float(info["format"]["duration"])
        chapters = len(info.get("chapters", []))
        audio = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        container = info["format"]["format_name"]
    except (ValueError, TypeError, KeyError, AttributeError):
        raise Error("invalid_audio")
    if code or not audio or not math.isfinite(duration) or duration <= 0:
        raise Error("invalid_audio")
    if fmt == "m4b" and "mp4" not in container.split(","):
        raise Error("unexpected_container")
    if fmt == "mp3" and "mp3" not in container.split(","):
        raise Error("unexpected_container")
    if fmt == "m4b" and not chapters and not allow_no_chapters:
        raise Error("missing_chapters")
    minutes = row.get("duration_minutes")
    unavailable = []
    if minutes is not None:
        # ExportDto reports integer minutes: allow one minute of quantization.
        if abs(duration - minutes * 60) > 60:
            raise Error("duration_mismatch")
    else:
        unavailable.append("source_duration")
    if not chapters:
        unavailable.append("source_chapters")
    if deep:
        ffmpeg = program("AGENT_FFMPEG_BIN", "ffmpeg")
        if not ffmpeg:
            raise Error("missing_ffmpeg")
        code, _ = execute([ffmpeg, "-v", "error", "-xerror", "-i", str(path),
                           "-map", "0:a", "-f", "null", "-"], timeout=timeout)
        if code:
            raise Error("decode_failed")
    checksum = digest(path)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise Error("audio_changed_during_verification")
    return {"path": str(path), "size": after.st_size, "format": fmt,
            "duration": duration, "chapter_count": chapters, "sha256": checksum,
            "verification": {"success": True, "deep_decode": deep,
                             "unavailable_checks": unavailable,
                             "limits": [] if deep else ["audio_frames_not_fully_decoded"]}}


class Adapter:
    def __init__(self, engine, timeout=None):
        self.engine, self.timeout = engine, timeout
        self.root = Path(os.environ.get("AGENT_DO_HOME", "~/.agent-do")).expanduser().resolve() / "audiobook"

    def profiles(self):
        data = read_json(self.root / "profiles.json", {})
        if not isinstance(data, dict):
            raise Error("invalid_state")
        return data

    def profile(self, alias=None, marketplace=None):
        profiles = self.profiles()
        if alias is None and len(profiles) == 1:
            alias = next(iter(profiles))
        if alias not in profiles:
            raise Error("account_required")
        profile = profiles[alias]
        if marketplace and marketplace != profile["marketplace"]:
            raise Error("marketplace_mismatch")
        return profile

    def area(self, profile):
        return self.root / "accounts" / profile["alias"]

    def ready(self):
        if not self.engine:
            raise Error("missing_engine")
        code, raw = execute([self.engine, "--help"], timeout=self.timeout)
        if code or not re.search(r"(?m)^LibationCli v14\.2\.2\s*$", raw):
            raise Error("unsupported_version")
        key = os.environ.get("LIBATION_MASTER_KEY")
        if not key:
            raise Error("missing_credentials", credential="LIBATION_MASTER_KEY")
        try:
            if len(base64.b64decode(key, validate=True)) != 32:
                raise ValueError()
        except ValueError:
            raise Error("invalid_master_key")

    @contextmanager
    def mutation(self, profile=None):
        old_umask = os.umask(0o077)
        try:
            safe_tree(self.root, create=True)
            with lock(self.root / "operation.lock"):
                if profile:
                    native = safe_tree(profile["libation_files"])
                    protect(native)
                    with lock(native / ".agent-do.lock"):
                        try:
                            yield
                        finally:
                            protect(native)
                else:
                    yield
        finally:
            os.umask(old_umask)

    def logs(self, profile):
        native = safe_tree(profile["libation_files"])
        return {p: (p.stat().st_ino, p.stat().st_size) for p in native.glob("Log*.log")}

    def new_logs(self, profile, before):
        log_text = ""
        for path, (inode, size) in self.logs(profile).items():
            prior_inode, offset = before.get(path, (None, 0))
            with path.open("rb") as stream:
                if prior_inode == inode and size >= offset:
                    stream.seek(offset)
                log_text += stream.read().decode("utf-8", errors="replace")
        return log_text

    def check_result(self, code, raw, log_text):
        if "Another Libation GUI instance is running" in log_text:
            raise Error("native_state_busy")
        if code or re.search(r"\[(ERR|FTL)\]", log_text) or re.search(r"(?mi)^error[:\s]", raw) or any(term in (raw + log_text).lower() for term in ("saving as plaintext", "failed to encrypt")):
            raise Error(classify(raw + log_text), engine_exit_code=code)

    def run(self, profile, verb, *args):
        self.ready()
        before = self.logs(profile)
        env = dict(os.environ, LIBATION_FILES_DIR=profile["libation_files"])
        code, raw = execute([self.engine, verb, *args, "--override", "TokenStorageMethod=Encrypted"],
                            env=env, timeout=self.timeout)
        log_text = self.new_logs(profile, before)
        self.check_result(code, raw, log_text)
        return raw, log_text

    def native_account(self, profile, require_authenticated=True, expected_email=None):
        raw, _ = self.run(profile, "list-accounts", "--bare")
        rows = [line.split("\t") for line in raw.splitlines() if "\t" in line]
        if not rows:
            if not require_authenticated:
                return None, None
            raise Error("authentication_required")
        if len(rows) != 1 or len(rows[0]) != 6 or rows[0][5].strip():
            raise Error("dedicated_account_state_required")
        account, nickname, locale, scan, authenticated, _ = rows[0]
        if expected_email is not None and account != expected_email:
            raise Error("dedicated_account_state_required")
        if not locale or (require_authenticated and authenticated != "yes"):
            raise Error("authentication_required")
        if locale != profile["marketplace"]:
            raise Error("marketplace_mismatch", native_marketplace=locale)
        identity = hashlib.sha256((account + "\0" + locale).encode()).hexdigest()
        if profile.get("native_identity_sha256") and profile["native_identity_sha256"] != identity:
            raise Error("account_identity_changed")
        return account, nickname

    def interactive_login(self, profile, email):
        self.ready()
        if not email or email.startswith("-") or "\n" in email:
            raise Error("email_required")
        # A PTY satisfies native Console.IsInputRedirected without putting the
        # OAuth response in argv. Only the browser login URL is displayed.
        try:
            tty = open("/dev/tty", "w")
        except OSError:
            raise Error("interactive_terminal_required", action_required=True)
        import pty
        master, slave = pty.openpty()
        settings = termios.tcgetattr(slave)
        settings[3] &= ~termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, settings)
        before_logs = self.logs(profile)
        process = subprocess.Popen(
            [self.engine, "login-external", "--account", email, "--locale", profile["marketplace"],
             "--override", "TokenStorageMethod=Encrypted"],
            env=dict(os.environ, LIBATION_FILES_DIR=profile["libation_files"]),
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        content, sent = b"", False
        started = time.monotonic()
        try:
            while process.poll() is None:
                if self.timeout and time.monotonic() - started > self.timeout:
                    raise subprocess.TimeoutExpired("login", self.timeout)
                if not select.select([master], [], [], 0.2)[0]:
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                content += chunk
                if b"Paste URL: " in content and not sent:
                    matches = re.findall(rb"https://[^\s]+", content)
                    urls = []
                    for item in matches:
                        url = item.decode("utf-8", errors="replace")
                        host = urlsplit(url).hostname or ""
                        allowed_hosts = {"www.amazon.com", "www.amazon.co.uk", "www.amazon.de", "www.amazon.fr",
                                         "www.amazon.ca", "www.amazon.com.au", "www.amazon.co.jp", "www.amazon.in",
                                         "www.amazon.es", "www.audible.com", "www.audible.co.uk", "www.audible.de",
                                         "www.audible.fr", "www.audible.ca", "www.audible.com.au", "www.audible.co.jp",
                                         "www.audible.in", "www.audible.es"}
                        if host in allowed_hosts and urlsplit(url).path == "/ap/signin":
                            urls.append(url)
                    if not urls:
                        raise Error("login_protocol_failed")
                    tty.write("Open this Libation sign-in URL in your browser:\n" + urls[0] + "\n")
                    tty.flush()
                    response = getpass.getpass("Paste final browser URL (hidden): ", stream=tty)
                    if not response.startswith("https://") or "\n" in response or "\r" in response:
                        raise Error("invalid_login_response")
                    os.write(master, (response + "\n").encode())
                    sent = True
            process.wait(timeout=5)
            self.check_result(process.returncode, content.decode("utf-8", errors="replace"), self.new_logs(profile, before_logs))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            os.close(master)
            tty.close()

    def connect(self, args):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", args.account):
            raise Error("invalid_account_alias")
        native = safe_tree(args.libation_files)
        output = safe_tree(args.output, create=True)
        if native == output or native in output.parents or output in native.parents:
            raise Error("overlapping_directories")
        if not (native / "Settings.json").is_file():
            raise Error("native_setup_required", action_required=True)
        profile = {"alias": args.account, "marketplace": args.marketplace,
                   "libation_files": str(native), "output": str(output), "format": args.format}
        profiles = self.profiles()
        if args.account in profiles and {k: v for k, v in profiles[args.account].items() if k != "native_identity_sha256"} != profile:
            raise Error("profile_conflict")
        if any(p["libation_files"] == str(native) or p["output"] == str(output)
               for alias, p in profiles.items() if alias != args.account):
            raise Error("shared_profile_directory")
        with self.mutation(profile):
            # Reload inside the global lock to avoid losing another profile.
            profiles = self.profiles()
            if args.account in profiles and {k: v for k, v in profiles[args.account].items() if k != "native_identity_sha256"} != profile:
                raise Error("profile_conflict")
            for alias, p in profiles.items():
                if alias == args.account:
                    continue
                for owned in (Path(p["libation_files"]), Path(p["output"])):
                    for candidate in (native, output):
                        if candidate == owned or candidate in owned.parents or owned in candidate.parents:
                            raise Error("shared_profile_directory")
            if args.login:
                self.native_account(profile, require_authenticated=False, expected_email=args.email)
                self.interactive_login(profile, args.email)
            if args.account in profiles:
                profile["native_identity_sha256"] = profiles[args.account].get("native_identity_sha256")
            account, _ = self.native_account(profile)
            profile["native_identity_sha256"] = hashlib.sha256((account + "\0" + profile["marketplace"]).encode()).hexdigest()
            profiles[args.account] = profile
            atomic(self.root / "profiles.json", profiles)
            atomic(self.area(profile) / "readiness.json", {"authenticated": True, "checked_at": now()})
        return {"success": True, "account": args.account, "marketplace": args.marketplace,
                "session_storage": "libation_native", "encryption_at_rest": "not_validated"}

    def accounts(self):
        entries = []
        for alias, p in self.profiles().items():
            readiness = read_json(self.area(p) / "readiness.json", {})
            entries.append({"account": alias, "marketplace": p["marketplace"],
                            "format": p["format"], "readiness": readiness,
                            "readiness_is_cached": True})
        return {"success": True, "total": len(entries), "accounts": entries}

    def library(self, profile):
        cache = read_json(self.area(profile) / "library.json")
        if cache is None:
            raise Error("library_unavailable")
        if not isinstance(cache, dict) or not isinstance(cache.get("entries"), list) or not isinstance(cache.get("synced_at"), str):
            raise Error("invalid_state")
        seen = set()
        for row in cache["entries"]:
            if not isinstance(row, dict) or not isinstance(row.get("book_id"), str) or not re.fullmatch(r"[A-Za-z0-9]+", row["book_id"]) or row["book_id"] in seen:
                raise Error("invalid_state")
            seen.add(row["book_id"])
        return cache

    def sync(self, profile):
        with self.mutation(profile):
            status_path = self.area(profile) / "sync.json"
            atomic(status_path, {"status": "in_progress", "started_at": now()})
            try:
                account, nickname = self.native_account(profile)
                raw, logs = self.run(profile, "scan")
                processed = re.search(r"(?m)^Total processed: (\d+)\s*$", raw)
                # Native scan swallows some failures; require fresh info-level
                # logging in addition to CLI completion and no ERR/FTL records.
                scan_evidence = re.search(r"\[INF\].*GetAllLibraryItems: Total count (\d+)", logs)
                if "Scan complete." not in raw or not processed or not scan_evidence or int(scan_evidence[1]) != int(processed[1]):
                    raise Error("sync_unverifiable")
                with tempfile.TemporaryDirectory(dir=self.area(profile)) as scratch:
                    export = Path(scratch) / "library.json"
                    self.run(profile, "export", "--json", "--path", str(export))
                    rows = read_json(export)
                if not isinstance(rows, list):
                    raise Error("invalid_export")
                entries, seen = [], set()
                for row in rows:
                    if not isinstance(row, dict):
                        raise Error("invalid_export")
                    if row.get("Account") not in (account, nickname) or row.get("Locale") != profile["marketplace"]:
                        raise Error("export_account_mismatch")
                    book_id, title = row.get("AudibleProductId"), row.get("Title")
                    if not isinstance(book_id, str) or not re.fullmatch(r"[A-Za-z0-9]+", book_id) or not isinstance(title, str):
                        raise Error("invalid_export")
                    if book_id in seen:
                        raise Error("ambiguous_identity")
                    seen.add(book_id)
                    if row.get("AbsentFromLastScan") is True:
                        continue
                    minutes = row.get("LengthInMinutes")
                    entries.append({"book_id": book_id, "title": title,
                                    "duration_minutes": minutes if type(minutes) is int and minutes > 0 else None})
                if int(processed[1]) == 0:
                    entries = []  # Libation skips DB import on successful empty scans.
                cache = {"synced_at": now(), "entries": entries}
                atomic(self.area(profile) / "library.json", cache)
                atomic(self.area(profile) / "readiness.json", {"authenticated": True, "checked_at": now()})
                atomic(status_path, {"status": "complete", "finished_at": now(), "partial_failure": False})
                return {"success": True, "account": profile["alias"], "total": len(entries), "partial_failure": False}
            except BaseException as exc:
                code = exc.code if isinstance(exc, Error) else "interrupted" if isinstance(exc, KeyboardInterrupt) else "operation_timeout" if isinstance(exc, subprocess.TimeoutExpired) else "operation_failed"
                atomic(status_path, {"status": "failed", "error": code, "finished_at": now(), "partial_failure": True})
                if isinstance(exc, Error) and exc.code.startswith("authentication"):
                    atomic(self.area(profile) / "readiness.json", {"authenticated": False, "checked_at": now()})
                raise

    def row(self, profile, book_id):
        if not re.fullmatch(r"[A-Za-z0-9]+", book_id):
            raise Error("invalid_book_id")
        rows = [r for r in self.library(profile)["entries"] if r["book_id"] == book_id]
        if len(rows) != 1:
            raise Error("book_not_found")
        return rows[0]

    def receipt_path(self, profile, book_id):
        return self.area(profile) / "receipts" / (book_id + ".json")

    def operation_path(self, profile, book_id):
        return self.area(profile) / "operations" / (book_id + ".json")

    def audio(self, directory, book_id, fmt):
        directory = safe_tree(directory)
        files = [p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in (".m4b", ".mp3")]
        if len(files) != 1 or files[0].suffix.lower() != "." + fmt or book_id not in files[0].name:
            raise Error("missing_or_ambiguous_audio")
        return files[0]

    def evidence(self, profile, row, directory, allow_no_chapters=False, deep=False):
        path = self.audio(directory, row["book_id"], profile["format"])
        return inspect_audio(path, row, profile["format"], allow_no_chapters, deep, self.timeout)

    def save_receipt(self, profile, row, evidence, started):
        receipt = {"schema_version": 1, "provider": "libation", "account": profile["alias"],
                   "marketplace": profile["marketplace"], "book_id": row["book_id"], "title": row["title"],
                   "engine_version": VERSION, "source_duration_minutes": row.get("duration_minutes"), "started_at": started, "verified_at": now(), **evidence}
        atomic(self.receipt_path(profile, row["book_id"]), receipt)
        atomic(self.operation_path(profile, row["book_id"]), {"status": "verified", "finished_at": now()})
        return receipt

    def receipt_current(self, profile, row):
        receipt = read_json(self.receipt_path(profile, row["book_id"]))
        if not receipt:
            return False
        directory = Path(profile["output"]) / row["book_id"]
        try:
            path = self.audio(directory, row["book_id"], profile["format"])
            return (receipt.get("account") == profile["alias"] and
                    receipt.get("marketplace") == profile["marketplace"] and
                    receipt.get("book_id") == row["book_id"] and receipt.get("path") == str(path) and
                    receipt.get("format") == profile["format"] and
                    receipt.get("source_duration_minutes") == row.get("duration_minutes") and
                    receipt.get("verification", {}).get("success") is True and
                    receipt.get("size") == path.stat().st_size and receipt.get("sha256") == digest(path))
        except Error:
            return False

    def download_one(self, profile, book_id, resume=False, allow_no_chapters=False):
        row = self.row(profile, book_id)
        with self.mutation(profile):
            output = safe_tree(profile["output"])
            final = output / book_id
            if final.exists():
                if self.receipt_current(profile, row):
                    return {"success": True, "book_id": book_id, "status": "already_verified"}
                raise Error("archive_conflict", book_id=book_id)
            if not program("AGENT_FFPROBE_BIN", "ffprobe"):
                raise Error("missing_ffprobe")
            stage = output / ".staging" / book_id
            existing_stage = stage.exists()
            if existing_stage and not resume:
                raise Error("resume_required", book_id=book_id)
            stage = safe_tree(stage, create=True)
            identity = {"account": profile["alias"], "marketplace": profile["marketplace"], "book_id": book_id}
            manifest = read_json(stage / "identity.json")
            if existing_stage and manifest != identity:
                raise Error("archive_conflict")
            atomic(stage / "identity.json", identity)
            started = now()
            atomic(self.operation_path(profile, book_id), {"status": "in_progress", "started_at": started})
            try:
                audio = [p for p in stage.rglob("*") if p.suffix.lower() in (".mp3", ".m4b")]
                if audio:
                    # Recover a completed-but-unreceipted download; never overwrite
                    # invalid/conflicting output just because --resume was supplied.
                    self.evidence(profile, row, stage, allow_no_chapters)
                else:
                    self.native_account(profile)
                    progress = safe_tree(Path(profile["libation_files"]) / "in-progress" / book_id, create=True)
                    overrides = {"Books": str(stage), "InProgress": str(progress),
                                 "FolderTemplate": "<id>", "FileTemplate": "<id>",
                                 "DecryptToLossy": str(profile["format"] == "mp3").lower(),
                                 "SplitFilesByChapter": "false", "OverwriteExisting": "false",
                                 "RetainAaxFile": "false", "AudiobookshelfEnabled": "false",
                                 "StripAudibleBrandAudio": "false"}
                    args = [book_id]
                    for key, value in overrides.items():
                        args.extend(["--override", key + "=" + value])
                    self.run(profile, "liberate", *args)
                    self.evidence(profile, row, stage, allow_no_chapters)
                try:
                    final.mkdir(mode=0o700)
                except FileExistsError:
                    raise Error("archive_conflict")
                os.rename(stage, final / "payload")
                evidence = self.evidence(profile, row, final, allow_no_chapters)
                receipt = self.save_receipt(profile, row, evidence, started)
                return {"success": True, "book_id": book_id, "status": "verified", "receipt": receipt}
            except BaseException as exc:
                code = exc.code if isinstance(exc, Error) else "interrupted" if isinstance(exc, KeyboardInterrupt) else "operation_timeout" if isinstance(exc, subprocess.TimeoutExpired) else "operation_failed"
                status = "interrupted" if isinstance(exc, (KeyboardInterrupt, subprocess.TimeoutExpired)) else "failed"
                if any(p.suffix.lower() in (".mp3", ".m4b") for d in (stage, final) for p in d.rglob("*")):
                    status = "completed_unverified"
                atomic(self.operation_path(profile, book_id), {"status": status, "error": code, "finished_at": now()})
                raise

    def verify(self, profile, book_id, save=False, allow_no_chapters=False, deep=False):
        row = self.row(profile, book_id)
        if save:
            with self.mutation():
                evidence = self.evidence(profile, row, Path(profile["output"]) / book_id, allow_no_chapters, deep)
                return {"success": True, "receipt": self.save_receipt(profile, row, evidence, now())}
        evidence = self.evidence(profile, row, Path(profile["output"]) / book_id, allow_no_chapters, deep)
        return {"success": True, "book_id": book_id, **evidence}

    def state_for(self, profile, row):
        if self.receipt_current(profile, row):
            return "verified"
        if (Path(profile["output"]) / row["book_id"]).exists():
            return "unverifiable"
        op = read_json(self.operation_path(profile, row["book_id"]), {})
        return op.get("status", "missing") if op.get("status") != "verified" else "missing"

    def snapshot(self, profile):
        cache = self.library(profile)
        entries = [{"account": profile["alias"], "marketplace": profile["marketplace"], **row,
                    "archive_state": self.state_for(profile, row)} for row in cache["entries"]]
        sync = read_json(self.area(profile) / "sync.json", {})
        return {"success": True, "source": "local_cache", "synced_at": cache["synced_at"],
                "last_sync": sync, "freshness": "last_successful_sync",
                "partial_failure": sync.get("status") != "complete", "total": len(entries), "entries": entries}

    def reconcile(self, profile):
        snapshot = self.snapshot(profile)
        entries = [row for row in snapshot["entries"] if row["archive_state"] != "verified"]
        return {"success": True, "total": len(entries), "entries": entries,
                "partial_failure": snapshot["partial_failure"], "last_sync": snapshot["last_sync"]}
