"""
Account Management Lambda Function
Handles account suspension and closure through AWS Organizations

This Lambda function:
1. Assumes a role in the Management Account
2. Moves the target account to the Suspended OU
3. Initiates the account closure process
4. Returns confirmation of operations

Requirements: 3.1, 3.2, 3.3, 8.1
"""

import json
import os
import boto3
import logging
from datetime import datetime
from typing import Dict, Any
from botocore.exceptions import ClientError, BotoCoreError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
MANAGEMENT_ACCOUNT_ROLE_ARN = os.environ.get('MANAGEMENT_ACCOUNT_ROLE_ARN')
SUSPENDED_OU_ID = os.environ.get('SUSPENDED_OU_ID')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

class AccountManagementError(Exception):
    """Custom exception for account management operations"""
    def __init__(self, message: str, error_code: str = None, details: Dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

def assume_management_role(role_arn: str, session_name: str) -> boto3.Session:
    """
    Assume role in the management account
    
    Args:
        role_arn: ARN of the role to assume
        session_name: Name for the assumed role session
        
    Returns:
        boto3.Session: Session with assumed role credentials
        
    Raises:
        AccountManagementError: If role assumption fails
    """
    try:
        sts_client = boto3.client('sts', region_name=AWS_REGION)
        
        logger.info(f"Assuming management account role: {role_arn}")
        
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=3600  # 1 hour
        )
        
        credentials = response['Credentials']
        
        # Create session with assumed role credentials
        session = boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=AWS_REGION
        )
        
        logger.info("Successfully assumed management account role")
        return session
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"Failed to assume management role: {error_code} - {error_message}")
        
        raise AccountManagementError(
            f"Failed to assume management account role: {error_message}",
            error_code=error_code,
            details={'role_arn': role_arn}
        )
    except Exception as e:
        logger.error(f"Unexpected error assuming management role: {str(e)}")
        raise AccountManagementError(
            f"Unexpected error assuming management role: {str(e)}",
            error_code="ASSUME_ROLE_ERROR"
        )

def move_account_to_suspended_ou(organizations_client, account_id: str, suspended_ou_id: str) -> str:
    """
    Move account to the Suspended OU
    
    Args:
        organizations_client: AWS Organizations client
        account_id: ID of the account to move
        suspended_ou_id: ID of the Suspended OU
        
    Returns:
        str: The OU ID where the account was moved
        
    Raises:
        AccountManagementError: If account movement fails
    """
    try:
        logger.info(f"Moving account {account_id} to Suspended OU {suspended_ou_id}")
        
        # First, get the current parent of the account
        response = organizations_client.list_parents(ChildId=account_id)
        current_parents = response['Parents']
        
        if not current_parents:
            raise AccountManagementError(
                f"No parent found for account {account_id}",
                error_code="NO_PARENT_FOUND"
            )
        
        current_parent = current_parents[0]  # Account should have only one parent
        current_parent_id = current_parent['Id']
        
        logger.info(f"Current parent of account {account_id}: {current_parent_id}")
        
        # Check if account is already in the Suspended OU
        if current_parent_id == suspended_ou_id:
            logger.info(f"Account {account_id} is already in Suspended OU")
            return suspended_ou_id
        
        # Move the account to the Suspended OU
        organizations_client.move_account(
            AccountId=account_id,
            SourceParentId=current_parent_id,
            DestinationParentId=suspended_ou_id
        )
        
        logger.info(f"Successfully moved account {account_id} to Suspended OU {suspended_ou_id}")
        return suspended_ou_id
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"Failed to move account to Suspended OU: {error_code} - {error_message}")
        
        raise AccountManagementError(
            f"Failed to move account to Suspended OU: {error_message}",
            error_code=error_code,
            details={
                'account_id': account_id,
                'suspended_ou_id': suspended_ou_id
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error moving account to Suspended OU: {str(e)}")
        raise AccountManagementError(
            f"Unexpected error moving account to Suspended OU: {str(e)}",
            error_code="MOVE_ACCOUNT_ERROR"
        )

def initiate_account_closure(organizations_client, account_id: str) -> bool:
    """
    Initiate account closure process
    
    Args:
        organizations_client: AWS Organizations client
        account_id: ID of the account to close
        
    Returns:
        bool: True if closure was initiated successfully
        
    Raises:
        AccountManagementError: If account closure initiation fails
    """
    try:
        logger.info(f"Initiating closure for account {account_id}")
        
        # Close the account
        organizations_client.close_account(AccountId=account_id)
        
        logger.info(f"Successfully initiated closure for account {account_id}")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"Failed to initiate account closure: {error_code} - {error_message}")
        
        # Some errors might be acceptable (e.g., account already closed)
        if error_code in ['AccountAlreadyClosedException', 'AccountNotActiveException']:
            logger.warning(f"Account {account_id} closure already initiated or account not active")
            return True
        
        raise AccountManagementError(
            f"Failed to initiate account closure: {error_message}",
            error_code=error_code,
            details={'account_id': account_id}
        )
    except Exception as e:
        logger.error(f"Unexpected error initiating account closure: {str(e)}")
        raise AccountManagementError(
            f"Unexpected error initiating account closure: {str(e)}",
            error_code="CLOSE_ACCOUNT_ERROR"
        )

def validate_input(event: Dict[str, Any]) -> str:
    """
    Validate input parameters
    
    Args:
        event: Lambda event containing input parameters
        
    Returns:
        str: Validated account ID
        
    Raises:
        AccountManagementError: If input validation fails
    """
    if not isinstance(event, dict):
        raise AccountManagementError(
            "Invalid input: event must be a dictionary",
            error_code="INVALID_INPUT_TYPE"
        )
    
    account_id = event.get('accountId')
    if not account_id:
        raise AccountManagementError(
            "Missing required parameter: accountId",
            error_code="MISSING_ACCOUNT_ID"
        )
    
    if not isinstance(account_id, str):
        raise AccountManagementError(
            "Invalid accountId: must be a string",
            error_code="INVALID_ACCOUNT_ID_TYPE"
        )
    
    # Validate account ID format (12 digits)
    if not account_id.isdigit() or len(account_id) != 12:
        raise AccountManagementError(
            f"Invalid accountId format: {account_id}. Must be 12 digits",
            error_code="INVALID_ACCOUNT_ID_FORMAT"
        )
    
    return account_id

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Main Lambda handler for account management operations
    
    Args:
        event: Lambda event containing accountId
        context: Lambda context object
        
    Returns:
        Dict containing operation results
    """
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    try:
        logger.info(f"Account Management Lambda started at {timestamp}")
        logger.info(f"Event: {json.dumps(event)}")
        
        # Validate input
        account_id = validate_input(event)
        
        # Validate environment variables
        if not MANAGEMENT_ACCOUNT_ROLE_ARN:
            raise AccountManagementError(
                "Missing environment variable: MANAGEMENT_ACCOUNT_ROLE_ARN",
                error_code="MISSING_ENV_VAR"
            )
        
        if not SUSPENDED_OU_ID:
            raise AccountManagementError(
                "Missing environment variable: SUSPENDED_OU_ID",
                error_code="MISSING_ENV_VAR"
            )
        
        # Assume management account role
        session_name = f"AccountTermination-{account_id}-{int(datetime.utcnow().timestamp())}"
        management_session = assume_management_role(MANAGEMENT_ACCOUNT_ROLE_ARN, session_name)
        
        # Create Organizations client with assumed role
        organizations_client = management_session.client('organizations')
        
        # Move account to Suspended OU
        organizational_unit = move_account_to_suspended_ou(
            organizations_client, 
            account_id, 
            SUSPENDED_OU_ID
        )
        
        # Initiate account closure
        closure_initiated = initiate_account_closure(organizations_client, account_id)
        
        # Prepare successful response
        response = {
            'accountId': account_id,
            'suspended': True,
            'closureInitiated': closure_initiated,
            'organizationalUnit': organizational_unit,
            'timestamp': timestamp
        }
        
        logger.info(f"Account management completed successfully: {json.dumps(response)}")
        return response
        
    except AccountManagementError as e:
        logger.error(f"Account management error: {e.message}")
        
        # Return error response
        error_response = {
            'accountId': event.get('accountId', 'unknown'),
            'suspended': False,
            'closureInitiated': False,
            'organizationalUnit': '',
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
        logger.error(f"Unexpected error in account management: {str(e)}")
        
        # Return generic error response
        error_response = {
            'accountId': event.get('accountId', 'unknown'),
            'suspended': False,
            'closureInitiated': False,
            'organizationalUnit': '',
            'timestamp': timestamp,
            'error': {
                'code': 'UNEXPECTED_ERROR',
                'message': str(e),
                'details': {}
            }
        }
        
        # Re-raise the exception to trigger Step Function error handling
        raise Exception(json.dumps(error_response))