# AWS Account Termination Solution - Deployment Guide

## 🚀 Quick Start

### Prerequisites

1. **AWS CLI** configured with appropriate permissions
2. **Node.js 18+** and npm installed
3. **AWS CDK** installed globally: `npm install -g aws-cdk`
4. **Python 3.12** (for Lambda functions)

### One-Command Deployment

```bash
# Clone and deploy
git clone <repository-url>
cd aws-account-termination
cp .env.example .env
# Edit .env with your configuration
./deploy.sh
```

## 📋 Detailed Deployment Steps

### 1. Environment Setup

```bash
# Install dependencies
npm install

# Copy environment template
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env` file with your specific configuration:

```bash
# Required
AWS_REGION=us-east-1
ENVIRONMENT=prod
NOTIFICATION_EMAIL=admin@company.com
MANAGEMENT_ACCOUNT_ROLE_ARN=arn:aws:iam::MGMT-ACCOUNT:role/AccountTermination-ManagementAccount-Role
SUSPENDED_OU_ID=ou-root-suspended123

# Optional
VPC_ID=vpc-existing123
PRIVATE_SUBNET_IDS=subnet-123,subnet-456
PRISMA_API_KEY=your-key
PRISMA_SECRET_KEY=your-secret
```

### 3. Pre-Deployment Validation

```bash
# Build and test
npm run build
npm test

# Validate CDK template
npm run synth
```

### 4. Deploy Infrastructure

```bash
# Automated deployment
./deploy.sh

# Or manual deployment
cdk deploy AccountTerminationStack \
  --context environment=prod \
  --parameters managementAccountRoleArn=arn:aws:iam::MGMT:role/Role \
  --parameters suspendedOuId=ou-root-123 \
  --parameters notificationEmail=admin@company.com
```

## 🔧 Configuration Options

### Environment-Specific Deployments

```bash
# Development
ENVIRONMENT=dev ./deploy.sh

# Staging
ENVIRONMENT=staging ./deploy.sh

# Production (default)
ENVIRONMENT=prod ./deploy.sh
```

### Custom VPC Deployment

```bash
# Use existing VPC
export VPC_ID=vpc-12345678
export PRIVATE_SUBNET_IDS=subnet-123,subnet-456
./deploy.sh
```

### Multi-Region Deployment

```bash
# Deploy to different regions
AWS_REGION=us-west-2 ./deploy.sh
AWS_REGION=eu-west-1 ./deploy.sh
```

## 🏗️ Infrastructure Components

### Created Resources

- **Step Functions State Machine**: Orchestrates the workflow
- **4 Lambda Functions**: Pre-check, Account Management, Metadata Update, Decommission
- **DynamoDB Table**: Stores account termination metadata
- **VPC & Networking**: Secure network isolation
- **IAM Roles & Policies**: Least-privilege access
- **CloudWatch Logs & Alarms**: Monitoring and alerting
- **SNS Topic**: Notifications

### Resource Naming Convention

```
AccountTermination-{Component}-{Environment}
```

Examples:
- `AccountTermination-PreCheck-prod`
- `AccountTermination-Workflow-staging`
- `AccountTermination-Metadata-dev`

## 🔐 Security Configuration

### IAM Roles Setup

1. **Management Account Role** (in Organizations management account):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "organizations:ListParents",
        "organizations:MoveAccount",
        "organizations:CloseAccount",
        "organizations:DescribeAccount"
      ],
      "Resource": "*"
    }
  ]
}
```

2. **Target Account Role** (in each account to be terminated):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVolumes",
        "rds:DescribeDBInstances"
      ],
      "Resource": "*"
    }
  ]
}
```

### Network Security

- All Lambda functions deployed in private subnets
- Security groups with minimal required access
- VPC endpoints for AWS services
- No direct internet access except for third-party APIs

## 📊 Monitoring & Observability

### CloudWatch Alarms

- Lambda function errors and duration
- Step Functions execution failures
- DynamoDB throttling

### Logging

- Structured JSON logging
- Correlation IDs for tracing
- Configurable log levels
- Centralized log aggregation

### Metrics

- Execution success/failure rates
- Processing times
- Resource utilization

## 🧪 Testing

### Pre-Deployment Testing

```bash
# Unit tests
npm test

# Integration tests
npm run test:integration

# Property-based tests
npm run test:property
```

### Post-Deployment Validation

```bash
# Test with dummy account
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:region:account:stateMachine:AccountTermination-Workflow-prod \
  --input '{"accountId":"999999999999"}' \
  --name "test-execution-$(date +%s)"
```

## 🔄 Updates & Maintenance

### Updating the Solution

```bash
# Pull latest changes
git pull origin main

# Update dependencies
npm update

# Deploy updates
./deploy.sh
```

### Rolling Back

```bash
# Rollback to previous version
cdk deploy AccountTerminationStack --rollback
```

### Monitoring Health

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name AccountTerminationStack

# View recent executions
aws stepfunctions list-executions \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --max-items 10
```

## 🚨 Troubleshooting

### Common Issues

1. **CDK Bootstrap Required**
```bash
cdk bootstrap aws://ACCOUNT-ID/REGION
```

2. **Insufficient Permissions**
- Verify IAM roles and policies
- Check cross-account trust relationships

3. **VPC Configuration Issues**
- Ensure private subnets have NAT gateway access
- Verify security group rules

4. **Lambda Timeout Issues**
- Check CloudWatch logs for specific errors
- Increase timeout if necessary

### Debug Commands

```bash
# View CloudWatch logs
aws logs tail /aws/stepfunctions/AccountTermination-prod --follow

# Check Lambda function logs
aws logs tail /aws/lambda/AccountTermination-PreCheck-prod --follow

# Describe failed execution
aws stepfunctions describe-execution --execution-arn <EXECUTION_ARN>
```

## 📞 Support

For issues and questions:

1. Check CloudWatch logs for detailed error messages
2. Review the troubleshooting section above
3. Verify environment configuration
4. Test with a non-production account first

## 🔒 Security Best Practices

1. **Principle of Least Privilege**: All IAM roles follow minimal permissions
2. **Network Isolation**: Lambda functions in private subnets
3. **Encryption**: Data encrypted in transit and at rest
4. **Audit Logging**: All actions logged to CloudTrail
5. **Monitoring**: Real-time alerts for failures and anomalies

## 📈 Performance Optimization

1. **Reserved Concurrency**: Prevents runaway executions
2. **Dead Letter Queues**: Handles failed invocations
3. **Exponential Backoff**: Retry logic with jitter
4. **Connection Pooling**: Optimized AWS SDK usage
5. **Memory Optimization**: Right-sized Lambda functions