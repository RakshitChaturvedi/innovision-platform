import os
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

load_dotenv()

BUCKETS = [
    "innovision-frames",
    "innovision-snapshots",
    "innovision-evidence",
    "innovision-reports",
]

"""
Object Key Conventions:
    innovision-frames --> frames/{camera_id}/{frame_seq:08d}.jpg
    innovision-snapshots --> uc1/alerts/{date}/{alert_id}.jpg
    innovision-evidence --> incidents/{incident_id}/{file_name}
    innovision-reports --> {year}/{month}/{report_id}.pdf
"""

def create_buckets() -> None:
    client = Minio(
        endpoint=os.environ.get("MINIO_HOST_ENDPOINT","localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY"),
        secret_key=os.environ.get("MINIO_SECRET_KEY"),
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true"
    )

    for bucket in BUCKETS:
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                print(f"Created: {bucket}")
            else:
                print(f"Exists: {bucket}")
        except S3Error as e:
            print(f"Error: {bucket}:{e}")
            raise
    print("\nAll buckets ready.")

if __name__=="__main__":
    create_buckets()