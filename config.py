import os
class Config:
    INTERNAL_TRUSTED_CIDRS = os.getenv('INTERNAL_TRUSTED_CIDRS', '')
    TFA_TRUST_DAYS = int(os.getenv('TFA_TRUST_DAYS', '30'))
    TFA_TOTP_WINDOW = int(os.getenv('TFA_TOTP_WINDOW', '1'))
