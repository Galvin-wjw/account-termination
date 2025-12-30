#!/bin/bash

# AWS Account Termination Solution Deployment Script
# This script deploys the solution with proper configuration validation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="AccountTerminationStack"
ENVIRONMENT="${ENVIRONMENT:-prod}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo -e "${BLUE}🚀 AWS Account Termination Solution Deployment${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "Environment: ${GREEN}${ENVIRONMENT}${NC}"
echo -e "Region: ${GREEN}${AWS_REGION}${NC}"
echo -e "Stack Name: ${GREEN}${STACK_NAME}${NC}"
echo ""

# Function to check if AWS CLI is configured
check_aws_cli() {
    echo -e "${BLUE}🔍 Checking AWS CLI configuration...${NC}"
    
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}❌ AWS CLI is not installed${NC}"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}❌ AWS CLI is not configured or credentials are invalid${NC}"
        exit 1
    fi
    
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    echo -e "${GREEN}✅ AWS CLI configured for account: ${ACCOUNT_ID}${NC}"
}

# Function to check if CDK is installed and bootstrapped
check_cdk() {
    echo -e "${BLUE}🔍 Checking CDK installation...${NC}"
    
    if ! command -v cdk &> /dev/null; then
        echo -e "${RED}❌ AWS CDK is not installed${NC}"
        echo -e "${YELLOW}💡 Install with: npm install -g aws-cdk${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ CDK is installed: $(cdk --version)${NC}"
    
    # Check if CDK is bootstrapped
    echo -e "${BLUE}🔍 Checking CDK bootstrap status...${NC}"
    if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region ${AWS_REGION} &> /dev/null; then
        echo -e "${YELLOW}⚠️  CDK is not bootstrapped in region ${AWS_REGION}${NC}"
        echo -e "${BLUE}🔧 Bootstrapping CDK...${NC}"
        cdk bootstrap aws://${ACCOUNT_ID}/${AWS_REGION}
    else
        echo -e "${GREEN}✅ CDK is bootstrapped${NC}"
    fi
}

# Function to validate environment variables
validate_environment() {
    echo -e "${BLUE}🔍 Validating environment configuration...${NC}"
    
    MISSING_VARS=()
    
    # Optional but recommended variables
    if [[ -z "${MANAGEMENT_ACCOUNT_ROLE_ARN}" ]]; then
        echo -e "${YELLOW}⚠️  MANAGEMENT_ACCOUNT_ROLE_ARN not set${NC}"
    fi
    
    if [[ -z "${SUSPENDED_OU_ID}" ]]; then
        echo -e "${YELLOW}⚠️  SUSPENDED_OU_ID not set${NC}"
    fi
    
    if [[ -z "${NOTIFICATION_EMAIL}" ]]; then
        echo -e "${YELLOW}⚠️  NOTIFICATION_EMAIL not set${NC}"
    fi
    
    if [[ -z "${VPC_ID}" ]]; then
        echo -e "${YELLOW}⚠️  VPC_ID not set - will create new VPC${NC}"
    fi
    
    if [[ ${#MISSING_VARS[@]} -eq 0 ]]; then
        echo -e "${GREEN}✅ Environment validation completed${NC}"
    else
        echo -e "${YELLOW}⚠️  Some optional environment variables are not set${NC}"
        echo -e "${YELLOW}   The deployment will continue with default values${NC}"
    fi
}

# Function to build the project
build_project() {
    echo -e "${BLUE}🔨 Building project...${NC}"
    
    if ! npm run build; then
        echo -e "${RED}❌ Build failed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Build completed successfully${NC}"
}

# Function to run tests
run_tests() {
    echo -e "${BLUE}🧪 Running tests...${NC}"
    
    if ! npm test; then
        echo -e "${RED}❌ Tests failed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ All tests passed${NC}"
}

# Function to synthesize CDK template
synthesize_template() {
    echo -e "${BLUE}🔧 Synthesizing CDK template...${NC}"
    
    if ! cdk synth ${STACK_NAME} --context environment=${ENVIRONMENT}; then
        echo -e "${RED}❌ CDK synthesis failed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ CDK synthesis completed${NC}"
}

# Function to deploy the stack
deploy_stack() {
    echo -e "${BLUE}🚀 Deploying stack...${NC}"
    
    # Prepare context parameters
    CONTEXT_PARAMS="--context environment=${ENVIRONMENT}"
    
    if [[ -n "${VPC_ID}" ]]; then
        CONTEXT_PARAMS="${CONTEXT_PARAMS} --context vpcId=${VPC_ID}"
    fi
    
    if [[ -n "${PRIVATE_SUBNET_IDS}" ]]; then
        CONTEXT_PARAMS="${CONTEXT_PARAMS} --context privateSubnetIds=${PRIVATE_SUBNET_IDS}"
    fi
    
    # Prepare parameters
    PARAMETERS=""
    
    if [[ -n "${MANAGEMENT_ACCOUNT_ROLE_ARN}" ]]; then
        PARAMETERS="${PARAMETERS} --parameters managementAccountRoleArn=${MANAGEMENT_ACCOUNT_ROLE_ARN}"
    fi
    
    if [[ -n "${SUSPENDED_OU_ID}" ]]; then
        PARAMETERS="${PARAMETERS} --parameters suspendedOuId=${SUSPENDED_OU_ID}"
    fi
    
    if [[ -n "${NOTIFICATION_EMAIL}" ]]; then
        PARAMETERS="${PARAMETERS} --parameters notificationEmail=${NOTIFICATION_EMAIL}"
    fi
    
    # Deploy with confirmation
    echo -e "${YELLOW}📋 Deployment Summary:${NC}"
    echo -e "   Stack: ${STACK_NAME}"
    echo -e "   Environment: ${ENVIRONMENT}"
    echo -e "   Region: ${AWS_REGION}"
    echo -e "   Account: ${ACCOUNT_ID}"
    echo ""
    
    read -p "Do you want to proceed with deployment? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}⏹️  Deployment cancelled${NC}"
        exit 0
    fi
    
    # Execute deployment
    if cdk deploy ${STACK_NAME} ${CONTEXT_PARAMS} ${PARAMETERS} --require-approval never; then
        echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
        
        # Display outputs
        echo -e "${BLUE}📋 Stack Outputs:${NC}"
        aws cloudformation describe-stacks \
            --stack-name ${STACK_NAME} \
            --region ${AWS_REGION} \
            --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
            --output table
    else
        echo -e "${RED}❌ Deployment failed${NC}"
        exit 1
    fi
}

# Function to display post-deployment instructions
post_deployment_instructions() {
    echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
    echo ""
    echo -e "${BLUE}📋 Next Steps:${NC}"
    echo -e "1. Configure environment variables in Lambda functions if needed"
    echo -e "2. Set up the AccountTerminationRole in target accounts"
    echo -e "3. Test the workflow with a non-production account"
    echo -e "4. Monitor CloudWatch logs and alarms"
    echo ""
    echo -e "${BLUE}🔗 Useful Commands:${NC}"
    echo -e "   View stack: aws cloudformation describe-stacks --stack-name ${STACK_NAME}"
    echo -e "   Execute workflow: aws stepfunctions start-execution --state-machine-arn <ARN> --input '{\"accountId\":\"123456789012\"}'"
    echo -e "   View logs: aws logs tail /aws/stepfunctions/AccountTermination-${ENVIRONMENT} --follow"
    echo ""
}

# Main execution
main() {
    check_aws_cli
    check_cdk
    validate_environment
    build_project
    run_tests
    synthesize_template
    deploy_stack
    post_deployment_instructions
}

# Handle script interruption
trap 'echo -e "\n${RED}❌ Deployment interrupted${NC}"; exit 1' INT TERM

# Execute main function
main "$@"