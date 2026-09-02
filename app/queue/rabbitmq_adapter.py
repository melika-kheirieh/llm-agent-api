class RabbitMQAdapter:
    """Broker boundary for async agent execution."""

    def publish(self, job):
        raise NotImplementedError

    def consume(self):
        raise NotImplementedError

    def ack(self, message):
        raise NotImplementedError

    def nack(self, message, retry=False):
        raise NotImplementedError
