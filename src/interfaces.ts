/**
 * Core interfaces for AWS Account Termination Solution
 * These interfaces define the input/output contracts for all Lambda functions
 */

// Pre-Check Lambda Interfaces
export interface PreCheckInput {
  accountId: string;
}

export interface PreCheckOutput {
  accountId: string;
  safeToTerminate: boolean;
  resourcesFound: {
    ebsVolumes: number;
    rdsInstances: number;
  };
  timestamp: string;
}

// Account Management Lambda Interfaces
export interface AccountManagementInput {
  accountId: string;
}

export interface AccountManagementOutput {
  accountId: string;
  suspended: boolean;
  closureInitiated: boolean;
  organizationalUnit: string;
  timestamp: string;
}

// Metadata Update Lambda Interfaces
export interface MetadataUpdateInput {
  accountId: string;
  terminationStatus: string;
  executionArn: string;
}

export interface MetadataUpdateOutput {
  accountId: string;
  recordUpdated: boolean;
  timestamp: string;
}

// Decommission Lambda Interfaces
export interface DecommissionInput {
  accountId: string;
}

export interface DecommissionOutput {
  accountId: string;
  vendorsProcessed: string[];
  results: {
    [vendor: string]: {
      success: boolean;
      message: string;
    };
  };
  timestamp: string;
}

// Step Function Execution Context
export interface ExecutionContext {
  accountId: string;
  executionArn: string;
  startTime: string;
  currentStage: string;
  results: {
    preCheck?: PreCheckOutput;
    accountManagement?: AccountManagementOutput;
    metadataUpdate?: MetadataUpdateOutput;
    decommission?: DecommissionOutput;
  };
}

// DynamoDB Account Metadata Model
export interface AccountMetadata {
  accountId: string; // Partition Key
  status: 'ACTIVE' | 'TERMINATING' | 'TERMINATED' | 'FAILED';
  terminationInitiated: string; // ISO timestamp
  terminationCompleted?: string; // ISO timestamp
  executionArn: string;
  preCheckResults: {
    ebsVolumes: number;
    rdsInstances: number;
    safeToTerminate: boolean;
  };
  organizationalUnit: string;
  vendorDecommissionResults: {
    [vendor: string]: {
      success: boolean;
      message: string;
      timestamp: string;
    };
  };
  createdAt: string;
  updatedAt: string;
}

// Common Error Interface
export interface TerminationError {
  code: string;
  message: string;
  details?: any;
  timestamp: string;
  stage: string;
}

// VPC Configuration Interface
export interface VpcConfig {
  vpcId: string;
  privateSubnetIds: string[];
  securityGroupIds: string[];
  natGatewayId?: string;
}

// AWS Service Configuration
export interface AwsServiceConfig {
  region: string;
  managementAccountRoleArn: string;
  suspendedOuId: string;
  dynamoDbTableName: string;
}

// Vendor Configuration
export interface VendorConfig {
  prisma: {
    apiEndpoint: string;
    apiKey: string;
    timeout: number;
  };
}

// Lambda Function Configuration
export interface LambdaConfig {
  runtime: string;
  timeout: number;
  memorySize: number;
  environment: {
    [key: string]: string;
  };
}