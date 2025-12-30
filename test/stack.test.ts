import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { AccountTerminationStack } from '../src/stack';

describe('AccountTerminationStack', () => {
  let app: cdk.App;
  let stack: AccountTerminationStack;
  let template: Template;

  beforeEach(() => {
    app = new cdk.App();
    stack = new AccountTerminationStack(app, 'TestStack');
    template = Template.fromStack(stack);
  });

  describe('Step Functions State Machine', () => {
    it('should create Step Functions state machine with correct properties', () => {
      template.hasResourceProperties('AWS::StepFunctions::StateMachine', {
        StateMachineName: 'AccountTermination-Workflow-prod',
        TracingConfiguration: {
          Enabled: true
        },
        LoggingConfiguration: {
          Level: 'ALL',
          IncludeExecutionData: true
        }
      });
    });

    it('should create CloudWatch log group for Step Functions', () => {
      template.hasResourceProperties('AWS::Logs::LogGroup', {
        LogGroupName: '/aws/stepfunctions/AccountTermination-prod',
        RetentionInDays: 90
      });
    });

    it('should create IAM role for Step Functions with correct permissions', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'AccountTermination-StepFunctions-Role-prod',
        AssumeRolePolicyDocument: {
          Statement: [{
            Action: 'sts:AssumeRole',
            Effect: 'Allow',
            Principal: {
              Service: 'states.amazonaws.com'
            }
          }]
        }
      });
    });
  });

  describe('Lambda Functions', () => {
    it('should create Pre-Check Lambda function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'AccountTermination-PreCheck-prod',
        Runtime: 'python3.12',
        Handler: 'index.lambda_handler',
        MemorySize: 512,
        Timeout: 300
      });
    });

    it('should create Account Management Lambda function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'AccountTermination-AccountManagement-prod',
        Runtime: 'python3.12',
        Handler: 'index.lambda_handler',
        MemorySize: 1024,
        Timeout: 600
      });
    });

    it('should create Metadata Update Lambda function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'AccountTermination-MetadataUpdate-prod',
        Runtime: 'python3.12',
        Handler: 'index.lambda_handler',
        MemorySize: 256,
        Timeout: 180
      });
    });

    it('should create Decommission Lambda function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'AccountTermination-Decommission-prod',
        Runtime: 'python3.12',
        Handler: 'index.lambda_handler',
        MemorySize: 512,
        Timeout: 900
      });
    });
  });

  describe('VPC Configuration', () => {
    it('should create VPC with correct configuration', () => {
      template.hasResourceProperties('AWS::EC2::VPC', {
        CidrBlock: '10.0.0.0/16',
        EnableDnsHostnames: true,
        EnableDnsSupport: true
      });
    });

    it('should create private subnets for Lambda functions', () => {
      template.resourceCountIs('AWS::EC2::Subnet', 4); // 2 public + 2 private
    });

    it('should create NAT gateway for private subnet internet access', () => {
      template.resourceCountIs('AWS::EC2::NatGateway', 2); // Production uses 2 NAT gateways
    });
  });

  describe('DynamoDB Table', () => {
    it('should create DynamoDB table with correct configuration', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'AccountTermination-Metadata-prod',
        BillingMode: 'PAY_PER_REQUEST',
        SSESpecification: {
          SSEEnabled: true
        },
        PointInTimeRecoverySpecification: {
          PointInTimeRecoveryEnabled: true
        }
      });
    });

    it('should create Global Secondary Index for status queries', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        GlobalSecondaryIndexes: [{
          IndexName: 'StatusIndex',
          KeySchema: [
            { AttributeName: 'status', KeyType: 'HASH' },
            { AttributeName: 'terminationInitiated', KeyType: 'RANGE' }
          ]
        }]
      });
    });
  });

  describe('Security Groups', () => {
    it('should create security groups for each Lambda function', () => {
      template.resourceCountIs('AWS::EC2::SecurityGroup', 4); // 4 Lambda SGs (no default VPC SG counted)
    });

    it('should configure restrictive security group for Metadata Update Lambda', () => {
      template.hasResourceProperties('AWS::EC2::SecurityGroup', {
        GroupName: 'AccountTermination-MetadataUpdate-prod-SG',
        SecurityGroupEgress: [{
          CidrIp: '0.0.0.0/0',
          Description: 'HTTPS access for AWS services',
          FromPort: 443,
          IpProtocol: 'tcp',
          ToPort: 443
        }]
      });
    });
  });

  describe('IAM Roles and Policies', () => {
    it('should create IAM roles for all Lambda functions', () => {
      // Count IAM roles: 4 Lambda roles + 1 Step Functions role + 1 Management Account role
      template.resourceCountIs('AWS::IAM::Role', 6);
    });

    it('should configure least privilege permissions for Pre-Check Lambda', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'AccountTermination-PreCheck-prod-Role',
        AssumeRolePolicyDocument: {
          Statement: [{
            Action: 'sts:AssumeRole',
            Effect: 'Allow',
            Principal: {
              Service: 'lambda.amazonaws.com'
            }
          }]
        }
      });
    });
  });

  describe('Outputs', () => {
    it('should export Step Functions ARN', () => {
      template.hasOutput('StepFunctionsArn', {
        Export: {
          Name: 'AccountTermination-StepFunctions-Arn-TestStack'
        }
      });
    });

    it('should export all Lambda function ARNs', () => {
      template.hasOutput('preCheckLambdaArn', {
        Export: {
          Name: 'AccountTermination-preCheckLambda-Arn-TestStack'
        }
      });

      template.hasOutput('accountManagementLambdaArn', {
        Export: {
          Name: 'AccountTermination-accountManagementLambda-Arn-TestStack'
        }
      });

      template.hasOutput('metadataUpdateLambdaArn', {
        Export: {
          Name: 'AccountTermination-metadataUpdateLambda-Arn-TestStack'
        }
      });

      template.hasOutput('decommissionLambdaArn', {
        Export: {
          Name: 'AccountTermination-decommissionLambda-Arn-TestStack'
        }
      });
    });

    it('should export DynamoDB table information', () => {
      template.hasOutput('MetadataTableName', {
        Export: {
          Name: 'AccountTermination-Metadata-Table-Name-TestStack'
        }
      });

      template.hasOutput('MetadataTableArn', {
        Export: {
          Name: 'AccountTermination-Metadata-Table-Arn-TestStack'
        }
      });
    });
  });
});