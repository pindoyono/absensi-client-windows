"""Tests for app/validation.py (REQ-SEC-004)."""
import pytest
from app.validation import (
    validate_nis,
    validate_nama,
    validate_kelas,
    validate_tanggal,
    validate_device_id,
    validate_api_key,
    validate_timestamp,
    validate_signature,
    validate_record_size,
    sanitize_string,
    ValidationError,
)


class TestValidateNIS:
    def test_valid_nis(self):
        assert validate_nis("1234567") == "1234567"
        assert validate_nis("123456789012345") == "123456789012345"

    def test_invalid_nis_too_short(self):
        with pytest.raises(ValidationError):
            validate_nis("123456")

    def test_invalid_nis_too_long(self):
        with pytest.raises(ValidationError):
            validate_nis("1234567890123456")

    def test_invalid_nis_letters(self):
        with pytest.raises(ValidationError):
            validate_nis("123456a")

    def test_invalid_nis_empty(self):
        with pytest.raises(ValidationError):
            validate_nis("")


class TestValidateNama:
    def test_valid_nama(self):
        assert validate_nama("Budi Santoso") == "Budi Santoso"
        assert validate_nama("Siti Aisyah") == "Siti Aisyah"
        assert validate_nama("O'Connor") == "O'Connor"
        assert validate_nama("Jean-Pierre") == "Jean-Pierre"

    def test_invalid_nama_empty(self):
        with pytest.raises(ValidationError):
            validate_nama("")

    def test_invalid_nama_too_long(self):
        with pytest.raises(ValidationError):
            validate_nama("A" * 101)

    def test_invalid_nama_special_chars(self):
        with pytest.raises(ValidationError):
            validate_nama("Budi@Santoso")

    def test_invalid_nama_numbers(self):
        with pytest.raises(ValidationError):
            validate_nama("Budi123")


class TestValidateKelas:
    def test_valid_kelas(self):
        assert validate_kelas("XI") == "XI"
        assert validate_kelas("XII") == "XII"
        assert validate_kelas("X") == "X"

    def test_invalid_kelas_empty(self):
        with pytest.raises(ValidationError):
            validate_kelas("")

    def test_invalid_kelas_format(self):
        with pytest.raises(ValidationError):
            validate_kelas("XI@")


class TestValidateTanggal:
    def test_valid_tanggal(self):
        assert validate_tanggal("2025-01-15") == "2025-01-15"
        assert validate_tanggal("2024-12-31") == "2024-12-31"

    def test_invalid_tanggal_format(self):
        with pytest.raises(ValidationError):
            validate_tanggal("15-01-2025")

    def test_invalid_tanggal_invalid_date(self):
        with pytest.raises(ValidationError):
            validate_tanggal("2025-02-30")


class TestValidateDeviceId:
    def test_valid_device_id(self):
        assert validate_device_id("DEVICE_001") == "DEVICE_001"
        assert validate_device_id("device-01") == "device-01"

    def test_invalid_device_id_empty(self):
        with pytest.raises(ValidationError):
            validate_device_id("")

    def test_invalid_device_id_special_chars(self):
        with pytest.raises(ValidationError):
            validate_device_id("DEVICE@001")


class TestValidateApiKey:
    def test_valid_api_key(self):
        key = "a" * 32
        assert validate_api_key(key) == key

    def test_invalid_api_key_too_short(self):
        with pytest.raises(ValidationError):
            validate_api_key("a" * 31)

    def test_invalid_api_key_too_long(self):
        with pytest.raises(ValidationError):
            validate_api_key("a" * 129)


class TestValidateTimestamp:
    def test_valid_timestamp(self):
        assert validate_timestamp("1700000000") == "1700000000"

    def test_invalid_timestamp_not_digits(self):
        with pytest.raises(ValidationError):
            validate_timestamp("abc")

    def test_invalid_timestamp_wrong_length(self):
        with pytest.raises(ValidationError):
            validate_timestamp("170000000")


class TestValidateSignature:
    def test_valid_signature(self):
        sig = "a" * 64
        assert validate_signature(sig) == sig

    def test_invalid_signature_wrong_length(self):
        with pytest.raises(ValidationError):
            validate_signature("a" * 63)

    def test_invalid_signature_not_hex(self):
        with pytest.raises(ValidationError):
            validate_signature("g" * 64)


class TestValidateRecordSize:
    def test_valid_size(self):
        data = b"x" * 1000
        assert validate_record_size(data) == data

    def test_invalid_size_too_large(self):
        data = b"x" * 10001
        with pytest.raises(ValidationError):
            validate_record_size(data)


class TestSanitizeString:
    def test_sanitize_normal(self):
        assert sanitize_string("hello world") == "hello world"

    def test_sanitize_removes_control_chars(self):
        assert sanitize_string("hello\x00world") == "helloworld"

    def test_sanitize_truncates(self):
        assert len(sanitize_string("a" * 300, max_length=100)) == 100

    def test_sanitize_none(self):
        assert sanitize_string(None) == ""

    def test_sanitize_non_string(self):
        assert sanitize_string(123) == "123"