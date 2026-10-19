"""Sabit, tanınır e-posta/SMS metinleri (§8.3: serbest metin yok, persona içeriği yok).

Hazır metin gönderen adaptörler (dev mailbox, düz SMTP tarzı sağlayıcılar) ``render``'ı
kullanır; şablonları kendi sunucusunda tutan sağlayıcılar ise şablon id'sini eşler.
Link eklenirse yalnızca kendi alan adımıza gitmeli.
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
        "step_up_code": (
            "EVA onay kodun: {code}",
            "Hassas bir işlem için kimliğini doğrulaman istendi (ör. ses ya da yüz kaydı). "
            "Onaylamak için bu kodu gir: {code}\n\n"
            "Kod 10 dakika geçerli. Bunu sen yapmadıysan şifreni hemen değiştir.",
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
        "legacy_key_delivery": (
            "{owner_name} seninle EVA'da bir Miras paylaştı",
            "{owner_name}, EVA'daki dijital Miras'ını seninle paylaştı.\n\n"
            "Miras anahtarın: {key}\n\n"
            "Açmak için EVA'ya kendi hesabınla gir ve anahtarı şu sayfada yaz: {link}\n"
            "Ardından bu e-posta adresine bir doğrulama kodu gelecek.\n\n"
            "Anahtar tek kullanımlık ve {expires_on} tarihine kadar geçerli. Kimseyle paylaşma. "
            "EVA senden asla şifre, kart bilgisi ya da para istemez.\n\n"
            "Bu e-postayı beklemiyorsan yok say.",
        ),
        "legacy_redeem_code": (
            "EVA Miras doğrulama kodun: {code}",
            "Miras'ı açmak için bu kodu gir: {code}\n\n"
            "Kod 10 dakika geçerli. Bunu sen yapmadıysan kodu kimseyle paylaşma ve bu "
            "e-postayı yok say.",
        ),
        "legacy_posthumous_warning": (
            "EVA: Miras'ın açılmak üzere",
            "Bir süredir EVA'ya girmedin ya da bir yakının vefatını bildirdi. Belirlediğin "
            "kişilere vefat sonrası Miras anahtarları {days_left} gün içinde otomatik "
            "gönderilecek.\n\n"
            "Sen buradaysan EVA'ya bir kez giriş yapman yeterli; süreç hemen durur: {link}\n\n"
            "Bu e-postayı yakınların da görüyorsa: bu uyarı Miras'ın sahibine gönderilir.",
        ),
        "legacy_posthumous_delivery": (
            "{owner_name} sana EVA'da bir Miras bıraktı",
            "{owner_name}, vefatından sonra EVA'daki dijital Miras'ının sana ulaşmasını "
            "istemişti. Başın sağ olsun.\n\n"
            "Miras anahtarın: {key}\n\n"
            "Açmak için EVA'ya kendi hesabınla gir ve anahtarı şu sayfada yaz: {link}\n"
            "Ardından bu e-posta adresine bir doğrulama kodu gelecek.\n\n"
            "Anahtar tek kullanımlık ve {expires_on} tarihine kadar geçerli. Kimseyle paylaşma. "
            "EVA senden asla şifre, kart bilgisi ya da para istemez.",
        ),
        "legacy_delete_code": (
            "EVA Miras silme onay kodun: {code}",
            "Bir Miras'ı kendi listenden silmek istedin. Onaylamak için bu kodu gir: {code}\n\n"
            "Kod 10 dakika geçerli. Bunu sen yapmadıysan bu e-postayı yok say.",
        ),
        "legacy_key_used": (
            "Miras anahtarın kullanıldı",
            "{recipient_email} adresine gönderdiğin Miras anahtarı az önce kullanıldı; "
            "bu kişi artık Miras'ınla konuşabiliyor.\n\n"
            "Bunu beklemiyorsan EVA'da Miras ekranından erişimi hemen kapatabilirsin.",
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
        "step_up_code": (
            "Your EVA confirmation code: {code}",
            "You were asked to confirm it's you for a sensitive action (such as voice or face "
            "enrollment). Enter this code to confirm: {code}\n\n"
            "The code is valid for 10 minutes. If this wasn't you, change your password now.",
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
        "legacy_key_delivery": (
            "{owner_name} shared an EVA Legacy with you",
            "{owner_name} shared their digital Legacy on EVA with you.\n\n"
            "Your Legacy key: {key}\n\n"
            "To open it, sign in to EVA with your own account and enter the key here: {link}\n"
            "We will then send a verification code to this email address.\n\n"
            "The key works once and is valid until {expires_on}. Don't share it with anyone. "
            "EVA never asks you for passwords, card details or money.\n\n"
            "If you weren't expecting this email, ignore it.",
        ),
        "legacy_redeem_code": (
            "Your EVA Legacy verification code: {code}",
            "Enter this code to open the Legacy: {code}\n\n"
            "The code is valid for 10 minutes. If this wasn't you, don't share the code and "
            "ignore this email.",
        ),
        "legacy_posthumous_warning": (
            "EVA: your Legacy is about to open",
            "You haven't signed in to EVA for a while, or someone close reported your death. "
            "Your posthumous Legacy keys will be sent automatically to the people you chose in "
            "{days_left} days.\n\n"
            "If you are here, just sign in to EVA once and the process stops right away: {link}",
        ),
        "legacy_posthumous_delivery": (
            "{owner_name} left you a Legacy on EVA",
            "{owner_name} wanted their digital Legacy on EVA to reach you after their death. "
            "We are sorry for your loss.\n\n"
            "Your Legacy key: {key}\n\n"
            "To open it, sign in to EVA with your own account and enter the key here: {link}\n"
            "We will then send a verification code to this email address.\n\n"
            "The key works once and is valid until {expires_on}. Don't share it with anyone. "
            "EVA never asks you for passwords, card details or money.",
        ),
        "legacy_delete_code": (
            "Your EVA Legacy deletion code: {code}",
            "You asked to remove a Legacy from your list. Enter this code to confirm: {code}\n\n"
            "The code is valid for 10 minutes. If this wasn't you, ignore this email.",
        ),
        "legacy_key_used": (
            "Your Legacy key was used",
            "The Legacy key you sent to {recipient_email} was just used; this person can now "
            "talk to your Legacy.\n\n"
            "If you didn't expect this, you can close their access right away from the Legacy "
            "screen in EVA.",
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
