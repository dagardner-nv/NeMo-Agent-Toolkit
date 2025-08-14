# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pydantic import Field

from nat.data_models.component_ref import EmbedderRef
from nat.data_models.memory import MemoryBaseConfig


class RedisMemoryClientConfig(MemoryBaseConfig, name="redis_memory"):
    host: str = Field(default="localhost", description="Redis server host")
    db: int = Field(default=0, description="Redis DB")
    port: int = Field(default=6379, description="Redis server port")
    key_prefix: str = Field(default="nat", description="Key prefix to use for redis keys")
    embedder: EmbedderRef = Field(description=("Instance name of the memory client instance from the workflow "
                                               "configuration object."))
