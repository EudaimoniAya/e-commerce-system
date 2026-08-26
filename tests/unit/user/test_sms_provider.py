"""SMS Provider 类名单测（Fake* 命名迁移）。

覆盖 spec user-auth：SHALL NOT 保留名为 ``MockSmsProvider`` 的产品类。
不引入短信 provider 配置 / 协议，仅校验类名与可调用性。
"""

import allure

from app.user import sms_service


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("FakeSmsProvider.send 可调用。")
def test_fake_sms_provider_send_is_callable() -> None:
    """FakeSmsProvider.send 为可调用静态方法（dev/test/CI 不调用真实网关）。"""
    assert callable(sms_service.FakeSmsProvider.send)


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("MockSmsProvider 产品类已移除。")
def test_no_mock_sms_provider_class_remains() -> None:
    """app.user.sms_service 不得再保留 MockSmsProvider。"""
    assert not hasattr(sms_service, "MockSmsProvider")
