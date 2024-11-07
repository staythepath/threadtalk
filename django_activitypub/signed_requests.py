import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, ed25519, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
import requests
import logging
import json

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)



def get_gmt_now() -> str:
    return datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")


def sign_message(private_key, message):
    logging.debug("\n\n########### Starting sign_message ###########")
    
    # Log the first 100 characters of the private key for verification
    logging.debug("Client Private Key (first 100 chars): %s", private_key.decode('utf-8')[:100])
    
    key = load_pem_private_key(private_key, password=None)
    
    # Log the canonical message that will be signed
    logging.debug("Canonical message (signing): %s", repr(message))
    
    # Sign the canonical message
    signature = base64.standard_b64encode(
        key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    ).decode("utf-8")
    
    # Log the generated signature
    logging.debug("Generated signature: %s", signature)
    
    logging.debug("########### Ending sign_message ###########\n\n")
    
    return signature



class HttpSignature:
    def __init__(self):
        self.fields = []

    def build_signature(self, key_id, private_key):
        message = self.build_message()

        signature_string = sign_message(private_key, message)
        headers = " ".join(name for name, _ in self.fields)

        signature_parts = [
            f'keyId="{key_id}"',
            'algorithm="rsa-sha256"',
            f'headers="{headers}"',
            f'signature="{signature_string}"',
        ]

        return ",".join(signature_parts)

    def build_message(self):
        return "\n".join(f"{name}: {value}" for name, value in self.fields)

    def with_field(self, field_name, field_value):
        self.fields.append((field_name, field_value))
        return self


def content_digest_sha256(content):
    if isinstance(content, str):
        content = content.encode("utf-8")

    digest = base64.standard_b64encode(hashlib.sha256(content).digest()).decode("utf-8")
    return "SHA-256=" + digest


def build_signature(host, method, target):
    return (
        HttpSignature()
        .with_field("(request-target)", f"{method} {target}")
        .with_field("host", host)
    )


def signed_post(url, private_key, public_key_url, headers=None, body=None):
    logging.debug("\n\n#####################################################Starting signed_post#####################################################")
    headers = {} if headers is None else headers

    logging.debug("Parsing URL: %s", url)
    parsed_url = urlparse(url)
    host = parsed_url.netloc
    target = parsed_url.path

    logging.debug("Parsed host: %s", host)
    logging.debug("Parsed target: %s", target)

    accept = "application/activity+json"
    content_type = "application/activity+json"
    date_header = get_gmt_now()

    logging.debug("Generated Date header: %s", date_header)

    digest = content_digest_sha256(body)
    logging.debug("Generated Digest: %s", digest)

    logging.debug("Building signature...")
    signature_header = (
        build_signature(host, "post", target)
        .with_field("date", date_header)
        .with_field("digest", digest)
        .with_field("content-type", content_type)
        .build_signature(public_key_url, private_key)
    )
    logging.debug("Generated Signature header: %s", signature_header)

    # Log the private key in a safe way
    logging.debug("Private Key Length (in bytes): %d", len(private_key))

    headers["accept"] = accept
    headers["digest"] = digest
    headers["date"] = date_header
    headers["host"] = host
    headers["content-type"] = content_type
    headers["signature"] = signature_header
    headers["user-agent"] = "shimmy's django_activitypub service - unlike mozilla"

    logging.debug("Final headers: %s", headers)
    logging.debug("Request body: %s", body)
    logging.debug("Request URL: %s", url)

    logging.debug("Sending POST request to %s", url)
    try:
        response = requests.post(url, data=body, headers=headers)
        logging.debug("Response status code: %s", response.status_code)
        logging.debug("Response headers: %s", response.headers)
        logging.debug("Response body: %s", response.text)
    except requests.RequestException as e:
        logging.error("Request failed: %s", e)
        return None

    return response



def parse_signature_header(header):
    parts = header.split(",")
    headers = [x.split('="', 1) for x in parts]
    parsed = {x[0]: x[1].replace('"', '') for x in headers}
    return parsed


@dataclass
class ValidateResult:
    success: bool
    identity: str = None
    error: str = None

    @classmethod
    def success(cls, identity):
        return cls(True, identity=identity)

    @classmethod
    def fail(cls, error):
        return cls(False, error=error)


class SignatureChecker:
    def __init__(self, obj: dict):
        logging.debug("Initializing SignatureChecker with object: %s", obj)

        self.controller = obj.get('owner')
        self.key_id = obj.get('id')
        logging.debug("Key ID set to: %s", self.key_id)
        
        public_key = obj.get('publicKeyPem')
        if isinstance(public_key, dict):
            public_key = public_key.get('@value')
        
        # Log the first 100 characters of the public key for verification
        logging.debug("Server Public Key (first 100 chars): %s", public_key[:100])
        
        try:
            self.public_key = load_pem_public_key(public_key.encode('utf-8'))
            logging.debug("Loaded public key successfully.")
        except Exception as e:
            logging.error("Failed to load public key: %s", e)
            raise


    def validate(self, method, url, headers, body) -> ValidateResult:
        logging.debug("\n\n============================= START SIGNATURE VALIDATION =============================")
        logging.debug(">> Method: %s, URL: %s", method, url)

        # Convert headers to a dictionary for logging
        headers_dict = dict(headers.items())
        logging.debug(">> Received Headers:\n%s", json.dumps(headers_dict, indent=2))
        logging.debug(">> Received Body:\n%s", body.decode('utf-8') if isinstance(body, bytes) else body)

        if 'signature' not in headers:
            logging.error("!!! ERROR: Missing signature header !!!")
            return ValidateResult.fail("Missing signature header")

        if method.lower() == 'post':
            digest = content_digest_sha256(body)
            req_digest = headers.get('digest', '')
            logging.debug(">> Calculated Digest: %s", digest)
            logging.debug(">> Received Digest: %s", req_digest)

            if digest != req_digest:
                logging.error("!!! ERROR: Digest mismatch !!!\nExpected: %s\nReceived: %s", digest, req_digest)
                return ValidateResult.fail(f"Digest mismatch: {digest} != {req_digest}")
            logging.debug(">>> Digest verification passed.")

        parsed = parse_signature_header(headers['signature'])
        logging.debug(">> Parsed Signature Header:\n%s", json.dumps(parsed, indent=2))

        fields = parsed['headers'].split(' ')
        logging.debug(">> Signature Fields:\n%s", fields)

        required_fields = {"(request-target)", "date"}
        if not required_fields.issubset(fields):
            missing_fields = required_fields - set(fields)
            logging.error("!!! ERROR: Missing required signature fields: %s !!!", missing_fields)
            return ValidateResult.fail(f"Missing required signature fields: {missing_fields}")

        builder = HttpSignature()
        for field in fields:
            if field == "(request-target)":
                parsed_url = urlparse(url)
                builder.with_field(field, f"{method.lower()} {parsed_url.path}")
            else:
                builder.with_field(field, headers[field])
        canonical_message = builder.build_message().encode('utf8')
        logging.debug("CCCCCCCCCCCCCCCCCCCCCCCCCCCCanonical message (verification): %s", repr(canonical_message))  # Log for verification

        logging.debug(">> Comparing Key ID\nExpected: %s\nReceived: %s", self.key_id, parsed.get('keyId'))
        if self.key_id != parsed.get('keyId'):
            logging.error("!!! ERROR: Key ID mismatch !!!\nExpected: %s\nReceived: %s", self.key_id, parsed.get('keyId'))
            return ValidateResult.fail(f"Key ID mismatch: expected({self.key_id}) != parsed({parsed.get('keyId')})")

        message = builder.build_message().encode('utf8')
        signature = base64.standard_b64decode(parsed['signature'])
        logging.debug("DDDDDDDDDDDDDDDDDDDecoded signature: %s", signature)  # Log the decoded signature

        logging.debug(">>> Canonical Message to Verify:\n%s", message)
        logging.debug(">>> Received Signature:\n%s", signature)

        try:
            if isinstance(self.public_key, rsa.RSAPublicKey):
                self.public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
                logging.info("*** SUCCESS: Signature verified using RSA ***")
            elif isinstance(self.public_key, ed25519.Ed25519PublicKey):
                self.public_key.verify(signature, message)
                logging.info("*** SUCCESS: Signature verified using Ed25519 ***")
            else:
                logging.error("!!! ERROR: Unsupported public key type: %s !!!", type(self.public_key))
                return ValidateResult.fail(f"Unsupported public key type: {type(self.public_key)}")

            logging.debug("============================= END SIGNATURE VALIDATION =============================\n\n")
            return ValidateResult.success(self.controller)
        except InvalidSignature as e:
            logging.error("!!! ERROR: Invalid signature !!!\nException: %s", e)
            logging.debug("============================= END SIGNATURE VALIDATION =============================\n\n")
            return ValidateResult.fail(f"Invalid signature: {e}")


