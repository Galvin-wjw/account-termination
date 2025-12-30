/**
 * AWS Account Termination Configuration
 * Centralized configuration management with environment variable support
 */

// Configuration Interfaces
export interface VpcConfig {
  vpcId: string;
  privateSubnetIds: string[];
  securityGroupIds: string[];
  natGatewayId?: string;
}

export interface AwsServiceConfig {
  region: string;
  managementAccountRoleArn: string;
  suspendedOuId: string;
  dynamoDbTableName: string;
}

// Lambda Function Interfaces (for testing)
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

export interface AccountMetadata {
  accountId: string;
  status: 'ACTIVE' | 'TERMINATING' | 'TERMINATED' | 'FAILED';
  terminationInitiated: string;
  terminationCompleted?: string;
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

export interface TerminationError {
  code: string;
  message: string;
  details?: any;
  timestamp: string;
  stage: string;
}

export class AwsConfigManager {
  private static instance: AwsConfigManager;
  private config: AwsServiceConfig;

  private constructor() {
    this.config = {
      region: process.env.AWS_REGION || 'us-east-1',
      managementAccountRoleArn: process.env.MANAGEMENT_ACCOUNT_ROLE_ARN || '',
      suspendedOuId: process.env.SUSPENDED_OU_ID || '',
      dynamoDbTableName: process.env.DYNAMODB_TABLE_NAME || 'account-termination-metadata'
    };
  }

  public static getInstance(): AwsConfigManager {
    if (!AwsConfigManager.instance) {
      AwsConfigManager.instance = new AwsConfigManager();
    }
    return AwsConfigManager.instance;
  }

  public getConfig(): AwsServiceConfig {
    return this.config;
  }

  public validateConfig(): boolean {
    return !!(
      this.config.region &&
      this.config.managementAccountRoleArn &&
      this.config.suspendedOuId &&
      this.config.dynamoDbTableName
    );
  }
}

export const getVpcConfig = (): VpcConfig => {
  return {
    vpcId: process.env.VPC_ID || '',
    privateSubnetIds: (process.env.PRIVATE_SUBNET_IDS || '').split(',').filter(id => id.trim()),
    securityGroupIds: (process.env.SECURITY_GROUP_IDS || '').split(',').filter(id => id.trim()),
    natGatewayId: process.env.NAT_GATEWAY_ID
  };
};

/**
 * Centralized logging utility for AWS Account Termination Solution
 * Provides structured logging with correlation IDs for audit trails
 */

export interface LogContext {
  correlationId: string;
  accountId?: string;
  stage?: string;
  executionArn?: string;
}

export enum LogLevel {
  ERROR = 'ERROR',
  WARN = 'WARN',
  INFO = 'INFO',
  DEBUG = 'DEBUG'
}

export class Logger {
  private context: LogContext;

  constructor(context: LogContext) {
    this.context = context;
  }

  private log(level: LogLevel, message: string, data?: any): void {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      context: this.context,
      data
    };

    console.log(JSON.stringify(logEntry));
  }

  public error(message: string, error?: Error | any): void {
    this.log(LogLevel.ERROR, message, error);
  }

  public warn(message: string, data?: any): void {
    this.log(LogLevel.WARN, message, data);
  }

  public info(message: string, data?: any): void {
    this.log(LogLevel.INFO, message, data);
  }

  public debug(message: string, data?: any): void {
    this.log(LogLevel.DEBUG, message, data);
  }

  public updateContext(updates: Partial<LogContext>): void {
    this.context = { ...this.context, ...updates };
  }
}

export const createLogger = (context: LogContext): Logger => {
  return new Logger(context);
};