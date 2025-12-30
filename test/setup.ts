/**
 * Jest test setup configuration
 * Configures testing environment for AWS Account Termination Solution
 */

// Mock AWS SDK to prevent actual AWS calls during testing
jest.mock('aws-sdk', () => ({
  EC2: jest.fn(() => ({
    describeVolumes: jest.fn(),
    describeInstances: jest.fn()
  })),
  RDS: jest.fn(() => ({
    describeDBInstances: jest.fn(),
    describeDBClusters: jest.fn()
  })),
  Organizations: jest.fn(() => ({
    moveAccount: jest.fn(),
    closeAccount: jest.fn()
  })),
  DynamoDB: {
    DocumentClient: jest.fn(() => ({
      put: jest.fn(),
      update: jest.fn(),
      get: jest.fn()
    }))
  },
  STS: jest.fn(() => ({
    assumeRole: jest.fn()
  }))
}));

// Set up environment variables for testing
process.env.AWS_REGION = 'us-east-1';
process.env.MANAGEMENT_ACCOUNT_ROLE_ARN = 'arn:aws:iam::123456789012:role/TestRole';
process.env.SUSPENDED_OU_ID = 'ou-test-suspended';
process.env.DYNAMODB_TABLE_NAME = 'test-account-termination-metadata';
process.env.VPC_ID = 'vpc-test123';
process.env.PRIVATE_SUBNET_IDS = 'subnet-test1,subnet-test2';
process.env.SECURITY_GROUP_IDS = 'sg-test123';

// Global test timeout
jest.setTimeout(30000);