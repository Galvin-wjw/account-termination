"""
Metadata Update Lambda Function
Updates DynamoDB with account termination metadata

This Lambda function:
1. Updates DynamoDB table with account termination timestamp
2. Records termination status and workflow execution details
3. Implements retry logic with exponential backoff up to three attempts
4. Returns confirmation of successful record updates

Requirements: 4.1, 4.2, 4.3
"""

import json
import os
import boto3
import logging
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError, BotoCoreError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
AWS_REGION = os.environ.get('AWS_REGION')

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 16

class MetadataUpdateError(Exception):
    """Custom exception for metadata update operations"""
    def __init__(self, message: str, error_code: str = None, details: Dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

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

def validate_input(event: Dict[str, Any]) -> tuple[str, str, str]:
    """
    Validate input parameters
    
    Args:
        event: Lambda event containing input parameters
        
    Returns:
        tuple: (account_id, termination_status, execution_arn)
        
    Raises:
        MetadataUpdateError: If input validation fails
    """
    if not isinstance(event, dict):
        raise MetadataUpdateError(
            "Invalid input: event must be a dictionary",
            error_code="INVALID_INPUT_TYPE"
        )
    
    account_id = event.get('accountId')
    if not account_id:
        raise MetadataUpdateError(
            "Missing required parameter: accountId",
            error_code="MISSING_ACCOUNT_ID"
        )
    
    if not isinstance(account_id, str):
        raise MetadataUpdateError(
            "Invalid accountId: must be a string",
            error_code="INVALID_ACCOUNT_ID_TYPE"
        )
    
    # Validate account ID format (12 digits)
    if not account_id.isdigit() or len(account_id) != 12:
        raise MetadataUpdateError(
            f"Invalid accountId format: {account_id}. Must be 12 digits",
            error_code="INVALID_ACCOUNT_ID_FORMAT"
        )
    
    termination_status = event.get('terminationStatus', 'TERMINATING')
    if not isinstance(termination_status, str):
        raise MetadataUpdateError(
            "Invalid terminationStatus: must be a string",
            error_code="INVALID_TERMINATION_STATUS_TYPE"
        )
    
    # Validate termination status values
    valid_statuses = ['ACTIVE', 'TERMINATING', 'TERMINATED', 'FAILED']
    if termination_status not in valid_statuses:
        raise MetadataUpdateError(
            f"Invalid terminationStatus: {termination_status}. Must be one of {valid_statuses}",
            error_code="INVALID_TERMINATION_STATUS_VALUE"
        )
    
    execution_arn = event.get('executionArn', '')
    if not isinstance(execution_arn, str):
        raise MetadataUpdateError(
            "Invalid executionArn: must be a string",
            error_code="INVALID_EXECUTION_ARN_TYPE"
        )
    
    return account_id, termination_status, execution_arn

def create_metadata_record(
    dynamodb_client,
    account_id: str,
    termination_status: str,
    execution_arn: str,
    timestamp: str,
    pre_check_results: Optional[Dict] = None,
    account_management_results: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Create or update account metadata record in DynamoDB
    
    Args:
        dynamodb_client: DynamoDB client
        account_id: Account ID
        termination_status: Current termination status
        execution_arn: Step Function execution ARN
        timestamp: Current timestamp
        pre_check_results: Results from pre-check stage
        account_management_results: Results from account management stage
        
    Returns:
        Dict: DynamoDB response
        
    Raises:
        MetadataUpdateError: If DynamoDB operation fails
    """
    try:
        logger.info(f"Creating/updating metadata record for account {account_id}")
        
        # Prepare the item to put/update
        item = {
            'accountId': {'S': account_id},
            'status': {'S': termination_status},
            'executionArn': {'S': execution_arn},
            'updatedAt': {'S': timestamp}
        }
        
        # Add termination timestamps based on status
        if termination_status == 'TERMINATING':
            item['terminationInitiated'] = {'S': timestamp}
        elif termination_status == 'TERMINATED':
            item['terminationCompleted'] = {'S': timestamp}
        
        # Add pre-check results if provided
        if pre_check_results:
            item['preCheckResults'] = {
                'M': {
                    'ebsVolumes': {'N': str(pre_check_results.get('ebsVolumes', 0))},
                    'rdsInstances': {'N': str(pre_check_results.get('rdsInstances', 0))},
                    'safeToTerminate': {'BOOL': pre_check_results.get('safeToTerminate', False)}
                }
            }
        
        # Add account management results if provided
        if account_management_results:
            item['organizationalUnit'] = {'S': account_management_results.get('organizationalUnit', '')}
        
        # Set createdAt only for new records (use conditional expression)
        item['createdAt'] = {'S': timestamp}
        
        # Use put_item with condition to handle both create and update
        response = dynamodb_client.put_item(
            TableName=DYNAMODB_TABLE_NAME,
            Item=item,
            ConditionExpression='attribute_not_exists(accountId)',
            ReturnValues='ALL_OLD'
        )
        
        logger.info(f"Successfully created new metadata record for account {account_id}")
        return response
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        # If item already exists, update it instead
        if error_code == 'ConditionalCheckFailedException':
            logger.info(f"Metadata record exists for account {account_id}, updating instead")
            return update_existing_metadata_record(
                dynamodb_client, account_id, termination_status, 
                execution_arn, timestamp, pre_check_results, account_management_results
            )
        
        error_message = e.response['Error']['Message']
        logger.error(f"DynamoDB put_item failed: {error_code} - {error_message}")
        
        raise MetadataUpdateError(
            f"Failed to create metadata record: {error_message}",
            error_code=error_code,
            details={
                'account_id': account_id,
                'table_name': DYNAMODB_TABLE_NAME
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error creating metadata record: {str(e)}")
        raise MetadataUpdateError(
            f"Unexpected error creating metadata record: {str(e)}",
            error_code="CREATE_RECORD_ERROR"
        )

def update_existing_metadata_record(
    dynamodb_client,
    account_id: str,
    termination_status: str,
    execution_arn: str,
    timestamp: str,
    pre_check_results: Optional[Dict] = None,
    account_management_results: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Update existing account metadata record in DynamoDB
    
    Args:
        dynamodb_client: DynamoDB client
        account_id: Account ID
        termination_status: Current termination status
        execution_arn: Step Function execution ARN
        timestamp: Current timestamp
        pre_check_results: Results from pre-check stage
        account_management_results: Results from account management stage
        
    Returns:
        Dict: DynamoDB response
        
    Raises:
        MetadataUpdateError: If DynamoDB operation fails
    """
    try:
        logger.info(f"Updating existing metadata record for account {account_id}")
        
        # Build update expression and attribute values
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}
        
        # Always update status, executionArn, and updatedAt
        update_expression_parts.append('#status = :status')
        update_expression_parts.append('executionArn = :executionArn')
        update_expression_parts.append('updatedAt = :updatedAt')
        
        expression_attribute_names['#status'] = 'status'
        expression_attribute_values[':status'] = {'S': termination_status}
        expression_attribute_values[':executionArn'] = {'S': execution_arn}
        expression_attribute_values[':updatedAt'] = {'S': timestamp}
        
        # Add termination timestamps based on status
        if termination_status == 'TERMINATING':
            update_expression_parts.append('terminationInitiated = :terminationInitiated')
            expression_attribute_values[':terminationInitiated'] = {'S': timestamp}
        elif termination_status == 'TERMINATED':
            update_expression_parts.append('terminationCompleted = :terminationCompleted')
            expression_attribute_values[':terminationCompleted'] = {'S': timestamp}
        
        # Add pre-check results if provided
        if pre_check_results:
            update_expression_parts.append('preCheckResults = :preCheckResults')
            expression_attribute_values[':preCheckResults'] = {
                'M': {
                    'ebsVolumes': {'N': str(pre_check_results.get('ebsVolumes', 0))},
                    'rdsInstances': {'N': str(pre_check_results.get('rdsInstances', 0))},
                    'safeToTerminate': {'BOOL': pre_check_results.get('safeToTerminate', False)}
                }
            }
        
        # Add account management results if provided
        if account_management_results:
            update_expression_parts.append('organizationalUnit = :organizationalUnit')
            expression_attribute_values[':organizationalUnit'] = {
                'S': account_management_results.get('organizationalUnit', '')
            }
        
        update_expression = 'SET ' + ', '.join(update_expression_parts)
        
        # Perform the update
        response = dynamodb_client.update_item(
            TableName=DYNAMODB_TABLE_NAME,
            Key={'accountId': {'S': account_id}},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues='ALL_NEW'
        )
        
        logger.info(f"Successfully updated metadata record for account {account_id}")
        return response
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"DynamoDB update_item failed: {error_code} - {error_message}")
        
        raise MetadataUpdateError(
            f"Failed to update metadata record: {error_message}",
            error_code=error_code,
            details={
                'account_id': account_id,
                'table_name': DYNAMODB_TABLE_NAME
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error updating metadata record: {str(e)}")
        raise MetadataUpdateError(
            f"Unexpected error updating metadata record: {str(e)}",
            error_code="UPDATE_RECORD_ERROR"
        )

def update_metadata_with_retry(
    account_id: str,
    termination_status: str,
    execution_arn: str,
    timestamp: str,
    pre_check_results: Optional[Dict] = None,
    account_management_results: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Update metadata with retry logic and exponential backoff
    
    Args:
        account_id: Account ID
        termination_status: Current termination status
        execution_arn: Step Function execution ARN
        timestamp: Current timestamp
        pre_check_results: Results from pre-check stage
        account_management_results: Results from account management stage
        
    Returns:
        Dict: DynamoDB response
        
    Raises:
        MetadataUpdateError: If all retry attempts fail
    """
    dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
    
    last_exception = None
    
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            logger.info(f"Metadata update attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} for account {account_id}")
            
            response = create_metadata_record(
                dynamodb_client,
                account_id,
                termination_status,
                execution_arn,
                timestamp,
                pre_check_results,
                account_management_results
            )
            
            logger.info(f"Metadata update successful on attempt {attempt + 1} for account {account_id}")
            return response
            
        except MetadataUpdateError as e:
            last_exception = e
            
            # Don't retry for certain error types
            non_retryable_errors = [
                'INVALID_INPUT_TYPE',
                'MISSING_ACCOUNT_ID',
                'INVALID_ACCOUNT_ID_TYPE',
                'INVALID_ACCOUNT_ID_FORMAT',
                'INVALID_TERMINATION_STATUS_TYPE',
                'INVALID_TERMINATION_STATUS_VALUE',
                'INVALID_EXECUTION_ARN_TYPE'
            ]
            
            if e.error_code in non_retryable_errors:
                logger.error(f"Non-retryable error on attempt {attempt + 1}: {e.message}")
                raise e
            
            # Check if this is the last attempt
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                logger.error(f"All retry attempts exhausted for account {account_id}")
                break
            
            # Calculate backoff delay
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Metadata update failed on attempt {attempt + 1}, retrying in {delay:.2f} seconds: {e.message}")
            
            time.sleep(delay)
            
        except Exception as e:
            last_exception = MetadataUpdateError(
                f"Unexpected error during metadata update: {str(e)}",
                error_code="UNEXPECTED_ERROR"
            )
            
            # Check if this is the last attempt
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                logger.error(f"All retry attempts exhausted for account {account_id}")
                break
            
            # Calculate backoff delay
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Unexpected error on attempt {attempt + 1}, retrying in {delay:.2f} seconds: {str(e)}")
            
            time.sleep(delay)
    
    # If we get here, all retries failed
    logger.error(f"Metadata update failed after {MAX_RETRY_ATTEMPTS} attempts for account {account_id}")
    raise last_exception

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Main Lambda handler for metadata update operations
    
    Args:
        event: Lambda event containing accountId, terminationStatus, and executionArn
        context: Lambda context object
        
    Returns:
        Dict containing operation results
    """
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    try:
        logger.info(f"Metadata Update Lambda started at {timestamp}")
        logger.info(f"Event: {json.dumps(event)}")
        
        # Validate environment variables
        if not DYNAMODB_TABLE_NAME:
            raise MetadataUpdateError(
                "Missing environment variable: DYNAMODB_TABLE_NAME",
                error_code="MISSING_ENV_VAR"
            )
        
        # Validate input
        account_id, termination_status, execution_arn = validate_input(event)
        
        # Extract additional data from event if present
        pre_check_results = event.get('preCheckResults')
        account_management_results = event.get('accountManagementResults')
        
        # Update metadata with retry logic
        dynamodb_response = update_metadata_with_retry(
            account_id,
            termination_status,
            execution_arn,
            timestamp,
            pre_check_results,
            account_management_results
        )
        
        # Prepare successful response
        response = {
            'accountId': account_id,
            'recordUpdated': True,
            'timestamp': timestamp
        }
        
        logger.info(f"Metadata update completed successfully: {json.dumps(response)}")
        return response
        
    except MetadataUpdateError as e:
        logger.error(f"Metadata update error: {e.message}")
        
        # Return error response
        error_response = {
            'accountId': event.get('accountId', 'unknown'),
            'recordUpdated': False,
            'timestamp': timestamp,
            'error': {
                'code': e.error_code,
                'message': e.message,
                'details': e.details
            }
        }
        
        # Re-raise the exception to trigger Step Function error handling
        raise Exception(json.dumps(error_response))
        
    except Exception as e:
        logger.error(f"Unexpected error in metadata update: {str(e)}")
        
        # Return generic error response
        error_response = {
            'accountId': event.get('accountId', 'unknown'),
            'recordUpdated': False,
            'timestamp': timestamp,
            'error': {
                'code': 'UNEXPECTED_ERROR',
                'message': str(e),
                'details': {}
            }
        }
        
        # Re-raise the exception to trigger Step Function error handling
        raise Exception(json.dumps(error_response))