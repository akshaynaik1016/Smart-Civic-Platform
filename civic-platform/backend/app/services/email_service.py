"""
EmailService — async SMTP email delivery with Jinja2 HTML templates.

Handles:
  • OTP delivery (registration, password reset, phone verification)
  • Welcome email after account activation
  • Complaint status change notifications
  • Officer assignment notifications

The service gracefully degrades: if SMTP is not configured, it logs
the email content instead of failing — useful in development.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from jinja2 import Environment, PackageLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)


# ─── Jinja2 environment ───────────────────────────────────────────────────────

_INLINE_TEMPLATES: dict[str, str] = {

    "otp_verify": """
<!DOCTYPE html><html><body style="font-family:Inter,sans-serif;background:#f0f4f8;margin:0;padding:32px">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;box-shadow:0 2px 12px rgba(0,0,0,.07)">
  <div style="text-align:center;margin-bottom:24px">
    <div style="width:48px;height:48px;background:#1565c0;border-radius:12px;display:inline-flex;align-items:center;justify-content:center">
      <span style="color:#fff;font-size:24px">🏙️</span>
    </div>
    <h2 style="color:#0d1b2a;margin:12px 0 4px">Smart Civic</h2>
    <p style="color:#64748b;margin:0;font-size:13px">Verify your email address</p>
  </div>
  <p style="color:#334155;line-height:1.6">Hi {{ name }},</p>
  <p style="color:#334155;line-height:1.6">
    Use the one-time password below to verify your email address.
    This code is valid for <strong>5 minutes</strong>.
  </p>
  <div style="background:#eff6ff;border:2px solid #bfdbfe;border-radius:12px;padding:20px;text-align:center;margin:24px 0">
    <p style="margin:0;font-size:36px;font-weight:700;letter-spacing:8px;color:#1d4ed8;font-family:monospace">
      {{ otp }}
    </p>
  </div>
  <p style="color:#94a3b8;font-size:12px;line-height:1.6">
    If you did not request this, please ignore this email. Your account remains secure.
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
  <p style="color:#94a3b8;font-size:11px;text-align:center;margin:0">
    © {{ year }} Smart Civic Intelligence Platform · {{ city }} Municipal Corporation
  </p>
</div>
</body></html>""",

    "otp_reset": """
<!DOCTYPE html><html><body style="font-family:Inter,sans-serif;background:#f0f4f8;margin:0;padding:32px">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:32px">
  <h2 style="color:#0d1b2a">Password Reset</h2>
  <p style="color:#334155">Hi {{ name }}, use this code to reset your password:</p>
  <div style="background:#fef2f2;border:2px solid #fecaca;border-radius:12px;padding:20px;text-align:center;margin:24px 0">
    <p style="margin:0;font-size:36px;font-weight:700;letter-spacing:8px;color:#dc2626;font-family:monospace">{{ otp }}</p>
  </div>
  <p style="color:#94a3b8;font-size:12px">Valid for 10 minutes. If you didn't request this, ignore this email.</p>
</div></body></html>""",

    "welcome": """
<!DOCTYPE html><html><body style="font-family:Inter,sans-serif;background:#f0f4f8;margin:0;padding:32px">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:32px">
  <h2 style="color:#0d1b2a">Welcome to Smart Civic! 🎉</h2>
  <p style="color:#334155;line-height:1.6">
    Hi {{ name }}, your account is now active. Start reporting civic issues in
    <strong>{{ city }}</strong> and help build a better city.
  </p>
  <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:16px;margin:24px 0">
    <p style="margin:0;color:#15803d;font-size:13px">✅ Email verified · Ready to report issues</p>
  </div>
  <p style="color:#94a3b8;font-size:11px">© {{ year }} Smart Civic Intelligence Platform</p>
</div></body></html>""",

    "status_update": """
<!DOCTYPE html><html><body style="font-family:Inter,sans-serif;background:#f0f4f8;margin:0;padding:32px">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:32px">
  <h2 style="color:#0d1b2a">Complaint Update 📋</h2>
  <p style="color:#334155">Hi {{ name }}, your complaint has been updated.</p>
  <div style="background:#eff6ff;border-radius:12px;padding:16px;margin:16px 0">
    <p style="margin:0 0 8px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.05em">Complaint</p>
    <p style="margin:0;font-weight:600;color:#0d1b2a">{{ complaint_number }} — {{ title }}</p>
  </div>
  <div style="display:flex;gap:12px;margin:16px 0">
    <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px;text-align:center">
      <p style="margin:0;font-size:11px;color:#64748b">Previous</p>
      <p style="margin:4px 0 0;font-weight:600;color:#475569">{{ old_status }}</p>
    </div>
    <div style="width:24px;text-align:center;line-height:48px;color:#94a3b8">→</div>
    <div style="flex:1;background:#{{ status_color }};border-radius:8px;padding:12px;text-align:center">
      <p style="margin:0;font-size:11px;color:#64748b">New Status</p>
      <p style="margin:4px 0 0;font-weight:600;color:#0d1b2a">{{ new_status }}</p>
    </div>
  </div>
  {% if notes %}<p style="color:#475569;font-size:13px;background:#f8fafc;padding:12px;border-radius:8px">{{ notes }}</p>{% endif %}
  <p style="color:#94a3b8;font-size:11px">© {{ year }} Smart Civic</p>
</div></body></html>""",
}


def _render(template_name: str, **ctx) -> str:
    template = _INLINE_TEMPLATES.get(template_name, "")
    # Minimal Jinja2-style substitution using actual Jinja2
    from jinja2 import Template
    return Template(template).render(year=datetime.now().year, **ctx)


class EmailService:
    """Async-friendly email service (uses smtplib in a thread pool)."""

    def __init__(self) -> None:
        self._host     = settings.SMTP_HOST
        self._port     = settings.SMTP_PORT
        self._user     = settings.SMTP_USER
        self._password = settings.SMTP_PASSWORD
        self._from     = settings.EMAIL_FROM
        self._enabled  = bool(settings.SMTP_USER and settings.SMTP_PASSWORD)

    # ── Public send methods ───────────────────────────────────────────────────

    async def send_otp_email(
        self,
        to_email: str,
        name: str,
        otp: str,
        purpose: str = "verify",
        city: str = "Hubballi",
    ) -> bool:
        """Send an OTP verification / reset email."""
        template = "otp_reset" if purpose == "reset" else "otp_verify"
        subject  = {
            "verify": "Verify your Smart Civic account",
            "reset":  "Smart Civic — Password Reset OTP",
            "phone":  "Smart Civic — Phone Verification OTP",
        }.get(purpose, "Smart Civic — OTP")

        html = _render(template, name=name, otp=otp, city=city)
        return await self._send(to_email, subject, html)

    async def send_welcome_email(
        self,
        to_email: str,
        name: str,
        city: str = "Hubballi",
    ) -> bool:
        html = _render("welcome", name=name, city=city)
        return await self._send(to_email, "Welcome to Smart Civic!", html)

    async def send_status_update_email(
        self,
        to_email: str,
        name: str,
        complaint_number: str,
        title: str,
        old_status: str,
        new_status: str,
        notes: Optional[str] = None,
    ) -> bool:
        status_colors = {
            "resolved":   "f0fdf4",
            "in_progress":"fffbeb",
            "assigned":   "f5f3ff",
            "rejected":   "fef2f2",
        }
        html = _render(
            "status_update",
            name=name,
            complaint_number=complaint_number,
            title=title,
            old_status=old_status.replace("_", " ").title(),
            new_status=new_status.replace("_", " ").title(),
            status_color=status_colors.get(new_status, "f1f5f9"),
            notes=notes,
        )
        return await self._send(
            to_email,
            f"[{complaint_number}] Status updated: {new_status.replace('_',' ').title()}",
            html,
        )

    # ── Core send ─────────────────────────────────────────────────────────────

    async def _send(self, to: str, subject: str, html: str) -> bool:
        if not self._enabled:
            logger.info(
                "SMTP not configured — email suppressed",
                extra={"to": to, "subject": subject},
            )
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self._from
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_sync, to, msg.as_string())
            logger.info("Email sent", extra={"to": to, "subject": subject})
            return True
        except Exception as exc:
            logger.error("Email send failed", extra={"to": to, "error": str(exc)})
            return False

    def _send_sync(self, to: str, raw: str) -> None:
        context = ssl.create_default_context()
        with smtplib.SMTP(self._host, self._port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(self._user, self._password)
            server.sendmail(self._from, [to], raw)


# Singleton used by background tasks and endpoints
email_service = EmailService()
