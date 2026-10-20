from pathlib import Path
from devsnap.crypto.age_engine import decrypt_file, encrypt_file
from devsnap.crypto.ssh_keys import find_default_identities, resolve_identity_path
from devsnap.scanner.git_info import read_recipients_file, save_recipients_file


def test_encryption_decryption_roundtrip(tmp_path: Path):
    plain_file = tmp_path / "secret.env"
    enc_file = tmp_path / "secret.env.age"
    dec_file = tmp_path / "restored.env"

    content = b"SECRET_API_KEY=sk_test_123456789\nDATABASE_PASSWORD=supersecret\n"
    plain_file.write_bytes(content)

    recipients = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI123456 test@user"]
    encrypt_file(plain_file, enc_file, recipients=recipients)
    assert enc_file.is_file()
    assert enc_file.read_bytes() != content

    decrypt_file(enc_file, dec_file)
    assert dec_file.is_file()
    assert dec_file.read_bytes() == content


def test_recipients_file_io(tmp_path: Path):
    rec_file = tmp_path / "recipients.txt"
    keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI111 user1",
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ222 user2",
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI111 user1", # duplicate
    ]
    save_recipients_file(keys, rec_file)
    read_back = read_recipients_file(rec_file)
    assert len(read_back) == 2
    assert "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI111 user1" in read_back


def test_resolve_identity(tmp_path: Path):
    fake_key = tmp_path / "id_ed25519"
    fake_key.write_text("FAKE_PRIVATE_KEY", encoding="utf-8")

    resolved = resolve_identity_path(str(fake_key))
    assert resolved == fake_key
