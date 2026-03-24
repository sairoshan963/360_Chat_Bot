import logging

from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Shared HTML wrapper ──────────────────────────────────────────────────────

def _html_wrap(title, preheader, body_html):
    """Wrap content in a branded Gamyam email template."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;color:#f4f6fb;">{preheader}</div>

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb;padding:40px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);padding:32px 40px;text-align:center;">
            <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
              <tr>
                <td style="padding-right:12px;">
                  <div style="width:40px;height:40px;background:#FF6B1A;border-radius:8px;display:inline-block;line-height:40px;text-align:center;font-size:20px;font-weight:800;color:#fff;">G</div>
                </td>
                <td>
                  <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">Gamyam</span>
                  <span style="font-size:13px;color:#94a3b8;display:block;margin-top:2px;letter-spacing:1px;text-transform:uppercase;">360° Feedback</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:40px 40px 32px;">
            {body_html}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:24px 40px;border-top:1px solid #e2e8f0;text-align:center;">
            <p style="margin:0;font-size:12px;color:#94a3b8;line-height:1.6;">
              This email was sent by <strong style="color:#64748b;">Gamyam 360° Feedback</strong><br/>
              If you did not expect this email, you can safely ignore it.<br/>
              © {__import__('datetime').date.today().year} Gamyam. All rights reserved.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _send(subject, to_email, plain_text, html):
    """Send email with both plain text and HTML alternatives."""
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error('Email send failed to %s (subject: %s): %s', to_email, subject, exc, exc_info=True)
        return False


# ─── Password Reset ───────────────────────────────────────────────────────────

def send_password_reset(to_email, first_name, reset_link):
    subject    = 'Reset your Gamyam 360° Feedback password'
    plain_text = (
        f'Hi {first_name},\n\n'
        f'Click the link below to reset your password:\n{reset_link}\n\n'
        f'This link expires in 1 hour.\n\n'
        f'If you did not request this, ignore this email.'
    )
    body_html = f"""
      <h2 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#0f172a;">Reset your password</h2>
      <p style="margin:0 0 24px;font-size:15px;color:#64748b;line-height:1.6;">
        Hi <strong>{first_name}</strong>, we received a request to reset your password.
        Click the button below to set a new one.
      </p>

      <div style="text-align:center;margin:32px 0;">
        <a href="{reset_link}"
           style="display:inline-block;background:#FF6B1A;color:#ffffff;font-size:16px;font-weight:700;
                  text-decoration:none;padding:14px 40px;border-radius:8px;
                  box-shadow:0 4px 16px rgba(255,107,26,0.35);">
          Reset Password
        </a>
      </div>

      <p style="margin:24px 0 0;font-size:13px;color:#94a3b8;line-height:1.6;text-align:center;">
        This link expires in <strong style="color:#64748b;">1 hour</strong>.<br/>
        If the button doesn't work, copy this link:<br/>
        <a href="{reset_link}" style="color:#FF6B1A;word-break:break-all;">{reset_link}</a>
      </p>

      <div style="margin:28px 0 0;padding:16px;background:#fef3ec;border-left:4px solid #FF6B1A;border-radius:4px;">
        <p style="margin:0;font-size:13px;color:#92400e;">
          🔒 If you did not request a password reset, please ignore this email. Your account remains secure.
        </p>
      </div>
    """
    return _send(subject, to_email, plain_text, _html_wrap('Reset Password', 'Reset your Gamyam 360° password', body_html))


# ─── Admin-triggered password reset for a user ───────────────────────────────

def send_admin_password_reset(to_email, first_name, reset_link, admin_name):
    subject    = 'Your Gamyam 360° Feedback password has been reset'
    plain_text = (
        f'Hi {first_name},\n\n'
        f'An administrator ({admin_name}) has initiated a password reset for your account.\n'
        f'Click the link below to set a new password:\n{reset_link}\n\n'
        f'This link expires in 1 hour.\n\n'
        f'If this was unexpected, contact your HR administrator.'
    )
    body_html = f"""
      <h2 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#0f172a;">Password Reset Initiated</h2>
      <p style="margin:0 0 24px;font-size:15px;color:#64748b;line-height:1.6;">
        Hi <strong>{first_name}</strong>,<br/><br/>
        An administrator (<strong>{admin_name}</strong>) has initiated a password reset for your account.
        Click the button below to set a new password.
      </p>

      <div style="text-align:center;margin:32px 0;">
        <a href="{reset_link}"
           style="display:inline-block;background:#FF6B1A;color:#ffffff;font-size:16px;font-weight:700;
                  text-decoration:none;padding:14px 40px;border-radius:8px;
                  box-shadow:0 4px 16px rgba(255,107,26,0.35);">
          Set New Password
        </a>
      </div>

      <p style="margin:24px 0 0;font-size:13px;color:#94a3b8;line-height:1.6;text-align:center;">
        This link expires in <strong style="color:#64748b;">1 hour</strong>.
      </p>

      <div style="margin:28px 0 0;padding:16px;background:#fef3ec;border-left:4px solid #FF6B1A;border-radius:4px;">
        <p style="margin:0;font-size:13px;color:#92400e;">
          If you did not expect this, contact your HR administrator immediately.
        </p>
      </div>
    """
    return _send(subject, to_email, plain_text, _html_wrap('Password Reset', 'Your password reset was initiated by an admin', body_html))


# ─── Reminder ─────────────────────────────────────────────────────────────────

def send_reminder(to_email, first_name, cycle_name, deadline_str):
    subject    = f'Reminder: Pending feedback for "{cycle_name}"'
    tasks_link = f'{settings.FRONTEND_URL}/employee/tasks'
    plain_text = (
        f'Hi {first_name},\n\n'
        f'You have pending feedback tasks in the review cycle "{cycle_name}".\n'
        f'Deadline: {deadline_str}\n\n'
        f'Please complete your feedback at your earliest.\n\n'
        f'Log in: {tasks_link}'
    )
    body_html = f"""
      <h2 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#0f172a;">Pending Feedback Reminder</h2>
      <p style="margin:0 0 24px;font-size:15px;color:#64748b;line-height:1.6;">
        Hi <strong>{first_name}</strong>, you have pending feedback tasks that need your attention.
      </p>

      <div style="background:#f8fafc;border-radius:8px;padding:20px 24px;margin-bottom:24px;">
        <p style="margin:0 0 8px;font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Review Cycle</p>
        <p style="margin:0;font-size:18px;font-weight:700;color:#0f172a;">{cycle_name}</p>
        <p style="margin:8px 0 0;font-size:13px;color:#ef4444;">⏰ Deadline: <strong>{deadline_str}</strong></p>
      </div>

      <div style="text-align:center;margin:32px 0;">
        <a href="{tasks_link}"
           style="display:inline-block;background:#FF6B1A;color:#ffffff;font-size:16px;font-weight:700;
                  text-decoration:none;padding:14px 40px;border-radius:8px;
                  box-shadow:0 4px 16px rgba(255,107,26,0.35);">
          Complete My Tasks
        </a>
      </div>
    """
    return _send(subject, to_email, plain_text, _html_wrap('Feedback Reminder', f'Pending feedback for {cycle_name}', body_html))


# ─── Cycle Notification ───────────────────────────────────────────────────────

def send_cycle_notification(to_email, first_name, subject, body):
    plain_text = f'Hi {first_name},\n\n{body}'
    body_html  = f"""
      <h2 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#0f172a;">{subject}</h2>
      <p style="margin:0 0 24px;font-size:15px;color:#64748b;line-height:1.6;">
        Hi <strong>{first_name}</strong>,
      </p>
      <p style="margin:0;font-size:15px;color:#374151;line-height:1.7;">{body}</p>

      <div style="text-align:center;margin:32px 0;">
        <a href="{settings.FRONTEND_URL}"
           style="display:inline-block;background:#FF6B1A;color:#ffffff;font-size:15px;font-weight:700;
                  text-decoration:none;padding:12px 32px;border-radius:8px;">
          Open Gamyam 360°
        </a>
      </div>
    """
    return _send(subject, to_email, plain_text, _html_wrap(subject, body[:90], body_html))
