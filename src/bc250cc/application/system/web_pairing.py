"""One-time QR pairing tokens for the frontends."""
from bc250cc.infrastructure.web_pairing import RENEW_SECONDS, age, consume, issue, valid

__all__ = ['RENEW_SECONDS', 'age', 'consume', 'issue', 'valid']
