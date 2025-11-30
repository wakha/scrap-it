"""Kafka client wrapper for producing and consuming messages."""
import json
import logging
from typing import Optional, Callable, Any
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class KafkaProducerClient:
    """Kafka producer wrapper with error handling and metrics."""

    def __init__(self, bootstrap_servers: str, client_id: str):
        """Initialize Kafka producer.
        
        Args:
            bootstrap_servers: Kafka broker addresses
            client_id: Client identifier for this producer
        """
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.producer = None
        self._connect()

    def _connect(self):
        """Establish connection to Kafka."""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',  # Wait for all replicas
                retries=3,
                max_in_flight_requests_per_connection=1,
            )
            logger.info(f"Kafka producer connected: {self.client_id}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka producer: {e}")
            raise

    def send(self, topic: str, message: dict, key: Optional[str] = None) -> bool:
        """Send message to Kafka topic.
        
        Args:
            topic: Kafka topic name
            message: Message payload as dict
            key: Optional message key for partitioning
            
        Returns:
            True if successful, False otherwise
        """
        try:
            future = self.producer.send(topic, value=message, key=key)
            record_metadata = future.get(timeout=10)
            logger.info(
                f"Message sent to {topic} - partition: {record_metadata.partition}, "
                f"offset: {record_metadata.offset}"
            )
            return True
        except KafkaError as e:
            logger.error(f"Failed to send message to {topic}: {e}")
            return False

    def close(self):
        """Close producer connection."""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info(f"Kafka producer closed: {self.client_id}")


class KafkaConsumerClient:
    """Kafka consumer wrapper with error handling and metrics."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list,
        client_id: str,
        auto_offset_reset: str = 'earliest'
    ):
        """Initialize Kafka consumer.
        
        Args:
            bootstrap_servers: Kafka broker addresses
            group_id: Consumer group ID
            topics: List of topics to subscribe to
            client_id: Client identifier
            auto_offset_reset: Where to start reading ('earliest' or 'latest')
        """
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topics = topics
        self.client_id = client_id
        self.auto_offset_reset = auto_offset_reset
        self.consumer = None
        self._connect()

    def _connect(self):
        """Establish connection to Kafka."""
        try:
            self.consumer = KafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                client_id=self.client_id,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                key_deserializer=lambda k: k.decode('utf-8') if k else None,
                auto_offset_reset=self.auto_offset_reset,
                enable_auto_commit=False,  # Manual commit for reliability
                max_poll_records=10,
            )
            logger.info(
                f"Kafka consumer connected: {self.client_id}, "
                f"group: {self.group_id}, topics: {self.topics}"
            )
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka consumer: {e}")
            raise

    def consume(self, handler: Callable[[dict], bool]) -> None:
        """Consume messages and process with handler.
        
        Args:
            handler: Function to process each message, returns True if successful
        """
        try:
            logger.info(f"Starting to consume from topics: {self.topics}")
            for message in self.consumer:
                try:
                    logger.info(
                        f"Received message from {message.topic} "
                        f"[partition: {message.partition}, offset: {message.offset}]"
                    )
                    
                    # Process message
                    success = handler(message.value)
                    
                    if success:
                        # Commit offset only after successful processing
                        self.consumer.commit()
                        logger.info(f"Message processed and committed: offset {message.offset}")
                    else:
                        logger.warning(f"Message processing failed: offset {message.offset}")
                        
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Don't commit on error - message will be reprocessed
                    
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        except Exception as e:
            logger.error(f"Consumer error: {e}", exc_info=True)
        finally:
            self.close()

    def close(self):
        """Close consumer connection."""
        if self.consumer:
            self.consumer.close()
            logger.info(f"Kafka consumer closed: {self.client_id}")
