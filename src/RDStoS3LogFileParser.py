import boto3
import gzip
import base64
import json
from datetime import datetime

s3_client = boto3.client('s3')

def lambda_handler(event, context):

    # Decode the CloudWatch Logs data
    log_data = event['awslogs']['data']
    compressed_data = base64.b64decode(log_data)
    decompressed_data = gzip.decompress(compressed_data)
    
    # Convert bytes to string
    log_text = decompressed_data.decode('utf-8')

    # Try parsing as JSON
    try:
        log_json = json.loads(log_text)
        log_events = log_json.get('logEvents', [])
    except json.JSONDecodeError:
        print("ERROR: Logs are not in JSON format")
        return {'statusCode': 500, 'body': "Log format error"}

    # Extract structured messages
    messages = []
    for event in log_events:
        timestamp = datetime.utcfromtimestamp(event["timestamp"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        
        # Format message, replace tab characters with spaces
        message = event["message"].replace("\t", " ").strip()
        
        messages.append(f"{timestamp} - {message}")

    # If there are messages, save them to S3
    if messages:
        formatted_log = "\n".join(messages)  # Newline-separated logs
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        s3_key = f"error_warning_logs/summary_{timestamp}.txt"

        s3_client.put_object(
            Bucket='rds-to-s3-log-summaries-bucket',
            Key=s3_key,
            Body=formatted_log.encode('utf-8')
        )

        return {'statusCode': 200, 'body': f"Saved {len(messages)} messages to {s3_key}"}

    return {'statusCode': 200, 'body': "No errors or warnings found in logs"}
