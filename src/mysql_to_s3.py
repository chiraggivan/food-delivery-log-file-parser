# File: mysql_to_s3.py

import mysql.connector
from mysql.connector import errorcode
import pandas as pd
import boto3
import logging
from datetime import datetime
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  

# S3 bucket and key for last extract timestamp
TIMESTAMP_BUCKET = "test.complete.food-delivery"
TIMESTAMP_KEY = "location/csv/last_extract.txt"

# Step 1: Read the last extracted timestamp from S3
def get_last_extract_timestamp(s3_client, table):
    try:
        obj = s3_client.get_object(Bucket=TIMESTAMP_BUCKET, Key=f"{table}/csv/last_extract.txt")
        logger.info(f'Last extract date file found in csv folder of {table} entity.')
        return obj['Body'].read().decode('utf-8').strip()
    except s3_client.exceptions.NoSuchKey:
        logger.warning(f'Extract date file NOT found in csv folder of {table} entity. Returning default timestamp: 1970-01-01 00:00:00')
        return "1970-01-01 00:00:00"
    except s3_client.exceptions.NoSuchBucket:
        logger.error(f"The bucket {TIMESTAMP_BUCKET} does not exist.")
        return "1970-01-01 00:00:00"
    except ClientError as e:
        logger.error(f"Error accessing S3: {e}")
        return "1970-01-01 00:00:00"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return "1970-01-01 00:00:00"

# Step 2: Save the new last extracted timestamp to S3
def save_last_extract_timestamp(s3_client, timestamp, table):
    try:
        s3_client.put_object(Bucket=TIMESTAMP_BUCKET, Key=f"{table}/csv/last_extract.txt", Body=timestamp)
        logger.info('New date saved in last extracted file.')
    except Exception as e:
        logger.error(f"Error saving last extract timestamp: {e}")

# Step 3: Read the parameter values stored in system manager
def get_para(ssm_client, para_name):
    try:
        parameter = ssm_client.get_parameter(Name=para_name, WithDecryption=True)
        logger.info(f'{para_name} found in System Manager.')
        return parameter['Parameter']['Value']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            logger.warning(f'Error: {para_name} not found in Systems Manager.')
        else:
            logger.error(f'Error fetching {para_name}: {e}')
        return ''

def lambda_handler(event, context):
    # Initialize AWS clients
    s3_client = boto3.client("s3")
    ssm_client = boto3.client("ssm")

    logger.info('AWS clients initialized (S3 and SSM).')

    rds_username = get_para(ssm_client, '/foodDelivery/rds/username')
    rds_password = get_para(ssm_client, '/foodDelivery/rds/password')

    if rds_username and rds_password:
        logger.info('RDS username and password retrieved from System Manager.')
    else:
        logger.error('Failed to retrieve RDS credentials from System Manager.')

    # Step 4: Connect to MySQL
    try:
        conn = mysql.connector.connect(
            host="mysqldatabase.cb8ewcagm8cm.eu-north-1.rds.amazonaws.com",
            user=rds_username,  
            password=rds_password,  
            database="food_test_db"
        )
        logger.info('Connected to MySQL AWS RDS successfully.')

        tables = ['location','customer']

        for table in tables:
            logger.info(f'Processing table: {table}')
            last_extract = get_last_extract_timestamp(s3_client, table)

            query = f"""
            SELECT *
            FROM {table}
            WHERE (modifiedDate > '{last_extract}'
                OR (modifiedDate IS NULL AND createdDate > '{last_extract}'))
            """
            try:
                df = pd.read_sql(query, conn)
                logger.info(f'Dataframe created from MySQL query for {table} entity.')

                if not df.empty:
                    logger.info('Dataframe is not empty, processing CSV export.')

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    local_file = f"/tmp/{table}_data_{timestamp}.csv"
                    df.to_csv(local_file, index=False)
                    logger.info(f'CSV file created and saved in /tmp: {local_file}')

                    # Step 7: Upload the CSV to S3
                    s3_key = f"{table}/csv/{table}_data_{timestamp}.csv"
                    s3_client.upload_file(local_file, TIMESTAMP_BUCKET, s3_key)
                    logger.info(f'CSV file uploaded to S3: {s3_key}')

                    # Step 8: Update the last extracted timestamp
                    latest_timestamp = df['modifiedDate'].fillna(df['createdDate']).max()
                    save_last_extract_timestamp(s3_client, str(latest_timestamp), table)
                    logger.info(f'Updated last extracted timestamp for {table} entity.')

                    #conn.close()
                    logger.info(f"Uploaded {local_file} to s3://{TIMESTAMP_BUCKET}/{s3_key}")

                else:
                    logger.info(f'BUT Dataframe is empty for {table} entity. No new or updated data to extract.')

                    #conn.close()
                    #logger.info('MySQL connection closed.')      

            except Exception as e:
                logger.error(f'Error executing query and processing data: {e}')
                conn.close()

        conn.close() # closing connectiion after fetching data from all the tables
        logger.info('MySQL connection closed after fetching all tables.')
        return {
                    "statusCode": 200,
                    "body": f"MySQL connection closed after fetching all tables."
                }
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("MySQL Error: Invalid username or password.")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logger.error("MySQL Error: Database does not exist.")
        else:
            logger.error(f"MySQL Error: {err}")
