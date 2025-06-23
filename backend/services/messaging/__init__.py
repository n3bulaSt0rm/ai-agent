"""
Messaging service module for handling message passing between components using RabbitMQ.
"""

from typing import Dict, Any, Callable
import logging

logger = logging.getLogger(__name__)

from backend.common.config import settings
from backend.services.messaging.rabbitmq import get_rabbitmq_client

async def get_messaging_client():
    """
    Get the RabbitMQ messaging client.
    
    Returns:
        RabbitMQClient instance
    """
    logger.info("Using RabbitMQ messaging implementation")
    return get_rabbitmq_client()

async def publish_message(topic_name: str, message_data: Dict[str, Any]) -> str:
    """
    Publish a message using RabbitMQ.
    
    Args:
        topic_name: Name of the exchange/topic
        message_data: Message data as dictionary
            
    Returns:
        Message ID
    """
    client = await get_messaging_client()
    return await client.publish_message(topic_name, message_data)

async def create_subscription(topic_name: str, subscription_name: str, 
                             callback: Callable[[Dict[str, Any]], None]) -> None:
    """
    Create a subscription using RabbitMQ.
    
    Args:
        topic_name: Name of the exchange/topic
        subscription_name: Name for the queue
        callback: Function to call when a message is received
    """
    client = await get_messaging_client()
    await client.create_subscription(topic_name, subscription_name, callback) 