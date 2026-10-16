"""Fixed, recognisable email/SMS texts (§8.3: no free-form bodies, no persona content).

Adapters that send rendered text (dev mailbox, plain SMTP-style providers) use
``render``; providers with server-side templates map the template id instead.
Links, when added, must point only to our own domain.
"""

from dataclasses import dataclass

from app.providers.base import MessageTemplate, OutboundMessage


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    subject: str
    body: str


_TEXTS: dict[str, dict[MessageTemplate, tuple[str, str]]] = {
    "tr": {
        "signup_code": (
            "EVA hesap doğrulama kodun: {code}",
            "EVA'ya hoş geldin!\n\nHesabını oluşturmak için bu kodu gir: {code}\n\n"
            "Kod 10 dakika geçerli. Bu isteği sen yapmadıysan bu e-postayı yok say.",
        ),
        "login_code": (
            "EVA giriş kodun: {code}",
            "EVA'ya giriş yapmak için bu kodu gir: {code}\n\n"
            "Kod 10 dakika geçerli. Giriş yapmaya çalışan sen değilsen şifreni hemen değiştir.",
        ),
        "password_reset_code": (
            "EVA şifre sıfırlama kodun: {code}",
            "Şifreni sıfırlamak için bu kodu gir: {code}\n\n"
            "Kod 10 dakika geçerli. Bu isteği sen yapmadıysan bu e-postayı yok say; "
            "şifren değişmez.",
        ),
        "account_exists": (
            "EVA hesabın zaten var",
            "Bu e-posta adresiyle yeni bir EVA hesabı açılmak istendi, ama zaten bir hesabın "
            "var. Giriş yapabilir ya da şifreni unuttuysan 'Şifremi unuttum' ile "
            "sıfırlayabilirsin.\n\nBu isteği sen yapmadıysan bu e-postayı yok say.",
        ),
        "password_changed": (
            "EVA şifren değiştirildi",
            "EVA şifren az önce değiştirildi ve tüm cihazlardaki oturumların kapatıldı.\n\n"
            "Bunu sen yapmadıysan hemen 'Şifremi unuttum' ile şifreni yeniden belirle.",
        ),
    },
    "en": {
        "signup_code": (
            "Your EVA verification code: {code}",
            "Welcome to EVA!\n\nEnter this code to create your account: {code}\n\n"
            "The code is valid for 10 minutes. If you did not ask for this, ignore this email.",
        ),
        "login_code": (
            "Your EVA sign-in code: {code}",
            "Enter this code to sign in to EVA: {code}\n\n"
            "The code is valid for 10 minutes. If this wasn't you, change your password now.",
        ),
        "password_reset_code": (
            "Your EVA password reset code: {code}",
            "Enter this code to reset your password: {code}\n\n"
            "The code is valid for 10 minutes. If you did not ask for this, ignore this "
            "email; your password stays the same.",
        ),
        "account_exists": (
            "You already have an EVA account",
            "Someone tried to create a new EVA account with this email, but you already "
            "have one. Sign in, or use 'Forgot password' to reset it.\n\n"
            "If this wasn't you, ignore this email.",
        ),
        "password_changed": (
            "Your EVA password was changed",
            "Your EVA password was just changed and you were signed out everywhere.\n\n"
            "If this wasn't you, reset your password now with 'Forgot password'.",
        ),
    },
}


def render(message: OutboundMessage) -> RenderedMessage:
    texts = _TEXTS.get(message.locale) or _TEXTS["tr"]
    try:
        subject, body = texts[message.template]
    except KeyError as exc:
        raise ValueError(f"no text for template {message.template!r}") from exc
    params = dict(message.params)
    return RenderedMessage(subject.format(**params), body.format(**params))
