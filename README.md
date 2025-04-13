# Error Logging for Food Delivery Data Pipeline

## Overview

This project extends the existing [End-to-End Data Engineering Project for a Food Delivery Company](https://github.com/chiraggivan/DE-food-delivery) by adding an error logging mechanism. The goal is to capture errors (e.g., database connection failures, S3 upload issues) from the food delivery data pipeline, log them to a CSV file, and store the CSV in an S3 bucket. This enhances the pipeline’s monitoring and debugging capabilities, ensuring issues can be identified and resolved quickly.

The error logging system uses a CloudWatch subscription filter to capture error logs from the original pipeline’s Lambda function (`mysql-to-s3`), processes them using a new Lambda function (`RDStoS3LogFileParser`), and saves the error details in a CSV file in an S3 bucket.

### Key Features
- **Error Detection**: Captures errors from the original pipeline using CloudWatch Logs.
- **Subscription Filter**: Filters error logs with a CloudWatch subscription filter.
- **Error Logging**: Saves error details (timestamp, error message, source) to a CSV file in S3.
- **Scalability**: Appends new errors to the existing CSV, maintaining a historical log.

---

## Architecture Diagram

Below is the architecture diagram for the error logging addition, integrated with the original pipeline:

![Error Logging Architecture Diagram](/src/architecture.png)

1. **Original Pipeline**:
   - The `RDStoS3function` Lambda function extracts data from MySQL (RDS) and uploads it to S3, triggered every 4 hours by EventBridge.
   - Logs (including errors) are sent to CloudWatch Logs under `/aws/lambda/RDStoS3function`.
2. **Error Logging Addition**:
   - A CloudWatch subscription filter (`ErrorLogFilter`) captures error logs (e.g., “ERROR” level) from the `RDStoS3function` log group.
   - The subscription filter triggers the `RDStoS3LogFileParser` Lambda function.
   - `RDStoS3LogFileParser` processes the error logs and appends them to `error_log.csv` in the S3 bucket (`mysql-s3-transfer-bucket`) under the `error_logs` folder.

## Technologies Used

### AWS Services:
  -  CloudWatch Logs: For storing pipeline logs.
  -  CloudWatch Subscription Filter: For filtering error logs.
  -  Lambda: For processing error logs (RDStoS3LogFileParser).
  -  S3: For storing the error log CSV.
  -  
### Python Libraries:
  -  boto3: For interacting with S3.
  - pandas: For handling CSV data.
  - gzip, base64: For decoding CloudWatch Logs data.
  - logging: For logging errors in the original Lambda function.


## Project Setup

### Prerequisites
- An AWS account with the original pipeline set up (see [DE-food-delivery](https://github.com/chiraggivan/DE-food-delivery)).
- The `mysql-s3-transfer-bucket` S3 bucket already created.
- Python 3.11 for Lambda functions.
- Required Python libraries: `boto3`, `pandas`, `gzip`, `base64`.

### Steps to Set Up the Error Logging System

#### 1. Modify the Original Lambda Function to Log Errors
- Update the `lambda_function.py` (from the original project) to use Python’s `logging` module for error logging.
- Example:
  ```python
  import logging

  # Configure logging
  logging.basicConfig(level=logging.INFO)
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.INFO)  

  try:
      # Database connection or S3 upload code
      logger.info('Connected to MySQL AWS RDS successfully.')
  except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("MySQL Error: Invalid username or password.")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logger.error("MySQL Error: Database does not exist.")
        else:
            logger.error(f"MySQL Error: {err}")
  ```
-  Complete python file is here : [mysql_to_s3.py](/src/mysql_to_s3.py)
    
#### 2. Create the Error Logging Lambda Function
-  Create a new Lambda function named `RDStoS3LogFileParser`.
-  **Decodes CloudWatch Logs**: It receives log data from CloudWatch via a subscription filter, decodes the base64-encoded and gzip-compressed payload, and converts it into a readable string format.
-  **Formats Log Messages**: It processes each log event, extracting the timestamp and message, formats them into a readable string (e.g., "YYYY-MM-DD HH:MM:SS - message"), and replaces tab characters with spaces for consistency.
-  **Saves to S3**: It joins the formatted messages with newlines, creates a timestamped text file (e.g., summary_20250412_103022.txt), and saves it to the S3 bucket (rds-to-s3-log-summaries-bucket) in the error_warning_logs folder, returning the number of messages saved or a message if no logs are found.
-  Example
  ``` python
messages = []
    for event in log_events:
        timestamp = datetime.utcfromtimestamp(event["timestamp"] / 1000).strftime('%Y-%m-%d %H:%M:%S') 
        message = event["message"].replace("\t", " ").strip()
        messages.append(f"{timestamp} - {message}")

if messages:
    formatted_log = "\n".join(messages)  
    s3_client.download_file(ERROR_BUCKET_NAME, ERROR_LOG_FILE, '/tmp/error_warning_log.txt')
    with open('/tmp/error_warning_log.txt', 'r') as f:
      existing_log = f.read()
    updated_log = existing_log + formatted_log

 s3_client.put_object(
    Bucket='rds-to-s3-log-summaries-bucket',
    Key=s3_key,
    Body=formatted_log.encode('utf-8')
    )
  ```
-  Complete python file is here : [RDStoS3LogFileParser.py](/src/RDStoS3LogFileParser.py)

#### 3. Set Up the CloudWatch Subscription Filter
-  Go to CloudWatch > Log Groups > /aws/lambda/RDStoS3function.
-  Create a subscription filter:
    -  Desitination Lambda Function Name: `RDStoS3LogFileParser`
    -  Log Format: `space delimited`
    -  Filter Pattern: `?WARNING ?ERROR` 
    -  Filter Name: ErrorLogFilter
-  Save the subscription filter.

#### 4. Test the Error Logging System
-  Introduce an error in the `RDStoS3function` Lambda function (e.g., incorrect MySQL password).
-  Trigger the mysql-to-s3 Lambda function.
-  Verify that the error is logged in CloudWatch Logs.
-  Check that the subscription filter triggers RDStoS3LogFileParser.
-  Confirm that error_log.csv is created in s3://mysql-s3-transfer-bucket/error_logs/ with the error details:

#### Future Enhancements
-  Add SNS notifications to alert the team when new errors are logged.
-  Create a dashboard in CloudWatch or Tableau to visualize error trends.
-  Implement log rotation for the error CSV to manage file size over time.
