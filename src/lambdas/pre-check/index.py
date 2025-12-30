import json
import boto3
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Pre-Check Lambda Function
    Validates account state before termination by scanning for critical resources
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
    """
    correlation_id = context.aws_request_id
    account_id = event.get('accountId')
    
    logger.info(f"Pre-Check Lambda started - CorrelationId: {correlation_id}, AccountId: {account_id}")
    
    try:
        # Input validation
        if not account_id or not isinstance(account_id, str):
            raise ValueError("Invalid or missing accountId in input")
        
        # Validate account ID format (12-digit AWS account ID)
        if not re.match(r'^\d{12}$', account_id):
            raise ValueError(f"Invalid account ID format: {account_id}. Must be 12 digits.")
        
        logger.info(f"Input validation passed - AccountId: {account_id}")
        
        # Assume role in target account for resource scanning
        sts_client = boto3.client('sts')
        role_arn = f"arn:aws:iam::{account_id}:role/AccountTerminationRole"
        
        try:
            assume_role_response = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"PreCheck-{correlation_id}",
                DurationSeconds=3600
            )
            
            credentials = assume_role_response['Credentials']
            
        except ClientError as e:
            error_msg = f"Cannot assume role in account {account_id}: {str(e)}"
            logger.error(f"Failed to assume role - {error_msg}")
            raise Exception(error_msg)
        
        # Initialize AWS clients with assumed role credentials
        session = boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
        
        ec2_client = session.client('ec2')
        rds_client = session.client('rds')
        
        # Scan for EBS volumes
        logger.info(f"Scanning for EBS volumes - AccountId: {account_id}")
        ebs_volume_count = 0
        
        try:
            volumes_response = ec2_client.describe_volumes()
            ebs_volume_count = len(volumes_response.get('Volumes', []))
            logger.info(f"EBS volume scan completed - AccountId: {account_id}, Count: {ebs_volume_count}")
            
        except ClientError as e:
            error_msg = f"Failed to scan EBS volumes: {str(e)}"
            logger.error(f"EBS scan failed - {error_msg}")
            raise Exception(error_msg)
        
        # Scan for RDS instances
        logger.info(f"Scanning for RDS instances - AccountId: {account_id}")
        rds_instance_count = 0
        
        try:
            instances_response = rds_client.describe_db_instances()
            rds_instance_count = len(instances_response.get('DBInstances', []))
            logger.info(f"RDS instance scan completed - AccountId: {account_id}, Count: {rds_instance_count}")
            
        except ClientError as e:
            error_msg = f"Failed to scan RDS instances: {str(e)}"
            logger.error(f"RDS scan failed - {error_msg}")
            raise Exception(error_msg)
        
        # Determine if account is safe to terminate
        safe_to_terminate = ebs_volume_count == 0 and rds_instance_count == 0
        
        result = {
            'accountId': account_id,
            'safeToTerminate': safe_to_terminate,
            'resourcesFound': {
                'ebsVolumes': ebs_volume_count,
                'rdsInstances': rds_instance_count
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        if not safe_to_terminate:
            logger.warning(f"Safety violation detected - AccountId: {account_id}, "
                         f"EBS: {ebs_volume_count}, RDS: {rds_instance_count}")
        else:
            logger.info(f"Pre-check completed successfully - Account safe to terminate: {account_id}")
        
        return result
        
    except Exception as e:
        error_details = {
            'code': 'PRE_CHECK_FAILED',
            'message': str(e),
            'details': {
                'accountId': account_id,
                'correlationId': correlation_id
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'stage': 'PRE_CHECK'
        }
        
        logger.error(f"Pre-Check Lambda failed - {json.dumps(error_details)}")
        raise e


def validate_input(event: Dict[str, Any]) -> str:
    """
    Validates the input event and returns the account ID
    """
    account_id = event.get('accountId')
    
    if not account_id or not isinstance(account_id, str):
        raise ValueError("Invalid or missing accountId in input")
    
    if not re.match(r'^\d{12}$', account_id):
        raise ValueError(f"Invalid account ID format: {account_id}. Must be 12 digits.")
    
    return account_id


def scan_ebs_volumes(ec2_client) -> int:
    """
    Scans for EBS volumes in the target account
    Returns the count of EBS volumes found
    """
    try:
        response = ec2_client.describe_volumes()
        return len(response.get('Volumes', []))
    except ClientError as e:
        raise Exception(f"Failed to scan EBS volumes: {str(e)}")


def scan_rds_instances(rds_client) -> int:
    """
    Scans for RDS instances in the target account
    Returns the count of RDS instances found
    """
    try:
        response = rds_client.describe_db_instances()
        return len(response.get('DBInstances', []))
    except ClientError as e:
        raise Exception(f"Failed to scan RDS instances: {str(e)}")


def assume_target_account_role(account_id: str, correlation_id: str) -> Dict[str, str]:
    """
    Assumes the AccountTerminationRole in the target account
    Returns the temporary credentials
    """
    sts_client = boto3.client('sts')
    role_arn = f"arn:aws:iam::{account_id}:role/AccountTerminationRole"
    
    try:
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f"PreCheck-{correlation_id}",
            DurationSeconds=3600
        )
        return response['Credentials']
    except ClientError as e:
        raise Exception(f"Cannot assume role in account {account_id}: {str(e)}")