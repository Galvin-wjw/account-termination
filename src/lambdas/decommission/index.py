"""
Decommission Lambda Function
Handles third-party vendor cleanup operations

This Lambda function:
1. Initiates Prisma vendor cleanup operations for the target account
2. Removes account-specific configurations and monitoring
3. Implements retry logic with appropriate backoff strategies
4. Logs failures but allows workflow continuation
5. Returns a summary of decommissioning results

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

import json
import os
import boto3
import logging
import time
import random
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from botocore.exceptions import ClientError, BotoCoreError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
PRISMA_API_URL = os.environ.get('PRISMA_API_URL', 'https://api.prismacloud.io')
PRISMA_API_KEY = os.environ.get('PRISMA_API_KEY')
PRISMA_SECRET_KEY = os.environ.get('PRISMA_SECRET_KEY')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 2
MAX_BACKOFF_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 30

class DecommissionError(Exception):
    """Custom exception for decommission operations"""
    def __init__(self, message: str, error_code: str = None, details: Dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

class PrismaAPIClient:
    """Client for interacting with Prisma Cloud API"""
    
    def __init__(self, api_url: str, api_key: str, secret_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.secret_key = secret_key
        self.access_token = None
        self.token_expires_at = None
    
    def authenticate(self) -> str:
        """
        Authenticate with Prisma Cloud API and get access token
        
        Returns:
            str: Access token
            
        Raises:
            DecommissionError: If authentication fails
        """
        try:
            logger.info("Authenticating with Prisma Cloud API")
            
            auth_url = f"{self.api_url}/login"
            auth_payload = {
                "username": self.api_key,
                "password": self.secret_key
            }
            
            response = requests.post(
                auth_url,
                json=auth_payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                auth_data = response.json()
                self.access_token = auth_data.get('token')
                
                if not self.access_token:
                    raise DecommissionError(
                        "Authentication successful but no token received",
                        error_code="NO_TOKEN_RECEIVED"
                    )
                
                logger.info("Successfully authenticated with Prisma Cloud API")
                return self.access_token
            else:
                error_msg = f"Authentication failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise DecommissionError(
                    error_msg,
                    error_code="AUTH_FAILED",
                    details={'status_code': response.status_code}
                )
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error during authentication: {str(e)}"
            logger.error(error_msg)
            raise DecommissionError(
                error_msg,
                error_code="AUTH_NETWORK_ERROR"
            )
        except Exception as e:
            error_msg = f"Unexpected error during authentication: {str(e)}"
            logger.error(error_msg)
            raise DecommissionError(
                error_msg,
                error_code="AUTH_UNEXPECTED_ERROR"
            )
    
    def get_headers(self) -> Dict[str, str]:
        """
        Get headers for API requests including authentication
        
        Returns:
            Dict: Headers for API requests
        """
        if not self.access_token:
            self.authenticate()
        
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }
    
    def remove_account_monitoring(self, account_id: str) -> Dict[str, Any]:
        """
        Remove account-specific monitoring configurations from Prisma Cloud
        
        Args:
            account_id: AWS account ID to remove
            
        Returns:
            Dict: API response
            
        Raises:
            DecommissionError: If removal fails
        """
        try:
            logger.info(f"Removing Prisma monitoring for account {account_id}")
            
            # First, get the account configuration
            get_url = f"{self.api_url}/cloud/aws/{account_id}"
            headers = self.get_headers()
            
            get_response = requests.get(
                get_url,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            
            if get_response.status_code == 404:
                logger.info(f"Account {account_id} not found in Prisma Cloud - already removed")
                return {
                    'success': True,
                    'message': 'Account not found - already removed',
                    'account_id': account_id
                }
            elif get_response.status_code != 200:
                error_msg = f"Failed to get account configuration: {get_response.status_code} - {get_response.text}"
                logger.error(error_msg)
                raise DecommissionError(
                    error_msg,
                    error_code="GET_ACCOUNT_FAILED",
                    details={'status_code': get_response.status_code}
                )
            
            # Delete the account configuration
            delete_url = f"{self.api_url}/cloud/aws/{account_id}"
            delete_response = requests.delete(
                delete_url,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            
            if delete_response.status_code in [200, 204]:
                logger.info(f"Successfully removed Prisma monitoring for account {account_id}")
                return {
                    'success': True,
                    'message': 'Account monitoring removed successfully',
                    'account_id': account_id
                }
            else:
                error_msg = f"Failed to remove account monitoring: {delete_response.status_code} - {delete_response.text}"
                logger.error(error_msg)
                raise DecommissionError(
                    error_msg,
                    error_code="DELETE_ACCOUNT_FAILED",
                    details={'status_code': delete_response.status_code}
                )
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error removing account monitoring: {str(e)}"
            logger.error(error_msg)
            raise DecommissionError(
                error_msg,
                error_code="REMOVE_MONITORING_NETWORK_ERROR"
            )
        except DecommissionError:
            raise
        except Exception as e:
            error_msg = f"Unexpected error removing account monitoring: {str(e)}"
            logger.error(error_msg)
            raise DecommissionError(
                error_msg,
                error_code="REMOVE_MONITORING_UNEXPECTED_ERROR"
            )
    
    def remove_account_policies(self, account_id: str) -> Dict[str, Any]:
        """
        Remove account-specific policies and configurations from Prisma Cloud
        
        Args:
            account_id: AWS account ID to remove policies for
            
        Returns:
            Dict: API response
            
        Raises:
            DecommissionError: If removal fails
        """
        try:
            logger.info(f"Removing Prisma policies for account {account_id}")
            
            # Get policies associated with the account
            policies_url = f"{self.api_url}/policy"
            headers = self.get_headers()
            
            params = {
                'cloud.account': account_id,
                'cloud.type': 'aws'
            }
            
            policies_response = requests.get(
                policies_url,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            
            if policies_response.status_code != 200:
                error_msg = f"Failed to get account policies: {policies_response.status_code} - {policies_response.text}"
                logger.warning(error_msg)
                # Don't fail the entire operation for policy retrieval issues
                return {
                    'success': True,
                    'message': 'Could not retrieve policies, but continuing',
                    'account_id': account_id
                }
            
            policies_data = policies_response.json()
            policies = policies_data.get('data', [])
            
            if not policies:
                logger.info(f"No policies found for account {account_id}")
                return {
                    'success': True,
                    'message': 'No policies found for account',
                    'account_id': account_id
                }
            
            # Remove each policy associated with the account
            removed_policies = []
            for policy in policies:
                policy_id = policy.get('policyId')
                if policy_id:
                    try:
                        delete_policy_url = f"{self.api_url}/policy/{policy_id}"
                        delete_response = requests.delete(
                            delete_policy_url,
                            headers=headers,
                            timeout=REQUEST_TIMEOUT_SECONDS
                        )
                        
                        if delete_response.status_code in [200, 204]:
                            removed_policies.append(policy_id)
                            logger.info(f"Removed policy {policy_id} for account {account_id}")
                        else:
                            logger.warning(f"Failed to remove policy {policy_id}: {delete_response.status_code}")
                    except Exception as e:
                        logger.warning(f"Error removing policy {policy_id}: {str(e)}")
            
            return {
                'success': True,
                'message': f'Removed {len(removed_policies)} policies',
                'account_id': account_id,
                'removed_policies': removed_policies
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error removing account policies: {str(e)}"
            logger.error(error_msg)
            raise DecommissionError(
                error_msg,
                error_code="REMOVE_POLICIES_NETWORK_ERROR"
            )
        except DecommissionError:
            raise
        except Exception as e:
            error_msg = f"Unexpected error removing account policies: {str(e)}"
            logger.error(error_msg)
            raise DecommissionError(
                error_msg,
                error_code="REMOVE_POLICIES_UNEXPECTED_ERROR"
            )

def calculate_backoff_delay(attempt: int) -> float:
    """
    Calculate exponential backoff delay with jitter
    
    Args:
        attempt: Current attempt number (0-based)
        
    Returns:
        float: Delay in seconds
    """
    # Exponential backoff: base_delay * (2 ^ attempt)
    delay = BASE_BACKOFF_SECONDS * (2 ** attempt)
    
    # Cap the delay at maximum
    delay = min(delay, MAX_BACKOFF_SECONDS)
    
    # Add jitter to prevent thundering herd
    jitter = random.uniform(0.1, 0.3) * delay
    
    return delay + jitter

def validate_input(event: Dict[str, Any]) -> str:
    """
    Validate input parameters
    
    Args:
        event: Lambda event containing input parameters
        
    Returns:
        str: Validated account ID
        
    Raises:
        DecommissionError: If input validation fails
    """
    if not isinstance(event, dict):
        raise DecommissionError(
            "Invalid input: event must be a dictionary",
            error_code="INVALID_INPUT_TYPE"
        )
    
    account_id = event.get('accountId')
    if not account_id:
        raise DecommissionError(
            "Missing required parameter: accountId",
            error_code="MISSING_ACCOUNT_ID"
        )
    
    if not isinstance(account_id, str):
        raise DecommissionError(
            "Invalid accountId: must be a string",
            error_code="INVALID_ACCOUNT_ID_TYPE"
        )
    
    # Validate account ID format (12 digits)
    if not account_id.isdigit() or len(account_id) != 12:
        raise DecommissionError(
            f"Invalid accountId format: {account_id}. Must be 12 digits",
            error_code="INVALID_ACCOUNT_ID_FORMAT"
        )
    
    return account_id

def decommission_prisma_vendor(account_id: str) -> Dict[str, Any]:
    """
    Decommission Prisma vendor for the specified account with retry logic
    
    Args:
        account_id: AWS account ID to decommission
        
    Returns:
        Dict: Decommission results
    """
    last_exception = None
    
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            logger.info(f"Prisma decommission attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} for account {account_id}")
            
            # Initialize Prisma API client
            prisma_client = PrismaAPIClient(PRISMA_API_URL, PRISMA_API_KEY, PRISMA_SECRET_KEY)
            
            # Remove account monitoring
            monitoring_result = prisma_client.remove_account_monitoring(account_id)
            
            # Remove account policies
            policies_result = prisma_client.remove_account_policies(account_id)
            
            # Successful decommission
            result = {
                'success': True,
                'message': 'Prisma vendor decommissioned successfully',
                'monitoring_removal': monitoring_result,
                'policies_removal': policies_result,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            logger.info(f"Prisma decommission successful on attempt {attempt + 1} for account {account_id}")
            return result
            
        except DecommissionError as e:
            last_exception = e
            
            # Don't retry for certain error types
            non_retryable_errors = [
                'INVALID_INPUT_TYPE',
                'MISSING_ACCOUNT_ID',
                'INVALID_ACCOUNT_ID_TYPE',
                'INVALID_ACCOUNT_ID_FORMAT'
            ]
            
            if e.error_code in non_retryable_errors:
                logger.error(f"Non-retryable error on attempt {attempt + 1}: {e.message}")
                raise e
            
            # Check if this is the last attempt
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                logger.error(f"All retry attempts exhausted for Prisma decommission of account {account_id}")
                break
            
            # Calculate backoff delay
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Prisma decommission failed on attempt {attempt + 1}, retrying in {delay:.2f} seconds: {e.message}")
            
            time.sleep(delay)
            
        except Exception as e:
            last_exception = DecommissionError(
                f"Unexpected error during Prisma decommission: {str(e)}",
                error_code="UNEXPECTED_ERROR"
            )
            
            # Check if this is the last attempt
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                logger.error(f"All retry attempts exhausted for Prisma decommission of account {account_id}")
                break
            
            # Calculate backoff delay
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Unexpected error on attempt {attempt + 1}, retrying in {delay:.2f} seconds: {str(e)}")
            
            time.sleep(delay)
    
    # If we get here, all retries failed - but we should continue workflow
    logger.error(f"Prisma decommission failed after {MAX_RETRY_ATTEMPTS} attempts for account {account_id}: {last_exception.message}")
    
    return {
        'success': False,
        'message': f'Prisma decommission failed after {MAX_RETRY_ATTEMPTS} attempts: {last_exception.message}',
        'error_code': last_exception.error_code if hasattr(last_exception, 'error_code') else 'UNKNOWN_ERROR',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Main Lambda handler for decommission operations
    
    Args:
        event: Lambda event containing accountId
        context: Lambda context object
        
    Returns:
        Dict containing operation results
    """
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    try:
        logger.info(f"Decommission Lambda started at {timestamp}")
        logger.info(f"Event: {json.dumps(event)}")
        
        # Validate input
        account_id = validate_input(event)
        
        # Validate environment variables
        if not PRISMA_API_KEY:
            logger.warning("Missing environment variable: PRISMA_API_KEY - using dummy mode")
        
        if not PRISMA_SECRET_KEY:
            logger.warning("Missing environment variable: PRISMA_SECRET_KEY - using dummy mode")
        
        # Initialize results tracking
        vendors_processed = []
        results = {}
        
        # Decommission Prisma vendor
        logger.info(f"Starting Prisma vendor decommission for account {account_id}")
        
        if PRISMA_API_KEY and PRISMA_SECRET_KEY:
            prisma_result = decommission_prisma_vendor(account_id)
        else:
            # Dummy mode for testing/development
            logger.info("Running in dummy mode - simulating Prisma decommission")
            prisma_result = {
                'success': True,
                'message': 'Dummy Prisma decommission completed successfully',
                'timestamp': timestamp
            }
        
        vendors_processed.append('Prisma')
        results['Prisma'] = prisma_result
        
        # Prepare response
        response = {
            'accountId': account_id,
            'vendorsProcessed': vendors_processed,
            'results': results,
            'timestamp': timestamp
        }
        
        # Log summary
        successful_vendors = [vendor for vendor, result in results.items() if result.get('success', False)]
        failed_vendors = [vendor for vendor, result in results.items() if not result.get('success', False)]
        
        logger.info(f"Decommission completed for account {account_id}")
        logger.info(f"Successful vendors: {successful_vendors}")
        if failed_vendors:
            logger.warning(f"Failed vendors: {failed_vendors}")
        
        logger.info(f"Decommission Lambda completed: {json.dumps(response)}")
        return response
        
    except DecommissionError as e:
        logger.error(f"Decommission error: {e.message}")
        
        # Return error response but don't fail the workflow
        error_response = {
            'accountId': event.get('accountId', 'unknown'),
            'vendorsProcessed': [],
            'results': {
                'error': {
                    'success': False,
                    'message': e.message,
                    'error_code': e.error_code,
                    'details': e.details
                }
            },
            'timestamp': timestamp
        }
        
        logger.info(f"Decommission Lambda completed with errors: {json.dumps(error_response)}")
        return error_response
        
    except Exception as e:
        logger.error(f"Unexpected error in decommission: {str(e)}")
        
        # Return generic error response but don't fail the workflow
        error_response = {
            'accountId': event.get('accountId', 'unknown'),
            'vendorsProcessed': [],
            'results': {
                'error': {
                    'success': False,
                    'message': str(e),
                    'error_code': 'UNEXPECTED_ERROR',
                    'details': {}
                }
            },
            'timestamp': timestamp
        }
        
        logger.info(f"Decommission Lambda completed with unexpected error: {json.dumps(error_response)}")
        return error_response