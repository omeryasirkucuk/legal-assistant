from legal_api.privacy.credentials import decrypt_credential, encrypt_credential


def test_provider_key_is_encrypted_and_round_trips():
    value = "openwebui-test-token"
    encrypted = encrypt_credential(value)
    assert value not in encrypted
    assert decrypt_credential(encrypted) == value
