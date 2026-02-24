# AWS ECR Setup

Dredge can scan Amazon Elastic Container Registry (ECR) repositories. It uses standard AWS SDK authentication methods.

## Prerequisites

- An AWS Account.
- An IAM User or Role with `ecr:DescribeRepositories` and `ecr:ListImages` permissions.

## IAM Permissions Policy

Create a minimal IAM policy for the Dredge user:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ecr:DescribeRepositories",
                "ecr:ListImages",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:GetRepositoryPolicy",
                "ecr:DescribeImages",
                "ecr:BatchGetImage"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "ecr:GetAuthorizationToken",
            "Resource": "*"
        }
    ]
}
```

## Configuration Steps

1.  **Environment Variables (Recommended)**
    If running Dredge via Docker Compose, pass standard AWS credentials:

    ```yaml
    services:
      dredge:
        environment:
          - AWS_ACCESS_KEY_ID=your_access_key
          - AWS_SECRET_ACCESS_KEY=your_secret_key
          - AWS_REGION=us-east-1
    ```

    Alternatively, mount your `~/.aws` directory:

    ```yaml
    volumes:
      - ~/.aws:/root/.aws:ro
    ```

2.  **Add Registry in Dredge**
    *   Navigate to **Registries**.
    *   Click **"Add Registry"**.
    *   **Name**: `AWS Production`
    *   **Provider**: `ECR`
    *   **Endpoint**: `<account-id>.dkr.ecr.<region>.amazonaws.com` (Used to discover region)
    *   **Username**: Your AWS Access Key ID.
    *   **Password**: Your AWS Secret Access Key.
    *   Click **Save**.

## Troubleshooting

- **"NoAuthToken" Error**: Ensure the container has internet access to reach AWS endpoints.
- **"AccessDenied"**: Double-check the IAM policy attached to the user/role.
