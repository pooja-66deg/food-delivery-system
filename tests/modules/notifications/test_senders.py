"""Notification channel senders + dispatch."""
import pytest

from src.modules.notifications import senders


def test_get_sender_by_channel():
    assert senders.get_sender("SMS").channel == "SMS"
    assert senders.get_sender("EMAIL").channel == "EMAIL"
    assert senders.get_sender("PUSH").channel == "PUSH"
    # unknown channel falls back to the in-app LOG channel
    assert senders.get_sender("carrier-pigeon").channel == "LOG"


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["LOG", "SMS", "EMAIL", "PUSH"])
async def test_dispatch_succeeds_on_every_channel(channel):
    assert await senders.dispatch(channel, "recipient", "Your order is on the way!") is True
