import socket
import pytest

def test_default_suite_cannot_reach_paid_services():
    for host in ['api.openai.com','llm.api.cloud.yandex.net','api.apify.com','api.yookassa.ru','goapi.unisender.ru','api.cloudpayments.ru']:
        with pytest.raises(AssertionError,match='External DNS'):
            socket.getaddrinfo(host,443)
        with socket.socket() as connection:
            with pytest.raises(AssertionError,match='External network'):
                connection.connect((host,443))
