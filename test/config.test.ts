/**
 * Unit tests for AWS configuration utilities and logging
 */

import { AwsConfigManager, getVpcConfig, Logger, createLogger, LogLevel } from '../src/config';

describe('AwsConfigManager', () => {
  let configManager: AwsConfigManager;

  beforeEach(() => {
    configManager = AwsConfigManager.getInstance();
  });

  it('should return singleton instance', () => {
    const instance1 = AwsConfigManager.getInstance();
    const instance2 = AwsConfigManager.getInstance();
    
    expect(instance1).toBe(instance2);
  });

  it('should return valid configuration', () => {
    const config = configManager.getConfig();
    
    expect(config).toHaveProperty('region');
    expect(config).toHaveProperty('managementAccountRoleArn');
    expect(config).toHaveProperty('suspendedOuId');
    expect(config).toHaveProperty('dynamoDbTableName');
  });

  it('should validate configuration correctly', () => {
    const isValid = configManager.validateConfig();
    
    // Should be true since we set environment variables in setup.ts
    expect(isValid).toBe(true);
  });
});

describe('getVpcConfig', () => {
  it('should return VPC configuration from environment variables', () => {
    const vpcConfig = getVpcConfig();
    
    expect(vpcConfig).toHaveProperty('vpcId');
    expect(vpcConfig).toHaveProperty('privateSubnetIds');
    expect(vpcConfig).toHaveProperty('securityGroupIds');
    expect(Array.isArray(vpcConfig.privateSubnetIds)).toBe(true);
    expect(Array.isArray(vpcConfig.securityGroupIds)).toBe(true);
  });

  it('should handle comma-separated subnet IDs', () => {
    const vpcConfig = getVpcConfig();
    
    expect(vpcConfig.privateSubnetIds).toContain('subnet-test1');
    expect(vpcConfig.privateSubnetIds).toContain('subnet-test2');
  });
});

// Mock console.log to capture log output
const mockConsoleLog = jest.spyOn(console, 'log').mockImplementation();

describe('Logger', () => {
  let logger: Logger;
  const testContext = {
    correlationId: 'test-correlation-id',
    accountId: '123456789012',
    stage: 'pre-check'
  };

  beforeEach(() => {
    logger = createLogger(testContext);
    mockConsoleLog.mockClear();
  });

  afterAll(() => {
    mockConsoleLog.mockRestore();
  });

  it('should create logger with context', () => {
    expect(logger).toBeInstanceOf(Logger);
  });

  it('should log error messages', () => {
    const errorMessage = 'Test error message';
    const error = new Error('Test error');
    
    logger.error(errorMessage, error);
    
    expect(mockConsoleLog).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(mockConsoleLog.mock.calls[0][0]);
    
    expect(loggedData.level).toBe(LogLevel.ERROR);
    expect(loggedData.message).toBe(errorMessage);
    expect(loggedData.context).toEqual(testContext);
    expect(loggedData.data).toBeDefined();
  });

  it('should log info messages', () => {
    const infoMessage = 'Test info message';
    const data = { key: 'value' };
    
    logger.info(infoMessage, data);
    
    expect(mockConsoleLog).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(mockConsoleLog.mock.calls[0][0]);
    
    expect(loggedData.level).toBe(LogLevel.INFO);
    expect(loggedData.message).toBe(infoMessage);
    expect(loggedData.data).toEqual(data);
  });

  it('should update context', () => {
    const updates = { stage: 'account-management', executionArn: 'test-arn' };
    
    logger.updateContext(updates);
    logger.info('Test message');
    
    const loggedData = JSON.parse(mockConsoleLog.mock.calls[0][0]);
    expect(loggedData.context.stage).toBe('account-management');
    expect(loggedData.context.executionArn).toBe('test-arn');
    expect(loggedData.context.correlationId).toBe(testContext.correlationId);
  });

  it('should include timestamp in log entries', () => {
    logger.info('Test message');
    
    const loggedData = JSON.parse(mockConsoleLog.mock.calls[0][0]);
    expect(loggedData.timestamp).toBeDefined();
    expect(new Date(loggedData.timestamp)).toBeInstanceOf(Date);
  });
});