/**
 * Unit tests for TypeScript interfaces
 * Validates interface structure and type safety
 */

import {
  PreCheckInput,
  PreCheckOutput,
  AccountManagementInput,
  AccountManagementOutput,
  MetadataUpdateInput,
  MetadataUpdateOutput,
  DecommissionInput,
  DecommissionOutput,
  ExecutionContext,
  AccountMetadata,
  TerminationError
} from '../src/interfaces';

describe('Interface Type Validation', () => {
  describe('PreCheck Interfaces', () => {
    it('should validate PreCheckInput structure', () => {
      const input: PreCheckInput = {
        accountId: '123456789012'
      };
      
      expect(input.accountId).toBe('123456789012');
      expect(typeof input.accountId).toBe('string');
    });

    it('should validate PreCheckOutput structure', () => {
      const output: PreCheckOutput = {
        accountId: '123456789012',
        safeToTerminate: true,
        resourcesFound: {
          ebsVolumes: 0,
          rdsInstances: 0
        },
        timestamp: new Date().toISOString()
      };

      expect(output.accountId).toBe('123456789012');
      expect(typeof output.safeToTerminate).toBe('boolean');
      expect(typeof output.resourcesFound.ebsVolumes).toBe('number');
      expect(typeof output.resourcesFound.rdsInstances).toBe('number');
      expect(typeof output.timestamp).toBe('string');
    });
  });

  describe('AccountManagement Interfaces', () => {
    it('should validate AccountManagementInput structure', () => {
      const input: AccountManagementInput = {
        accountId: '123456789012'
      };
      
      expect(input.accountId).toBe('123456789012');
    });

    it('should validate AccountManagementOutput structure', () => {
      const output: AccountManagementOutput = {
        accountId: '123456789012',
        suspended: true,
        closureInitiated: true,
        organizationalUnit: 'ou-suspended-123',
        timestamp: new Date().toISOString()
      };

      expect(typeof output.suspended).toBe('boolean');
      expect(typeof output.closureInitiated).toBe('boolean');
      expect(typeof output.organizationalUnit).toBe('string');
    });
  });

  describe('MetadataUpdate Interfaces', () => {
    it('should validate MetadataUpdateInput structure', () => {
      const input: MetadataUpdateInput = {
        accountId: '123456789012',
        terminationStatus: 'TERMINATING',
        executionArn: 'arn:aws:states:us-east-1:123456789012:execution:test'
      };
      
      expect(input.terminationStatus).toBe('TERMINATING');
      expect(input.executionArn).toContain('execution');
    });
  });

  describe('Decommission Interfaces', () => {
    it('should validate DecommissionOutput structure', () => {
      const output: DecommissionOutput = {
        accountId: '123456789012',
        vendorsProcessed: ['prisma'],
        results: {
          prisma: {
            success: true,
            message: 'Successfully decommissioned'
          }
        },
        timestamp: new Date().toISOString()
      };

      expect(Array.isArray(output.vendorsProcessed)).toBe(true);
      expect(typeof output.results.prisma.success).toBe('boolean');
    });
  });

  describe('AccountMetadata Interface', () => {
    it('should validate AccountMetadata structure', () => {
      const metadata: AccountMetadata = {
        accountId: '123456789012',
        status: 'TERMINATING',
        terminationInitiated: new Date().toISOString(),
        executionArn: 'arn:aws:states:us-east-1:123456789012:execution:test',
        preCheckResults: {
          ebsVolumes: 0,
          rdsInstances: 0,
          safeToTerminate: true
        },
        organizationalUnit: 'ou-suspended-123',
        vendorDecommissionResults: {},
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };

      expect(['ACTIVE', 'TERMINATING', 'TERMINATED', 'FAILED']).toContain(metadata.status);
      expect(typeof metadata.preCheckResults.safeToTerminate).toBe('boolean');
    });
  });
});