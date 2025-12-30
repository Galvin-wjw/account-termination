import { AwsServiceConfig, VpcConfig } from './interfaces';

/**
 * AWS Service Configuration Utilities
 * Centralized configuration management for AWS services
 */

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