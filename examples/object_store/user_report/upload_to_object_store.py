#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import mimetypes
import sys
from pathlib import Path

import click

from nat.object_store.models import ObjectStoreItem
from nat.plugins.mysql.mysql_object_store import MySQLObjectStore
from nat.plugins.mysql.mysql_object_store import MySQLObjectStoreClientConfig
from nat.plugins.redis.redis_object_store import RedisObjectStore
from nat.plugins.redis.redis_object_store import RedisObjectStoreClientConfig
from nat.plugins.s3.object_store import S3ObjectStoreClientConfig
from nat.plugins.s3.s3_object_store import S3ObjectStore


async def upload_file(object_store: S3ObjectStore | MySQLObjectStore | RedisObjectStore, file_path: Path, key: str):
    """
    Upload a single file to S3/Minio using S3ObjectStore.

    Args:
        object_store: The S3ObjectStore instance to use.
        file_path: The path to the file to upload.
        key: The key to upload the file to.
    """
    try:
        with open(file_path, "rb") as f:
            data = f.read()

        # Detect content type
        content_type, _ = mimetypes.guess_type(str(file_path))

        # Create ObjectStoreItem
        item = ObjectStoreItem(data=data,
                               content_type=content_type,
                               metadata={
                                   "original_filename": file_path.name, "file_size": str(len(data))
                               })

        # Upload using upsert to allow overwriting
        await object_store.upsert_object(key, item)
        print(f"✅ Uploaded: {file_path.name} -> {key}")

    except Exception as e:
        print(f"❌ Failed to upload {file_path.name}: {e}")
        raise


async def upload_directory(source_dir: Path, object_store: S3ObjectStore | MySQLObjectStore | RedisObjectStore):
    """
    Upload all files from a directory to S3/Minio using AIQ S3ObjectStore.

    Args:
        source_dir: The local directory to upload.
        bucket_name: The name of the bucket to upload to.
        object_store: The object store to use.
    """

    try:
        async with object_store as store:
            print(f"📁 Processing directory: {source_dir}")
            file_count = 0

            # Process each file recursively
            for file_path in source_dir.rglob('*'):
                if file_path.is_file():
                    relative_path = str(file_path.relative_to(source_dir))
                    # Construct the key with bucket prefix
                    key = relative_path

                    await upload_file(store, file_path, key)
                    file_count += 1

            print(f"✅ Upload completed successfully! {file_count} files uploaded.")
            return 0

    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return 1


@click.command()
@click.option('--store-type',
              type=click.Choice(['s3', 'mysql', 'redis'], case_sensitive=False),
              help='Object store type',
              required=True)
@click.option('--local-dir',
              type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
              help='Directory to upload',
              required=True)
@click.option('--bucket-name', type=str, help='Bucket name', required=True)
@click.option('--host', type=str, help='MySQL or Redis host (optional)')
@click.option('--port', type=int, help='MySQL or Redis port (optional)')
@click.option('--db', type=int, help='Redis db index (optional)')
@click.option('--username', type=str, help='MySQL username (optional)')
@click.option('--password', type=str, help='MySQL password (optional)')
@click.option('--endpoint-url', type=str, help='S3 endpoint URL (optional)')
@click.option('--access-key', type=str, help='S3 access key (optional)')
@click.option('--secret-key', type=str, help='S3 secret key (optional)')
@click.option('--region', type=str, help='S3 region (optional)')
@click.help_option('--help', '-h')
def main(store_type: str,
         local_dir: Path,
         bucket_name: str,
         host: str | None,
         port: int | None,
         db: int | None,
         username: str | None,
         password: str | None,
         endpoint_url: str | None,
         access_key: str | None,
         secret_key: str | None,
         region: str | None):

    all_args = {
        "bucket_name": bucket_name,
        "host": host,
        "port": port,
        "db": db,
        "username": username,
        "password": password,
        "endpoint_url": endpoint_url,
        "access_key": access_key,
        "secret_key": secret_key,
        "region": region
    }

    object_store: S3ObjectStore | MySQLObjectStore | RedisObjectStore | None = None

    # Remove all None values
    all_args = {k: v for k, v in all_args.items() if v is not None}

    if store_type == "s3":
        for key in ["host", "port", "db", "username", "password"]:
            assert all_args.pop(key, None) is None, f"{key} is not supported for S3"
        config = S3ObjectStoreClientConfig(**all_args)
        object_store = S3ObjectStore(config)
    elif store_type == "mysql":
        for key in ["endpoint_url", "access_key", "secret_key", "region"]:
            assert all_args.pop(key, None) is None, f"{key} is not supported for MySQL"
        if "username" not in all_args:
            all_args["username"] = "root"
        if "password" not in all_args:
            all_args["password"] = "root"
        config = MySQLObjectStoreClientConfig(**all_args)
        object_store = MySQLObjectStore(config)
    elif store_type == "redis":
        for key in ["host", "port", "db", "username", "password"]:
            assert all_args.pop(key, None) is None, f"{key} is not supported for Redis"
        config = RedisObjectStoreClientConfig(**all_args)
        object_store = RedisObjectStore(config)

    if object_store is None:
        raise ValueError(f"Invalid object store type: {store_type}")

    return asyncio.run(upload_directory(
        source_dir=local_dir,
        object_store=object_store,
    ))


if __name__ == "__main__":
    sys.exit(main())
