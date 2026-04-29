#!/usr/bin/env python3
"""Safe send/compose helper for agent-email."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import smtplib
import subprocess
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        path = Path(args.body_file).expanduser()
        if not path.is_file():
            fail(f"body file not found: {path}")
        return path.read_text(encoding="utf-8")
    return args.body or "(No body)"


def add_attachment(msg: MIMEMultipart, path_text: str) -> None:
    path = Path(path_text).expanduser()
    if not path.is_file():
        fail(f"attachment not found: {path}")
    with path.open("rb") as fh:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(fh.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
    msg.attach(part)


def split_recipients(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def send_smtp(args: argparse.Namespace, body: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    email_from = args.from_override or os.environ.get("EMAIL_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        fail("SMTP_USER and SMTP_PASS required")
    if not email_from:
        fail("EMAIL_FROM or SMTP_USER required")

    msg = MIMEMultipart()
    msg["From"] = email_from
    msg["To"] = args.to
    msg["Subject"] = args.subject
    if args.cc:
        msg["Cc"] = args.cc
    if args.bcc:
        msg["Bcc"] = args.bcc
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if args.attach:
        add_attachment(msg, args.attach)

    recipients = [args.to]
    recipients.extend(split_recipients(args.cc or ""))
    recipients.extend(split_recipients(args.bcc or ""))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if os.environ.get("SMTP_STARTTLS", "1") not in {"0", "false", "False"}:
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, recipients, msg.as_string())
        print(f"Email sent to {args.to}")
    except Exception as exc:
        fail(str(exc))


def send_mail_command(args: argparse.Namespace, body: str) -> None:
    if args.cc or args.bcc or args.from_override:
        fail("--cc, --bcc, and --from require smtp or macos send methods")
    mail_bin = shutil.which("mail")
    if not mail_bin:
        fail("mail command not found")
    proc = subprocess.run([mail_bin, "-s", args.subject, args.to], input=body, text=True, check=False)
    if proc.returncode != 0:
        fail(f"mail command failed with exit code {proc.returncode}")
    print(f"Email sent to {args.to}")


def compose_macos(args: argparse.Namespace, body: str) -> None:
    script = r'''
on run argv
    set toAddress to item 1 of argv
    set messageSubject to item 2 of argv
    set messageBody to item 3 of argv
    set ccAddress to item 4 of argv
    set bccAddress to item 5 of argv
    set senderAddress to item 6 of argv

    tell application "Mail"
        set newMessage to make new outgoing message with properties {subject:messageSubject, content:messageBody, visible:true}
        if senderAddress is not "" then set sender of newMessage to senderAddress
        tell newMessage
            make new to recipient with properties {address:toAddress}
            if ccAddress is not "" then make new cc recipient with properties {address:ccAddress}
            if bccAddress is not "" then make new bcc recipient with properties {address:bccAddress}
        end tell
        activate
    end tell
end run
'''
    proc = subprocess.run(
        ["osascript", "-", args.to, args.subject, body, args.cc or "", args.bcc or "", args.from_override or ""],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        fail(proc.stderr.strip() or proc.stdout.strip() or "Mail.app compose failed")
    print("Email composed in Mail.app")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send or compose email")
    parser.add_argument("to")
    parser.add_argument("subject")
    parser.add_argument("body_positional", nargs="?")
    parser.add_argument("--body", "-b")
    parser.add_argument("--file", "-f", dest="body_file")
    parser.add_argument("--attach", "-a")
    parser.add_argument("--cc")
    parser.add_argument("--bcc")
    parser.add_argument("--from", dest="from_override")
    parser.add_argument("--method", choices=["auto", "smtp", "python", "mail", "macos", "app"], default="auto")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.body is None and args.body_positional is not None:
        args.body = args.body_positional
    body = read_body(args)

    method = args.method
    if method == "auto":
        if os.environ.get("SMTP_USER"):
            method = "smtp"
        elif platform.system() == "Darwin":
            method = "macos"
        else:
            method = "mail"

    if method in {"smtp", "python"}:
        send_smtp(args, body)
    elif method == "mail":
        send_mail_command(args, body)
    elif method in {"macos", "app"}:
        compose_macos(args, body)
    else:
        fail(f"unknown send method: {args.method}")


if __name__ == "__main__":
    main()
