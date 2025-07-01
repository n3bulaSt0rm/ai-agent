import pika
import json
import threading
import asyncio
import ssl
import logging
from typing import Dict, Any, Callable, Optional, List
from pika.adapters.asyncio_connection import AsyncioConnection
from backend.common.config import settings

logger = logging.getLogger(__name__)

class RabbitMQClient:
    """
    Client for RabbitMQ messaging service.
    """
    
    def __init__(self):
        """Initialize RabbitMQ client with credentials."""
        try:
            # RabbitMQ connection parameters
            self.credentials = pika.PlainCredentials(
                username=settings.RABBITMQ_USERNAME,
                password=settings.RABBITMQ_PASSWORD
            )
            
            # Use SSL if TLS port is configured
            if settings.RABBITMQ_PORT == 5671:
                self.ssl_options = pika.SSLOptions(ssl.create_default_context())
                self.use_ssl = True
            else:
                self.ssl_options = None
                self.use_ssl = False
            
            self.connection_params = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                virtual_host=settings.RABBITMQ_VHOST,
                credentials=self.credentials,
                ssl_options=self.ssl_options,
                heartbeat=600, 
                blocked_connection_timeout=300 
            )
            
            # Connection and channel are created when needed
            self.connection = None
            self.channel = None
            self.consumer_threads = {}
            
            logger.info(f"Initialized RabbitMQ client for {settings.RABBITMQ_HOST}")
        except Exception as e:
            logger.error(f"Error initializing RabbitMQ client: {e}")
            raise
    
    async def _ensure_connection(self):
        """Ensure that a connection and channel are established."""
        if self.connection is None or self.connection.is_closed:
            self.connection = pika.BlockingConnection(self.connection_params)
            
        if self.channel is None or self.channel.is_closed:
            self.channel = self.connection.channel()
            
    async def publish_message(self, topic_name: str, message_data: Dict[str, Any]) -> str:
        """
        Publish a message to a RabbitMQ exchange.
        
        Args:
            topic_name: Name of the exchange (topic)
            message_data: Message data as dictionary
            
        Returns:
            Message ID (in RabbitMQ case, just a confirmation string)
        """
        try:
            await self._ensure_connection()
            
            # Create exchange if it doesn't exist
            self.channel.exchange_declare(
                exchange=topic_name,
                exchange_type='topic',
                durable=True
            )
            
            # Convert message to JSON
            message_json = json.dumps(message_data)
            message_bytes = message_json.encode("utf-8")
            
            # Publish message
            self.channel.basic_publish(
                exchange=topic_name,
                routing_key='',  # Empty routing key for topic exchange
                body=message_bytes,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                    content_type='application/json'
                )
            )
            
            message_id = f"{topic_name}-{len(message_bytes)}"
            logger.info(f"Published message to {topic_name}")
            return message_id
        except Exception as e:
            logger.error(f"Error publishing message to {topic_name}: {e}")
            raise
    
    async def create_subscription(self, topic_name: str, subscription_name: str, 
                                 callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Create a subscription and start listening for messages.
        
        Args:
            topic_name: Name of the exchange (topic)
            subscription_name: Name for the queue
            callback: Function to call when a message is received
        """
        try:
            # Create a new connection and channel for this subscription
            connection = pika.BlockingConnection(self.connection_params)
            channel = connection.channel()
            
            # Declare exchange
            channel.exchange_declare(
                exchange=topic_name,
                exchange_type='topic',
                durable=True
            )
            
            # Declare queue
            channel.queue_declare(
                queue=subscription_name,
                durable=True
            )
            
            # Bind queue to exchange
            channel.queue_bind(
                exchange=topic_name,
                queue=subscription_name,
                routing_key='#'  # Match all routing keys
            )
            
            # Define callback wrapper to parse JSON
            def callback_wrapper(ch, method, properties, body):
                try:
                    data = json.loads(body.decode("utf-8"))
                    
                    # Check if callback is a coroutine function
                    if asyncio.iscoroutinefunction(callback):
                        # Create a new event loop for this thread
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        # Run the coroutine to completion
                        loop.run_until_complete(callback(data))
                        loop.close()
                    else:
                        # Normal function call
                        callback(data)
                        
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            
            # Set up consumer
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=subscription_name,
                on_message_callback=callback_wrapper
            )
            
            logger.info(f"Listening for messages on queue {subscription_name} bound to {topic_name}")
            
            # Start consuming in a separate thread
            def run_consumer():
                try:
                    channel.start_consuming()
                except Exception as e:
                    logger.error(f"Subscription {subscription_name} failed: {e}")
                    if channel.is_open:
                        channel.stop_consuming()
                    if connection.is_open:
                        connection.close()
            
            consumer_thread = threading.Thread(target=run_consumer, daemon=True)
            consumer_thread.start()
            
            # Store thread reference
            self.consumer_threads[subscription_name] = {
                'thread': consumer_thread,
                'connection': connection,
                'channel': channel
            }
            
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            raise
    
    def close(self):
        """Close all connections and channels."""
        try:
            # Stop all consumers
            for subscription_name, thread_info in self.consumer_threads.items():
                channel = thread_info.get('channel')
                connection = thread_info.get('connection')
                
                if channel and channel.is_open:
                    channel.stop_consuming()
                
                if connection and connection.is_open:
                    connection.close()
            
            # Clear consumer threads
            self.consumer_threads = {}
            
            # Close main connection
            if self.connection and self.connection.is_open:
                self.connection.close()
                self.connection = None
                self.channel = None
                
            logger.info("Closed all RabbitMQ connections")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connections: {e}")

# Create singleton instance
_rabbitmq_client = None

def get_rabbitmq_client() -> RabbitMQClient:
    """Get the RabbitMQ client instance."""
    global _rabbitmq_client
    if _rabbitmq_client is None:
        _rabbitmq_client = RabbitMQClient()
    return _rabbitmq_client 