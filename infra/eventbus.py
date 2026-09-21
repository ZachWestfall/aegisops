# Placeholder for Kafka/NATS wrappers. Implement when ready.
class EventBus:
    def publish(self, topic: str, message: dict):  # pragma: no cover
        print(f"[eventbus] topic={topic} message={message}")
