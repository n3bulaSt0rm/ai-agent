import os
import boto3
import json
import time
from botocore.exceptions import ClientError
from botocore.config import Config
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import logging
from typing import Any, Dict, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import requests
from datetime import datetime, timedelta
import hashlib
import hmac
import base64
import urllib.parse

from backend.common.config import settings

logger = logging.getLogger(__name__)

# Initialize basic S3 client 
s3_client = boto3.client(
    's3',
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
    config=Config(
        signature_version='s3v4',
        s3={'addressing_style': 'path'}
    )
)

# Thread pool for async operations
_executor = ThreadPoolExecutor(max_workers=10)

async def upload_to_s3(content: bytes, path: str, content_type: str = 'application/pdf') -> str:
    """
    Upload content to S3 bucket using presigned URL approach.
    
    Args:
        content: File content as bytes
        path: Path within bucket
        content_type: MIME type of the content
        
    Returns:
        S3 URL for the uploaded file
    """
    bucket_name = settings.S3_BUCKET_NAME
    
    try:
        logger.info(f"Uploading to S3 using presigned URL approach: {path} with content-type: {content_type}")
        
        # Get a pre-signed URL for PUT request
        def _get_presigned_url():
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={'Bucket': bucket_name, 'Key': path, 'ContentType': content_type},
                ExpiresIn=3600
            )
            return presigned_url
            
        presigned_url = await asyncio.get_event_loop().run_in_executor(_executor, _get_presigned_url)
        
        # Upload using the presigned URL
        def _upload_with_presigned():
            response = requests.put(
                presigned_url,
                data=content,
                headers={'Content-Type': content_type}
            )
            
            if response.status_code not in (200, 204):
                raise Exception(f"Presigned upload failed: {response.status_code}")
                
            return f"s3://{bucket_name}/{path}"
            
        s3_url = await asyncio.get_event_loop().run_in_executor(_executor, _upload_with_presigned)
        logger.info(f"Uploaded file using presigned URL to {s3_url}")
        return s3_url
            
    except Exception as e:
        logger.error(f"Error with upload: {str(e)}")
        # Last resort - attempt to use boto3 directly with error details
        try:
            logger.info("Attempting direct boto3 upload as last resort...")
            
            def _last_resort_upload():
                # Direct upload without streaming
                response = s3_client.put_object(
                    Bucket=bucket_name,
                    Key=path,
                    Body=content,
                    ContentType=content_type
                )
                logger.info(f"Last resort upload response: {response}")
                return f"s3://{bucket_name}/{path}"
                
            s3_url = await asyncio.get_event_loop().run_in_executor(_executor, _last_resort_upload)
            logger.info(f"Last resort upload succeeded to {s3_url}")
            return s3_url
        except Exception as final_e:
            logger.error(f"All upload methods failed. Final error: {str(final_e)}")
            raise Exception(f"Could not upload file using any method: {str(e)} -> {str(final_e)}")

async def upload_to_s3_public(content: bytes, path: str, content_type: str = 'application/pdf') -> str:
    """
    Upload content to S3 bucket and return a direct public URL.
    
    Args:
        content: File content as bytes
        path: Path within bucket
        content_type: MIME type of the content
        
    Returns:
        Public URL for the uploaded file
    """
    bucket_name = settings.S3_BUCKET_NAME
    
    try:
        logger.info(f"Uploading to S3 with public URL: {path} with content-type: {content_type}")
        
        def _upload_public():
            # Upload without ACL
            response = s3_client.put_object(
                Bucket=bucket_name,
                Key=path,
                Body=content,
                ContentType=content_type
            )
            logger.info(f"Public upload response: {response}")
            
            # Return direct URL, not s3:// format
            return f"https://{bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{path}"
        
        public_url = await asyncio.get_event_loop().run_in_executor(_executor, _upload_public)
        logger.info(f"Uploaded file with public access URL: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"Error with public upload: {str(e)}")
        raise Exception(f"Could not upload file with public access: {str(e)}")

def get_signed_url(s3_url: str, expiration: int = 31536000) -> str:
    """
    Generate a signed URL for accessing a file in S3.
    
    Args:
        s3_url: S3 URL in format s3://bucket-name/path/to/file
        expiration: URL expiration time in seconds (default: 1 year)
        
    Returns:
        Presigned URL for accessing the file
    """
    try:
        # Parse S3 URL to get bucket and key
        if not s3_url.startswith('s3://'):
            raise ValueError(f"Invalid S3 URL format: {s3_url}")
            
        path = s3_url.replace('s3://', '', 1)
        bucket_name, key = path.split('/', 1)
        
        # Generate presigned URL
        signed_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': key
            },
            ExpiresIn=expiration
        )
        
        return signed_url
        
    except Exception as e:
        logger.error(f"Error generating signed URL: {str(e)}")
        # Return empty URL on error instead of failing the request
        return ""

async def download_from_s3(s3_url: str) -> bytes:
    """
    Download file content from S3.
    
    Args:
        s3_url: S3 URL in format s3://bucket-name/path/to/file
        
    Returns:
        File content as bytes
    """
    try:
        # Parse S3 URL to get bucket and key
        if not s3_url.startswith('s3://'):
            raise ValueError(f"Invalid S3 URL format: {s3_url}")
            
        path = s3_url.replace('s3://', '', 1)
        bucket_name, key = path.split('/', 1)
        
        # Try to get a presigned URL first
        presigned_url = get_signed_url(s3_url)
        
        if presigned_url:
            # Download using the presigned URL
            def _download_with_presigned():
                response = requests.get(presigned_url)
                if response.status_code == 200:
                    return response.content
                else:
                    raise Exception(f"Failed to download with presigned URL: {response.status_code}")
            
            try:
                content = await asyncio.get_event_loop().run_in_executor(_executor, _download_with_presigned)
                logger.info(f"Downloaded file from {s3_url} using presigned URL")
                return content
            except Exception as e:
                logger.warning(f"Failed to download with presigned URL: {e}, falling back to direct method")
                # Fall through to direct method
        
        # Fall back to direct boto3 method
        def _download():
            response = s3_client.get_object(Bucket=bucket_name, Key=key)
            return response['Body'].read()
            
        content = await asyncio.get_event_loop().run_in_executor(_executor, _download)
        logger.info(f"Downloaded file from {s3_url}")
        return content
        
    except Exception as e:
        logger.error(f"Error downloading from S3: {str(e)}")
        raise

async def delete_from_s3(s3_url: str) -> bool:
    """
    Delete file from S3.
    
    Args:
        s3_url: S3 URL in format s3://bucket-name/path/to/file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Parse S3 URL to get bucket and key
        if not s3_url.startswith('s3://'):
            raise ValueError(f"Invalid S3 URL format: {s3_url}")
            
        path = s3_url.replace('s3://', '', 1)
        bucket_name, key = path.split('/', 1)
        
        # Run delete in thread pool to not block event loop
        def _delete():
            s3_client.delete_object(Bucket=bucket_name, Key=key)
            return True
            
        result = await asyncio.get_event_loop().run_in_executor(_executor, _delete)
        logger.info(f"Deleted file from {s3_url}")
        return result
        
    except Exception as e:
        logger.error(f"Error deleting from S3: {str(e)}")
        return False

# Helper for direct S3 requests with signature v4
class AWSRequestsAuth(requests.auth.AuthBase):
    """AWS Signature V4 Request Signer for Requests."""

    def __init__(self, aws_access_key, aws_secret_access_key, aws_host, 
                 aws_region, aws_service):
        self.aws_access_key = aws_access_key
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_host = aws_host
        self.aws_region = aws_region
        self.service = aws_service

    def __call__(self, r):
        aws_date = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        aws_datestamp = aws_date[:8]
        
        url_parts = requests.utils.urlparse(r.url)
        host = url_parts.netloc
        canonical_uri = self._normalize_url_path(url_parts.path)
        canonical_querystring = url_parts.query
        
        # Create canonical headers
        canonical_headers = (
            f'content-type:{r.headers.get("Content-Type", "")}\n'
            f'host:{host}\n'
            f'x-amz-date:{aws_date}\n'
        )
        
        # Create signed headers
        signed_headers = 'content-type;host;x-amz-date'
        
        # Create payload hash (hash of request body content)
        payload_hash = hashlib.sha256(
            r.body if r.body else b''
        ).hexdigest()
        
        # Create canonical request
        canonical_request = (
            f'{r.method}\n'
            f'{canonical_uri}\n'
            f'{canonical_querystring}\n'
            f'{canonical_headers}\n'
            f'{signed_headers}\n'
            f'{payload_hash}'
        )
        
        # Create string to sign
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = (
            f'{aws_datestamp}/{self.aws_region}/{self.service}/aws4_request'
        )
        string_to_sign = (
            f'{algorithm}\n'
            f'{aws_date}\n'
            f'{credential_scope}\n'
            f'{hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()}'
        )
        
        # Create signing key
        k_date = self._sign(
            ('AWS4' + self.aws_secret_access_key).encode('utf-8'),
            aws_datestamp
        )
        k_region = self._sign(k_date, self.aws_region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, 'aws4_request')
        
        # Create signature
        signature = hmac.new(
            k_signing,
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Create authorization header
        auth_header = (
            f'{algorithm} '
            f'Credential={self.aws_access_key}/{credential_scope}, '
            f'SignedHeaders={signed_headers}, '
            f'Signature={signature}'
        )
        
        # Add headers to request
        r.headers.update({
            'Authorization': auth_header,
            'x-amz-date': aws_date,
            'x-amz-content-sha256': payload_hash
        })
        
        return r
    
    def _normalize_url_path(self, path):
        normalized_path = urllib.parse.quote(path, safe='/-_.~')
        if not normalized_path.startswith('/'):
            normalized_path = '/' + normalized_path
        return normalized_path

    def _sign(self, key, msg):
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest() 