#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AccountTerminationStack } from './stack';

const app = new cdk.App();

// Get required configuration from environment variables
const vpcId = process.env.VPC_ID;
const dynamoDbTableName = process.env.DYNAMODB_TABLE_NAME;

if (!vpcId) {
  throw new Error('VPC_ID environment variable is required');
}

if (!dynamoDbTableName) {
  throw new Error('DYNAMODB_TABLE_NAME environment variable is required');
}

new AccountTerminationStack(app, 'AccountTerminationStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID,
    region: process.env.CDK_DEFAULT_REGION || process.env.AWS_REGION || 'us-east-1',
  },
  vpcId,
  dynamoDbTableName,
  managementAccountRoleArn: process.env.MANAGEMENT_ACCOUNT_ROLE_ARN,
  suspendedOuId: process.env.SUSPENDED_OU_ID,
  notificationEmail: process.env.NOTIFICATION_EMAIL,
  environment: (process.env.ENVIRONMENT as 'dev' | 'staging' | 'prod') || 'prod'
});