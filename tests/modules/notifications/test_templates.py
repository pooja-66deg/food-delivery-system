"""Outbound copy and the per-status channel policy."""
import pytest

from src.modules.notifications import templates
from src.modules.notifications.models import Channel


def test_push_covers_every_status():
    """Push mirrors the timeline, so nothing the feed shows is silent on push."""
    for status in templates.STATUS_COPY:
        assert Channel.PUSH in templates.channels_for(status)


@pytest.mark.parametrize(
    "status", ["OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED", "REJECTED"]
)
def test_sms_goes_out_for_the_statuses_you_need_away_from_the_app(status):
    assert Channel.SMS in templates.channels_for(status)


@pytest.mark.parametrize("status", ["PREPARING", "RESTAURANT_ACCEPTED", "READY_FOR_PICKUP"])
def test_sms_stays_quiet_for_intermediate_kitchen_steps(status):
    """Each SMS costs money; the kitchen's internal progress does not warrant one."""
    assert Channel.SMS not in templates.channels_for(status)


@pytest.mark.parametrize("status", ["PAYMENT_SUCCESS", "DELIVERED", "CANCELLED", "REJECTED"])
def test_email_goes_out_for_the_paper_trail(status):
    assert Channel.EMAIL in templates.channels_for(status)


@pytest.mark.parametrize("status", ["PREPARING", "OUT_FOR_DELIVERY", "COMPLETED"])
def test_email_stays_quiet_for_everything_else(status):
    """Nine emails an order is how a domain gets filtered as spam."""
    assert Channel.EMAIL not in templates.channels_for(status)


def test_log_is_never_an_outbound_channel():
    """The in-app row is written directly, not dispatched."""
    for status in templates.STATUS_COPY:
        assert Channel.LOG not in templates.channels_for(status)


def test_unknown_status_sends_nothing_outbound():
    assert templates.channels_for("INVENTED_STATUS") == ()


def test_unknown_status_still_has_readable_in_app_copy():
    """A new status must not produce a blank feed row."""
    assert "INVENTED_STATUS" in templates.short_copy("INVENTED_STATUS")


def test_email_render_carries_a_subject_naming_the_order():
    rendered = templates.render(Channel.EMAIL, "DELIVERED", order_id=42)

    assert rendered.channel == "EMAIL"
    assert rendered.subject == "Order #42 delivered"
    assert templates.STATUS_COPY["DELIVERED"] in rendered.body


@pytest.mark.parametrize("channel", [Channel.SMS, Channel.PUSH])
def test_short_channels_have_no_subject_but_name_the_order(channel):
    """An SMS arrives with no context, so the order number rides in the body."""
    rendered = templates.render(channel, "OUT_FOR_DELIVERY", order_id=42)

    assert rendered.subject is None
    assert rendered.body.startswith("Order #42:")
    assert templates.STATUS_COPY["OUT_FOR_DELIVERY"] in rendered.body
