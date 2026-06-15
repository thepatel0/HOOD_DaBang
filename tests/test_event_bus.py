import unittest

from src.event_bus import EventBus, Event


class TestEventBus(unittest.TestCase):
    def test_killevent_jumps_queue(self):
        bus = EventBus()
        bus.publish(Event("MarketDataEvent"))
        bus.publish(Event("SignalEvent"))
        bus.publish(Event("KillEvent"))           # published last
        self.assertEqual(bus.pop().type, "KillEvent")  # comes out first

    def test_fifo_within_priority(self):
        bus = EventBus()
        bus.publish(Event("SignalEvent", {"n": 1}))
        bus.publish(Event("SignalEvent", {"n": 2}))
        bus.publish(Event("SignalEvent", {"n": 3}))
        order = [bus.pop().payload["n"] for _ in range(3)]
        self.assertEqual(order, [1, 2, 3])

    def test_priority_ordering(self):
        bus = EventBus()
        for t in ["HeartbeatEvent", "RegimeChangeEvent", "OrderEvent", "FillEvent"]:
            bus.publish(Event(t))
        got = [bus.pop().type for _ in range(4)]
        self.assertEqual(got, ["FillEvent", "OrderEvent", "RegimeChangeEvent", "HeartbeatEvent"])

    def test_unknown_event_rejected(self):
        bus = EventBus()
        with self.assertRaises(ValueError):
            bus.publish(Event("NotARealEvent"))

    def test_subscribe_and_dispatch(self):
        bus = EventBus()
        seen = []
        bus.subscribe("SignalEvent", lambda e: seen.append(e.payload["n"]))
        bus.publish(Event("SignalEvent", {"n": 42}))
        bus.dispatch_once()
        self.assertEqual(seen, [42])

    def test_kill_published_mid_drain_is_handled_first(self):
        bus = EventBus()
        order = []
        # MarketDataEvent (pri 11) dispatches before HeartbeatEvent (pri 99).
        # The md handler enqueues a KillEvent (pri 0): it must jump ahead of the
        # still-pending heartbeat.
        bus.subscribe("MarketDataEvent", lambda e: (order.append("md"),
                       bus.publish(Event("KillEvent"))))
        bus.subscribe("HeartbeatEvent", lambda e: order.append("hb"))
        bus.subscribe("KillEvent", lambda e: order.append("KILL"))
        bus.publish(Event("MarketDataEvent"))
        bus.publish(Event("HeartbeatEvent"))
        bus.drain()
        self.assertEqual(order, ["md", "KILL", "hb"])


if __name__ == "__main__":
    unittest.main()
