"""使用本域独立密钥和 AAD；不挂载 Monitoring 私钥。"""

from services.common.email_crypto import EmailCrypto as BaseEmailCrypto


class EmailCrypto(BaseEmailCrypto):
    @staticmethod
    def aad(owner, version):
        return f"elect:notification-email:{owner}:{version}".encode()
