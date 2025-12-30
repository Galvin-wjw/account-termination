import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as stepfunctions from 'aws-cdk-lib/aws-stepfunctions';
import * as stepfunctionsTasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as snsSubscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cloudwatchActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import { Construct } from 'constructs';

export interface AccountTerminationStackProps extends cdk.StackProps {
  readonly vpcId: string; // Required - use existing VPC
  readonly privateSubnetIds?: string[];
  readonly dynamoDbTableName: string; // Required - use existing DynamoDB table
  readonly managementAccountRoleArn?: string;
  readonly suspendedOuId?: string;
  readonly notificationEmail?: string;
  readonly environment?: 'dev' | 'staging' | 'prod';
}

export class AccountTerminationStack extends cdk.Stack {
  public readonly stateMachine: stepfunctions.StateMachine;
  public readonly vpc: ec2.IVpc;

  constructor(scope: Construct, id: string, props: AccountTerminationStackProps) {
    super(scope, id, props);

    const environment = props.environment || 'prod';
    const isProduction = environment === 'prod';

    // Use existing VPC (required)
    this.vpc = ec2.Vpc.fromLookup(this, 'ExistingVPC', { vpcId: props.vpcId });

    // SNS Topic for notifications
    const notificationTopic = new sns.Topic(this, 'NotificationTopic', {
      topicName: `AccountTermination-Notifications-${environment}`,
      displayName: 'Account Termination Notifications',
      fifo: false
    });

    if (props.notificationEmail) {
      notificationTopic.addSubscription(
        new snsSubscriptions.EmailSubscription(props.notificationEmail)
      );
    }

    // Use existing DynamoDB table
    const existingTable = dynamodb.Table.fromTableName(
      this, 
      'ExistingMetadataTable', 
      props.dynamoDbTableName
    );

    // Lambda functions
    const lambdaFunctions = this.createLambdaFunctions(environment, props, existingTable);

    // Step Functions state machine
    this.stateMachine = this.createStateMachine(
      environment, 
      lambdaFunctions, 
      notificationTopic,
      isProduction
    );

    // CloudWatch Alarms for monitoring
    this.createCloudWatchAlarms(lambdaFunctions, this.stateMachine, notificationTopic);

    // Outputs
    this.createOutputs(lambdaFunctions, this.stateMachine, existingTable);

    // Tags
    this.addTags(environment);
  }

  private createLambdaFunctions(environment: string, props: AccountTerminationStackProps, existingTable: dynamodb.ITable) {
    const commonEnvironment = {
      LOG_LEVEL: environment === 'prod' ? 'INFO' : 'DEBUG',
      ENVIRONMENT: environment
    };

    // Pre-Check Lambda
    const preCheckLambda = this.createLambdaFunction({
      id: 'PreCheckLambda',
      functionName: `AccountTermination-PreCheck-${environment}`,
      codePath: 'src/lambdas/pre-check',
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      environment: commonEnvironment,
      description: 'Lambda function for pre-check validation before account termination',
      policies: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['sts:AssumeRole'],
          resources: ['arn:aws:iam::*:role/AccountTerminationRole']
        })
      ]
    });

    // Account Management Lambda
    const accountManagementLambda = this.createLambdaFunction({
      id: 'AccountManagementLambda',
      functionName: `AccountTermination-AccountManagement-${environment}`,
      codePath: 'src/lambdas/account-management',
      timeout: cdk.Duration.minutes(10),
      memorySize: 1024,
      environment: {
        ...commonEnvironment,
        MANAGEMENT_ACCOUNT_ROLE_ARN: props.managementAccountRoleArn || '',
        SUSPENDED_OU_ID: props.suspendedOuId || ''
      },
      description: 'Lambda function for AWS Organizations account management operations',
      policies: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['sts:AssumeRole'],
          resources: [`arn:aws:iam::*:role/AccountTermination-ManagementAccount-Role`],
          conditions: {
            StringEquals: { 'sts:ExternalId': 'AccountTermination' }
          }
        })
      ]
    });

    // Metadata Update Lambda
    const metadataUpdateLambda = this.createLambdaFunction({
      id: 'MetadataUpdateLambda',
      functionName: `AccountTermination-MetadataUpdate-${environment}`,
      codePath: 'src/lambdas/metadata-update',
      timeout: cdk.Duration.minutes(3),
      memorySize: 256,
      environment: {
        ...commonEnvironment,
        DYNAMODB_TABLE_NAME: existingTable.tableName
      },
      description: 'Lambda function for updating account termination metadata in DynamoDB',
      policies: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:GetItem'],
          resources: [existingTable.tableArn, `${existingTable.tableArn}/index/*`]
        })
      ],
      restrictedNetworking: true
    });

    // Decommission Lambda
    const decommissionLambda = this.createLambdaFunction({
      id: 'DecommissionLambda',
      functionName: `AccountTermination-Decommission-${environment}`,
      codePath: 'src/lambdas/decommission',
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      environment: {
        ...commonEnvironment,
        PRISMA_API_URL: 'https://api.prismacloud.io',
        PRISMA_API_KEY: '', // To be configured during deployment
        PRISMA_SECRET_KEY: '' // To be configured during deployment
      },
      description: 'Lambda function for third-party vendor decommissioning operations'
    });

    return {
      preCheckLambda,
      accountManagementLambda,
      metadataUpdateLambda,
      decommissionLambda
    };
  }

  private createLambdaFunction(config: {
    id: string;
    functionName: string;
    codePath: string;
    timeout: cdk.Duration;
    memorySize: number;
    environment: Record<string, string>;
    description: string;
    policies?: iam.PolicyStatement[];
    restrictedNetworking?: boolean;
  }): lambda.Function {
    // Create IAM role
    const role = new iam.Role(this, `${config.id}Role`, {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      roleName: `${config.functionName}-Role`,
      description: `IAM role for ${config.functionName} with least privilege permissions`,
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole')
      ]
    });

    // Add custom policies
    if (config.policies) {
      config.policies.forEach((policy) => {
        role.addToPolicy(policy);
      });
    }

    // Add CloudWatch Logs permissions
    role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
      resources: [`arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/${config.functionName}*`]
    }));

    // Create security group
    const securityGroup = new ec2.SecurityGroup(this, `${config.id}SecurityGroup`, {
      vpc: this.vpc,
      securityGroupName: `${config.functionName}-SG`,
      description: `Security group for ${config.functionName}`,
      allowAllOutbound: !config.restrictedNetworking
    });

    // Add restricted egress for DynamoDB-only access
    if (config.restrictedNetworking) {
      securityGroup.addEgressRule(
        ec2.Peer.anyIpv4(),
        ec2.Port.tcp(443),
        'HTTPS access for AWS services'
      );
    }

    // Create Lambda function
    return new lambda.Function(this, config.id, {
      functionName: config.functionName,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'index.lambda_handler',
      code: lambda.Code.fromAsset(config.codePath),
      role,
      timeout: config.timeout,
      memorySize: config.memorySize,
      vpc: this.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [securityGroup],
      environment: config.environment,
      description: config.description,
      reservedConcurrentExecutions: 10, // Prevent runaway executions
      deadLetterQueue: new sqs.Queue(this, `${config.id}DLQ`, {
        queueName: `${config.functionName}-DLQ`,
        retentionPeriod: cdk.Duration.days(14)
      })
    });
  }

  private createStateMachine(
    environment: string,
    lambdaFunctions: any,
    notificationTopic: sns.Topic,
    isProduction: boolean
  ): stepfunctions.StateMachine {
    // CloudWatch Log Group for Step Functions
    const logGroup = new logs.LogGroup(this, 'StepFunctionsLogGroup', {
      logGroupName: `/aws/stepfunctions/AccountTermination-${environment}`,
      retention: isProduction ? logs.RetentionDays.THREE_MONTHS : logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.RETAIN
    });

    // IAM role for Step Functions
    const role = new iam.Role(this, 'StepFunctionsRole', {
      assumedBy: new iam.ServicePrincipal('states.amazonaws.com'),
      roleName: `AccountTermination-StepFunctions-Role-${environment}`,
      description: 'IAM role for Step Functions state machine with least privilege permissions'
    });

    // Add Lambda invoke permissions
    Object.values(lambdaFunctions).forEach((lambdaFunction: any) => {
      role.addToPolicy(new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['lambda:InvokeFunction'],
        resources: [lambdaFunction.functionArn]
      }));
    });

    // Add SNS publish permissions
    role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['sns:Publish'],
      resources: [notificationTopic.topicArn]
    }));

    // Add CloudWatch Logs permissions
    role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'logs:CreateLogDelivery', 'logs:GetLogDelivery', 'logs:UpdateLogDelivery',
        'logs:DeleteLogDelivery', 'logs:ListLogDeliveries', 'logs:PutResourcePolicy',
        'logs:DescribeResourcePolicies', 'logs:DescribeLogGroups'
      ],
      resources: ['*']
    }));

    role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['logs:PutLogEvents', 'logs:CreateLogGroup', 'logs:CreateLogStream'],
      resources: [logGroup.logGroupArn, `${logGroup.logGroupArn}:*`]
    }));

    // Define Step Functions tasks
    const tasks = this.createStepFunctionsTasks(lambdaFunctions, notificationTopic);

    // Create state machine
    return new stepfunctions.StateMachine(this, 'AccountTerminationStateMachine', {
      stateMachineName: `AccountTermination-Workflow-${environment}`,
      definitionBody: stepfunctions.DefinitionBody.fromChainable(tasks.definition),
      role,
      timeout: cdk.Duration.hours(2), // Increased timeout for production
      comment: 'AWS Account Termination Workflow - Orchestrates safe account termination process',
      logs: {
        destination: logGroup,
        level: stepfunctions.LogLevel.ALL,
        includeExecutionData: true
      },
      tracingEnabled: true
    });
  }

  private createStepFunctionsTasks(lambdaFunctions: any, notificationTopic: sns.Topic) {
    const { preCheckLambda, accountManagementLambda, metadataUpdateLambda, decommissionLambda } = lambdaFunctions;

    // Lambda invoke tasks
    const preCheckTask = new stepfunctionsTasks.LambdaInvoke(this, 'PreCheckTask', {
      lambdaFunction: preCheckLambda,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
      taskTimeout: stepfunctions.Timeout.duration(cdk.Duration.minutes(6))
    });

    const accountManagementTask = new stepfunctionsTasks.LambdaInvoke(this, 'AccountManagementTask', {
      lambdaFunction: accountManagementLambda,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
      taskTimeout: stepfunctions.Timeout.duration(cdk.Duration.minutes(11))
    });

    const metadataUpdateTask = new stepfunctionsTasks.LambdaInvoke(this, 'MetadataUpdateTask', {
      lambdaFunction: metadataUpdateLambda,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
      taskTimeout: stepfunctions.Timeout.duration(cdk.Duration.minutes(4))
    });

    const decommissionTask = new stepfunctionsTasks.LambdaInvoke(this, 'DecommissionTask', {
      lambdaFunction: decommissionLambda,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
      taskTimeout: stepfunctions.Timeout.duration(cdk.Duration.minutes(16))
    });

    // Notification tasks
    const successNotification = new stepfunctionsTasks.SnsPublish(this, 'SuccessNotification', {
      topic: notificationTopic,
      subject: 'Account Termination Completed Successfully',
      message: stepfunctions.TaskInput.fromJsonPathAt('$')
    });

    const failureNotification = new stepfunctionsTasks.SnsPublish(this, 'FailureNotification', {
      topic: notificationTopic,
      subject: 'Account Termination Failed',
      message: stepfunctions.TaskInput.fromJsonPathAt('$')
    });

    const safetyViolationNotification = new stepfunctionsTasks.SnsPublish(this, 'SafetyViolationNotification', {
      topic: notificationTopic,
      subject: 'Account Termination - Safety Violation',
      message: stepfunctions.TaskInput.fromJsonPathAt('$')
    });

    // States
    const failureState = new stepfunctions.Fail(this, 'TerminationFailed', {
      comment: 'Account termination workflow failed'
    });

    const successState = new stepfunctions.Succeed(this, 'TerminationSucceeded', {
      comment: 'Account termination workflow completed successfully'
    });

    const safetyViolationState = new stepfunctions.Fail(this, 'SafetyViolation', {
      comment: 'Account termination halted due to safety violation - critical resources found',
      cause: 'Critical resources (EBS volumes or RDS instances) found in target account'
    });

    // Retry policies
    const retryPolicy = {
      errors: ['Lambda.ServiceException', 'Lambda.AWSLambdaException', 'Lambda.SdkClientException'],
      intervalSeconds: 2,
      maxAttempts: 3,
      backoffRate: 2.0
    };

    // Add retry policies and individual catch blocks
    preCheckTask.addRetry(retryPolicy);
    preCheckTask.addCatch(failureState, {
      errors: ['States.ALL'],
      resultPath: '$.error'
    });

    accountManagementTask.addRetry(retryPolicy);
    accountManagementTask.addCatch(failureState, {
      errors: ['States.ALL'],
      resultPath: '$.error'
    });

    metadataUpdateTask.addRetry(retryPolicy);
    metadataUpdateTask.addCatch(failureState, {
      errors: ['States.ALL'],
      resultPath: '$.error'
    });

    decommissionTask.addRetry(retryPolicy);
    decommissionTask.addCatch(failureState, {
      errors: ['States.ALL'],
      resultPath: '$.error'
    });

    // Safety check
    const safetyCheck = new stepfunctions.Choice(this, 'SafetyCheck', {
      comment: 'Check if account is safe to terminate'
    });

    safetyCheck
      .when(
        stepfunctions.Condition.booleanEquals('$.safeToTerminate', false),
        safetyViolationNotification.next(safetyViolationState)
      )
      .otherwise(
        accountManagementTask
          .next(metadataUpdateTask)
          .next(decommissionTask)
          .next(successNotification)
          .next(successState)
      );

    const definition = preCheckTask.next(safetyCheck);

    return { definition, tasks: { preCheckTask, accountManagementTask, metadataUpdateTask, decommissionTask } };
  }

  private createCloudWatchAlarms(lambdaFunctions: any, stateMachine: stepfunctions.StateMachine, notificationTopic: sns.Topic) {
    // Lambda function alarms
    Object.entries(lambdaFunctions).forEach(([name, lambdaFunction]: [string, any]) => {
      // Error rate alarm
      new cloudwatch.Alarm(this, `${name}ErrorAlarm`, {
        alarmName: `${lambdaFunction.functionName}-ErrorRate`,
        metric: lambdaFunction.metricErrors({
          period: cdk.Duration.minutes(5)
        }),
        threshold: 1,
        evaluationPeriods: 2,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING
      }).addAlarmAction(new cloudwatchActions.SnsAction(notificationTopic));

      // Duration alarm
      new cloudwatch.Alarm(this, `${name}DurationAlarm`, {
        alarmName: `${lambdaFunction.functionName}-Duration`,
        metric: lambdaFunction.metricDuration({
          period: cdk.Duration.minutes(5)
        }),
        threshold: lambdaFunction.timeout.toMilliseconds() * 0.8, // 80% of timeout
        evaluationPeriods: 2,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING
      }).addAlarmAction(new cloudwatchActions.SnsAction(notificationTopic));
    });

    // Step Functions alarms
    new cloudwatch.Alarm(this, 'StateMachineFailedAlarm', {
      alarmName: `${stateMachine.stateMachineName}-Failed`,
      metric: stateMachine.metricFailed({
        period: cdk.Duration.minutes(5)
      }),
      threshold: 1,
      evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING
    }).addAlarmAction(new cloudwatchActions.SnsAction(notificationTopic));
  }

  private createOutputs(lambdaFunctions: any, stateMachine: stepfunctions.StateMachine, existingTable: dynamodb.ITable) {
    // Step Functions ARN
    new cdk.CfnOutput(this, 'StepFunctionsArn', {
      value: stateMachine.stateMachineArn,
      description: 'ARN of the Account Termination Step Functions state machine',
      exportName: `AccountTermination-StepFunctions-Arn-${this.stackName}`
    });

    // Lambda function ARNs
    Object.entries(lambdaFunctions).forEach(([name, lambdaFunction]: [string, any]) => {
      new cdk.CfnOutput(this, `${name}Arn`, {
        value: lambdaFunction.functionArn,
        description: `ARN of the ${name} Lambda function`,
        exportName: `AccountTermination-${name}-Arn-${this.stackName}`
      });
    });

    // DynamoDB table information
    new cdk.CfnOutput(this, 'MetadataTableName', {
      value: existingTable.tableName,
      description: 'Name of the Account Metadata DynamoDB table',
      exportName: `AccountTermination-Metadata-Table-Name-${this.stackName}`
    });

    new cdk.CfnOutput(this, 'MetadataTableArn', {
      value: existingTable.tableArn,
      description: 'ARN of the Account Metadata DynamoDB table',
      exportName: `AccountTermination-Metadata-Table-Arn-${this.stackName}`
    });
  }

  private addTags(environment: string) {
    cdk.Tags.of(this).add('Project', 'AccountTermination');
    cdk.Tags.of(this).add('Environment', environment);
    cdk.Tags.of(this).add('Owner', 'CloudAdministration');
    cdk.Tags.of(this).add('CostCenter', 'Infrastructure');
    cdk.Tags.of(this).add('Compliance', 'Required');
  }
}